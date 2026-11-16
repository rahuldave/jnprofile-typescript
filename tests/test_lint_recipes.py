"""The tests of scripts/lint_recipes.py, the lint of the recipe files, on copies of the profile."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("lint_recipes", REPO / "scripts/lint_recipes.py")
LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LINT)


class LintRecipesTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / "profile"
        shutil.copytree(REPO / ".agents/just", self.repo / ".agents/just")
        shutil.copy(REPO / "profile.json", self.repo / "profile.json")
        self.folder = self.repo / ".agents/just/typescript"

    def lint(self) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = LINT.main(self.repo)
        return code, out.getvalue() + err.getvalue()

    def test_the_recipes_of_the_profile_pass(self) -> None:
        code, out = self.lint()
        self.assertEqual(code, 0, out)
        self.assertIn("parses, alone and with all of them", out)

    def test_a_recipe_file_that_does_not_parse_fails(self) -> None:
        with (self.folder / "api.just").open("a") as handle:
            handle.write("\nbroken:\n  {{nothing_defines_this}}\n")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("the tool api alone", out)

    def test_a_recipe_file_that_needs_another_tool_fails(self) -> None:
        # A tool file can use only what base.just defines, because a project can have that tool alone.
        (self.folder / "lint.just").write_text((self.folder / "lint.just").read_text()
                                               + "\nuses-other:\n  just {{ts_steps_of_the_test_tool}}\n")
        (self.folder / "test.just").write_text((self.folder / "test.just").read_text()
                                               + "\nts_steps_of_the_test_tool := 'x'\n")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("the tool lint alone", out)

    def test_a_recipe_verify_in_a_tool_file_fails(self) -> None:
        # just install writes the recipe verify into the module file, so a tool file cannot have one.
        with (self.folder / "lint.just").open("a") as handle:
            handle.write("\nverify:\n  true\n")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("the tool lint alone", out)
        self.assertIn("verify", out)

    def test_a_verify_step_with_no_recipe_fails(self) -> None:
        profile = json.loads((self.repo / "profile.json").read_text())
        profile["tools"]["api"]["verify"].append("no-such-recipe")
        (self.repo / "profile.json").write_text(json.dumps(profile))
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("the tool api alone", out)
        self.assertIn("no-such-recipe", out)

    def test_a_recipe_file_that_no_tool_names_fails(self) -> None:
        (self.folder / "stray.just").write_text("stray:\n  true\n")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("stray.just: no tool of profile.json names it", out)


if __name__ == "__main__":
    unittest.main()
