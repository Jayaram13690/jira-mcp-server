# Jira MCP Server — Verification Report

| | |
|---|---|
| **Document** | `REPORT.md` — Phase 5 (Verify) |
| **Subject** | `pdlc-jira-mcp-server`, branch `feature/jira_mcp_phase2` |
| **Verified against** | `spec.md` v1.0 · `openapi.yaml` v1.0.0 |
| **Type** | **Baseline report.** No code was changed. It records what the code does today against the spec, so M1–M6 have a measured starting point. |
| **Re-run** | After every milestone. Replace the numbers; keep the structure. |

## 1. Verdict

**The baseline is sound at its core and not yet production-ready.**

- The defining rule — *no default project* (FR-14) — is implemented and genuinely well guarded.
- `jira-transitionIssue` is the model tool: fully specified, idempotent, thoroughly tested.
- **One High finding:** `jira-addAttachment` can read any file the server process can read and upload it to Jira (DEF-1).
- Six of the 13 tools have **no behavioural test** at all; overall coverage is **67%** against an 85% target.
- Failure behaviour is inconsistent across tools; there are no timeouts; 34 `print()` calls bypass logging and write issue content to stdout.
- A fresh clone using the shipped `.env.example` **fails at startup** (DEF-8).

| | Count |
|---|---|
| Requirements in spec | 13 tool FRs + 11 cross-cutting FRs + 7 CFG + 7 NFR + 7 SEC + 3 ERR = **48** |
| ✅ Verified by a behavioural test | **3** (FR-13, FR-14, FR-24) |
| 🟡 Implemented, partly tested | **21** |
| ⚪ Implemented, no behavioural test | **9** |
| ❌ TARGET — not implemented (each has a task) | **15** |
| Defects found | **16** — 1 High · 10 Medium · 5 Low |

## 2. Evidence

**Environment.** Python 3.12.3 (project requires ≥ 3.11; CI uses 3.11), `fastmcp 3.4.4` / `mcp 1.30.0` — the versions pinned in `uv.lock`. A first run on current releases (`fastmcp 4.1.0`) gave identical results plus one deprecation warning (`Tool.inputSchema`). Tool schemas were byte-identical on both versions.

```text
$ pytest tests/ -q --cov=src --cov-report=term
33 passed, 10 subtests passed in 4.72s

Name                                Stmts   Miss  Cover
src/jira/config/config.py              14      0   100%
src/jira/config/config_reader.py       15      4    73%
src/jira/servers/server.py             23      5    78%
src/jira/services/jira_service.py     401    165    59%
src/jira/tools/jira_tools.py          158     38    76%
src/jira/utils/log_helper.py           44      3    93%
TOTAL                                 656    215    67%

$ ruff check .
All checks passed!
```

```text
openapi.yaml : valid OpenAPI 3.1 (openapi-spec-validator) · 13 tools · 38 schemas
tool names   : set(x-mcp-tools) == set(live tools/list)        → identical
required args: per-tool `required` lists == live schemas        → identical (13/13)
print( under src/ : 34        timeout= under src/ : 0       mask_error_details : not set
JIRA_PORT=""  →  int("") in config.py  →  ValueError at import
```

**Not run** (no environment): the Docker build, Trivy, pip-audit, trufflehog, the Azure deploy, and any call to a real Jira site. Everything above used the project's own mocked Jira (`tests/_mock_jira_api.py`). *Findings in §4 are from reading the code and, where stated, executing it; none were reproduced against live Jira.*

## 3. Traceability — requirement → code → test

**Result key:** ✅ verified by a behavioural test · 🟡 implemented, only partly tested · ⚪ implemented, **no** behavioural test · ❌ TARGET, not implemented.

### 3.1 Tools

| ID | Tool | Code | Test evidence | Result |
|---|---|---|---|---|
| FR-1 | `jira-createIssue` | `create_issue` | `project_key` required/blank/exact use (service + tool). Priority default, issue-type validation, labels, parent, epic name **not** tested | 🟡 |
| FR-2 | `jira-updateIssue` | `update_issue` | Only a schema check that it has no `project_key`. "Nothing to update", priority validation untested | ⚪ |
| FR-3 | `jira-getIssue` | `get_issue` | One service test (no project involved). Parent branch, null priority untested (**DEF-7**) | 🟡 |
| FR-4 | `jira-getIssuesBulk` | `get_issues_bulk` | One test: project mode, first page, JQL text. Epic mode, pagination, `max_results`, `fetch_all` untested — and the last two are ignored (**DEF-5**) | 🟡 |
| FR-5 | `jira-createIssuesBulk` | `create_issues_bulk` | Pre-flight `project_key` validation, per-issue project keys. Parsing of string/wrapped entries, partial failure untested; **DEF-13** | 🟡 |
| FR-6 | `jira-linkIssueToEpic` | `link_issue_to_epic` | Schema check only | ⚪ |
| FR-7 | `jira-addComment` | `add_comment` | One call asserted (works without `project_key`) | 🟡 |
| FR-8 | `jira-addCommentWithLinks` | `add_comment_with_links` | Schema check only | ⚪ |
| FR-9 | `jira-searchIssues` | `search_issues` | JQL passed through unchanged, no project injected. Multi-page, loop guard, cap untested | 🟡 |
| FR-10 | `jira-updateLabels` | `update_labels` | Schema check only | ⚪ |
| FR-11 | `jira-addRemoteLink` | `add_remote_link` | Schema check only | ⚪ |
| FR-12 | `jira-addAttachment` | `add_attachment` | Schema check only. **DEF-1** | ⚪ |
| FR-13 | `jira-transitionIssue` | `transition_issue` | **9 tests:** resolved ID used, case-insensitive, `already_done` makes no POST, no-transition error lists options, Jira errors propagate (lookup, POST, issue-not-found), blank args make no call, schema | ✅ |

### 3.2 Cross-cutting

| ID | Result | Evidence / note |
|---|---|---|
| FR-14 | ✅ | `test_no_default_project.py` (3 static guards) + 9 service tests + 6 tool tests, incl. "zero calls on refusal", "stray `JIRA_PROJECT_KEY` ignored", mixed projects in one bulk. **Strongest area.** |
| FR-15 | ⚪ | `register_tools` reads `ENABLED_JIRA_TOOLS`; no test for subset, unknown name, or empty (AC-11) |
| FR-16 | 🟡 | Every tool test runs through the in-memory `Client(server.mcp)`; the `/mcp/jira` HTTP mount itself is not exercised |
| FR-17 | ⚪ | Route exists (`server.py:33`); lines 33–34 uncovered |
| FR-18 | 🟡 | Tags present on every tool (read from live `tools/list` here); no test asserts it |
| FR-19 | 🟡 | Mixed (see DEF-14) |
| FR-20, 21 | 🟡 | Exercised incidentally; no focused test; `_readable_desc` bare `except` (DEF-15) |
| FR-22 | ⚪ | Not tested; **DEF-12** |
| FR-23 | 🟡 | First page only |
| FR-24 | ✅ | Transition tests prove Jira errors surface unmodified |
| CFG-1…3, 7 | 🟡 | `config.py` 100% covered by import; `config_reader.py` Azure branch (lines 24–45) untested |
| CFG-4, 5, 6 | ❌ | DEF-8, 9, 10 |
| NFR-3 | 🟡 | All tools use `asyncio.to_thread` (code review only) |
| NFR-4 | 🟡 | `log_helper.py` 93% covered incidentally; format not asserted |
| NFR-1, 2, 5, 6 | ❌ | DEF-2, —, DEF-3, 67% < 85% |
| NFR-7 | 🟡 | Dockerfile correct in design (comment explains why not `--reload`); port hard-coded to 9002 and not built here |
| SEC-2, 7 | 🟡 | CI has `pip-audit`, trufflehog, Trivy (read, not run); no leak test; unused deps remain |
| SEC-1 | ❌ | Unresolved by design — decision Q-2 |
| SEC-3, 4, 5, 6 | ❌ | DEF-1, 4, 11, 6 |
| ERR-1…3 | ❌ | DEF-14 |

## 4. Defects

Severity: **High** = exploitable or data-exposing · **Med** = wrong result or reliability · **Low** = hygiene.
"How found": **R** = read in code · **X** = executed here.

| ID | Sev | Finding | Where | How | Spec | Task |
|---|---|---|---|---|---|---|
| **DEF-1** | **High** | `file_path` is opened with no confinement. A caller can pass `/proc/self/environ`, a mounted secret, or `../../..` and the server uploads it to Jira, where the caller (or anyone with issue access) reads it back. | `add_attachment`: `os.path.isfile(file_path)` → `open(file_path,"rb")` | R | SEC-3 | T-7 |
| DEF-2 | Med | No timeout on any Jira call. A hung Jira holds a worker thread forever. | `_request`; `timeout` appears nowhere in `src/` | X | NFR-1 | T-10 |
| DEF-3 | Med | 34 `print()` calls. `create_issue` and `create_issues_bulk` print every summary, description and the raw payload to stdout regardless of `LOG_LEVEL`. | `jira_tools.py`, `jira_service.py` | X | NFR-5 | T-19 |
| DEF-4 | Med | Keys are interpolated unvalidated into URL paths and JQL. `get_issues_bulk` builds `project = {input}`; `get_issue_types` puts `project_key` in a query string. Host is fixed so SSRF is not possible, but a crafted key reaches other Jira endpoints or alters JQL. | `jira_service.py` (throughout) | R | SEC-4 | T-8 |
| DEF-5 | Med | `get_issues_bulk`: `fetch_all` is never read; `max_results` stops fetching but never truncates, so `max_results=1` returns a whole page of 100. Epic mode is chosen by "contains `-`". | `get_issues_bulk` | R | FR-4 | T-11 |
| DEF-6 | Med | On any Jira error `_request` raises `RuntimeError(f"Jira API error {status}: {resp.text}")` — the raw body. `mask_error_details` is not set, so FastMCP forwards the message to the agent. | `_request` | R | SEC-6 | T-9 |
| DEF-7 | Med | `get_issue` does `fields["priority"]["name"]`; Jira returns `priority: null` for some projects/schemes → `TypeError`. (`search_issues` already guards this; `get_issue` does not.) | `get_issue` | R | FR-3 | T-13 |
| DEF-8 | Med | `.env.example` ships `JIRA_PORT=` (blank). `load_dotenv` sets it to `""`; `config.py` then raises `ValueError` at import. `run_server.py` also does `int(os.getenv("JIRA_PORT"))` with no default → `TypeError` when unset. | `config.py:66`, `run_server.py` | **X** | CFG-4 | T-15 |
| DEF-9 | Low | No startup validation. Missing credentials are discovered on the first Jira call; `JiraService()` is built at import time in `jira_tools.py`. | `jira_tools.py:36` | R | CFG-5 | T-15 |
| DEF-10 | Low | `JIRA_URL` trailing slash handled in `search_issues` (`rstrip`) but not in the 6 other places that build URLs → `//rest/api/3/...`. | `jira_service.py` | R | CFG-6 | T-15 |
| DEF-11 | Low | `addRemoteLink` / `addCommentWithLinks` accept any URL scheme (`javascript:`, `file:`) and any link dict shape (`KeyError` on missing `text`/`url`). | service | R | SEC-5 | T-25 |
| DEF-12 | Med | `_load_custom_fields` sets `_custom_fields_loaded = True` **before** the request. One failed `/field` call permanently disables epic handling for the process. The cache is also process-global although the code's own comment says flavour is per-project. | `jira_service.py:44-47` | R | FR-22 | T-14 |
| DEF-13 | Med | `create_issues_bulk` attributes each created key to `issues[len(created_issues)]["summary"]` — wrong whenever Jira rejects a non-final item. It also returns `success: true` even when `errors` is non-empty, so an agent concludes everything was created. | `create_issues_bulk` | R | FR-5 | T-12 |
| DEF-14 | Med | Four failure shapes: `ToolError` (5 tools), raw `RuntimeError` (8 tools), `{"success": false}` as a *successful* result (`get_issues_bulk`, `create_issues_bulk`), and unhandled `KeyError`/`TypeError`. An agent cannot reliably distinguish failure from success. | `jira_tools.py`, service | R | ERR-1…3 | T-18 |
| DEF-15 | Low | `_readable_desc` uses a bare `except:` and flattens only top-level paragraphs; lists, headings, code blocks vanish from descriptions. | `_readable_desc` | R | FR-20 | T-26 |
| DEF-16 | Low | `pyproject.toml` carries unrelated packages (`agent-framework`, `agent-framework-foundry`, `httpx2`, `mcp[cli]`) → larger attack surface and image; description reads "unchanged from GCP, not ADK-specific code". README is a single line. | `pyproject.toml`, `README.md` | R | SEC-7 | T-16, T-23 |

### Also noted (not defects)
- `create_issue` silently applies priority `Low` and type `story` when omitted — intended and documented, but invisible to the agent (Q-1).
- `add_comment` echoes the comment text back (FR-7 target: omit).
- CI runs only on push to `develop`; `trufflehog@main` is an unpinned action (T-22).
- `requests.Session` is shared across `to_thread` workers; `requests` does not guarantee thread safety for a shared session. Low risk at current load; revisit with T-10.
- `ruff` ignores seven rule families (`BLE001`, `E722`, `F841`…). "All checks passed" therefore means less than it appears: the ignored rules cover exactly the `except Exception:`, bare `except:` and unused-variable patterns present in DEF-14/15.

## 5. Acceptance criteria status

| AC | Covers | Status |
|---|---|---|
| AC-1 | FR-14 create without project | ✅ passes today |
| AC-2 | FR-14 bulk, one bad entry | ✅ passes today (error names index) |
| AC-3 | FR-13 `already_done`, no POST | ✅ passes today |
| AC-4 | FR-13 no transition, lists options | ✅ passes today |
| AC-5 | SEC-3 attachment confinement | ❌ fails — DEF-1 |
| AC-6 | SEC-4 crafted key | ❌ fails — DEF-4 |
| AC-7 | FR-4 `max_results` | ❌ fails — DEF-5 |
| AC-8 | FR-5 attribution | ❌ fails — DEF-13 |
| AC-9 | NFR-2 retry rules | ❌ no retry/timeout — DEF-2 |
| AC-10 | CFG-4/5 | ❌ fails — DEF-8/9 *(AC-10 first clause reproduced)* |
| AC-11 | FR-15 | ⚪ unverified (probably passes; no test) |
| AC-12 | NFR-5 no content in logs | ❌ fails — DEF-3 |

**4 of 12 pass; 7 fail by design (TARGET); 1 unverified.** A failing acceptance test is the starting point of its task, not a regression.

## 6. Contract check (`openapi.yaml`)
- Validates as OpenAPI 3.1.
- Argument schemas were generated from the live tool schemas; names and required-argument lists match for all 13 tools.
- Result schemas (`*Result`) were written from reading the service code. They are **not** machine-checked against real output until T-21 adds the contract test.
- `x-target-*` markers show constraints the spec requires and the code does not yet enforce (key patterns, `minLength`).

## 7. Recommended next step

Approve `plan.md` and `tasks.md`, then say `proceed` to start **M1**. Suggested order inside M1: **T-9 → T-7 → T-8 → T-10**. If M1 cannot start soon, the cheapest interim mitigation for DEF-1 is to remove `jira-addAttachment` from `ENABLED_JIRA_TOOLS` in the deployed environment.

Decisions waiting on a human: **Q-1** priority default · **Q-2/SEC-1** caller identity · **Q-3** keep `file_path` at all · **Q-4** structured results · **Q-5** read-only preset.

## 8. Sign-off

| Gate | Approver | Date | Decision |
|---|---|---|---|
| Spec accepted | | | |
| Plan accepted | | | |
| Baseline accepted | | | |

## 9. Modularization and test-isolation evidence (P2.1 – P2.9, T-29)

*Added after §8. §1–§8 remain the M0 baseline and were not re-run; the numbers below are from this change set.* All Jira traffic is the project's mock; no real Jira call was made.

**Commands and results**

```text
$ ruff check .
All checks passed!

$ pytest tests/ -q --cov=src          # documented command
132 passed, 252 subtests passed
TOTAL                          777  19   98%      # was 67% at baseline (§2); the coverage gate is still T-20
  below 100%:  src/tools/jira_tools.py      136  3  98%  (27-29 logging-setup handler)
               src/services/jira_service.py  90  4  96%  (21-23 logging-setup handler, 57 private compat delegate)
               src/servers/server.py         23  5  78%  src/config/config_reader.py 15 4 73% (Azure body)
               src/utils/log_helper.py       44  3  93%  every other module 100%
```

Test count by step: 33 (M0 baseline) → 36 → 55 (P2.1) → 79 (P2.2) → 82 (T-29) → 101 (service golden + boundary) → 109 (P2.8) → 120 (P2.9: tool contract + normalization) → 125 (P2.10: registration behaviour) → **132** (T-15a: service lifecycle).
*Coverage measurement note:* 98% (775 statements, 19 missed) in three consecutive runs of the documented command after P2.10; the registration test also covers the unknown-tool branch, which was the only uncovered line in `register_tools`. Before P2.10, 97% was reproduced in every run but one. A single run at the start of the P2.9 work read 91% (73 missed) with the same 109 tests; it did not recur in the 11 coverage runs that followed (7 at 96% before the tool-layer change, 4 at 97% after) and its cause was not determined.

**Final source tree and size** (`wc -l`; original = git `b6fc26d`)

| Module | Lines | Responsibility |
|---|---|---|
| `servers/server.py` | 47 (was 47) | App, health route, `mcp_app` |
| `tools/jira_tools.py` | 317 (was 354) | The 13 tool registrations; thin handlers delegating to the facade; `ENABLED_JIRA_TOOLS` |
| `tools/bulk_issue_input.py` | 54 | `normalize_bulk_issues`: createIssuesBulk argument normalization (pure) |
| `services/jira_service.py` | 144 (was 846) | `JiraService` facade: public API, entry/exit logging, composition, `_dispatch_request` |
| `services/jira_client.py` | 36 | HTTP transport and the `RequestFn` protocol |
| `services/adf.py` | 53 | Pure ADF builders and reader |
| `services/fields.py` | 73 | Issue types, priorities, epic-field cache (DEF-12 preserved) |
| `services/issues.py` | 226 | Create, read, update, labels, comments, links |
| `services/search.py` | 272 | JQL reads: `search_issues`, `get_issues_bulk` |
| `services/bulk_create.py` | 177 | Bulk create across projects |
| `services/transitions.py` | 67 | Status transitions |
| `services/attachments.py` | 59 | Attachments (T-7 lands here) |

`services/` is 846 → 1,107 lines across 9 modules; `tools/` is 354 → 371 across 2.

**13-tool contract — evidence.**
- **Schemas byte-identical.** A byte comparison of name, description and input schema for all 13 tools, taken from the original tree and the current tree, is identical (13 tools, 12,095 bytes).
- **Full definitions identical.** `tests/test_tool_contract.py` compares the complete MCP definition of every tool (including output schema, tags and annotations) and the registration order against `tests/golden/tool_contract.json`, generated from the original code. It also pins, for every tool, the facade method and exact arguments it delegates to (18 calls), the error mapping (26 cases) and the `createIssuesBulk` normalization (14 cases including stdout).
- **Not vacuous.** The contract test passed against the unchanged tool layer, then failed (5 failures) under deliberate mutations of a tool description, the bulk normalization and a `print`; the file was restored byte-for-byte.
- **The extraction is verbatim.** The moved normalization block is AST-identical to the original handler's; the handler's `except` clauses are unchanged. Real `print()` calls in `src/`: 33 in the original, 33 now.

**Architecture and dependency audit.**
- **Layering.** The import graph is acyclic and no lower layer imports a higher one (`servers → tools → services → config/utils/exceptions`). The tools layer imports no `requests` and no service module except the facade (`tests/test_tool_contract.py`); only `jira_client.py` imports `requests`; no service component imports the facade, FastMCP, tools or servers (`tests/test_service_modules.py`).
- **Thin handlers.** The 13 handlers are 5–17 lines and call exactly 13 distinct facade methods. Argument shaping lives in one pure function; all Jira logic is in `services/`.
- **Facade.** The 15 public `JiraService` signatures equal the original (`tests/golden/service_api.json`).
- **Behaviour.** The service golden trace (81 scenarios, 278 HTTP calls, 1,406 log records, generated from the original) passes unchanged; 14 of 16 moved service functions are AST-identical to the originals, the other two differ only by the P2.1 calls into the `adf` builders.
- **Hermetic.** `tests/__init__.py` blanks `AZURE_APPCONFIG_ENDPOINT` before any import. The whole suite (132 tests, re-run after T-15a) was run with every non-loopback connection, connect attempt and DNS lookup turned into a hard failure: 120 passed, 0 attempts recorded; a self-test confirmed the detector refuses and records deliberate outbound attempts (3 of 3). Docker builds from the unmodified `Dockerfile` and the app imports inside the container; the health endpoint returns 200.
- **No unrelated fixes.** Tracked defects are unchanged by design (DEF-2, 3, 5, 6, 12, 13; T-8, T-11, T-12, T-18, T-19, T-25).

**Intentional, documented differences.** (1) Logging: the Entry/Exit/Exception lines of five internal service helpers (`get_issue_types`, `get_priorities`, `_load_custom_fields`, `_as_rich_text`, `_readable_desc`) are not emitted when the extracted components call each other directly; they still are through the facade (pinned). (2) None in the tool layer: stdout, results and errors are identical.

**Environment observations during the audit.** (a) The local `.env` was modified while the work was in progress. As of the final checks it no longer sets `AZURE_APPCONFIG_ENDPOINT` (observed with boolean probes only; values were never read), so a clean offline run is no longer discriminating for T-29 on this machine. The discriminating evidence is the guard test with an emulated populated `.env`, which fails without the fix (2 failures) and passes with it. (b) `src/services/search.py` was rewritten by something other than this work at 16:21:52: its module docstring and header comments were removed and the `search_issues` docstring was re-flowed. A statement-level comparison against the original shows the code is unchanged apart from the intended `self._readable_desc` → `extract_plain_text` rewrite; only documentation text differs. It was left as found. (c) An intermittent "Application Control policy has blocked this file" error from `uv` occurred a few times and passed on retry.

**T-29 — the guard detects the defect.** `tests/test_config_hermeticity.py` runs a fresh interpreter with an emulated populated `.env` (real `dotenv` loader, fake values) and stubs for the Azure entry points.

```text
fix line REMOVED from tests/__init__.py:
  pytest tests/test_config_hermeticity.py -k Populated
  AssertionError: 'https://guard.invalid' != ''          1 failed
fix line RESTORED:
  pytest tests/test_config_hermeticity.py                3 passed
```

**Tool-layer review (P2.10).** No further extraction was justified. `jira_tools.py` (317 lines) holds the logging bootstrap, the `_jira` instance (built on the first registration since T-15a), the enabled-tools resolution and selection loop, and 13 thin handlers; the only independent logic (bulk-input normalization) is already in `tools/bulk_issue_input.py`. Extracting the ~45-line registration function would leave its name → `_register_*` table behind and add no testability, and the handlers will all be touched by T-15 (instance) and T-18 (`guarded`), so those boundaries are left to those tasks. What was added instead is `tests/test_tool_registration.py` + `tests/golden/tool_registration.json` (10 `ENABLED_JIRA_TOOLS` cases, generated from the original code) pinning the effective registration order — the order of the enabled list, not of the lookup table — the unknown-name warning, duplicates and the empty/absent fallbacks; it fails under mutations of the default order and the warning level. No application code changed in P2.10; the 13 schemas remain byte-identical (12,095 bytes) and the import graph is acyclic.

**T-15a — no import-time service construction.** *Before:* `_jira = JiraService()` ran when `src.tools.jira_tools` was imported (1 construction, measured in a fresh interpreter). *Now:* `_jira` is `None` at import; the first `register_tools()` call builds the service only if `_jira` is still `None` (7 changed lines in `jira_tools.py`: the declaration and a guarded `global _jira` initialisation; the 13 handler bodies, the `register_tools(mcp)` signature and the `_jira` name are untouched). *Measured, fresh interpreter:* importing `jira_tools` constructs 0 services and leaves `_jira` as `None`; importing `src.servers.server` constructs exactly 1, registers all 13 tools and serves `/mcp/jira/health` (200). *Tests:* `tests/test_service_lifecycle.py` (7): import constructs none (fresh interpreter, so the module cache cannot hide it); first registration builds exactly one; repeated registration builds none; a pre-set or patched `_jira` is never replaced; the signature and name are unchanged; all 13 tools reach the service built at registration; server import still builds exactly one (pinned as the accepted limitation). Four of them failed against the old code (1 != 0 at import, 0 != 1 on registration, `NoneType` in a handler). To keep `tests/test_tool_registration.py` independent of whether another test already built the service, its capture helper now holds a placeholder in `_jira` while it runs; the golden file is untouched and the original code passes it identically. *Verified:* registration golden, tool contract, service golden and the 13 schemas (byte-identical, 12,095 bytes) unchanged; 132 passed in the normal order, in reverse file order and with each order-sensitive file run alone; the whole suite passes with non-loopback networking blocked (0 attempts); import graph acyclic. *Limits:* the service is still module-level singleton state and server import still constructs it; nothing here establishes concurrency safety. Parent T-15 (blank-safe config, startup validation, URL normalisation, port/Dockerfile, AC-10) is not done.

**Known limitations and deferred debt.** Mocked traffic only: no live Jira, network failure modes or concurrent calls; the shared `requests.Session` and epic cache under concurrent `to_thread` calls are untested. The two long methods (`get_issues_bulk` 193 lines, `create_issues_bulk` 151) and the two pagination loops are intentionally not decomposed or merged (T-11, T-12, T-19). `jira_tools.py` still holds the service as module-level state (`_jira`, built by the first `register_tools()` call — T-15a; explicit injection is for the rest of T-15), the `JiraValidationError` → `ToolError` mapping on only 5 of 13 handlers (T-18), the tool-name list duplicated in `register_tools`, and 7 `print()` calls (T-19); splitting it into group modules is deferred until T-15 and T-18 land. The `JiraService.session` property and three private compatibility delegates remain for existing callers. The golden files were generated by scripts that are not committed; regenerating them needs the original tree (git `b6fc26d`) and must never be done from refactored code. The contract test (T-21) and the coverage gate (T-20) are still open.

**Disclosure.** Before T-29, test runs in this repository imported `src.config` with a `.env` that set `AZURE_APPCONFIG_ENDPOINT`, and so read Azure App Configuration (read-only; no Jira call, because `requests` is mocked). One unfixed in-process run during the T-29 work did the same before the stubbed variant was used. After the fix this no longer happens.
