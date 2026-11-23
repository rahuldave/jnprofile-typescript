"""Run the recipe quick of the base with real just, uv, git, biome, tsc and node."""

import unittest

from test_steps import CODE, MODULE, TEST, TOOLS, Project

# A module with no tool: the base only.
BASE = "set positional-arguments\nset working-directory := '../..'\nimport? 'typescript/base.just'\n"
# The test of test_steps, with its imports in the order that the lint of biome wants.
SORTED = TEST.replace('import { test } from "node:test";\nimport assert from "node:assert/strict";\n',
                      'import assert from "node:assert/strict";\nimport { test } from "node:test";\n')
FAILING = SORTED.replace("3);", "4);")


@unittest.skipUnless(TOOLS, "needs just, uv and git")
class QuickTests(Project):
    def setUp(self) -> None:
        super().setUp()
        self.write("src/app.test.ts", SORTED)

    def test_quick_runs_the_unit_tests_with_no_coverage_and_writes_no_report(self) -> None:
        code, out = self.just("typescript::quick")
        self.assertEqual(code, 0, out)
        self.assertIn("ℹ pass 1", out)
        self.assertNotIn("% Stmts", out)
        self.assertFalse((self.root / ".jnprofile-typescript/lcov.info").exists())
        self.assertFalse((self.root / ".jnprofile-typescript/c8").exists())
        self.assertFalse((self.root / ".jnprofile-typescript/build").exists())

    def test_a_failing_test_fails_quick(self) -> None:
        self.write("src/app.test.ts", FAILING)
        code, out = self.just("typescript::quick")
        self.assertNotEqual(code, 0, out)
        self.assertIn("ℹ fail 1", out)

    def test_extra_arguments_go_to_node_test(self) -> None:
        self.write("src/other.test.ts", FAILING.replace('test("add"', 'test("other"'))
        code, out = self.just("typescript::quick", "--test-name-pattern=^add$")
        self.assertEqual(code, 0, out)
        self.assertNotIn("✖", out)
        code, out = self.just("typescript::quick")
        self.assertNotEqual(code, 0, out)

    def test_a_format_problem_fails_quick_and_stops_the_tests(self) -> None:
        self.write("src/app.ts", CODE.replace("a + b", "a+b"))
        code, out = self.just("typescript::quick")
        self.assertNotEqual(code, 0, out)
        self.assertIn("Formatter would have printed", out)
        self.assertNotIn("ℹ pass", out)

    def test_a_lint_problem_fails_quick(self) -> None:
        self.write("src/app.ts", CODE + "\nexport function f(x: number): boolean {\n  return x == 1;\n}\n")
        code, out = self.just("typescript::quick")
        self.assertNotEqual(code, 0, out)
        self.assertIn("noDoubleEquals", out)

    def test_with_no_code_quick_passes_alone_and_fails_with_arguments_as_test_does(self) -> None:
        (self.root / "src/app.ts").unlink()
        (self.root / "src/app.test.ts").unlink()
        code, out = self.just("typescript::quick")
        self.assertEqual(code, 0, out)
        self.assertIn("no code yet", out)
        code, out = self.just("typescript::quick", "--test-name-pattern=x")
        self.assertEqual(code, 1, out)
        self.assertIn("tsconfig.json finds no code", out)

    def test_with_no_tool_quick_runs_nothing_and_passes(self) -> None:
        self.write(".agents/just/typescript.just", BASE)
        self.write("src/app.ts", CODE.replace("a + b", "a+b"))
        self.write("src/app.test.ts", FAILING)
        code, out = self.just("typescript::quick")
        self.assertEqual(code, 0, out)
        self.assertNotIn("biome", out)
        self.assertNotIn("ℹ fail", out)

    def test_quick_runs_typecheck_when_the_tool_is_installed(self) -> None:
        self.write(".agents/just/typescript.just", MODULE + "import? 'typescript/typecheck.just'\n")
        self.write("src/bad.ts", '/** Bad. */\nexport function bad(): number {\n  return "x";\n}\n')
        code, out = self.just("typescript::quick")
        self.assertNotEqual(code, 0, out)
        self.assertIn("error TS2322", out)
        (self.root / "src/bad.ts").unlink()
        code, out = self.just("typescript::quick")
        self.assertEqual(code, 0, out)

    def test_quick_leaves_the_build_and_the_report_of_test_alone(self) -> None:
        self.commit()
        code, out = self.just("typescript::test")
        self.assertEqual(code, 0, out)
        report = (self.root / ".jnprofile-typescript/lcov.info").read_text()
        # tsc removes the build before it writes it again, so a marker in the build of test shows that quick left it.
        marker = self.root / ".jnprofile-typescript/build/marker"
        marker.write_text("x")
        code, out = self.just("typescript::quick")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.root / ".jnprofile-typescript/lcov.info").read_text(), report)
        self.assertTrue(marker.exists())
        self.assertTrue((self.root / ".jnprofile-typescript/quick-build").is_dir())
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")
