# Prism Registry Template

This directory contains everything needed to deploy a Prism skill registry backed by a GitHub repo and a Cloudflare Worker.

## Prerequisites

- Node.js 22+ (for Wrangler)
- A Cloudflare account
- A GitHub account with a Personal Access Token (PAT) with `repo` scope
- Wrangler CLI: `npm install -g wrangler`

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
wrangler deploy
```

### 4. Set Secrets

```bash
# Your GitHub PAT with repo scope
wrangler secret put GH_TOKEN

# Comma-separated API tokens for Prism clients
wrangler secret put REGISTRY_TOKENS
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
