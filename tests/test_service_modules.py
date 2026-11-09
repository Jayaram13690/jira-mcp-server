"""
Boundary tests for the extracted service modules (P2.3, P2.4c, P2.6, P2.7).

Behaviour is pinned end-to-end by tests/test_service_golden.py. These tests pin the
architecture: dependency direction, the injected-request seam, and JiraFields' cache
semantics (including the tracked DEF-12 behaviour) without any HTTP at all.
"""
import ast
import unittest
from pathlib import Path
from unittest import mock

import requests

from src.exceptions.exceptions import JiraValidationError
from src.services.fields import JiraFields
from src.services.jira_service import JiraService
from tests._mock_jira_api import FakeResponse, install_mock

SERVICES_DIR = Path(__file__).resolve().parent.parent / "src" / "services"

# module -> the only first-party / third-party imports it may use (stdlib is always fine)
ALLOWED_IMPORTS = {
    "adf": set(),
    "jira_client": {"requests", "src.config"},
    "fields": {"src.exceptions.exceptions", "src.services.jira_client"},
    "bulk_create": {"src.config", "src.exceptions.exceptions", "src.services.adf", "src.services.fields",
                    "src.services.jira_client"},
    "search": {"src.config", "src.exceptions.exceptions", "src.services.adf", "src.services.jira_client"},
    "issues": {"src.config", "src.exceptions.exceptions", "src.services.adf", "src.services.fields",
               "src.services.jira_client"},
    "transitions": {"src.exceptions.exceptions", "src.services.jira_client"},
    "attachments": {"src.exceptions.exceptions", "src.services.jira_client"},
    "jira_service": {"src.services", "src.services.adf", "src.services.bulk_create", "src.services.fields",
                     "src.services.issues", "src.services.jira_client", "src.services.search",
                     "src.utils.log_helper"},
}
STDLIB_OK = {"json", "logging", "traceback", "typing", "base64", "os", "time"}


def _imports(module_name):
    tree = ast.parse((SERVICES_DIR / f"{module_name}.py").read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module)
    return found - STDLIB_OK


class DependencyDirectionTests(unittest.TestCase):
    def test_each_service_module_imports_only_what_its_layer_allows(self):
        for module, allowed in ALLOWED_IMPORTS.items():
            with self.subTest(module=module):
                self.assertLessEqual(_imports(module), allowed)

    def test_no_component_imports_the_facade_mcp_or_tools(self):
        forbidden = {"fastmcp", "mcp", "src.services.jira_service", "src.tools", "src.servers"}
        for module in ALLOWED_IMPORTS:
            if module == "jira_service":
                continue
            with self.subTest(module=module):
                self.assertTrue(_imports(module).isdisjoint(forbidden))

    def test_only_the_client_touches_requests(self):
        for module in ALLOWED_IMPORTS:
            with self.subTest(module=module):
                self.assertEqual("requests" in _imports(module), module == "jira_client")

    def test_no_default_project_or_credentials_in_service_modules(self):
        for module in ALLOWED_IMPORTS:
            text = (SERVICES_DIR / f"{module}.py").read_text(encoding="utf-8")
            with self.subTest(module=module):
                self.assertNotIn("JIRA_PROJECT_KEY", text)
                self.assertNotIn("atlassian.net", text)


class RequestSeamTests(unittest.TestCase):
    def test_patching_the_facade_request_reaches_extracted_components(self):
        """Components call self._request through the facade at call time, so patching it still works."""
        call_log, restore = install_mock()
        try:
            svc = JiraService()
            seen = []

            def fake_request(method, path, **kwargs):
                seen.append((method, path))
                return FakeResponse(200, [{"name": "Only"}])

            with mock.patch.object(svc, "_request", fake_request):
                self.assertEqual(svc.get_priorities(), ["Only"])
            self.assertEqual(seen, [("GET", "/rest/api/3/priority")])
            self.assertEqual(call_log, [], "the real session must not have been used")
        finally:
            restore()

    def test_facade_request_is_the_single_logged_path_for_components(self):
        call_log, restore = install_mock()
        try:
            with self.assertLogs("src.services.jira_service", level="INFO") as cm:
                JiraService().add_comment("TST-1", "hi")
        finally:
            restore()
        messages = [r.getMessage() for r in cm.records]
        self.assertEqual(messages.count("Entry :  JiraService._request"), 1)
        self.assertEqual(len(call_log), 1)


class JiraFieldsTests(unittest.TestCase):
    """JiraFields with a fake request: no HTTP, no facade."""

    def _fields(self, handler):
        calls = []

        def request(method, path, **kwargs):
            calls.append((method, path))
            return handler(method, path)
        return JiraFields(request), calls

    @staticmethod
    def _ok(method, path):
        if path.endswith("/field"):
            return FakeResponse(200, [{"id": "cf1", "name": "Epic Name"}, {"id": "cf2", "name": "Epic Link"}])
        if "createmeta" in path:
            return FakeResponse(200, {"projects": [{"issuetypes": [{"name": "Story"}, {"name": "Epic"}]}]})
        return FakeResponse(200, [{"name": "High"}])

    def test_custom_fields_are_loaded_once_per_instance(self):
        fields, calls = self._fields(self._ok)
        fields.load_custom_fields()
        fields.load_custom_fields()
        self.assertEqual(calls, [("GET", "/rest/api/3/field")])
        self.assertEqual((fields.epic_name_field, fields.epic_link_field), ("cf1", "cf2"))

    def test_failed_field_lookup_is_never_retried_DEF12(self):
        """Pins tracked defect DEF-12 / T-14. Flip this test in T-14, not in a refactor."""
        state = {"fail": True}

        def handler(method, path):
            if path.endswith("/field") and state["fail"]:
                state["fail"] = False
                raise requests.ConnectionError("boom")
            return self._ok(method, path)

        fields, calls = self._fields(handler)
        with self.assertRaises(requests.ConnectionError):
            fields.load_custom_fields()
        fields.load_custom_fields()  # does nothing: the flag was set before the request
        self.assertEqual(len(calls), 1)
        self.assertIsNone(fields.epic_name_field)

    def test_issue_types_are_looked_up_on_every_call_and_never_cached(self):
        fields, calls = self._fields(self._ok)
        self.assertEqual(fields.get_issue_types(" TST "), {"story": "Story", "epic": "Epic"})
        fields.get_issue_types("TST")
        self.assertEqual(calls, [("GET", "/rest/api/3/issue/createmeta?projectKeys=TST")] * 2)

    def test_blank_project_key_is_refused_before_any_request(self):
        fields, calls = self._fields(self._ok)
        for bad in ("", "   ", None):
            with self.subTest(project_key=bad), self.assertRaises(JiraValidationError):
                fields.get_issue_types(bad)
        self.assertEqual(calls, [])

    def test_priorities_are_names_in_jira_order(self):
        fields, _ = self._fields(lambda m, p: FakeResponse(200, [{"name": "Highest"}, {"name": "Low"}]))
        self.assertEqual(fields.get_priorities(), ["Highest", "Low"])


class FacadeCompositionTests(unittest.TestCase):
    def test_service_owns_one_client_and_shares_it_with_components(self):
        _log, restore = install_mock()
        try:
            svc = JiraService()
        finally:
            restore()
        self.assertIs(svc.session, svc._client.session)
        self.assertIsInstance(svc._fields, JiraFields)
        self.assertEqual(sorted(vars(svc)), ["_bulk", "_client", "_fields", "_issues", "_search"])


if __name__ == "__main__":
    unittest.main()
