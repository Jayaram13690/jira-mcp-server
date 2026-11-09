"""
Golden-trace regression for the JiraService modularization (P2.1-P2.4, FR-14, FR-20..24).

tests/golden/service_traces.json was generated from the ORIGINAL implementation
(git b6fc26d, before any modularization) with tests/_service_scenarios.py. This
test replays the same mocked scenarios against the current code and requires:
results/exceptions, every HTTP call (method, URL, kwargs, order), captured stdout
and the project's log records to match. It also pins the 13-tool contract output
and JiraService's public method signatures.

Known, intentional log difference: the Entry/Exit/Exception lines of five
INTERNAL helpers (get_issue_types, get_priorities, _load_custom_fields,
_as_rich_text, _readable_desc) are not emitted when the extracted modules call
each other directly. They are still emitted when those methods are called
through the JiraService facade, which the *_direct scenarios pin strictly.

Do not regenerate the golden files from refactored code.
All Jira HTTP is mocked; no network.
"""
import inspect
import json
import shutil
import unittest
from pathlib import Path

from src.servers import server as server_module
from src.services.jira_service import JiraService
from src.tools import jira_tools
from tests import _mock_jira_api
from tests._service_scenarios import collect_trace, new_tmpdir

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
INTERNAL_HELPERS = (
    "JiraService.get_issue_types", "JiraService.get_priorities", "JiraService._load_custom_fields",
    "JiraService._as_rich_text", "JiraService._readable_desc",
)
STRICT_LOG_SCENARIOS = {"get_issue_types_direct", "get_issue_types_blank", "get_priorities_direct"}


def _without_internal_helper_logs(scenario, logs):
    if scenario in STRICT_LOG_SCENARIOS:
        return logs
    return [rec for rec in logs if not any(name in rec[2] for name in INTERNAL_HELPERS)]


class GoldenTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads((GOLDEN_DIR / "service_traces.json").read_text(encoding="utf-8"))
        tmp = new_tmpdir()
        try:
            cls.actual = collect_trace(JiraService, server_module, jira_tools, _mock_jira_api, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_scenario_set_is_unchanged(self):
        self.assertEqual(sorted(self.actual), sorted(self.golden))

    def test_every_scenario_matches_the_original_implementation(self):
        scenarios = [name for name in self.golden if not name.startswith("__")]
        self.assertGreaterEqual(len(scenarios), 80)
        for name in scenarios:
            with self.subTest(scenario=name):
                want, got = self.golden[name], self.actual[name]
                self.assertEqual(got["res"], want["res"], "result / exception")
                self.assertEqual(got["calls"], want["calls"], "HTTP calls (method, url, kwargs, order)")
                if "stdout" in want:
                    self.assertEqual(got["stdout"], want["stdout"], "stdout")
                if "logs" in want:
                    self.assertEqual(_without_internal_helper_logs(name, got["logs"]),
                                     _without_internal_helper_logs(name, want["logs"]), "log records")

    def test_mcp_tool_calls_match_the_original_implementation(self):
        self.assertEqual(len(self.golden["__tools__"]), 15)
        for name, want in self.golden["__tools__"].items():
            with self.subTest(tool_call=name):
                self.assertEqual(self.actual["__tools__"][name], want)

    def test_tool_registration_order_is_unchanged(self):
        self.assertEqual(len(self.golden["__tool_order__"]), 13)
        self.assertEqual(self.actual["__tool_order__"], self.golden["__tool_order__"])

    def test_known_baseline_behaviours_are_pinned(self):
        """Spot-checks that the golden file itself encodes the behaviours called out as must-preserve."""
        def urls(name):
            return [c["u"].split("/rest/api/3")[-1] for c in self.golden[name]["calls"]]

        twice = urls("create_issue_twice_field_once_createmeta_twice")
        self.assertEqual(twice.count("/field"), 1)
        self.assertEqual(sum("createmeta" in u for u in twice), 2)
        self.assertEqual(len(self.golden["search_issues_safety_cap_50_pages"]["calls"]), 50)
        self.assertEqual(len(self.golden["get_issues_bulk_safety_cap_101_calls"]["calls"]), 101)
        cache = urls("epic_cache_failure_is_not_retried_DEF12")
        self.assertEqual(cache.count("/field"), 1)
        self.assertIn("Invalid issue type", json.dumps(
            self.golden["create_issue_bad_type_and_priority_type_wins"]["res"]))
        self.assertEqual(sum("createmeta" in u for u in urls(
            "create_issues_bulk_same_project_types_looked_up_once")), 1)


class PublicApiTests(unittest.TestCase):
    def test_public_method_names_and_signatures_match_the_original(self):
        want = json.loads((GOLDEN_DIR / "service_api.json").read_text(encoding="utf-8"))["public_methods"]
        got = {name: str(inspect.signature(func))
               for name, func in inspect.getmembers(JiraService, inspect.isfunction)
               if not name.startswith("_")}
        self.assertEqual(got, want)

    def test_facade_still_logs_helper_entry_exit_when_called_directly(self):
        call_log, restore = _mock_jira_api.install_mock()
        try:
            with self.assertLogs("src.services.jira_service", level="INFO") as cm:
                JiraService().get_priorities()
        finally:
            restore()
        messages = [r.getMessage() for r in cm.records]
        self.assertIn("Entry :  JiraService.get_priorities", messages)
        self.assertIn("Exit : JiraService.get_priorities", messages)
        self.assertEqual(len(call_log), 1)


if __name__ == "__main__":
    unittest.main()
