"""
Characterization tests for the HTTP transport behaviour of JiraService.

P2.2 / NFR-1, NFR-2 context: these pin what the transport does TODAY - one
requests.Session per service, Basic auth, JSON Content-Type default, URL =
JIRA_URL + path, kwargs passed straight through, RuntimeError on a non-2xx,
NO timeout and NO retry (DEF-2 / T-10 will change those, not P2.2).

They go through JiraService only, so they pass unchanged before and after the
transport moves into src/services/jira_client.py. The last class tests the new
module directly and only exists after the extraction.

All Jira HTTP is mocked (tests/_mock_jira_api.py) - no network.
"""
import json
import unittest

import requests

from src.config import config
from src.services.jira_service import JiraService
from tests._mock_jira_api import FakeResponse, install_mock

SERVICE_LOGGER = "src.services.jira_service"


def _shape(call_log):
    """(method, url-after-host) for each recorded call, in order."""
    return [(c["method"], c["url"][len(config.JIRA_URL):]) for c in call_log]


class SessionSetupTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()

    def tearDown(self):
        self._restore()

    def test_session_is_a_requests_session(self):
        self.assertIsInstance(JiraService().session, requests.Session)

    def test_session_auth_is_basic_auth_tuple_from_config(self):
        self.assertEqual(
            JiraService().session.auth, (config.JIRA_USERNAME, config.JIRA_API_TOKEN))

    def test_session_default_content_type_is_json(self):
        self.assertEqual(JiraService().session.headers["Content-Type"], "application/json")

    def test_each_service_instance_has_its_own_session(self):
        self.assertIsNot(JiraService().session, JiraService().session)

    def test_session_is_assignable_and_used_for_requests(self):
        """Pins that `svc.session` stays a settable attribute with one source of truth."""
        svc = JiraService()
        replacement = requests.Session()
        svc.session = replacement
        self.assertIs(svc.session, replacement)
        svc._request("GET", "/rest/api/3/priority")
        self.assertEqual(len(self.call_log), 1)


class RequestBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_url_is_jira_url_plus_path(self):
        self.svc._request("GET", "/rest/api/3/priority")
        self.assertEqual(self.call_log[0]["url"], f"{config.JIRA_URL}/rest/api/3/priority")
        self.assertEqual(self.call_log[0]["method"], "GET")

    def test_kwargs_are_passed_through_unchanged(self):
        self.svc._request("POST", "/rest/api/3/issue", json={"a": 1}, params={"p": "q"},
                          headers={"H": "v"})
        self.assertEqual(self.call_log[0]["kwargs"],
                         {"json": {"a": 1}, "params": {"p": "q"}, "headers": {"H": "v"}})

    def test_no_timeout_is_sent_today(self):
        """Pins DEF-2 (no timeout). T-10 flips this, not P2.2."""
        self.svc._request("GET", "/rest/api/3/priority")
        self.assertNotIn("timeout", self.call_log[0]["kwargs"])

    def test_successful_response_object_is_returned(self):
        resp = self.svc._request("GET", "/rest/api/3/priority")
        self.assertTrue(resp.ok)
        self.assertEqual(resp.json()[0]["name"], "Highest")

    def test_non_2xx_raises_runtime_error_with_status_and_raw_body(self):
        for status in (400, 401, 403, 404, 429, 500, 503):
            with self.subTest(status=status):
                body = {"errorMessages": [f"boom {status}"]}
                _log, restore = install_mock(lambda m, u, _s=status, _b=body, **k: FakeResponse(_s, _b))
                try:
                    with self.assertRaises(RuntimeError) as cm:
                        JiraService()._request("GET", "/rest/api/3/issue/X-1")
                finally:
                    restore()
                self.assertEqual(str(cm.exception),
                                 f"Jira API error {status}: {json.dumps(body)}")

    def test_no_retry_on_error_response(self):
        log, restore = install_mock(lambda m, u, **k: FakeResponse(503, {}))
        try:
            with self.assertRaises(RuntimeError):
                JiraService()._request("GET", "/rest/api/3/issue/X-1")
        finally:
            restore()
        self.assertEqual(len(log), 1)

    def test_transport_exception_propagates_without_retry(self):
        def handler(method, url, **kwargs):
            raise requests.ConnectionError("down")
        log, restore = install_mock(handler)
        try:
            with self.assertRaises(requests.ConnectionError):
                JiraService()._request("GET", "/rest/api/3/priority")
        finally:
            restore()
        self.assertEqual(len(log), 1)


class RequestOrderTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_create_issue_call_order(self):
        self.svc.create_issue("TST", "S", "d", None, "story", None)
        self.assertEqual(_shape(self.call_log), [
            ("GET", "/rest/api/3/field"),
            ("GET", "/rest/api/3/issue/createmeta?projectKeys=TST"),
            ("GET", "/rest/api/3/priority"),
            ("POST", "/rest/api/3/issue"),
        ])

    def test_transition_issue_call_order(self):
        self.svc.transition_issue("TST-1", "Done")
        self.assertEqual(_shape(self.call_log), [
            ("GET", "/rest/api/3/issue/TST-1"),
            ("GET", "/rest/api/3/issue/TST-1/transitions"),
            ("POST", "/rest/api/3/issue/TST-1/transitions"),
        ])
        self.assertEqual(self.call_log[0]["kwargs"], {"params": {"fields": "status"}})
        self.assertEqual(self.call_log[2]["kwargs"], {"json": {"transition": {"id": "31"}}})

    def test_add_attachment_overrides_content_type_and_sets_atlassian_token(self):
        import base64
        self.svc.add_attachment("TST-1", filename="a.txt",
                                content_base64=base64.b64encode(b"hi").decode())
        call = self.call_log[0]
        self.assertEqual(call["method"], "POST")
        self.assertTrue(call["url"].endswith("/rest/api/3/issue/TST-1/attachments"))
        self.assertEqual(call["kwargs"]["headers"],
                         {"X-Atlassian-Token": "no-check", "Content-Type": None})
        self.assertIn("file", call["kwargs"]["files"])

    def test_get_priorities_and_search_use_expected_endpoints(self):
        self.svc.get_priorities()
        self.svc.search_issues("project = TST")
        self.assertEqual(_shape(self.call_log), [
            ("GET", "/rest/api/3/priority"),
            ("GET", "/rest/api/3/search/jql"),
        ])


class RequestLoggingTests(unittest.TestCase):
    """The `Entry : JiraService._request` log line comes from JiraService's decorator."""

    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_request_logs_entry_and_exit_under_service_logger(self):
        with self.assertLogs(SERVICE_LOGGER, level="INFO") as cm:
            self.svc._request("GET", "/rest/api/3/priority")
        messages = [r.getMessage() for r in cm.records]
        self.assertEqual(messages, ["Entry :  JiraService._request", "Exit : JiraService._request"])

    def test_failed_request_logs_exception_line(self):
        _log, restore = install_mock(lambda m, u, **k: FakeResponse(500, {"e": 1}))
        try:
            with self.assertLogs(SERVICE_LOGGER, level="INFO") as cm:
                with self.assertRaises(RuntimeError):
                    JiraService()._request("GET", "/x")
        finally:
            restore()
        self.assertEqual(
            [r.getMessage() for r in cm.records if r.levelname == "ERROR"],
            ['Exception : JiraService._request: Jira API error 500: {"e": 1}'])

    def test_constructor_logs_entry_under_service_logger(self):
        with self.assertLogs(SERVICE_LOGGER, level="INFO") as cm:
            JiraService()
        self.assertIn("Entry :  JiraService.__init__", [r.getMessage() for r in cm.records])


class JiraClientModuleTests(unittest.TestCase):
    """P2.2: the extracted client, tested directly (exists only after extraction)."""

    def setUp(self):
        self.call_log, self._restore = install_mock()

    def tearDown(self):
        self._restore()

    def test_client_behaves_like_the_service_transport(self):
        from src.services.jira_client import JiraClient

        client = JiraClient()
        self.assertIsInstance(client.session, requests.Session)
        self.assertEqual(client.session.auth, (config.JIRA_USERNAME, config.JIRA_API_TOKEN))
        resp = client.request("GET", "/rest/api/3/priority", params={"a": "b"})
        self.assertTrue(resp.ok)
        self.assertEqual(self.call_log[0]["url"], f"{config.JIRA_URL}/rest/api/3/priority")
        self.assertEqual(self.call_log[0]["kwargs"], {"params": {"a": "b"}})

    def test_client_raises_same_error_text(self):
        from src.services.jira_client import JiraClient

        _log, restore = install_mock(lambda m, u, **k: FakeResponse(404, {"x": 1}))
        try:
            with self.assertRaises(RuntimeError) as cm:
                JiraClient().request("GET", "/nope")
        finally:
            restore()
        self.assertEqual(str(cm.exception), 'Jira API error 404: {"x": 1}')

    def test_service_holds_one_client_and_shares_its_session(self):
        svc = JiraService()
        self.assertIs(svc.session, svc._client.session)

    def test_client_module_is_transport_only(self):
        """Layering: no service, tool or MCP imports; no logging decorators (no extra log lines)."""
        import ast
        from pathlib import Path

        from src.services import jira_client

        tree = ast.parse(Path(jira_client.__file__).read_text(encoding="utf-8"))
        imported = {
            (n.module if isinstance(n, ast.ImportFrom) else a.name)
            for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        }
        self.assertLessEqual(imported, {"requests", "src.config", "typing"})
        self.assertNotIn("src.services.jira_service", imported)
        self.assertNotIn("fastmcp", imported)

    def test_client_methods_emit_no_log_records(self):
        from src.services.jira_client import JiraClient

        with self.assertNoLogs(level="INFO"):
            JiraClient().request("GET", "/rest/api/3/priority")
