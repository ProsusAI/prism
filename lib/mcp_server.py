#!/usr/bin/env python3
"""Prism MCP server - stdio transport, zero dependencies.

Exposes prism knowledge base to Claude Code via MCP protocol.
Tools: prism_search, prism_get, prism_relevant, prism_record.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from parent dir (works both in repo and ~/.prism/)
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config import PRISM_HOME, get_config, get_engrams_dir, ensure_dirs
from lib.index import (
    add_entry,
    build_index_entry,
    get_entry,
    load_index,
    list_entries,
)

SERVER_NAME = "prism"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-03-26"


# --- Search ---

def _tokenize(text):
    """Split text into lowercase tokens for Jaccard similarity."""
    if not text:
        return set()
    return set(t for t in re.split(r"[\s\-_/.,;:!?()\"']+", text.lower()) if t)


def _search(query, project_id=None, limit=5):
    """Token Jaccard search across all entries."""
    index = load_index()
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    error_terms = {"error", "fail", "crash", "exception", "oom", "bug", "broken", "issue"}
    is_error_query = bool(query_tokens & error_terms)

    scored = []
    for entry in index.get("engrams", []):
        # Skip if project-scoped and wrong project
        if project_id and entry.get("scope") == "project":
            if entry.get("project_id") not in (project_id, "global"):
                continue

        entry_tokens = _tokenize(entry.get("trigger", ""))
        entry_tokens |= set(t.lower() for t in entry.get("tags", []))
        entry_tokens |= _tokenize(entry.get("domain", ""))

        overlap = query_tokens & entry_tokens
        union = query_tokens | entry_tokens
        score = len(overlap) / len(union) if union else 0

        # Boost error_recipes for error-related queries
        if is_error_query and entry.get("kind") == "error_recipe":
            score *= 1.3

        # Boost higher-confidence entries slightly
        score += entry.get("confidence", 0) * 0.05

        if score > 0.05:
            scored.append((score, entry))

    scored.sort(key=lambda x: (-x[0], -x[1].get("confidence", 0)))
    return [{"score": round(s, 3), **e} for s, e in scored[:limit]]


def _get_entry_content(entry_id):
    """Read full content of an knowledge entry file."""
    entry = get_entry(entry_id)
    if not entry:
        return None

    filepath = PRISM_HOME / entry["path"]
    if not filepath.exists():
        return None

    try:
        return {
            "id": entry_id,
            "content": filepath.read_text(),
            "confidence": entry.get("confidence"),
            "kind": entry.get("kind"),
            "source": entry.get("source", "local"),
        }
    except OSError:
        return None


def _relevant(file_path=None, domain=None, project_id=None, limit=5):
    """Find entries relevant to current context."""
    # Map file extensions to domains
    ext_domain = {
        ".py": "python", ".ts": "typescript", ".tsx": "react",
        ".jsx": "react", ".js": "javascript", ".rs": "rust",
        ".go": "go", ".java": "java", ".rb": "ruby",
        ".css": "css", ".html": "html", ".sql": "database",
        ".sh": "shell", ".bash": "shell", ".zsh": "shell",
        ".yml": "infra", ".yaml": "infra", ".tf": "infra",
        ".dockerfile": "infra", ".toml": "config", ".json": "config",
    }

    if not domain and file_path:
        ext = Path(file_path).suffix.lower()
        domain = ext_domain.get(ext)

    filters = {}
    if domain:
        filters["kind"] = None  # all kinds
    if project_id:
        filters["project_id"] = project_id

    entries = list_entries(**filters)

    if domain:
        # Prioritize matching domain, but include others
        matching = [e for e in entries if e.get("domain") == domain]
        others = [e for e in entries if e.get("domain") != domain]
        entries = matching + others

    return entries[:limit]


def _record(text, kind="preference", project_id=None, scope="global"):
    """Record a new entry mid-session (like 'prism learn')."""
    if not project_id:
        project_id = os.environ.get("PRISM_PROJECT", "global")

    ensure_dirs(project_id)

    # Generate ID from text
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())[:60].strip("-")
    if not slug:
        slug = "prism"
    entry_id = slug

    # Check for duplicates
    if get_entry(entry_id):
        return {"id": entry_id, "status": "already_exists"}

    # Write knowledge entry file
    engrams_dir = get_engrams_dir(project_id) if scope == "project" else PRISM_HOME / "global" / "engrams"
    engrams_dir.mkdir(parents=True, exist_ok=True)
    filepath = engrams_dir / f"{entry_id}.md"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = f"""---
id: {entry_id}
kind: {kind}
trigger: "{text[:80]}"
confidence: 0.9
domain: general
scope: {scope}
project_id: {project_id}
evidence_count: 1
tags: [manual, mcp]
last_observed: {now}
---

# {text}

Recorded via MCP during coding session.
"""
    filepath.write_text(content)

    # Add to index
    rel_path = str(filepath.relative_to(PRISM_HOME)) if str(filepath).startswith(str(PRISM_HOME)) else str(filepath)
    entry = build_index_entry(
        entry_id=entry_id, kind=kind, trigger=text[:80],
        confidence=0.9, domain="general", scope=scope,
        project_id=project_id, path=rel_path,
        evidence_count=1, tags=["manual", "mcp"],
    )
    add_entry(entry)

    return {"id": entry_id, "status": "created", "confidence": 0.9}


# --- MCP Protocol ---

TOOLS = [
    {
        "name": "prism_search",
        "description": "Search the knowledge base for relevant entries (learned patterns, preferences, error recipes, procedures). Use when encountering errors, starting tasks, or making design decisions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "prism_get",
        "description": "Get the full content of a specific entry by ID. Use after search to read detailed steps, evidence, or context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entry ID (kebab-case slug)"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "prism_relevant",
        "description": "Get entries relevant to the current file or domain. Use when starting work on a file to load applicable knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Current file path (used to infer domain)"},
                "domain": {"type": "string", "description": "Explicit domain (python, react, testing, etc.)"},
                "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
            },
        },
    },
    {
        "name": "prism_record",
        "description": "Record a new piece of knowledge mid-session. Use when the user teaches something or you discover a pattern worth remembering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The knowledge to record"},
                "kind": {
                    "type": "string",
                    "description": "Type of knowledge",
                    "enum": ["preference", "correction", "procedure", "error_recipe", "domain_fact", "tool_pattern"],
                    "default": "preference",
                },
            },
            "required": ["text"],
        },
    },
]


def _handle_tool_call(name, arguments):
    """Dispatch MCP tool calls to implementations."""
    project_id = os.environ.get("PRISM_PROJECT")

    if name == "prism_search":
        results = _search(
            arguments["query"],
            project_id=project_id,
            limit=arguments.get("limit", 5),
        )
        if not results:
            return {"content": [{"type": "text", "text": "No matching entries found."}]}
        lines = []
        for r in results:
            source = f" ({r.get('source', 'local')})" if r.get("source") else ""
            lines.append(f"- **{r['id']}** [{r['kind']}] (conf: {r.get('confidence', '?')}{source}): {r.get('trigger', '')}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    elif name == "prism_get":
        result = _get_entry_content(arguments["id"])
        if not result:
            return {"content": [{"type": "text", "text": f"Entry '{arguments['id']}' not found."}], "isError": True}
        return {"content": [{"type": "text", "text": result["content"]}]}

    elif name == "prism_relevant":
        results = _relevant(
            file_path=arguments.get("file_path"),
            domain=arguments.get("domain"),
            project_id=project_id,
            limit=arguments.get("limit", 5),
        )
        if not results:
            return {"content": [{"type": "text", "text": "No relevant entries for this context."}]}
        lines = []
        for r in results:
            lines.append(f"- **{r['id']}** [{r['kind']}] (conf: {r.get('confidence', '?')}): {r.get('trigger', '')}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    elif name == "prism_record":
        result = _record(
            arguments["text"],
            kind=arguments.get("kind", "preference"),
            project_id=project_id,
        )
        return {"content": [{"type": "text", "text": f"Recorded entry: {result['id']} (status: {result['status']})"}]}

    else:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}


def _handle_message(msg):
    """Handle a JSON-RPC 2.0 message, return response or None for notifications."""
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    # Notifications (no id) - no response needed
    if msg_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result = _handle_tool_call(tool_name, arguments)
        except Exception as e:
            result = {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main():
    """Run the MCP server on stdio."""
    # Log to stderr (stdout is reserved for MCP messages)
    sys.stderr.write(f"prism MCP server v{SERVER_VERSION} starting\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"Invalid JSON: {e}\n")
            sys.stderr.flush()
            continue

        response = _handle_message(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
