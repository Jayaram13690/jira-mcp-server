"""
Service-layer tests proving there is no default/fallback Jira project.

All Jira HTTP calls are mocked (see tests/_mock_jira_api.py) - these
tests never make a real network request and therefore can never create,
update, comment on, label, link, or otherwise modify real Jira data.
"""
import json
import os
import unittest

from src.config import config
from src.exceptions.exceptions import JiraValidationError
from src.services.jira_service import JiraService
from tests._mock_jira_api import install_mock


class ConfigHasNoDefaultProjectTests(unittest.TestCase):
    def test_jira_project_key_removed_from_config(self):
        self.assertFalse(
            hasattr(config, "JIRA_PROJECT_KEY"),
            "config.JIRA_PROJECT_KEY must not exist - no default/fallback project is allowed.",
        )


class CreateIssueProjectKeyTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_missing_project_key_raises_before_any_api_call(self):
        with self.assertRaises(JiraValidationError):
            self.svc.create_issue(
                project_key=None, summary="Test", description="",
                priority=None, issue_type="story", epic_name=None,
            )
        self.assertEqual(self.call_log, [], "No Jira API call should happen when project_key is missing.")

    def test_blank_project_key_raises_before_any_api_call(self):
        for bad in ["", "   "]:
            with self.subTest(project_key=repr(bad)):
                with self.assertRaises(JiraValidationError):
                    self.svc.create_issue(
                        project_key=bad, summary="Test", description="",
                        priority=None, issue_type="story", epic_name=None,
                    )
        self.assertEqual(self.call_log, [], "No Jira API call should happen when project_key is blank.")

    def test_uses_exact_caller_supplied_project_key(self):
        result = self.svc.create_issue(
            project_key="TEST_PROJECT", summary="Test issue", description="desc",
            priority=None, issue_type="story", epic_name=None,
        )
        payload = json.loads(result)
        self.assertEqual(payload["key"], "MOCK-1")

        createmeta_calls = [c for c in self.call_log if "createmeta" in c["url"]]
        self.assertEqual(len(createmeta_calls), 1)
        self.assertIn("projectKeys=TEST_PROJECT", createmeta_calls[0]["url"])

        create_calls = [c for c in self.call_log
                         if c["url"].endswith("/rest/api/3/issue") and c["method"] == "POST"]
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0]["kwargs"]["json"]["fields"]["project"]["key"], "TEST_PROJECT")

    def test_ignores_stray_jira_project_key_env_var(self):
        """Even if a leftover JIRA_PROJECT_KEY env var exists (e.g. an old
        .env file nobody cleaned up), it must never be used as a fallback
        or override the caller-supplied project_key."""
        os.environ["JIRA_PROJECT_KEY"] = "LEFTOVER_ENV_VALUE"
        try:
            result = self.svc.create_issue(
                project_key="EXPLICIT_PROJECT", summary="Test", description="",
                priority=None, issue_type="story", epic_name=None,
            )
        finally:
            del os.environ["JIRA_PROJECT_KEY"]

        create_calls = [c for c in self.call_log
                         if c["url"].endswith("/rest/api/3/issue") and c["method"] == "POST"]
        sent_key = create_calls[0]["kwargs"]["json"]["fields"]["project"]["key"]
        self.assertEqual(sent_key, "EXPLICIT_PROJECT")
        self.assertNotEqual(sent_key, "LEFTOVER_ENV_VALUE")


class CreateIssuesBulkProjectKeyTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_missing_project_key_on_any_issue_fails_before_any_api_call(self):
        issues = [
            {"project_key": "TEST_PROJECT_A", "summary": "Has project key"},
            {"summary": "Missing project key"},
        ]
        with self.assertRaises(JiraValidationError):
            self.svc.create_issues_bulk(issues)
        self.assertEqual(self.call_log, [], "No Jira API call should happen if any issue lacks project_key.")

    def test_blank_project_key_on_any_issue_fails_before_any_api_call(self):
        issues = [
            {"project_key": "TEST_PROJECT_A", "summary": "Has project key"},
            {"project_key": "   ", "summary": "Blank project key"},
        ]
        with self.assertRaises(JiraValidationError):
            self.svc.create_issues_bulk(issues)
        self.assertEqual(self.call_log, [])

    def test_uses_exact_per_issue_project_keys(self):
        issues = [
            {"project_key": "TEST_PROJECT_A", "summary": "Issue A"},
            {"project_key": "TEST_PROJECT_B", "summary": "Issue B", "issue_type": "bug"},
        ]
        result = self.svc.create_issues_bulk(issues)
        payload = json.loads(result)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["total_created"], 2)

        bulk_calls = [c for c in self.call_log if c["url"].endswith("/rest/api/3/issue/bulk")]
        self.assertEqual(len(bulk_calls), 1)
        sent_updates = bulk_calls[0]["kwargs"]["json"]["issueUpdates"]
        self.assertEqual(sent_updates[0]["fields"]["project"]["key"], "TEST_PROJECT_A")
        self.assertEqual(sent_updates[1]["fields"]["project"]["key"], "TEST_PROJECT_B")

        # Issue-type lookup must happen per distinct project, not once globally.
        createmeta_urls = [c["url"] for c in self.call_log if "createmeta" in c["url"]]
        self.assertTrue(any("projectKeys=TEST_PROJECT_A" in u for u in createmeta_urls))
        self.assertTrue(any("projectKeys=TEST_PROJECT_B" in u for u in createmeta_urls))


class SearchIssuesNoProjectInjectionTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_jql_passed_through_unchanged_no_project_injected(self):
        jql = "assignee = currentUser() ORDER BY updated DESC"
        self.svc.search_issues(jql)

        search_calls = [c for c in self.call_log if "/search/jql" in c["url"]]
        self.assertEqual(len(search_calls), 1)
        sent_jql = search_calls[0]["kwargs"]["params"]["jql"]
        self.assertEqual(sent_jql, jql, "search_issues must forward the caller's JQL completely unchanged.")


class IssueKeyOnlyOperationsUnaffectedTests(unittest.TestCase):
    """Regression check: operations keyed by issue_key must keep working
    with zero project_key dependency added, and get_issues_bulk must use
    only the caller-supplied project/epic key."""

    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_get_issue_no_project_involved(self):
        result = self.svc.get_issue("MOCK-1")
        payload = json.loads(result)
        self.assertEqual(payload["key"], "MOCK-1")

    def test_get_issues_bulk_uses_only_caller_supplied_project_key(self):
        self.svc.get_issues_bulk("TEST_PROJECT")
        search_calls = [c for c in self.call_log if "/search/jql" in c["url"]]
        self.assertIn("project = TEST_PROJECT", search_calls[0]["kwargs"]["params"]["jql"])


if __name__ == "__main__":
    unittest.main()
