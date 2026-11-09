# exceptions.py
class JiraValidationError(Exception):
    """Raised when a bad input is passed to the Jira client."""
