# transitions.py
"""Issue status transitions by resolved transition ID (FR-13).

Moved unchanged from JiraService (P2.7). Transition IDs are workflow-specific, so the
target status is always resolved through Jira's own transitions list; workflow rules stay
in Jira. `already_done` is a success, not an error.
"""
import json

from src.exceptions.exceptions import JiraValidationError
from src.services.jira_client import RequestFn


def transition_issue(request: RequestFn, key: str, target_status: str) -> str:
    """Moves an issue to target_status by resolving the real Jira
    transition ID (transition IDs are workflow-specific, never the
    status name). Idempotent: if the issue is already in the target
    status, no transition is performed and "already_done" is returned.
    """
    if not key or not key.strip():
        raise JiraValidationError("issue_key is required and must be a non-empty string.")
    if not target_status or not target_status.strip():
        raise JiraValidationError("target_status is required and must be a non-empty string.")
    key = key.strip()
    wanted = target_status.strip().lower()

    issue = request("GET", f"/rest/api/3/issue/{key}", params={"fields": "status"}).json()
    current_status = ((issue.get("fields") or {}).get("status") or {}).get("name")
    if not current_status:
        raise RuntimeError(f"Unexpected Jira response: no status found for issue {key}")
    if current_status.lower() == wanted:
        return json.dumps({
            "success": True,
            "result": "already_done",
            "message": f"Issue {key} is already in status '{current_status}'; no transition performed",
            "issue": key,
            "from_status": current_status,
            "to_status": current_status,
        })

    data = request("GET", f"/rest/api/3/issue/{key}/transitions").json()
    if "transitions" not in data:
        raise RuntimeError(f"Unexpected Jira response: no transitions list for issue {key}")
    transitions = data["transitions"] or []

    match = next(
        (t for t in transitions if ((t.get("to") or {}).get("name") or "").lower() == wanted),
        None,
    ) or next((t for t in transitions if (t.get("name") or "").lower() == wanted), None)
    if match is None:
        available = ", ".join(sorted({(t.get("to") or {}).get("name") or t.get("name", "?") for t in transitions}))
        raise JiraValidationError(
            f"No transition to status '{target_status}' is available for issue {key} "
            f"(current status: '{current_status}'). Available target statuses: {available or 'none'}"
        )

    request("POST", f"/rest/api/3/issue/{key}/transitions", json={"transition": {"id": match["id"]}})
    to_status = (match.get("to") or {}).get("name") or target_status
    return json.dumps({
        "success": True,
        "result": "transitioned",
        "message": f"Issue {key} transitioned from '{current_status}' to '{to_status}'",
        "issue": key,
        "from_status": current_status,
        "to_status": to_status,
        "transition_id": match["id"],
    })
