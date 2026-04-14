## SECTION 6: TOOLS AND TOOL CALLING

Find and read all tool definitions, the tool registry, and tool binding code.
Common locations: files containing "tool", "function", "schema" in name; decorator patterns like @tool, @function_tool.

Answer:

**Tool binding and scoping:**
- Are tools shared across agents or scoped to specific agents?
- Are tools bound statically or dynamically? Can the tool set vary per request or per user?
- Is there a force-required tool that is always included regardless of filters?
- Are parallel tool calls enabled or disabled?

**Tool execution:**
- What happens after a tool executes? Is there a special post-tool router?
- Is there a direct-execution path that bypasses the LLM for tool calls?
- What is the retry logic for failed tool calls?

---

## SECTION 7: RAG AND RETRIEVAL

Find all search, retrieval, embedding, and vector database code.

Answer:
- Is RAG implemented? Is it standard RAG or Agentic RAG? (Does the agent reason about retrieved chunk quality, call tools, or iterate on retrieval?)
- What are the retrieval sources?
- What is the chunking strategy? (size, overlap, method — how documents are split matters for preserving context)
- What embedding model is used?
- What vector database is used?
- What retrieval method is used? (vector search, hybrid BM25 + vector, other)
- Is there an LLM reranking step after retrieval? If so, what is the prompt and model used?
- How is retrieval integrated into the agent: as a tool, as a pipeline stage, or inline?
- Is retrieval cached? What is the cache key and TTL?
- Are there multiple retrieval strategies? How is the right one selected (deterministic rules, ML classifier)?
- What happens when retrieval returns no results or results below a relevance threshold? (proceeds without retrieved context, returns an error, tries a fallback strategy).
