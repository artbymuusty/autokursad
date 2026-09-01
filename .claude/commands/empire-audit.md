---
description: Run a broad Agentic Empire audit of a subsystem
argument-hint: <subsystem or question>
---
Run `.ai/bin/empire run "AUDIT: $ARGUMENTS"`.

The classifier will select the `audit` tier, which engages the full specialist
set. This is expensive in backend quota — Codex runs on ChatGPT Go and Gemini on
the free tier — so confirm with the user before running it a second time in one
session.

Report the findings by severity, and separate verified findings from inferred
ones.
