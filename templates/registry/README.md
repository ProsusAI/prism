# Prism Registry Template

This directory contains everything needed to deploy a Prism skill registry backed by a GitHub repo and a Cloudflare Worker.

## Supported backends

The registry can be hosted on either GitHub or GitLab. Pick one — the Worker selects the backend via the `GIT_PROVIDER` env var in `worker/wrangler.toml` (defaults to `github`).

- [GitHub setup](#setup) — default, instructions below
- [GitLab setup](#gitlab-setup) — see further down

## Prerequisites

- Node.js 22+ (for Wrangler)
- A Cloudflare account
- A GitHub account with a Personal Access Token (PAT) with `repo` scope
- Wrangler CLI: installed locally via `npm install` (no global install needed)

## Setup

### 1. Create the GitHub Registry Repo

Create a new private GitHub repository for your registry. Copy the contents of this template into it:

```bash
# Initialize the repo with template contents
git init my-registry && cd my-registry
cp -r /path/to/templates/registry/* .
cp -r /path/to/templates/registry/.* . 2>/dev/null || true
mkdir -p skills
echo '{"generated_by":"prism-registry","generated_at":"","skill_count":0,"skills":[]}' > skill-registry.json
git add . && git commit -m "Initial registry setup"
git remote add origin git@github.com:YOUR_ORG/YOUR_REPO.git
git push -u origin main
```

### 2. Configure the Worker

Edit `worker/wrangler.toml`:

```toml
[vars]
GH_OWNER = "your-github-org"
GH_REPO = "your-registry-repo"
GH_BRANCH = "main"
```

### 3. Deploy the Worker

```bash
cd worker
npm install
npm run deploy
```

### 4. Set Secrets

```bash
# Your GitHub PAT with repo scope
npx wrangler secret put GH_TOKEN

# Comma-separated API tokens for Prism clients
npx wrangler secret put REGISTRY_TOKENS
```

### 5. Set Up CI

Copy `ci/validate-pr.yml` and `ci/build-registry.yml` to `.github/workflows/` in your registry repo.

Copy `scripts/` and `schemas/` to the repo root.

### 6. Verify

```bash
curl https://your-worker.workers.dev/health
# Should return: {"status":"ok","service":"prism-registry"}
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/registry` | Yes | Returns skill-registry.json |
| GET | `/api/skills/registry` | Yes | Alias for /registry |
| GET | `/file/{path}` | Yes | Fetch any file from the repo |
| POST | `/api/skills/publish` | Yes | Publish skills (creates PR) |

## Authentication

All endpoints except `/health` require a Bearer token:

```
Authorization: Bearer your-token-here
```

Tokens are validated against the `REGISTRY_TOKENS` secret (comma-separated list).

## Publishing Skills

Prism clients send skills in flat-field format to `POST /api/skills/publish`:

```json
{
  "skills": [
    {
      "name": "skill-name",
      "description": "What the skill does",
      "author": "author-name",
      "repository": "org/repo",
      "category": ["architecture"],
      "source": "prism",
      "commit_date": "2026-04-14",
      "source_hash": "abc123def456",
      "content": "# SKILL.md content here..."
    }
  ],
  "description": "Publishing skills from org/repo"
}
```

The Worker reconstructs `plugin.json` from the flat fields and uses `content` as `SKILL.md`, then creates a PR on the registry repo.

## GitLab Setup

The registry can equivalently be backed by a GitLab project. The Worker, wizard, and CI templates all support GitLab as of v1.1.

### 1. Create the GitLab Project

Create a new private GitLab project (gitlab.com or self-hosted). Copy the template contents into it:

```bash
git init my-registry && cd my-registry
cp -r /path/to/templates/registry/* .
mkdir -p skills
cp ci/gitlab-ci.yml .gitlab-ci.yml
echo '{"generated_by":"prism-registry","generated_at":"","skill_count":0,"skills":[]}' > skill-registry.json
git add . && git commit -m "Initial registry setup"
git remote add origin git@gitlab.com:YOUR_GROUP/YOUR_PROJECT.git
git push -u origin main
```

### 2. Configure the Worker for GitLab

Edit `worker/wrangler.toml`:

```toml
GIT_PROVIDER = "gitlab"

[vars]
GITLAB_HOST       = "https://gitlab.com"        # or self-hosted URL
GITLAB_PROJECT_ID = "your-group/your-project"   # or numeric project ID
GITLAB_BRANCH     = "main"
```

### 3. Deploy the Worker

```bash
cd worker
npm install
npm run deploy
```

### 4. Set Secrets

```bash
# GitLab Personal Access Token with 'api' scope
npx wrangler secret put GITLAB_TOKEN

# Same as the GitHub flow: comma-separated client API tokens
npx wrangler secret put REGISTRY_TOKENS
```

### 5. Set Up CI

The `ci/gitlab-ci.yml` file already lives at the project root as `.gitlab-ci.yml` (step 1). In GitLab, go to **Settings -> CI/CD -> Variables** and add `REGISTRY_PUSH_TOKEN` (a project access token with `write_repository` scope, marked masked + protected).

### 6. Verify

```bash
curl https://your-worker.workers.dev/health
# Should return: {"status":"ok","service":"prism-registry"}
```

The API endpoints, authentication, and publishing payload format are identical to the GitHub backend — the Worker abstracts the provider behind a common interface, so Prism clients don't know or care which platform hosts the registry.
