# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prism dashboard - a local-first, zero-dependency web view of your knowledge.

Serves a small single-page UI (lib/dashboard.html) backed by a stdlib
http.server. Reads everything from ~/.prism/ via the same modules the rest of
Prism uses (index, config, registry) plus a read-only peek at prism.db for
activity stats. No external dependencies, no second runtime.

Layout of the view:
  - one section per project (project id + name + path), each listing its engrams
  - a Global section for scope=global engrams
  - Overview (kind/domain/health distribution), Registries, and Archive views

Run via:  prism dashboard [--port N] [--no-open]
"""

import json
import re
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import PRISM_HOME, get_config
from .index import load_index
from .registry import list_registries


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

_CRED_RE = re.compile(r"//[^/@]*@")  # strip user:token@ from a remote URL
_BODY_CAP = 8000  # max chars of engram body shipped to the client


def _prettify(entry_id: str) -> str:
    """Turn a kebab-case engram id into a readable display name."""
    s = (entry_id or "").replace("-", " ").strip()
    return (s[:1].upper() + s[1:]) if s else (entry_id or "")


def _scrub_remote(url: str) -> str:
    """Remove embedded credentials from a git remote URL before exposing it."""
    if not url:
        return ""
    return _CRED_RE.sub("//", url)


def _health(entry: dict, cfg: dict) -> str:
    """Classify an engram relative to the configured thresholds."""
    c = float(entry.get("confidence", 0) or 0)
    if c < cfg.get("archive_threshold", 0.2):
        return "decaying"
    if (c >= cfg.get("publish_min_confidence", 0.7)
            and int(entry.get("evidence_count", 0) or 0) >= cfg.get("publish_min_evidence", 3)):
        return "strong"
    return "active"


def _read_body(rel_path: str) -> str:
    """Read an engram markdown body (everything after the frontmatter block)."""
    if not rel_path:
        return ""
    full = (PRISM_HOME / rel_path).resolve()
    try:
        if not str(full).startswith(str(PRISM_HOME.resolve())) or not full.is_file():
            return ""
        text = full.read_text()
    except OSError:
        return ""
    _, body = _split_frontmatter(text)
    return body.strip()[:_BODY_CAP]


def _split_frontmatter(text: str):
    """Split a markdown file into (frontmatter dict, body str). No PyYAML."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta, text
    lines = text.splitlines(keepends=True)
    # find closing delimiter
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        return meta, text
    for line in lines[1:close]:
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [t.strip().strip("'\"") for t in inner.split(",") if t.strip()] if inner else []
        else:
            meta[key] = val.strip("'\"")
    body = "".join(lines[close + 1:])
    return meta, body


def _shape_engram(entry: dict, cfg: dict) -> dict:
    """Project an index entry into the shape the dashboard renders."""
    eid = entry.get("id", "")
    return {
        "id": eid,
        "name": _prettify(eid),
        "kind": entry.get("kind", ""),
        "trigger": entry.get("trigger", ""),
        "confidence": round(float(entry.get("confidence", 0) or 0), 3),
        "domain": entry.get("domain", ""),
        "scope": entry.get("scope", "project"),
        "project_id": entry.get("project_id", ""),
        "tags": entry.get("tags", []) or [],
        "evidence_count": int(entry.get("evidence_count", 0) or 0),
        "success_count": int(entry.get("success_count", 0) or 0),
        "failure_count": int(entry.get("failure_count", 0) or 0),
        "pinned": bool(entry.get("pinned", False)),
        "last_observed": entry.get("last_observed", ""),
        "last_used": entry.get("last_used", ""),
        "health": _health(entry, cfg),  # used only to tint the confidence meter
        "description": _read_body(entry.get("path", "")),
    }


def _count_files(d: Path) -> int:
    try:
        return sum(1 for f in d.iterdir() if f.is_file() and not f.name.startswith("."))
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

def _load_project_meta() -> dict:
    """Map project_id -> {name, root, remote, last_seen} from projects/*/project.json."""
    meta: dict = {}
    proj_root = PRISM_HOME / "projects"
    try:
        dirs = [d for d in proj_root.iterdir() if d.is_dir()]
    except OSError:
        dirs = []
    for d in dirs:
        pj = d / "project.json"
        info = {}
        if pj.is_file():
            try:
                info = json.loads(pj.read_text())
            except (OSError, json.JSONDecodeError):
                info = {}
        meta[d.name] = {
            "name": info.get("name") or d.name,
            "root": info.get("root", ""),
            "remote": _scrub_remote(info.get("remote", "")),
            "last_seen": info.get("last_seen", ""),
            "candidates": _count_files(d / "candidates"),
        }
    return meta


def _project_stats(engrams: list, candidates: int = 0) -> dict:
    by_kind: dict = {}
    confs = []
    for e in engrams:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        confs.append(e["confidence"])
    return {
        "count": len(engrams),
        "avg_confidence": round(sum(confs) / len(confs), 3) if confs else 0,
        "by_kind": by_kind,
        "candidates": candidates,
    }


def build_data() -> dict:
    """Assemble the full payload the dashboard renders."""
    cfg = get_config()
    proj_meta = _load_project_meta()
    index = load_index()
    raw = index.get("engrams", [])

    # Group engrams by project (and collect globals separately).
    by_project: dict = {}
    global_engrams: list = []
    by_kind_all: dict = {}
    by_domain_all: dict = {}
    all_confs = []

    for entry in raw:
        e = _shape_engram(entry, cfg)
        by_kind_all[e["kind"]] = by_kind_all.get(e["kind"], 0) + 1
        if e["domain"]:
            by_domain_all[e["domain"]] = by_domain_all.get(e["domain"], 0) + 1
        all_confs.append(e["confidence"])
        if e["scope"] == "global":
            global_engrams.append(e)
        else:
            by_project.setdefault(e["project_id"] or "unknown", []).append(e)

    # Only show projects that have at least one engram.
    project_ids = set(by_project)
    projects = []
    for pid in project_ids:
        engrams = sorted(
            by_project.get(pid, []),
            key=lambda x: (not x["pinned"], -x["confidence"]),
        )
        meta = proj_meta.get(pid, {})
        projects.append({
            "id": pid,
            "name": meta.get("name") or pid,
            "root": meta.get("root", ""),
            "remote": meta.get("remote", ""),
            "last_seen": meta.get("last_seen", ""),
            "engrams": engrams,
            "stats": _project_stats(engrams, meta.get("candidates", 0)),
        })

    # Sort projects: most engrams first, then by name.
    projects.sort(key=lambda p: (-p["stats"]["count"], p["name"].lower()))

    global_engrams.sort(key=lambda x: (not x["pinned"], -x["confidence"]))

    overview = {
        "total_engrams": len(raw),
        "total_projects": len([p for p in projects if p["stats"]["count"] > 0]),
        "global_count": len(global_engrams),
        "by_kind": by_kind_all,
        "by_domain": by_domain_all,
        "avg_confidence": round(sum(all_confs) / len(all_confs), 3) if all_confs else 0,
        "candidates_total": sum(p["stats"]["candidates"] for p in projects),
    }

    return {
        "prism_home": str(PRISM_HOME),
        "scanned_at": datetime.now().isoformat(),
        "config": {
            "extract_threshold": cfg.get("extract_threshold"),
            "decay_rate_per_week": cfg.get("decay_rate_per_week"),
            "archive_threshold": cfg.get("archive_threshold"),
            "publish_min_confidence": cfg.get("publish_min_confidence"),
            "publish_min_evidence": cfg.get("publish_min_evidence"),
        },
        "registries": list_registries(),  # tokens already masked
        "projects": projects,
        "global": {
            "engrams": global_engrams,
            "stats": _project_stats(global_engrams),
        },
        "overview": overview,
    }


def _fingerprint() -> dict:
    """Cheap change-detector for client polling: index mtime + engram count."""
    idx = PRISM_HOME / "index.json"
    try:
        mtime = idx.stat().st_mtime
    except OSError:
        mtime = 0
    try:
        count = len(load_index().get("engrams", []))
    except Exception:
        count = 0
    return {"mtime": mtime, "count": count}


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

def _html_path() -> Path:
    return Path(__file__).parent / "dashboard.html"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default request logging
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, obj) -> None:
        self._send(200, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/fingerprint":
                return self._json(_fingerprint())
            if path == "/api/data":
                return self._json(build_data())
            if path in ("/", "/index.html"):
                html = _html_path()
                if html.is_file():
                    return self._send(200, html.read_bytes(),
                                      "text/html; charset=utf-8")
                return self._send(500, b"dashboard.html not found", "text/plain")
            return self._send(404, b"Not found", "text/plain")
        except Exception as e:  # never crash the server on one bad request
            return self._send(500, json.dumps({"error": str(e)}).encode(),
                              "application/json; charset=utf-8")


def serve_dashboard(port: int = 4318, no_open: bool = False) -> None:
    """Start the dashboard server, retrying the next few ports if needed."""
    attempts = 0
    httpd = None
    while attempts < 10:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
            break
        except OSError:
            port += 1
            attempts += 1
    if httpd is None:
        print("Could not bind a port for the dashboard.")
        return

    url = f"http://localhost:{port}"
    print("\n  Prism Dashboard")
    print("  ───────────────")
    print(f"  Reading:  {PRISM_HOME}")
    print(f"  Open:     {url}")
    print("  (Ctrl-C to stop)\n")
    if not no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
    finally:
        httpd.server_close()
