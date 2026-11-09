"""
Static regression guard: fails the build if a default/fallback Jira
project (a JIRA_PROJECT_KEY reference or a hardcoded project literal
such as 'KAN') is ever reintroduced into the server's source code under
src/. This operationalizes the "no default project anywhere in the MCP
server" requirement as an automated check, not just a one-time manual
grep.
"""
import re
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


class NoDefaultProjectInSourceTests(unittest.TestCase):
    def _iter_source_files(self):
        for path in sorted(SRC_ROOT.rglob("*.py")):
            yield path, path.read_text(encoding="utf-8")

    def test_no_jira_project_key_reference_under_src(self):
        offenders = [str(p) for p, text in self._iter_source_files() if "JIRA_PROJECT_KEY" in text]
        self.assertEqual(
            offenders, [],
            f"JIRA_PROJECT_KEY must not appear anywhere under src/ (no default/fallback project allowed): {offenders}",
        )

    def test_no_hardcoded_kan_project_literal_under_src(self):
        # Matches a quoted "KAN"/'KAN' literal or a bare `= KAN` assignment,
        # without flagging unrelated words that merely contain "KAN".
        pattern = re.compile(r'["\']KAN["\']|=\s*KAN\b')
        offenders = [str(p) for p, text in self._iter_source_files() if pattern.search(text)]
        self.assertEqual(
            offenders, [],
            f"Hardcoded 'KAN' project literal found under src/: {offenders}",
        )

    def test_no_other_project_default_constants_under_src(self):
        pattern = re.compile(r'\b(DEFAULT_PROJECT|PROJECT_KEY)\s*=')
        offenders = [str(p) for p, text in self._iter_source_files() if pattern.search(text)]
        self.assertEqual(
            offenders, [],
            f"A default project constant (DEFAULT_PROJECT / PROJECT_KEY assignment) was found under src/: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
