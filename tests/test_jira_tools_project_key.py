"""
MCP tool-layer tests, exercising the real FastMCP server (real tool
registration, real pydantic schemas) via FastMCP's in-memory Client -
no network, no uvicorn, and the Jira HTTP layer is mocked
(tests/_mock_jira_api.py), so these tests can never touch real Jira data.
"""
import json
import unittest

from fastmcp import Client

from src.servers import server as server_module
from tests._mock_jira_api import install_mock


def _tool_result_str(result):
    return result.data if hasattr(result, "data") else str(result)


class CreateIssueToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call_log, self._restore = install_mock()

    async def asyncTearDown(self):
        self._restore()

    async def test_missing_project_key_rejected_without_any_api_call(self):
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception):
                await client.call_tool("jira-createIssue", {"summary": "No project key"})
        self.assertEqual(self.call_log, [])

    async def test_blank_project_key_rejected_without_any_api_call(self):
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception):
                await client.call_tool(
                    "jira-createIssue", {"project_key": "   ", "summary": "Blank project key"}
                )
        self.assertEqual(self.call_log, [])

    async def test_explicit_project_key_used_end_to_end(self):
        async with Client(server_module.mcp) as client:
            result = await client.call_tool(
                "jira-createIssue",
                {"project_key": "TEST_PROJECT", "summary": "End to end test"},
            )
        payload = json.loads(_tool_result_str(result))
        self.assertEqual(payload["key"], "MOCK-1")

        create_calls = [c for c in self.call_log
                         if c["url"].endswith("/rest/api/3/issue") and c["method"] == "POST"]
        self.assertEqual(create_calls[0]["kwargs"]["json"]["fields"]["project"]["key"], "TEST_PROJECT")

    async def test_project_key_is_required_in_tool_schema(self):
        async with Client(server_module.mcp) as client:
            tools = await client.list_tools()
        create_issue = next(t for t in tools if t.name == "jira-createIssue")
        schema = create_issue.inputSchema
        self.assertIn("project_key", schema.get("properties", {}))
        self.assertIn("project_key", schema.get("required", []))


class CreateIssuesBulkToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call_log, self._restore = install_mock()

    async def asyncTearDown(self):
        self._restore()

    async def test_missing_project_key_on_one_issue_fails_before_any_api_call(self):
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception):
                await client.call_tool(
                    "jira-createIssuesBulk",
                    {"issues": [
                        {"project_key": "TEST_PROJECT_A", "summary": "Has key"},
                        {"summary": "Missing key"},
                    ]},
                )
        self.assertEqual(self.call_log, [])

    async def test_multiple_project_keys_propagated_correctly(self):
        async with Client(server_module.mcp) as client:
            await client.call_tool(
                "jira-createIssuesBulk",
                {"issues": [
                    {"project_key": "TEST_PROJECT_A", "summary": "Issue A"},
                    {"project_key": "TEST_PROJECT_B", "summary": "Issue B"},
                ]},
            )
        bulk_calls = [c for c in self.call_log if c["url"].endswith("/rest/api/3/issue/bulk")]
        self.assertEqual(len(bulk_calls), 1)
        sent = bulk_calls[0]["kwargs"]["json"]["issueUpdates"]
        self.assertEqual(sent[0]["fields"]["project"]["key"], "TEST_PROJECT_A")
        self.assertEqual(sent[1]["fields"]["project"]["key"], "TEST_PROJECT_B")


class SearchIssuesToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call_log, self._restore = install_mock()

    async def asyncTearDown(self):
        self._restore()

    async def test_no_project_injected_into_jql(self):
        jql = "assignee = currentUser()"
        async with Client(server_module.mcp) as client:
            await client.call_tool("jira-searchIssues", {"jql": jql})
        search_calls = [c for c in self.call_log if "/search/jql" in c["url"]]
        self.assertEqual(search_calls[0]["kwargs"]["params"]["jql"], jql)


class IssueKeyOnlyToolsUnaffectedTests(unittest.IsolatedAsyncioTestCase):
    """Regression check: tools keyed by issue_key must not gain a
    project_key dependency, and must keep working unchanged."""

    async def asyncSetUp(self):
        self.call_log, self._restore = install_mock()

    async def asyncTearDown(self):
        self._restore()

    async def test_issue_key_tools_have_no_project_key_param(self):
        issue_key_tools = [
            "jira-getIssue", "jira-updateIssue", "jira-updateLabels",
            "jira-linkIssueToEpic", "jira-addComment", "jira-addCommentWithLinks",
            "jira-addRemoteLink", "jira-addAttachment",
        ]
        async with Client(server_module.mcp) as client:
            tools = await client.list_tools()
        by_name = {t.name: t for t in tools}
        for name in issue_key_tools:
            with self.subTest(tool=name):
                props = by_name[name].inputSchema.get("properties", {})
                self.assertNotIn("project_key", props,
                                  f"{name} operates on issue_key and must not gain a project_key dependency")

    async def test_add_comment_works_without_project_key(self):
        async with Client(server_module.mcp) as client:
            await client.call_tool("jira-addComment", {"issue_key": "MOCK-1", "comment": "hi"})
        comment_calls = [c for c in self.call_log if c["url"].endswith("/comment")]
        self.assertEqual(len(comment_calls), 1)

    async def test_get_issues_bulk_still_takes_caller_supplied_project_key(self):
        async with Client(server_module.mcp) as client:
            await client.call_tool("jira-getIssuesBulk", {"project_key": "TEST_PROJECT"})
        search_calls = [c for c in self.call_log if "/search/jql" in c["url"]]
        self.assertIn("project = TEST_PROJECT", search_calls[0]["kwargs"]["params"]["jql"])


if __name__ == "__main__":
    unittest.main()
