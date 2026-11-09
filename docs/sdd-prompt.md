# SDD master prompt (copy–paste to start any change)

Replace the `<…>` parts. Keep this file in git so the whole team starts the same way.

```
You are working in the Jira MCP Server repo. Follow CLAUDE.md and the SDD loop strictly.
First read docs/sdd/spec.md, tools-contract.yaml, plan.md, tasks.md, traceability.md.

CHANGE REQUEST: <one paragraph: what and why>
RELATED REQUIREMENTS / TASKS: <FR-xx, T-Bx or "new">

Run these phases. STOP at the end of each and wait for me to reply "proceed".

PHASE 1 — SPECIFY: Propose exact edits to spec.md (new/changed FR/NFR/SEC ids with MUST/SHOULD wording)
  and tools-contract.yaml (names, params, result shape). List open questions. Do not write code.
PHASE 2 — PLAN: Files to change, layering impact, risks (security, logging, backward compatibility), ADR if needed.
PHASE 3 — TASKS: Ordered checklist for tasks.md, each task tied to an FR id and a test.
PHASE 4 — IMPLEMENT: One task at a time. Tests first or alongside. No print(), no default project, no secrets.
PHASE 5 — VERIFY: Run ruff + pytest --cov. Update traceability.md and REPORT.md. Report any spec/code drift honestly,
  including failing gates. Summarise as a Conventional-Commit list referencing FR ids.
```

## Quick variants
- **Add a tool:** "CHANGE REQUEST: add `jira-<name>` that … Mirror `jira-transitionIssue` (FR-32): validate first, idempotent if possible, ToolError on bad input."
- **Fix a gap:** "Close T-B3 (SEC-1). Start from Phase 2 since the spec already exists."
- **Audit only:** "Phases 1–2 only: re-verify spec.md against current code and list drift."
