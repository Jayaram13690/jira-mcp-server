"""Bulk and search tools: getIssuesBulk, searchIssues, createIssuesBulk (FR-4, 5, 11).

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
from src.tools.bulk_issue_input import normalize_bulk_issues
from src.utils.log_helper import log_async_method_calls


def register_get_issues_bulk(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-getIssuesBulk",
        description="Fetches detailed information for issues from a Jira project OR epic. Supports TWO modes: 1) Project mode: Provide project key (e.g., 'RET') to fetch ALL issues in the project. 2) Epic mode: Provide epic key (e.g., 'RET-424') to fetch the epic AND all child issues under it. Returns key, summary, status, priority, description, labels, parent, issue_type, created, and updated for each issue. Automatically paginates through all issues in batches of 100.",
        tags={"jira", "read", "bulk"})
    @log_async_method_calls
    async def get_issues_bulk(
        ctx: Context,
        project_key: Annotated[str, Field(description="Project key (e.g., 'RET') to fetch all project issues, OR Epic key (e.g., 'RET-424') to fetch epic and its children")],
        max_results: Annotated[int | None, Field(description="Maximum number of results to return. If not specified, fetches ALL issues using automatic pagination.")] = None,
        fetch_all: Annotated[bool, Field(description="If True, automatically paginates through all issues (default: True). Set to False to fetch only first 100.")] = True,
    ) -> str:
        return await asyncio.to_thread(jira().get_issues_bulk, project_key, max_results, fetch_all)


def register_search_issues(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-searchIssues",
        description="Searches Jira using a JQL query. Returns ALL matching issues (paginates automatically) unless max_results is explicitly set to cap it.",
        tags={"jira", "read"})
    @log_async_method_calls
    async def search_issues(
        ctx: Context,
        jql: Annotated[str, Field(description="JQL query")],
        max_results: Annotated[int, Field(description="Optional cap on results - 0 (default) fetches everything")] = 0,
    ) -> str:
        return await asyncio.to_thread(jira().search_issues, jql, max_results)


def register_create_issues_bulk_tool(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-createIssuesBulk",
        description="Creates multiple Jira issues in bulk. Accepts a list of issue objects, each with project_key (required) and summary (required), plus optional description, issue_type, priority, epic_name (for epics), labels, and parent (to link to an epic or parent issue). There is no default project - every issue in the list must specify its own project_key (they may target different projects in the same call).",
        tags={"jira", "write", "bulk"})
    @log_async_method_calls
    async def create_issues_bulk(
        ctx: Context,
        issues: Annotated[list, Field(description="List of issue objects to create. Each object must contain: project_key (required, no default project), summary (required), description (optional), issue_type (optional, default='story'), priority (optional), epic_name (optional, for epics only), labels (optional, list of strings), parent (optional, parent issue key)")],
    ) -> str:
        try:
            print("Raw issues received:", issues)
            print("Type of issues:", type(issues))
            
            parsed_issues = normalize_bulk_issues(issues)
            
            print("Final parsed issues:", parsed_issues)
            return await asyncio.to_thread(jira().create_issues_bulk, parsed_issues)
        except JiraValidationError as e:
            raise ToolError(str(e))
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise ToolError(f"Bulk creation failed: {e!s}")
