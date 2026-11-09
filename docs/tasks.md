# Jira MCP Server — Tasks

| | |
|---|---|
| **Document** | `tasks.md` — ordered, checkable work list |
| **Owner** | Claude maintains; a human approves scope changes |
| **Source** | `spec.md` (requirements) · `plan.md` (milestones M0–M6) |
| **Rule** | Tick a box only when its **Done when** line is true *and* the evidence is in `REPORT.md`. Tests come first. |

Legend: ☑ done · ☐ open · **S/M/L** ≈ ½ day / 1–2 days / 3+ days · `[blocked: Q-n]` needs a human decision (spec §7).

---

## M0 — Baseline (as built on `feature/jira_mcp_phase2`)

- [x] **T-1** Project scaffold: `src/jira/{config,servers,services,tools,utils,exceptions}`, `pyproject.toml`, `.env.example`, `run_server.py`. *(CFG-1…3, NFR-4)*
- [x] **T-2** `JiraService`: session, `_request`, ADF helpers, epic-field discovery, pagination. *(FR-20, 22, 23)*
- [x] **T-3** Thirteen tools registered with names, descriptions, schemas, tags; `ENABLED_JIRA_TOOLS`. *(FR-1…13, 15, 18)*
- [x] **T-4** No-default-project rule + 3 static guards + service/tool tests. *(FR-14 · 22 tests)*
- [x] **T-5** `jira-transitionIssue`: resolve ID, idempotent, clear errors. *(FR-13 · 9 tests)*
- [x] **T-6** Dockerfile (`uvicorn` direct), GitHub Actions: ruff → pytest → pip-audit → trufflehog → build → Trivy → ACR → Container Apps. *(NFR-7, SEC-7)*

---

## M1 — Safety  *(do first)*

- [ ] **T-7** `S` **Confine `file_path` attachments.** *(SEC-3 · DEF-1 · R1 · **High**)*
  - New `JIRA_ATTACH_ROOT` setting. Unset ⇒ `file_path` refused with `VALIDATION_ERROR`; only `content_base64` works.
  - Resolve with `Path.resolve(strict=True)`; require `is_relative_to(root.resolve())`; reject symlink escapes and non-regular files; enforce a size cap (`JIRA_ATTACH_MAX_BYTES`, default 10 MB).
  - Tests first: `/etc/passwd`, `root/../../etc/passwd`, symlink inside root → outside, directory, oversize, valid file inside root. **AC-5**
  - **Done when:** all six cases pass and zero Jira requests are made for the five refusals.

- [ ] **T-8** `S` **Validate keys before they reach a URL or JQL.** *(SEC-4 · DEF-4)*
  - New `src/utils/validation.py`: `issue_key()`, `project_key()`, regexes from SEC-4; raise `JiraValidationError`.
  - Apply to every `key`/`issue_key`/`epic_key`/`parent` in `jira_service.py`; to `project_key` in `get_issue_types` and `get_issues_bulk` (which today interpolates it into JQL and the `createmeta` query string).
  - Tests: `../../rest/api/3/myself`, `RET-1/../x`, `RET OR 1=1`, empty, unicode, 10 000 chars — all refused, no request. **AC-6**
  - **Done when:** parametrised test covers every issue-key tool.

- [ ] **T-9** `S` **Stop leaking Jira bodies and secrets.** *(SEC-2, SEC-6 · DEF-6)*
  - `_request` raises `JiraApiError(status, message)`; `message` built from Jira's `errorMessages`/`errors`; raw body → `logger.debug` only.
  - Test: a mocked 500 HTML body and a mocked 400 containing the Basic-auth header value never appear in the raised text.
  - Audit that `JIRA_API_TOKEN` is never formatted into any log/exception (grep + test).
  - **Done when:** the leak tests pass. *(Introduces the exception T-18 builds on.)*

- [ ] **T-10** `M` **Timeouts and read-only retry.** *(NFR-1, NFR-2 · DEF-2 · R3)*
  - `JIRA_CONNECT_TIMEOUT` (5), `JIRA_READ_TIMEOUT` (30), `JIRA_MAX_RETRIES` (2) — all with blank-safe parsing (see T-15).
  - `_request(..., retry: bool)`; `get()` ⇒ `True`; `post()/put()` ⇒ `False`, no override.
  - Tests: GET timeout×2 then 200 ⇒ success, 3 calls. POST timeout ⇒ **exactly 1** call. GET 503 ⇒ 1 call. GET connection error ×3 ⇒ `CONNECTION_ERROR`. **AC-9**
  - **Done when:** the four tests pass and `time.sleep` is patched so the suite stays fast.

- [ ] **T-25** `S` **Scheme-check outbound links.** *(SEC-5 · DEF-11)* `addRemoteLink`, `addCommentWithLinks`: only `http`/`https`; each link needs `text` and `url`. Tests: `javascript:`, `file:`, missing `text`.

---

## M2 — Correctness

- [ ] **T-11** `S` **Honour `max_results` and `fetch_all` in `jira-getIssuesBulk`.** *(FR-4 · DEF-5)* Truncate to exactly `max_results`; `fetch_all=false` ⇒ one page. Replace the `"-" in key` heuristic with the T-8 validators. Tests with a 3-page fake. **AC-7**
- [ ] **T-12** `M` **Fix bulk-create attribution and success flag.** *(FR-5 · DEF-13 · R4)* Map results to inputs by Jira's `failedElementNumber`/response order, not `issues[len(created)]`. `success` is `false` only when nothing was created; `errors` always listed. Tests: middle item rejected; all rejected; all OK. **AC-8**
- [ ] **T-13** `S` **`jira-getIssue` and bulk/search tolerate a null priority.** *(FR-3 · DEF-7)* `(fields.get("priority") or {}).get("name")`. Test: issue with `priority: null`.
- [ ] **T-14** `M` **Per-project epic-field cache; don't poison on failure.** *(FR-22 · DEF-12 · R7)* Today `_custom_fields_loaded = True` is set *before* the request, so one failed `/field` call permanently disables epic handling; and the cache is global although projects differ. Set the flag only on success; key detection by project (via `createmeta` field list or `/field` + project scope). Tests: first call 500 then 200 ⇒ second call loads; two projects of different flavour.
- [ ] **T-26** `S` **Make `_readable_desc` honest.** *(FR-20)* Replace bare `except:`; walk nested ADF nodes (lists, headings, code blocks) so descriptions aren't truncated to top-level paragraphs. Tests with a bullet list and a heading.

---

## M3 — Config & ops

- [ ] **T-15** `S` **Blank-safe config, fail-fast, one URL form.** *(CFG-4, 5, 6 · DEF-8, 9, 10 · R8)*
  - `_env(name, default)` treats `""` as unset; use it for `JIRA_PORT`, timeouts, `LOG_LEVEL`.
  - `run_server.py`: use `config.JIRA_PORT` (today `int(os.getenv("JIRA_PORT"))` raises `TypeError` when unset).
  - Startup validation: missing `JIRA_URL`/`JIRA_USERNAME`/`JIRA_API_TOKEN` ⇒ raise with the variable name. Move `JiraService()` out of module import time in `jira_tools.py`.
  - `JIRA_URL = value.rstrip("/")` once.
  - Dockerfile: `EXPOSE` and `--port` from `JIRA_PORT` (default 9002).
  - Tests: **AC-10** (blank port ⇒ 9002; missing URL ⇒ named error).
- [x] **T-15a** `S` **Remove import-time `JiraService` construction.** *(sub-task of T-15 — only its "move `JiraService()` out of module import time" bullet; DEF-9 · scope and design chosen by the human)*
  - **Design (guarded initialization):** `_jira = None` at module level; `register_tools(mcp)` builds the service only when `_jira` is still `None`. Existing module-level name `_jira`, `register_tools(mcp)` signature, the 13 handler bodies and the `patch.object(jira_tools, "_jira", …)` test convention are unchanged.
  - **Acceptance:** importing `src.tools.jira_tools` constructs no `JiraService`; the first `register_tools()` call constructs exactly one; repeated calls construct none; a pre-set or patched `_jira` is left alone; every one of the 13 tools reaches the service built at registration; registration goldens, tool contract and 13 schemas unchanged.
  - **Not in scope (stays in T-15):** blank-safe config, `JIRA_PORT`/`run_server.py`/Dockerfile, startup validation, `JIRA_URL` normalisation, AC-10.
  - **Done** — `tests/test_service_lifecycle.py` (7 tests; the four that assert the new behaviour failed against the old code for the intended reasons); evidence in `REPORT.md` §9. **Parent T-15 remains open.**
  - **Known limitation, accepted by the human:** the service is still module-level singleton state, and importing `src.servers.server` still constructs it because `server.py` calls `register_tools` at module level. Explicit injection (`register_tools(mcp, service)`, built in `server.py`) is to be evaluated with T-15's startup-validation work.
- [ ] **T-16** `S` **Prune dependencies and metadata.** *(SEC-7)* Remove `agent-framework`, `agent-framework-foundry`, `httpx2`, and `mcp[cli]` unless a test proves they're needed; fix `description` ("unchanged from GCP, not ADK-specific code"); regenerate `uv.lock`; re-run `pip-audit` + Trivy. **Done when:** `uv run pytest` still green and the lock has fewer packages.

---

## M4 — Error contract & logging

- [ ] **T-18** `M` **One error contract.** *(ERR-1…3, FR-19 · DEF-14)*
  - `guarded` decorator in `jira_tools.py` mapping `JiraValidationError`, `JiraApiError(status)`, `Timeout`, `ConnectionError` → `ToolError("<CODE>: …")`.
  - Bulk tools: stop returning `{"success": false, "error": …}` as a successful result; raise instead. Per-item errors inside a *partially successful* bulk create remain in the result.
  - Apply to **all 13** tools (eight have no handling today).
  - Tests: one table-driven test, 13 tools × {400, 401, 403, 404, 409, 429, 500, timeout}. Add a CHANGELOG line (R5).
- [ ] **T-19** `M` **Delete all 34 `print()` calls.** *(NFR-5 · DEF-3 · R6)* Replace with `logger.debug` of *non-content* facts (key, counts, durations). `jira_tools.create_issue` and `create_issues_bulk` currently print every summary, description and the raw payload. Add a static guard test (`print(` under `src/` fails) next to the no-default-project guard. **AC-12**
- [ ] **T-27** `S` **Stop echoing comment text** in `jira-addComment`'s result. *(FR-7)*

---

## M5 — Tests & CI

- [ ] **T-17** `L` **Cover the untested surface.** *(NFR-6, FR-15, FR-17)* Today `jira_service.py` is 59% and `config_reader.py` 73%. Add tests for: `updateIssue` (incl. "Nothing to update", invalid priority), `updateLabels`, `addRemoteLink` (TestRail branch), `addAttachment` (base64 happy path, invalid base64, both/neither argument), `linkIssueToEpic` (both flavours), `addComment`, `addCommentWithLinks`, `getIssue` (with/without parent), `searchIssues` pagination + loop guard + `max_results`, `getIssuesBulk` epic mode + not-an-epic, `register_tools` with `ENABLED_JIRA_TOOLS` (**AC-11**), `/mcp/jira/health`, `AppConfigReader` (mock `load`).
- [ ] **T-20** `S` **Coverage gate.** *(NFR-6)* `pytest --cov=src --cov-fail-under=85` in CI. Don't lower it to get green.
- [ ] **T-21** `M` **Contract test.** *(plan §3)* Commit `scripts/gen_openapi.py` (builds `openapi.yaml` from `Client.list_tools()`); a test regenerates in memory and fails if it differs from the committed file; another validates it with `openapi-spec-validator`. Also assert tool-name set == `x-mcp-tools` names.
- [x] **T-29** `S` **Hermetic test configuration.** *(NFR-6 · CLAUDE.md "No network, ever")* `config.get_config()` prefers Azure App Configuration over env vars, so a populated `.env` (`AZURE_APPCONFIG_ENDPOINT`) made every test run read Azure and replace the fake Jira settings. `tests/__init__.py` now sets `AZURE_APPCONFIG_ENDPOINT=""` before any import; production config code is unchanged. Guard: `tests/test_config_hermeticity.py` (fresh interpreter, emulated populated `.env`, Azure entry points stubbed). **Done:** guard fails without the fix line and passes with it; evidence in `REPORT.md` §9. *Found by the post-modularization audit; do before P2.3.*
- [ ] **T-22** `S` **CI hardening.** *(R9)* Trigger on `pull_request` to `develop`/`main` (CI job only; deploy stays on push); pin `trufflehog` and `trivy-action` to a release/SHA; add `--cov`; use `Tool.input_schema` in tests (the deprecation warning in `test_jira_tools_project_key.py:58`); review each `ruff` ignore in `pyproject.toml` and remove those no longer needed.

---

## M6 — Docs & decisions  `[needs a human]`

- [ ] **T-23** `S` **Write `README.md`** (currently one line) — layout, run locally, tool table, config precedence, security note, Docker, link to these documents. Fix `.env.example`: add `ENVIRONMENT`, `JIRA_ATTACH_ROOT`, timeout/retry variables; mark which can be blank.
- [ ] **T-24** `S` **Decide SEC-1** `[blocked: Q-2]` Network-only, gateway authoriser, or per-user credentials. Record the decision in `spec.md` and flip SEC-1 from UNRESOLVED.
- [ ] **T-28** `S` **Resolve Q-1, Q-3, Q-4, Q-5** `[blocked]` and update FR-1/FR-5, SEC-3, FR-21 accordingly.

---

## P2 — Service modularization  `[needs a human: approval gate]`

Goal: split `src/services/jira_service.py` (847 lines, one 20-method class) into focused
modules **without changing behaviour**. Pure moves only — no defect fixes, no merging of
duplicate code, no new error types, no payload/URL/log-text changes.

**Prerequisites (recorded, not bypassed)**
- `spec.md` has no requirement for this refactor and is human-owned. A human either approves it as a
  non-functional change or adds an NFR; Claude does not edit `spec.md` to justify it.
- `CLAUDE.md` gates: each P2 task starts only on the word `proceed`; the characterization test is
  written and seen **passing against the current code** before any code moves (the usual
  "failing test first" does not apply to a pure move — the proof is that the same tests pass before
  and after).
- Cite `P2.n` in tests, commits and PR (`refactor(services): extract adf helpers (P2.1)`).

**Verified facts the plan relies on** (checked against the code, not the earlier assessment)
- Every Jira call goes through `JiraService._request` (21 call sites) → `self.session.request` (line 42).
  Tests mock `requests.Session.request` at class level (`tests/_mock_jira_api.py`), so they stay valid as long
  as the session is still a `requests.Session`.
- No test or other module references any private helper (`_as_rich_text`, `_readable_desc`, `_request`,
  `_load_custom_fields`, `_epic_*`). Tests construct `JiraService()` directly and call public methods;
  tools hold a module-level `_jira = JiraService()` and call 13 public methods.
- ADF *builders*: `_as_rich_text` (called at lines ~124, 170, 762), plus inline duplicates in `add_comment` (~297) and
  `add_comment_with_links` (~384). `_readable_desc` is an ADF *reader* (called ~408, 580, 672).
- Epic-field cache: `_epic_name_field`, `_epic_link_field`, `_custom_fields_loaded`, loaded by
  `_load_custom_fields` from `create_issue` (~104), `link_issue_to_epic` (~275), `create_issues_bulk` (~729).
- `get_issue_types`/`get_priorities` are called by `create_issue`, `update_issue`, `create_issues_bulk`.
- Methods carry `@log_method_calls`; the logger name is the literal `"jira-mcp-server"`. Moved code keeps both so log output is unchanged.
- **Coverage gap:** `get_issues_bulk` epic branch, `_readable_desc`, `add_comment*`, `update_*`, `link_issue_to_epic` and
  `search_issues` pagination have no tests today (T-17). Characterization tests are therefore part of each task.

**Rules for every P2 task:** `JiraService` public method names, signatures and return strings unchanged;
tool schemas unchanged (compare `list_tools()` output byte-for-byte before/after); `services` still never
imports FastMCP; `ruff` clean with no new ignores; `pytest` green; coverage not lower; `REPORT.md` gets real output.

- [x] **P2.1** `S` **Extract ADF/rich-text helpers → `src/services/adf.py`.** *(FR-20 · NFR-4 · done — evidence in `REPORT.md` §9)*
  - Move `_as_rich_text` and `_readable_desc` as module functions; `JiraService._as_rich_text` / `_readable_desc` stay as one-line delegates so call sites and any external patching keep working.
  - Move the inline `doc` literals in `add_comment` and `add_comment_with_links` **only as-is** (e.g. `build_comment_body`, `build_comment_with_links_body`) — keep their exact structure; do **not** route them through `_as_rich_text` (that is a separate, approved-later consolidation).
  - Do not fix `_readable_desc`'s bare `except:` or nesting (T-26).
  - Tests first (pass before and after): exact JSON equality for `_as_rich_text("x")`, the `add_comment` and `add_comment_with_links` request bodies (via `call_log`), `_readable_desc` on simple paragraph, absent, and malformed description.
  - **Done when:** request bodies for `createIssue`, `updateIssue`, `addComment`, `addCommentWithLinks`, `createIssuesBulk` are identical to baseline and `adf.py` imports nothing but stdlib/typing.

- [x] **P2.2** `M` **Extract HTTP transport → `src/services/jira_client.py`.** *(NFR-1, NFR-2, SEC-6 context · done — evidence in `REPORT.md` §9)*
  - Assess first, then move `session` creation, auth, default headers and `_request` into a `JiraClient`; `JiraService` holds one and keeps `_request` as a delegate. The session must remain a `requests.Session` created per service instance, so the class-level test mock still applies.
  - Preserve verbatim: URL = `config.JIRA_URL + path`, one call to `session.request(method, url, **kwargs)`, `RuntimeError("Jira API error {status}: {text}")` on `not resp.ok`, no timeout and no retry (none exist today), `Content-Type` header handling for attachments (`None` for multipart), `X-Atlassian-Token`.
  - Characterization tests: a 4xx and a 5xx raise the same `RuntimeError` text; request order and count for `createIssue` and `transitionIssue`; auth tuple and `Content-Type` header on the session.
  - **Sequencing:** land **before** T-9 (`JiraApiError`), T-10 (timeouts/retry) and T-15 so they edit one small file. If a human prefers those first, re-plan P2.2 against the new `_request`.
  - **Done when:** every test passes unmodified, `call_log` sequences are identical for all 13 tools, and `jira_service.py` no longer imports `requests`.

- [x] **P2.3** `M` **Extract issue metadata and epic-field cache → `src/services/fields.py`.** *(FR-14, FR-22 · done — evidence in `REPORT.md` §9)*
  - Move `get_issue_types` (per project, **every call, no global cache** — FR-14), `get_priorities`, and the epic-field state with `_load_custom_fields`.
  - Preserve **exactly** the current cache semantics, including the flaw: `_custom_fields_loaded = True` is set before the request succeeds and the cache is process-wide per service instance. **DEF-12 / T-14 is excluded**; a characterization test pins the current behaviour (first `/field` call fails ⇒ later calls do not retry) and is flipped by T-14, not here.
  - Keep `JiraService._epic_name_field` / `_epic_link_field` readable as properties if any caller still reads them.
  - Tests: `createmeta` called on every `create_issue`; `/field` called once across repeated calls; team-managed fallback (no Epic fields) vs company-managed; `linkIssueToEpic` both flavours.
  - **Done when:** call counts per endpoint are identical to baseline in the characterization tests.

- [x] **P2.4a** `S` **Map `get_issues_bulk` (analysis only, then characterization tests).** *(FR-4, FR-23 · done: map in P2 notes below, pinned by `tests/test_service_golden.py`)*
  - Produce a written map in this file's notes or `plan.md`: validation → key-type detection (`"-" in key`) → epic verification GET → JQL build → paginated `/search/jql` loop (guards) → field formatting → JSON result, including the `{"success": false}` early return.
  - Add tests with a multi-page fake (project mode, epic mode, non-epic key, loop guard, page cap) that **pin current behaviour including DEF-5** (`max_results` and `fetch_all` ignored).
  - **Done when:** the map and tests are reviewed. No code moves in this task.

- [x] **P2.4b** `S` **Map `create_issues_bulk`.** *(FR-5 · done: map in P2 notes below, pinned by `tests/test_service_golden.py`)* Same as P2.4a: validation up front, per-project type cache, payload build, `/issue/bulk` call(s), result attribution. Tests pin partial success, ordering, request count and the DEF-13 attribution as it behaves today.

- [x] **P2.4c** `L` **Extract bulk operations → `src/services/bulk.py`.** *(FR-4, FR-5, FR-23 · done — evidence in `REPORT.md` §9; later split into `search.py` + `bulk_create.py` by P2.8)*
  - Split into private helpers along the mapped seams (validate, detect, fetch page, format issue, build payload, format result) — **moves only**: same HTTP calls, same count and order, same batching, same result order and JSON, same early-return shapes.
  - `JiraService.get_issues_bulk` / `create_issues_bulk` remain as delegates with identical signatures.
  - Do not touch the hyphen heuristic (T-8/T-11), `max_results`/`fetch_all` (T-11), attribution/`success` flag (T-12), `print()` (T-19).
  - **Done when:** P2.4a/b tests pass unchanged and `call_log` for each scenario is identical before and after.

- [x] **P2.5** `S` **Facade and compatibility audit.** *(FR-1…13, 15, 18 · NFR-4 · done — evidence in `REPORT.md` §9; `openapi.yaml` needs no regeneration because the tool schemas are byte-identical; the contract test is T-21)*
  - `JiraService` exposes the same public methods (diff the `inspect` signatures against a baseline file); `jira_service.py` is delegation plus the non-extracted single-issue operations.
  - Tool-surface check: `list_tools()` dump (names, descriptions, input schemas) byte-identical to baseline; exact set of 13 names; `tests/test_package_layout.py` green.
  - Import and layering: `tools` imports no `requests`; `services` imports no `fastmcp`; no cycles; the old import paths used by tests (`src.services.jira_service.JiraService`) still work.
  - Docs: update `CLAUDE.md` "Where things live" and the `plan.md` module list; tick the P2 boxes; `REPORT.md` with real output.
  - **Done when:** the Definition of Done checklist in `CLAUDE.md` is complete.

- [x] **P2.6** `M` **Extract single-issue operations and search → `src/services/issues.py`.** *(FR-1…3, 6…10, 14, 23 · done — scope added by the human: "complete all remaining justified service-layer modularization")* `create_issue`, `update_issue`, `update_labels`, `add_remote_link`, `link_issue_to_epic`, `add_comment`, `add_comment_with_links`, `get_issue`, `search_issues` moved verbatim into `IssueOperations` (`search_issues` later moved to `search.py` by P2.8). Comments and links stay here: each is a few lines over the shared request path and ADF builders, so separate `comments.py` / `links.py` modules would only forward calls.
- [x] **P2.7** `S` **Extract `transitions.py` and `attachments.py`.** *(FR-12, FR-13 · done — same authorisation as P2.6)* Both are single-purpose algorithms with their own validation. `attachments.py` is isolated because T-7 (path confinement) changes exactly that code.

- [x] **P2.8** `M` **Split by dependency profile: `search.py` and `bulk_create.py`.** *(FR-4, FR-5, FR-23 · scope added by the human: "review the remaining service modules ... complete any justified modularization")*
  - **Inspected** (AST, not names): `bulk.py` 374 lines = `get_issues_bulk` (193) + `create_issues_bulk` (151); `issues.py` 299 lines = 9 methods, of which `search_issues` (68) is the only one that needs neither field metadata nor ADF builders.
  - **Finding:** `get_issues_bulk` needs only `_request` and the description reader; `create_issues_bulk` needs `JiraFields`, `build_rich_text`, `config` and validation. They share no code and change for different reasons (T-8/T-11 vs T-12). `search_issues` and `get_issues_bulk` are the same `/search/jql` token-paginated read with duplicate-key and page-cap guards.
  - **Proposal:** `search.py` → `IssueSearch(request)` with `search_issues` + `get_issues_bulk` (JQL-driven reads); `bulk.py` → `bulk_create.py` → `BulkIssueCreator(request, fields)` with `create_issues_bulk`; `issues.py` keeps create/update/labels/get/comments/links. Whole methods move verbatim; facade delegates change target only.
  - **Deliberately retained:** the two long methods (193 / 151 lines) are *not* decomposed. Splitting their control flow (prints, early returns, per-index error handling) is a restructuring that T-11, T-12 and T-19 will do with their own tests; doing it here would mix a refactor with defect work. `issues.py` keeps comments/links (4 methods, ~50 lines over the shared request path): separate modules would only forward calls. The two pagination loops are *not* merged: their guards differ (50 vs 101 calls, sleep, truncation).
  - **Must stay unchanged:** request order and payloads, return strings, exceptions, stdout and log lines, `/search/jql` pagination and both safety caps, DEF-5 (`max_results`/`fetch_all`), the hyphen heuristic, DEF-13 attribution, public method signatures, facade logging, 13 tool schemas.
  - **Characterization already in place:** `tests/test_service_golden.py` — 6 search, 10 bulk-read and 12 bulk-create scenarios plus the 15 tool calls, generated from the original code. New focused tests only for the seams: each new module runs with nothing but a fake request (no facade, no HTTP); import allow-list updated in `tests/test_service_modules.py`.
  - **Done when:** golden + full suite green before and after, Ruff clean, schemas byte-identical, AST comparison shows the moved methods unchanged, coverage re-measured with the documented command. **Done** — evidence in `REPORT.md` §9; `bulk.py` no longer exists (it was split by this task).

- [x] **P2.9** `S` **Tool layer: contract tests first, one justified extraction → `src/tools/bulk_issue_input.py`.** *(FR-5, FR-18 · scope added by the human: "Phase 2: jira_tools.py modularization and final architecture audit")*
  - **Inspected:** `jira_tools.py` 354 lines = `register_tools` + 13 `_register_*` functions whose handlers are 5–17 lines and call exactly 13 distinct facade methods; the one real logic block is the 38-line `createIssuesBulk` argument normalization. Module state: `_jira = JiraService()` (T-15).
  - **Tests first:** `tests/test_tool_contract.py` + `tests/golden/tool_contract.json`, generated from the original code (git `b6fc26d`): full definition of all 13 tools in registration order, service method and exact arguments per tool (18 calls), error mapping of every tool (26), `createIssuesBulk` normalization (14 cases incl. stdout). Passed against the unchanged tool layer, and fails under deliberate mutations of a description, the normalization and a print.
  - **Extracted:** the normalization loop moved verbatim (AST-identical) into the pure function `normalize_bulk_issues`; the handler keeps its bracketing `print()` calls, `except` clauses and service call. `tests/test_bulk_issue_input.py` checks the function against the original handler's outputs from the golden file.
  - **Deliberately not done:** splitting the 13 registrations into group modules. Handlers are already thin and uniform; groups would have to share the `_jira` singleton, which T-15 is about to replace, and the registration order (the `ENABLED_JIRA_TOOLS` default list differs from the dict order) is part of the contract. The duplicated tool-name lists in `register_tools` are not merged for the same reason. The `JiraValidationError` → `ToolError` mapping (5 of 13 handlers) is T-18, not this task.
  - **Done when:** contract + golden + full suite green, Ruff clean, 13 schemas byte-identical, coverage re-measured, hermeticity audited. **Done** — evidence in `REPORT.md` §9.

- [x] **P2.10** `S` **Tool-layer review: no further extraction; registration behaviour pinned.** *(FR-15, FR-18, AC-11 · scope: "determine whether `jira_tools.py` should be further modularized")*
  - **Inspected:** responsibilities of `jira_tools.py` (logging bootstrap, `_jira` instance, enabled-tools resolution and selection loop, 13 thin handlers, error translation in 5 of 13 handlers) against the actual T-15 and T-18 definitions. T-15 moves `JiraService()` out of import time; T-18 adds `guarded` "in `jira_tools.py`" around all 13 handlers.
  - **Decision: no extraction.** The only code with independent behaviour is the enabled-tools resolution and selection loop (~45 lines); extracting it would leave the name → `_register_*` table in `jira_tools.py` (moving it would create an import cycle) and split one function into three pieces with no new testability — it is already pinned end to end. Handlers stay together because they share the `_jira` instance (T-15) and will all receive the same decorator (T-18). Error translation and instance lifecycle belong to T-18 and T-15 and are not pre-empted.
  - **Effective registration order** is the order of the enabled list (the 13-name default or `ENABLED_JIRA_TOOLS`), not the lookup table's order; the table's order only appears in the unknown-tool warning text.
  - **Added:** `tests/test_tool_registration.py` + `tests/golden/tool_registration.json`, generated from the original code (git `b6fc26d`): 10 `ENABLED_JIRA_TOOLS` cases (default, empty, absent, subsets in both orders, unknown names, duplicates, all 13 reversed) recording the registered tools in order and the logger output. It passed against the unchanged code and fails under mutations of the default order and the warning level. This closes the one contract area (FR-15 / AC-11) the other goldens did not cover.
  - **Revisit** the tool layer once T-15 and T-18 have landed: a `guarded` decorator and an injected service may then justify a small shared module.

**P2 notes — responsibility maps** (what the golden scenarios pin)
- `get_issues_bulk`: validate non-empty string → detect `"-" in key` (epic heuristic, T-8/T-11) → for an issue key, GET the issue and require type `epic` (else `{"success": false}`) → JQL `project = K` or `(key = K OR parent = K)`, `ORDER BY key ASC` → token-paginated `/search/jql`, 100 per page, stops on an empty page, repeated keys, `isLast`/no token, `max_results` reached at a page boundary, or more than 100 calls; `time.sleep(0.1)` between pages → per-issue formatting → `{"success": true, …}`; any exception becomes `{"success": false}`. `fetch_all` is ignored (DEF-5).
- `create_issues_bulk`: validate that every item has a string `project_key` before any request → load epic fields once → priorities once → per item: summary required, issue types looked up once per distinct project, type then priority validated, fields built (default priority `Low`, epic name only when the field exists, labels filtered, parent) → one POST `/issue/bulk` → results attributed by `issues[len(created)]` (DEF-13) → `errors` from `failedElementNumber`; a validation error mid-list returns `{"success": false, "failed_at_index": i}` with nothing sent.

**Explicitly excluded from P2 (tracked elsewhere — do not fold in)**
| Item | Task |
|---|---|
| Typed exception hierarchy, `JiraApiError`, `guarded`, ERR-1…3 | T-9, T-18 |
| `print()` removal / logging cleanup | T-19 |
| Epic-field cache defect (flag set before success, global scope) | T-14 / DEF-12 |
| `getIssuesBulk` `max_results`/`fetch_all`, hyphen heuristic | T-11 / DEF-5 |
| Bulk-create attribution and `success` flag | T-12 / DEF-13 |
| Key validation, timeouts and retry, `_readable_desc` honesty | T-8, T-10, T-26 |
| Consolidating the three hand-built ADF literals into one | needs separate approval after P2.1 |
| Moving `JiraService()` out of import time | T-15 |

**P2 order and rationale:** P2.1 first (pure functions, no state, lowest risk) → P2.2 (central choke point; do it before T-9/T-10/T-15 so
they change one file) → P2.3 (state; depends on the client) → P2.4a/b (analysis and tests only, because the bulk methods are the
riskiest and least tested) → P2.4c (the actual move) → P2.5 (audit).

---

## Dependency order

```
T-9 ─┬─> T-10 ─┬─> T-18
     │         └─> T-17
T-8 ─┼─> T-11
     └─> T-7        T-15 ──> T-10 (blank-safe parsing), T-20
T-12, T-13, T-14, T-26, T-25, T-27, T-19  (independent; each after its tests)
T-17 ─> T-20 ─> T-22          T-21 after T-18 (schemas settle)
T-29 (hermetic tests) ─> P2.3 and later P2 tasks
T-23, T-24, T-28  last
```

## Progress

| Milestone | Tasks | Done |
|---|---|---|
| M0 Baseline | T-1…6 | **6 / 6** |
| M1 Safety | T-7, 8, 9, 10, 25 | 0 / 5 |
| M2 Correctness | T-11, 12, 13, 14, 26 | 0 / 5 |
| M3 Config & ops | T-15 (T-15a done), 16 | 0 / 2 |
| M4 Error & logging | T-18, 19, 27 | 0 / 3 |
| M5 Tests & CI | T-17, 20, 21, 22, 29 | 1 / 5 |
| M6 Docs & decisions | T-23, 24, 28 | 0 / 3 |
| P2 Service and tool modularization | P2.1, 2, 3, 4a, 4b, 4c, 5, 6, 7, 8, 9, 10 | **12 / 12** |
| T-15a (sub-task of T-15) | T-15a | **1 / 1** |
| **Total** | **42** | **20 / 42** |
