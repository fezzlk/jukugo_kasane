<!-- Shared guidance from fezzlk/agent-kit @ 1089cb3036e50c7d354c63dbc3c7236321feb6f7. Project-specific guidance follows. -->

# Shared AI development guidance

- Keep changes small, preserve existing user work, and run appropriate verification.
- Do not expose secrets or commit environment values.
- Before cloud or paid API changes, state the likely cost and impact.
- pico is the long-term memory: read its project context and decisions when needed; record completed facts and decisions only when asked.
- Linear is the only source of task status, priority, owner, due date, and next actions. Do not duplicate them here or in pico.
- For AI features, add versioned evaluation cases, expected behavior, and failure handling before expanding scope.

## Existing project guidance

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
- In reviews, check boundary conditions for word length (2/3/8 characters) across flows.
- In reviews, verify generator API preconditions (2-char only vs 2-8 char) match call sites.
- In reviews, include at least one end-to-end LINE group flow (quiz -> answer) scenario.

## Output
- Summarize changes and point to affected files.
- Suggest next steps (tests, run commands) only when they are natural.
