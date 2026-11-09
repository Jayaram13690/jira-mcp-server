# bulk_create.py
"""Bulk issue creation across projects (FR-5).

Moved unchanged from `bulk.py` (P2.8). Tracked defects are preserved on purpose and are
fixed in their own tasks, not here: result attribution by `issues[len(created)]` and the
`success` flag (DEF-13, T-12), key validation (T-8), `print()` / `traceback` output (T-19).

The request path and field metadata are injected; nothing here knows about the HTTP
client, MCP, or the JiraService facade.
"""
import json
import traceback
from typing import Any

from src.config import config
from src.exceptions.exceptions import JiraValidationError
from src.services.adf import build_rich_text
from src.services.fields import JiraFields
from src.services.jira_client import RequestFn


class BulkIssueCreator:
    def __init__(self, request: RequestFn, fields: JiraFields) -> None:
        self._request = request
        self._fields = fields

    def create_issues_bulk(self, issues: list[dict[str, Any]]) -> str:
        """
        Creates multiple Jira issues in bulk using the Jira Cloud REST API.

        Args:
            issues: List of issue dictionaries, each containing:
                - project_key (required): Target Jira project key for this issue.
                  There is no default/fallback project - every issue must
                  specify its own, and different issues in the same call
                  may target different projects.
                - summary (required): Issue title
                - description (optional): Issue description
                - issue_type (optional): Issue type (default: "story")
                - priority (optional): Priority level
                - epic_name (optional): Only for epic issue types
                - labels (optional): List of labels to add to the issue
                - parent (optional): Parent issue key to link at creation time

        Returns:
            JSON string with created issues and any errors
        """
        # Validate every issue up front, before making ANY Jira API call.
        # No default project: if even one issue is missing project_key,
        # fail the whole batch now rather than partially creating issues.
        for idx, issue in enumerate(issues):
            pk = issue.get("project_key") if isinstance(issue, dict) else None
            if not pk or not isinstance(pk, str) or not pk.strip():
                raise JiraValidationError(
                    f"Issue at index {idx}: 'project_key' is required and must be a non-empty string. "
                    "No default project is configured — every issue must specify its target Jira project key."
                )

        self._fields.load_custom_fields()
        priorities = self._fields.get_priorities()
        # Issue types can differ per project, so look them up per distinct
        # project_key encountered rather than once globally.
        issue_types_by_project: dict[str, dict[str, str]] = {}

        # Prepare issue updates for bulk creation
        issue_updates = []

        for idx, issue in enumerate(issues):
            try:
                project_key = issue["project_key"].strip()

                # Validate required fields
                if "summary" not in issue:
                    raise JiraValidationError(f"Issue at index {idx}: 'summary' is required")

                if project_key not in issue_types_by_project:
                    issue_types_by_project[project_key] = self._fields.get_issue_types(project_key)
                available_issue_types = issue_types_by_project[project_key]

                # Get and validate issue type
                issue_type = issue.get("issue_type", "story").strip().lower()
                if issue_type not in available_issue_types:
                    valid_types = ", ".join(available_issue_types.keys())
                    raise JiraValidationError(
                        f"Issue at index {idx}: Invalid issue type '{issue_type}'. Valid types are: {valid_types}")

                # Build fields
                fields = {
                    "project": {"key": project_key},
                    "issuetype": {"name": available_issue_types[issue_type]},
                    "summary": issue["summary"],
                    "description": build_rich_text(issue.get("description", "")),
                }

                # Handle priority
                priority = issue.get("priority")
                if priority:
                    priority = priority.capitalize()
                    if priority not in priorities:
                        raise JiraValidationError(f"Issue at index {idx}: Invalid priority '{priority}'")
                    fields["priority"] = {"name": priority}
                else:
                    fields["priority"] = {"name": "Low"}

                # Handle epic name — only set if the project has an Epic Name
                # custom field (company-managed projects). Team-managed projects
                # use summary as the epic name and don't have this field.
                if issue_type == "epic" and "epic_name" in issue and self._fields.epic_name_field:
                    fields[self._fields.epic_name_field] = issue["epic_name"]

                # Handle labels
                labels = issue.get("labels")
                if labels and isinstance(labels, list):
                    # Filter out empty strings and ensure all labels are strings
                    valid_labels = [str(label).strip() for label in labels if label and str(label).strip()]
                    if valid_labels:
                        fields["labels"] = valid_labels

                # Handle parent (to link issue to epic or parent at creation time)
                parent = issue.get("parent")
                if parent:
                    fields["parent"] = {"key": parent.strip()}

                issue_updates.append({"fields": fields})

            except Exception as e:
                # Return error early if validation fails
                print("Error in issue at index", idx, ":", str(e))
                traceback.print_exc()
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "failed_at_index": idx
                })

        # Make bulk create request
        try:
            print("Creating issues in bulk -- service:", issue_updates)
            response = self._request("POST", "/rest/api/3/issue/bulk", json={"issueUpdates": issue_updates})
            data = response.json()

            # Parse results
            created_issues = []
            errors = []

            if "issues" in data:
                for issue_data in data["issues"]:
                    created_issues.append({
                        "key": issue_data["key"],
                        "url": f"{config.JIRA_URL}/browse/{issue_data['key']}",
                        "summary": issues[len(created_issues)]["summary"]
                    })

            if "errors" in data:
                for error in data["errors"]:
                    errors.append({
                        "index": error.get("failedElementNumber"),
                        "error": error.get("elementErrors", {})
                    })

            payload = {
                "success": True,
                "message": f"Created {len(created_issues)} issues successfully",
                "created_issues": created_issues,
                "total_requested": len(issues),
                "total_created": len(created_issues),
                "errors": errors if errors else None
            }

            return json.dumps(payload)

        except Exception as e:
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "error": f"Bulk creation failed: {e!s}"
            })
