# Jira MCP Server — Plan

| | |
|---|---|
| **Document** | `plan.md` — architecture and approach |
| **Owner** | Claude drafts; a human approves at the Phase-2 gate |
| **Implements** | `spec.md` v1.0 (IDs cited throughout) |
| **Status** | Baseline architecture is **as built**. §6 onward is the plan for the TARGET requirements. |

---

## 1. Architecture as built

```
 MCP client (agent)
      |  streamable HTTP  POST /mcp/jira        GET /mcp/jira/health
      v
 ┌─────────────────────────── src/ ───────────────────────────────┐
 │ servers/server.py     FastMCP app, health route, http_app(path=...)  │  FR-16 FR-17
 │        │ register_tools(mcp)                                          │
 │ tools/jira_tools.py   13 @mcp.tool wrappers; ENABLED_JIRA_TOOLS      │  FR-1…13 FR-15 FR-18
 │   └─ bulk_issue_input.py  createIssuesBulk argument normalization   │  FR-5
 │        │ asyncio.to_thread(...)                                       │  NFR-3
 │ services/jira_service.py   JiraService — public facade, delegates    │  FR-14 FR-20…24
 │   ├─ issues.py  search.py  bulk_create.py  transitions.py  attachments.py │  FR-1…13 FR-23
 │   ├─ fields.py      issue types, priorities, epic-field cache         │  FR-14 FR-22
 │   ├─ adf.py         ADF helpers (pure)                                │  FR-20
 │   └─ jira_client.py JiraClient: requests.Session (Basic auth)         │  NFR-1 NFR-2
 │ config/…  utils/log_helper.py  exceptions/exceptions.py              │  CFG-* NFR-4
 └───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTPS
                                 v
                      Jira Cloud  /rest/api/3/*
```

| Layer | File | Owns | Must not |
|---|---|---|---|
| **Server** | `servers/server.py` | App construction, health route, transport path | Contain tool or Jira logic |
| **Tools** | `tools/jira_tools.py`, `tools/bulk_issue_input.py` | MCP names, descriptions, argument schemas, tags, translating `JiraValidationError` → `ToolError`, thread off-loading | Call `requests`; build Jira payloads |
| **Service — facade** | `services/jira_service.py` | The public `JiraService` API, entry/exit logging, composition of the components below, the request path they call | Hold Jira logic; import FastMCP |
| **Service — operations** | `services/issues.py`, `search.py`, `bulk_create.py`, `transitions.py`, `attachments.py` | Payload shape, validation, pagination — one module per cohesive concern; request path and field metadata injected | Import the facade, FastMCP or `requests` |
| **Service — fields** | `services/fields.py` | Issue types (per project, every call), priorities, epic custom-field discovery and its cache | Build payloads |
| **Service — transport** | `services/jira_client.py` | `requests.Session`, Basic auth, default headers, the single request path every Jira call uses, the non-2xx `RuntimeError` | Contain Jira business logic; import service or tool modules |
| **Service — ADF** | `services/adf.py` | Pure ADF builders and the plain-text description reader | Do I/O, read config, or log |
| **Config** | `config/config.py`, `config_reader.py` | Reading App Configuration → env → default | Hold business rules |
| **Utils** | `utils/log_helper.py` | Logging setup and entry/exit decorators | — |
| **Exceptions** | `exceptions/exceptions.py` | `JiraValidationError` | — |

The dependency direction is one-way: **server → tools → service → config**. The
service layer knows nothing about MCP, so it is unit-testable with a mocked
`requests.Session.request` (see `tests/_mock_jira_api.py`).

### 1.1 Technology
Python ≥ 3.11 · FastMCP ≥ 2 · Starlette/uvicorn · `requests` · Pydantic v2 ·
`azure-identity` + `azure-appconfiguration-provider` · `uv` + `hatchling` · pytest · ruff.
Container: `python:3.11-slim` + `uv sync --frozen --no-dev`, `CMD uv run uvicorn …`.
CD: GitHub Actions → ACR (OIDC, Trivy gate) → Azure Container Apps revision.

### 1.2 Decisions that are not obvious from the code

| # | Decision | Why | Spec |
|---|---|---|---|
| D1 | **No default project, anywhere.** Not in config, not in constants, not in `.env.example`. A static test greps `src/` for `JIRA_PROJECT_KEY`, `DEFAULT_PROJECT`, a literal `"KAN"`. | The server is shared across Jira projects with no redeploy. A silent default writes issues into the wrong project. | FR-14 |
| D2 | **Issue types are looked up per project** (`createmeta`), not globally. | Projects have different issue-type schemes. | FR-1 |
| D3 | **`transitionIssue` resolves the transition ID from the live transitions list.** | IDs are workflow-specific; the status name is not an ID. | FR-13 |
| D4 | **Idempotent transition.** Already in target ⇒ `already_done`, no write. | Agents retry; a repeat must be harmless. | FR-13 |
| D5 | **Blocking `requests` + `asyncio.to_thread`**, not an async HTTP client. | Smallest correct change; keeps the service layer plain and synchronous. | NFR-3 |
| D6 | **`createIssuesBulk` tolerates string-encoded or `{"issues":[…]}`-wrapped entries.** | Observed LLM behaviour. Removing it breaks real agents. | FR-5 |
| D7 | **Tool results are JSON strings.** | Existing clients depend on it. Changing is a v2 decision (Q-4). | FR-21 |
| D8 | **Epic fields discovered once and cached; fall back to `parent`.** | Company- vs team-managed projects differ. | FR-22 |
| D9 | **Production uses `uvicorn` directly; `run_server.py` (`--reload`, `os.system`) is local-dev only.** | A reload watcher in a container can leave it "running" but not serving. | NFR-7 |
| D10 | **App Configuration is skipped, not failed, when its endpoint is unset.** | Local development needs no Azure. | CFG-2 |

---

## 2. Requirement → module map

| Requirement | Module(s) |
|---|---|
| FR-1…13 (tools) | `jira_tools.py` (surface) · `jira_service.py` (behaviour) |
| FR-14 | `jira_service.create_issue`, `create_issues_bulk`, `get_issue_types` · `test_no_default_project.py` |
| FR-15, FR-18 | `jira_tools.register_tools` |
| FR-16, FR-17 | `server.py` |
| FR-19, ERR-* | `jira_tools.py` (translation) · **new** `exceptions.py` hierarchy + `guarded` |
| FR-20 | `_as_rich_text`, `_readable_desc` |
| FR-22 | `_load_custom_fields` |
| FR-23 | `get_issues_bulk`, `search_issues` |
| CFG-* | `config.py`, `config_reader.py` |
| NFR-1, NFR-2 | **new** request-path rewrite in `services/jira_client.py` (`JiraService._request` delegates to it) |
| NFR-4, NFR-5 | `log_helper.py` |
| SEC-3, SEC-4, SEC-5 | **new** `src/utils/validation.py`, called from the service layer |

---

## 3. Data and contracts

There is no database. The contracts are:

- **Inbound:** MCP JSON-RPC 2.0 over streamable HTTP — `openapi.yaml`.
- **Outbound:** Jira Cloud REST v3 — the per-tool upstream list is in `openapi.yaml` under `x-mcp-tools[*].upstream`.
- **State:** one in-process cache (epic custom-field IDs). Safe to lose; rebuilt on first use.

`openapi.yaml` is **generated** from the live FastMCP tool schemas (`scripts/gen_openapi.py`, task T-21),
so the argument schemas cannot drift from the code. A test fails CI if they do.

---

## 4. Error model (target)

```
tool function
   └─ try: service call
      except JiraValidationError → ToolError("VALIDATION_ERROR: …")
      except JiraApiError(status, body)  → ToolError("<MAPPED_CODE>: <sanitised message>")
      except requests.Timeout            → ToolError("TIMEOUT: …")
      except requests.ConnectionError    → ToolError("CONNECTION_ERROR: …")
```

Implemented once as a `guarded` decorator in `jira_tools.py` (replacing the
`try/except` currently copied into five tools and absent from the other eight). `functools.wraps`
is load-bearing: FastMCP derives the tool schema from the wrapped signature.
`JiraService._request` raises `JiraApiError` carrying `status` and a sanitised
`message`; the raw body goes to the log only.

---

## 5. Retry and timeout model (target)

| Request | Timeout | Retry |
|---|---|---|
| `GET` | connect 5 s, read 30 s (`JIRA_CONNECT_TIMEOUT`, `JIRA_READ_TIMEOUT`) | Connection error or timeout only; ≤ `JIRA_MAX_RETRIES` (default 2), exponential back-off with jitter |
| `POST` / `PUT` | same | **Never** |
| Any response that arrived (4xx/5xx incl. 429, 503) | — | **Never** |

Enforced structurally: `get()` passes `retry=True`; `post()`/`put()` pass `retry=False`;
no setting flips it. A retried `createIssue` or `createIssuesBulk` is a duplicate
issue; an overloaded Jira is exactly when hammering it is wrong.

---

## 6. Phased delivery

Gates: Claude stops after each phase and waits for `proceed`.

| Phase | Output | Status |
|---|---|---|
| **1 Specify** | `spec.md`, `openapi.yaml` | ✅ this change |
| **2 Plan** | this file | ✅ awaiting approval |
| **3 Tasks** | `tasks.md` | ✅ awaiting approval |
| **4 Implement** | code + tests, milestone by milestone | **M0 done (baseline). M1–M6 open.** |
| **5 Verify** | `REPORT.md`, coverage, contract check | ✅ baseline report written; re-run at each milestone |

### 6.1 Milestones (details in `tasks.md`)

| M | Theme | Closes | Why this order |
|---|---|---|---|
| **M0** | Baseline | FR-1…18 as built | Done. |
| **M1** | **Safety** | SEC-3, SEC-4, SEC-2/6, NFR-1/2 | Only High finding is file exfiltration; timeouts stop a hung Jira from hanging the agent. Everything after builds on a safe `_request`. |
| **M2** | **Correctness** | FR-4, FR-5, FR-3, FR-22 | Wrong or silently truncated results are worse than errors. |
| **M3** | **Config & ops** | CFG-4/5/6, NFR-7, SEC-7 | A fresh clone with the shipped `.env.example` currently crashes. |
| **M4** | **Error contract & logging** | ERR-1…3, NFR-5 | Needs M1's `JiraApiError`. Touches every tool, so done after tests exist. |
| **M5** | **Tests & CI** | NFR-6, contract test | Coverage rises *during* M1–M4 (test-first); M5 sets the gate and closes remaining gaps. |
| **M6** | **Docs & decisions** | README, `.env.example`, SEC-1/Q-1…5 | Needs human answers. |

### 6.2 Method for every fix
1. Write the failing test that cites the requirement (`# FR-4 / AC-7`).
2. Make it pass with the smallest change in the right layer.
3. Run ruff, pytest, coverage; update `openapi.yaml` if a schema changed.
4. Tick the task; add the ID to the commit message.

---

## 7. Risk register

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | **Arbitrary file read via `file_path`** exfiltrates server files (tokens, config) into Jira. | M | **H** | SEC-3 first (T-7). Until then disable `jira-addAttachment` via `ENABLED_JIRA_TOOLS`. |
| R2 | Any network-reachable caller acts with the service account's full rights (SEC-1). | M | H | Keep off the internet; decide Q-2; consider read-only preset (Q-5). |
| R3 | Hung Jira call blocks a worker thread indefinitely (no timeout). | M | M | NFR-1 (T-10). |
| R4 | Bulk create mis-attributes summaries / reports success on partial failure → agent believes work exists that doesn't. | M | M | T-12 with AC-8. |
| R5 | Changing result shape (FR-21, ERR-*) breaks existing agents. | M | M | ERR change is announced; results stay strings; add a CHANGELOG entry; ship behind a minor version bump. |
| R6 | Issue content in logs via `print()` (34 sites) — PII in container logs. | H | M | T-19; interim: ship with `LOG_LEVEL` irrelevant, so fix is code, not config. |
| R7 | Process-wide epic-field cache is wrong when one server fronts both company- and team-managed projects. | L | M | T-14: cache per project. |
| R8 | A blank `.env` value crashes startup; onboarding friction. | H | L | T-15. |
| R9 | CI only runs on push to `develop`; PRs are unchecked; `trufflehog@main` is an unpinned action. | M | L | T-22. |
| R10 | Coverage 67% — regressions in 6 of 13 tools would pass CI. | H | M | T-17, T-20. |

---

## 8. Definition of Done (per milestone)

- [ ] Every requirement touched has ≥ 1 test citing its ID.
- [ ] `ruff check .` clean — and no **new** entries in `pyproject.toml`'s ignore list.
- [ ] `pytest tests/` green; coverage not lower than before; ≥ 85% at M5.
- [ ] No `print()`, no secret or issue content in logs or error text.
- [ ] `openapi.yaml` regenerated; contract test green.
- [ ] `REPORT.md` updated with real command output, not assertions.
- [ ] `spec.md` status flipped TARGET → BASELINE for what shipped.
