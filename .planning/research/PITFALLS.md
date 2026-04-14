# Pitfalls Research

**Domain:** Knowledge layer for AI coding assistants (hook-based observation, extraction pipeline, skill registry)
**Researched:** 2026-04-14
**Confidence:** HIGH (based on source code review of Engram + Lens, official Claude Code docs, CVE records, real-world JSONL corruption issues)

## Critical Pitfalls

### Pitfall 1: Shell Injection via Capture Hook Variable Interpolation

**What goes wrong:**
The existing `capture.sh` builds a Python dict using shell variable interpolation on line 88-100: `'timestamp': '$TIMESTAMP'`, `'input_summary': '''$INPUT_SUMMARY'''`. If a tool input contains single quotes or backticks, the resulting Python code breaks or executes unintended content. A carefully crafted tool input could inject Python code through the `INPUT_SUMMARY` variable. This is not theoretical -- Claude Code tool inputs regularly contain complex strings, code snippets, and regex patterns with quotes.

**Why it happens:**
The original Engram code was a proof-of-concept. Embedding shell variables directly into Python string literals via `python3 -c` is fragile. The triple-quote escaping on line 99 (`.replace("'''", '')`) only handles one edge case.

**How to avoid:**
Rewrite the observation serialization to pass data through stdin to Python (pipe the JSON, parse it in Python, emit the observation). Never interpolate untrusted shell variables into Python string literals. Use Python's `json.dumps()` for all serialization. The capture hook should read stdin once and do ALL processing in a single Python invocation rather than multiple `python3 -c` calls.

**Warning signs:**
- Observations with missing or corrupted fields in `observations.jsonl`
- Occasional hook errors in stderr (Python syntax errors)
- Empty `input_summary` fields where there should be content

**Phase to address:**
Phase 1 (Core/Foundation) -- this is in the critical path for all observation capture. Fix during the port from Engram to Prism.

---

### Pitfall 2: Hook Blocking Claude Code Despite "Exit 0 Always" Contract

**What goes wrong:**
The capture hook invokes `python3` synchronously three times (field extraction, summary building, serialization) plus `git remote get-url origin` and `shasum`. If Python startup is slow (cold cache, pyenv shim overhead, virtualenv resolution), the hook takes 500ms-2s. Multiplied by every PreToolUse and PostToolUse event, this adds perceptible lag to every Claude Code action. The Claude Code hooks system defaults to a 600s timeout and runs hooks synchronously for blocking events (PreToolUse). Even for non-blocking events, a slow hook holds up processing.

**Why it happens:**
Python cold start is ~80-150ms. Three Python invocations = ~300-450ms minimum. On systems with pyenv/asdf shims, `python3` resolution adds another 50-200ms per call. The `git remote get-url` can hang on network-mounted repos or repos without remotes configured.

**How to avoid:**
1. Use `async: true` in the hook configuration (Claude Code supports this since January 2026 -- the hook outputs `{"async":true}` as first line and backgrounds itself).
2. Reduce to a single Python invocation: read stdin, parse JSON, build observation, write to file -- all in one process.
3. Cache the project ID (write it to `.prism/project_id` on `prism init`, read it back instead of computing every time).
4. Set a conservative timeout (5s) so even a hung hook doesn't block indefinitely.
5. For PostToolUse (non-blocking), use `async: true` unconditionally.

**Warning signs:**
- Users reporting "Claude Code feels slow after installing Prism"
- Hook timeout errors in Claude Code debug logs
- High `python3` process count during active sessions

**Phase to address:**
Phase 1 (Core/Foundation) -- hook performance is the make-or-break for adoption. A slow hook means immediate uninstall.

---

### Pitfall 3: JSONL Concurrent Write Corruption

**What goes wrong:**
Multiple concurrent processes can append to `observations.jsonl` simultaneously: the capture hook fires for every tool use (often overlapping when Claude runs multiple tools), the session reviewer appends insights, and background extraction reads while a new hook appends. On real Claude Code sessions, there are documented cases of JSONL corruption from interleaved writes (Claude Code's own session files suffer this exact problem -- see GitHub issues #20992, #29051, #29198, #29217).

**Why it happens:**
POSIX `O_APPEND` is only atomic for writes under `PIPE_BUF` (4096 bytes on Linux, varies on macOS). Most observations are under this limit, but longer tool inputs or session insights can exceed it. More importantly, the Python `open("a")` + `write()` pattern is not guaranteed atomic -- buffering can split a single JSON line across two kernel writes.

**How to avoid:**
1. Use `os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)` + `os.write()` with a single byte-string (no Python buffering).
2. Keep each observation line under 4096 bytes (already approximately enforced by the 500-char payload truncation).
3. Add a newline-recovery step in the extraction reader: skip lines that fail `json.loads()` instead of crashing.
4. Consider per-session observation files (`observations_{session_id}.jsonl`) to reduce contention.

**Warning signs:**
- `json.loads()` errors when reading observations
- Observations with merged content from two different events on the same line
- Extraction reporting "0 observations" when the file is clearly non-empty

**Phase to address:**
Phase 1 (Core/Foundation) -- observations are the input to the entire pipeline. Corrupt observations = garbage engrams.

---

### Pitfall 4: Secret Leakage Through Observation Capture

**What goes wrong:**
The scrubbing patterns in `config.py` cover common token formats (sk-*, ghp_*, bearer, xoxb-) but miss: AWS access keys (AKIA...), private keys (BEGIN RSA/EC/OPENSSH PRIVATE KEY), database connection strings (postgres://user:pass@..., mongodb+srv://...), JWT tokens, base64-encoded credentials in headers, .env file contents captured through Write/Edit tool observations, and webhook URLs containing secrets. The 500-char truncation helps but doesn't prevent leakage in the first 500 chars. Once leaked to `observations.jsonl`, the secret persists through extraction and could end up in an engram, then in `.claude/prism.md`, and eventually in a published skill.

**Why it happens:**
Secret patterns are unbounded -- new services introduce new formats constantly. Regex-only approaches have both high false positive rates (disrupting useful observations) and false negatives (missing novel secret formats). The Engram scrubber is a minimal starting point, not a comprehensive solution.

**How to avoid:**
1. Expand the default scrub patterns to cover AWS keys (`AKIA[0-9A-Z]{16}`), connection strings (`[a-z]+://[^:]+:[^@]+@`), private keys (`-----BEGIN .* PRIVATE KEY-----`), and JWTs (`eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`).
2. Add entropy-based detection: any token-like string (alphanumeric, 20+ chars, high entropy) adjacent to assignment operators should be flagged.
3. Add a scrub validation step in the extraction pipeline: the validator (Sonnet) should have an explicit safety gate checking for embedded secrets.
4. Never include raw `input_summary` in published skills -- the promotion pipeline must re-scrub.
5. Allow users to add custom patterns via `config.json`.

**Warning signs:**
- Grep for common secret prefixes in `observations.jsonl` or engram files
- Users reporting secrets visible in `.claude/prism.md`
- Security audit finding credentials in archived observations

**Phase to address:**
Phase 1 (Core/Foundation) for expanded scrub patterns. Phase 2 (Extraction) for validator gate. Phase 3 (Registry/Publishing) for re-scrub on promotion.

---

### Pitfall 5: Extraction Quality Drift -- AI Writing Instructions for AI

**What goes wrong:**
The two-phase extraction uses Haiku to propose engrams and Sonnet to validate them. Both receive file system access (`--allowedTools Read,Write,Glob,Grep` for Haiku; adds `Edit,Bash` for Sonnet). The core quality risk is "meta-instruction drift": Haiku generates engrams that are vague, over-general, or subtly wrong because it's summarizing tool usage patterns, not actual human preferences. Examples: "Always use TypeScript" extracted from a session where the user happened to be working on a TypeScript project, or "Prefer functional components" extracted from a React session where no class components existed (absence =/= preference). These false positives accumulate and corrupt the knowledge base, making Claude less helpful over time.

**Why it happens:**
LLM extraction from tool usage traces is inherently lossy. The observations capture what happened but not why. Without explicit user signals (corrections, stated preferences), the extractor hallucinates intent from behavior. The session reviewer helps but has the same fundamental problem -- it reads conversation transcript and infers preferences that may have been situational.

**How to avoid:**
1. Start all extracted engrams at low confidence (0.4-0.5), not 0.5-0.7. Require reinforcement before they affect behavior.
2. Add a "requires human confirmation" state for extracted engrams -- show them in `prism status` with a [?] marker, let users approve/reject.
3. The extractor prompt must explicitly instruct: "Only extract preferences the user explicitly stated or corrected. Do not infer preferences from what tools were used."
4. Add negative examples to the extractor prompt: "Do NOT extract: 'User prefers X' when X was simply what was available."
5. Weight session_insight observations higher than tool_start/tool_end for preference extraction.
6. Track extraction false positive rate: if users frequently `prism forget` recently extracted engrams, reduce extraction aggressiveness.

**Warning signs:**
- Engrams that sound generic (could apply to any developer)
- Users running `prism forget` frequently
- `.claude/prism.md` containing advice that contradicts user behavior
- Low evidence_count engrams persisting at medium confidence

**Phase to address:**
Phase 2 (Extraction Pipeline) -- this is the quality-defining phase. Get this wrong and the product actively harms users.

---

### Pitfall 6: Index.json as Single Point of Failure

**What goes wrong:**
The entire engram knowledge base depends on `index.json` -- a single JSON file that is read-modify-written on every `add_engram()`, `remove_engram()`, and `update_confidence()` call. It has no locking, no atomic writes, and no backup. A crash during `save_index()` produces a truncated file. A concurrent extraction + MCP record produces a race condition where one write clobbers the other's changes. Over months of use, a single corruption event loses the entire index.

**Why it happens:**
The `load_index()` / `save_index()` pattern is the simplest possible implementation. It works perfectly for single-threaded use but fails with concurrent access (background extraction + MCP server + manual CLI + decay cycle all access the same file).

**How to avoid:**
1. Use atomic writes: write to `index.json.tmp`, then `os.rename()` to `index.json` (atomic on POSIX).
2. Add file locking: `fcntl.flock()` around all index mutations.
3. Keep a backup: copy `index.json` to `index.json.bak` before each write.
4. Add recovery: if `index.json` fails to parse, check `.bak`, then rebuild from engram files on disk.
5. Consider SQLite for the index if concurrency needs grow -- but the zero-dependency constraint means this should be a last resort.

**Warning signs:**
- `json.JSONDecodeError` when loading index
- Missing engrams that were previously confirmed to exist
- Duplicate entries in the index
- `prism status` showing 0 engrams unexpectedly

**Phase to address:**
Phase 1 (Core/Foundation) -- atomic writes and backup are essential from day one.

---

### Pitfall 7: Codebase Merge Name Collision and Convention Conflict

**What goes wrong:**
Engram and Lens have fundamentally different conventions: Engram is Python with `snake_case`, JSONL data files, and `~/.engram/` file tree; Lens is Markdown slash commands + TypeScript Worker + JSON schemas with `kebab-case` skill names. The merge requires renaming (`engram` -> `prism`, `ENGRAM_HOME` -> `PRISM_HOME`, MCP tools renamed) across every file. Incomplete renames create subtle bugs: a leftover `ENGRAM_HOME` reference reads from `~/.engram/` instead of `~/.prism/`, splitting state between two directories. Lens's skill names use `kebab-case` while Engram's engram IDs are generated from slugified text -- if the slugification rules differ, promoted engrams get ID mismatches with their skill counterparts.

**Why it happens:**
Find-and-replace renames are brittle. The two codebases embed their identities in environment variables, file paths, CLI names, MCP tool names, config keys, and user-facing strings. Missing even one creates a hard-to-diagnose bug where half the system reads from the old location.

**How to avoid:**
1. Create a comprehensive rename checklist covering: env vars, file paths, CLI command names, MCP tool names, config keys, import paths, user-facing strings, error messages, README/docs references.
2. Use `grep -r "engram\|ENGRAM\|Engram" --include="*.py" --include="*.sh" --include="*.md" --include="*.json"` after the rename to verify zero leftover references.
3. Write an integration test that sets `PRISM_HOME` to a temp dir and verifies no files are created under `~/.engram/`.
4. Standardize ID generation: one slugification function used for both engram IDs and skill names.
5. Document the naming convention (kebab-case for all identifiers) and enforce it programmatically.

**Warning signs:**
- Any reference to "engram" in the codebase after Phase 1 (except historical docs)
- Files appearing under `~/.engram/` when only `~/.prism/` should be used
- MCP tool names not matching documentation
- `prism status` reporting different counts than file system shows

**Phase to address:**
Phase 1 (Core/Foundation) -- do the rename once, verify exhaustively, then never look back.

---

### Pitfall 8: Registry Token Security -- Timing Attacks and Plain-Text Comparison

**What goes wrong:**
The Cloudflare Worker authenticates requests by splitting `REGISTRY_TOKENS` by comma and checking `validTokens.includes(token)` (line 53 of `index.ts`). JavaScript's `Array.includes()` uses `===` comparison which is vulnerable to timing attacks -- an attacker can determine token characters one at a time by measuring response latency. Additionally, tokens are stored as a comma-separated string in a single environment variable, making rotation painful (must update the entire string to revoke one token).

**Why it happens:**
Simple string comparison is the obvious implementation. Timing attacks feel academic until someone actually exploits them. The comma-separated format was expedient for a single-registry prototype.

**How to avoid:**
1. Use constant-time comparison: Cloudflare Workers support `crypto.subtle.timingSafeEqual()`. Hash both the provided token and each stored token before comparing.
2. Store tokens as hashed values (SHA-256) in the environment variable. The client sends the raw token, the worker hashes it and compares hashes.
3. Support per-token metadata: `{hash, name, created, scopes}` stored in Workers KV, not env vars. This enables individual revocation and audit trails.
4. Add rate limiting on auth failures (Workers KV counter or Cloudflare Rate Limiting rules).
5. Token generation should use `crypto.randomUUID()` or `crypto.getRandomValues()` with sufficient entropy (32+ bytes, base62-encoded).

**Warning signs:**
- No rate limiting on the `/publish` endpoint
- Token revocation requiring Worker redeployment
- Tokens not expiring after creation

**Phase to address:**
Phase 3 (Registry) -- but design the token model in Phase 1 to avoid migration pain.

---

### Pitfall 9: MCP Server Stdout Contamination

**What goes wrong:**
The MCP server uses stdio transport (JSON-RPC over stdin/stdout). Any print statement, logging call, or unhandled exception traceback that writes to stdout instead of stderr corrupts the MCP message stream. Claude Code will receive malformed JSON, disconnect the MCP server, and the user loses all MCP-based knowledge access for the session. The existing code correctly uses `sys.stderr.write()` for startup logging, but any future modification that adds a `print()` call will silently break the server.

**Why it happens:**
Python's `print()` defaults to stdout. It's the most natural debugging tool, and every developer's first instinct. The constraint "nothing may ever go to stdout except JSON-RPC messages" is invisible and easily violated, especially by contributors who don't understand the MCP protocol. Library imports that print warnings (deprecation notices, etc.) also corrupt the stream.

**How to avoid:**
1. Redirect stdout at process startup: `sys.stdout = sys.stderr` after saving the real stdout for MCP output. Use the saved fd exclusively for JSON-RPC.
2. Add a wrapper function for MCP output: `_mcp_send(msg)` that writes to the saved original stdout, never to `sys.stdout`.
3. Add a CI test that imports the MCP server module and asserts nothing was written to stdout during import.
4. Suppress Python warnings that might go to stdout: `import warnings; warnings.filterwarnings('ignore')` or redirect warnings to stderr.
5. Document the constraint prominently in the MCP server source file.

**Warning signs:**
- MCP server disconnects mid-session
- Claude Code reporting "MCP server error" or "invalid JSON"
- Works locally but fails when Python version differs (different deprecation warnings)

**Phase to address:**
Phase 1 (Core/Foundation) -- the MCP server is a primary knowledge access channel.

---

### Pitfall 10: Custom YAML Frontmatter Parser Breaking on Edge Cases

**What goes wrong:**
The `_parse_engram_frontmatter()` function in `extract.py` implements a custom YAML parser to maintain zero-dependency status. It handles simple `key: value` pairs and basic `[list]` syntax, but fails on: multiline values, values containing colons (URLs, time strings), nested structures, quoted strings containing brackets, boolean/null edge cases ("yes"/"no"/"~"), and comments within frontmatter. As engrams accumulate, edge cases eventually corrupt the index because a parsing failure returns `None` and the engram is silently dropped.

**Why it happens:**
YAML is deceptively complex. A simple line-by-line parser handles 90% of cases but the remaining 10% fails silently. The zero-dependency constraint rules out PyYAML, so a custom parser is necessary -- but the current one is too naive.

**How to avoid:**
1. Define a strict subset: "Prism frontmatter" is not YAML. It's `key: value` pairs where values are single-line strings, numbers, booleans, or `[comma, separated, lists]`. Document this explicitly.
2. Validate on write: the extraction pipeline should only produce frontmatter in the supported subset. Add a `validate_frontmatter()` function that rejects unsupported syntax.
3. Handle colons in values: split on first `:` only (already done), but also handle the case where the value starts with `http://` or contains time strings.
4. Add unit tests for every edge case: URLs as values, empty values, trailing spaces, values that look like booleans, values with brackets that aren't lists.
5. On parse failure, log a warning and fall back to reading the file's trigger from the filename rather than silently returning `None`.

**Warning signs:**
- Engrams with URLs in frontmatter disappearing from the index
- Parse failures in `validation-log.jsonl`
- Mismatched counts between files on disk and index entries

**Phase to address:**
Phase 1 (Core/Foundation) for parser hardening. Phase 2 (Extraction) for write-side validation.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Multiple `python3 -c` calls in capture.sh | Easy to read, each step isolated | 300ms+ overhead per hook invocation, shell injection risk | Never -- rewrite to single invocation in Phase 1 |
| Comma-separated token string in Worker env | Simple config, no KV dependency | Can't revoke individual tokens, no audit trail, timing attack surface | MVP only -- migrate to KV-backed tokens in Phase 3 |
| JSON file as index (no locking) | Zero dependencies, simple code | Corruption under concurrency | Acceptable if atomic writes + backup added in Phase 1 |
| Custom YAML frontmatter parser | Zero dependencies | Silent data loss on edge cases | Acceptable if strict subset defined and validated |
| `nohup ... &` for background extraction | Works on all POSIX systems | No cleanup of zombie/orphan processes, no way to track completion | Acceptable for MVP, add process tracking in later phase |
| Hardcoded 500-char payload truncation | Keeps observations small | May miss context needed for accurate extraction | Acceptable -- revisit if extraction quality is low |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Code hooks (PreToolUse/PostToolUse) | Using `cat` to read stdin then passing through shell variables | Read stdin once in Python, process entirely in Python, avoid shell variable interpolation of untrusted data |
| Claude Code hooks (async mode) | Assuming all hooks run asynchronously | Only hooks with `"async": true` run in background. PreToolUse is always synchronous (it decides whether to proceed). Use PostToolUse with async for observation capture |
| Claude Code MCP (stdio) | Using `print()` for debugging | All debug output must go to `sys.stderr`. Redirect stdout immediately at startup |
| GitHub API (Worker) | Sequential blob creation for multi-file PRs | Current implementation creates blobs sequentially (line 115-125 of Worker). For large publishes, use `Promise.all()` for parallel blob creation |
| `claude --print` CLI for extraction | Assuming the CLI is always available | The `claude` CLI may not be on PATH in background processes spawned by `nohup`. Use absolute path resolution at install time and store in config |
| Cloudflare Worker secrets | Storing tokens in `wrangler.toml` | Use `wrangler secret put` for all secrets. Never commit secrets to source control, even in template repos |
| Session transcript reading | Assuming transcript path format is stable | Claude Code's `~/.claude/projects/` structure may change between versions. Use `transcript_path` from hook input instead of deriving it |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Reading entire `index.json` for every MCP search | Increasing latency as engram count grows | Cache index in memory with mtime-based invalidation | ~500+ engrams (index.json > 100KB, parse time > 50ms) |
| Glob-scanning engram directories for count | `prism status` takes seconds | Use index as source of truth, not filesystem glob | ~200+ engram files |
| Full-file re-read for JSONL observation counting | Hook trigger check (`wc -l`) re-reads entire file | Keep a counter file or use `stat` file size estimate | ~10K+ observations (10MB+ file) |
| GitHub API calls per registry on every `advise-skills` query | Timeouts, rate limits, slow responses | 24h TTL cache for `skill-registry.json` (already planned). Serve from local cache, refresh in background | 3+ registries, each with 100+ skills |
| `_search()` Jaccard similarity on all engrams | Linear scan with tokenization per query | Pre-compute token sets on index load, cache until index changes | ~1000+ engrams |
| Extraction spawning `claude --print` in background | Multiple simultaneous extractions if lock check races | Use `O_CREAT | O_EXCL` for lock file (already implemented in extract.py). Ensure capture.sh also checks lock before spawning |  When extraction takes > 2 minutes and new threshold is hit |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Secrets in observations surviving through extraction to published skills | API keys, tokens, passwords visible in team registry | Multi-layer scrubbing: capture-time, extraction-time, publish-time. Add entropy detection. Validator safety gate must check for secret patterns |
| Hook scripts executable by other users on shared machines | Another user modifies capture hook to exfiltrate data | Install hooks with `chmod 700`. Verify hook file integrity on `prism init` |
| Worker REGISTRY_TOKENS in plain text in env var | Token compromise requires full redeployment to rotate | Hash tokens before storage, support per-token revocation via KV |
| `--allowedTools Bash` on Sonnet validator | Extraction validation step can execute arbitrary commands | Remove `Bash` from validator allowedTools. Sonnet only needs `Read,Write,Edit,Glob,Grep` to validate candidates. Bash access during validation is unnecessary risk |
| MCP server runs with user's full filesystem access | Malicious prompt injection could attempt to read sensitive files via engram paths | MCP server should validate that all file paths are under `PRISM_HOME`. No path traversal allowed |
| `git remote get-url origin` in hook exposes repo URL | Repo URLs may contain tokens (https://token@github.com/...) | Use `shasum` only on the URL (already done), never log the raw URL. Scrub the remote URL before any use |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent extraction failures (nohup suppresses all output) | User never knows extraction ran, failed, or what it produced | Write extraction results to a log file. Show summary on next `prism status`. Add `prism extract --verbose` for debugging |
| Engram decay happening invisibly | User's preferences disappear without notice. "Why did Claude forget that I hate semicolons?" | Show decaying engrams in `prism status` with time-until-archive. Notify when a previously active engram is archived |
| `prism init` modifying `~/.claude/settings.json` | User's existing hooks overwritten or conflicted | Merge hooks, don't replace. Check for existing hooks before adding. Show diff of what will change and require confirmation |
| Too many engrams in `.claude/prism.md` (system prompt bloat) | Claude Code performance degrades, context window wasted | Enforce the max_context_lines limit strictly. Prioritize ruthlessly (corrections > pinned > high-confidence). Show context budget in `prism status` |
| Registry publish creating PRs without feedback | User runs publish, sees no output, doesn't know if it worked | Return PR URL immediately. Show publish status in CLI. Handle GitHub API errors with actionable messages |
| Cold start: new install with zero engrams feels useless | User installs, nothing happens, uninstalls | `prism analyze-sessions` to bootstrap from existing session history. Show first-run guide explaining that learning takes a few sessions |

## "Looks Done But Isn't" Checklist

- [ ] **Hook installation:** Often missing re-run safety -- verify `prism init` is idempotent (running twice doesn't duplicate hooks in settings.json)
- [ ] **MCP server registration:** Often missing unregistration -- verify `prism uninstall` removes the MCP server from Claude Code config
- [ ] **Secret scrubbing:** Often missing new patterns -- verify against AWS, GCP, Azure, Stripe, Twilio token formats, not just GitHub/OpenAI
- [ ] **Extraction lock cleanup:** Often missing crash recovery -- verify stale lock files (older than 10 min) are cleaned up on next run
- [ ] **Cross-platform `shasum`:** Often missing Linux compatibility -- macOS uses `shasum`, Linux may need `sha256sum`. Verify on both
- [ ] **`date -u` format:** Often missing portability -- macOS `date` and GNU `date` have different flags. `date -u +"%Y-%m-%dT%H:%M:%SZ"` works on both but verify
- [ ] **Installer PATH setup:** Often missing shell profile detection -- verify the CLI wrapper works in bash, zsh, and fish (or document fish as unsupported)
- [ ] **Multi-registry read merge:** Often missing conflict resolution -- verify what happens when two registries have skills with the same name
- [ ] **Decay cycle scheduling:** Often missing automation -- verify `prism maintain` runs on a schedule (cron/launchd) or is triggered automatically, not just manually
- [ ] **Constitution protection:** Often missing overwrite prevention -- verify that `install.sh` re-run preserves user-modified constitution.md

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Corrupted index.json | LOW | Rebuild from engram files on disk: glob `~/.prism/**/engrams/*.md`, parse frontmatter, reconstruct index. Add `prism repair` command |
| Corrupted observations.jsonl | LOW | Skip malformed lines during extraction. Archive the corrupted file. No data loss beyond the corrupted lines |
| Secret leaked in observation/engram | MEDIUM | Remove the engram (`prism forget`), scrub archived observations, rotate the leaked credential. If published to registry, create PR to remove, revoke registry token if exposed |
| Wrong engrams extracted (quality drift) | MEDIUM | `prism forget` individual bad engrams. Lower confidence thresholds. Review and tune extractor/validator prompts. Run `prism maintain` to force re-evaluation |
| Hook breaking Claude Code | LOW | Remove hook from `~/.claude/settings.json`. Claude Code continues normally. Fix hook, re-add. Always test hooks in isolation first |
| MCP server crash loop | LOW | Claude Code will show error and continue without MCP tools. Fix server, restart Claude Code session. Users still have `.claude/prism.md` push layer |
| Registry Worker down | LOW | All reads served from 24h TTL cache. Publishes queue locally. Worker recovery restores service. No knowledge lost |
| Full index loss (no backup) | HIGH | If no `.bak` file exists, must re-extract from archived observations + session transcripts. `prism analyze-sessions` can partially rebuild. Manual knowledge (via `prism learn`) is lost |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Shell injection in capture hook | Phase 1: Core | Zero shell variable interpolation in Python strings. Code review pass |
| Hook blocking Claude Code | Phase 1: Core | Measure hook execution time in CI. Target: < 50ms for capture, < 5ms for async handoff |
| JSONL concurrent write corruption | Phase 1: Core | Concurrent write stress test: 100 parallel appends, verify all lines parse |
| Secret leakage | Phase 1: Core + Phase 2: Extraction + Phase 3: Registry | Scrub test suite with real-world secret formats. Grep audit on every extraction run |
| Extraction quality drift | Phase 2: Extraction | Manual review of first 20 extracted engrams. False positive tracking metric |
| Index.json corruption | Phase 1: Core | Crash simulation test: kill process mid-write, verify recovery |
| Codebase merge name collision | Phase 1: Core | Zero-match grep for old names (engram/ENGRAM) after rename. Integration test with clean PRISM_HOME |
| Registry token security | Phase 3: Registry | Timing attack test (response time variance < 1ms). Token rotation without redeployment |
| MCP stdout contamination | Phase 1: Core | CI test: import MCP module, assert stdout empty. Redirect stdout at startup |
| Custom frontmatter parser | Phase 1: Core + Phase 2: Extraction | Unit tests for 15+ edge cases. Validation on write side |

## Sources

- Engram source code review: `/Users/gaurav/codes/engram/` (hooks/capture.sh, lib/extract.py, lib/scrub.py, lib/mcp_server.py, lib/index.py, lib/sync.py, lib/review.py, lib/trigger.py, lib/config.py)
- Lens source code review: `/Users/gaurav/codes/Lens/` (cloudfare_worker/src/index.ts, scripts/validate.py)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- official documentation, 28 hook events, async mode, exit code semantics
- [CVE-2025-59536: RCE via Claude Code project files](https://research.checkpoint.com/2026/rce-and-api-token-exfiltration-through-claude-code-project-files-cve-2025-59536/) -- Check Point Research, hook security vulnerability
- Claude Code JSONL corruption issues: [#20992](https://github.com/anthropics/claude-code/issues/20992), [#29051](https://github.com/anthropics/claude-code/issues/29051), [#29198](https://github.com/anthropics/claude-code/issues/29198), [#29217](https://github.com/anthropics/claude-code/issues/29217)
- [Cloudflare Workers Secrets docs](https://developers.cloudflare.com/workers/configuration/secrets/) -- secret management best practices
- [Cloudflare Secrets Store Beta](https://blog.cloudflare.com/secrets-store-beta/) -- account-level secret management
- [MCP Transports specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) -- stdio protocol requirements
- [Gitleaks](https://github.com/gitleaks/gitleaks) -- secret detection regex patterns reference
- [Secrets-Patterns-DB](https://github.com/mazen160/secrets-patterns-db) -- 1600+ regex patterns for secret detection
- [MCP server troubleshooting](https://mcp.harishgarg.com/learn/mcp-server-troubleshooting-guide-2025) -- common -32000 errors and fixes

---
*Pitfalls research for: Knowledge layer for AI coding assistants (Prism)*
*Researched: 2026-04-14*
