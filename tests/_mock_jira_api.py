"""
Shared mock Jira Cloud REST API used by every test in this package.

This patches `requests.Session.request` at the class level so NO test can
ever make a real HTTP call to Jira, no matter what credentials are
configured. Every call that would have gone out is recorded in a
call_log list so tests can assert on exactly what was sent (e.g. which
project_key ended up in the request body/URL) - and, just as
importantly, assert that call_log stayed EMPTY when a validation error
is supposed to prevent any Jira API call at all.
"""
import json

import requests


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


def default_handler(method, url, **kwargs):
    """A generic-enough fake Jira Cloud API for the tools under test."""
    if url.endswith("/rest/api/3/field"):
        return FakeResponse(200, [
            {"id": "customfield_10011", "name": "Epic Name"},
            {"id": "customfield_10014", "name": "Epic Link"},
        ])

    if "/issue/createmeta" in url:
        return FakeResponse(200, {"projects": [{"issuetypes": [
            {"name": "Story"}, {"name": "Task"}, {"name": "Bug"}, {"name": "Epic"},
        ]}]})

    if url.endswith("/rest/api/3/priority"):
        return FakeResponse(200, [{"name": n} for n in
                                   ["Highest", "High", "Medium", "Low", "Lowest"]])

    if url.endswith("/rest/api/3/issue") and method == "POST":
        return FakeResponse(201, {"key": "MOCK-1"})

    if url.endswith("/rest/api/3/issue/bulk") and method == "POST":
        body = kwargs.get("json", {})
        n = len(body.get("issueUpdates", []))
        return FakeResponse(201, {"issues": [{"key": f"MOCK-{i + 1}"} for i in range(n)]})

    if "/issue/" in url and url.endswith("/comment"):
        return FakeResponse(201, {"id": "10001"})

    if "/issue/" in url and url.endswith("/remotelink"):
        return FakeResponse(201, {"id": "10002"})

    if "/issue/" in url and url.endswith("/attachments"):
        return FakeResponse(200, [{"id": "10003", "filename": "mock.txt"}])

    if "/issue/" in url and url.endswith("/transitions"):
        if method == "POST":
            return FakeResponse(204, {})
        return FakeResponse(200, {"transitions": [
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]})

    if "/search/jql" in url:
        return FakeResponse(200, {"issues": [], "isLast": True, "nextPageToken": None})

    if method == "GET" and "/issue/" in url:
        return FakeResponse(200, {"fields": {
            "summary": "Mock issue", "status": {"name": "To Do"},
            "priority": {"name": "Medium"}, "labels": [],
            "description": {"content": [{"content": [{"type": "text", "text": "hello"}]}]},
        }})

    if method == "PUT" and "/issue/" in url:
        return FakeResponse(204, {})

    return FakeResponse(404, {"errorMessages": [f"No mock handler for {method} {url}"]})


def install_mock(handler=None):
    """Patches requests.Session.request for the duration of a test.

    Returns (call_log, restore_fn). Call restore_fn in tearDown to
    un-patch, even on failure.
    """
    call_log = []
    active_handler = handler or default_handler

    def fake_request(self, method, url, **kwargs):
        call_log.append({"method": method, "url": url, "kwargs": kwargs})
        return active_handler(method, url, **kwargs)

    original = requests.Session.request
    requests.Session.request = fake_request

    def restore():
        requests.Session.request = original

    return call_log, restore
