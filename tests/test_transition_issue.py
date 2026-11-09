"""
Tests for the jira-transitionIssue MCP tool, run through the real FastMCP
server via the in-memory Client. The Jira HTTP layer is mocked
(tests/_mock_jira_api.py), so no real Jira call is ever made.
"""
import json
import unittest

from fastmcp import Client

from src.servers import server as server_module
from tests._mock_jira_api import FakeResponse, default_handler, install_mock


def make_handler(current_status="In Progress", transitions=None, transitions_get=None, transition_post=None):
    """Fake Jira for one issue: status lookup, transitions list, transition POST."""
    if transitions is None:
        transitions = [
            {"id": "21", "name": "Back to To Do", "to": {"name": "To Do"}},
            {"id": "31", "name": "Complete", "to": {"name": "Done"}},
        ]

    def handler(method, url, **kwargs):
        if url.endswith("/transitions"):
            if method == "POST":
                return transition_post or FakeResponse(204, {})
            return transitions_get or FakeResponse(200, {"transitions": transitions})
        if method == "GET" and "/issue/" in url:
            return FakeResponse(200, {"fields": {"status": {"name": current_status}}})
        return default_handler(method, url, **kwargs)

    return handler


def _text(result):
    return result.data if hasattr(result, "data") else str(result)


class TransitionIssueToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._restore = None

    async def asyncTearDown(self):
        if self._restore:
            self._restore()

    def _install(self, **kwargs):
        self.call_log, self._restore = install_mock(make_handler(**kwargs))

    def _posts(self):
        return [c for c in self.call_log if c["method"] == "POST" and c["url"].endswith("/transitions")]

    async def test_successful_transition_uses_resolved_transition_id(self):
        self._install()
        async with Client(server_module.mcp) as client:
            result = await client.call_tool(
                "jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": "Done"})
        payload = json.loads(_text(result))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "transitioned")
        self.assertEqual(payload["transition_id"], "31")
        self.assertEqual(payload["from_status"], "In Progress")
        self.assertEqual(payload["to_status"], "Done")

        gets = [c for c in self.call_log if c["method"] == "GET" and c["url"].endswith("/PROJ-1/transitions")]
        self.assertEqual(len(gets), 1)
        self.assertEqual(len(self._posts()), 1)
        self.assertEqual(self._posts()[0]["kwargs"]["json"], {"transition": {"id": "31"}})

    async def test_target_status_match_is_case_insensitive(self):
        self._install()
        async with Client(server_module.mcp) as client:
            await client.call_tool("jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": "done"})
        self.assertEqual(self._posts()[0]["kwargs"]["json"], {"transition": {"id": "31"}})

    async def test_already_done_is_successful_noop(self):
        self._install(current_status="Done")
        async with Client(server_module.mcp) as client:
            result = await client.call_tool(
                "jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": "Done"})
        payload = json.loads(_text(result))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "already_done")
        self.assertEqual(self._posts(), [])

    async def test_missing_target_transition_returns_clear_error(self):
        self._install(transitions=[{"id": "21", "name": "Back to To Do", "to": {"name": "To Do"}}])
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception) as ctx:
                await client.call_tool(
                    "jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": "Done"})
        self.assertIn("No transition to status 'Done'", str(ctx.exception))
        self.assertIn("To Do", str(ctx.exception))
        self.assertEqual(self._posts(), [])

    async def test_jira_error_on_transitions_lookup_propagates(self):
        self._install(transitions_get=FakeResponse(403, {"errorMessages": ["forbidden"]}))
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception) as ctx:
                await client.call_tool(
                    "jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": "Done"})
        self.assertIn("403", str(ctx.exception))
        self.assertEqual(self._posts(), [])

    async def test_jira_error_on_transition_post_propagates(self):
        self._install(transition_post=FakeResponse(400, {"errorMessages": ["validator failed"]}))
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception) as ctx:
                await client.call_tool(
                    "jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": "Done"})
        self.assertIn("400", str(ctx.exception))

    async def test_issue_not_found_propagates(self):
        def handler(method, url, **kwargs):
            return FakeResponse(404, {"errorMessages": ["Issue does not exist"]})
        self.call_log, self._restore = install_mock(handler)
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception) as ctx:
                await client.call_tool(
                    "jira-transitionIssue", {"issue_key": "NOPE-1", "target_status": "Done"})
        self.assertIn("404", str(ctx.exception))
        self.assertEqual(self._posts(), [])

    async def test_blank_args_rejected_without_api_call(self):
        self._install()
        async with Client(server_module.mcp) as client:
            with self.assertRaises(Exception):
                await client.call_tool("jira-transitionIssue", {"issue_key": "  ", "target_status": "Done"})
            with self.assertRaises(Exception):
                await client.call_tool("jira-transitionIssue", {"issue_key": "PROJ-1", "target_status": ""})
        self.assertEqual(self.call_log, [])

    async def test_schema_requires_issue_key_and_target_status(self):
        self._install()
        async with Client(server_module.mcp) as client:
            tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "jira-transitionIssue")
        self.assertEqual(set(tool.inputSchema["required"]), {"issue_key", "target_status"})
        self.assertNotIn("project_key", tool.inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
