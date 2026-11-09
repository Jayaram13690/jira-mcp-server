# fields.py
"""Jira field metadata: issue types, priorities and the epic custom fields (FR-14, FR-22).

Moved unchanged from JiraService (P2.3), including the known cache behaviour
tracked as DEF-12 / T-14: the "loaded" flag is set *before* the `/field` request,
so a failed lookup is never retried for the lifetime of the instance. Issue types
are looked up per project on every call and never cached (FR-14).

The request path is injected, so this module knows nothing about HTTP clients,
MCP or the facade.
"""
import logging

from src.exceptions.exceptions import JiraValidationError
from src.services.jira_client import RequestFn

logger = logging.getLogger("jira-mcp-server")


class JiraFields:
    def __init__(self, request: RequestFn) -> None:
        self._request = request
        self._epic_name_field: str | None = None
        self._epic_link_field: str | None = None
        self._custom_fields_loaded = False

    @property
    def epic_name_field(self) -> str | None:
        return self._epic_name_field

    @property
    def epic_link_field(self) -> str | None:
        return self._epic_link_field

    def load_custom_fields(self) -> None:
        if self._custom_fields_loaded:
            return
        self._custom_fields_loaded = True
        fields = self._request("GET", "/rest/api/3/field").json()
        for f in fields:
            if f["name"] == "Epic Name":
                self._epic_name_field = f["id"]
            elif f["name"] == "Epic Link":
                self._epic_link_field = f["id"]
        if self._epic_name_field:
            logger.info(f"Company-managed project detected: Epic Name field = {self._epic_name_field}")
        else:
            logger.info("Team-managed project detected: no 'Epic Name' custom field — epics will use summary as name")
        if self._epic_link_field:
            logger.info(f"Epic Link field = {self._epic_link_field}")
        else:
            logger.info("No 'Epic Link' custom field — stories will use parent field for epic linking")

    def get_issue_types(self, project_key: str) -> dict[str, str]:
        """Looks up the valid issue types for a specific Jira project.

        project_key is required and must come from the caller — there is
        no server-side default project. Different projects can have
        different issue-type schemes, so this must be looked up per
        project rather than once globally.
        """
        if not project_key or not project_key.strip():
            raise JiraValidationError(
                "project_key is required and must be a non-empty string. "
                "No default project is configured — the caller must supply the target Jira project key."
            )
        meta = self._request("GET", f"/rest/api/3/issue/createmeta?projectKeys={project_key.strip()}").json()
        payload = {t["name"].lower(): t["name"] for t in meta["projects"][0]["issuetypes"]}
        # return json.dumps(payload)
        return payload

    def get_priorities(self) -> list[str]:
        return [p["name"] for p in self._request("GET", "/rest/api/3/priority").json()]
