# Shared: Stripping Rules

Apply before writing any skill file output.

- Remove all internal product names, class names, table names, endpoint names, domain entities
- Replace with generics: "cache layer", "session state", "agent node", "job queue", "task runner", "record", "direct call path"
- Keep: technology names (Redis, Postgres, Celery, FastAPI, LangGraph, OpenAI), general patterns, observable symptoms, fix mechanics
- Use month+year for dates, never full commit hashes
