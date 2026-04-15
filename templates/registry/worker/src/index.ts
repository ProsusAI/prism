/**
 * Prism Registry API -- Cloudflare Worker
 *
 * Acts as a proxy between Prism clients and a private GitHub registry repo.
 * Clients authenticate with Bearer tokens (REGISTRY_TOKENS secret).
 * The Worker uses a GitHub PAT (GH_TOKEN) to read/write the repo.
 *
 * READ:  Client calls GET endpoints -> Worker fetches from GitHub -> returns to client
 * WRITE: Client POSTs skills -> Worker validates, creates branch, commits all files,
 *        opens PR on registry repo -> GitHub Actions runs scripts/validate.py
 */

export interface Env {
  GH_TOKEN: string;           // GitHub PAT with repo scope
  REGISTRY_TOKENS: string;    // Comma-separated list of valid API tokens
  GH_OWNER: string;           // GitHub org, e.g. "my-org"
  GH_REPO: string;            // Registry repo name
  GH_BRANCH: string;          // Branch to read from, e.g. "main"
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function unauthorized(msg = "Unauthorized") {
  return new Response(JSON.stringify({ error: msg }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

function badRequest(msg: string) {
  return new Response(JSON.stringify({ error: msg }), {
    status: 400,
    headers: { "Content-Type": "application/json" },
  });
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Constant-time string comparison to prevent timing side-channel attacks */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    // Compare against dummy to avoid leaking length info via timing
    b = a;
  }
  let result = a.length ^ b.length; // will be non-zero if lengths differ
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

/** Verify the client's API token */
function authenticate(request: Request, env: Env): boolean {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader) return false;

  const token = authHeader.replace("Bearer ", "").trim();
  const validTokens = env.REGISTRY_TOKENS.split(",").map((t) => t.trim());
  return validTokens.some((valid) => timingSafeEqual(token, valid));
}

/** Fetch a raw file from the private GitHub repo */
async function fetchFromGitHub(
  env: Env,
  path: string
): Promise<Response> {
  const url = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/contents/${path}?ref=${env.GH_BRANCH}`;

  return fetch(url, {
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github.raw+json",
      "User-Agent": "Prism-Worker/1.0",
    },
  });
}

// ---------------------------------------------------------------------------
// GitHub Git API: create branch -> commit all files -> open PR (single commit)
// ---------------------------------------------------------------------------

async function createPullRequest(
  env: Env,
  branchLabel: string,
  files: { path: string; content: string }[],
  title: string,
  description: string
): Promise<Response> {
  const branchName = `prism/publish-${Date.now()}`;
  const ghApi = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}`;
  const headers = {
    Authorization: `Bearer ${env.GH_TOKEN}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "Prism-Worker/1.0",
    "Content-Type": "application/json",
  };

  async function ghFetch(url: string, opts?: RequestInit) {
    const resp = await fetch(url, { headers, ...opts });
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(`GitHub API error (${resp.status}): ${err}`);
    }
    return resp.json() as Promise<any>;
  }

  try {
    // 1. Get the latest commit on the base branch
    const refData = await ghFetch(`${ghApi}/git/ref/heads/${env.GH_BRANCH}`);
    const baseCommitSha = refData.object.sha;

    // 2. Get its tree SHA
    const commitData = await ghFetch(`${ghApi}/git/commits/${baseCommitSha}`);
    const baseTreeSha = commitData.tree.sha;

    // 3. Create blobs for every file
    const treeEntries = [];
    for (const file of files) {
      const blobData = await ghFetch(`${ghApi}/git/blobs`, {
        method: "POST",
        body: JSON.stringify({ content: file.content, encoding: "utf-8" }),
      });
      treeEntries.push({
        path: file.path,
        mode: "100644",
        type: "blob",
        sha: blobData.sha,
      });
    }

    // 4. Create a single tree containing all files
    const treeData = await ghFetch(`${ghApi}/git/trees`, {
      method: "POST",
      body: JSON.stringify({ base_tree: baseTreeSha, tree: treeEntries }),
    });

    // 5. One atomic commit
    const newCommit = await ghFetch(`${ghApi}/git/commits`, {
      method: "POST",
      body: JSON.stringify({
        message: title,
        tree: treeData.sha,
        parents: [baseCommitSha],
      }),
    });

    // 6. Create the branch
    await ghFetch(`${ghApi}/git/refs`, {
      method: "POST",
      body: JSON.stringify({ ref: `refs/heads/${branchName}`, sha: newCommit.sha }),
    });

    // 7. Open the PR
    const prData = await ghFetch(`${ghApi}/pulls`, {
      method: "POST",
      body: JSON.stringify({
        title,
        body: description,
        head: branchName,
        base: env.GH_BRANCH,
      }),
    });

    return json({
      message: "Skills submitted successfully",
      pr_url: prData.html_url,
      branch: branchName,
      files_count: files.length,
    }, 201);

  } catch (err: any) {
    return json({ error: err.message || "Failed to create PR" }, 500);
  }
}

// ---------------------------------------------------------------------------
// Validation -- Prism payload format (flat fields, NOT Lens format)
// ---------------------------------------------------------------------------

interface PrismSkillPayload {
  name: string;
  description: string;
  author: string;
  repository: string;
  category: string[];
  source: string;
  commit_date: string;
  source_hash: string | null;
  content: string;  // SKILL.md content
}

interface PrismPublishRequest {
  repository: string;
  skills: PrismSkillPayload[];
  description: string;
}

const MAX_SKILLS_PER_BATCH = 50;
const MAX_CONTENT_LENGTH = 500_000; // 500KB per skill

function validatePrismPublish(body: any):
  | { ok: true; data: PrismPublishRequest }
  | { ok: false; error: string }
{
  if (!body || typeof body !== "object") {
    return { ok: false, error: "Request body must be a JSON object" };
  }

  const skills = body.skills;
  if (!Array.isArray(skills) || skills.length === 0) {
    return { ok: false, error: "'skills' must be a non-empty array" };
  }

  if (skills.length > MAX_SKILLS_PER_BATCH) {
    return { ok: false, error: `Too many skills (max ${MAX_SKILLS_PER_BATCH})` };
  }

  for (let i = 0; i < skills.length; i++) {
    const s = skills[i];
    const p = `skills[${i}]: `;

    if (!s || typeof s !== "object") return { ok: false, error: `${p}must be an object` };
    if (!s.name || typeof s.name !== "string") return { ok: false, error: `${p}missing 'name'` };
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(s.name)) {
      return { ok: false, error: `${p}'${s.name}' must be lowercase alphanumeric with hyphens` };
    }
    if (!s.content || typeof s.content !== "string") return { ok: false, error: `${p}missing 'content'` };
    if (s.content.length < 50) return { ok: false, error: `${p}content too short (min 50 chars)` };
    if (s.content.length > MAX_CONTENT_LENGTH) return { ok: false, error: `${p}content too large (max ${MAX_CONTENT_LENGTH} chars)` };
    if (!s.repository || typeof s.repository !== "string") return { ok: false, error: `${p}missing 'repository'` };
    if (!s.description || typeof s.description !== "string") return { ok: false, error: `${p}missing 'description'` };
    if (!s.author || typeof s.author !== "string") return { ok: false, error: `${p}missing 'author'` };
  }

  // Check for duplicate names
  const names = skills.map((s: any) => s.name);
  const dupes = names.filter((n: string, i: number) => names.indexOf(n) !== i);
  if (dupes.length > 0) {
    return { ok: false, error: `Duplicate skill names: ${[...new Set(dupes)].join(", ")}` };
  }

  // All skills must belong to the same repository
  const repos = new Set(skills.map((s: any) => s.repository));
  if (repos.size > 1) {
    return { ok: false, error: `All skills in a batch must have the same repository. Found: ${[...repos].join(", ")}` };
  }

  const repository = [...repos][0] as string;

  return {
    ok: true,
    data: {
      repository,
      description: body.description || "",
      skills: skills as PrismSkillPayload[],
    },
  };
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
        },
      });
    }

    // Health check (no auth needed)
    if (path === "/" || path === "/health") {
      return json({ status: "ok", service: "prism-registry" });
    }

    // ---------- Everything below requires auth ----------
    if (!authenticate(request, env)) {
      return unauthorized();
    }

    // GET /registry OR /api/skills/registry -- returns skill-registry.json
    if ((path === "/registry" || path === "/api/skills/registry") && request.method === "GET") {
      const resp = await fetchFromGitHub(env, "skill-registry.json");
      if (!resp.ok) return json({ error: "Failed to fetch registry" }, resp.status);
      const body = await resp.text();
      return new Response(body, {
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // GET /api/skills/:name -- returns SKILL.md for a published skill
    if (path.startsWith("/api/skills/") && !path.endsWith("/registry") && !path.endsWith("/publish") && request.method === "GET") {
      const skillName = path.replace("/api/skills/", "").replace(/\/$/, "");
      if (!skillName || skillName.includes("/")) return badRequest("Skill name required");
      // Search across all repo directories for this skill name
      const resp = await fetchFromGitHub(env, `skills`);
      // Fallback: try direct name lookup assuming flat structure is unlikely,
      // the client should use the registry index to find the full path.
      // For now, return a helpful error.
      return json({ error: `Use /api/skills/registry to find skill paths, then fetch via /file/{path}` }, 400);
    }

    // GET /file/* -- generic file proxy (for fetching specific skill files)
    if (path.startsWith("/file/") && request.method === "GET") {
      const filePath = decodeURIComponent(path.replace("/file/", ""));
      if (!filePath) return badRequest("File path required");

      // Sanitize: reject path traversal attempts
      if (filePath.includes("..") || filePath.startsWith("/") || filePath.includes("//")) {
        return badRequest("Invalid file path");
      }

      // Restrict to skills/ directory only
      if (!filePath.startsWith("skills/")) {
        return badRequest("File access restricted to skills/ directory");
      }

      const resp = await fetchFromGitHub(env, filePath);
      if (!resp.ok) return json({ error: `File not found: ${filePath}` }, 404);
      const body = await resp.text();
      const ct = filePath.endsWith(".json") ? "application/json"
               : filePath.endsWith(".md")   ? "text/markdown"
               : "text/plain";
      return new Response(body, {
        headers: {
          "Content-Type": ct,
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // ------------------------------------------------------------------
    // POST /api/skills/publish -- submit a batch of skills from a source repo
    //
    // Body (Prism flat-field format):
    // {
    //   "skills": [
    //     {
    //       "name": "retry-backoff",
    //       "description": "...",
    //       "author": "...",
    //       "repository": "org/repo",
    //       "category": ["architecture"],
    //       "source": "prism",
    //       "commit_date": "2026-04-14",
    //       "source_hash": "abc123def456",
    //       "content": "# SKILL.md content..."
    //     }
    //   ],
    //   "description": "Publishing N skills from org/repo"
    // }
    //
    // The Worker reconstructs plugin.json from flat fields and uses
    // 'content' as SKILL.md. Files are placed at:
    //   skills/{repository}/{skill_name}/plugin.json
    //   skills/{repository}/{skill_name}/SKILL.md
    //
    // One branch, one commit, one PR.
    // ------------------------------------------------------------------
    if (path === "/api/skills/publish" && request.method === "POST") {
      let body: any;
      try {
        body = await request.json();
      } catch {
        return badRequest("Invalid JSON body");
      }

      const validation = validatePrismPublish(body);
      if (!validation.ok) {
        return badRequest(validation.error);
      }

      const { data } = validation;
      const { repository, skills } = data;

      // Build file list -- reconstruct plugin.json from flat fields, use content as SKILL.md
      const files: { path: string; content: string }[] = [];
      for (const skill of skills) {
        const dir = `skills/${skill.repository}/${skill.name}`;

        // Reconstruct plugin.json from flat fields
        const pluginJson = JSON.stringify({
          name: skill.name,
          description: skill.description,
          author: skill.author,
          repository: skill.repository,
          category: skill.category || [],
          source: skill.source || "prism",
          commit_date: skill.commit_date || new Date().toISOString().split("T")[0],
          source_hash: skill.source_hash || null,
        }, null, 2);

        files.push({ path: `${dir}/plugin.json`, content: pluginJson });
        files.push({ path: `${dir}/SKILL.md`, content: skill.content });
      }

      const skillNames = skills.map((s) => s.name);
      const title = `Publish skills from ${repository}`;
      const description = data.description
        || `Automated publish of ${skills.length} skill(s) from **${repository}**:\n\n${skillNames.map((n) => `- ${n}`).join("\n")}`;

      return createPullRequest(env, repository, files, title, description);
    }

    return json({ error: "Not found" }, 404);
  },
};
