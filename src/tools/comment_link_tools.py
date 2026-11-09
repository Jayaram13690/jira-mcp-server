"""Comment, label, link and attachment tools (FR-6..8, 10, 12).

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


def register_add_comment(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-addComment",
        description="Adds a comment to an existing Jira issue.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def add_comment(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key")],
        comment: Annotated[str, Field(description="Text to add as comment")],
    ) -> str:
        return await asyncio.to_thread(jira().add_comment, issue_key, comment)


def register_add_comment_with_links(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-addCommentWithLinks",
        description="Adds a comment to a Jira issue where specific text segments render as real clickable links, e.g. linking each TestRail case ID to its actual case page.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def add_comment_with_links(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key")],
        intro_text: Annotated[str, Field(description="Plain text shown before the links")],
        links: Annotated[list[dict], Field(description="List of {text, url} objects, each rendered as a clickable link")],
    ) -> str:
        return await asyncio.to_thread(jira().add_comment_with_links, issue_key, intro_text, links)


def register_update_labels(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-updateLabels",
        description="Adds and/or removes specific labels on a Jira issue, without touching any other labels already there.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def update_labels(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key")],
        add_labels: Annotated[list[str], Field(description="Labels to add")] = [],
        remove_labels: Annotated[list[str], Field(description="Labels to remove")] = [],
    ) -> str:
        return await asyncio.to_thread(jira().update_labels, issue_key, add_labels, remove_labels)


def register_add_remote_link(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-addRemoteLink",
        description="Adds a real clickable remote link (e.g. to a TestRail case) to a Jira issue - not a text comment, a proper link object.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def add_remote_link(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key")],
        url: Annotated[str, Field(description="The external URL to link to")],
        title: Annotated[str, Field(description="Display title for the link")],
    ) -> str:
        return await asyncio.to_thread(jira().add_remote_link, issue_key, url, title)


def register_add_attachment_tool(mcp: FastMCP, jira: Callable[[], JiraService]) -> None:
    @mcp.tool(
        name="jira-addAttachment",
        description="Attaches a file to an existing Jira issue (Epics included). Provide EITHER file_path (a path to a local file on this server's disk) OR content_base64 + filename (in-memory bytes, base64-encoded — use this for generated content like a PDF report that never touches disk). Exactly one of file_path / content_base64 is required.",
        tags={"jira", "write"})
    @log_async_method_calls
    async def add_attachment(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key")],
        file_path: Annotated[str | None, Field(description="Path to a local file to attach (mutually exclusive with content_base64)")] = None,
        filename: Annotated[str | None, Field(description="Filename for the attachment. Optional with file_path (defaults to the file's own name); required with content_base64.")] = None,
        content_base64: Annotated[str | None, Field(description="Base64-encoded file content to attach directly, without a local file (mutually exclusive with file_path)")] = None,
        mime_type: Annotated[str | None, Field(description="MIME type of the content, e.g. 'application/pdf' (only used with content_base64)")] = None,
    ) -> str:
        try:
            return await asyncio.to_thread(jira().add_attachment, issue_key, file_path, filename, content_base64, mime_type)
        except JiraValidationError as e:
            raise ToolError(str(e))
