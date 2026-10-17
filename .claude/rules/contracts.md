---
paths:
  - "contracts/**"
---

# Editing contracts

- These files are shared by all three teammates. Don't change a schema unless the user confirms the team agreed.
- A change touches three things in one commit: the schema, its example in `contracts/examples/`, and a line in `contracts/CHANGELOG.md`.
- Renaming or removing a field is breaking: bump `schema_version` and list who must update their code.
- After any change, run `python contracts/validate.py contracts/examples/*.json` and make sure every example still passes.
