# Jira MCP Server — context and standing orders

Loaded automatically every session. Read `spec.md` first; this file records the
rules of engagement and the decisions that are not obvious from the code.

## The artifacts

| File | Owner | Purpose |
|---|---|---|
| `spec.md` | Human | Requirements (`FR-n`, `CFG-n`, `NFR-n`, `SEC-n`, `ERR-n`, `AC-n`). Source of truth. |
| `openapi.yaml` | Human + AI | MCP contract. **Generated** from live tool schemas — never hand-edit argument schemas. |
| `plan.md` | AI | Architecture, decisions D1–D10, risks, milestones. |
| `tasks.md` | AI | Ordered checklist `T-n`. |
| `REPORT.md` | AI + CI | Verification evidence. Real command output only. |

## Workflow — five gated phases

Specify (human) → Plan → Tasks → Implement → Verify. **Stop at each gate and wait
for the word `proceed`.** No code before Phase 4. If the spec is ambiguous or two
requirements conflict, **stop and ask** — do not pick silently, and do not edit
`spec.md` yourself except to flip a status after the evidence exists.

Every change cites an ID: in the test (`# FR-14 / AC-1`), the commit
(`fix(sec): confine attachment paths (SEC-3)`) and the PR.

## What this is not

**Not a second Jira.** Every tool is a thin wrapper over Jira Cloud REST v3. If a
rule seems missing — workflow validity, who may transition what, allowed field
values, permission checks — it is in Jira, deliberately. Do not re-implement it.
If a tool's behaviour looks wrong, read the Jira response (and Atlassian's docs)
before changing this repository.

## Where things live

```
src/servers/server.py          app, health route                (FR-16, 17)
src/tools/jira_tools.py        MCP surface ONLY                 (FR-1…13, 15, 18)
src/tools/bulk_issue_input.py  createIssuesBulk argument normalization (pure; FR-5)
src/services/jira_service.py   JiraService facade: public API, logging, delegates only
src/services/jira_client.py    HTTP transport: session, auth, request
src/services/adf.py            ADF build / read helpers (pure)  (FR-20)
src/services/fields.py         issue types, priorities, epic-field cache (FR-14, 22)
src/services/issues.py         create / read / update / labels / comments / links (FR-1…3, 6…10, 14)
src/services/search.py         JQL reads: search_issues + get_issues_bulk (token pagination) (FR-4, 11, 23)
src/services/bulk_create.py    bulk create across projects      (FR-5)
src/services/transitions.py    status transitions               (FR-13)
src/services/attachments.py    attachments — SEC-3 / T-7 lands here (FR-12)
src/config/                    App Configuration → env → default (CFG-*)
src/utils/log_helper.py        logging
src/exceptions/exceptions.py   exceptions
tests/                              mock-only, no network
```

**Layering (never violate):** `server → tools → service → config`.
- The **service** layer never imports FastMCP. The **tools** layer never imports `requests`, never builds a Jira payload.
- Adding a tool touches: one delegate on `JiraService` plus its implementation in the matching `services/` module, one `_register_*` function and one entry in `register_tools` in `jira_tools.py`, one entry in `tests/`, then regenerate `openapi.yaml`. If it needs `server.py` or `_request`, it changes how *everything* behaves — stop and check.
- Tool names share one namespace; a duplicate silently replaces another. The contract test asserts the exact set of 13.

## Things that look like bugs but are not

- **No default project, on purpose** (FR-14). Do not add `JIRA_PROJECT_KEY`, a constant, or a "convenient" fallback. `tests/test_no_default_project.py` greps `src/` for it and will fail. Issue-key tools take no project; `searchIssues` injects none into JQL.
- **Issue types are looked up per project**, every call. Do not cache them globally.
- **Transition by resolved ID**, never by status name; `already_done` is a success, not an error.
- **`createIssuesBulk` accepts string-encoded and `{"issues":[…]}`-wrapped entries.** That is observed LLM behaviour. Do not "simplify" it away. It lives in `src/tools/bulk_issue_input.py` and is pinned by `tests/test_tool_contract.py` / `tests/test_bulk_issue_input.py`.
- **Default issue type is `story` and default priority is `Low`** when omitted (Q-1 open). Don't change either without a decision.
- **Results are JSON strings, not objects** (FR-21). Changing this breaks existing agents.
- **`run_server.py` uses `--reload` via `os.system`.** Local dev only. The container runs `uvicorn` directly (NFR-7).
- **`Content-Type` is set to `None` for attachments** so `requests` can write its multipart boundary. `X-Atlassian-Token: no-check` is required by Jira.
- **`fetch_all` and `max_results` on `getIssuesBulk` are currently ignored** — a known defect (DEF-5, T-11), not a design.

## Standing orders

### Retry and timeouts
Reads retry on transport failure only; **writes never retry**; nothing that reached
Jira retries (not even 429/503). Structural: `get()` → `retry=True`, `post()/put()`
→ `retry=False`, no setting changes it. A retried `createIssue` is a duplicate issue.
Every call has a timeout.

### Errors
A tool never raises a stack trace at an agent. Target contract (ERR-1…3): every
failure is a tool error `"<CODE>: <message>"`; no `{"success": false}` returned as a
successful result. Raw Jira bodies go to the log, never to the caller.

### Security
- No hard-coded secrets. `JIRA_API_TOKEN` never appears in a log, a result or an error.
- No `print()` in `src/`. Use `logging`. Never log issue summaries, descriptions or comments at INFO.
- **Never read a path or interpolate a key you haven't validated** (SEC-3, SEC-4). `file_path` only inside `JIRA_ATTACH_ROOT`.
- Tools never accept a host. `JIRA_URL` is the only destination.
- **Any caller who reaches this server acts as the service account** (SEC-1, unresolved). Don't deploy it internet-facing.
- Don't widen `ruff`'s ignore list to get green. Fix the code.

### Testing
- `uv run pytest tests/ -q --cov=src --cov-fail-under=85` (gate arrives with T-20; target ≥ 85%).
- **No network, ever.** Tests mock `requests.Session.request` via `tests/_mock_jira_api.py` and call tools through `fastmcp.Client(server.mcp)`, so the code under test is the code that ships. `tests/__init__.py` sets fake credentials and blanks `AZURE_APPCONFIG_ENDPOINT` *before* imports — keep it first (a populated `.env` would otherwise make tests read Azure App Configuration; guarded by `tests/test_config_hermeticity.py`).
- Test first. A failing test citing the requirement precedes every fix.
- Every tool and every `JiraService` public method needs ≥ 1 test. A requirement with no test is a finding.
- **Service components** (`fields`, `issues`, `search`, `bulk_create`, `transitions`, `attachments`) never import `jira_service`, FastMCP or `requests`; they receive the request path as an injected callable and `JiraFields` where they need field metadata. The facade passes `_dispatch_request`, which resolves the logged, patchable `_request` at call time. `tests/test_service_modules.py` enforces the import rules.
- **Service lifecycle (T-15a):** `jira_tools._jira` is `None` until the first `register_tools()` call builds it; importing `src.tools.jira_tools` constructs nothing, repeated registration constructs nothing more, and a pre-set or patched `_jira` is never replaced. It is still module-level state, and importing `src.servers.server` still builds it once (server.py registers at module level). Tests substitute the service with `patch.object(jira_tools, "_jira", …)`; `tests/test_service_lifecycle.py` pins all of this. Parent T-15 (blank-safe config, startup validation, URL, port) is still open.
- `tests/test_tool_contract.py` compares the complete MCP definition of all 13 tools (name, description, input/output schema, tags, order), the service method and arguments each tool delegates to, every tool's error mapping, and the `createIssuesBulk` normalization against `tests/golden/tool_contract.json`, generated from the same original code. Same rule: **never regenerate it from refactored code.** `tests/test_tool_registration.py` pins `ENABLED_JIRA_TOOLS` handling (golden from the original code): the effective registration order is the order of the enabled list, not of the lookup table. The tool layer stays one registration module (`jira_tools.py`); revisit splitting it only after T-15 (service injection) and T-18 (`guarded` error contract) have landed.
- `tests/test_service_golden.py` replays 81 mocked scenarios against `tests/golden/`, which were generated from the **pre-modularization code** (git `b6fc26d`). **Never regenerate the golden files from refactored code** — that hides behaviour changes. Intentional exception: Entry/Exit log lines of five internal helpers are not emitted when components call each other directly (documented in the test).
- Assert **zero Jira calls** for every validation refusal (`call_log == []`).

### Commands
```bash
uv sync --locked
uv run --with ruff ruff check .
uv run --with pytest --with pytest-cov pytest tests/ -q --cov=src
uv run python -m uvicorn src.servers.server:mcp_app --port 9002   # local
curl http://127.0.0.1:9002/mcp/jira/health
```

## Per-milestone Definition of Done
- [ ] Each requirement touched has a test citing its ID
- [ ] `ruff` clean, no new ignores · `pytest` green · coverage not lower
- [ ] No `print()`, no secrets or issue content in logs/errors
- [ ] `openapi.yaml` regenerated and contract test green
- [ ] `REPORT.md` updated with actual output
- [ ] `tasks.md` ticked; `spec.md` TARGET → BASELINE for what shipped
- [ ] Conventional Commit messages carry the requirement IDs

## Known rough edges
- **Port:** the code defaults to 9002; `.env.example` ships `JIRA_PORT=` blank, which currently crashes startup (DEF-8, T-15). Set it, or fix T-15 first.
- **`getIssuesBulk` epic detection** is "contains a hyphen" — fragile until T-8/T-11.
- **Epic field cache is process-wide** and set before the request succeeds (DEF-12, T-14).
- **`pyproject.toml` carries unrelated dependencies** (`agent-framework*`, `httpx2`); don't build on them.
- **README is empty** (T-23).
