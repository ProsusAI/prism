---
phase: 260511-fyh
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - templates/registry/worker/src/index.ts
  - templates/registry/worker/wrangler.toml
  - templates/registry/ci/gitlab-ci.yml
  - lib/registry.py
  - templates/registry/README.md
autonomous: true
requirements:
  - QUICK-260511-FYH-01
must_haves:
  truths:
    - "Worker source compiles cleanly and selects GitHub or GitLab provider via GIT_PROVIDER env var (default: github)"
    - "GitHubProvider exists as an extracted class with all current GitHub-specific calls (fetchFile + createPullRequest equivalent), and behaviour is unchanged when GIT_PROVIDER is unset or 'github'"
    - "GitLabProvider implements the same provider interface against GitLab REST API v4 (read raw file, create branch via commits, open merge request)"
    - "wrangler.toml documents the GitLab env vars (GITLAB_HOST, GITLAB_PROJECT_ID, GITLAB_BRANCH, GITLAB_TOKEN, GIT_PROVIDER) without breaking existing GitHub deployments"
    - "templates/registry/ci/gitlab-ci.yml runs the same validate.py + build_registry.py pipeline that GitHub CI runs"
    - "prism registry create wizard prompts the user to choose github or gitlab and prints provider-appropriate setup instructions"
    - "README documents both backends with parallel setup sections and a provider-selection note"
  artifacts:
    - path: "templates/registry/worker/src/index.ts"
      provides: "Refactored Worker with GitHubProvider + GitLabProvider + factory"
      contains: "class GitHubProvider"
    - path: "templates/registry/worker/wrangler.toml"
      provides: "Wrangler config with GitHub + GitLab env var sections"
      contains: "GITLAB_PROJECT_ID"
    - path: "templates/registry/ci/gitlab-ci.yml"
      provides: "GitLab CI pipeline (validate + build registry index)"
      contains: "validate.py"
    - path: "lib/registry.py"
      provides: "cmd_registry_create wizard with provider selection"
      contains: "GitLab"
    - path: "templates/registry/README.md"
      provides: "Setup docs for both GitHub and GitLab backends"
      contains: "## GitLab Setup"
  key_links:
    - from: "templates/registry/worker/src/index.ts (router)"
      to: "GitHubProvider | GitLabProvider"
      via: "getProvider(env) factory dispatched on env.GIT_PROVIDER"
      pattern: "GIT_PROVIDER"
    - from: "templates/registry/worker/src/index.ts (publish handler)"
      to: "provider.createPullRequest()"
      via: "interface method on RegistryProvider"
      pattern: "createPullRequest"
    - from: "lib/registry.py cmd_registry_create"
      to: "templates/registry/README.md backend-specific instructions"
      via: "wizard input -> conditional setup text"
      pattern: "gitlab|github"
---

<objective>
Add GitLab registry backend support alongside GitHub so users can host a Prism skill registry on either platform. The Worker, CI templates, wizard, and docs all need parallel paths.

Purpose: Today the registry template is GitHub-only. Some users (corporate self-hosted, GitLab-first teams) cannot use it. Adding a provider abstraction in the Worker plus mirroring CI/wizard/README support unblocks them without forking the project.

Output: Refactored Worker with provider abstraction, GitLab CI template, wizard provider-selection step, and updated README. Existing GitHub deployments must be unaffected — refactor preserves current behaviour as the default.
</objective>

<execution_context>
@/Users/lara.baseggio/Documents/prism/.claude/get-shit-done/workflows/execute-plan.md
@/Users/lara.baseggio/Documents/prism/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@templates/registry/worker/src/index.ts
@templates/registry/worker/wrangler.toml
@templates/registry/ci/validate-pr.yml
@templates/registry/ci/build-registry.yml
@templates/registry/README.md
@lib/registry.py

<interfaces>
<!-- Provider interface the executor must implement in Task 1. -->
<!-- GitHubProvider must wrap existing fetchFromGitHub + createPullRequest verbatim. -->
<!-- GitLabProvider uses GitLab REST API v4 against ${GITLAB_HOST}/api/v4. -->

```typescript
interface RegistryFile {
  path: string;
  content: string;
}

interface PublishResult {
  message: string;
  pr_url: string;   // For GitLab this is the MR web_url
  branch: string;
  files_count: number;
}

interface RegistryProvider {
  // Read a single file from the registry repo (returns Fetch Response so
  // headers like ETag pass through; non-2xx returned as-is for caller).
  fetchFile(path: string): Promise<Response>;

  // Atomic batch: create branch -> single commit with all files -> open PR/MR.
  // Throws on API failure. Returns 201-shaped JSON Response.
  createPullRequest(
    files: RegistryFile[],
    title: string,
    description: string
  ): Promise<Response>;
}

// Factory: defaults to 'github' when env.GIT_PROVIDER is unset or empty.
function getProvider(env: Env): RegistryProvider;
```

GitLab API references (use these endpoints):
- Read file: GET `${GITLAB_HOST}/api/v4/projects/${GITLAB_PROJECT_ID}/repository/files/${encodeURIComponent(path)}/raw?ref=${GITLAB_BRANCH}` with header `PRIVATE-TOKEN: ${GITLAB_TOKEN}`
- Create commit with multiple files: POST `${GITLAB_HOST}/api/v4/projects/${GITLAB_PROJECT_ID}/repository/commits` body `{ branch, start_branch, commit_message, actions: [{ action: "create", file_path, content }] }` — this creates the branch and the commit in one call
- Create MR: POST `${GITLAB_HOST}/api/v4/projects/${GITLAB_PROJECT_ID}/merge_requests` body `{ source_branch, target_branch, title, description }`

Existing Env interface adds these optional fields:
```typescript
GIT_PROVIDER?: "github" | "gitlab";   // default "github"
// GitLab-specific (only required when GIT_PROVIDER === "gitlab")
GITLAB_HOST?: string;        // e.g. "https://gitlab.com" or self-hosted
GITLAB_PROJECT_ID?: string;  // numeric ID or URL-encoded "group/repo"
GITLAB_BRANCH?: string;      // default branch name, e.g. "main"
GITLAB_TOKEN?: string;       // PAT with api scope (secret, not in wrangler.toml)
```
</interfaces>

<conventions>
Hard constraints from CLAUDE.md that apply here:
- Worker stays TypeScript stdlib + Fetch API — no new npm deps
- No Python deps in `lib/registry.py` changes; stdlib only (argparse/input/subprocess already in use)
- Use `subprocess.run(..., capture_output=True, text=True, timeout=N)` if any subprocess calls are added
- Wrangler secrets (`GH_TOKEN`, `GITLAB_TOKEN`, `REGISTRY_TOKENS`) stay in `wrangler secret put`, never in `wrangler.toml`
- README must keep current GitHub flow as the documented default to avoid breaking existing readers
</conventions>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Refactor Worker into provider abstraction and add GitLab provider</name>
  <files>templates/registry/worker/src/index.ts, templates/registry/worker/wrangler.toml</files>
  <action>
Refactor `templates/registry/worker/src/index.ts` to introduce a `RegistryProvider` interface and two implementations, then wire a factory selected by `env.GIT_PROVIDER`.

Steps:

1. Extend `Env` interface to add the optional fields shown in `<interfaces>` above (`GIT_PROVIDER`, `GITLAB_HOST`, `GITLAB_PROJECT_ID`, `GITLAB_BRANCH`, `GITLAB_TOKEN`). All existing `GH_*` fields stay. Keep `REGISTRY_TOKENS` and the auth path untouched — it is provider-agnostic.

2. Define a `RegistryProvider` interface with `fetchFile(path)` and `createPullRequest(files, title, description)` methods exactly as specified in `<interfaces>`.

3. Create `class GitHubProvider implements RegistryProvider`:
   - Constructor takes `env: Env`; validates `env.GH_OWNER`, `env.GH_REPO`, `env.GH_BRANCH`, `env.GH_TOKEN` are present (throw `Error("GitHub provider missing required env var: GH_OWNER")` etc.).
   - `fetchFile(path)` = the current `fetchFromGitHub` body, called as instance method (use `this.env`).
   - `createPullRequest(files, title, description)` = the current `createPullRequest` body verbatim — branches, commit, PR, returns the existing `json({ message, pr_url, branch, files_count }, 201)`. Branch name stays `prism/publish-${Date.now()}`.

4. Create `class GitLabProvider implements RegistryProvider`:
   - Constructor takes `env: Env`; validates `env.GITLAB_HOST`, `env.GITLAB_PROJECT_ID`, `env.GITLAB_BRANCH`, `env.GITLAB_TOKEN` (throw similar errors).
   - `fetchFile(path)`: GET `${host}/api/v4/projects/${encodeURIComponent(projectId)}/repository/files/${encodeURIComponent(path)}/raw?ref=${branch}` with header `PRIVATE-TOKEN: ${token}` and `User-Agent: Prism-Worker/1.0`. Strip trailing slash from `GITLAB_HOST`. Return the raw `Response` (callers already check `resp.ok`).
   - `createPullRequest(files, title, description)`:
     - `branchName = `prism/publish-${Date.now()}``
     - One POST to `/api/v4/projects/${encodeURIComponent(projectId)}/repository/commits` with body `{ branch: branchName, start_branch: env.GITLAB_BRANCH, commit_message: title, actions: files.map(f => ({ action: "create", file_path: f.path, content: f.content })) }` — this creates the branch and commits all files in one atomic call.
     - One POST to `/api/v4/projects/${encodeURIComponent(projectId)}/merge_requests` with body `{ source_branch: branchName, target_branch: env.GITLAB_BRANCH, title, description }`. Read `web_url` from response.
     - Return `json({ message: "Skills submitted successfully", pr_url: mr.web_url, branch: branchName, files_count: files.length }, 201)`.
     - Wrap in try/catch identical to GitHub path; on error return `json({ error: err.message || "Failed to create MR" }, 500)`.
     - Use a small `glFetch(url, opts)` helper inside the method (mirrors the existing `ghFetch` pattern) that adds `PRIVATE-TOKEN` and `Content-Type: application/json` headers and throws on non-2xx.

5. Add a `getProvider(env: Env): RegistryProvider` factory near the bottom of the helpers section:
   ```typescript
   function getProvider(env: Env): RegistryProvider {
     const which = (env.GIT_PROVIDER || "github").toLowerCase();
     if (which === "gitlab") return new GitLabProvider(env);
     if (which === "github") return new GitHubProvider(env);
     throw new Error(`Unsupported GIT_PROVIDER: ${which}`);
   }
   ```

6. Update the router's `fetch` handler:
   - At the top of the `fetch` method (after the CORS preflight and `/health` short-circuits but before any provider call), instantiate `const provider = getProvider(env);` inside a try/catch — on failure return `json({ error: e.message }, 500)`.
   - Replace `fetchFromGitHub(env, "skill-registry.json")` with `provider.fetchFile("skill-registry.json")`.
   - Replace `fetchFromGitHub(env, filePath)` (inside `/file/`) with `provider.fetchFile(filePath)`.
   - Replace `fetchFromGitHub(env, \`skills\`)` (the stub branch that returns the 400 error) with `provider.fetchFile("skills")` to keep parity, even though the response is discarded.
   - Replace `createPullRequest(env, repository, files, title, description)` in the publish handler with `provider.createPullRequest(files, title, description)` — note `repository` was already unused as a parameter; drop it from the call.

7. After step 6 the top-level `fetchFromGitHub` and `createPullRequest` functions should no longer be referenced anywhere. Delete them — their logic now lives inside `GitHubProvider`.

8. Update `templates/registry/worker/wrangler.toml`. Keep current `[vars]` section as-is to preserve GitHub-default behaviour and add a GitLab section + provider toggle:
   ```toml
   # Provider selection: "github" (default) or "gitlab"
   # GIT_PROVIDER = "github"

   # --- GitHub backend (default) ---
   # These are set via `wrangler secret put` -- NOT here
   # GH_TOKEN = "your github pat"
   # REGISTRY_TOKENS = "token1,token2,token3"

   [vars]
   GH_OWNER = "YOUR_GITHUB_ORG"
   GH_REPO = "YOUR_REGISTRY_REPO"
   GH_BRANCH = "main"

   # --- GitLab backend (uncomment and set GIT_PROVIDER above to "gitlab") ---
   # Required when GIT_PROVIDER = "gitlab":
   # GITLAB_HOST       = "https://gitlab.com"   # or your self-hosted URL
   # GITLAB_PROJECT_ID = "group/repo"           # or numeric project ID
   # GITLAB_BRANCH     = "main"
   # GITLAB_TOKEN is set via `wrangler secret put GITLAB_TOKEN`
   ```
   Move the existing GH-secret comments under the new "GitHub backend" header. `GIT_PROVIDER` stays commented so existing deployments default to GitHub.

Avoid:
- Do NOT add npm dependencies (`@gitbeaker/*` or similar) — the Worker uses the global Fetch API, same as GitHub today.
- Do NOT change `REGISTRY_TOKENS`, `authenticate`, `timingSafeEqual`, `validatePrismPublish`, the CORS handling, or the publish endpoint shape. The refactor is purely behind the provider interface.
- Do NOT rename the existing `pr_url` field in the response payload — `lib/registry.py` and any CLI consumers depend on it. For GitLab the field still holds the MR `web_url`.
  </action>
  <verify>
    <automated>cd templates/registry/worker && (test -f node_modules/.bin/tsc || npm install --silent) && npx tsc --noEmit && grep -q "class GitHubProvider" src/index.ts && grep -q "class GitLabProvider" src/index.ts && grep -q "getProvider" src/index.ts && ! grep -qE "^async function (fetchFromGitHub|createPullRequest)\b" src/index.ts && grep -q "GITLAB_PROJECT_ID" wrangler.toml && grep -q "GIT_PROVIDER" wrangler.toml</automated>
  </verify>
  <done>
- `index.ts` type-checks cleanly with no errors (npx tsc --noEmit returns 0).
- `GitHubProvider`, `GitLabProvider`, and `getProvider` are defined.
- Top-level `fetchFromGitHub` and `createPullRequest` functions are removed.
- Router instantiates the provider once and uses it for all reads + the publish path.
- `wrangler.toml` documents both GitHub (active) and GitLab (commented) env var blocks plus the `GIT_PROVIDER` toggle.
- Existing GitHub deployments behave identically because GIT_PROVIDER defaults to `"github"`.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add GitLab CI pipeline template</name>
  <files>templates/registry/ci/gitlab-ci.yml</files>
  <action>
Create `templates/registry/ci/gitlab-ci.yml` mirroring what `validate-pr.yml` + `build-registry.yml` do on GitHub.

Two stages:
1. `validate` — runs on every MR touching `skills/**` and on every push to the default branch. Runs `pip install -q jsonschema` then `python scripts/validate.py`.
2. `build_registry` — runs only on the default branch *after* `validate` succeeds. Runs `python scripts/build_registry.py`, then commits and pushes `skill-registry.json` back to the default branch using a project access token.

Content:

```yaml
# GitLab CI pipeline for a Prism skill registry repo.
# Place this file at the repo root as `.gitlab-ci.yml`.
#
# Mirrors GitHub Actions workflows:
#   - validate.yml          -> stage: validate
#   - build-registry.yml    -> stage: build_registry (default branch only)
#
# Required CI/CD variables (Settings -> CI/CD -> Variables):
#   REGISTRY_PUSH_TOKEN - Project access token with `write_repository` scope,
#                         masked + protected. Used by build_registry to push
#                         the updated skill-registry.json back to the default
#                         branch.

stages:
  - validate
  - build_registry

default:
  image: python:3.12-slim

validate_skills:
  stage: validate
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      changes:
        - skills/**/*
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      changes:
        - skills/**/*
  script:
    - set -euo pipefail
    - pip install -q jsonschema
    - python scripts/validate.py

build_registry:
  stage: build_registry
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  needs:
    - validate_skills
  variables:
    GIT_STRATEGY: clone
  before_script:
    - apt-get update -qq && apt-get install -y -qq git
    - git config user.name "gitlab-ci"
    - git config user.email "ci@gitlab"
  script:
    - set -euo pipefail
    - python scripts/build_registry.py
    - git add skill-registry.json
    - |
      if git diff --staged --quiet; then
        echo "No registry changes"
        exit 0
      fi
    - git commit -m "Update skill-registry.json"
    - git push "https://oauth2:${REGISTRY_PUSH_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" HEAD:${CI_DEFAULT_BRANCH}
```

Notes:
- `REGISTRY_PUSH_TOKEN` is the GitLab equivalent of the implicit `GITHUB_TOKEN` write permission. We document it explicitly because GitLab does not grant default-branch push to `CI_JOB_TOKEN` for project access tokens.
- Keep the `set -euo pipefail`, idempotent commit-only-if-changed, and `python scripts/...` invocations parallel to the GitHub workflows so users see the same behaviour on both platforms.
- Do NOT change the existing GitHub workflows in `ci/validate-pr.yml` or `ci/build-registry.yml`. This task only adds a new file.
  </action>
  <verify>
    <automated>test -f templates/registry/ci/gitlab-ci.yml && python3 -c "import sys; content = open('templates/registry/ci/gitlab-ci.yml').read(); assert 'stages:' in content; assert 'validate_skills' in content; assert 'build_registry' in content; assert 'scripts/validate.py' in content; assert 'scripts/build_registry.py' in content; assert 'REGISTRY_PUSH_TOKEN' in content; print('ok')"</automated>
  </verify>
  <done>
- File `templates/registry/ci/gitlab-ci.yml` exists.
- Contains `stages: [validate, build_registry]`, runs `python scripts/validate.py` in the validate stage, runs `python scripts/build_registry.py` in build_registry.
- build_registry stage gated on default branch, depends on validate_skills, and pushes back via `REGISTRY_PUSH_TOKEN`.
- File parses as valid YAML (the Python assertion runs through the file).
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Wire provider selection into wizard and README</name>
  <files>lib/registry.py, templates/registry/README.md</files>
  <action>
Update `cmd_registry_create()` in `lib/registry.py` and `templates/registry/README.md` so the new GitLab path is discoverable and the wizard branches on provider.

**Part A — `lib/registry.py`:**

Modify only the `cmd_registry_create()` function (defined around line 378). Do NOT change any other function. Keep behaviour identical when the user picks `github` (the default).

1. After the existing "Step 1: Registry name" block and before the current "Step 2: GitHub org/repo" block, insert a new step that asks the user for a provider:

   ```python
   # Step 2: Backend provider
   provider = input("Backend provider [github/gitlab] (default: github): ").strip().lower() or "github"
   if provider not in ("github", "gitlab"):
       print(f"\033[31mUnknown provider '{provider}'. Choose 'github' or 'gitlab'.\033[0m")
       return
   ```

2. Renumber the subsequent comments (Step 2 -> Step 3, etc.) so the flow reads coherently.

3. Branch the org/repo prompt:
   ```python
   if provider == "github":
       org_repo = input("GitHub org/repo (e.g., acme/skill-registry): ").strip()
   else:
       org_repo = input("GitLab group/project path (e.g., acme/skill-registry): ").strip()
   ```
   The downstream validation (must contain `/`) stays the same. `repo_name = org_repo.split("/")[-1]` stays the same.

4. Wrap the existing `gh CLI` check and `gh repo create` block in `if provider == "github":`. Add a parallel branch for GitLab:
   ```python
   else:
       # GitLab: check glab CLI is available
       try:
           result = subprocess.run(
               ["glab", "auth", "status"],
               capture_output=True, text=True, timeout=10,
           )
           if result.returncode != 0:
               print("\033[33mWarning: glab CLI not authenticated. Run 'glab auth login' first.\033[0m")
               print("You can continue and create the project manually.")
       except FileNotFoundError:
           print("\033[33mWarning: glab CLI not found. Install it from https://gitlab.com/gitlab-org/cli\033[0m")
           print("You can continue and create the project manually on GitLab.")
       except subprocess.TimeoutExpired:
           print("\033[33mWarning: glab CLI timed out.\033[0m")

       print(f"\nCreating GitLab project: {org_repo}...")
       try:
           result = subprocess.run(
               ["glab", "repo", "create", org_repo, "--private"],
               capture_output=True, text=True, timeout=30,
           )
           if result.returncode == 0:
               print(f"\033[32mProject created: https://gitlab.com/{org_repo}\033[0m")
           else:
               print(f"\033[33mCould not create project automatically: {result.stderr.strip()}\033[0m")
               print(f"Create it manually at: https://gitlab.com/projects/new")
       except (FileNotFoundError, subprocess.TimeoutExpired):
           print("\033[33mCould not create project. Create it manually at: https://gitlab.com/projects/new\033[0m")
   ```
   Follow the existing patterns exactly: `subprocess.run(..., capture_output=True, text=True, timeout=N)`, no exceptions leaking.

5. Branch the "Next steps" message (the big f-string starting `\n\033[1mNext steps:\033[0m`). For GitHub, keep the existing text verbatim. For GitLab, print a parallel instruction block:
   ```python
   if provider == "github":
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
   else:
       print(f"""
   \033[1mNext steps (GitLab):\033[0m

     1. Clone your new project:
        git clone https://gitlab.com/{org_repo}.git
        cd {repo_name}

     2. Copy the registry template:
        cp -r ~/.prism/templates/registry/* .
        mkdir -p skills
        cp ci/gitlab-ci.yml .gitlab-ci.yml

     3. Install and deploy the Worker:
        cd worker && npm install && npm run deploy

     4. Set Worker secrets:
        npx wrangler secret put GITLAB_TOKEN
        (paste your GitLab Personal Access Token with 'api' scope)
        npx wrangler secret put REGISTRY_TOKENS
        (paste: {generated_token})

     5. Update wrangler.toml:
        - Set GIT_PROVIDER = "gitlab"
        - Set GITLAB_HOST, GITLAB_PROJECT_ID, GITLAB_BRANCH

     6. Add a project access token for CI:
        Project Settings -> Access Tokens -> create token with `write_repository`
        Settings -> CI/CD -> Variables -> add REGISTRY_PUSH_TOKEN (masked, protected)

     7. Commit and push:
        git add . && git commit -m "Initial registry setup" && git push
   """)
   ```

6. Leave Step 7 (`add_registry(...)`) and Step 8 (summary print) unchanged — `add_registry` doesn't care which backend is in use, the URL placeholder `https://{name}.workers.dev` stays the same.

Avoid:
- Do NOT introduce any non-stdlib import. Everything you need (`subprocess`, `input`, `print`) is already in scope.
- Do NOT modify other functions in `lib/registry.py` — only `cmd_registry_create()`. The registry storage schema is provider-agnostic on purpose.
- Do NOT auto-`wrangler secret put` for the user; the wizard prints instructions only, matching the existing GitHub flow.

**Part B — `templates/registry/README.md`:**

Add a "Backend selection" callout near the top and a parallel GitLab setup section. Keep the existing GitHub flow as the default-documented path so existing users see no surprises.

1. After the `# Prism Registry Template` title and intro paragraph, insert a "Supported backends" subsection:
   ```markdown
   ## Supported backends

   The registry can be hosted on either GitHub or GitLab. Pick one — the Worker selects the backend via the `GIT_PROVIDER` env var in `worker/wrangler.toml` (defaults to `github`).

   - [GitHub setup](#setup) — default, instructions below
   - [GitLab setup](#gitlab-setup) — see further down
   ```

2. Rename the current `## Setup` heading to `## Setup (GitHub)` and update any anchor references (the README itself doesn't currently cross-link, but the table of contents link above expects `#setup`, so use `## Setup` and keep `(GitHub)` as a parenthetical so the slug stays `setup`). Confirm: heading line becomes `## Setup`.

3. Append a new top-level section after the existing `## Publishing Skills` section (i.e. at the very end of the file):

   ```markdown
   ## GitLab Setup

   The registry can equivalently be backed by a GitLab project. The Worker, wizard, and CI templates all support GitLab as of v1.1.

   ### 1. Create the GitLab Project

   Create a new private GitLab project (gitlab.com or self-hosted). Copy the template contents into it:

   \`\`\`bash
   git init my-registry && cd my-registry
   cp -r /path/to/templates/registry/* .
   mkdir -p skills
   cp ci/gitlab-ci.yml .gitlab-ci.yml
   echo '{"generated_by":"prism-registry","generated_at":"","skill_count":0,"skills":[]}' > skill-registry.json
   git add . && git commit -m "Initial registry setup"
   git remote add origin git@gitlab.com:YOUR_GROUP/YOUR_PROJECT.git
   git push -u origin main
   \`\`\`

   ### 2. Configure the Worker for GitLab

   Edit `worker/wrangler.toml`:

   \`\`\`toml
   GIT_PROVIDER = "gitlab"

   [vars]
   GITLAB_HOST       = "https://gitlab.com"        # or self-hosted URL
   GITLAB_PROJECT_ID = "your-group/your-project"   # or numeric project ID
   GITLAB_BRANCH     = "main"
   \`\`\`

   ### 3. Deploy the Worker

   \`\`\`bash
   cd worker
   npm install
   npm run deploy
   \`\`\`

   ### 4. Set Secrets

   \`\`\`bash
   # GitLab Personal Access Token with 'api' scope
   npx wrangler secret put GITLAB_TOKEN

   # Same as the GitHub flow: comma-separated client API tokens
   npx wrangler secret put REGISTRY_TOKENS
   \`\`\`

   ### 5. Set Up CI

   The `ci/gitlab-ci.yml` file already lives at the project root as `.gitlab-ci.yml` (step 1). In GitLab, go to **Settings -> CI/CD -> Variables** and add `REGISTRY_PUSH_TOKEN` (a project access token with `write_repository` scope, marked masked + protected).

   ### 6. Verify

   \`\`\`bash
   curl https://your-worker.workers.dev/health
   # Should return: {"status":"ok","service":"prism-registry"}
   \`\`\`

   The API endpoints, authentication, and publishing payload format are identical to the GitHub backend — the Worker abstracts the provider behind a common interface, so Prism clients don't know or care which platform hosts the registry.
   ```

Replace the literal `\`\`\`` shown in this plan with real triple-backticks in the file.

Avoid:
- Do NOT remove or rewrite the existing GitHub setup section. It stays the canonical example.
- Do NOT introduce a separate provider-specific publishing format — the payload at `POST /api/skills/publish` is unchanged.
  </action>
  <verify>
    <automated>python3 -c "import ast; tree = ast.parse(open('lib/registry.py').read()); funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'cmd_registry_create']; assert len(funcs) == 1, 'cmd_registry_create must still exist exactly once'; src = open('lib/registry.py').read(); assert 'gitlab' in src.lower(), 'gitlab branch missing in wizard'; assert 'Backend provider' in src, 'provider prompt missing'; assert 'GITLAB_TOKEN' in src, 'gitlab token instructions missing'; readme = open('templates/registry/README.md').read(); assert '## GitLab Setup' in readme, 'GitLab Setup section missing'; assert 'GIT_PROVIDER' in readme, 'GIT_PROVIDER reference missing in README'; assert 'gitlab-ci.yml' in readme, 'gitlab-ci.yml reference missing in README'; print('ok')" &amp;&amp; python3 -m py_compile lib/registry.py</automated>
  </verify>
  <done>
- `cmd_registry_create()` prompts for `github`/`gitlab`, defaulting to `github`.
- Wizard branches on the choice: gh CLI + GitHub instructions for `github`, glab CLI + GitLab instructions (including REGISTRY_PUSH_TOKEN setup and `GIT_PROVIDER = "gitlab"`) for `gitlab`.
- `lib/registry.py` still imports only stdlib + existing internal modules and compiles (`python3 -m py_compile` returns 0).
- `templates/registry/README.md` has a "Supported backends" callout and a complete `## GitLab Setup` section parallel to the GitHub one.
- Existing GitHub setup section is unchanged in content.
  </done>
</task>

</tasks>

<verification>
- `npx tsc --noEmit` from `templates/registry/worker/` passes with zero errors.
- `python3 -m py_compile lib/registry.py` succeeds.
- `grep -c "GitHubProvider\|GitLabProvider\|getProvider" templates/registry/worker/src/index.ts` returns >= 3.
- `templates/registry/ci/gitlab-ci.yml` and the new README section both reference the same `scripts/validate.py` and `scripts/build_registry.py` paths so a single registry repo can be reused across backends.
- Running `python3 -c "from lib import registry"` from repo root imports cleanly (no syntax errors introduced).
</verification>

<success_criteria>
- A Prism user choosing `gitlab` in the wizard ends up with: a GitLab project, a Worker deployed with `GIT_PROVIDER="gitlab"`, a `.gitlab-ci.yml` running validate + build_registry, and a `registries.json` entry pointing at their Worker URL.
- A Prism user choosing `github` (or any existing deployment) experiences zero behaviour change — the GitHub default path is untouched at runtime.
- The Worker’s public HTTP contract is unchanged: same endpoints, same payloads, same status codes, same `pr_url` field in the publish response (it holds the MR `web_url` for GitLab).
- No new runtime dependencies — Worker remains stdlib + Fetch, Python remains stdlib + existing internal modules.
</success_criteria>

<output>
After completion, create `.planning/quick/260511-fyh-add-gitlab-registry-backend-support-alon/260511-fyh-SUMMARY.md` capturing: what changed, the provider interface added, files touched, and a verification snippet showing both `tsc --noEmit` and `python3 -m py_compile lib/registry.py` passing.
</output>
