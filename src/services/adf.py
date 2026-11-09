# adf.py
"""Atlassian Document Format (ADF) helpers for Jira rich text (FR-20).

Pure functions: no HTTP, no config, no logging. Moved unchanged from
JiraService (P2.1); JiraService keeps thin delegates so callers are unaffected.
"""
from typing import Any


def build_rich_text(text: str) -> dict[str, Any]:
    """Wrap plain text in a single-paragraph ADF document."""
    return {
        "type": "doc", "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    }


def extract_plain_text(fields: dict[str, Any]) -> str:
    """Flatten an issue's ADF description to plain text; "No description." if absent or unparseable."""
    try:
        blocks = fields["description"]["content"]
        return " ".join(t["text"] for b in blocks for t in b.get("content", []) if t["type"] == "text")
    except:
        return "No description."


def build_comment_body(comment: str) -> dict[str, Any]:
    """Request body for a plain-text comment."""
    return {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}]
        }
    }


def build_comment_with_links_body(intro_text: str, links: list[dict]) -> dict[str, Any]:
    """Request body for a comment whose `links` ({"text", "url"}) render as clickable links.

    Jira requires an explicit link mark per text run; a raw URL in plain text
    does not become clickable on its own.
    """
    content = [{"type": "text", "text": intro_text}]
    for i, link in enumerate(links):
        content.append({
            "type": "text",
            "text": link["text"],
            "marks": [{"type": "link", "attrs": {"href": link["url"]}}],
        })
        if i < len(links) - 1:
            content.append({"type": "text", "text": ", "})

    return {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": content}]}}
