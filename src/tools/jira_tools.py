# jira_tools.py
import logging

from fastmcp import FastMCP

from src.config import config  # Import to load config
from src.exceptions.exceptions import JiraValidationError
from src.services.jira_service import JiraService
from src.tools import bulk_search_tools, comment_link_tools, issue_tools
from src.utils.log_helper import log_method_calls, setup_logging

# JiraValidationError is re-exported: the tool-contract harness reads it from this module.
__all__ = ["JiraService", "JiraValidationError", "config", "register_tools"]

# Initialize logging at module level
try:
    setup_logging()
    logger = logging.getLogger("jira-mcp-server")
    logger.debug("Initializing jira MCP server at module level...")
except Exception as e:
    print(f"Logging setup error during initialization: {e}")
    raise


# project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# sys.path.insert(0, project_root)

# Built by the first register_tools() call, not at import (T-15a). Module-level state on purpose: the
# handlers read `_jira`, and tests substitute it with patch.object(jira_tools, "_jira", ...).
_jira: JiraService | None = None


def _get_jira() -> JiraService:
    """Resolve `_jira` at call time so patch.object(jira_tools, "_jira", ...) reaches every handler."""
    return _jira


# MCP tool registrations
@log_method_calls
def register_tools(mcp: FastMCP) -> None:
    """Register JIRA tools based on configuration."""
    global _jira
    if _jira is None:
        _jira = JiraService()

    enabled_tools = getattr(config, 'ENABLED_JIRA_TOOLS', None) or [
        "jira-createIssue",
        "jira-updateIssue",
        "jira-getIssue",
        "jira-getIssuesBulk",
        "jira-createIssuesBulk",
        "jira-linkIssueToEpic",
        "jira-addComment",
        "jira-addCommentWithLinks",
        "jira-searchIssues",
        "jira-updateLabels",
        "jira-addRemoteLink",
        "jira-addAttachment",
        "jira-transitionIssue",
    ]
    
    logger.info(f"Registering JIRA tools: {enabled_tools}")
    
    # Define all available tools
    available_tools = {
        "jira-createIssue": _register_create_issue_tool,
        "jira-updateIssue": _register_update_issue_tool,
        "jira-linkIssueToEpic":_register_link_issue_to_epic_tool,
        "jira-addComment":_register_add_comment,
        "jira-addCommentWithLinks": _register_add_comment_with_links,
        "jira-getIssue": _register_get_issue,
        "jira-getIssuesBulk": _register_get_issues_bulk,
        "jira-searchIssues": _register_search_issues,
        "jira-createIssuesBulk": _register_create_issues_bulk_tool,
        "jira-updateLabels": _register_update_labels,
        "jira-addRemoteLink": _register_add_remote_link,
        "jira-addAttachment": _register_add_attachment_tool,
        "jira-transitionIssue": _register_transition_issue,
        #"jira-healthCheck": health_check,
    }
    
    # Register only enabled tools
    registered_count = 0
    for tool_name in enabled_tools:
        if tool_name in available_tools:
            available_tools[tool_name](mcp)
            logger.debug(f"Registered tool: {tool_name}")
            registered_count += 1
        else:
            logger.warning(f"Unknown tool requested: {tool_name}. Available tools: {list(available_tools.keys())}")
    
    logger.info(f"Successfully registered {registered_count} JIRA tools")


@log_method_calls
def _register_create_issue_tool(mcp: FastMCP) -> None:
    issue_tools.register_create_issue_tool(mcp, _get_jira)


@log_method_calls
def _register_update_issue_tool(mcp: FastMCP) -> None:
    issue_tools.register_update_issue_tool(mcp, _get_jira)


@log_method_calls
def _register_link_issue_to_epic_tool(mcp: FastMCP) -> None:
    issue_tools.register_link_issue_to_epic_tool(mcp, _get_jira)


@log_method_calls
def _register_add_comment(mcp: FastMCP) -> None:
    comment_link_tools.register_add_comment(mcp, _get_jira)


@log_method_calls
def _register_transition_issue(mcp: FastMCP) -> None:
    issue_tools.register_transition_issue(mcp, _get_jira)


@log_method_calls
def _register_add_comment_with_links(mcp: FastMCP) -> None:
    comment_link_tools.register_add_comment_with_links(mcp, _get_jira)


@log_method_calls
def _register_update_labels(mcp: FastMCP) -> None:
    comment_link_tools.register_update_labels(mcp, _get_jira)


@log_method_calls
def _register_add_remote_link(mcp: FastMCP) -> None:
    comment_link_tools.register_add_remote_link(mcp, _get_jira)


@log_method_calls
def _register_add_attachment_tool(mcp: FastMCP) -> None:
    comment_link_tools.register_add_attachment_tool(mcp, _get_jira)


@log_method_calls
def _register_get_issue(mcp: FastMCP) -> None:
    issue_tools.register_get_issue(mcp, _get_jira)


@log_method_calls
def _register_get_issues_bulk(mcp: FastMCP) -> None:
    bulk_search_tools.register_get_issues_bulk(mcp, _get_jira)


@log_method_calls
def _register_search_issues(mcp: FastMCP) -> None:
    bulk_search_tools.register_search_issues(mcp, _get_jira)


@log_method_calls
def _register_create_issues_bulk_tool(mcp: FastMCP) -> None:
    bulk_search_tools.register_create_issues_bulk_tool(mcp, _get_jira)
