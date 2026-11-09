"""
Seam tests for the P2.8 modules: `search.IssueSearch` and `bulk_create.BulkIssueCreator`.

Behaviour (pagination, caps, payloads, errors) is pinned end-to-end by
tests/test_service_golden.py against the original implementation. These tests only prove
each module works with nothing but an injected request - no facade, no HTTP, no session -
and that the dependency profile that justified the split holds.
"""
import inspect
import json
import unittest

from src.config import config
from src.exceptions.exceptions import JiraValidationError
from src.services.bulk_create import BulkIssueCreator
from src.services.fields import JiraFields
from src.services.search import IssueSearch
from tests._mock_jira_api import FakeResponse


def _issue(key, issue_type="Story"):
    return {"key": key, "fields": {
        "summary": f"s {key}", "status": {"name": "To Do"}, "priority": {"name": "High"},
        "labels": [], "issuetype": {"name": issue_type},
        "description": {"content": [{"content": [{"type": "text", "text": "d"}]}]},
    }}


class FakeJira:
    """Records (method, path, kwargs); answers from a path -> response function."""

    def __init__(self, responder):
        self.calls, self._responder = [], responder

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self._responder(method, path, kwargs)


class IssueSearchTests(unittest.TestCase):
    def test_needs_only_a_request_callable(self):
        self.assertEqual(list(inspect.signature(IssueSearch.__init__).parameters), ["self", "request"])

    def test_search_issues_single_page(self):
        fake = FakeJira(lambda m, p, k: FakeResponse(200, {"issues": [_issue("S-1")], "isLast": True}))
        result = json.loads(IssueSearch(fake).search_issues("project = X"))
        self.assertEqual([c[:2] for c in fake.calls], [("GET", "/rest/api/3/search/jql")])
        self.assertEqual(fake.calls[0][2]["params"]["jql"], "project = X")
        self.assertEqual(result["results"][0]["key"], "S-1")
        self.assertEqual(result["results"][0]["url"], f"{config.JIRA_URL.rstrip('/')}/browse/S-1")

    def test_get_issues_bulk_project_key_builds_project_jql(self):
        fake = FakeJira(lambda m, p, k: FakeResponse(200, {"issues": [_issue("P-1")], "isLast": True}))
        result = json.loads(IssueSearch(fake).get_issues_bulk("PRJ"))
        self.assertEqual(fake.calls[0][2]["params"]["jql"], "project = PRJ ORDER BY key ASC")
        self.assertTrue(result["success"])
        self.assertEqual(result["fetch_mode"], "all issues in project PRJ")

    def test_get_issues_bulk_issue_key_verifies_epic_first(self):
        def responder(method, path, kwargs):
            if path.endswith("/issue/EP-1"):
                return FakeResponse(200, {"fields": {"summary": "E", "issuetype": {"name": "Epic"}}})
            return FakeResponse(200, {"issues": [_issue("EP-1", "Epic")], "isLast": True})

        fake = FakeJira(responder)
        result = json.loads(IssueSearch(fake).get_issues_bulk("EP-1"))
        self.assertEqual([c[1] for c in fake.calls], ["/rest/api/3/issue/EP-1", "/rest/api/3/search/jql"])
        self.assertEqual(fake.calls[1][2]["params"]["jql"], "(key = EP-1 OR parent = EP-1) ORDER BY key ASC")
        self.assertTrue(result["success"])

    def test_get_issues_bulk_blank_key_refused_before_any_request(self):
        fake = FakeJira(lambda m, p, k: FakeResponse(200, {}))
        with self.assertRaises(JiraValidationError):
            IssueSearch(fake).get_issues_bulk("")
        self.assertEqual(fake.calls, [])


class BulkIssueCreatorTests(unittest.TestCase):
    @staticmethod
    def _jira():
        def responder(method, path, kwargs):
            if path.endswith("/field"):
                return FakeResponse(200, [{"id": "cf_epic", "name": "Epic Name"}])
            if path.endswith("/priority"):
                return FakeResponse(200, [{"name": "High"}, {"name": "Low"}])
            if "createmeta" in path:
                return FakeResponse(200, {"projects": [{"issuetypes": [{"name": "Story"}]}]})
            return FakeResponse(201, {"issues": [{"key": "A-1"}]})
        return FakeJira(responder)

    def _creator(self, fake):
        return BulkIssueCreator(fake, JiraFields(fake))

    def test_signature_is_request_and_fields(self):
        self.assertEqual(list(inspect.signature(BulkIssueCreator.__init__).parameters),
                         ["self", "request", "fields"])

    def test_missing_project_key_refused_before_any_request(self):
        fake = self._jira()
        with self.assertRaises(JiraValidationError):
            self._creator(fake).create_issues_bulk([{"summary": "x"}])
        self.assertEqual(fake.calls, [])

    def test_request_order_and_single_bulk_post(self):
        fake = self._jira()
        result = json.loads(self._creator(fake).create_issues_bulk(
            [{"project_key": "A", "summary": "one", "description": "d"}]))
        self.assertEqual([(m, p) for m, p, _ in fake.calls], [
            ("GET", "/rest/api/3/field"),
            ("GET", "/rest/api/3/priority"),
            ("GET", "/rest/api/3/issue/createmeta?projectKeys=A"),
            ("POST", "/rest/api/3/issue/bulk"),
        ])
        sent = fake.calls[-1][2]["json"]["issueUpdates"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["fields"]["project"], {"key": "A"})
        self.assertEqual(sent[0]["fields"]["priority"], {"name": "Low"})
        self.assertTrue(result["success"])
        self.assertEqual(result["total_created"], 1)


if __name__ == "__main__":
    unittest.main()
