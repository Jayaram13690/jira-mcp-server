# attachments.py
"""Attach a file to an issue: local path or base64 content (FR-12).

Moved unchanged from JiraService (P2.7). Isolated because path confinement (SEC-3,
T-7) will change exactly this code. Until then `file_path` is read as given.
"""
import base64
import json
import os

from src.exceptions.exceptions import JiraValidationError
from src.services.jira_client import RequestFn


def add_attachment(request: RequestFn, key: str, file_path: str | None = None, filename: str | None = None,
                   content_base64: str | None = None, mime_type: str | None = None) -> str:
    """Attaches a file to an existing issue via Jira's Attachments
    API. This endpoint requires the X-Atlassian-Token header and a
    multipart/form-data body, so the session's default
    Content-Type: application/json header must be overridden to None
    for this request so `requests` can set its own multipart
    boundary Content-Type.

    Accepts EITHER a local file_path (read from disk) OR
    content_base64 (in-memory bytes, base64-encoded — the only way
    raw bytes survive a JSON-RPC MCP call) + filename. Exactly one
    of the two must be provided.
    """
    if not file_path and not content_base64:
        raise JiraValidationError("Provide either file_path or content_base64.")
    if file_path and content_base64:
        raise JiraValidationError("Provide only one of file_path or content_base64, not both.")

    headers = {"X-Atlassian-Token": "no-check", "Content-Type": None}

    if content_base64:
        if not filename:
            raise JiraValidationError("filename is required when attaching via content_base64.")
        try:
            file_bytes = base64.b64decode(content_base64, validate=True)
        except Exception as e:
            raise JiraValidationError(f"Invalid base64 content: {e}")
        attachment_name = filename
        files = {"file": (attachment_name, file_bytes, mime_type or "application/octet-stream")}
        request("POST", f"/rest/api/3/issue/{key}/attachments", headers=headers, files=files)
    else:
        if not os.path.isfile(file_path):
            raise JiraValidationError(f"File not found: {file_path}")
        attachment_name = filename or os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (attachment_name, f, mime_type)} if mime_type else {"file": (attachment_name, f)}
            request("POST", f"/rest/api/3/issue/{key}/attachments", headers=headers, files=files)

    payload = {
        "message": f"Attachment added to {key}",
        "key": key,
        "filename": attachment_name,
    }
    return json.dumps(payload)
