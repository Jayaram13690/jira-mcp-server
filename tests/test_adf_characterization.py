"""
Characterization tests for the ADF / rich-text behaviour of JiraService.

P2.1 / FR-20: these pin what the service sends to and reads from Jira today.
They go through JiraService only, so they pass unchanged before and after the
helpers move into src/services/adf.py. They deliberately pin current quirks
(e.g. _readable_desc's flattening); changing those belongs to T-26, not P2.1.

All Jira HTTP is mocked (tests/_mock_jira_api.py) - no network.
"""
import json
import unittest

from src.services.jira_service import JiraService
from tests._mock_jira_api import FakeResponse, default_handler, install_mock


def _doc(text):
    return {
        "type": "doc", "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _issue_handler(description_field):
    """default_handler, except GET /issue/<key> returns the given 'description'."""
    def handler(method, url, **kwargs):
        if method == "GET" and "/issue/" in url and "/search" not in url and "/transitions" not in url:
            fields = {
                "summary": "S", "status": {"name": "To Do"},
                "priority": {"name": "Medium"}, "labels": [],
            }
            if description_field is not _ABSENT:
                fields["description"] = description_field
            return FakeResponse(200, {"fields": fields})
        return default_handler(method, url, **kwargs)
    return handler


_ABSENT = object()


class AsRichTextTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def test_as_rich_text_exact_structure(self):
        self.assertEqual(self.svc._as_rich_text("hello"), _doc("hello"))

    def test_as_rich_text_empty_string_is_kept(self):
        self.assertEqual(self.svc._as_rich_text(""), _doc(""))

    def test_create_issue_sends_description_as_adf(self):
        self.svc.create_issue(
            project_key="TST", summary="S", description="desc",
            priority=None, issue_type="story", epic_name=None,
        )
        posts = [c for c in self.call_log
                 if c["method"] == "POST" and c["url"].endswith("/rest/api/3/issue")]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["kwargs"]["json"]["fields"]["description"], _doc("desc"))

    def test_update_issue_sends_description_as_adf(self):
        self.svc.update_issue("TST-1", None, "new desc", None)
        puts = [c for c in self.call_log if c["method"] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertEqual(puts[0]["kwargs"]["json"]["fields"]["description"], _doc("new desc"))

    def test_create_issues_bulk_sends_description_as_adf(self):
        self.svc.create_issues_bulk([
            {"project_key": "TST", "summary": "A", "description": "da"},
        ])
        bulk = [c for c in self.call_log if c["url"].endswith("/rest/api/3/issue/bulk")]
        self.assertEqual(len(bulk), 1)
        update = bulk[0]["kwargs"]["json"]["issueUpdates"][0]
        self.assertEqual(update["fields"]["description"], _doc("da"))


class CommentBodyTests(unittest.TestCase):
    def setUp(self):
        self.call_log, self._restore = install_mock()
        self.svc = JiraService()

    def tearDown(self):
        self._restore()

    def _comment_posts(self):
        return [c for c in self.call_log if c["url"].endswith("/comment")]

    def test_add_comment_request_body(self):
        result = json.loads(self.svc.add_comment("TST-1", "hi there"))
        posts = self._comment_posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["method"], "POST")
        self.assertTrue(posts[0]["url"].endswith("/rest/api/3/issue/TST-1/comment"))
        self.assertEqual(posts[0]["kwargs"]["json"], {"body": _doc("hi there")})
        self.assertEqual(result, {
            "message": "Comment added to issue TST-1", "issue": "TST-1", "comment": "hi there",
        })

    def test_add_comment_with_links_request_body(self):
        links = [
            {"text": "One", "url": "https://a.example/1"},
            {"text": "Two", "url": "https://a.example/2"},
        ]
        result = json.loads(self.svc.add_comment_with_links("TST-1", "See: ", links))
        posts = self._comment_posts()
        self.assertEqual(len(posts), 1)

        def link(text, url):
            return {"type": "text", "text": text,
                    "marks": [{"type": "link", "attrs": {"href": url}}]}

        expected = {"body": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "See: "},
                link("One", "https://a.example/1"),
                {"type": "text", "text": ", "},
                link("Two", "https://a.example/2"),
            ]},
        ]}}
        self.assertEqual(posts[0]["kwargs"]["json"], expected)
        self.assertEqual(result, {
            "message": "Comment with links added to issue TST-1", "issue": "TST-1",
        })

    def test_add_comment_with_links_single_link_has_no_separator(self):
        self.svc.add_comment_with_links("TST-1", "x", [{"text": "T", "url": "https://u"}])
        content = self._comment_posts()[0]["kwargs"]["json"]["body"]["content"][0]["content"]
        self.assertEqual([c["text"] for c in content], ["x", "T"])

    def test_add_comment_with_links_no_links_is_intro_only(self):
        self.svc.add_comment_with_links("TST-1", "only intro", [])
        content = self._comment_posts()[0]["kwargs"]["json"]["body"]["content"][0]["content"]
        self.assertEqual(content, [{"type": "text", "text": "only intro"}])


class ReadableDescTests(unittest.TestCase):
    def tearDown(self):
        self._restore()

    def _description_via_get_issue(self, description_field):
        self.call_log, self._restore = install_mock(_issue_handler(description_field))
        svc = JiraService()
        return json.loads(svc.get_issue("TST-1"))["description"]

    def test_single_paragraph_is_flattened(self):
        self.assertEqual(self._description_via_get_issue(_doc("hello world")), "hello world")

    def test_multiple_paragraphs_and_runs_joined_with_single_space(self):
        desc = {"content": [
            {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
            {"content": [{"type": "text", "text": "c"}]},
        ]}
        self.assertEqual(self._description_via_get_issue(desc), "a b c")

    def test_non_text_nodes_are_skipped(self):
        desc = {"content": [{"content": [
            {"type": "text", "text": "keep"}, {"type": "hardBreak"},
            {"type": "text", "text": "this"},
        ]}]}
        self.assertEqual(self._description_via_get_issue(desc), "keep this")

    def test_block_without_content_contributes_nothing(self):
        desc = {"content": [{"type": "rule"}, {"content": [{"type": "text", "text": "x"}]}]}
        self.assertEqual(self._description_via_get_issue(desc), "x")

    def test_absent_description_reads_as_no_description(self):
        self.assertEqual(self._description_via_get_issue(_ABSENT), "No description.")

    def test_null_description_reads_as_no_description(self):
        self.assertEqual(self._description_via_get_issue(None), "No description.")

    def test_malformed_description_reads_as_no_description(self):
        for bad in ("plain string", {"content": "nope"}, {"content": [{"content": [{"text": "x"}]}]}):
            with self.subTest(description=repr(bad)):
                self.assertEqual(self._description_via_get_issue(bad), "No description.")
                self._restore()

    def test_nested_list_text_is_not_reached_today(self):
        """Pins current behaviour (T-26 will change it): nested text is skipped, result is ''."""
        desc = {"content": [{"type": "bulletList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "nested"}]}]},
        ]}]}
        self.assertEqual(self._description_via_get_issue(desc), "")


class AdfModuleTests(unittest.TestCase):
    """P2.1: the extracted pure functions and the facade delegates agree."""

    def test_module_is_pure_stdlib(self):
        import ast
        from pathlib import Path

        from src.services import adf

        tree = ast.parse(Path(adf.__file__).read_text(encoding="utf-8"))
        imported = {
            (n.module if isinstance(n, ast.ImportFrom) else a.name)
            for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        }
        self.assertEqual(imported, {"typing"})

    def test_functions_match_service_delegates(self):
        from src.services import adf

        svc = JiraService()
        self.assertEqual(adf.build_rich_text("t"), svc._as_rich_text("t"))
        self.assertEqual(adf.extract_plain_text({}), svc._readable_desc({}))
        self.assertEqual(adf.build_comment_body("c"), {"body": _doc("c")})
