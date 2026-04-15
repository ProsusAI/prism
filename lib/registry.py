"""Prism registry configuration management.

Handles multi-registry CRUD operations on ~/.prism/registries.json,
auto-migration from config.json registry_url, token generation,
multi-registry fetch/cache/merge, and guided registry creation wizard.
"""

import json
import os
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .config import PRISM_HOME, get_config


REGISTRIES_PATH = PRISM_HOME / "registries.json"
CACHE_DIR = PRISM_HOME / "cache"

# Kebab-case validation: lowercase alphanumeric with hyphens, no leading/trailing hyphen
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


def load_registries() -> dict:
    """Load registries.json, auto-migrating from config.json if needed.

    Migration: if registries.json does not exist but config.json has registry_url,
    create a "default" registry entry with that URL (D-02).

    The migration uses atomic write (temp + rename). If two processes race on migration,
    both write the same content (same source registry_url), so the race is benign.
    """
    if REGISTRIES_PATH.exists():
        try:
            with open(REGISTRIES_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"registries": [], "default": None}

    # Migration: config.json registry_url -> registries.json
    config = get_config()
    registry_url = config.get("registry_url", "")
    if registry_url:
        registries = {
            "registries": [{
                "name": "default",
                "url": registry_url.rstrip("/"),
                "token": "",
                "writable": True,
            }],
            "default": "default",
        }
        save_registries(registries)
        return registries

    return {"registries": [], "default": None}


def save_registries(data: dict) -> None:
    """Atomic write of registries.json with 0o600 permissions (T-04-01).

    Tokens are stored in plaintext, so file permissions must restrict access
    to the owning user only. Uses os.open with restrictive permissions from
    the start to prevent TOCTOU race where the temp file is world-readable.
    """
    REGISTRIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(REGISTRIES_PATH) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.rename(tmp, str(REGISTRIES_PATH))
    except Exception:
        os.unlink(tmp)
        raise


def add_registry(name: str, url: str, token: str = "", writable: bool = True) -> None:
    """Add a registry entry to registries.json.

    Validates name is kebab-case (T-04-02). Raises ValueError if name already exists
    or name format is invalid. Sets as default if no default exists yet.
    """
    # Validate name format (T-04-02: prevent injection)
    if not name:
        raise ValueError("Registry name is required.")
    # Allow single-char alphanumeric names; require kebab-case for multi-char
    if len(name) == 1:
        if not name.isalnum():
            raise ValueError(
                f"Invalid registry name '{name}'. Must be alphanumeric."
            )
    elif not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid registry name '{name}'. Use kebab-case: [a-z0-9][a-z0-9-]*[a-z0-9]"
        )

    data = load_registries()

    # Check for duplicate
    for entry in data.get("registries", []):
        if entry["name"] == name:
            raise ValueError(f"Registry '{name}' already exists. Remove it first or use a different name.")

    entry = {
        "name": name,
        "url": url.rstrip("/"),
        "token": token,
        "writable": writable,
    }
    data.setdefault("registries", []).append(entry)

    # Set as default if no default yet
    if not data.get("default"):
        data["default"] = name

    save_registries(data)


def remove_registry(name: str) -> None:
    """Remove a registry entry by name. Raises ValueError if not found.

    If the removed entry was the default, sets default to first remaining
    registry or None if empty.
    """
    data = load_registries()
    registries = data.get("registries", [])
    original_len = len(registries)

    data["registries"] = [r for r in registries if r["name"] != name]

    if len(data["registries"]) == original_len:
        raise ValueError(f"Registry '{name}' not found.")

    # Update default if removed entry was the default
    if data.get("default") == name:
        if data["registries"]:
            data["default"] = data["registries"][0]["name"]
        else:
            data["default"] = None

    save_registries(data)


def list_registries() -> list:
    """List all configured registries with masked tokens.

    Returns list of dicts with keys: name, url, token (masked), writable, is_default.
    Token masking: first 8 chars + "..." if len > 8, else "***" if non-empty, else "".
    """
    data = load_registries()
    default_name = data.get("default")
    result = []

    for entry in data.get("registries", []):
        token_raw = entry.get("token", "")
        if token_raw:
            if len(token_raw) > 8:
                masked = token_raw[:8] + "..."
            else:
                masked = "***"
        else:
            masked = ""

        result.append({
            "name": entry["name"],
            "url": entry.get("url", ""),
            "token": masked,
            "writable": entry.get("writable", True),
            "is_default": entry["name"] == default_name,
        })

    return result


def set_default_registry(name: str) -> None:
    """Set the default write-target registry. Raises ValueError if name not found."""
    data = load_registries()

    found = any(r["name"] == name for r in data.get("registries", []))
    if not found:
        raise ValueError(f"Registry '{name}' not found.")

    data["default"] = name
    save_registries(data)


def get_registry(name: str) -> dict:
    """Get a registry entry by name. Raises ValueError if not found."""
    data = load_registries()
    for entry in data.get("registries", []):
        if entry["name"] == name:
            return entry
    raise ValueError(f"Registry '{name}' not found.")


def get_default_registry() -> Optional[dict]:
    """Get the default registry entry, or None if no default is set."""
    data = load_registries()
    default_name = data.get("default")
    if not default_name:
        return None
    for entry in data.get("registries", []):
        if entry["name"] == default_name:
            return entry
    return None


def generate_token() -> str:
    """Generate a cryptographically secure API token (T-04-03).

    Uses secrets.token_hex(32) for 64 hex chars of entropy, prefixed with 'prism_'
    for identifiability. Total length: 69 chars.
    """
    return "prism_" + secrets.token_hex(32)


def resolve_token(registry: dict) -> str:
    """Resolve the API token for a registry entry.

    Checks REGISTRY_TOKEN env var first (backward compat with Phase 3),
    then falls back to the token stored in registries.json.
    """
    env_token = os.environ.get("REGISTRY_TOKEN", "")
    if env_token:
        return env_token
    return registry.get("token", "")


def get_cached_registry(name: str, url: str, token: str) -> dict:
    """Fetch a registry's skill-registry.json using ETag-based conditional GET (D-04).

    Cache path: ~/.prism/cache/{name}.json stores skills + '_etag' field.
    On each call, sends If-None-Match if a cached ETag exists. Server returns:
      304 Not Modified — no body, use cached data (registry unchanged)
      200 OK           — fresh data + new ETag, replace cache
    On fetch failure, returns stale cache if available, otherwise {"skills": []}.
    Each urllib.request.urlopen has timeout=15 to mitigate T-04-11 (DoS from unreachable registry).
    """
    cache_path = CACHE_DIR / f"{name}.json"

    # Load cached data and extract stored ETag if available
    cached = None
    stored_etag = None
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            stored_etag = cached.get("_etag")
        except (OSError, json.JSONDecodeError):
            cached = None

    # Build request — conditional GET if we have a cached ETag
    headers = {"User-Agent": "Prism/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if stored_etag:
        headers["If-None-Match"] = stored_etag

    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/skills/registry",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                new_etag = resp.headers.get("ETag")
        except urllib.error.HTTPError as e:
            if e.code == 304 and cached is not None:
                return cached  # 304 Not Modified — registry unchanged, use cache
            raise

        # Only cache non-empty results — an empty skills list is likely transient.
        if data.get("skills"):
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_data = dict(data)
            if new_etag:
                cache_data["_etag"] = new_etag
            tmp = str(cache_path) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(cache_data, f)
            os.rename(tmp, str(cache_path))
        return data

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        # On failure, return stale cache if available (no time limit — stale beats nothing)
        if cached:
            print(f"Warning: could not reach registry '{name}': {e}. Using stale cache.", file=sys.stderr)
            return cached
        print(f"Warning: could not reach registry '{name}': {e}", file=sys.stderr)
        return {"skills": []}


def fetch_all_registries() -> list:
    """Fetch skills from all configured registries, merge with source tagging (D-03).

    Each skill gets a '_registry' field set to the source registry name.
    Deduplicates by (name, repository) -- keeps first occurrence (registry list order).
    Each registry fetch is wrapped in try/except so one failure doesn't block others (T-04-11).
    """
    registries = load_registries()
    all_skills = []
    seen = set()

    for entry in registries.get("registries", []):
        try:
            token = resolve_token(entry)
            data = get_cached_registry(entry["name"], entry["url"], token)
            for skill in data.get("skills", []):
                key = (skill.get("name", ""), skill.get("repository", ""))
                if key not in seen:
                    seen.add(key)
                    skill["_registry"] = entry["name"]
                    all_skills.append(skill)
        except Exception as e:
            print(f"Warning: skipping registry '{entry.get('name', '?')}': {e}", file=sys.stderr)
            continue

    return all_skills


def get_write_target(registry_name: Optional[str] = None) -> dict:
    """Resolve the target registry for publish operations (D-05/D-06).

    If registry_name is provided, looks it up and checks writable flag.
    If None, uses the default registry.
    Raises ValueError if not found, no default, or not writable.
    """
    if registry_name:
        entry = get_registry(registry_name)
        if not entry.get("writable", True):
            raise ValueError(f"Registry '{registry_name}' is read-only.")
        return entry

    entry = get_default_registry()
    if not entry:
        raise ValueError("No default registry configured. Run 'prism registry default NAME' to set one.")
    if not entry.get("writable", True):
        raise ValueError(f"Default registry '{entry['name']}' is read-only.")
    return entry


def cmd_registry_create() -> None:
    """Guided wizard for creating a new Prism registry (D-08).

    Walks user through: create GitHub repo, deploy Worker, set secrets,
    generate API token, configure local Prism. Does NOT automate wrangler
    deploy or wrangler secret -- provides instructions only.
    """
    print()
    print("\033[1m=== Prism Registry Setup Wizard ===\033[0m")
    print()

    # Step 1: Registry name
    name = input("Registry name (kebab-case): ").strip().lower()
    if not name:
        print("\033[31mRegistry name is required.\033[0m")
        return
    if len(name) > 1 and not _NAME_RE.match(name):
        print(f"\033[31mInvalid name '{name}'. Use kebab-case: [a-z0-9][a-z0-9-]*[a-z0-9]\033[0m")
        return

    # Step 2: GitHub org/repo
    org_repo = input("GitHub org/repo (e.g., acme/skill-registry): ").strip()
    if not org_repo or "/" not in org_repo:
        print("\033[31mPlease provide org/repo format (e.g., acme/skill-registry).\033[0m")
        return

    repo_name = org_repo.split("/")[-1]

    # Step 3: Check gh CLI
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print("\033[33mWarning: gh CLI not authenticated. Run 'gh auth login' first.\033[0m")
            print("You can continue and create the repo manually.")
    except FileNotFoundError:
        print("\033[33mWarning: gh CLI not found. Install it from https://cli.github.com/\033[0m")
        print("You can continue and create the repo manually on GitHub.")
    except subprocess.TimeoutExpired:
        print("\033[33mWarning: gh CLI timed out.\033[0m")

    # Step 4: Create repo
    print(f"\nCreating GitHub repo: {org_repo}...")
    try:
        result = subprocess.run(
            ["gh", "repo", "create", org_repo, "--private", "--confirm"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"\033[32mRepo created: https://github.com/{org_repo}\033[0m")
        else:
            print(f"\033[33mCould not create repo automatically: {result.stderr.strip()}\033[0m")
            print(f"Create it manually at: https://github.com/new")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("\033[33mCould not create repo. Create it manually at: https://github.com/new\033[0m")

    # Step 5: Generate token
    generated_token = generate_token()

    # Step 6: Print setup instructions
    print(f"""
\033[1mNext steps:\033[0m

  1. Clone your new repo:
     git clone https://github.com/{org_repo}.git
     cd {repo_name}

  2. Copy the registry template:
     cp -r ~/.prism/templates/registry/* .
     mkdir -p skills .github/workflows
     cp ci/*.yml .github/workflows/

  3. Install and deploy the Worker:
     cd worker && npm install && npm run deploy

  4. Set Worker secrets:
     npx wrangler secret put GH_TOKEN
     (paste your GitHub Personal Access Token)
     npx wrangler secret put REGISTRY_TOKENS
     (paste: {generated_token})

  5. Update wrangler.toml:
     Set GH_OWNER and GH_REPO to match your repo

  6. Commit and push:
     git add . && git commit -m "Initial registry setup" && git push
""")

    # Step 7: Auto-add registry locally
    try:
        add_registry(name, f"https://{name}.workers.dev", generated_token)
    except ValueError as e:
        print(f"\033[33mNote: {e}\033[0m")

    # Step 8: Summary
    print(f"\033[32mRegistry '{name}' configured locally.\033[0m")
    print(f"  URL:   https://{name}.workers.dev")
    print(f"  Token: {generated_token[:8]}...")
    print(f"\nUpdate the URL after deploying your Worker if it differs.")
