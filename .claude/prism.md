# Learned Knowledge (Prism)
<!-- Updated: 2026-04-21T07:59:05Z | 8 pushed, 0 via MCP -->

## Corrections -- do NOT repeat these

- Use npm instead of pnpm

## Key Preferences

- Recorded via MCP during coding session. (0.90 [procedure])
- Infrastructure nodes (gazebo, robot_state_publisher, turtlebot3_diff_drive) should never be classified as tactical roles (Task Executor, Task Requester, HW Requestor, Sensor Requestor). These nodes are structural/simulation infrastructure, not mission-level entities that make energy decisions. The candidate function heuristics must filter them out explicitly, even when they match pattern signatures (e.g., publishing sensor messages or advertising services). (0.75 [domain_fact])
- The rospec_questions_generator.py was producing systematic false-positive role assignments for infrastructure nodes (gazebo, robot_state_publisher, turtlebot3_diff_drive) across multiple tactical role categories. Root causes included: (1) overly broad service name pattern matching (mode substring colliding with model), (2) candidate functions not explicitly excluding infrastructure nodes, and (3) insufficient structural checks to distinguish mission-level nodes from infrastructure. Fixed through: refined pattern matching, explicit is_sensor_publisher checks, and adding node-name filters for known infrastructure nodes. (0.72 [solution])
- When reading large files that exceed token limits, systematically use the Read tool's offset and limit parameters to read the file in chunks rather than attempting to read the entire file at once. (0.70 [tool_pattern])
- The 'mode' substring in PARAM_SVC_PATTERNS causes false positives on services like `/get_model_list`, which contain 'mode' but are not mode-management services. Remove 'mode' and use more specific patterns like 'set_mode' and 'get_mode' to avoid substring collision with 'model'. (0.70 [solution])
- EE1 Task Requester and EE2 HW Requestor candidate functions must check `not is_sensor_publisher(name)` to distinguish mission-level request nodes from infrastructure or sensor processing nodes. A node that publishes any topic is not automatically a task requester; only non-sensor publishers (command/mission-level topics) are candidates. The is_sensor_publisher helper filters by message type (sensor_msgs/*) and patterns indicating sensor data (battery, status readings). (0.70 [domain_fact])
- Use the Glob tool instead of Bash shell commands (`ls`, `find`) when discovering files matching a pattern. This pattern shows a clear evolution from Bash-based discovery to the dedicated Glob tool across sessions. (0.63 [tool_pattern])

## Publish-Ready

- use-read-offset-limit-for-large-files (0.70, 8 evidence) -- `prism promote use-read-offset-limit-for-large-files`

---
Full knowledge base available via prism MCP tools.

**Search** (`prism_search`): when encountering errors, starting tasks, or making design decisions.

**Record** (`prism_record`): proactively record knowledge when you discover it:
- Design decisions with rationale ("chose X because Y")
- Project conventions and coding standards
- Domain facts (API limits, service ownership, deployment rules)
- Non-obvious error resolutions that required trial-and-error
- User corrections or preference signals ("actually, use X instead")

**When to record** (evaluate after completing non-trivial tasks):
- Did you try an approach that failed before finding what works?
- Did the user correct you or express a preference?
- Was the solution non-obvious or project-specific?
- Would this knowledge help in a future session?

Don't record one-off task instructions, exploratory discussion, or obvious patterns.
