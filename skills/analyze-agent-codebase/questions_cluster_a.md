## SECTION 0: AGENT METADATA

### Project Identity
| **Attribute** | **Answer** | **Source (file:line)** |
|:-:|:-:|:-:|
| Project name | | |
| Stated purpose | Quote the package description or README opening verbatim | |
| Use case domain | e.g. customer service, coding assistant, research, data analysis, DevOps | |
| Is the system described as an "agent" in its own documentation? | Quote the relevant line, or state: No | |

### Authorship and Provenance
| **Attribute** | **Answer** | **Source** |
|:-:|:-:|:-:|
| Author(s) or organization | | pyproject.toml / package.json / git log |
| License | | LICENSE file |
| Repository creation date | | git log — first commit |
| Last commit date | | git log — most recent commit |
| Version | | pyproject.toml / package.json |


## SECTION 1: SDK, LLM STACK AND MODEL CONFIGURATION

Find and read every file related to model configuration and LLM invocation.
Common locations: pyproject.toml, requirements.txt, package.json for dependencies; files containing "llm", "model", "client", "openai", "anthropic" in name or imports.

Answer:
- Which LLM(s) are used? For each: role/agent it serves, model name, provider SDK, temperature, max_tokens, top_p, timeout, any custom parameters.
- Are models hardcoded or dynamically selected? What drives selection (task type, cost, latency, A/B testing, feature flags)?
- Is there model routing by task complexity? (e.g., simple classification to a small model, complex reasoning to a large model) What is the routing logic?
- Is there a fallback model? Under what conditions is it triggered? What is the fallback chain?
- What is the exact tool binding configuration (strict mode, parallel_tool_calls)?
- Is there token usage tracking per request or per session? How is it measured and where is it stored? Is there a token budget or cost ceiling per request — what happens when it is exceeded? (truncate, switch to cheaper model, abort)

---

## SECTION 2A: AGENT ARCHITECTURE — INVENTORY

Prerequisite: complete Section 3A first. Use the generic terms defined there.

Find and read the orchestration definition, all execution unit implementations, all control flow logic, and all LLM instantiation code.

**1A — Execution units:** For every execution unit in the system:
| **Name** | **Has tool selection discretion?** | **Can loop?** | **What it does (one sentence)** |
|:-:|:-:|:-:|:-:|
|  | Yes (N tools) / No (forced single tool) / N/A (no LLM) | Yes / No |  |

**1B — Control flow logic:** For each piece of control flow logic:
| **Name / location** | **Mechanism** | **What it checks** | **Where it routes to** |
|:-:|:-:|:-:|:-:|
|  | Rule-based / LLM classification / Tool selection / Event-driven |  |  |

**1C — Tools:** For each tool registered in the system:
| **Tool name** | **Bound to which execution unit(s)** | **Required or optional** | **Description** |
|:-:|:-:|:-:|:-:|
|  |  | Required (forced) / Optional (unit chooses) |  |

---

## SECTION 2B: AGENT ARCHITECTURE — CLASSIFICATION

Prerequisite: complete Section 3B first. Apply the criteria below to the inventory produced there.

**2A — Execution unit classification:** Apply these criteria to each unit from Section 3B:
- **Agent**: Makes LLM calls, AND has tool selection discretion (can choose among multiple tools or none), AND can loop (output can route back to itself for further reasoning).
- **Constrained LLM step**: Makes LLM calls but fails one or both conditions above. State which condition(s) it fails and why an LLM is needed here at all (vs. deterministic code).
- **Deterministic processing unit**: Makes no LLM calls. A chain of these is a data pipeline, not an agent pattern.
- **Control flow logic**: Directs execution between units based on state inspection. If rule-based, it is not an agent pattern. If it involves an LLM call to classify intent, note whether it qualifies as a constrained LLM step.

**2B — System-level classification:**
| **Level** | **Criteria** | **Applies?** |
|:-:|:-:|:-:|
| Direct model call | Zero agents. No tool access, no loop. Just LLM call(s) with a prompt. |  |
| Single agent with tools | Exactly one agent. Other execution units may exist but are constrained LLM steps, deterministic processing, or control flow. |  |
| Multi-agent orchestration | Two or more agents (each meeting all three criteria: LLM calls, tool discretion, looping). |  |

**2C — Multi-agent patterns** *(complete only if two or more agents are confirmed in 2B):*
| **Pattern** | **Key indicator** | **Present?** | **Evidence** |
|:-:|:-:|:-:|:-:|
| Sequential / Pipeline | Two or more **agents** execute in fixed order, each doing LLM-based reasoning. |  |  |
| Concurrent / Parallel | Two or more **agents** execute in parallel on the same input. |  |  |
| Supervisor / Subagents | An **agent** delegates to other **agents**; supervisor has discretion in delegation. |  |  |
| Handoff / Transfer | An **agent** transfers control to another **agent** via explicit handoff mechanism. |  |  |
| Router / Dispatch | An **LLM-based** classification dispatches to different **agents**. Rule-based routing does not qualify. |  |  |
| Group chat / Roundtable | Multiple **agents** share a conversation thread and take turns. |  |  |
| None of the above | Doesn't fit any category above. |  |  |

**2D — Identity cards**

For each **agent** (not constrained LLM steps or deterministic units):
| **Attribute** | **Value** |
|:-:|:-:|
| Name / ID |  |
| Description |  |
| Capabilities (tools available with discretion) |  |
| Model and parameters |  |
| System prompt (summarize role and constraints) |  |
| Registration (how it is wired into the orchestration layer) |  |

For each **constrained LLM step**:
| **Name** | **Purpose** | **What it's forced/constrained to do** | **Why an LLM is needed here (vs deterministic code)** |
|:-:|:-:|:-:|:-:|
|  |  |  |  |

---

## SECTION 2C: AGENT ARCHITECTURE — COMMUNICATION, ROUTING, AND PROMPTS

Prerequisite: complete Section 3C first. Describe everything in terms that match the actual architecture established there. If this is a single-agent system, do not describe deterministic control flow as "inter-agent communication."

**Communication and state:**
- How are errors handled? (fallback models, retries, error routing)
- Is there any formal inter-agent protocol (A2A, message bus, agent registry, capability advertisement)? If no: state "No formal inter-agent protocol — all coordination is via [describe actual mechanism]."

**Routing:**
- How is routing implemented? (LLM-based classification, rule-based, keyword matching, embedding similarity)
- What are the routing targets? List each route with its trigger condition and destination.
- What happens when the router is uncertain? Is there a default/fallback route?
- Can routing decisions be overridden by the user or by configuration?

**System prompts:**
- What is the system prompt structure per agent? (role definition, task framing, constraints, output format instructions, few-shot examples)
- How are system prompts stored and templated? (hardcoded strings, template files, external config, prompt registry) Are they versioned and can the system roll back to a previous version?

## SECTION 2D: AGENT ARCHITECTURE — MCP
- Is MCP used to connect the LLM to external resources?
- What is the client-server setup? (MCP client, MCP server, third-party services connected)
- Is there evidence that MCP was chosen over direct API integration — or vice versa — and why?
