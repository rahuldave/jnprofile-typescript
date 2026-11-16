"""The tests of scripts/run_tests.py: in CI a skipped test fails the run."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parent.parent / "scripts/run_tests.py"
SKIPS = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.skipTest("no x")\n'
PASSES = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n'


class RunTestsTests(unittest.TestCase):
    def run_with(self, text: str, ci: str) -> subprocess.CompletedProcess:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder = Path(temp.name) / "tests"
        folder.mkdir()
        (folder / "test_x.py").write_text(text)
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        if ci is not None:
            env["CI"] = ci
        return subprocess.run([sys.executable, "-B", str(RUNNER), str(folder)], capture_output=True, text=True,
                              env=env, check=False)

    def test_a_skip_fails_in_ci(self) -> None:
        for ci in ("true", "1"):
            with self.subTest(ci=ci):
                run = self.run_with(SKIPS, ci)
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertIn("skipped in CI: no x", run.stderr)

    def test_a_skip_passes_outside_ci(self) -> None:
        for ci in (None, "", "false", "0"):
            with self.subTest(ci=ci):
                self.assertEqual(self.run_with(SKIPS, ci).returncode, 0)

    def test_a_pass_passes_in_ci(self) -> None:
        self.assertEqual(self.run_with(PASSES, "true").returncode, 0)


if __name__ == "__main__":
    unittest.main()
