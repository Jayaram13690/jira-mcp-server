"""
Deterministic scenario battery for the JiraService golden-trace test.

collect_trace() runs every scenario against whatever JiraService / MCP server
it is handed, with Jira fully mocked (tests/_mock_jira_api.py), and returns a
JSON-serialisable trace: result or exception, every HTTP call (method, URL,
kwargs), captured stdout and the project's own log records.

The committed golden file (tests/golden/service_traces.json) was generated from
the ORIGINAL implementation (git b6fc26d, before any modularization). It must
never be regenerated from refactored code - that would hide behaviour changes.
This module imports nothing from src.* so it can run against either layout.
"""
import asyncio
import base64
import contextlib
import io
import logging
import os
import tempfile
from unittest import mock as umock

B64 = base64.b64encode(b"hi").decode()
PROJECT_LOGGERS = ("src.", "jira-mcp-server")


def _norm(text, tmp):
    return str(text).replace("src.jira.", "src.").replace(tmp, "<TMP>")


def _ser(o):
    if isinstance(o, (bytes, bytearray)):
        return f"<bytes:{len(o)}>"
    if hasattr(o, "read"):
        return "<file>"
    if isinstance(o, dict):
        return {k: _ser(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_ser(x) for x in o]
    return o


class _Capture(logging.Handler):
    def __init__(self, tmp):
        super().__init__(logging.DEBUG)
        self.tmp, self.records = tmp, []

    def emit(self, record):
        if record.name.startswith(PROJECT_LOGGERS):
            self.records.append([_norm(record.name, self.tmp), record.levelname,
                                 _norm(record.getMessage(), self.tmp)])


def _issue(key, typ="Story", parent=None, desc=True):
    f = {"summary": f"sum {key}", "status": {"name": "To Do"}, "priority": {"name": "High"},
         "labels": ["a"], "issuetype": {"name": typ}, "created": "c", "updated": "u"}
    if desc:
        f["description"] = {"content": [{"content": [{"type": "text", "text": f"d {key}"}]}]}
    if parent:
        f["parent"] = {"key": parent, "fields": {"summary": "p"}}
    return {"key": key, "fields": f}


def collect_trace(service_cls, server_module, tools_module, mock_api, tmp):
    """Run all scenarios (tool phase uses a fresh tools-module service); returns {scenario_name: {...}} plus '__tools__' and '__tool_order__'."""
    from fastmcp import Client

    FakeResponse, default_handler = mock_api.FakeResponse, mock_api.default_handler

    def paged(pages, base=default_handler):
        state = {"i": 0}

        def handler(method, url, **kw):
            if "/search/jql" in url:
                page = pages(state["i"]) if callable(pages) else pages[min(state["i"], len(pages) - 1)]
                state["i"] += 1
                return FakeResponse(200, page)
            return base(method, url, **kw)
        return handler

    def endless(prefix):
        return lambda i: {"issues": [_issue(f"{prefix}-{i}")], "isLast": False, "nextPageToken": f"t{i}"}

    def epic_aware(base):
        def handler(method, url, **kw):
            if method == "GET" and url.endswith("/issue/EP-1"):
                return FakeResponse(200, {"fields": {"summary": "Epic", "issuetype": {"name": "Epic"}}})
            if method == "GET" and url.endswith("/issue/ST-1") and "params" not in kw:
                return FakeResponse(200, {"fields": {"summary": "Story", "issuetype": {"name": "Story"}}})
            return base(method, url, **kw)
        return handler

    def err(status, body=None):
        return lambda m, u, **k: FakeResponse(status, body if body is not None else {"errorMessages": ["x"]})

    def bulk_partial(method, url, **kw):
        if url.endswith("/issue/bulk"):
            return FakeResponse(201, {"issues": [{"key": "B-1"}], "errors": [
                {"failedElementNumber": 1, "elementErrors": {"errors": {"summary": "bad"}}}]})
        return default_handler(method, url, **kw)

    def team_managed(method, url, **kw):
        if url.endswith("/rest/api/3/field"):
            return FakeResponse(200, [{"id": "summary", "name": "Summary"}])
        return default_handler(method, url, **kw)

    def no_issuetypes(method, url, **kw):
        if "/issue/createmeta" in url:
            return FakeResponse(200, {"projects": []})
        return default_handler(method, url, **kw)

    def transition_status(current):
        def handler(method, url, **kw):
            if method == "GET" and url.endswith("/issue/T-1"):
                return FakeResponse(200, {"fields": {"status": {"name": current}}})
            return default_handler(method, url, **kw)
        return handler

    def transitions_variant(payload):
        def handler(method, url, **kw):
            if method == "GET" and url.endswith("/issue/T-1"):
                return FakeResponse(200, {"fields": {"status": {"name": "To Do"}}})
            if method == "GET" and url.endswith("/issue/T-1/transitions"):
                return FakeResponse(200, payload)
            return default_handler(method, url, **kw)
        return handler

    def bulk_http500(method, url, **kw):
        if url.endswith("/issue/bulk"):
            return FakeResponse(500, {})
        return default_handler(method, url, **kw)

    attach_file = os.path.join(tmp, "attach.txt")
    with open(attach_file, "wb") as fh:
        fh.write(b"filedata")

    def twice(fn):
        def run(s):
            return [fn(s), fn(s)]
        return run

    S = [  # (name, handler, fn(svc))
        # --- create_issue / fields / validation order
        ("create_issue_basic", None, lambda s: s.create_issue("TST", "Sum", "desc", None, "story", None)),
        ("create_issue_all_fields", None, lambda s: s.create_issue("TST", "Sum", "d", "high", "Epic", "EpicName", ["x", " ", "y"], " PAR-1 ")),
        ("create_issue_team_managed_epic", team_managed, lambda s: s.create_issue("TST", "Sum", "d", None, "epic", "E")),
        ("create_issue_bad_type", None, lambda s: s.create_issue("TST", "Sum", "d", None, "nope", None)),
        ("create_issue_bad_priority", None, lambda s: s.create_issue("TST", "Sum", "d", "zzz", "story", None)),
        ("create_issue_bad_type_and_priority_type_wins", None, lambda s: s.create_issue("TST", "Sum", "d", "zzz", "nope", None)),
        ("create_issue_blank_project", None, lambda s: s.create_issue(" ", "Sum", "d", None, "story", None)),
        ("create_issue_no_issuetypes_for_project", no_issuetypes, lambda s: s.create_issue("TST", "S", "d", None, "story", None)),
        ("create_issue_http500", err(500, {"e": 1}), lambda s: s.create_issue("TST", "S", "d", None, "story", None)),
        ("create_issue_twice_field_once_createmeta_twice", None, twice(lambda s: s.create_issue("TST", "S", "d", None, "story", None))),
        ("get_issue_types_direct", None, lambda s: s.get_issue_types(" TST ")),
        ("get_issue_types_blank", None, lambda s: s.get_issue_types("  ")),
        ("get_priorities_direct", None, lambda s: s.get_priorities()),
        # --- update / labels / links / comments
        ("update_issue_all", None, lambda s: s.update_issue("TST-1", "new", "newd", "low")),
        ("update_issue_nothing", None, lambda s: s.update_issue("TST-1", None, None, None)),
        ("update_issue_bad_priority", None, lambda s: s.update_issue("TST-1", None, None, "zzz")),
        ("update_issue_priority_validated_after_fields_built", None, lambda s: s.update_issue("TST-1", "s", None, "zzz")),
        ("update_labels", None, lambda s: s.update_labels("TST-1", ["a"], ["b"])),
        ("update_labels_none", None, lambda s: s.update_labels("TST-1", [], [])),
        ("add_remote_link_plain", None, lambda s: s.add_remote_link("TST-1", "https://x.example/a", "T")),
        ("add_remote_link_testrail", None, lambda s: s.add_remote_link("TST-1", "https://TestRail.io/c/1", "T")),
        ("link_issue_to_epic_company", None, lambda s: s.link_issue_to_epic("TST-1", "EP-1")),
        ("link_issue_to_epic_team", team_managed, lambda s: s.link_issue_to_epic("TST-1", "EP-1")),
        ("add_comment", None, lambda s: s.add_comment("TST-1", "hello")),
        ("add_comment_http404", err(404), lambda s: s.add_comment("TST-1", "hello")),
        ("add_comment_with_links", None, lambda s: s.add_comment_with_links("TST-1", "see ", [{"text": "A", "url": "https://a"}, {"text": "B", "url": "https://b"}])),
        ("add_comment_with_links_empty", None, lambda s: s.add_comment_with_links("TST-1", "only", [])),
        ("add_comment_with_links_badlink", None, lambda s: s.add_comment_with_links("TST-1", "x", [{"text": "A"}])),
        # --- attachments
        ("add_attachment_b64", None, lambda s: s.add_attachment("TST-1", None, "a.txt", B64, "text/plain")),
        ("add_attachment_b64_default_mime", None, lambda s: s.add_attachment("TST-1", None, "a.bin", B64)),
        ("add_attachment_b64_nofilename", None, lambda s: s.add_attachment("TST-1", None, None, B64)),
        ("add_attachment_bad_b64", None, lambda s: s.add_attachment("TST-1", None, "a", "!!!")),
        ("add_attachment_both", None, lambda s: s.add_attachment("TST-1", attach_file, "a", B64)),
        ("add_attachment_neither", None, lambda s: s.add_attachment("TST-1")),
        ("add_attachment_file", None, lambda s: s.add_attachment("TST-1", attach_file, None, None, "text/plain")),
        ("add_attachment_file_no_mime_custom_name", None, lambda s: s.add_attachment("TST-1", attach_file, "renamed.txt")),
        ("add_attachment_missing_file", None, lambda s: s.add_attachment("TST-1", attach_file + ".nope")),
        ("add_attachment_http403", err(403), lambda s: s.add_attachment("TST-1", None, "a", B64)),
        # --- transitions
        ("transition_already_done", transition_status("Done"), lambda s: s.transition_issue("T-1", "Done")),
        ("transition_ok_case_insensitive", transition_status("To Do"), lambda s: s.transition_issue("T-1", "done")),
        ("transition_matches_by_transition_name", transitions_variant({"transitions": [{"id": "7", "name": "Ship it", "to": {"name": "Released"}}]}), lambda s: s.transition_issue("T-1", "ship it")),
        ("transition_missing_target", transition_status("To Do"), lambda s: s.transition_issue("T-1", "Nowhere")),
        ("transition_no_transitions_key", transitions_variant({}), lambda s: s.transition_issue("T-1", "Done")),
        ("transition_no_status", lambda m, u, **k: FakeResponse(200, {"fields": {}}) if (m == "GET" and u.endswith("/issue/T-1")) else default_handler(m, u, **k), lambda s: s.transition_issue("T-1", "Done")),
        ("transition_blank_key", None, lambda s: s.transition_issue(" ", "Done")),
        ("transition_blank_target", None, lambda s: s.transition_issue("T-1", " ")),
        ("transition_http404", err(404), lambda s: s.transition_issue("T-1", "Done")),
        # --- single reads
        ("get_issue", None, lambda s: s.get_issue("TST-1")),
        ("get_issue_http404", err(404), lambda s: s.get_issue("TST-1")),
        ("get_issue_null_priority", lambda m, u, **k: FakeResponse(200, {"fields": {"summary": "s", "status": {"name": "x"}, "priority": None}}) if m == "GET" else FakeResponse(404), lambda s: s.get_issue("TST-1")),
        ("get_issue_with_parent", lambda m, u, **k: FakeResponse(200, {"fields": {"summary": "s", "status": {"name": "x"}, "priority": {"name": "Low"}, "parent": {"key": "P-1", "fields": {"summary": "ps"}}}}) if m == "GET" else FakeResponse(404), lambda s: s.get_issue("TST-1")),
        # --- search
        ("search_issues_pages_cap", paged([{"issues": [_issue("S-1"), _issue("S-2")], "isLast": False, "nextPageToken": "t1"}, {"issues": [_issue("S-3")], "isLast": True}]), lambda s: s.search_issues("project = X", 1)),
        ("search_issues_all", paged([{"issues": [_issue("S-1")], "isLast": False, "nextPageToken": "t1"}, {"issues": [_issue("S-2")], "isLast": True}]), lambda s: s.search_issues("project = X")),
        ("search_issues_dup_loop", paged([{"issues": [_issue("S-1")], "isLast": False, "nextPageToken": "t1"}, {"issues": [_issue("S-1")], "isLast": False, "nextPageToken": "t2"}]), lambda s: s.search_issues("project = X")),
        ("search_issues_safety_cap_50_pages", paged(endless("S")), lambda s: s.search_issues("project = X")),
        ("search_issues_empty_priority", paged([{"issues": [{"key": "S-1", "fields": {"summary": "s", "status": {"name": "x"}, "priority": None}}], "isLast": True}]), lambda s: s.search_issues("project = X")),
        ("search_issues_http400", err(400), lambda s: s.search_issues("bad jql")),
        # --- bulk read
        ("get_issues_bulk_project_3pages", paged([{"issues": [_issue("P-1"), _issue("P-2")], "isLast": False, "nextPageToken": "t1"}, {"issues": [_issue("P-3", parent="EP-1")], "isLast": False, "nextPageToken": "t2"}, {"issues": [_issue("P-4", desc=False)], "isLast": True}]), lambda s: s.get_issues_bulk("PRJ", 3, True)),
        ("get_issues_bulk_max_results_and_fetch_all_false_today", paged([{"issues": [_issue("P-1")], "isLast": False, "nextPageToken": "t1"}, {"issues": [_issue("P-2")], "isLast": False, "nextPageToken": "t2"}, {"issues": [_issue("P-3")], "isLast": True}]), lambda s: s.get_issues_bulk("PRJ", None, False)),
        ("get_issues_bulk_epic", epic_aware(paged([{"issues": [_issue("EP-1", "Epic"), _issue("EP-2")], "isLast": True}])), lambda s: s.get_issues_bulk("EP-1")),
        ("get_issues_bulk_not_epic", epic_aware(default_handler), lambda s: s.get_issues_bulk("ST-1")),
        ("get_issues_bulk_epic_lookup_fails", err(404), lambda s: s.get_issues_bulk("EP-1")),
        ("get_issues_bulk_dup_loop", paged([{"issues": [_issue("P-1")], "isLast": False, "nextPageToken": "t1"}, {"issues": [_issue("P-1")], "isLast": False, "nextPageToken": "t2"}]), lambda s: s.get_issues_bulk("PRJ")),
        ("get_issues_bulk_safety_cap_101_calls", paged(endless("P")), lambda s: s.get_issues_bulk("PRJ")),
        ("get_issues_bulk_empty_first_page", paged([{"issues": [], "isLast": False, "nextPageToken": "t1"}]), lambda s: s.get_issues_bulk("PRJ")),
        ("get_issues_bulk_http500", err(500), lambda s: s.get_issues_bulk("PRJ")),
        ("get_issues_bulk_blank", None, lambda s: s.get_issues_bulk("")),
        ("get_issues_bulk_non_string", None, lambda s: s.get_issues_bulk(None)),
        # --- bulk create
        ("create_issues_bulk_ok", None, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "one", "description": "d1", "labels": ["l"], "priority": "high"}, {"project_key": "B", "summary": "two", "issue_type": "epic", "epic_name": "E", "parent": "X-1"}])),
        ("create_issues_bulk_same_project_types_looked_up_once", None, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "one"}, {"project_key": " A ", "summary": "two"}])),
        ("create_issues_bulk_team_managed_epic_name", team_managed, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "one", "issue_type": "epic", "epic_name": "E"}])),
        ("create_issues_bulk_partial", bulk_partial, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "one"}, {"project_key": "A", "summary": "two"}])),
        ("create_issues_bulk_no_project", None, lambda s: s.create_issues_bulk([{"summary": "x"}])),
        ("create_issues_bulk_non_dict_item", None, lambda s: s.create_issues_bulk(["just a string"])),
        ("create_issues_bulk_second_issue_invalid_nothing_sent", None, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "ok"}, {"project_key": "A"}])),
        ("create_issues_bulk_no_summary", None, lambda s: s.create_issues_bulk([{"project_key": "A"}])),
        ("create_issues_bulk_bad_type", None, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "s", "issue_type": "zz"}])),
        ("create_issues_bulk_bad_priority", None, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "s", "priority": "zz"}])),
        ("create_issues_bulk_http500", bulk_http500, lambda s: s.create_issues_bulk([{"project_key": "A", "summary": "s"}])),
        ("create_issues_bulk_empty_list", None, lambda s: s.create_issues_bulk([])),
    ]

    def run_one(handler, fn):
        capture = _Capture(tmp)
        root = logging.getLogger()
        previous_level = root.level
        root.setLevel(logging.INFO)
        root.addHandler(capture)
        call_log, restore = mock_api.install_mock(handler)
        out = io.StringIO()
        try:
            with umock.patch("time.sleep", lambda *_: None):
                svc = service_cls()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    try:
                        res = {"result": fn(svc)}
                    except BaseException as exc:
                        res = {"exc": [type(exc).__name__, _norm(exc, tmp)]}
        finally:
            restore()
            root.removeHandler(capture)
            root.setLevel(previous_level)
        return {
            "res": _ser(res),
            "calls": [{"m": c["method"], "u": c["url"], "k": _ser(c["kwargs"])} for c in call_log],
            "stdout": _norm(out.getvalue(), tmp),
            "logs": capture.records,
        }

    trace = {name: run_one(handler, fn) for name, handler, fn in S}

    # DEF-12: first /field call fails; the cache flag is already set, so it is never retried.
    def cache_scenario():
        state = {"fail": True}

        def handler(m, u, **k):
            if u.endswith("/rest/api/3/field") and state["fail"]:
                state["fail"] = False
                return FakeResponse(500, {})
            return default_handler(m, u, **k)

        call_log, restore = mock_api.install_mock(handler)
        results = []
        try:
            svc = service_cls()
            for _ in range(2):
                try:
                    results.append(svc.link_issue_to_epic("TST-1", "EP-1"))
                except Exception as exc:
                    results.append(["exc", type(exc).__name__, str(exc)])
        finally:
            restore()
        return {"res": results, "calls": [{"m": c["method"], "u": c["url"], "k": _ser(c["kwargs"])} for c in call_log]}

    trace["epic_cache_failure_is_not_retried_DEF12"] = cache_scenario()

    async def tool_calls():
        cases = [
            ("jira-addComment", {"issue_key": "TST-1", "comment": "c"}),
            ("jira-getIssue", {"issue_key": "TST-1"}),
            ("jira-createIssue", {"project_key": "TST", "summary": "s"}),
            ("jira-createIssue", {"project_key": " ", "summary": "s"}),
            ("jira-updateIssue", {"issue_key": "TST-1"}),
            ("jira-transitionIssue", {"issue_key": "T-1", "target_status": "Done"}),
            ("jira-createIssuesBulk", {"issues": ['{"issues":[{"project_key":"A","summary":"s1"}]}', {"project_key": "A", "summary": "s2"}]}),
            ("jira-createIssuesBulk", {"issues": ["plain text"]}),
            ("jira-searchIssues", {"jql": "project = X"}),
            ("jira-addCommentWithLinks", {"issue_key": "TST-1", "intro_text": "i", "links": [{"text": "a", "url": "https://u"}]}),
            ("jira-addRemoteLink", {"issue_key": "TST-1", "url": "https://u", "title": "t"}),
            ("jira-updateLabels", {"issue_key": "TST-1", "add_labels": ["a"]}),
            ("jira-linkIssueToEpic", {"issue_key": "TST-1", "epic_key": "EP-1"}),
            ("jira-getIssuesBulk", {"project_key": "PRJ"}),
            ("jira-addAttachment", {"issue_key": "TST-1", "content_base64": B64, "filename": "f.txt"}),
        ]
        out = {}
        for i, (name, args) in enumerate(cases):
            call_log, restore = mock_api.install_mock()
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    async with Client(server_module.mcp) as client:
                        try:
                            r = await client.call_tool(name, args)
                            val = {"ok": [getattr(x, "text", str(x)) for x in r.content]}
                        except Exception as exc:
                            val = {"err": [type(exc).__name__, str(exc)]}
            finally:
                restore()
            out[f"{i}:{name}"] = {"res": val, "stdout": buf.getvalue(),
                                  "calls": [{"m": c["method"], "u": c["url"], "k": _ser(c["kwargs"])} for c in call_log]}
        async with Client(server_module.mcp) as client:
            order = [t.name for t in await client.list_tools()]
        return out, order

    # The tools module holds a process-wide service whose epic-field cache survives between
    # calls; give the tool phase a fresh one so the trace does not depend on test order.
    with umock.patch.object(tools_module, "_jira", service_cls()):
        trace["__tools__"], trace["__tool_order__"] = asyncio.run(tool_calls())
    return trace


def new_tmpdir():
    return tempfile.mkdtemp(prefix="jira-golden-")
