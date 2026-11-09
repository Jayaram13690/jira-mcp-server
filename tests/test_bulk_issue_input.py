"""
Direct tests for `src.tools.bulk_issue_input.normalize_bulk_issues` (Phase 2, FR-5).

The expectations are NOT re-typed here: they are the outputs the ORIGINAL handler
(git b6fc26d) passed to the service for each input, taken from tests/golden/tool_contract.json.
The end-to-end behaviour (handler, stdout, error mapping) is pinned by tests/test_tool_contract.py;
these tests prove the extracted function alone produces the same normalization.
"""
import ast
import contextlib
import io
import json
import unittest
from pathlib import Path

from src.tools.bulk_issue_input import normalize_bulk_issues

GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "golden" / "tool_contract.json").read_text(encoding="utf-8"))


class NormalizeBulkIssuesTests(unittest.TestCase):
    def test_matches_what_the_original_handler_passed_to_the_service(self):
        cases = [c for c in GOLDEN["bulk_normalization"] if "issues" in c and c["service_calls"]]
        self.assertGreaterEqual(len(cases), 12)
        for case in cases:
            with self.subTest(issues=json.dumps(case["issues"])[:70]):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = normalize_bulk_issues(case["issues"])
                (_name, args, _kwargs), = case["service_calls"]
                self.assertEqual(result, args[0])

    def test_documented_llm_shapes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(normalize_bulk_issues(["plain text"]), [{"summary": "plain text"}])
            self.assertEqual(
                normalize_bulk_issues(['{"issues":[{"summary":"a"},{"summary":"b"}]}']),
                [{"summary": "a"}, {"summary": "b"}])
            self.assertEqual(
                normalize_bulk_issues([{"issues": [{"summary": "a"}]}]), [{"summary": "a"}])
            self.assertEqual(normalize_bulk_issues([7]), [{"summary": "7"}])

    def test_is_a_pure_function_with_no_service_or_mcp_dependency(self):
        import src.tools.bulk_issue_input as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
        imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"json"})

    def test_does_not_mutate_its_input(self):
        original = [{"issues": [{"summary": "a"}]}, '{"summary": "b"}']
        snapshot = json.loads(json.dumps(original))
        with contextlib.redirect_stdout(io.StringIO()):
            normalize_bulk_issues(original)
        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main()
