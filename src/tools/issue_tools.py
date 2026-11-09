"""Issue tools: create, update, get, link to epic, transition (FR-1..3, 9, 13).

Handlers read the service through `jira()` at call time so tests can substitute
`jira_tools._jira` with patch.object.
"""
import asyncio
from collections.abc import Callable
from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from src.exceptions.exceptions import JiraValidationError
from src.services.jira_service import JiraService
from src.utils.log_helper import log_async_method_calls


def register_create_issue_tool(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-createIssue",
        description="Creates a new Jira issue in the given project. Use 'epic' as the issue_type to create an Epic. Supports optional priority, epic name, labels, and parent (to link to an epic or parent issue at creation time). project_key is required - there is no default project, so the caller must always specify which Jira project the issue belongs to.",
        tags={"jira", "write"}
    )
    @log_async_method_calls
    async def create_issue(
        ctx: Context,
        project_key: Annotated[str, Field(description="Target Jira project key (e.g., 'RET'). Required - there is no default project.")],
        summary: Annotated[str, Field(description="Short title for the issue")],
        description: Annotated[str, Field(description="Detailed description (optional)")] = "",
        issue_type: Annotated[str, Field(description="Jira issue type (e.g., 'Task', 'Sub-task', 'Story', 'Bug', 'Epic', 'Feature', 'Chore)")] = "story",
        priority: Annotated[str | None, Field(description="Priority (e.g., 'Highest', 'High', 'Medium', 'Low', 'Lowest')")] = None,
        labels: Annotated[list | None, Field(description="List of labels to add to the issue (e.g., ['backend', 'urgent'])")] = None,
        parent: Annotated[str | None, Field(description="Parent issue key (e.g., epic key like 'PROJ-123') to link this issue at creation time")] = None,
        epic_name: Annotated[str | None, Field(description="Name of the epic (required if issue_type is 'epic')")] = None,
    ) -> str:
        try:
            print("Creating issue with:", project_key, summary, description, priority, issue_type, epic_name, labels, parent)
            return await asyncio.to_thread(jira().create_issue, project_key, summary, description, priority, issue_type, epic_name, labels, parent)
        except JiraValidationError as e:
            raise ToolError(str(e))


def register_update_issue_tool(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-updateIssue",
        description="Updates summary, description, or priority for an existing Jira issue. Provide at least one field to update.",
        tags={"jira", "write"})
    
    @log_async_method_calls
    async def update_issue(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Issue key to update")],
        summary: Annotated[str | None, Field(description="title for the issue to update")] = None,
        description: Annotated[str | None, Field(description="Detailed description to update")] = None,
        priority: Annotated[str | None, Field(description="Priority to update (e.g., 'Highest', 'High', 'Medium', 'Low', 'Lowest')")] = None,
    ) -> str:
        try:
            return await asyncio.to_thread(jira().update_issue, issue_key, summary, description, priority)
        except JiraValidationError as e:
            raise ToolError(str(e))


def register_get_issue(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-getIssue",
        description="Fetches details of a specific Jira issue by its issue key. Returns key, summary, status, priority, description, labels, and parent (if linked to a parent issue/epic).",
        tags={"jira", "read"})
    @log_async_method_calls
    async def get_issue(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key")],
    ) -> str:
        return await asyncio.to_thread(jira().get_issue, issue_key)


def register_link_issue_to_epic_tool(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-linkIssueToEpic",
        description="Links an existing Jira issue (story or task) to a specified Epic.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def link_issue_to_epic(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Story/task issue key")],
        epic_key: Annotated[str, Field(description="Epic issue key")],
    ) -> str:
        print("Linking issue to epic with:", issue_key, epic_key)
        return await asyncio.to_thread(jira().link_issue_to_epic, issue_key, epic_key)


def register_transition_issue(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-transitionIssue",
        description="Moves a Jira issue to a target status (e.g. 'In Progress' -> 'Done') by resolving the real Jira transition ID from the issue's available transitions. Idempotent: if the issue is already in the target status, returns result 'already_done' without changing anything. Fails with a clear error if no transition to the target status is available.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def transition_issue(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key to transition (e.g., 'PROJ-123')")],
        target_status: Annotated[str, Field(description="Name of the status to move the issue to (e.g., 'Done')")],
    ) -> str:
        try:
            return await asyncio.to_thread(jira().transition_issue, issue_key, target_status)
        except JiraValidationError as e:
            raise ToolError(str(e))
