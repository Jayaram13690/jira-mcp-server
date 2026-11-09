# jira_client.py
"""HTTP transport for Jira Cloud REST v3.

Owns the requests.Session, its authentication and default headers, and the
single request path every Jira call goes through. Moved unchanged from
JiraService (P2.2): no timeout, no retry, RuntimeError on a non-2xx response.
Those are tracked separately (T-9, T-10) and are deliberately not changed here.

No logging decorators on purpose: JiraService's own `_request` / `__init__`
remain the logged entry points, so observable log output is unchanged.
"""
from typing import Any, Protocol

import requests

from src.config import config


class RequestFn(Protocol):
    """The request path components receive: `(method, path, **requests_kwargs) -> Response`."""

    def __call__(self, method: str, path: str, **kwargs: Any) -> requests.Response: ...


class JiraClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.auth = (config.JIRA_USERNAME, config.JIRA_API_TOKEN)
        self.session.headers.update({"Content-Type": "application/json"})

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{config.JIRA_URL}{path}"
        resp = self.session.request(method, url, **kwargs)
        if not resp.ok:
            raise RuntimeError(f"Jira API error {resp.status_code}: {resp.text}")
        return resp
