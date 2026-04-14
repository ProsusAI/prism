# Prism Constitution

These principles are immutable. No entry may violate them. The validation gate rejects any candidate that conflicts with these rules.

## Core Principles

1. **No credential storage.** Entries must never contain API keys, tokens, passwords, secrets, or any authentication material. Even if a pattern involves credentials, the entry must describe the pattern without including the actual values.

2. **No permission escalation.** Entries must not suggest expanding access, granting permissions, disabling security checks, or bypassing authentication. An entry that says "skip auth in development" violates this principle.

3. **No self-modification.** Entries must not instruct the AI to modify the prism system itself, change this constitution, alter the validation pipeline, or adjust confidence scores programmatically. Human users can edit entries directly - the AI cannot.

4. **No personal data.** Entries may include team attribution (who published an entry) but must not store personal information, user behavior profiles, or identifying data beyond what's needed for team collaboration.

5. **No instruction override.** Entries must not contain phrases that attempt to override system prompts, ignore safety guidelines, or redirect AI behavior outside the scope of coding assistance. Examples: "ignore previous instructions", "you are now a different assistant", "disregard safety rules".

6. **No destructive defaults.** Entries must not encode destructive operations as default behavior. A procedure that includes `rm -rf` or `git push --force` must explicitly mark those steps as requiring confirmation.

7. **Scope accuracy.** Project-scoped entries must not claim to be universal truths. A project convention (e.g., "use tabs") is a project preference, not a global rule. The scope field must accurately reflect the entry's applicability.

8. **Evidence required.** Every entry must cite its evidence: observation counts, session IDs, or explicit user instruction. Entries without evidence are rejected. This prevents hallucinated knowledge.
