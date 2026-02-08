# AGENTS.md

This repository uses AGENTS instructions to guide Codex-style agents.
Place concise, stable rules here so agents can read them implicitly before
working on the codebase.

## Purpose
- Provide repo-specific behavior rules.
- Keep instructions short and actionable.
- Avoid duplicating user/system instructions.

## Repo rules
- Prefer `rg` for searches.
- Use `apply_patch` for single-file edits when practical.
- Keep changes minimal and focused.
- Do not introduce non-ASCII characters unless the file already uses them.
- Do not add external libraries.
- Preserve the basic structure.
- If anything is unclear, ask questions only and do not implement.
- In reviews, verify user-facing help/usage text covers implemented settings and behavior.
- In reviews, include user-facing messages (help/usage, error messages, settings guidance) in scope.
- When reviewing specs, do both spec-to-implementation and implementation-to-spec/help cross-checks.

## Output
- Summarize changes and point to affected files.
- Suggest next steps (tests, run commands) only when they are natural.
