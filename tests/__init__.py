"""
Test package init.

Sets fake Jira credentials BEFORE any test module imports src.config
(which calls load_dotenv() at import time and would otherwise pick up
whatever is in the real, gitignored .env file). load_dotenv() does not
override already-set environment variables, so setting these here
guarantees every test uses fake, obviously-non-real values regardless of
what's in .env or the shell environment.

This is defense in depth only: the real safety net is that every test
mocks requests.Session.request (see tests/_mock_jira_api.py), so no test
in this package can ever make a real HTTP call to Jira, regardless of
which credentials are configured.
"""
import os

# Disable Azure App Configuration for the whole test run. config.get_config()
# prefers App Configuration over environment variables, so a populated local
# .env (AZURE_APPCONFIG_ENDPOINT) would otherwise make every test import contact
# Azure and replace the fake Jira settings below. Blank, not unset: load_dotenv()
# only fills variables that are absent, so "" cannot be overridden by .env.
# Guarded by tests/test_config_hermeticity.py.
os.environ["AZURE_APPCONFIG_ENDPOINT"] = ""

os.environ["JIRA_URL"] = "https://mock-test.atlassian.net"
os.environ["JIRA_USERNAME"] = "mock-user@example.com"
os.environ["JIRA_API_TOKEN"] = "mock-token-not-a-real-credential"
os.environ.setdefault("LOG_LEVEL", "WARNING")

# Intentionally NOT setting JIRA_PROJECT_KEY: the whole point of this test
# suite is to prove the server has no default/fallback project, so tests
# must pass with that variable entirely absent from the environment.
os.environ.pop("JIRA_PROJECT_KEY", None)
