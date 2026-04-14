import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
REGISTRY_PATH = ROOT / "skill-registry.json"


def main():
    skills = []
    errors = []

    if not SKILLS_DIR.is_dir():
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for repo_dir in sorted(SKILLS_DIR.iterdir()):
        if not repo_dir.is_dir():
            continue
        for skill_dir in sorted(repo_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            plugin_path = skill_dir / "plugin.json"
            if not plugin_path.exists():
                continue

            label = f"{repo_dir.name}/{skill_dir.name}"
            try:
                with open(plugin_path) as f:
                    plugin = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"{label}: invalid JSON in plugin.json: {e}")
                continue
            except OSError as e:
                errors.append(f"{label}: could not read plugin.json: {e}")
                continue

            skill_rel_path = f"skills/{repo_dir.name}/{skill_dir.name}"

            skills.append({
                "name": plugin["name"],
                "description": plugin["description"],
                "author": plugin["author"],
                "repository": plugin["repository"],
                "category": plugin.get("category"),
                "source": plugin.get("source"),
                "commit_date": plugin.get("commit_date"),
                "source_hash": plugin.get("source_hash"),
                "path": skill_rel_path,
            })

    if errors:
        for err in errors:
            print(f"  ERROR  {err}", file=sys.stderr)
        sys.exit(1)

    registry = {
        "generated_by": "prism-registry",
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "skill_count": len(skills),
        "skills": skills,
    }

    # Atomic write: write to a temp file in the same directory, then
    # replace the target. This prevents a partial/corrupt registry if
    # the process is interrupted mid-write.
    registry_dir = REGISTRY_PATH.parent
    fd, tmp_path = tempfile.mkstemp(dir=registry_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(registry, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, REGISTRY_PATH)
    except Exception:
        os.unlink(tmp_path)
        raise

    print(
        f"skill-registry.json updated with {len(skills)} skill(s)"
    )


if __name__ == "__main__":
    main()
