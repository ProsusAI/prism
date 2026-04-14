import json
import sys
from pathlib import Path

try:
    from jsonschema import validate, ValidationError
except ImportError:
    print("jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
SCHEMA_PATH = ROOT / "schemas" / "plugin.schema.json"

REQUIRED_FRONTMATTER = ["name", "description"]


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def parse_frontmatter(path):
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def collect_skill_dirs():
    skill_dirs = []
    if not SKILLS_DIR.exists():
        return skill_dirs
    for repo_dir in sorted(SKILLS_DIR.iterdir()):
        if not repo_dir.is_dir():
            continue
        for skill_dir in sorted(repo_dir.iterdir()):
            if skill_dir.is_dir():
                skill_dirs.append((repo_dir.name, skill_dir))
    return skill_dirs


def validate_skill(skill_dir, repo_name, schema):
    errors = []
    name = skill_dir.name
    label = f"{repo_name}/{name}"

    plugin_path = skill_dir / "plugin.json"
    if not plugin_path.exists():
        errors.append(f"{label}: missing plugin.json")
        return errors

    try:
        with open(plugin_path) as f:
            plugin = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"{label}: invalid JSON in plugin.json: {e}")
        return errors

    try:
        validate(instance=plugin, schema=schema)
    except ValidationError as e:
        errors.append(
            f"{label}: schema validation failed: {e.message}"
        )

    if plugin.get("name") != name:
        errors.append(
            f"{label}: plugin.json name '{plugin.get('name')}' "
            f"does not match directory name '{name}'"
        )

    if plugin.get("repository") != repo_name:
        errors.append(
            f"{label}: plugin.json repository "
            f"'{plugin.get('repository')}' "
            f"does not match directory '{repo_name}'"
        )

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append(f"{label}: missing SKILL.md")
        return errors

    frontmatter = parse_frontmatter(skill_md)
    if frontmatter is None:
        errors.append(
            f"{label}: SKILL.md missing frontmatter block"
        )
    else:
        for field in REQUIRED_FRONTMATTER:
            if field not in frontmatter:
                errors.append(
                    f"{label}: SKILL.md frontmatter "
                    f"missing '{field}'"
                )

        # Ensure plugin.json name and SKILL.md frontmatter name agree.
        plugin_name = plugin.get("name")
        skill_md_name = frontmatter.get("name")
        if (
            plugin_name
            and skill_md_name
            and plugin_name != skill_md_name
        ):
            errors.append(
                f"{label}: plugin.json name '{plugin_name}' "
                f"does not match SKILL.md frontmatter "
                f"name '{skill_md_name}'"
            )

    return errors


def check_duplicates(skill_entries):
    errors = []
    seen_path = {}
    seen_name = {}
    for repo_name, skill_dir in skill_entries:
        # Check duplicate (repo, dir) paths
        key = (repo_name, skill_dir.name)
        if key in seen_path:
            errors.append(
                f"Duplicate skill '{skill_dir.name}' "
                f"in repository '{repo_name}'"
            )
        seen_path[key] = True

        # Check duplicate skill names across all repos
        plugin_path = skill_dir / "plugin.json"
        if plugin_path.exists():
            try:
                with open(plugin_path) as f:
                    plugin = json.load(f)
                name = plugin.get("name")
                if name and name in seen_name:
                    errors.append(
                        f"Duplicate skill name '{name}': "
                        f"found in '{repo_name}/{skill_dir.name}' "
                        f"and '{seen_name[name]}'"
                    )
                elif name:
                    seen_name[name] = f"{repo_name}/{skill_dir.name}"
            except (json.JSONDecodeError, OSError):
                pass  # Already caught by validate_skill
    return errors


def main():
    print("Prism Registry -- Skill Validation")
    print("=" * 40)

    if not SKILLS_DIR.exists():
        print("No skills/ directory found")
        sys.exit(1)

    schema = load_schema()
    skill_entries = collect_skill_dirs()

    if not skill_entries:
        print("No skills found in skills/")
        sys.exit(0)

    all_errors = []
    for repo_name, skill_dir in skill_entries:
        errors = validate_skill(skill_dir, repo_name, schema)
        if errors:
            all_errors.extend(errors)
        else:
            print(f"  OK  {repo_name}/{skill_dir.name}")

    dup_errors = check_duplicates(skill_entries)
    all_errors.extend(dup_errors)

    if all_errors:
        print(f"\n{len(all_errors)} error(s) found:\n")
        for err in all_errors:
            print(f"  FAIL  {err}")
        sys.exit(1)

    print(f"\n{len(skill_entries)} skill(s) validated")


if __name__ == "__main__":
    main()
