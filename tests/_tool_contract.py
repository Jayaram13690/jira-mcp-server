"""
Tool-layer contract capture for the jira_tools modularization (Phase 2).

collect_contract() records, for whatever server/tools modules it is handed:
  * the complete MCP definition of every tool, in registration order (name, description,
    input/output schema, annotations, tags/meta) - the wire contract;
  * the service-facade method each tool delegates to and the exact positional/keyword
    arguments it passes (a recording stub replaces the module's service);
  * how each tool maps JiraValidationError and any other exception;
  * what jira-createIssuesBulk passes to the service for a range of string-encoded,
    nested and malformed `issues` entries, with the captured stdout.

The committed golden file (tests/golden/tool_contract.json) was generated from the ORIGINAL
implementation (git b6fc26d). It must never be regenerated from refactored code.
This module imports nothing from src.* so it can run against either layout.
"""
import asyncio
import contextlib
import io
from unittest import mock as umock

MIN_ARGS = [
    ("jira-createIssue", {"project_key": "TST", "summary": "s"}),
    ("jira-createIssue", {"project_key": "TST", "summary": "s", "description": "d", "issue_type": "Bug",
                          "priority": "High", "labels": ["a"], "parent": "P-1", "epic_name": "E"}),
    ("jira-updateIssue", {"issue_key": "TST-1", "summary": "x"}),
    ("jira-linkIssueToEpic", {"issue_key": "TST-1", "epic_key": "EP-1"}),
    ("jira-addComment", {"issue_key": "TST-1", "comment": "c"}),
    ("jira-transitionIssue", {"issue_key": "T-1", "target_status": "Done"}),
    ("jira-addCommentWithLinks", {"issue_key": "TST-1", "intro_text": "i", "links": [{"text": "a", "url": "https://u"}]}),
    ("jira-updateLabels", {"issue_key": "TST-1"}),
    ("jira-updateLabels", {"issue_key": "TST-1", "add_labels": ["a"], "remove_labels": ["b"]}),
    ("jira-addRemoteLink", {"issue_key": "TST-1", "url": "https://u", "title": "t"}),
    ("jira-addAttachment", {"issue_key": "TST-1", "content_base64": "aGk=", "filename": "f.txt", "mime_type": "text/plain"}),
    ("jira-addAttachment", {"issue_key": "TST-1", "file_path": "/tmp/x"}),
    ("jira-getIssue", {"issue_key": "TST-1"}),
    ("jira-getIssuesBulk", {"project_key": "PRJ"}),
    ("jira-getIssuesBulk", {"project_key": "PRJ", "max_results": 5, "fetch_all": False}),
    ("jira-searchIssues", {"jql": "project = X"}),
    ("jira-searchIssues", {"jql": "project = X", "max_results": 3}),
    ("jira-createIssuesBulk", {"issues": [{"project_key": "A", "summary": "s"}]}),
]

BULK_INPUTS = [
    ["plain text"],
    ['{"project_key":"A","summary":"s"}'],
    ['{"issues":[{"project_key":"A","summary":"s1"},{"project_key":"A","summary":"s2"}]}'],
    ['{"issues":{"project_key":"A","summary":"x"}}'],
    [{"issues": [{"a": 1}, {"b": 2}]}],
    [{"issues": "not-a-list", "summary": "s"}],
    [{"project_key": "A", "summary": "s"}, "not json {", 5, None, 3.5, True],
    ["[1,2,3]"],
    ['"just a json string"'],
    ["null"],
    [],
    [{"project_key": "A", "summary": "s", "labels": ["x"], "priority": "high", "issue_type": "bug"}],
]


def _ser(o):
    if isinstance(o, dict):
        return {str(k): _ser(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_ser(x) for x in o]
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return repr(o)


class _Stub:
    """Stands in for the module's service; records every call and optionally raises."""

    def __init__(self, raises=None):
        self.calls, self._raises = [], raises

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append([name, _ser(list(args)), _ser(kwargs)])
            if self._raises is not None:
                raise self._raises
            return '{"stub": true}'
        return method


def collect_contract(server_module, tools_module):
    from fastmcp import Client

    validation_error = tools_module.JiraValidationError

    async def call(stub, name, args):
        out = io.StringIO()
        with umock.patch.object(tools_module, "_jira", stub), contextlib.redirect_stdout(out):
            async with Client(server_module.mcp) as client:
                try:
                    result = await client.call_tool(name, args)
                    outcome = {"ok": [getattr(c, "text", repr(c)) for c in result.content]}
                except Exception as exc:
                    outcome = {"error": [type(exc).__name__, str(exc)]}
        return outcome, out.getvalue()

    async def run():
        contract = {}
        async with Client(server_module.mcp) as client:
            tools = await client.list_tools()
        contract["tools"] = [_ser(t.model_dump(mode="json")) for t in tools]

        contract["delegation"] = []
        for name, args in MIN_ARGS:
            stub = _Stub()
            outcome, stdout = await call(stub, name, args)
            contract["delegation"].append({"tool": name, "args": _ser(args), "service_calls": stub.calls,
                                           "outcome": outcome, "stdout": stdout})

        contract["error_mapping"] = []
        seen = set()
        for name, args in MIN_ARGS:
            if name in seen:
                continue
            seen.add(name)
            for label, exc in (("JiraValidationError", validation_error("validation-msg")),
                               ("RuntimeError", RuntimeError("runtime-msg"))):
                outcome, stdout = await call(_Stub(raises=exc), name, args)
                contract["error_mapping"].append({"tool": name, "raises": label, "outcome": outcome, "stdout": stdout})

        contract["bulk_normalization"] = []
        for issues in BULK_INPUTS:
            stub = _Stub()
            outcome, stdout = await call(stub, "jira-createIssuesBulk", {"issues": issues})
            contract["bulk_normalization"].append({"issues": _ser(issues), "service_calls": stub.calls,
                                                   "outcome": outcome, "stdout": stdout})
        for label, exc in (("JiraValidationError", validation_error("validation-msg")),
                           ("RuntimeError", RuntimeError("runtime-msg"))):
            outcome, stdout = await call(_Stub(raises=exc), "jira-createIssuesBulk", {"issues": ["x"]})
            contract["bulk_normalization"].append({"service_raises": label, "outcome": outcome, "stdout": stdout})
        return contract

    return asyncio.run(run())
