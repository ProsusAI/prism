## SECTION 3: CONTROL FLOW AND PLANNING

Find all planning logic, branching conditions, and execution orchestration code.

Answer:

**Planning:**
- How is branching implemented (e.g. conditional edges, switch on state, agent return value)?
- Is execution sequential only, or are there parallel/concurrent agent or tool runs?
- What triggers replanning or re-routing mid-execution?

**Prompt chaining:**
- Are there explicit multi-step chains where one LLM call produces output that is transformed and passed to the next?
- What are the gates or checkpoints between chain steps? (validation, format checking, conditional branching)
- How is intermediate output transformed between steps? (string formatting, structured extraction, summarization)
- Is the chain structure static or dynamic? Can it short-circuit early based on intermediate results or vary per request?

---

## SECTION 4: STATE MANAGEMENT

Find and read the State TypedDict or equivalent, all reducers, and the state save/load functions.

Answer:
- What design choices does the State structure reflect? (which fields use reducers vs plain fields, how conversation/session/client data are separated, any annotations that affect merge/serialization behavior)
- How is each field updated when new information arrives? (append-only, overwrite, custom merge logic, reducer functions) Cite the update logic per field.
- Where is state persisted between turns or sessions? (in-memory only, Redis, SQL database, file system, framework checkpoint) Cite the persistence code.
- What is the TTL and key structure for stored state? (session ID, user ID, thread ID as key) Cite the key construction code or state: No implementation.
- Are there multiple state scopes? (per-turn vs per-session vs per-user vs global) Cite the scope boundaries.
- Are there concurrency risks in state reads and writes? (concurrent sessions sharing state, no locking, optimistic concurrency control) Cite the concurrency mechanism or state: No implementation.

---

## SECTION 5: MEMORY MANAGEMENT

Find all memory-related code: long-term stores, profiles, user preferences, context window management, history.
Common locations: files containing "memory", "store", "history", "profile", "context".

Answer:

**Memory types — for each, state whether implemented:**
- Semantic memory (facts, domain knowledge, user preferences)
- Episodic memory (past successful interactions, few-shot examples learned from history)
- Procedural memory (task instructions/rules — are these updated dynamically? Describe the update loop.)

**Short-term memory (context window):**
- What is kept in the context window? (recent messages, tool results, agent reflections)
- Is there a hard cap on message history? How is it enforced and how are messages truncated when exceeded? Is ordering preserved? Are tool calls and system prompts handled differently from regular messages?
- Is user input truncated before being added to state? How?
- Is there LLM-based summarization of history? When is it triggered?

**Long-term memory (persistent):**
- What types of memory exist: in-context (messages), in-store (vector/KV), external (Redis/DB)?
- For each memory type: what is stored, how is it retrieved, what is the TTL, what is the key structure?
- Is memory cross-session or single-session?
- Is memory shared across agents or isolated per agent?

**Memory injection:**
- How is long-term memory injected into the prompt?
- Is there a user profile or preference store? How is it built and updated?
- Is profile summarization implemented? Is it active or disabled?
- Can memory be disabled per request? Why would that be done?
