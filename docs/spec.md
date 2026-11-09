# Jira MCP Server — Specification

| | |
|---|---|
| **Document** | `spec.md` — source of truth for requirements |
| **Owner** | Human (engineering + product). Claude proposes edits; a human approves them. |
| **Status** | v1.0 — baseline captured from branch `feature/jira_mcp_phase2`, plus a hardening target |
| **Companions** | `openapi.yaml` (contract) · `plan.md` (architecture) · `tasks.md` (work) · `REPORT.md` (verification) · `CLAUDE.md` (standing orders) |

> **How to read this spec.** The server already exists. This spec was written
> *from* the code and its tests, then extended with what production needs that
> the code does not yet do. Every requirement therefore carries a **Status**:
>
> - **BASELINE** — implemented today, backed by code (and a test where noted).
> - **TARGET** — required for production, not yet implemented. Each has a task in `tasks.md`.
>
> Requirement IDs are permanent. Commits, tests and PRs cite them (`FR-12`,
> `SEC-3`). Never renumber; retire an ID by marking it `WITHDRAWN`.

---

## 1. Purpose and scope

### 1.1 What this is
An **MCP (Model Context Protocol) server** that exposes Jira Cloud operations as
13 tools an AI agent can call over streamable HTTP. It is an **adapter**: it
translates a tool call into Jira Cloud REST API v3 requests and translates the
answer back. Jira remains the single source of truth for issues, workflows,
permissions and field schemes.

```
MCP client (agent)
   |  streamable HTTP  POST /mcp/jira
   v
server.py -> jira_tools.py -> JiraService -> requests.Session
                                                 |  HTTPS, Basic auth
                                                 v
                                     Jira Cloud  /rest/api/3/*
```

### 1.2 In scope
- The 13 tools in §4, their inputs, outputs and failure behaviour.
- Configuration, logging, health check, container image and CI/CD pipeline.
- The "no default project" rule (FR-14) — the defining design decision.

### 1.3 Out of scope
- **Not a second Jira.** No workflow rules, permission logic, field schemes or
  issue-type rules are re-implemented. If a rule appears to be missing, it
  belongs to Jira. Do not add it here.
- No Jira Server / Data Center support (REST v3 + ADF are Cloud features).
- No delete, assign, sprint, board, worklog or user-search tools.
- No UI. No persistence. The server is stateless apart from a per-process cache
  (FR-22).
- Identity propagation / end-user authentication (see SEC-1; unresolved).

### 1.4 Users and actors
| Actor | Needs |
|---|---|
| **Agent** (LLM via an MCP client) | Predictable tool names, schemas and error text it can act on. |
| **Operator** | Deploy the same image to dev/qa/prod by changing configuration only; see health and logs. |
| **Jira admin** | One service account whose reach bounds everything the server can do. |
| **Reviewer / auditor** | Trace any line of code to a requirement ID. |

---

## 2. Glossary
| Term | Meaning |
|---|---|
| **Issue key** | `PROJ-123`. A project key plus a number. |
| **Project key** | `PROJ`. The prefix only. |
| **ADF** | Atlassian Document Format — Jira's JSON rich-text format; required for descriptions and comments in REST v3. |
| **Company-managed / team-managed** | Jira project flavours. Company-managed has `Epic Name` / `Epic Link` custom fields; team-managed uses `parent`. |
| **Transition** | A workflow edge with a workflow-specific numeric ID. The ID is never the status name. |

---

## 3. Global requirements

### 3.1 Transport and surface
| ID | Requirement | Status |
|---|---|---|
| **FR-14** | **There is no default project.** No setting, constant or fallback may supply a project key. `jira-createIssue` and every issue inside `jira-createIssuesBulk` require `project_key`; it is validated (present, string, non-blank, trimmed) **before the first Jira call**. A bulk batch with one bad entry makes zero Jira calls. Different issues in one bulk call may target different projects. | BASELINE — `test_no_default_project.py`, `test_jira_service_project_key.py`, `test_jira_tools_project_key.py` |
| **FR-15** | The server registers the 13 tools by default. `ENABLED_JIRA_TOOLS` (comma-separated tool names) restricts the set; empty/unset means all. An unknown name is logged as a warning and skipped, never fatal. | BASELINE (untested — see T-17) |
| **FR-16** | MCP endpoint is `POST /mcp/jira` (streamable HTTP). | BASELINE |
| **FR-17** | `GET /mcp/jira/health` returns `200 {"status":"healthy","service":"jira-mcp-server"}`. It does **not** call Jira (liveness, not readiness). | BASELINE (untested — T-17) |
| **FR-18** | Every tool carries tags `jira` plus `read` or `write` (and `bulk` where relevant) so a client or gateway can filter read-only tools. | BASELINE |

### 3.2 Behaviour shared by all tools
| ID | Requirement | Status |
|---|---|---|
| **FR-19** | **Error contract.** A tool never leaks a stack trace. Bad input → `JiraValidationError` → surfaced as an MCP tool error carrying a message the agent can act on. A non-2xx answer from Jira → an error naming the HTTP status. *Target:* one uniform contract for every tool (see ERR-1…3). | BASELINE (inconsistent — DEF-14, see §5) |
| **FR-20** | Descriptions and comments are sent to Jira as ADF. Descriptions read back are flattened to plain text; an absent or unparseable description reads as `"No description."`. | BASELINE |
| **FR-21** | Tool results are JSON **strings** (serialised objects), not structured objects. | BASELINE — fixed contract for current clients; changing it is a breaking change |
| **FR-22** | Epic custom fields (`Epic Name`, `Epic Link`) are discovered once from `/rest/api/3/field` and cached for the process lifetime. Where absent (team-managed) the server falls back to `parent`. | BASELINE (known defect — see DEF-12) |
| **FR-23** | Search and bulk-read paginate automatically using Jira's token-based `/rest/api/3/search/jql` (`nextPageToken`, 100 per page), stopping on `isLast`, empty page, repeated keys (loop guard) or a page safety cap. | BASELINE (partially tested) |
| **FR-24** | Jira's own authorisation is authoritative. The server never widens it; a Jira 401/403/404 is reported, not retried or masked. | BASELINE |

### 3.3 Configuration
| ID | Requirement | Status |
|---|---|---|
| **CFG-1** | Precedence, highest first: **Azure App Configuration → OS env / `.env` → field default**. | BASELINE |
| **CFG-2** | `AZURE_APPCONFIG_ENDPOINT` unset ⇒ App Configuration is skipped entirely (no Azure call, no credential). Set ⇒ keys `"<APP_NAME>:*"` with label `<ENVIRONMENT>` are loaded, prefix trimmed. Defaults: `APP_NAME=jira-mcp`, `ENVIRONMENT=dev`. | BASELINE |
| **CFG-3** | Settings: `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`, `LOG_LEVEL` (App Config → env); `JIRA_PORT`, `ENABLED_JIRA_TOOLS` (env only). | BASELINE |
| **CFG-4** | A **blank** environment value (as produced by copying `.env.example`) must behave as *unset*, not crash. | **TARGET** — today `JIRA_PORT=` raises `ValueError` at import (DEF-8) |
| **CFG-5** | The server **fails fast at startup** with a clear message if `JIRA_URL`, `JIRA_USERNAME` or `JIRA_API_TOKEN` is missing, instead of failing on the first tool call. | **TARGET** (DEF-9) |
| **CFG-6** | `JIRA_URL` is normalised once (trailing slash stripped) and used everywhere. | **TARGET** (DEF-10) |
| **CFG-7** | Nothing environment-specific is hard-coded. The same image runs in dev/qa/prod by changing configuration only. | BASELINE |

### 3.4 Non-functional
| ID | Requirement | Status |
|---|---|---|
| **NFR-1** | Every outbound Jira call has a connect and read timeout. | **TARGET** — none today (DEF-2) |
| **NFR-2** | Reads (`GET`) retry on connection failure/timeout (bounded, with back-off). **Writes never retry.** A response that reached Jira (4xx/5xx) is never retried. This is structural, not configurable — a retried `createIssue` is a duplicate issue. | **TARGET** — no retries today |
| **NFR-3** | Blocking `requests` calls run off the event loop (`asyncio.to_thread`) so one slow Jira call does not stall other agents. | BASELINE |
| **NFR-4** | Logs are UTC, `LOG_LEVEL`-controlled, one line per entry/exit/exception of each service and tool call. | BASELINE — `log_helper.py` |
| **NFR-5** | **All** diagnostics go through `logging`. No `print()` in `src/`. Issue content (summary, description, comments) is never logged at INFO. | **TARGET** — 34 `print()` calls today (DEF-3) |
| **NFR-6** | Line coverage ≥ **85%** overall, with every tool and every `JiraService` public method exercised by at least one test. CI enforces it. | **TARGET** — 67% today |
| **NFR-7** | The container image runs `uvicorn` directly (no `--reload`, no `os.system`), listens on `JIRA_PORT`, and passes Trivy HIGH/CRITICAL (fixable) before push. | BASELINE (port hard-coded — T-15) |

### 3.5 Security
| ID | Requirement | Status |
|---|---|---|
| **SEC-1** | **Authentication of callers — unresolved.** The server holds one Jira service-account credential; any caller that can reach `/mcp/jira` acts with that account's full rights. This is a deployment property to be decided by the organisation (network isolation, gateway authentication, or per-user credential propagation). Until decided, the endpoint **must not** be internet-reachable. | UNRESOLVED — decision needed |
| **SEC-2** | Secrets (`JIRA_API_TOKEN`) come from App Configuration/Key Vault or `.env` (git-ignored). They are never logged, never returned, never in an error message. | BASELINE (verify — T-9) |
| **SEC-3** | **`jira-addAttachment` with `file_path` must not read arbitrary files** from the server's disk. Allowed only inside a configured attachment directory (`JIRA_ATTACH_ROOT`); the path is resolved (symlinks, `..`) and rejected if it escapes. If `JIRA_ATTACH_ROOT` is unset, `file_path` mode is disabled and only `content_base64` works. | **TARGET** — today any readable file can be exfiltrated to Jira (DEF-1, **High**) |
| **SEC-4** | Issue keys and project keys are validated against `^[A-Za-z][A-Za-z0-9_]*(-[0-9]+)?$` (project key: without the number) **before** being interpolated into a URL path or JQL. A crafted value such as `../../x` or `A OR 1=1` is refused with no Jira call. | **TARGET** — only `project_key` presence is checked today (DEF-4) |
| **SEC-5** | Tools never accept a destination host. `JIRA_URL` is the sole host any call can reach. `jira-addRemoteLink` and `jira-addCommentWithLinks` accept only `http://`/`https://` URLs. | **TARGET** for the scheme check (DEF-11) |
| **SEC-6** | Jira error bodies are logged in full but returned to the agent only as status + Jira's `errorMessages`/`errors` (no raw HTML, no request echo). | **TARGET** (DEF-6) |
| **SEC-7** | Dependencies are audited (`pip-audit`), the repository secret-scanned, the image scanned. Unused dependencies are removed. | BASELINE (CI) / **TARGET** for pruning (T-16) |

---

## 4. Tool requirements

Common to all: results are JSON strings (FR-21); failures follow ERR-1…3 (§5).
Argument tables are normative and mirror `openapi.yaml`, which is generated
from the live tool schemas.

### FR-1 `jira-createIssue` &nbsp; `write`
Create one issue.

| Argument | Type | Req. | Notes |
|---|---|---|---|
| `project_key` | string | **yes** | FR-14. No default. |
| `summary` | string | **yes** | |
| `description` | string | no (`""`) | Sent as ADF. |
| `issue_type` | string | no (`"story"`) | Matched case-insensitively against **that project's** issue types (looked up via `createmeta` per call). |
| `priority` | string \| null | no | Normalised with `capitalize()`, checked against Jira's priorities. **If omitted, `Low` is applied.** |
| `labels` | string[] \| null | no | Blank entries dropped. |
| `parent` | string \| null | no | Parent/epic key, set at creation. |
| `epic_name` | string \| null | no | Applied only if `issue_type` is epic **and** the project has an `Epic Name` field. |

**Result:** `{message, key, url, summary, type}`.
**Rules:** invalid issue type → error listing the valid types; invalid priority → error.
**Open question (Q-1):** silently defaulting priority to `Low` — keep (documented) or require an explicit value? See §7.

### FR-2 `jira-updateIssue` &nbsp; `write`
Update `summary`, `description` and/or `priority` of one issue.
`issue_key` required; at least one other field required, else `"Nothing to update."`
Empty strings are treated as "not provided". **Result:** `{message, key, updated_fields[]}`.

### FR-3 `jira-getIssue` &nbsp; `read`
Fetch one issue. **Result:** `{key, summary, status, priority, description (flattened), labels[], parent: {key, summary} | null}`.
Raises on an issue with no priority (DEF-7).

### FR-4 `jira-getIssuesBulk` &nbsp; `read` `bulk`
Two modes selected by the shape of `project_key`:
- **Project mode** — `RET` → `project = RET ORDER BY key ASC`.
- **Epic mode** — `RET-424` → verifies the issue *is* an Epic, then `(key = RET-424 OR parent = RET-424)`.

Returns, per issue: `key, summary, status, priority, description, labels, parent, issue_type, created, updated`; plus `total_retrieved, api_calls_made, fetch_mode`.
**Target behaviour:** `max_results`, when given, truncates the result to exactly that many; `fetch_all=false` returns the first page only (today neither is honoured — DEF-5).

### FR-5 `jira-createIssuesBulk` &nbsp; `write` `bulk`
Create many issues in one Jira bulk call. Each entry needs `project_key` and `summary`; optional `description, issue_type (default story), priority (default Low), epic_name, labels, parent`.
The tool tolerates clients that send each entry as a JSON **string** or wrap the list as `{"issues":[…]}` (observed LLM behaviour — keep).
**Result:** `{success, message, created_issues[{key,url,summary}], total_requested, total_created, errors|null}`.
**Rules:** all validation up front (FR-14); partial Jira failures reported per index, with `summary` attributed to the **correct** issue (DEF-13) and `success` not `true` when `errors` is non-empty.

### FR-6 `jira-linkIssueToEpic` &nbsp; `write`
Link `issue_key` under `epic_key`. Company-managed → `Epic Link` field; team-managed → `parent`. **Result:** `{message, issue, epic}`.

### FR-7 `jira-addComment` &nbsp; `write`
Add a plain-text comment (ADF paragraph). **Result:** `{message, issue, comment}`.
*Target:* do not echo the full comment back (SEC / NFR-5 privacy).

### FR-8 `jira-addCommentWithLinks` &nbsp; `write`
One comment: `intro_text` followed by `links: [{text,url}]` each rendered as a real link mark, comma-separated. **Result:** `{message, issue}`.
Each link must contain `text` and `url` (http/https) or the call is refused before any Jira call (SEC-5).

### FR-9 `jira-searchIssues` &nbsp; `read`
Run caller-supplied JQL, paginated, **no project injected** (FR-14). `max_results=0` ⇒ everything (50-page safety cap, ≤ 5,000 issues). **Result:** `{results:[{key,summary,status,priority,description,labels,url}]}`.
JQL is the caller's responsibility; Jira rejects invalid JQL and that error is passed through (ERR-2).

### FR-10 `jira-updateLabels` &nbsp; `write`
Add and/or remove specific labels without replacing the array (uses Jira's `update.labels` add/remove operations). At least one label required. **Result:** `{message, key, added[], removed[]}`.

### FR-11 `jira-addRemoteLink` &nbsp; `write`
Add a Remote Issue Link object (`url`, `title`). URLs containing `testrail` additionally get the TestRail icon, application and relationship. **Result:** `{message, key, url, title}`.

### FR-12 `jira-addAttachment` &nbsp; `write`
Attach a file. **Exactly one** of `file_path` or `content_base64` (+ required `filename`; optional `mime_type`). Base64 is decoded strictly (`validate=True`). Uses `X-Atlassian-Token: no-check` and multipart.
**Result:** `{message, key, filename}`. `file_path` is subject to **SEC-3**.

### FR-13 `jira-transitionIssue` &nbsp; `write`
Move an issue to `target_status`:
1. Read current status. If it equals the target (case-insensitive) → `{result:"already_done"}`, **no write** (idempotent).
2. Read available transitions; match by destination status name, then by transition name (case-insensitive).
3. No match → error listing the available target statuses.
4. `POST` the resolved **transition ID** (never the status name).

**Result:** `{success, result: "transitioned"|"already_done", message, issue, from_status, to_status, transition_id?}`. Fully tested (9 tests).

---

## 5. Error contract (target)

Today the tools fail in four different ways (a `ToolError`, a raw `RuntimeError`, a `{"success":false}` JSON body from bulk tools, and `KeyError` on odd Jira payloads). An agent cannot reliably tell failure from success. The target is one contract:

| ID | Requirement |
|---|---|
| **ERR-1** | Every failure is raised as an MCP tool error (`isError=true`). No tool returns `{"success": false}` as a *successful* result. |
| **ERR-2** | The error message is `"<CODE>: <human text>"` with `CODE` ∈ `VALIDATION_ERROR`, `NOT_FOUND`, `AUTHENTICATION_ERROR`, `AUTHORIZATION_ERROR`, `CONFLICT`, `RATE_LIMITED`, `JIRA_SERVICE_ERROR`, `TIMEOUT`, `CONNECTION_ERROR`. |
| **ERR-3** | HTTP mapping: 400→`VALIDATION_ERROR`, 401→`AUTHENTICATION_ERROR`, 403→`AUTHORIZATION_ERROR`, 404→`NOT_FOUND`, 409→`CONFLICT`, 429→`RATE_LIMITED`, 5xx/unparseable→`JIRA_SERVICE_ERROR`. Partial success in a bulk create is **not** an error but must set `success:false` only if *nothing* was created, and always list `errors`. |

Bulk tools are the one place a result can legitimately contain per-item errors alongside successes.

---

## 6. Acceptance criteria (Given / When / Then)

**AC-1 (FR-14)** Given no `project_key`, when `jira-createIssue` is called, then the call is refused and the mock Jira receives **zero** requests.
**AC-2 (FR-14)** Given a bulk list of three issues where the third lacks `project_key`, when called, then **zero** issues are created and the error names index 2.
**AC-3 (FR-13)** Given an issue already in `Done`, when transitioned to `done`, then the result is `already_done` and **no** `POST …/transitions` is sent.
**AC-4 (FR-13)** Given no available transition to the target, when called, then the error lists the available target statuses.
**AC-5 (SEC-3)** Given `JIRA_ATTACH_ROOT=/data/attach`, when `file_path=/etc/passwd` or `/data/attach/../../etc/passwd` is supplied, then the call is refused with `VALIDATION_ERROR` and no Jira request is made.
**AC-6 (SEC-4)** Given `issue_key="../../rest/api/3/myself"`, when any issue-key tool is called, then the call is refused with no Jira request.
**AC-7 (FR-4)** Given a project with 250 issues and `max_results=120`, when called, then exactly 120 issues are returned.
**AC-8 (FR-5)** Given Jira rejects the 2nd of 3 issues, when called, then `created_issues` has 2 entries each with the *correct* summary, `errors` names index 1, and the 3rd summary is not attributed to the 2nd key.
**AC-9 (NFR-2)** Given a `GET` times out twice then succeeds, when called, then it succeeds (≤ `JIRA_MAX_RETRIES`). Given a `POST` times out, then exactly **one** request was made.
**AC-10 (CFG-4/5)** Given `JIRA_PORT=` (blank), when the server starts, then it listens on 9002. Given `JIRA_URL` unset, then startup fails with a message naming the missing variable.
**AC-11 (FR-15)** Given `ENABLED_JIRA_TOOLS=jira-getIssue,bogus`, when started, then exactly one tool is registered and a warning names `bogus`.
**AC-12 (NFR-5)** Given a comment body containing a secret marker, when `jira-addComment` runs at `LOG_LEVEL=DEBUG`, then the marker appears in **no** log line or stdout.

---

## 7. Open questions (human decisions)

| ID | Question | Default if unanswered |
|---|---|---|
| **Q-1** | Keep silent `Low` priority default in create tools, or require explicit priority? | Keep, but return the applied priority in the result so it is visible. |
| **Q-2** | SEC-1: how does caller identity reach Jira — network-only isolation, API-gateway authoriser, or per-user OAuth? | Network-only; document as accepted risk. |
| **Q-3** | Are `file_path` attachments needed at all, or is `content_base64` sufficient? | Disable `file_path` unless `JIRA_ATTACH_ROOT` is set. |
| **Q-4** | Should tool results become structured objects instead of JSON strings (FR-21)? | No — breaking change; revisit as a v2. |
| **Q-5** | Is a read-only deployment profile (only `read`-tagged tools) wanted? | Yes — already possible through `ENABLED_JIRA_TOOLS`; add a documented preset. |

---

## 8. Traceability

Every requirement maps to code and a test in `REPORT.md` §3. A requirement with no test is a finding, not a pass.
Commit messages use Conventional Commits with the ID: `fix(sec): confine attachment paths (SEC-3)`.
