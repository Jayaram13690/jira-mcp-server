"""
Test-isolation guard (T-29 / NFR-6, CLAUDE.md "No network, ever").

A populated local .env can set AZURE_APPCONFIG_ENDPOINT. config.get_config()
prefers App Configuration over environment variables, so without isolation
every test run would contact Azure and replace the fake Jira settings that
tests/__init__.py installs. tests/__init__.py therefore sets
AZURE_APPCONFIG_ENDPOINT to "" before anything imports src.config.

Because src.config is imported (and cached) by the time a test body runs, the
decisive check runs in a FRESH interpreter that:
  * starts without any of the test-bootstrap variables,
  * emulates a populated .env (via the real dotenv loader, same non-override
    semantics as config.py's load_dotenv()), and
  * replaces the Azure network entry points with recording stubs, so even a
    failing run contacts nothing.
Nothing here reads the real .env or any secret.
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_URL = "https://mock-test.atlassian.net"

_CHILD = r"""
import json, os, sys
from pathlib import Path

import dotenv

# Emulate a populated .env: the real loader, non-override semantics, fake values.
_real_load_dotenv = dotenv.load_dotenv
def _populated_env(*args, **kwargs):
    return _real_load_dotenv(dotenv_path=os.environ["GUARD_FAKE_DOTENV"])
dotenv.load_dotenv = _populated_env

import tests  # the real test bootstrap under test (tests/__init__.py)

# Recording stubs for every Azure entry point; nothing real can be reached.
import src.config.config_reader as reader
calls = {"load": 0, "credential": 0}
def _stub_load(*a, **k):
    calls["load"] += 1
    return {"JIRA_URL": "https://from-app-config.invalid"}
class _StubCredential:
    def __init__(self, *a, **k):
        calls["credential"] += 1
reader.load = _stub_load
reader.DefaultAzureCredential = _StubCredential

from src.config import config

print(json.dumps({
    "endpoint_in_env": os.environ.get("AZURE_APPCONFIG_ENDPOINT"),
    "azure_load_calls": calls["load"],
    "credential_constructions": calls["credential"],
    "azure_config": config.azure_config,
    "jira_url": config.JIRA_URL,
    "jira_username": config.JIRA_USERNAME,
    "jira_token_is_mock": config.JIRA_API_TOKEN == "mock-token-not-a-real-credential",
}))
"""


class TestEnvironmentIsHermeticInProcess(unittest.TestCase):
    """Cheap in-process checks on the configuration this test run actually uses."""

    def test_app_config_endpoint_is_blank(self):
        importlib.import_module("src.config.config")  # load_dotenv() runs on first import

        self.assertEqual(os.environ.get("AZURE_APPCONFIG_ENDPOINT"), "")

    def test_jira_settings_are_the_fake_bootstrap_values(self):
        from src.config import config

        self.assertEqual(config.JIRA_URL, MOCK_URL)
        self.assertEqual(config.JIRA_USERNAME, "mock-user@example.com")
        self.assertEqual(config.JIRA_API_TOKEN, "mock-token-not-a-real-credential")
        self.assertEqual(config.azure_config, {})


class TestPopulatedDotenvCannotBreakIsolation(unittest.TestCase):
    """Fresh-interpreter check: a populated .env must not reach Azure or override the mocks."""

    def _run_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_env = Path(tmp) / "populated.env"
            fake_env.write_text(
                "AZURE_APPCONFIG_ENDPOINT=https://guard.invalid\n"
                "APP_NAME=guard-app\n"
                "ENVIRONMENT=guard\n"
                "JIRA_URL=https://from-dotenv.invalid\n",
                encoding="utf-8",
            )
            env = {k: v for k, v in os.environ.items()
                   if k not in {"AZURE_APPCONFIG_ENDPOINT", "JIRA_URL", "JIRA_USERNAME",
                                "JIRA_API_TOKEN", "APP_NAME", "ENVIRONMENT"}}
            env.update(GUARD_FAKE_DOTENV=str(fake_env), PYTHONPATH=str(REPO_ROOT),
                       LOG_LEVEL="WARNING")
            proc = subprocess.run(
                [sys.executable, "-c", _CHILD], cwd=str(REPO_ROOT), env=env,
                capture_output=True, text=True, timeout=60, check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_azure_is_never_contacted_and_mock_settings_win(self):
        result = self._run_child()
        self.assertEqual(result["endpoint_in_env"], "")
        self.assertEqual(result["azure_load_calls"], 0, "App Configuration load() was called")
        self.assertEqual(result["credential_constructions"], 0, "an Azure credential was created")
        self.assertEqual(result["azure_config"], {})
        self.assertEqual(result["jira_url"], MOCK_URL)
        self.assertEqual(result["jira_username"], "mock-user@example.com")
        self.assertTrue(result["jira_token_is_mock"])


if __name__ == "__main__":
    unittest.main()
