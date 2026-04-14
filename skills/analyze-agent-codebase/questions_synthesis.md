## SECTION 14: DECISION EXTRACTION AND CLASSIFICATION

This section is the bridge between codebase analysis (Sections 1–15) and skill extraction. Extract every non-obvious decision from the preceding sections. "Non-obvious" means: a competent developer building a similar system would not arrive at this decision without experience or research. Generic best practices ("use environment variables," "add retry logic," "validate input") are not decisions — skip them.

### 14A — Decision extraction

Read every preceding section. For each design decision, trade-off, or non-obvious behavior, write one row. Each decision must be:
- **Self-contained**: understandable without reading the source section
- **Atomic**: one decision per row, not a summary of a section
- **Actionable**: specific enough that a developer could implement it

| # | Decision (2-3 sentences: what was decided, what goes wrong otherwise) | Classification | Section ref |

**Classification tags:**
- **UNIVERSAL**: How LLMs fundamentally work — context window behavior, message sequence interpretation, tool calling semantics, token economics, prompt construction
- **ENGINEERING**: General software engineering pattern applied in an agent context — caching, persistence, error isolation, resilience, security
- **FRAMEWORK-SPECIFIC**: Tied to a specific framework's API, data structure, or behavior — a reducer type, a callback interface, a specific SDK method

Default to UNIVERSAL when unsure.

### 14B — Anti-patterns

For each finding where something is missing, disabled, or broken — and the absence causes a production-visible failure:

| # | What's wrong (one sentence) | What goes wrong in production (one sentence) | What the correct approach looks like (one sentence) | Section ref |
|---|---|---|---|---|

Include only anti-patterns where:
- The failure takes more than an hour to diagnose
- The fix involves an architectural decision, not a config change

### 14C — Design trade-offs

For each significant architectural choice where two valid approaches exist and the choice depends on context:

| Decision point | Choose option A when... | Choose option B when... | This codebase chose | Observed consequence |
|---|---|---|---|---|

Include only trade-offs where choosing wrong has structural consequences (not just performance tuning).
