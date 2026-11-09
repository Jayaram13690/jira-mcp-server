"""
Tool registration behaviour (FR-15 ENABLED_JIRA_TOOLS, FR-18; AC-11).

tests/golden/tool_registration.json was generated from the ORIGINAL implementation (git b6fc26d) with
tests/_registration_contract.py. The test replays the same ENABLED_JIRA_TOOLS values against the current
`register_tools()` and requires the registered tools, their order and the project's log lines to match.

What it pins, independent of how registration is organised in code:
  * the effective registration order is the order of the ENABLED list (or the default list), never
    the order of the lookup table;
  * unknown names are warned about and skipped; duplicates and empty/absent settings behave as before;
  * the unknown-tool warning lists the lookup table in its current order.

Do not regenerate the golden file from refactored code. No network; the service is never called.
"""
import json
import unittest
from pathlib import Path

from src.tools import jira_tools
from tests._registration_contract import ALL, CASES, collect_registration

GOLDEN = json.loads((Path(__file__).resolve().parent / "golden" / "tool_registration.json").read_text(encoding="utf-8"))


class ToolRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = collect_registration(jira_tools)

    def test_same_cases_as_the_original_capture(self):
        self.assertEqual(sorted(self.actual), sorted(GOLDEN))
        self.assertEqual(sorted(GOLDEN), sorted(label for label, _ in CASES))

    def test_every_case_matches_the_original_implementation(self):
        for label, want in GOLDEN.items():
            with self.subTest(case=label):
                self.assertEqual(self.actual[label], want)

    def test_effective_order_is_the_enabled_list_order(self):
        self.assertEqual(self.actual["default_none"]["registered_in_order"], ALL)
        self.assertEqual(self.actual["subset_in_reversed_order"]["registered_in_order"],
                         ["jira-addComment", "jira-getIssue"])
        self.assertEqual(self.actual["all_thirteen_reversed"]["registered_in_order"], list(reversed(ALL)))

    def test_unknown_names_are_skipped_with_a_warning(self):
        case = self.actual["unknown_name_is_warned_and_skipped"]
        self.assertEqual(case["registered_in_order"], ["jira-getIssue", "jira-addComment"])
        warnings = [r for r in case["logs"] if r[1] == "WARNING"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("Unknown tool requested: jira-nope", warnings[0][2])
        self.assertEqual(self.actual["only_unknown_names"]["registered_in_order"], [])

    def test_empty_or_absent_setting_means_all_thirteen_tools(self):
        for label in ("empty_list_falls_back_to_default", "attribute_absent_falls_back_to_default"):
            with self.subTest(case=label):
                self.assertEqual(self.actual[label]["registered_in_order"], ALL)


if __name__ == "__main__":
    unittest.main()
