# issues.py
"""Single-issue operations: create, read, update, labels, comments, links (FR-1..3, 6..10, 14, 20..22).

Moved unchanged from JiraService (P2.6); search moved to `search.py` (P2.8). Tracked defects are preserved on purpose
(T-8 key validation, T-13 null priority, T-14 epic cache, T-19 print(), T-25 link schemes,
T-26 description reading): fix them in their own tasks, not here.

The request path and field metadata are injected; nothing here knows about the HTTP
client, MCP, or the JiraService facade.
"""
import json

from src.config import config
from src.exceptions.exceptions import JiraValidationError
from src.services.adf import (
    build_comment_body,
    build_comment_with_links_body,
    build_rich_text,
    extract_plain_text,
)
from src.services.fields import JiraFields
from src.services.jira_client import RequestFn


class IssueOperations:
    def __init__(self, request: RequestFn, fields: JiraFields) -> None:
        self._request = request
        self._fields = fields

    def create_issue(self, project_key: str, summary: str, description: str, priority: str | None,
                     issue_type: str, epic_name: str | None, labels: list[str] | None = None,
                     parent: str | None = None) -> str:
        # project_key is required and must come from the caller. Validate
        # it before touching the Jira API at all - no default/fallback
        # project, and no partial work if it's missing.
        if not project_key or not project_key.strip():
            raise JiraValidationError(
                "project_key is required and must be a non-empty string. "
                "No default project is configured — you must specify the target Jira project key."
            )
        project_key = project_key.strip()

        self._fields.load_custom_fields()
        # issue_types = self._fields.get_issue_types()
        available_issue_types = self._fields.get_issue_types(project_key)
        priorities = self._fields.get_priorities()

        issue_type_clean = issue_type.strip().lower()

        print("issue_type_clean", issue_type_clean)

        if issue_type_clean not in available_issue_types:
            valid_types = ", ".join(available_issue_types.keys())
            raise JiraValidationError(f"Invalid issue type: '{issue_type}'. Valid types are: {valid_types}")

        print("available_issue_types[issue_type_clean]", available_issue_types[issue_type_clean])

        fields = {
            "project": {"key": project_key},
            # "issuetype": {"name": issue_types[issue_type_clean]},
            "issuetype": {"name": available_issue_types[issue_type_clean]},
            "summary": summary,
            "description": build_rich_text(description),
        }

        if priority:
            priority = priority.capitalize()
            if priority not in priorities:
                raise JiraValidationError(f"Invalid priority: {priority}")
            fields["priority"] = {"name": priority}
        else:
            priority = "Low"
            fields["priority"] = {"name": priority}

        # Handle epic name — only set if the project has an Epic Name
        # custom field (company-managed projects). Team-managed projects
        # use summary as the epic name and don't have this field.
        if issue_type_clean == "epic" and epic_name and self._fields.epic_name_field:
            fields[self._fields.epic_name_field] = epic_name

        # Add labels if provided
        if labels and isinstance(labels, list):
            # Filter out empty strings and ensure all labels are strings
            valid_labels = [str(label).strip() for label in labels if label and str(label).strip()]
            if valid_labels:
                fields["labels"] = valid_labels

        # Add parent if provided (e.g., to link a story to an epic)
        if parent:
            fields["parent"] = {"key": parent.strip()}

        data = self._request("POST", "/rest/api/3/issue", json={"fields": fields}).json()
        payload = {
            "message": "Issue created successfully",
            "key": data["key"],
            "url": f"{config.JIRA_URL}/browse/{data['key']}",
            "summary": summary,
            "type": available_issue_types[issue_type_clean],
        }
        return json.dumps(payload)  # <-- returns a str

    def update_issue(self, key: str, summary: str | None, description: str | None,
                     priority: str | None) -> str:
        fields = {}
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = build_rich_text(description)
        if priority:
            priority = priority.capitalize()
            if priority not in self._fields.get_priorities():
                raise JiraValidationError(f"Invalid priority: {priority}")
            fields["priority"] = {"name": priority}

        if not fields:
            raise JiraValidationError("Nothing to update.")

        self._request("PUT", f"/rest/api/3/issue/{key}", json={"fields": fields})
        payload = {
            "message": f"Issue {key} updated successfully",
            "key": key,
            "updated_fields": list(fields.keys())
        }
        return json.dumps(payload)

    def update_labels(self, key: str, add_labels: list[str] | None = None,
                      remove_labels: list[str] | None = None) -> str:
        """Adds and/or removes specific labels on an issue without
        replacing the whole labels array."""
        operations = []
        for label in (add_labels or []):
            operations.append({"add": label})
        for label in (remove_labels or []):
            operations.append({"remove": label})

        if not operations:
            raise JiraValidationError("Nothing to update - no labels given to add or remove.")

        self._request("PUT", f"/rest/api/3/issue/{key}", json={"update": {"labels": operations}})
        payload = {
            "message": f"Labels updated on {key}",
            "key": key,
            "added": add_labels or [],
            "removed": remove_labels or [],
        }
        return json.dumps(payload)

    def add_remote_link(self, key: str, url: str, title: str) -> str:
        """Adds a real remote link object to an issue via Jira's Remote
        Issue Link API."""
        body = {"object": {"url": url, "title": title}}
        # TestRail links: show the TestRail icon and group them under a
        # "TestRail" heading in Jira (same as the original REST implementation).
        if "testrail" in url.lower():
            body["object"]["icon"] = {"url16x16": "https://www.testrail.com/favicon.ico", "title": "TestRail"}
            body["application"] = {"type": "com.testrail", "name": "TestRail"}
            body["relationship"] = "Test Case"
        self._request("POST", f"/rest/api/3/issue/{key}/remotelink", json=body)
        payload = {"message": f"Remote link added to {key}", "key": key, "url": url, "title": title}
        return json.dumps(payload)

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> str:
        self._fields.load_custom_fields()
        if self._fields.epic_link_field:
            # Company-managed: use the Epic Link custom field
            self._request("PUT", f"/rest/api/3/issue/{issue_key}", json={
                "fields": {self._fields.epic_link_field: epic_key}
            })
        else:
            # Team-managed: use the parent field instead
            self._request("PUT", f"/rest/api/3/issue/{issue_key}", json={
                "fields": {"parent": {"key": epic_key}}
            })
        payload = {
            "message": f"Issue {issue_key} linked to epic {epic_key}",
            "issue": issue_key,
            "epic": epic_key
        }
        return json.dumps(payload)

    def add_comment(self, key: str, comment: str) -> str:
        body = build_comment_body(comment)
        self._request("POST", f"/rest/api/3/issue/{key}/comment", json=body)
        payload = {
            "message": f"Comment added to issue {key}",
            "issue": key,
            "comment": comment
        }
        return json.dumps(payload)

    def add_comment_with_links(self, key: str, intro_text: str, links: list[dict]) -> str:
        """
        Builds a single comment where each item in `links` (each a
        {"text": str, "url": str}) renders as a real clickable link,
        rather than plain text. Jira's rich-text comment format
        requires an explicit link mark per text run - a raw URL string
        embedded in plain text does not become clickable on its own.
        """
        body = build_comment_with_links_body(intro_text, links)
        self._request("POST", f"/rest/api/3/issue/{key}/comment", json=body)
        payload = {"message": f"Comment with links added to issue {key}", "issue": key}
        return json.dumps(payload)

    # displays detailed info of 1 issue
    def get_issue(self, key: str) -> str:
        data = self._request("GET", f"/rest/api/3/issue/{key}").json()
        fields = data["fields"]

        # Get parent info if present
        parent_info = None
        if fields.get("parent"):
            parent_info = {
                "key": fields["parent"].get("key"),
                "summary": fields["parent"].get("fields", {}).get("summary")
            }

        payload = {
            "key": key,
            "summary": fields["summary"],
            "status": fields["status"]["name"],
            "priority": fields["priority"]["name"],
            "description": extract_plain_text(fields),
            "labels": fields.get("labels", []),  # Get labels, default to empty list if not present
            "parent": parent_info  # Will be None if no parent, or a dict with key and summary
        }
        return json.dumps(payload)
