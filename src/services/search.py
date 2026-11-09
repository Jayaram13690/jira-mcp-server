# search.py
import json
import logging

from src.config import config
from src.exceptions.exceptions import JiraValidationError
from src.services.adf import extract_plain_text
from src.services.jira_client import RequestFn

logger = logging.getLogger("jira-mcp-server")


class IssueSearch:
    def __init__(self, request: RequestFn) -> None:
        self._request = request

    # gets a list of issues based on JQL query(limited fields, summaries not drich in detail like get issue)
    def search_issues(self, jql: str, max_results: int = 0) -> str:
        """
        FIX (round 2): the previous fix just requested a bigger fixed number (100) instead of a small one (10) - still a silent cap, just a bigger one. Production needs to handle a project with
        5 matching stories or 500 identically, without a number picked in advance. This now genuinely paginates through every page of results, reusing the exact working token-based pattern already
        proven in get_issues_bulk() above, rather than inventing a new approach. max_results=0 (the new default) means "fetch everything." Pass
        a positive number only if you deliberately want to cap it.
        """
        all_issues = []
        seen_keys = set()
        next_page_token = None
        page_size = 100
        api_calls = 0
        max_api_calls = 50  # safety valve against a truly runaway/looping query, not a result-count cap

        while True:
            params = {"jql": jql, "maxResults": page_size,
                      "fields": "summary,status,priority,description,labels,issuetype"}
            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = self._request("GET", "/rest/api/3/search/jql", params=params).json()
            api_calls += 1

            current_batch = response.get("issues", [])
            is_last = response.get("isLast", True)
            next_page_token = response.get("nextPageToken")

            batch_keys = [i["key"] for i in current_batch]
            if any(k in seen_keys for k in batch_keys):
                logger.warning(
                    "Detected duplicate issues while paginating search_issues - stopping to avoid an infinite loop")
                break

            for issue in current_batch:
                seen_keys.add(issue["key"])
                all_issues.append(issue)

            if not current_batch or is_last or not next_page_token:
                break
            if max_results and len(all_issues) >= max_results:
                all_issues = all_issues[:max_results]
                break
            if api_calls >= max_api_calls:
                logger.warning(f"Hit the {max_api_calls}-page safety limit for one search_issues call - stopping")
                break

        payload = {
            "results": [
                {
                    "key": i["key"],
                    "summary": i["fields"]["summary"],
                    "status": i["fields"]["status"]["name"],
                    "priority": (i["fields"].get("priority") or {}).get("name", ""),
                    "description": extract_plain_text(i["fields"]),
                    "labels": i["fields"].get("labels", []),
                    "url": f"{config.JIRA_URL.rstrip('/')}/browse/{i['key']}",
                }
                for i in all_issues
            ]
        }
        return json.dumps(payload)

    def get_issues_bulk(self, project_key: str, max_results: int = None, fetch_all: bool = True) -> str:
        """
        Fetches detailed information for ALL Jira issues from a project or epic using paginated JQL queries.

        Args:
            project_key: Project key (e.g., 'RET') OR Epic key (e.g., 'RET-424') to fetch issues from
                        - If project key: fetches all issues in the project
                        - If epic key: fetches the epic AND all child issues under it
            max_results: Maximum number of results to return (None = fetch all)
            fetch_all: If True, automatically paginates through all issues (default: True)

        Returns:
            JSON string with list of issue details

        Note: This method uses ORDER BY key ASC with token-based pagination to fetch issues in batches of 100.
        Works within Jira's 100-result limit by making multiple paginated requests.
        Supports both project-level fetching and epic-level fetching (epic + children).
        """
        if not project_key or not isinstance(project_key, str):
            raise JiraValidationError("project_key must be a non-empty string")

        import time

        # Request detailed fields
        fields = [
            "summary", "status", "priority", "description",
            "labels", "parent", "issuetype", "created", "updated"
        ]

        try:
            # Detect if input is an issue key (e.g., "RET-424") or project key (e.g., "RET")
            input_key = project_key.strip()
            is_epic_key = "-" in input_key  # Issue keys have hyphen (e.g., RET-424)

            if is_epic_key:
                # First, verify it's actually an epic
                print(f"Detected issue key format: {input_key}")
                print(f"Checking if {input_key} is an epic...")

                try:
                    epic_data = self._request("GET", f"/rest/api/3/issue/{input_key}").json()
                    issue_type = epic_data.get("fields", {}).get("issuetype", {}).get("name", "")

                    if issue_type.lower() != "epic":
                        return json.dumps({
                            "success": False,
                            "error": f"Issue {input_key} is not an Epic (it's a {issue_type}). Please provide either a project key (e.g., 'RET') or an Epic issue key."
                        })

                    print(f"Confirmed {input_key} is an Epic: {epic_data['fields']['summary']}")
                    print(f"Fetching Epic and all child issues under {input_key}...")

                    # Build JQL to fetch epic + all children
                    # This fetches the epic itself AND all issues that have this epic as parent
                    jql_query = f"(key = {input_key} OR parent = {input_key}) ORDER BY key ASC"
                    fetch_mode = f"epic and children of {input_key}"

                except Exception as e:
                    return json.dumps({
                        "success": False,
                        "error": f"Failed to fetch issue {input_key}: {e!s}"
                    })
            else:
                # It's a project key
                print(f"Fetching ALL issues from project {input_key}...")
                jql_query = f"project = {input_key} ORDER BY key ASC"
                fetch_mode = f"all issues in project {input_key}"

            all_issues = []  # Stores all fetched issues
            api_calls = 0  # Counts API requests made
            page_size = 100  # Jira's hard limit
            next_page_token = None  # Token-based pagination (not offset-based)
            seen_keys = set()  # Track seen issue keys to detect duplicates/loops

            print(f"Starting TOKEN-BASED pagination with {page_size} issues per page...")

            while True:
                # Build params for token-based pagination
                params = {
                    "jql": jql_query,  # Use the dynamic JQL query (project or epic+children)
                    "maxResults": page_size,
                    "fields": ",".join(fields)
                }

                # Add nextPageToken if we have one (for subsequent pages)
                if next_page_token:
                    params["nextPageToken"] = next_page_token

                # Fetch next page using JQL with ORDER BY key ASC for consistent ordering, making api call
                response = self._request(
                    "GET",
                    "/rest/api/3/search/jql",
                    params=params
                ).json()

                api_calls += 1

                # extracting pagination details like issues, last page, next token
                current_batch = response.get("issues", [])
                is_last = response.get("isLast", True)
                next_page_token = response.get("nextPageToken")

                # Check for duplicate/infinite loop detection
                batch_keys = [issue["key"] for issue in current_batch]
                duplicates = [key for key in batch_keys if key in seen_keys]

                if duplicates:
                    print(f"  Warning: Detected duplicate issues {duplicates[:5]}... Stopping pagination.")
                    break

                # Add new issues to collection, store issue
                for issue in current_batch:
                    seen_keys.add(issue["key"])
                    all_issues.append(issue)

                # Progress indicator
                print(f"  Progress: Page {api_calls}, fetched {len(all_issues)} issues (isLast={is_last})")

                # Check stopping conditions
                if not current_batch:
                    print("  No more issues returned. Stopping pagination.")
                    break

                # Check if this is the last page (token-based pagination flag)
                if is_last or not next_page_token:
                    print(f"  Last page reached (isLast={is_last}). Stopping pagination.")
                    break

                if max_results and len(all_issues) >= max_results:
                    print(f"  Reached max_results limit of {max_results}")
                    break

                # Safety: If we've made too many calls without progress, stop
                if api_calls > 100:  # Max 100 pages = 10,000 issues
                    print(f"  Safety limit: Made {api_calls} API calls. Stopping pagination.")
                    break

                # Small delay to avoid rate limiting
                time.sleep(0.1)

            print(f"\nPagination complete: Found {len(all_issues)} issues in {api_calls} API calls")

            # Parse all issues into detailed format
            results = []
            for issue_data in all_issues:
                fields_data = issue_data.get("fields", {})

                # Parse parent info
                parent_info = None
                if fields_data.get("parent"):
                    parent_data = fields_data["parent"]
                    parent_info = {
                        "key": parent_data.get("key"),
                        "summary": parent_data.get("fields", {}).get("summary", "")
                    }

                # Parse issue type
                issue_type = fields_data.get("issuetype", {}).get("name", "Unknown")

                results.append({
                    "key": issue_data["key"],
                    "summary": fields_data.get("summary", ""),
                    "status": fields_data.get("status", {}).get("name", "Unknown"),
                    "priority": fields_data.get("priority", {}).get("name", "Unknown"),
                    "description": extract_plain_text(fields_data),
                    "labels": fields_data.get("labels", []),
                    "parent": parent_info,
                    "issue_type": issue_type,
                    "created": fields_data.get("created", ""),
                    "updated": fields_data.get("updated", "")
                })

            payload = {
                "success": True,
                "message": f"Retrieved {len(results)} issues ({fetch_mode})",
                "project_key": project_key,
                "total_retrieved": len(results),
                "api_calls_made": api_calls,
                "issues": results,
                "fetching_strategy": "token-based pagination with nextPageToken",
                "fetch_mode": fetch_mode,
                "page_size": page_size
            }

            return json.dumps(payload)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "error": f"Failed to fetch issues from project {project_key}: {e!s}"
            })
