"""
MCP tool-layer contract (Phase 2 / FR-1..13, 15, 18, FR-21).

tests/golden/tool_contract.json was generated from the ORIGINAL implementation (git b6fc26d)
with tests/_tool_contract.py. This test replays the same capture against the current code and
requires: every tool definition (name, description, input/output schema, annotations, tags),
registration order, the service method and exact arguments each tool delegates to, the error
mapping of every tool, and the createIssuesBulk input normalization (including captured
stdout) to be identical. It also keeps the tool layer thin.

Do not regenerate the golden file from refactored code.
The service is replaced by a recording stub; no Jira or Azure call can happen.
"""
import ast
import json
import unittest
from pathlib import Path

from src.servers import server as server_module
from src.tools import jira_tools
from tests._tool_contract import collect_contract

GOLDEN = json.loads((Path(__file__).resolve().parent / "golden" / "tool_contract.json").read_text(encoding="utf-8"))
TOOLS_DIR = Path(__file__).resolve().parent.parent / "src" / "tools"


class ToolContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = collect_contract(server_module, jira_tools)

    def test_thirteen_tools_in_original_registration_order(self):
        self.assertEqual(len(GOLDEN["tools"]), 13)
        self.assertEqual([t["name"] for t in self.actual["tools"]], [t["name"] for t in GOLDEN["tools"]])

    def test_every_tool_definition_is_identical(self):
        for want, got in zip(GOLDEN["tools"], self.actual["tools"], strict=True):
            with self.subTest(tool=want["name"]):
                self.assertEqual(got, want)

    def test_every_tool_delegates_to_the_same_service_method_with_the_same_arguments(self):
        self.assertEqual(len(self.actual["delegation"]), len(GOLDEN["delegation"]))
        for want, got in zip(GOLDEN["delegation"], self.actual["delegation"], strict=True):
            with self.subTest(tool=want["tool"], args=want["args"]):
                self.assertEqual(got, want)

    def test_error_mapping_of_every_tool_is_identical(self):
        self.assertEqual(len(GOLDEN["error_mapping"]), 26)
        for want, got in zip(GOLDEN["error_mapping"], self.actual["error_mapping"], strict=True):
            with self.subTest(tool=want["tool"], raises=want["raises"]):
                self.assertEqual(got, want)

    def test_create_issues_bulk_input_normalization_is_identical(self):
        self.assertGreaterEqual(len(GOLDEN["bulk_normalization"]), 14)
        for want, got in zip(GOLDEN["bulk_normalization"], self.actual["bulk_normalization"], strict=True):
            with self.subTest(case=json.dumps(want.get("issues", want.get("service_raises")))[:60]):
                self.assertEqual(got, want)


class ToolLayerShapeTests(unittest.TestCase):
    """Handlers stay thin: they delegate to the facade and never reach below it."""

    def test_tool_modules_do_not_touch_http_or_service_internals(self):
        for path in sorted(TOOLS_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module)
            with self.subTest(module=path.name):
                self.assertTrue(imported.isdisjoint({"requests", "src.services.jira_client", "src.services.fields",
                                                     "src.services.issues", "src.services.search",
                                                     "src.services.bulk_create", "src.services.adf"}))
                self.assertNotIn("src.servers", imported)

    def test_handlers_call_only_the_service_facade(self):
        # Handlers live in the *_tools group modules and reach the service through the injected `jira()` accessor.
        facade_calls = set()
        for path in sorted(TOOLS_DIR.glob("*_tools.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            facade_calls |= {
                node.attr for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "jira"
            }
        public = {name for name in dir(jira_tools._jira) if not name.startswith("_") and callable(getattr(jira_tools._jira, name))}
        self.assertEqual(len(facade_calls), 13)
        self.assertLessEqual(facade_calls, public)


if __name__ == "__main__":
    unittest.main()
