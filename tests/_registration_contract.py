"""
Registration-behaviour capture for the tool layer (FR-15, FR-18; AC-11).

collect_registration() calls the module's `register_tools()` on a fresh FastMCP server for a range of
`ENABLED_JIRA_TOOLS` values and records which tools end up registered, in what order, and what the
project logger said (Registering / Registered / Unknown tool / Successfully registered).

The committed golden file (tests/golden/tool_registration.json) was generated from the ORIGINAL
implementation (git b6fc26d). It must never be regenerated from refactored code.
This module imports nothing from src.* so it can run against either layout.
"""
import asyncio
import logging
from unittest import mock as umock

ALL = [
    "jira-createIssue", "jira-updateIssue", "jira-getIssue", "jira-getIssuesBulk", "jira-createIssuesBulk",
    "jira-linkIssueToEpic", "jira-addComment", "jira-addCommentWithLinks", "jira-searchIssues",
    "jira-updateLabels", "jira-addRemoteLink", "jira-addAttachment", "jira-transitionIssue",
]
MISSING = object()

CASES = [
    ("default_none", None),
    ("empty_list_falls_back_to_default", []),
    ("attribute_absent_falls_back_to_default", MISSING),
    ("subset_in_listed_order", ["jira-getIssue", "jira-addComment"]),
    ("subset_in_reversed_order", ["jira-addComment", "jira-getIssue"]),
    ("unknown_name_is_warned_and_skipped", ["jira-getIssue", "jira-nope", "jira-addComment"]),
    ("only_unknown_names", ["jira-nope"]),
    ("duplicate_name", ["jira-getIssue", "jira-getIssue"]),
    ("all_thirteen_reversed", list(reversed(ALL))),
    ("one_tool", ["jira-transitionIssue"]),
]


def _norm(text):
    return str(text).replace("src.jira.", "src.")


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        if record.name.startswith(("src.", "jira-mcp-server")):
            self.records.append([_norm(record.name), record.levelname, _norm(record.getMessage())])


def collect_registration(tools_module):
    from fastmcp import Client, FastMCP

    config = tools_module.config

    async def registered_names(mcp):
        async with Client(mcp) as client:
            return [t.name for t in await client.list_tools()]

    result = {}
    # Registration is what is under test, not service construction: hold a placeholder in `_jira` so
    # the capture is identical whether or not another test already initialised the service (the original
    # implementation had built it at import; a guarded `register_tools()` builds it on first call).
    placeholder = umock.patch.object(tools_module, "_jira", object())
    placeholder.start()
    try:
        for label, value in CASES:
            mcp = FastMCP(name="registration-probe")
            capture, root = _Capture(), logging.getLogger()
            previous_level = root.level
            root.setLevel(logging.DEBUG)
            root.addHandler(capture)
            try:
                with umock.patch.object(config, "ENABLED_JIRA_TOOLS", None if value is MISSING else value):
                    if value is MISSING:
                        delattr(config, "ENABLED_JIRA_TOOLS")
                    tools_module.register_tools(mcp)
            finally:
                root.removeHandler(capture)
                root.setLevel(previous_level)
            names = asyncio.run(registered_names(mcp))
            result[label] = {"enabled": None if value is MISSING else value, "attribute_absent": value is MISSING,
                             "registered_in_order": names, "logs": capture.records}
    finally:
        placeholder.stop()
    return result
