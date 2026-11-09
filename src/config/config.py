"""
Configuration for Atlassian MCP application.
"""

import os

from dotenv import load_dotenv

from src.config.config_reader import AppConfigReader

# Load environment variables from .env file
load_dotenv()


# Load Azure App Configuration when configured.
#
# Local development:
#   AZURE_APPCONFIG_ENDPOINT is not set
#   -> returns {}
#
# Azure:
#   AZURE_APPCONFIG_ENDPOINT is set
#   -> loads configuration from Azure App Configuration
azure_config = AppConfigReader().load()

# Configuration variables from environment
# JIRA_PORT = int(os.getenv("JIRA_PORT", "9002"))
# JIRA_URL = os.getenv("JIRA_URL")
# # No default/fallback Jira project key is configured here on purpose: the
# # server must be reusable across multiple Jira projects without a
# # redeploy, so every operation that needs a project must receive it from
# # the caller. See jira_service.py's create_issue()/create_issues_bulk().
# JIRA_USERNAME = os.getenv("JIRA_USERNAME")
# JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
# _enabled_tools_raw = os.getenv("ENABLED_JIRA_TOOLS", "")
# ENABLED_JIRA_TOOLS = [t.strip() for t in _enabled_tools_raw.split(",") if t.strip()] or None
# LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def get_config(name: str, default: str | None = None) -> str | None:
    """
    Get configuration from Azure App Configuration first.
    Fall back to environment variables when Azure configuration
    is not available.
    """
    return azure_config.get(name, os.getenv(name, default))


# Server port remains environment-based.
JIRA_PORT = int(os.getenv("JIRA_PORT", "9002"))


# These values come from Azure App Configuration in Azure.
# They fall back to .env during local development.
JIRA_URL = get_config("JIRA_URL")

JIRA_USERNAME = get_config("JIRA_USERNAME")

JIRA_API_TOKEN = get_config("JIRA_API_TOKEN")


# Optional Jira tools configuration remains environment-based.
_enabled_tools_raw = os.getenv("ENABLED_JIRA_TOOLS", "")

ENABLED_JIRA_TOOLS = [
    t.strip()
    for t in _enabled_tools_raw.split(",")
    if t.strip()
] or None


# Log level can come from App Configuration.
LOG_LEVEL = get_config("LOG_LEVEL", "INFO")
