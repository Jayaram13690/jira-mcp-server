# jira_service.py
import logging
from typing import Any

from src.services import attachments, transitions
from src.services.adf import build_rich_text, extract_plain_text
from src.services.bulk_create import BulkIssueCreator
from src.services.fields import JiraFields
from src.services.issues import IssueOperations
from src.services.jira_client import JiraClient
from src.services.search import IssueSearch
from src.utils.log_helper import (
    log_method_calls,
    setup_logging,
)

try:
    setup_logging()
    logger = logging.getLogger("jira-mcp-server")
    logger.debug("Initializing jira MCP server at module level...")
except Exception as e:
    print(f"Logging setup error during initialization: {e}")
    raise


class JiraService:
    @log_method_calls
    def __init__(self):

        self._client = JiraClient()
        self._fields = JiraFields(self._dispatch_request)
        self._issues = IssueOperations(self._dispatch_request, self._fields)
        self._search = IssueSearch(self._dispatch_request)
        self._bulk = BulkIssueCreator(self._dispatch_request, self._fields)

    @property
    def session(self):
        # The session lives on the client (single source of truth); this keeps
        # `svc.session` readable and assignable for existing callers.
        return self._client.session

    @session.setter
    def session(self, value):
        self._client.session = value

    @log_method_calls
    def _request(self, method: str, path: str, **kwargs):
        return self._client.request(method, path, **kwargs)

    def _dispatch_request(self, method: str, path: str, **kwargs):
        # What extracted components call. Resolves `self._request` at call time so the
        # logged, patchable facade method stays the single request path.
        return self._request(method, path, **kwargs)

    @log_method_calls
    def _load_custom_fields(self):
        self._fields.load_custom_fields()

    @log_method_calls
    def get_issue_types(self, project_key: str) -> dict[str, str]:
        return self._fields.get_issue_types(project_key)

    @log_method_calls
    def get_priorities(self) -> list[str]:
        return self._fields.get_priorities()

    @log_method_calls
    def create_issue(self, project_key: str, summary: str, description: str, priority: str | None,
                     issue_type: str, epic_name: str | None, labels: list[str] | None = None,
                     parent: str | None = None) -> str:
        """Create an issue in the caller-supplied project (no default project)."""
        return self._issues.create_issue(project_key, summary, description, priority, issue_type, epic_name, labels, parent)

    @log_method_calls
    def update_issue(self, key: str, summary: str | None, description: str | None,
                     priority: str | None) -> str:
        """Update summary, description or priority of an issue."""
        return self._issues.update_issue(key, summary, description, priority)

    @log_method_calls
    def update_labels(self, key: str, add_labels: list[str] | None = None,
                      remove_labels: list[str] | None = None) -> str:
        """Add and/or remove labels on an issue."""
        return self._issues.update_labels(key, add_labels, remove_labels)

    @log_method_calls
    def add_remote_link(self, key: str, url: str, title: str) -> str:
        """Add a remote link object to an issue."""
        return self._issues.add_remote_link(key, url, title)

    @log_method_calls
    def add_attachment(self, key: str, file_path: str | None = None, filename: str | None = None,
                       content_base64: str | None = None, mime_type: str | None = None) -> str:
        """Attach a file (path or base64 content) to an issue."""
        return attachments.add_attachment(self._dispatch_request, key, file_path, filename, content_base64, mime_type)

    @log_method_calls
    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> str:
        """Link an issue to an epic (Epic Link field or parent)."""
        return self._issues.link_issue_to_epic(issue_key, epic_key)

    @log_method_calls
    def add_comment(self, key: str, comment: str) -> str:
        """Add a plain-text comment to an issue."""
        return self._issues.add_comment(key, comment)

    @log_method_calls
    def transition_issue(self, key: str, target_status: str) -> str:
        """Move an issue to a target status by resolving the real transition ID."""
        return transitions.transition_issue(self._dispatch_request, key, target_status)

    @log_method_calls
    def add_comment_with_links(self, key: str, intro_text: str, links: list[dict]) -> str:
        """Add a comment whose links render as clickable links."""
        return self._issues.add_comment_with_links(key, intro_text, links)

    @log_method_calls
    def get_issue(self, key: str) -> str:
        """Return the details of one issue."""
        return self._issues.get_issue(key)

    # gets detailed info of all issues from a project or epic (implementation: services/search.py)
    @log_method_calls
    def get_issues_bulk(self, project_key: str, max_results: int = None, fetch_all: bool = True) -> str:
        """Fetch details for all issues of a project or an epic (epic + children), paginated."""
        return self._search.get_issues_bulk(project_key, max_results, fetch_all)

    @log_method_calls
    def search_issues(self, jql: str, max_results: int = 0) -> str:
        """Search issues with JQL, paginating automatically."""
        return self._search.search_issues(jql, max_results)

    @log_method_calls
    def _as_rich_text(self, text: str) -> dict[str, Any]:
        return build_rich_text(text)

    @log_method_calls
    def _readable_desc(self, fields: dict[str, Any]) -> str:
        return extract_plain_text(fields)

    @log_method_calls
    def create_issues_bulk(self, issues: list[dict[str, Any]]) -> str:
        """Create multiple issues in one call; every issue carries its own project_key."""
        return self._bulk.create_issues_bulk(issues)
