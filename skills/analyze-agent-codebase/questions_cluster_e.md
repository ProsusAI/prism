## SECTION 9: GUARDRAILS AND AI SAFETY

Find all safety, content filtering, and behavioral constraint code. Focus on AI-specific safety — how the system controls what the LLM generates and does. General application security (auth, injection prevention, rate limiting) is covered in Section 12.

Answer:

For each guardrail type, state whether it is implemented, where in the agent flow it is applied, and cite the implementing code.

| **Guardrail type** | **Applied at** | **Implemented?** | **Evidence (file:line)** |
|:-:|:-:|:-:|:-:|
| Prompt injection detection | Input | | |
| Input content filtering (harmful, toxic, or policy-violating content) | Input | | |
| Output toxicity / bias filtering | Output | | |
| PII scrubbing from outputs | Output | | |
| Behavioral constraints via system prompt (explicit rules or refusals) | All turns | | |
| Tool use restrictions (blocked actions or tool categories) | Mid-task | | |
| External moderation API | Input / Output | | |
| Hallucination or grounding check | Output | | |
| Scope containment (domain or topic restriction) | Input | | |
| Model fallback on safety trigger | Mid-task / Output | | |

If zero guardrails are present: state No implementation and stop.

Additional questions — answer only for the guardrail types listed:

**External moderation API:** Which service? (Bedrock Guardrails, Azure Content Safety, OpenAI moderation, custom) Is it called synchronously (blocking the response) or asynchronously? Is there caching to avoid redundant calls?

**Hallucination / grounding check:** What is the mechanism? (citation verification against retrieved chunks, confidence threshold, LLM self-check prompt, retrieval grounding score) Is it applied to all outputs or triggered conditionally?

**Model fallback on safety trigger:** Which model or path does the fallback route to? Is the original request retried on the fallback, or is a canned response returned?

**Output filtering (post-generation only):**
*Definition:* A step that runs **after** the LLM has produced a response, taking that response as input and either blocking it, modifying it, or passing it through.
- Is there any code path that runs on the model's response string (e.g., toxicity check, bias detection, PII scrubbing)? What is the filtering logic?
- Is there an external moderation API (Bedrock Guardrails, Azure Content Safety, OpenAI moderation) called on the model output? When is it triggered? Is it on by default?
If the only control on final user-facing text is via prompts (e.g., a revision node with guardrail instructions in its prompt), answer "No" here and report those under Behavioral constraints.

**Behavioral constraints:**
- What constraints are baked into system prompts? (e.g., topic restrictions, tone requirements, refusal instructions, "do not change factual content" / style-only revision rules)
- Are agents explicitly blocked from using certain tools or performing certain actions?

**Human-in-the-loop:**
- When is human oversight triggered? What specific actions require human approval before proceeding?
- Is there an escalation path when the agent is uncertain or when guardrails fire?
- Can a human override or correct the agent's plan mid-execution? How is the correction integrated?
- What is the UX for human review? (chat interface, approval dashboard, email notification)
- Is there a timeout for human response? What happens if the human does not respond?

---

## SECTION 10: AUTHENTICATION, AUTHORIZATION, AND SECURITY

Find all middleware, auth checks, input validation, and security-related code.
Common locations: middleware directories, auth modules, request validators, decorators like @authenticate or @require_role, security config files.

Answer:

**Input validation and injection prevention:**
- Is there input validation for injection attacks? (SQL injection, prompt injection, XSS)
- How is input validated at the API boundary (e.g. schema validation, sanitization)?
- Is there prompt injection detection or sanitization before user input reaches the LLM?

**Data protection:**
- What PII is sanitized in logs? What is the sanitization logic?
- Are error details sanitized before being returned to callers? (e.g., stack traces, internal paths, model names)

**Rate limiting:**
- Is rate limiting implemented at the API level? At the tool level? At the LLM call level?
