## SECTION 11: ERROR HANDLING AND RESILIENCE

Find all retry logic, circuit breakers, timeout configurations, and error hierarchies.

Answer:
- What is the retry strategy for external services? 
- Is there a circuit breaker pattern? Where is it applied and what trips it? (error count, error rate, latency threshold)
- What is the error taxonomy? List the main error categories and how they are classified.
- Is there a fallback agent or fallback tool when the primary path fails?
- Are any failures silently swallowed? If so, where and why?
- What is the idempotency strategy? Where is it applied? (LLM calls, tool calls, state writes)
- Recovery strategies — when an error occurs mid-execution, does the agent: retry the failed step, skip and continue, roll back to a checkpoint, replan from current state, or escalate to a human?
- How is partial progress preserved after a failure? (checkpointing, intermediate state saves)
- Is there a dead letter queue or error log for unrecoverable failures?

---

## SECTION 12: EVALUATION AND TESTING

Find the test directory structure, evaluation harnesses, fixtures, and test patterns.

Answer:
- What test types exist? (unit, integration, smoke, end-to-end)
- How are external dependencies mocked? What is real vs mocked?
- How is test data organized (e.g. fixtures, factories, real vs mocked)?
- How are LLM calls handled in tests?
- Are there any tests specific to the agent flow (graph execution tests)?
- How is agent response quality assessed? (LLM-as-judge, deterministic assertions, human review)
- If LLM-as-judge is used: how is the judge configured (e.g. model size, rubric or criteria)?

---

## SECTION 13: DEPLOYMENT AND SCALING

Find deployment manifests, infrastructure config, and scaling configuration.

Answer:
- What is the deployment strategy? (rolling, blue-green, canary)
- Are there autoscaling configurations? What metrics trigger scaling?
- How is the application containerized?

