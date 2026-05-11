# Quick Task 260511-fyh: Add GitLab Registry Backend Support

**Completed:** 2026-05-11
**Commits:** d9dfead, 8c63a8d, 8be3e2a

## What was done

### Task 1 — Worker provider abstraction + GitLab implementation
`templates/registry/worker/src/index.ts`, `wrangler.toml`, `.gitignore`

Refactored the Cloudflare Worker's GitHub-specific code into a `GitHubProvider` class, added `GitLabProvider` using GitLab's single-call commit API (`POST /projects/{id}/repository/commits` with actions array), and a `getProvider()` factory that dispatches on the `GIT_PROVIDER` env var (`"github"` | `"gitlab"`). Default remains `"github"` — existing deployments unaffected. Added GitLab env vars section to `wrangler.toml` (`GL_PROJECT_ID`, `GL_BRANCH`, `GL_BASE_URL`).

### Task 2 — GitLab CI pipeline template
`templates/registry/ci/gitlab-ci.yml`

New `.gitlab-ci.yml` template mirroring the GitHub Actions validate + build_registry pipeline. Runs `scripts/validate.py` on MR trigger and `scripts/build_registry.py` on main push, committing updated `skill-registry.json`.

### Task 3 — Wizard provider selection + README
`lib/registry.py`, `templates/registry/README.md`

Added provider selection prompt to `cmd_registry_create()` wizard (GitHub vs GitLab). GitLab path prompts for project ID and optional self-hosted base URL, then prints equivalent setup instructions. Added GitLab setup section to README covering wrangler.toml config, `GL_TOKEN` secret, and GitLab CI workflow setup.

## Files changed
- `templates/registry/worker/src/index.ts` — provider abstraction + GitLabProvider
- `templates/registry/worker/wrangler.toml` — GitLab env var section
- `templates/registry/worker/.gitignore` — prevent node_modules leaking
- `templates/registry/ci/gitlab-ci.yml` — new GitLab CI template
- `templates/registry/README.md` — GitLab setup section
- `lib/registry.py` — provider selection in create wizard
