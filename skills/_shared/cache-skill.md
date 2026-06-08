# Shared: Cache Fetched Skill

After a skill's `SKILL.md` is successfully fetched from a remote registry, cache it in
the Prism home **and** link it into the current project so it is immediately available
as a slash command (`/skill-name`) and fetchable next time — across all projects.

This mirrors how `prism init` installs Prism's own skills: the canonical copy lives in
`~/.prism/skills/{name}/` and each project gets a symlink in `.claude/skills/` (plus a
Cursor rule in `.cursor/rules/`).

## Steps

1. Write the fetched content to `~/.prism/skills/{name}/SKILL.md` using the Write tool
   (this is the global cache, reused across every project).

2. Link it into the current project so Claude Code and Cursor can load it:

   ```bash
   name="{name}"   # <-- the skill's registry name
   prism_skill="$HOME/.prism/skills/$name"

   # Claude Code: .claude/skills/{name} -> ~/.prism/skills/{name}
   mkdir -p .claude/skills
   rm -rf ".claude/skills/$name"
   ln -s "$prism_skill" ".claude/skills/$name"

   # Cursor: .cursor/rules/{name}.mdc -> ~/.prism/skills/{name}/SKILL.md
   mkdir -p .cursor/rules
   rm -f ".cursor/rules/$name.mdc" ".cursor/rules/$name.md"
   ln -s "$prism_skill/SKILL.md" ".cursor/rules/$name.mdc"
   ```

Both `.claude/skills/` and `.cursor/rules/*.mdc` are already covered by Prism's
`.gitignore` entries, so these links are local-only and never committed.

Skip this entirely for skills loaded from local sources — they already live in the project.
