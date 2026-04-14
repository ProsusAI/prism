# Feature Research

**Domain:** Knowledge layers / memory systems for AI coding assistants
**Researched:** 2026-04-14
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Cross-session persistence** | Every competitor (Claude Code auto-memory, Windsurf Memories, Copilot Memory, Cursor rules) persists knowledge across sessions. Users will not adopt a memory tool that forgets. | LOW | Prism already has this via engrams + `.claude/prism.md`. Standard expectation since mid-2025. |
| **Automatic learning from interactions** | Claude Code auto-memory, Windsurf auto-generated memories, and Copilot agentic memory all learn without manual effort. Users expect "use it and it gets smarter." | HIGH | Prism's hook-based observation + two-phase extraction pipeline already implements this. The extraction quality (Haiku propose, Sonnet validate) is the key differentiator. |
| **Manual knowledge management** | Every tool supports explicit instruction: CLAUDE.md, .cursorrules/.mdc, .windsurfrules, .github/copilot-instructions.md. Users expect to tell the system things directly. | LOW | Prism has `prism learn` / `prism correct` / `prism forget`. Table stakes. |
| **Project-scoped context** | All competitors scope memory per-project/workspace. Windsurf memories are workspace-scoped. Claude Code auto-memory is per-project. Copilot memories are per-repository. | LOW | Prism already supports project-scoped engrams via `PRISM_HOME` project directories. |
| **User/global scope** | Claude Code has `~/.claude/CLAUDE.md` for personal preferences across all projects. Windsurf has global rules. Cursor has user-level rules. | LOW | Prism supports `--scope global` on `prism learn`. Already planned. |
| **Context injection into sessions** | Users expect stored knowledge to appear automatically in AI context without manual loading each session. | MEDIUM | Prism does push injection (`.claude/prism.md`) and pull injection (MCP server with 4 tools). Both channels are standard. |
| **Safety/privacy for stored knowledge** | Users will not trust a memory system that stores API keys, tokens, or secrets. Secret scrubbing is assumed. | MEDIUM | Prism already has secret scrubbing on all captured observations (regex patterns for API keys, tokens, bearer, sk-*, ghp-*). This is table stakes -- every tool that captures text must do this. |
| **Plain-text, auditable storage** | Claude Code stores auto-memory as plain markdown files. Windsurf stores memories as local files. Users expect to read, edit, and delete what the system remembers. | LOW | Prism engrams are JSONL, and the rendered view is `.claude/prism.md`. Both are human-readable. |
| **CLI or command interface** | Developers expect command-line access. Claude Code has `/memory`, Cursor has settings UI + file editing, all Claude Code tools are CLI-native. | LOW | `prism` CLI with subcommands (`learn`, `correct`, `forget`, `status`, `maintain`). Already designed. |
| **Non-blocking capture** | Claude Code hooks are async by default. Users will not tolerate a memory system that slows down their coding flow. | LOW | `capture.sh` exits 0 always, spawns background processes. Already designed with this constraint. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Two-phase extraction with safety gates** | No competitor validates extracted knowledge through a multi-gate pipeline (constitution, evidence, contradiction, safety). Claude Code auto-memory is single-pass writes by the model. Windsurf auto-generates without validation. Copilot memories expire after 28 days as a blunt safety mechanism. Prism's Haiku-proposes-Sonnet-validates approach catches hallucinated preferences and contradictions. | HIGH | This is Prism's strongest differentiator. The 4-gate validation ensures high-quality knowledge, which compounds over time. |
| **Confidence lifecycle with decay** | No competitor implements confidence scoring with time-based decay. Claude Code memories persist indefinitely (manual cleanup). Windsurf memories have no decay. Copilot uses blunt 28-day expiration. Prism's Ebbinghaus-inspired decay (-0.02/week) with reinforcement on reoccurrence is more sophisticated than anything in production. | MEDIUM | Research confirms this aligns with cutting-edge work (agentmemory, MemRL, Fazm's memory triage). Prism is ahead of the market here. |
| **Team knowledge registry (skills)** | Claude Code has skills (`.claude/skills/`) but no shared registry mechanism -- skills are shared via git commit only. Copilot has organization-level instructions but no queryable skill registry. No competitor offers a multi-registry architecture where teams publish and query architectural knowledge across organizational boundaries. | HIGH | Lens's Cloudflare Worker + GitHub registry architecture is unique. Multi-registry with query-across is novel. |
| **Engram-to-skill promotion** | No competitor has a pipeline from "things I learned personally" to "things the team should know." Claude Code's auto-memory and skills are completely separate systems. `prism promote` bridges personal learning to team knowledge with quality gates (confidence >= 0.7, evidence >= 3). | MEDIUM | Natural workflow that no competitor addresses. Turns individual developer experience into organizational knowledge. |
| **Session transcript analysis** | `prism analyze-sessions` bootstraps knowledge from historical transcripts. Claude Code's auto-memory only works forward (captures during active sessions). No competitor offers retroactive knowledge extraction from past sessions. | MEDIUM | Good onboarding story: "install and immediately learn from your past 30 days of coding." |
| **Constitution-based safety** | Immutable safety principles that can never be overwritten by updates or extracted knowledge. No competitor has formalized safety guarantees for their memory systems beyond basic filtering. | LOW | Constitution.md is a simple file but the guarantee it provides (never overwritten) is meaningful for enterprise trust. |
| **Background session review** | Haiku scans completed session transcripts for corrections, preferences, and decisions missed during real-time capture. No competitor does post-session review. Claude Code auto-memory only captures what happens in real-time. | MEDIUM | Catches knowledge that real-time hooks miss -- corrections the user made verbally, implicit preferences, architectural decisions buried in conversation. |
| **Multi-registry architecture** | Read from multiple registries, write to specific ones. No competitor supports cross-team knowledge federation. Copilot has organization-level instructions (one org, one set). Claude Code skills are per-project or per-user, not cross-org. | HIGH | Enterprise value: team A publishes backend patterns, team B publishes frontend patterns, everyone queries both. |
| **12 analysis slash commands** | Structured codebase analysis pipelines (extraction, history mining, design extraction, skill synthesis, curation, publishing). Not ad-hoc prompting but formalized analysis workflows. | MEDIUM | These go beyond what any competitor offers for knowledge extraction. Competitors have generic slash commands, not domain-specific analysis pipelines. |
| **Publish tracking with delta detection** | `.published.json` tracks content hashes per-registry, so `publish-skills` only publishes what changed. No competitor handles incremental publishing of team knowledge. | LOW | Small feature, big UX impact. Prevents re-publishing unchanged skills. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Real-time sync between team members** | "I want my team to see my knowledge instantly" | Async publish-merge-refresh is more predictable than real-time sync. Real-time creates conflict resolution nightmares, requires persistent connections, and adds infrastructure complexity. Copilot scopes to repos; Claude Code is local-only. The market validates async. | Registry is async: publish PR, merge, cache refreshes on 24h TTL. Fast enough for architectural knowledge that changes slowly. |
| **GUI/web dashboard** | "I want a visual way to manage my knowledge" | CLI-native users (the target audience) prefer terminal workflows. A GUI creates a second codebase to maintain, doubles bug surface, and pulls focus from the core value. None of the core competitors (Claude Code, Windsurf, Cursor) ship dashboards for their memory systems. | `prism status` for overview, `prism learn/correct/forget` for management, slash commands for analysis. All in the terminal. |
| **Non-Claude Code editor support** | "I want this for Cursor/Windsurf/VS Code too" | Each editor has a fundamentally different hook system, context injection model, and extension architecture. Supporting multiple editors means lowest-common-denominator features. Claude Code's hooks API is uniquely well-suited for observation-based learning. | Focus on Claude Code. Let the registry layer (Worker API) be editor-agnostic for team knowledge consumption. |
| **Automatic knowledge import/export between users** | "I want to share my personal engrams directly with a colleague" | Personal knowledge is shaped by individual context that may not transfer. An engram about "always use pnpm" makes sense for one user but would conflict for another who uses yarn. Cross-user engram sharing creates trust and conflict resolution problems. | Knowledge flows through the registry: promote high-quality engrams to skills, publish to registry, colleagues discover via queries. |
| **Vector/embedding-based semantic search for engrams** | "Semantic search would find more relevant memories" | Adds a vector database dependency (breaks zero-dependency constraint), requires embedding model calls (cost, latency), and for the expected engram count (dozens to low hundreds per project), keyword/tag search is sufficient and instant. | MCP tools (`prism_search`, `prism_relevant`) use keyword matching and relevance scoring. Good enough for the scale. |
| **OAuth/SSO for registry access** | "Enterprise needs proper auth" | Token-based auth is simpler, works everywhere, and is sufficient for the current use case. OAuth adds an identity provider dependency, callback flows, and refresh token management. | Token-based auth with `prism registry token create/revoke`. Simple, auditable, works in CI. |
| **Full codebase indexing/RAG** | "Index my entire codebase for the AI to search" | Augment Code does this well and is purpose-built for it. Prism's value is in learned knowledge and team knowledge, not codebase search. Adding RAG means competing with well-funded tools on their core competency. Claude Code already has codebase access via its file tools. | Prism stores what the codebase search cannot provide: preferences, conventions, decisions, architectural rationale, team patterns. Complementary, not competing. |
| **Memory consolidation / "dreaming"** | "Claude Code has dreaming, shouldn't Prism?" | Claude Code's dreaming consolidates auto-memory files (MEMORY.md + topic files). Prism's engrams are already structured individually with metadata (confidence, evidence, timestamps). Consolidation is solving a problem Prism doesn't have because its storage format is already structured. | Engram lifecycle (decay, archive, promote) already manages knowledge quality. The `maintain` command handles cleanup. |

## Feature Dependencies

```
[Hook-based observation capture]
    └──requires──> [Secret scrubbing]
    └──feeds──> [Two-phase extraction pipeline]
                    └──produces──> [Engrams with confidence scoring]
                                       └──enables──> [Confidence lifecycle / decay]
                                       └──enables──> [Context injection (push + pull)]
                                       └──enables──> [Manual management (learn/correct/forget)]
                                       └──enables──> [Engram-to-skill promotion]
                                                          └──requires──> [Skill format (plugin.json + SKILL.md)]
                                                          └──feeds──> [Publish to registry]

[Session transcript analysis]
    └──feeds──> [Two-phase extraction pipeline]

[Background session review]
    └──feeds──> [Two-phase extraction pipeline]

[12 slash commands]
    └──requires──> [Codebase access / file tools]
    └──produces──> [Skills in standard format]
                       └──feeds──> [Publish to registry]

[Multi-registry management]
    └──requires──> [Registry template (Worker + GitHub)]
    └──enables──> [Publish tracking with delta]
    └──enables──> [Cross-registry queries (/advise-skills, /audit-code)]

[Installer (install.sh)]
    └──enables──> [All features]
    └──configures──> [Hooks, MCP server, slash commands]

[prism init]
    └──requires──> [Installer]
    └──configures──> [Project-level hooks, .claude/prism.md]
```

### Dependency Notes

- **Extraction pipeline requires observation capture:** Without hooks capturing tool usage, there's nothing to extract from.
- **Engram promotion requires both engrams and skill format:** The bridge between personal and team knowledge needs both systems working.
- **Registry features require the template:** Multi-registry, token management, and publishing all depend on the Cloudflare Worker being deployable.
- **Context injection requires engrams to exist:** Push (`.claude/prism.md`) and pull (MCP) are two delivery channels for the same knowledge store.
- **Slash commands are independent of engrams:** They analyze the codebase directly, not the engram store. They produce skills, which feed into the registry.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate the concept.

- [ ] **Installer + `prism init`** -- Without zero-friction setup, nobody adopts. Single command to go from zero to working.
- [ ] **Hook-based observation capture with secret scrubbing** -- The foundation. Non-blocking capture of tool usage to JSONL.
- [ ] **Two-phase extraction pipeline** -- The core value. Haiku proposes, Sonnet validates. This is what makes Prism's knowledge trustworthy.
- [ ] **Engram storage with confidence scoring** -- Structured knowledge with metadata. The data model everything else builds on.
- [ ] **Context injection (push: `.claude/prism.md`)** -- Users must see the value immediately: Claude Code reads their preferences next session.
- [ ] **Manual management (`prism learn/correct/forget`)** -- Users need control. Must be able to teach, fix, and remove knowledge.
- [ ] **`prism status`** -- Users need to see what the system knows. Visibility builds trust.
- [ ] **Constitution safety principles** -- Must ship from day one. Safety is not a later feature.

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **MCP server (pull injection)** -- Adds mid-session knowledge access. Requires core engram system stable first.
- [ ] **Confidence lifecycle (decay + reinforcement + archive)** -- `prism maintain` and background decay. Adds long-term knowledge quality.
- [ ] **Background session reviewer** -- Haiku scans transcripts for missed knowledge. Improves extraction coverage.
- [ ] **`prism analyze-sessions`** -- Bootstraps from history. Improves onboarding experience.
- [ ] **Global vs project-scoped engrams** -- Refine scoping model after seeing real usage patterns.

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Skill format + `prism promote`** -- Bridge to team tier. Defer until personal tier is validated.
- [ ] **12 slash commands** -- Carry from Lens. Complex analysis pipelines that need the personal tier stable first.
- [ ] **Registry template + `prism registry create`** -- Cloudflare Worker deployment. Defer until skill production is working.
- [ ] **Multi-registry management** -- `add/remove/list/default`. Defer until single-registry works.
- [ ] **Publish tracking with delta** -- Incremental publishing. Defer until publishing exists.
- [ ] **Cross-registry queries** -- `/advise-skills`, `/audit-code`. Final integration layer.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Installer + `prism init` | HIGH | MEDIUM | P1 |
| Hook-based observation capture | HIGH | LOW | P1 |
| Secret scrubbing | HIGH | LOW | P1 |
| Two-phase extraction pipeline | HIGH | HIGH | P1 |
| Engram storage + confidence | HIGH | MEDIUM | P1 |
| Push context injection (`.claude/prism.md`) | HIGH | LOW | P1 |
| Manual management (learn/correct/forget) | HIGH | LOW | P1 |
| `prism status` | MEDIUM | LOW | P1 |
| Constitution safety | HIGH | LOW | P1 |
| MCP server (pull injection) | MEDIUM | MEDIUM | P2 |
| Confidence lifecycle (decay/reinforce) | MEDIUM | LOW | P2 |
| Background session reviewer | MEDIUM | MEDIUM | P2 |
| `prism analyze-sessions` | MEDIUM | MEDIUM | P2 |
| Global vs project scope | MEDIUM | LOW | P2 |
| Skill format + `prism promote` | MEDIUM | MEDIUM | P2 |
| 12 slash commands | MEDIUM | HIGH | P3 |
| Registry template + deployment | MEDIUM | HIGH | P3 |
| Multi-registry management | LOW | MEDIUM | P3 |
| Publish tracking with delta | LOW | LOW | P3 |
| Cross-registry queries | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch -- core personal learning loop
- P2: Should have, add when personal tier validated -- enriches personal tier + bridges to team
- P3: Nice to have, future consideration -- team tier features

## Competitor Feature Analysis

| Feature | Claude Code (native) | Cursor | Windsurf | Copilot | Prism |
|---------|---------------------|--------|----------|---------|-------|
| **Cross-session memory** | Auto-memory (MEMORY.md + topics) | .mdc rules files (manual) + community memory banks | Auto-generated memories (workspace-scoped) | Agentic memory (per-repo, 28-day expiry) | Engrams with confidence lifecycle |
| **Automatic learning** | Writes MEMORY.md itself, single-pass | No native auto-learning; community memory bank add-ons exist | Cascade auto-generates memories during conversation | Auto-discovers conventions, validates against codebase | Two-phase extraction: Haiku proposes, Sonnet validates through 4 gates |
| **Manual instructions** | CLAUDE.md (project, user, org, managed policy) | .mdc files in .cursor/rules/ with YAML frontmatter + path scoping | .windsurfrules (global, workspace, system) | .github/copilot-instructions.md + org-level instructions | `prism learn/correct/forget` + `.claude/prism.md` |
| **Knowledge validation** | None -- model self-polices what to remember | None | None | Validates memories against current codebase before applying | 4-gate validation: constitution, evidence, contradiction, safety |
| **Knowledge decay** | None (manual cleanup, consolidation via "dreaming") | None | None | 28-day hard expiry | Ebbinghaus-inspired: -0.02/week, reinforcement on reuse, archive at 0.2 threshold |
| **Team knowledge sharing** | Skills via git commit (.claude/skills/) | Rules via git commit (.cursor/rules/) | Rules via git commit (.windsurfrules) | Org instructions + Copilot Spaces | Multi-registry: publish to Cloudflare Worker, query across registries |
| **Analysis pipelines** | Bundled skills (/debug, /simplify, /batch) | None native | None native | None native | 12 specialized slash commands for extraction, mining, synthesis |
| **Reusable workflows** | Skills system (SKILL.md with frontmatter, subagent support, supporting files) | Custom modes (community) | None native | .agent.md files (custom agents) | Slash commands + skill format from registry |
| **Path-scoped context** | .claude/rules/ with `paths` frontmatter | .mdc with `paths` frontmatter | Workspace-scoped only | Repository-scoped | Project-scoped engrams (path scoping not in v1) |
| **Secret scrubbing** | Not documented for auto-memory | Not documented | Not documented | Enterprise data handling | Regex scrubbing on all captured observations |
| **MCP integration** | Native MCP client (connects to servers) | MCP client support | MCP client support | MCP support via custom agents | MCP server (provides 4 tools to Claude Code) |
| **Context delivery** | Loaded into context at session start (200 lines / 25KB MEMORY.md limit) | Rules loaded at session start or on path match | Assembled via context pipeline (rules, memories, open files, retrieval) | Included in all chat interactions | Dual: push (.claude/prism.md at session start) + pull (MCP tools mid-session) |

### Key Competitive Insights

1. **Claude Code's native auto-memory is Prism's direct competitor** for the personal tier. Claude Code writes MEMORY.md itself without validation gates. Prism's advantage is quality (4-gate validation) and lifecycle (decay/reinforcement), not capability.

2. **No competitor has team knowledge federation.** Copilot has org-level instructions (one org, one set of rules). Claude Code skills share via git. Nobody has a queryable cross-team registry. This is Prism's blue ocean.

3. **Copilot's 28-day expiry is crude but directional.** The market recognizes that unlimited memory accumulation is a problem. Prism's confidence-based decay is a more sophisticated answer to the same need.

4. **Claude Code's skills system is maturing rapidly.** Skills have frontmatter, subagent execution, path scoping, supporting files, auto-invocation. Prism's skill format must be compatible or complementary, not competing.

5. **Every competitor is converging on "rules files in the repo."** .cursorrules, .windsurfrules, CLAUDE.md, copilot-instructions.md. Prism's `.claude/prism.md` fits this pattern. The differentiation is in how that file gets populated (automatically vs. manually).

## Sources

- [Claude Code Memory Documentation](https://code.claude.com/docs/en/memory) -- Official Anthropic docs on CLAUDE.md, auto-memory, dreaming, /memory command (HIGH confidence)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills) -- Official Anthropic docs on skills system, SKILL.md format, frontmatter, subagent execution (HIGH confidence)
- [Claude Code Hooks Documentation](https://code.claude.com/docs/en/hooks) -- Official Anthropic docs on hook lifecycle events (HIGH confidence)
- [Windsurf Cascade Memories](https://docs.windsurf.com/windsurf/cascade/memories) -- Official Windsurf docs on auto-generated memories and rules (MEDIUM confidence, could not fetch full page)
- [Cursor Rules Documentation](https://docs.cursor.com/context/rules) -- Official Cursor docs on .mdc rules system (MEDIUM confidence, could not fetch full page)
- [GitHub Copilot Memory Changelog](https://github.blog/changelog/2026-03-04-copilot-memory-now-on-by-default-for-pro-and-pro-users-in-public-preview/) -- Copilot agentic memory now default for Pro users (HIGH confidence)
- [GitHub Copilot Custom Instructions](https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot) -- Official GitHub docs (HIGH confidence)
- [Augment Code Context Engine](https://www.augmentcode.com/context-engine) -- Augment's codebase indexing and memory approach (MEDIUM confidence)
- [Roo Code Memory Bank](https://github.com/GreatScottyMac/roo-code-memory-bank) -- MCP-based memory bank for coding agents (MEDIUM confidence)
- [agentmemory](https://github.com/rohitg00/agentmemory) -- Persistent memory with Ebbinghaus decay for AI coding agents (MEDIUM confidence)
- [Fazm Memory Triage](https://fazm.ai/blog/ai-agent-memory-triage-retention-decay) -- Why 100% retention is a bug (MEDIUM confidence)
- [Martin Fowler - Encoding Team Standards](https://martinfowler.com/articles/reduce-friction-ai/encoding-team-standards.html) -- Making tacit team knowledge explicit for AI (HIGH confidence)
- [Stack Overflow - Building Shared Coding Guidelines for AI](https://stackoverflow.blog/2026/03/26/coding-guidelines-for-ai-agents-and-people-too/) -- Team conventions for AI agents (MEDIUM confidence)

---
*Feature research for: Knowledge layers / memory systems for AI coding assistants*
*Researched: 2026-04-14*
