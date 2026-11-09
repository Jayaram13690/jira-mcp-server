# bulk_issue_input.py
"""Input normalization for jira-createIssuesBulk (FR-5).

Agents send the `issues` argument in several shapes: real objects, JSON-encoded strings,
objects wrapped as {"issues": [...]}, or plain text. This is observed LLM behaviour and
is a documented compatibility requirement (CLAUDE.md) - do not "simplify" it away.

Moved unchanged from jira_tools.py (Phase 2). It is the only argument-shaping logic in the
tool layer: a pure function over the raw argument, with no service, Jira or MCP dependency.
The `print()` diagnostics are preserved on purpose and are removed by T-19, not here.
"""
import json


def normalize_bulk_issues(issues: list) -> list:
    # Handle stringified JSON: check if the list contains strings that need parsing
    parsed_issues = []
    for idx, issue in enumerate(issues):
        print(f"Processing issue {idx}: {issue} (type: {type(issue)})")

        if isinstance(issue, str):
            try:
                # Try to parse the string as JSON
                parsed_issue = json.loads(issue)
                print(f"Parsed from JSON: {parsed_issue}")

                # Check if the parsed result has an "issues" key (nested structure)
                if isinstance(parsed_issue, dict) and "issues" in parsed_issue:
                    print("Found nested 'issues' key, extracting the list")
                    # Extract the actual issues array
                    nested_issues = parsed_issue["issues"]
                    if isinstance(nested_issues, list):
                        parsed_issues.extend(nested_issues)
                    else:
                        parsed_issues.append(nested_issues)
                else:
                    parsed_issues.append(parsed_issue)
            except json.JSONDecodeError as e:
                print(f"Not valid JSON, treating as summary. Error: {e}")
                # If it's not valid JSON, treat it as a summary
                parsed_issues.append({"summary": issue})
        elif isinstance(issue, dict):
            print(f"Already a dict: {issue}")
            # Check if it has nested "issues" key
            if "issues" in issue and isinstance(issue["issues"], list):
                print("Found nested 'issues' key in dict, extracting the list")
                parsed_issues.extend(issue["issues"])
            else:
                parsed_issues.append(issue)
        else:
            # If it's neither string nor dict, convert to dict with summary
            print(f"Converting to dict with summary: {issue}")
            parsed_issues.append({"summary": str(issue)})
    return parsed_issues
