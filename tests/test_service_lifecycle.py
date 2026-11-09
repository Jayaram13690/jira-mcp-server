"""
Service lifecycle of the tool layer (T-15a: no import-time JiraService construction).

Contract under test
  * importing `src.tools.jira_tools` constructs no `JiraService`;
  * the first `register_tools()` call builds exactly one, repeated calls build none;
  * an already-set (or patched) `_jira` is never replaced - the convention existing tests rely on;
  * every one of the 13 tools reaches the service that registration built.

Known, accepted limitation (pinned here so nobody mistakes it for a bug being fixed): the service is
still module-level singleton state, and importing `src.servers.server` still constructs it, because
server.py calls `register_tools()` at module level. Explicit injection is evaluated with T-15.

The import test runs in a FRESH interpreter: in this process `src.tools.jira_tools` is already imported
and cached, so an in-process test could not detect construction at import. No network, no real service.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastmcp import Client, FastMCP

from src.tools import jira_tools
from tests._tool_contract import MIN_ARGS

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((REPO_ROOT / "tests" / "golden" / "tool_contract.json").read_text(encoding="utf-8"))

_CHILD = r"""
import json, os
os.environ.update(JIRA_URL="https://mock-test.atlassian.net", JIRA_USERNAME="mock-user@example.com",
                  JIRA_API_TOKEN="mock-token-not-a-real-credential", AZURE_APPCONFIG_ENDPOINT="",
                  LOG_LEVEL="WARNING")

import src.services.jira_service as service_module

constructed = []
real_init = service_module.JiraService.__init__
def counting_init(self, *args, **kwargs):
    constructed.append(1)
    return real_init(self, *args, **kwargs)
service_module.JiraService.__init__ = counting_init

import src.tools.jira_tools as tools          # <- the import under test
after_tools_import, jira_after_tools_import = len(constructed), tools._jira

import src.servers.server as server           # calls register_tools() at module level
print(json.dumps({
    "constructed_by_importing_jira_tools": after_tools_import,
    "jira_is_none_after_importing_jira_tools": jira_after_tools_import is None,
    "constructed_after_importing_server": len(constructed),
    "jira_is_service_after_importing_server": isinstance(tools._jira, service_module.JiraService),
}))
"""


def _recording_service_class():
    """A stand-in `JiraService` that counts constructions and records every call."""
    created = []

    class RecordingService:
        def __init__(self):
            self.calls = []
            created.append(self)

        def __getattr__(self, name):
            def method(*args, **kwargs):
                self.calls.append(name)
                return '{"stub": true}'
            return method

    return RecordingService, created


class ImportTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {k: v for k, v in os.environ.items()
               if k not in {"JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "AZURE_APPCONFIG_ENDPOINT"}}
        env["PYTHONPATH"] = str(REPO_ROOT)
        proc = subprocess.run([sys.executable, "-c", _CHILD], cwd=str(REPO_ROOT), env=env,
                              capture_output=True, text=True, timeout=120, check=False)
        assert proc.returncode == 0, proc.stderr[-2000:]
        cls.result = json.loads(proc.stdout.strip().splitlines()[-1])

    def test_importing_jira_tools_constructs_no_service(self):
        self.assertEqual(self.result["constructed_by_importing_jira_tools"], 0)
        self.assertTrue(self.result["jira_is_none_after_importing_jira_tools"])

    def test_importing_server_still_constructs_exactly_one_service(self):
        """Accepted limitation: registration happens at server import, so the service is built there once."""
        self.assertEqual(self.result["constructed_after_importing_server"], 1)
        self.assertTrue(self.result["jira_is_service_after_importing_server"])


class RegistrationLifecycleTests(unittest.TestCase):
    def test_first_registration_builds_exactly_one_service(self):
        service_class, created = _recording_service_class()
        with mock.patch.object(jira_tools, "JiraService", service_class), \
                mock.patch.object(jira_tools, "_jira", None):
            self.assertEqual(created, [])
            jira_tools.register_tools(FastMCP(name="lifecycle-probe"))
            self.assertEqual(len(created), 1)
            self.assertIs(jira_tools._jira, created[0])

    def test_repeated_registration_builds_no_further_service(self):
        service_class, created = _recording_service_class()
        with mock.patch.object(jira_tools, "JiraService", service_class), \
                mock.patch.object(jira_tools, "_jira", None):
            for _ in range(3):
                jira_tools.register_tools(FastMCP(name="lifecycle-probe"))
            self.assertEqual(len(created), 1)
            self.assertIs(jira_tools._jira, created[0])

    def test_an_existing_or_patched_service_is_never_replaced(self):
        service_class, created = _recording_service_class()
        existing = object()
        with mock.patch.object(jira_tools, "JiraService", service_class), \
                mock.patch.object(jira_tools, "_jira", existing):
            jira_tools.register_tools(FastMCP(name="lifecycle-probe"))
            jira_tools.register_tools(FastMCP(name="lifecycle-probe"))
            self.assertIs(jira_tools._jira, existing)
            self.assertEqual(created, [])

    def test_the_service_name_and_registration_signature_are_unchanged(self):
        import inspect

        self.assertEqual(list(inspect.signature(jira_tools.register_tools).parameters), ["mcp"])
        self.assertTrue(hasattr(jira_tools, "_jira"))


class HandlersUseTheRegistrationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_thirteen_tools_reach_the_service_built_at_registration(self):
        service_class, created = _recording_service_class()
        mcp = FastMCP(name="lifecycle-probe")
        with mock.patch.object(jira_tools, "JiraService", service_class), \
                mock.patch.object(jira_tools, "_jira", None):
            jira_tools.register_tools(mcp)
            async with Client(mcp) as client:
                registered = [t.name for t in await client.list_tools()]
                self.assertEqual(len(registered), 13)
                seen_tools = set()
                for name, args in MIN_ARGS:
                    if name in seen_tools:
                        continue
                    seen_tools.add(name)
                    await client.call_tool(name, args)
            self.assertEqual(len(created), 1, "tools must not build their own service")
            expected_methods = {call[0] for entry in GOLDEN["delegation"] for call in entry["service_calls"]}
            self.assertEqual(len(expected_methods), 13)
            self.assertEqual(set(created[0].calls), expected_methods)


if __name__ == "__main__":
    unittest.main()
