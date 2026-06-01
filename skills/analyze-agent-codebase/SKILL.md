---
name: analyze-agent-codebase
description: Run a deep architectural analysis of an agentic AI codebase using a phased approach — index, parallel clustered analysis, and synthesis.
---

## Analyze Agent Codebase Skill

## When to use this skill

Use this skill when the user wants to perform a comprehensive architectural analysis of an agentic AI codebase. 

## Instructions

Analyze the target codebase in four phases. 

Each cluster has its own questions file in the skill directory (e.g. `questions_cluster_a.md`).

### Global Token Rules
- Do NOT launch parallel subagents.
- Run clusters sequentially.
- Do NOT read the entire repository per cluster.
- Read ONLY the assigned cluster questions file.
- Read ONLY files relevant to the cluster questions.

### Global Output Rules
- Iventories: always use tables (tools, models, entities, tests)
- Findings with evidence: always use bullet points in format `- [finding] — evidence: path/to/file.ext:Lxx` 
- Comparisons or yes/no pattern checks: always use a table with columns: Pattern | Implemented | Evidence
- Evidence format: `path/to/file.ext:Lxx-Lyy`
- NO prose or narrative explanations (except Section 14: Decision Extraction and Classification).
- NO restating questions.
- NO long evidence excerpts.
- Do NOT duplicate findings across sections.
- Write each cluster file immediately after completion.

### Per-section Output Format:
- Provide Finding: what is implemented in the codebase.
- Provide Evidence: exact file path and line number (file.py:Lxx) with a direct code quote.
- If nothing is implemented, write exactly: No implementation.
- If partially implemented, write: Partial — [what exists] / [what's missing].
- Separate implemented-and-active, implemented-but-disabled, and not-implemented items.
- Do not speculate. Only use code-level evidence.

Output all results to `{CODEBASE_ROOT}/_analysis/` directory inside the target codebase root.

### Phase 1: Index

Build a structural map of the codebase. This must complete before Phase 2.

1. List the full directory tree (exclude node_modules, .git, __pycache__, .venv, venv, dist, build, .next).
2. Read anchor files if they exist:
   - Dependency manifests: pyproject.toml, requirements.txt, setup.py, package.json, go.mod, Cargo.toml
   - Entry points: main.py, app.py, index.ts, server.py, or files referenced in manifest scripts/entry_points
   - Configuration: config.py, settings.py, docker-compose.yml, Dockerfile (must not read `.env`)
   - CI/CD: .github/workflows/*, Jenkinsfile, .github/workflows
3. Extract: orchestration framework and version, LLM provider SDKs, and key infrastructure dependencies.
4. Identify locations of: agent/graph definitions, tool definitions, state/memory definitions, tests, and deployment config live.
5. Write `{CODEBASE_ROOT}/_analysis/index.md`. No analysis. Mapping only.
   Structure:
      ### Project Metadata 
      - Project name
      - Stated purpose: Quote the package description or README opening verbatim 
      - Use case domain: e.g. customer service, coding assistant, research, data analysis, DevOps 
      - Project type: Product / internal tool / demo / research prototype 
      - Author(s) or organization 

      ### Framework
      - Name:
      - Version:
      - Provider SDKs:

      ### Directory Map
      Top-level directory table:

      | Directory | Purpose |

      ### Key File Registry

      | Category | File Path | Purpose |

### Phase 2: Clustered Analysis
Run clusters one at a time.  
Write file before proceeding to next. 

**Cluster assignments:**

| Cluster | Questions file | Output file (written by main agent) |
|---|---|---|
| A: Core Architecture | questions_cluster_a.md | cluster_a_core_architecture.md |
| B: Execution, State, Memory | questions_cluster_b.md | cluster_b_execution_state_memory.md |
| C: Tools and Retrieval | questions_cluster_c.md | cluster_c_tools_retrieval.md |
| D: Data and Adaptation | questions_cluster_d.md | cluster_d_data_adaptation.md |
| E: Safety and Security | questions_cluster_e.md | cluster_e_safety_security.md |
| F: Ops | questions_cluster_f.md | cluster_f_ops.md |

**Cluster Prompt Template:**

Use this template for each cluster:

> Read `{CODEBASE_ROOT}/_analysis/index.md`.
> Read `{CLUSTER_QUESTIONS_FILE}`.
> Identify relevant files using index.
> Read only relevant files.
> Produce structured findings only.

After each cluster completes, write output to: `{CODEBASE_ROOT}/_analysis/{OUTPUT_FILE}`. Then proceed to the next cluster.

### Phase 3: Synthesis

After all cluster files are written:

1. Read:
   - `{CODEBASE_ROOT}/_analysis/index.md`
   - All cluster output files
2. Read `questions_synthesis.md`.
4. Do not repeat findings from cluster files — reference them by section number.
5. Write output to `{CODEBASE_ROOT}/_analysis/synthesis.md`

### Phase 4: Assemble

Combine all output files into a single report at `{CODEBASE_ROOT}/_analysis/full_report.md`.

Concatenate in this order, with no modifications to content:
1. cluster_a_core_architecture.md
2. cluster_b_execution_state_memory.md
3. cluster_c_tools_retrieval.md
4. cluster_d_data_adaptation.md
5. cluster_e_safety_security.md
6. cluster_f_ops.md
7. synthesis.md

Prepend this header:

```
# Agent Codebase Analysis Report
**Codebase**: {CODEBASE_ROOT}
**Date**: {DATE}
```

### Error handling

- If a cluster fails or times out, re-run only that cluster.
- If the index file is missing when a cluster starts, fail immediately.
- If output limit reached:
  - Stop at last fully completed section.
  - Append a note listing incomplete sections from the cluster questions file.


