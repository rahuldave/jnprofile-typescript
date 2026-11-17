"""Run the steps fmt-check, test, coverage-check and docstring-check, and test-paths, with real just, uv, git and node.

The projects of the tests share one node_modules and one cache of npm, which the first test installs, so that each
project needs no install of its own. Each project links them in.
"""

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

REPO = Path(__file__).resolve().parents[1]
FOLDER = REPO / ".agents/just/typescript"
PROFILE = json.loads((REPO / "profile.json").read_text())
NPM = ["uvx", "--quiet", "--from", "nodejs-wheel==24.*", "npm"]
def clean_env(environ) -> dict:
    """The variables of ENVIRON for a project of the tests: without those of git, the run ID of jlog, and the
    variables of CI, such as CI and GITHUB_EVENT_NAME, that set the base of api-prose-check. A test that needs CI
    sets them itself."""
    return {k: v for k, v in environ.items()
            if not k.startswith(("GIT_", "GITHUB_")) and k not in ("JLOG_RUN", "CI")}


# The module file as just install writes it, without the shell of jlog.
MODULE = """set positional-arguments
set working-directory := '../..'
import? 'typescript/base.just'
import? 'typescript/lint.just'
import? 'typescript/test.just'
import? 'typescript/docstring.just'
"""
TSCONFIG = {
    "compilerOptions": {"target": "ES2023", "module": "NodeNext", "moduleResolution": "NodeNext", "strict": True,
                        "outDir": "${configDir}/dist", "rootDir": "${configDir}/src", "sourceMap": True,
                        "skipLibCheck": True, "types": ["node"]},
    "include": ["${configDir}/src"],
}
# The settings of files/lint.json, for the files in src only.
BIOME = ('{\n  "files": { "includes": ["src/**"] },\n  "formatter": { "indentStyle": "space", "lineWidth": 120 }\n}\n')
PACKAGE = {"name": "app", "version": "0.0.0", "type": "module", "private": True}
CODE = "/** Add A and B. */\nexport function add(a: number, b: number): number {\n  return a + b;\n}\n"
TEST = ('import { test } from "node:test";\nimport assert from "node:assert/strict";\n'
        'import { add } from "./app.js";\n\n'
        'test("add", () => {\n  assert.equal(add(1, 2), 3);\n});\n')
UNTESTED = "\n/** Subtract B from A. */\nexport function sub(a: number, b: number): number {\n  return a - b;\n}\n"
# A case that no test runs. c8 marks only its line as not run, so /* c8 ignore next */ above that line exempts it.
CASE = ("/** Add A and B. */\nexport function add(a: number, b: number): number {\n  switch (b) {\n    case -1:\n"
        "      return 0;\n    default:\n      return a + b;\n  }\n}\n")
# The links node_modules and .local have no / at the end, because git sees a link as a file.
IGNORE = "node_modules\n.local\ndist/\n.jnprofile-typescript/\n"
SHARED = {}


def shared():
    """The folder with the node_modules and the cache of npm that each project links in. The first call installs."""
    if not SHARED:
        folder = Path(tempfile.mkdtemp(prefix="jnprofile-typescript-tests-"))
        (folder / "package.json").write_text(json.dumps(PACKAGE))
        env = dict(os.environ, npm_config_cache=str(folder / ".local/npm-cache"))
        packages = PROFILE["tools"]["test"]["packages"] + PROFILE["tools"]["lint"]["packages"]
        # npm can finish without an optional package, such as the binary of tsc for the platform, when the network
        # fails. So the install runs again until tsc runs.
        for _ in range(3):
            subprocess.run([*NPM, "install", "--no-audit", "--no-fund", "--save-dev", *packages], cwd=folder, env=env,
                           check=True, capture_output=True)
            if subprocess.run([*NPM, "exec", "--", "tsc", "--version"], cwd=folder, env=env,
                              capture_output=True).returncode == 0:
                break
            shutil.rmtree(folder / "node_modules")
        else:
            raise RuntimeError("npm cannot install a tsc that runs")
        SHARED["folder"] = folder
    return SHARED["folder"]


def tearDownModule() -> None:
    """Remove the shared folder."""
    if SHARED:
        shutil.rmtree(SHARED["folder"], ignore_errors=True)


def load_steps():
    """The module steps.py of the profile."""
    # No __pycache__ in the folder that the installer copies.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(FOLDER))
    try:
        import steps
    finally:
        sys.path.pop(0)
    return steps


TOOLS = shutil.which("just") and shutil.which("uv") and shutil.which("git")


class Project(unittest.TestCase):
    """A TypeScript project in a temporary folder, with the recipe files of the profile and one tested function."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(os.path.realpath(temp.name))
        shutil.copytree(FOLDER, self.root / ".agents/just/typescript")
        (self.root / ".agents/just/typescript.just").write_text(MODULE)
        (self.root / "Justfile").write_text('export JLOG_RUN := env("JLOG_RUN", uuid())\n'
                                            'mod typescript ".agents/just/typescript.just"\n')
        folder = shared()
        (self.root / "node_modules").symlink_to(folder / "node_modules")
        (self.root / ".local").symlink_to(folder / ".local")
        self.write("package.json", json.dumps(PACKAGE))
        self.write("tsconfig.json", json.dumps(TSCONFIG))
        self.write("biome.json", BIOME)
        self.write(".gitignore", IGNORE)
        self.write("src/app.ts", CODE)
        self.write("src/app.test.ts", TEST)
        self.env = clean_env(os.environ)
        self.env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@example.com")
        self.git("init", "-q")

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.root, check=True, env=self.env,
                              capture_output=True, text=True).stdout

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "c")

    def just(self, *args: str, env: dict = None, cwd: Path = None) -> tuple:
        run = subprocess.run(["just", *args], cwd=cwd or self.root, capture_output=True, text=True,
                             env=env or self.env)
        return run.returncode, run.stdout + run.stderr


@unittest.skipUnless(TOOLS, "needs just, uv and git")
class StepTests(Project):
    def test_test_writes_lcov_into_an_ignored_folder_and_the_tree_stays_clean(self) -> None:
        self.commit()
        code, out = self.just("typescript::test")
        self.assertEqual(code, 0, out)
        report = (self.root / ".jnprofile-typescript/lcov.info").read_text()
        self.assertIn("SF:src/app.ts", report)
        self.assertNotIn("app.test", report)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_an_untested_changed_line_fails_and_c8_ignore_next_makes_it_pass(self) -> None:
        self.commit()
        self.write("src/app.ts", CASE)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/app.ts (83.3%): Missing lines 5", out)
        self.assertIn("write tests", out)
        self.write("src/app.ts", CASE.replace("      return 0;", "      /* c8 ignore next */\n      return 0;"))
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)
        # The reason that test-review.md asks for goes in the same comment.
        self.write("src/app.ts", CASE.replace("      return 0;",
                                              "      /* c8 ignore next -- no caller passes -1 */\n      return 0;"))
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)

    def test_a_failed_test_fails_test_and_coverage_check(self) -> None:
        self.commit()
        self.write("src/app.test.ts", TEST.replace("3);", "4);"))
        code, out = self.just("typescript::test")
        self.assertEqual(code, 1, out)
        code, out = self.just("typescript::coverage-check")
        self.assertNotEqual(code, 0, out)

    def test_changed_code_with_no_test_fails_and_says_write_tests(self) -> None:
        (self.root / "src/app.test.ts").unlink()
        self.commit()
        self.write("src/n.ts", "/** N. */\nexport function n(): number {\n  return 1;\n}\n")
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("there is no coverage report .jnprofile-typescript/lcov.info, so write tests", out)

    def test_a_failing_mts_or_cts_test_fails_test(self) -> None:
        for name in ("src/b.test.mts", "src/c.test.cts"):
            with self.subTest(name=name):
                self.write(name, 'import { test } from "node:test";\n\ntest("fails", () => {\n'
                                 '  throw new Error("f");\n});\n')
                code, out = self.just("typescript::test")
                self.assertEqual(code, 1, out)
                self.assertIn("✖ fails", out)
                (self.root / name).unlink()

    def sub_tested_then_untested(self) -> None:
        """Commit sub() with a test of its own and run the tests, then delete that test and change sub()."""
        self.write("src/app.ts", CODE + UNTESTED)
        self.write("src/sub.test.ts", 'import { test } from "node:test";\nimport { sub } from "./app.js";\n\n'
                                      'test("sub", () => {\n  sub(3, 1);\n});\n')
        self.commit()
        self.assertEqual(self.just("typescript::test")[0], 0)
        (self.root / "src/sub.test.ts").unlink()
        self.write("src/app.ts", CODE + UNTESTED.replace("return a - b;", "const r = a - b;\n  return r;"))

    def test_the_old_output_of_a_deleted_test_does_not_run(self) -> None:
        self.sub_tested_then_untested()
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/app.ts", out)
        self.assertNotIn("✔ sub", out)

    def test_old_coverage_does_not_count_with_clean_false_in_the_c8_config(self) -> None:
        self.write(".c8rc.json", '{ "clean": false }\n')
        self.commit()
        # A run of the tests while sub() had a test. The code stays the same, so old coverage would match it.
        self.write("src/app.ts", CODE + UNTESTED)
        self.write("src/sub.test.ts", 'import { test } from "node:test";\nimport { sub } from "./app.js";\n\n'
                                      'test("sub", () => {\n  sub(3, 1);\n});\n')
        self.assertEqual(self.just("typescript::test")[0], 0)
        (self.root / "src/sub.test.ts").unlink()
        # No old build, so only the raw coverage of c8 could hold the old run.
        for folder in ("dist", ".jnprofile-typescript/build"):
            shutil.rmtree(self.root / folder, ignore_errors=True)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)

    def test_a_file_in_a_folder_node_modules_counts_for_no_step(self) -> None:
        self.commit()
        self.write("lib/node_modules/x/nm.ts", "export function nm(): number {\n  return 1;\n}\n")
        self.git("add", "-f", "lib/node_modules/x/nm.ts")
        for step in ("coverage-check", "docstring-check"):
            code, out = self.just(f"typescript::{step}")
            self.assertEqual(code, 0, f"{step}: {out}")

    def test_an_incremental_project_runs_its_tests_on_each_run(self) -> None:
        self.write("tsconfig.json", json.dumps({**TSCONFIG, "compilerOptions": {
            **TSCONFIG["compilerOptions"], "incremental": True, "tsBuildInfoFile": "./.cache/app.tsbuildinfo"}}))
        self.write(".gitignore", IGNORE + ".cache/\n")
        for _ in range(2):
            code, out = self.just("typescript::test")
            self.assertEqual(code, 0, out)
            self.assertIn("✔ add", out)

    def options(self, **options) -> None:
        """Write tsconfig.json with the settings of the profile and OPTIONS."""
        self.write("tsconfig.json", json.dumps({**TSCONFIG, "compilerOptions": {**TSCONFIG["compilerOptions"],
                                                                               **options}}))

    def test_a_test_file_that_tsc_does_not_compile_fails_test(self) -> None:
        self.write("tests/outside.test.ts", 'import { test } from "node:test";\n\ntest("outside", () => {});\n')
        code, out = self.just("typescript::test")
        self.assertEqual(code, 1, out)
        self.assertIn("tests/outside.test.ts: tsc writes no output for this test file", out)

    def test_a_test_file_outside_an_include_that_finds_no_code_fails_test(self) -> None:
        shutil.rmtree(self.root / "src")
        self.write("tests/outside.test.ts", 'import { test } from "node:test";\n\ntest("outside", () => {});\n')
        code, out = self.just("typescript::test")
        self.assertEqual(code, 1, out)
        self.assertIn("tests/outside.test.ts: tsc writes no output", out)

    def test_no_emit_and_emit_declaration_only_still_run_the_tests(self) -> None:
        for options in ({"noEmit": True}, {"declaration": True, "emitDeclarationOnly": True}):
            with self.subTest(options=options):
                self.options(**options)
                code, out = self.just("typescript::test")
                self.assertEqual(code, 0, out)
                self.assertIn("✔ add", out)

    def test_a_tsx_test_with_jsx_preserve_is_not_left_out(self) -> None:
        # node cannot run the .jsx output, so the test fails, where a glob of .js only would skip it and pass.
        self.options(jsx="preserve")
        self.write("src/view.test.tsx", 'import { test } from "node:test";\n\ntest("view", () => {});\n')
        code, out = self.just("typescript::test")
        self.assertEqual(code, 1, out)
        self.assertIn("✖ .jnprofile-typescript/build/src/view.test.jsx", out)

    def test_declarations_go_into_the_build_and_the_tree_stays_clean(self) -> None:
        self.options(composite=True, declarationDir="types")
        self.commit()
        code, out = self.just("typescript::test")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / "types").exists(), out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_a_file_with_no_exports_is_no_file_of_types_with_declaration_maps(self) -> None:
        self.options(composite=True, declarationDir="types", declarationMap=True)
        self.commit()
        self.write("src/main.ts", 'import { add } from "./app.js";\n\nconsole.log(add(1, 2));\n')
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/main.ts: a changed file that is not in the coverage report", out)

    def test_an_untested_one_line_arrow_function_fails_and_c8_ignore_next_makes_it_pass(self) -> None:
        self.commit()
        arrow = "\n/** Multiply A and B. */\nexport const mul = (a: number, b: number): number => a * b;\n"
        self.write("src/app.ts", CODE + arrow)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("Missing lines 7", out)
        self.write("src/app.ts", CODE + arrow.replace("export const", "/* c8 ignore next */\nexport const"))
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)

    def test_a_file_of_types_only_needs_no_test(self) -> None:
        self.commit()
        self.write("src/types.ts", "/** A point. */\nexport interface Point {\n  x: number;\n}\n\n"
                                   "/** An id. */\nexport type Id = string;\n")
        self.write("src/app.ts", 'import type { Point } from "./types.js";\n\n' + CODE +
                   "\n/** The x of P. */\nexport function x(p: Point): number {\n  return p.x;\n}\n")
        self.write("src/app.test.ts", TEST + '\ntest("x", () => {\n  assert.equal(x({ x: 1 }), 1);\n});\n')
        self.write("src/app.test.ts", (self.root / "src/app.test.ts").read_text().replace("{ add }", "{ add, x }"))
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)

    def test_code_files_that_the_default_excludes_of_c8_would_drop_count(self) -> None:
        self.commit()
        for name in ("src/__tests__/helper.ts", "src/ab-test.ts"):
            self.write(name, "/** One. */\nexport function one(): number {\n  return 1;\n}\n")
        self.write("src/h.test.ts", 'import { test } from "node:test";\nimport { one } from "./__tests__/helper.js";\n'
                                    'import { one as two } from "./ab-test.js";\n\ntest("one", () => {\n'
                                    '  one();\n  two();\n});\n')
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)
        report = (self.root / ".jnprofile-typescript/lcov.info").read_text()
        self.assertIn("SF:src/__tests__/helper.ts", report)
        self.assertIn("SF:src/ab-test.ts", report)
        self.assertNotIn("h.test", report)

    def test_a_project_with_no_source_maps_still_maps_the_coverage_to_src(self) -> None:
        self.write("tsconfig.json", json.dumps({**TSCONFIG, "compilerOptions": {
            **TSCONFIG["compilerOptions"], "sourceMap": False}}))
        self.commit()
        self.write("src/app.ts", CODE + UNTESTED)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/app.ts (", out)
        self.assertNotIn("Traceback", out)

    def test_a_changed_file_that_no_test_imports_fails(self) -> None:
        self.commit()
        self.write("src/n.ts", "/** N. */\nexport function n(): number {\n  return 1;\n}\n")
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/n.ts: a changed file that is not in the coverage report", out)

    def test_a_generated_path_of_the_parent_is_exempt_and_a_commit_cannot_exempt_itself(self) -> None:
        self.commit()
        # The commit that adds gen.ts also lists it: the list of the parent does not have it, so both steps fail.
        self.write(".agents/generated.txt", "# made by a tool\nsrc/gen.ts\n")
        self.write("src/gen.ts", "export function made(): number {\n  return 1;\n}\n")
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/gen.ts: a changed file that is not in the coverage report", out)
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/gen.ts:1: no JSDoc comment: export function made()", out)
        # Once the parent lists it, a change to gen.ts fails neither step.
        self.commit()
        self.write("src/gen.ts", "export function made(): number {\n  return 2;\n}\n")
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 0, out)

    def test_a_coverage_exclude_path_of_the_parent_is_exempt_from_coverage_check_only(self) -> None:
        self.write(".agents/coverage-exclude.txt", "src/cli.ts\n")
        self.commit()
        self.write("src/cli.ts", "export function main(): number {\n  return 1;\n}\n")
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/cli.ts:1:", out)

    def test_the_first_commit_needs_every_line_of_code_to_run(self) -> None:
        self.write("src/app.ts", CODE + UNTESTED)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("the first commit, so every line of code must run", out)
        self.assertIn("src/app.ts:8: no test runs this line", out)
        self.write("src/app.ts", CODE)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)

    def test_an_untracked_file_in_a_project_in_a_subfolder_needs_each_line_to_run(self) -> None:
        # The git repository is one folder up, so the project is a subfolder of it.
        sub = self.root / "app"
        sub.mkdir()
        for name in [p.name for p in self.root.iterdir() if p.name not in ("app", ".git")]:
            shutil.move(str(self.root / name), str(sub / name))
        self.root = sub
        self.commit()
        self.write("src/n.ts", "/** F. */\nexport function f(): number {\n  return 1;\n}\n\n"
                               "/** G. */\nexport function g(): number {\n  return 2;\n}\n")
        self.write("src/n.test.ts", 'import { test } from "node:test";\nimport { f } from "./n.js";\n\n'
                                    'test("f", () => {\n  f();\n});\n')
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/n.ts:8: no test runs this line", out)
        # A tracked file in the subfolder goes through diff-cover.
        self.write("src/n.test.ts", 'import { test } from "node:test";\nimport { f, g } from "./n.js";\n\n'
                                    'test("f", () => {\n  f();\n  g();\n});\n')
        self.commit()
        self.write("src/app.ts", CODE + UNTESTED)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"app/src/app.ts \(\d+\.\d%\): Missing lines [78]-9")

    def test_coverage_check_reads_the_report_of_test_in_the_same_run(self) -> None:
        env = dict(self.env, JLOG_RUN="run-1")
        code, out = self.just("typescript::test", env=env)
        self.assertEqual(code, 0, out)
        code, out = self.just("typescript::coverage-check", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("the tests of this run, run-1, wrote the report, so they do not run again", out)
        # Another run, or a change to the tree, runs the tests again.
        code, out = self.just("typescript::coverage-check", env=dict(self.env, JLOG_RUN="run-2"))
        self.assertIn("no report of the tests of this run and this tree, so they run now", out)
        self.just("typescript::test", env=env)
        self.write("src/app.ts", CODE + "\n")
        code, out = self.just("typescript::coverage-check", env=env)
        self.assertIn("no report of the tests of this run and this tree, so they run now", out)

    def test_a_project_with_no_code_yet_passes_test_and_coverage_check(self) -> None:
        shutil.rmtree(self.root / "src")
        for step in ("test", "coverage-check", "docstring-check"):
            code, out = self.just(f"typescript::{step}")
            self.assertEqual(code, 0, f"{step}: {out}")

    def test_docstring_check_names_a_private_function_with_no_jsdoc(self) -> None:
        self.write("src/app.ts", CODE + "\nfunction helper(): number {\n  return 0;\n}\n\n"
                   "const twice = (x: number): number => x * 2;\n\nclass K {\n  private m(): void {}\n"
                   "  constructor() {}\n}\n\nexport const xs = [1, 2].map((x) => helper() + twice(x) + x);\n"
                   "export const k = new K();\n")
        self.write("src/types.d.ts", "export declare function f(): void;\n")
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/app.ts:6: no JSDoc comment: function helper()", out)
        self.assertIn("src/app.ts:10: no JSDoc comment: const twice = ", out)
        self.assertIn("src/app.ts:12: no JSDoc comment: class K {", out)
        self.assertIn("src/app.ts:13: no JSDoc comment: private m()", out)
        # A constructor, an inline callback, a test file, a declaration file and the folder .agents do not count.
        self.assertNotIn("src/app.ts:14:", out)
        self.assertNotIn("src/app.ts:17:", out)
        self.assertNotIn("app.test.ts", out)
        self.assertNotIn("types.d.ts", out)
        self.assertFalse([line for line in out.splitlines() if line.startswith(".agents")], out)

    def test_docstring_check_names_an_abstract_method_and_leaves_out_signatures(self) -> None:
        self.write("src/shape.ts", "/** A shape. */\nexport abstract class Shape {\n  abstract area(): number;\n}\n\n"
                   "/** A point. */\nexport interface Point {\n  norm(): number;\n}\n\n"
                   "export function f(x: number): number;\nexport function f(x: string): string;\n"
                   "/** F. */\nexport function f(x: unknown): unknown {\n  return x;\n}\n\n"
                   "export namespace N {\n  export const v = 1;\n}\n")
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 1, out)
        self.assertIn("src/shape.ts:3: no JSDoc comment: abstract area(): number;", out)
        findings = [line for line in out.splitlines() if line.startswith("src/shape.ts:")]
        self.assertEqual(len(findings), 1, out)

    def test_docstring_check_names_a_function_in_a_type_expression(self) -> None:
        wrapped = ("export const s = (() => 1) satisfies () => number;\nexport const f = (() => 5) as () => number;\n"
                   "export const t = (() => 1)!;\nexport const u = <() => number>(() => 1);\n")
        self.write("src/wrap.ts", wrapped)
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 1, out)
        for line in range(1, 5):
            self.assertIn(f"src/wrap.ts:{line}: no JSDoc comment", out)
        self.write("src/wrap.ts", "".join(f"/** Item. */\n{line}\n" for line in wrapped.splitlines()))
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 0, out)

    def test_docstring_check_passes_documented_code_and_ignores_the_eslint_config_of_the_project(self) -> None:
        # A config of the project that fails each file, if eslint read it.
        self.write("eslint.config.mjs", 'export default [{ rules: { "no-unused-vars": "error" } }];\n')
        self.write("src/app.ts", CODE + "\n/** Unused. */\nfunction unused(): void {}\n")
        code, out = self.just("typescript::docstring-check")
        self.assertEqual(code, 0, out)

    def test_fmt_check_fails_on_code_that_biome_would_change_and_changes_no_file(self) -> None:
        self.write("src/app.ts", CODE.replace("a + b", "a+b"))
        code, out = self.just("typescript::fmt-check")
        self.assertEqual(code, 1, out)
        self.assertIn("a+b", (self.root / "src/app.ts").read_text())
        self.write("src/app.ts", CODE)
        code, out = self.just("typescript::fmt-check")
        self.assertEqual(code, 0, out)

    def test_fmt_check_leaves_markdown_to_the_prose_check(self) -> None:
        # The docs role of jnterfaces writes docs/index.md with front matter. biome must not format a page.
        # The config of the profile, not the one of this lab, which reads src only.
        self.write("biome.json", (REPO / "files/lint.json").read_text())
        # That config also reads the JSON files of the lab, so they get the format of biome.
        self.assertEqual(self.just("typescript::fmt", "package.json", "tsconfig.json")[0], 0)
        self.write("docs/index.md", "---\ntitle: Home\n---\n\nThe home page.\n")
        code, out = self.just("typescript::fmt-check")
        self.assertEqual(code, 0, out)


TEST_FILES = {
    "src/pass.test.ts": 'import { test } from "node:test";\nimport { add } from "./app.js";\n\n'
                        'test("pass a", () => {\n  if (add(1, 2) !== 3) throw new Error("no");\n});\n',
    "src/fail.test.ts": 'import { test } from "node:test";\n\ntest("fail f", () => {\n  throw new Error("f");\n});\n',
    "src/new.test.ts": 'import { test } from "node:test";\nimport { nope } from "./app.js";\n\n'
                       'test("new n", () => {\n  nope();\n});\n',
    "src/skip.test.ts": 'import { test } from "node:test";\n\ntest.skip("skip s", () => {});\n'
                        'test.todo("todo t", () => {});\n',
    "src/empty.test.ts": "export const x = 1;\n",
    "src/mixed.test.ts": 'import { test } from "node:test";\n\ntest("mixed a", () => {});\n'
                         'test("mixed f", () => {\n  throw new Error("f");\n});\n',
    "src/exit0.test.ts": 'import { test } from "node:test";\n\ntest("exit a", () => {});\n'
                         'test("exit b", () => {\n  process.exit(0);\n});\n',
    "src/exit1.test.ts": 'import { test } from "node:test";\n\ntest("exit1 a", () => {\n  process.exit(1);\n});\n',
    "src/-dash.test.ts": 'import { test } from "node:test";\n\ntest("dash d", () => {});\n',
    "src/sub/deep.test.mts": 'import { test } from "node:test";\n\ntest("deep d", () => {});\n',
    "other/outside.test.ts": 'import { test } from "node:test";\n\ntest("outside o", () => {});\n',
}


@unittest.skipUnless(TOOLS, "needs just, uv and git")
class TestPathsTests(Project):
    def setUp(self) -> None:
        super().setUp()
        for name, text in TEST_FILES.items():
            self.write(name, text)

    def paths(self, *files: str) -> tuple:
        return self.just("typescript::test-paths", *files)

    def test_each_case_gives_its_code(self) -> None:
        cases = ((("src/pass.test.ts",), 0), (("src/fail.test.ts",), 1), (("src/new.test.ts",), 1),
                 (("src/skip.test.ts",), 5), (("src/empty.test.ts",), 5), ((), 5), (("src/mixed.test.ts",), 1),
                 (("src/exit0.test.ts",), 2), (("src/exit1.test.ts",), 2), (("src/-dash.test.ts",), 0),
                 (("./src/sub/deep.test.mts",), 0), (("other/outside.test.ts",), 2))
        for files, code in cases:
            with self.subTest(files=files):
                got, out = self.paths(*files)
                self.assertEqual(got, code, out)

    def test_a_file_that_does_not_build_hides_no_other_file(self) -> None:
        code, out = self.paths("src/pass.test.ts")
        self.assertEqual(code, 0, out)
        code, out = self.paths("src/new.test.ts", "src/pass.test.ts")
        self.assertEqual(code, 1, out)
        self.assertIn("src/new.test.ts(2,10): error TS2305", out)

    def test_no_emit_on_error_in_the_project_does_not_stop_the_build(self) -> None:
        self.write("tsconfig.json", json.dumps({**TSCONFIG, "compilerOptions": {**TSCONFIG["compilerOptions"],
                                                                               "noEmitOnError": True}}))
        self.write("src/bad.ts", '/** Bad. */\nexport const bad: number = "x";\n')
        code, out = self.paths("src/pass.test.ts")
        self.assertEqual(code, 0, out)

    def test_declarations_of_test_paths_go_into_its_build(self) -> None:
        for name in TEST_FILES:
            if name != "src/pass.test.ts":
                (self.root / name).unlink()
        self.write("tsconfig.json", json.dumps({**TSCONFIG, "compilerOptions": {
            **TSCONFIG["compilerOptions"], "composite": True, "declarationDir": "types"}}))
        self.commit()
        code, out = self.paths("src/pass.test.ts")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_an_incremental_project_builds_again_on_each_run(self) -> None:
        self.write("tsconfig.json", json.dumps({**TSCONFIG, "compilerOptions": {
            **TSCONFIG["compilerOptions"], "incremental": True, "tsBuildInfoFile": "./.cache/app.tsbuildinfo"}}))
        for _ in range(2):
            code, out = self.paths("src/pass.test.ts")
            self.assertEqual(code, 0, out)

    def test_each_test_has_its_line(self) -> None:
        code, out = self.paths("src/mixed.test.ts")
        self.assertEqual(code, 1, out)
        self.assertIn("✔ mixed a", out)
        self.assertIn("✖ mixed f", out)

    def test_a_worktree_with_no_node_modules_installs_them_first(self) -> None:
        (self.root / "node_modules").unlink()
        folder = shared()
        shutil.copy(folder / "package.json", self.root / "package.json")
        shutil.copy(folder / "package-lock.json", self.root / "package-lock.json")
        code, out = self.paths("src/pass.test.ts")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "node_modules/.bin").is_dir())

    def test_test_paths_writes_no_file_that_git_does_not_ignore(self) -> None:
        for name in TEST_FILES:
            (self.root / name).unlink()
        self.commit()
        self.write("src/pass.test.ts", TEST_FILES["src/pass.test.ts"])
        self.paths("src/pass.test.ts")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "?? src/pass.test.ts\n")


# A function that only the integration test runs, and that test, which imports the code from src.
ONLY_INTEGRATION = "\n/** Double A. */\nexport function twice(a: number): number {\n  return a * 2;\n}\n"
INTEGRATION_TEST = ('import { test } from "node:test";\nimport assert from "node:assert/strict";\n'
                    'import { twice } from "../../src/app.js";\n\ntest("twice", () => {\n  assert.equal(twice(2), 4);\n'
                    '});\n')
STEPS = ["fmt-check", "lint", "typecheck", "test", "integration", "coverage-check", "docstring-check", "docs-check",
         "prose-check", "diff-check"]


@unittest.skipUnless(TOOLS, "needs just, uv and git")
class IntegrationTests(Project):
    """A project with the integration tool, and a function that only an integration test runs."""

    def setUp(self) -> None:
        super().setUp()
        self.module(integration=True)
        self.steps(STEPS)
        self.commit()
        self.write("src/app.ts", CODE + ONLY_INTEGRATION)
        self.write("tests/integration/app.test.ts", INTEGRATION_TEST)

    def module(self, integration: bool) -> None:
        """Write the module file, with the integration tool when INTEGRATION is True."""
        extra = "import? 'typescript/integration.just'\n" if integration else ""
        (self.root / ".agents/just/typescript.just").write_text(MODULE + extra)

    def steps(self, steps: list) -> None:
        """Write .agents/stack.json with the key steps, as the installer writes it."""
        self.write(".agents/stack.json", json.dumps({"steps": steps}) + "\n")

    def test_a_line_that_only_integration_runs_passes_coverage_check_when_integration_is_a_step(self) -> None:
        env = dict(self.env, JLOG_RUN="run-1")
        code, out = self.just("typescript::test", env=env)
        self.assertEqual(code, 0, out)
        code, out = self.just("typescript::integration", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("✔ twice", out)
        report = (self.root / ".jnprofile-typescript/integration/lcov.info").read_text()
        self.assertIn("SF:src/app.ts", report)
        code, out = self.just("typescript::coverage-check", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("the integration tests of this run, run-1, wrote the report, so they do not run again", out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"),
                         " M src/app.ts\n?? tests/integration/app.test.ts\n")

    def test_without_integration_in_the_steps_the_line_fails_coverage_check(self) -> None:
        # The answer integration=verify leaves integration out of just check, so its report does not count.
        self.steps([step for step in STEPS if step != "integration"])
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("Missing lines", out)
        self.assertNotIn("✔ twice", out)

    def test_without_the_integration_tool_test_runs_the_integration_tests_and_the_line_counts(self) -> None:
        self.module(integration=False)
        code, out = self.just("typescript::test")
        self.assertEqual(code, 0, out)
        self.assertIn("✔ twice", out)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 0, out)

    def test_with_the_integration_tool_test_and_cov_leave_out_the_integration_tests(self) -> None:
        for recipe in ("test", "cov"):
            with self.subTest(recipe=recipe):
                code, out = self.just(f"typescript::{recipe}")
                self.assertEqual(code, 0, out)
                self.assertIn("✔ add", out)
                self.assertNotIn("✔ twice", out)
        self.assertFalse((self.root / ".jnprofile-typescript/build/tests/integration").exists())

    def test_coverage_check_runs_integration_once_and_the_step_then_does_not_run_it_again(self) -> None:
        env = dict(self.env, JLOG_RUN="run-1")
        code, out = self.just("typescript::coverage-check", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("no report of the integration tests of this run and this tree, so they run now", out)
        self.assertIn("✔ twice", out)
        code, out = self.just("typescript::integration", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("integration: it passed before in this run, run-1, on this tree, so it does not run again", out)
        self.assertNotIn("✔ twice", out)
        # Another run, a change to the tree, or an argument runs them again.
        for other, change in ((dict(self.env, JLOG_RUN="run-2"), False), (env, True)):
            if change:
                self.write("src/app.ts", CODE + ONLY_INTEGRATION + "\n")
            code, out = self.just("typescript::integration", env=other)
            self.assertEqual(code, 0, out)
            self.assertIn("✔ twice", out)
        code, out = self.just("typescript::integration", "--test-name-pattern=twice", env=env)
        self.assertIn("✔ twice", out)

    def test_a_failed_integration_test_fails_integration_and_coverage_check(self) -> None:
        self.write("tests/integration/app.test.ts", INTEGRATION_TEST.replace("4);", "5);"))
        code, out = self.just("typescript::integration")
        self.assertEqual(code, 1, out)
        code, out = self.just("typescript::coverage-check")
        self.assertNotEqual(code, 0, out)

    def test_integration_with_no_integration_tests_passes_and_fails_with_arguments(self) -> None:
        shutil.rmtree(self.root / "tests")
        code, out = self.just("typescript::integration")
        self.assertEqual(code, 0, out)
        self.assertIn("just integration: no integration tests yet, in tests/integration", out)
        code, out = self.just("typescript::integration", "--test-name-pattern=x")
        self.assertEqual(code, 1, out)
        # With no integration test, coverage-check reads the report of test only, and sub() is not run.
        self.write("src/app.ts", CODE + UNTESTED)
        code, out = self.just("typescript::coverage-check")
        self.assertEqual(code, 1, out)
        self.assertIn("Missing lines", out)

    def test_an_exclude_of_the_tests_folder_does_not_hide_the_integration_tests(self) -> None:
        self.write("tsconfig.json", json.dumps(dict(TSCONFIG, exclude=["${configDir}/tests"])))
        code, out = self.just("typescript::integration")
        self.assertEqual(code, 0, out)
        self.assertIn("✔ twice", out)

    def test_an_include_that_has_tests_already_needs_no_extra_config(self) -> None:
        options = dict(TSCONFIG["compilerOptions"], rootDir="${configDir}")
        self.write("tsconfig.json", json.dumps(dict(TSCONFIG, compilerOptions=options,
                                                    include=["${configDir}/src", "${configDir}/tests"])))
        for recipe in ("integration", "test"):
            code, out = self.just(f"typescript::{recipe}")
            self.assertEqual(code, 0, out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"),
                         " M src/app.ts\n M tsconfig.json\n?? tests/integration/app.test.ts\n")
        self.assertNotIn("✔ twice", out)

    def test_a_relative_include_or_exclude_still_means_the_folder_of_the_project(self) -> None:
        options = {k: v for k, v in TSCONFIG["compilerOptions"].items() if k not in ("outDir", "rootDir")}
        self.write("tsconfig.json", json.dumps({"compilerOptions": options, "include": ["src"],
                                                "exclude": ["src/broken"]}))
        self.write("src/broken/bad.ts", "export const x: number = 'no';\n")
        for integration in (False, True):
            with self.subTest(integration=integration):
                self.module(integration=integration)
                code, out = self.just("typescript::test")
                self.assertEqual(code, 0, out)
                code, out = self.just("typescript::test-paths", "src/app.test.ts", "tests/integration/app.test.ts")
                self.assertEqual(code, 0, out)
                self.assertIn("✔ twice", out)
        code, out = self.just("typescript::integration")
        self.assertEqual(code, 0, out)

    def test_a_config_dir_path_of_the_project_means_the_top_of_the_project(self) -> None:
        options = dict(TSCONFIG["compilerOptions"], typeRoots=["${configDir}/node_modules/@types"])
        self.write("tsconfig.json", json.dumps(dict(TSCONFIG, compilerOptions=options)))
        code, out = self.just("typescript::integration")
        self.assertEqual(code, 0, out)
        self.assertIn("✔ twice", out)

    def test_an_exclude_glob_of_the_tests_folder_does_not_hide_the_integration_tests(self) -> None:
        self.write("tsconfig.json", json.dumps(dict(TSCONFIG, exclude=["${configDir}/tests/**"])))
        code, out = self.just("typescript::integration")
        self.assertEqual(code, 0, out)
        self.assertIn("✔ twice", out)

    def test_test_with_arguments_fails_when_the_include_finds_no_code_and_only_integration_tests_exist(self) -> None:
        (self.root / "src/app.test.ts").unlink()
        self.write("tsconfig.json", json.dumps(dict(TSCONFIG, include=["${configDir}/lib"])))
        code, out = self.just("typescript::test", "--test-name-pattern=x")
        self.assertEqual(code, 1, out)
        self.assertIn("tsconfig.json finds no code", out)
        code, out = self.just("typescript::test")
        self.assertEqual(code, 0, out)
        self.assertIn("no code yet", out)

    def test_test_paths_runs_an_integration_test_outside_the_include(self) -> None:
        code, out = self.just("typescript::test-paths", "tests/integration/app.test.ts")
        self.assertEqual(code, 0, out)
        self.assertIn("✔ twice", out)


# A file with a module comment, a JSDoc comment with @returns, and a comment after each parameter, as biome
# formats it.
DOCUMENTED = ("/**\n * The arithmetic of the app.\n * @module\n */\n\n/**\n * Add two numbers.\n"
              " * @returns the sum\n */\nexport function add(\n  a: number, // the first number\n"
              "  b: number, // the second number\n): number {\n  return a + b;\n}\n")
# The same function with JSDoc tags in place of the comments after the parameters.
TAGGED = ("/**\n * The arithmetic of the app.\n * @module\n */\n\n/**\n * Add two numbers.\n"
          " * @param a the first number\n * @param b the second number\n * @returns the sum\n */\n"
          "export function add(a: number, b: number): number {\n  return a + b;\n}\n")
# A checker of nossaifd for the tests: it prints the path and the text of each page, and fails on the word WRONGWORD.
CHECKER = ("import sys\nfrom pathlib import Path\nbad = False\nfor name in sys.argv[1:]:\n"
           "    text = Path(name).read_text()\n    print('PAGE', name)\n    print(text)\n"
           "    bad = bad or 'WRONGWORD' in text\nsys.exit(1 if bad else 0)\n")
# A gate of nossaifd for the tests: base_commit gives the commit that the option names, and CI is never set.
GATE = ("import subprocess\n\ndef ci_set():\n    return False\n\ndef base_commit(root, option):\n"
        "    run = subprocess.run(['git', 'rev-parse', '--verify', '-q', option + '^{commit}'], cwd=root,\n"
        "                         capture_output=True, text=True)\n"
        "    return (run.stdout.strip(), option) if run.returncode == 0 else (None, 'no commit ' + option)\n")


@unittest.skipUnless(TOOLS, "needs just, uv and git")
class ApiTests(Project):
    """A project with the api tool, whose src/app.ts has the function add."""

    def setUp(self) -> None:
        super().setUp()
        (self.root / ".agents/just/typescript.just").write_text(MODULE + "import? 'typescript/api.just'\n")

    def prose_role(self) -> None:
        """Install the checker of nossaifd of the tests, as the prose role installs the real one."""
        self.write(".agents/skills/nossaifd/scripts/check.py", CHECKER)

    def test_an_exported_function_with_no_jsdoc_or_comments_fails_api_check(self) -> None:
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 1, out)
        self.assertIn("api-check: smalldocs api check, with the entry the 1 code files in src/", out)
        self.assertIn("app:add(a): no comment", out)
        self.assertIn("app: no module comment", out)
        self.assertIn("a JSDoc comment", out)

    def test_comments_after_the_parameters_or_jsdoc_tags_pass_api_check(self) -> None:
        for text in (DOCUMENTED, TAGGED):
            with self.subTest(text=text[:60]):
                self.write("src/app.ts", text)
                code, out = self.just("typescript::api-check")
                self.assertEqual(code, 0, out)
                # biome keeps each comment where it is.
                code, out_fmt = self.just("typescript::fmt-check")
                self.assertEqual(code, 0, out_fmt)
        # The test file is no part of the API, though it has no JSDoc.
        self.assertNotIn("app.test", out)

    def test_api_check_and_api_prose_check_take_python_3_11_when_uv_would_take_an_older_one(self) -> None:
        # smalldocs needs Python 3.11. With UV_PYTHON=3.9, as on a machine whose first Python is 3.9, uv would take
        # 3.9 and find no smalldocs, unless the step names the version.
        self.prose_role()
        self.write("src/app.ts", DOCUMENTED)
        self.commit()
        self.write("src/app.ts", DOCUMENTED.replace("the first number", "the WRONGWORD number"))
        env = dict(self.env, UV_PYTHON="3.9")
        code, out = self.just("typescript::api-check", env=env)
        self.assertEqual(code, 1, out)
        self.assertIn("the WRONGWORD number", out)
        self.assertNotIn("No solution found", out)

    def test_the_entry_is_src_index_ts_when_it_exists(self) -> None:
        self.write("src/app.ts", DOCUMENTED)
        # A file that the index does not export is no part of the API.
        self.write("src/hidden.ts", "export function hidden(a: number): number {\n  return a;\n}\n")
        self.write("src/index.ts", '/**\n * The package.\n * @module\n */\nexport * from "./app.js";\n')
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 0, out)
        self.assertIn("with the entry src/index.ts", out)
        self.write("src/index.ts", '/**\n * The package.\n * @module\n */\nexport * from "./app.js";\n'
                                   'export * from "./hidden.js";\n')
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 1, out)
        self.assertIn("hidden", out)

    def test_a_project_with_no_code_in_src_has_no_api_to_check(self) -> None:
        shutil.rmtree(self.root / "src")
        self.write("lib/x.ts", "export const x = 1;\n")
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 0, out)
        self.assertIn("so there is no API to check", out)

    def test_the_key_api_of_the_docs_config_names_the_entry(self) -> None:
        self.write("src/app.ts", DOCUMENTED)
        # The default entry, each code file in src, would take this file too.
        self.write("src/other.ts", "export function other(a: number): number {\n  return a;\n}\n")
        self.write("docs/_smalldocs.yml", "api:\n  language: typescript\n  entry: ../src/app.ts\n"
                                          "  tsconfig: ../tsconfig.json\n  out: api\n")
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 0, out)
        self.assertIn("with the TypeScript sections of the api settings of docs/_smalldocs.yml", out)
        self.assertEqual(sorted(path.name for path in (self.root / "docs").iterdir()), ["_smalldocs.yml"])
        (self.root / "docs/_smalldocs.yml").unlink()
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 1, out)
        self.assertIn("other", out)
        self.assertNotIn("docs/api", self.git("status", "--porcelain", "--untracked-files=all"))

    def checked(self, out: str) -> list:
        """The pages that the checker of the tests got, as their paths, from the output OUT."""
        return [line.split(" ", 1)[1] for line in out.splitlines()
                if line.startswith("PAGE ") and "/modules/" not in line]

    def test_a_changed_file_with_a_space_or_a_letter_outside_ascii_in_its_name_is_checked(self) -> None:
        self.prose_role()
        for name in ("src/my file.ts", "src/über.ts"):
            self.write(name, DOCUMENTED)
        self.commit()
        for name in ("src/my file.ts", "src/über.ts"):
            with self.subTest(name=name):
                self.git("checkout", "--", ".")
                self.write(name, DOCUMENTED.replace("the first number", "the WRONGWORD number"))
                code, out = self.just("typescript::api-prose-check")
                self.assertEqual(code, 1, out)
                self.assertEqual(len(self.checked(out)), 1, out)

    def test_a_root_in_the_docs_config_does_not_hide_the_changed_files(self) -> None:
        self.prose_role()
        self.write("docs/_smalldocs.yml", "api:\n  language: typescript\n  root: ..\n  entry: ../src/app.ts\n"
                                          "  tsconfig: ../tsconfig.json\n  out: api\n")
        self.commit()
        self.write("src/app.ts", DOCUMENTED.replace("the first number", "the WRONGWORD number"))
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 1, out)
        self.assertIn("the API pages app,", out)

    def test_the_page_of_an_unchanged_file_with_the_same_end_of_path_is_not_checked(self) -> None:
        self.prose_role()
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/nested/src/app.ts", DOCUMENTED.replace("the first number", "the WRONGWORD number"))
        self.commit()
        self.write("src/app.ts", DOCUMENTED.replace("Add two numbers.", "Add two numbers, a and b."))
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.checked(out)), 1, out)
        self.assertNotIn("WRONGWORD", out)

    def test_the_module_comment_of_a_changed_index_that_only_exports_again_is_checked(self) -> None:
        self.prose_role()
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/index.ts", '/**\n * The package.\n * @module\n */\nexport * from "./app.js";\n')
        self.commit()
        self.write("src/index.ts", '/**\n * The WRONGWORD package.\n * @module\n */\nexport * from "./app.js";\n')
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 1, out)
        self.assertIn("the module comment of src/index", out)
        self.assertIn("The WRONGWORD package.", out)
        self.assertNotIn("@module", out.split("api-prose-check: the API pages", 1)[1])

    def test_two_changed_files_whose_pages_have_one_flat_name_are_both_checked(self) -> None:
        self.prose_role()
        self.commit()
        self.write("src/a.b.ts", DOCUMENTED)
        self.write("src/a/b.ts", DOCUMENTED.replace("add", "plus"))
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.checked(out)), 2, out)

    def test_the_module_comment_of_a_changed_file_with_items_is_checked(self) -> None:
        self.prose_role()
        self.commit()
        self.write("src/other.ts", DOCUMENTED.replace("The arithmetic of the app.", "Other helpers that WRONGWORD add.")
                   .replace("add", "plus"))
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 1, out)
        self.assertIn("the module comment of src/other", out)

    def test_the_module_comment_of_a_changed_file_outside_the_api_is_not_checked(self) -> None:
        self.prose_role()
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/index.ts", '/**\n * The package.\n * @module\n */\nexport * from "./app.js";\n')
        self.commit()
        self.write("src/internal.ts", "/**\n * The WRONGWORD inside.\n * @module\n */\n\n/** One. */\n"
                                      "export const one = 1;\n")
        self.write("src/index.ts", '/**\n * The whole package.\n * @module\n */\nexport * from "./app.js";\n')
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 0, out)
        self.assertNotIn("WRONGWORD", out)
        # The comment of the index is checked once.
        self.assertEqual(out.count("The whole package."), 1, out)

    def test_a_plain_opening_comment_before_an_import_is_the_module_comment(self) -> None:
        self.prose_role()
        self.commit()
        text = ('/** The arithmetic of the WRONGWORD app. */\nimport { strict } from "node:assert";\n\n'
                + DOCUMENTED.split(" */\n\n", 1)[1].replace("return a + b;", "strict.ok(true);\n  return a + b;"))
        self.write("src/app.ts", text)
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 1, out)
        self.assertNotIn("no module comment", out)
        self.assertIn("The arithmetic of the WRONGWORD app.", out)
        self.assertIn("the module comment of src/app.ts", out)

    def test_an_index_tsx_is_the_entry_too(self) -> None:
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/hidden.ts", "export function hidden(a: number): number {\n  return a;\n}\n")
        self.write("src/index.tsx", '/**\n * The package.\n * @module\n */\nexport * from "./app.js";\n')
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 0, out)
        self.assertIn("with the entry src/index.tsx", out)

    def test_only_the_typescript_sections_of_the_docs_config_count(self) -> None:
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/other.ts", "export function other(a: number): number {\n  return a;\n}\n")
        python = "  - packages: [mypkg]\n    out: py\n"
        self.write("docs/_smalldocs.yml", "api:\n" + python + "  - language: typescript\n    entry: ../src/app.ts\n"
                                          "    tsconfig: ../tsconfig.json\n    out: ts\n")
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 0, out)
        self.assertIn("with the TypeScript sections of the api settings of docs/_smalldocs.yml", out)
        # A config with only a Python section is no config of the TypeScript API, so the default entry counts.
        self.write("docs/_smalldocs.yml", "api:\n" + python)
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 1, out)
        self.assertIn("with the entry the 2 code files in src/", out)
        self.assertIn("other", out)

    def test_a_flow_map_of_typescript_settings_counts_and_broken_yaml_fails_with_a_message(self) -> None:
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/other.ts", "export function other(a: number): number {\n  return a;\n}\n")
        self.write("docs/_smalldocs.yml", "api: {language: typescript, entry: ../src/app.ts, "
                                          "tsconfig: ../tsconfig.json, out: api}\n")
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 0, out)
        self.assertIn("with the TypeScript sections of the api settings of docs/_smalldocs.yml", out)
        self.write("docs/_smalldocs.yml", "api: [unclosed\n")
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 2, out)
        self.assertIn("docs/_smalldocs.yml cannot be read", out)

    def test_a_failure_of_smalldocs_or_uv_names_its_exit_code(self) -> None:
        steps = load_steps()
        os.chdir(self.root)
        self.addCleanup(os.chdir, REPO)
        real = steps.subprocess.run

        def run(args, **kwargs):
            if args[:1] == ["uv"] and "smalldocs" in args and "check" in args:
                return subprocess.CompletedProcess(args, 2)
            return real(args, **kwargs)

        steps.subprocess.run = run
        self.addCleanup(setattr, steps.subprocess, "run", real)
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(steps.api("check"), 2)
        self.assertIn("smalldocs or uv failed with the exit code 2", err.getvalue())

    def test_api_prose_check_passes_without_the_prose_role(self) -> None:
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 0, out)
        self.assertIn("no checker of nossaifd", out)

    def test_api_prose_check_checks_the_page_of_each_changed_file_outside_the_project(self) -> None:
        self.prose_role()
        self.write("src/app.ts", DOCUMENTED)
        self.write("src/other.ts", DOCUMENTED.replace("add", "other"))
        self.commit()
        self.write("src/app.ts", DOCUMENTED.replace("the first number", "the WRONGWORD number"))
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 1, out)
        self.assertIn("api-prose-check: the API pages app, the module comment of src/app.ts, of the files changed "
                      "since HEAD", out)
        self.assertIn("the WRONGWORD number", out)
        self.assertNotIn("function other", out)
        pages = [line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("PAGE ")]
        # The page of app.ts and its module comment.
        self.assertEqual(len(pages), 2, out)
        for page in pages:
            self.assertFalse(Path(page).resolve().is_relative_to(self.root), pages)
        self.assertIn("fix each hard problem in the JSDoc comment", out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), " M src/app.ts\n")

    def test_api_prose_check_reads_the_key_api_of_the_docs_config_and_writes_nothing_there(self) -> None:
        self.prose_role()
        self.write("docs/_smalldocs.yml", "api:\n  - language: typescript\n    entry: ../src/app.ts\n"
                                          "    tsconfig: ../tsconfig.json\n    out: reference\n"
                                          "    source: https://example.com/x\n")
        self.commit()
        self.write("src/app.ts", DOCUMENTED)
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 0, out)
        self.assertIn("the API pages app, the module comment of src/app.ts, of the files changed since HEAD", out)
        self.assertEqual(sorted(path.name for path in (self.root / "docs").iterdir()), ["_smalldocs.yml"])

    def test_api_prose_check_with_no_changed_code_passes(self) -> None:
        self.prose_role()
        self.commit()
        code, out = self.just("typescript::api-prose-check")
        self.assertEqual(code, 0, out)
        self.assertIn("no code changed since HEAD", out)

    def test_api_check_runs_api_prose_check_once_in_a_run(self) -> None:
        self.prose_role()
        self.commit()
        self.write("src/app.ts", DOCUMENTED)
        env = dict(self.env, JLOG_RUN="run-1")
        code, out = self.just("typescript::api-check", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("api-prose-check: the API pages app", out)
        code, out = self.just("typescript::api-prose-check", env=env)
        self.assertEqual(code, 0, out)
        self.assertIn("api-prose-check: it passed before in this run, run-1, on this tree", out)
        # Another base is another run.
        self.write(".agents/skills/nossaifd/scripts/prose_gate.py", GATE)
        code, out = self.just("typescript::api-prose-check", "--base", "HEAD", env=env)
        self.assertEqual(code, 0, out)
        self.assertNotIn("it passed before", out)

    def test_api_prose_check_with_a_base_takes_the_changes_since_the_base_from_the_gate(self) -> None:
        self.prose_role()
        self.write(".agents/skills/nossaifd/scripts/prose_gate.py", GATE)
        self.commit()
        self.write("src/app.ts", DOCUMENTED)
        self.commit()
        # The tree is clean, so only a base shows the change of the last commit.
        code, out = self.just("typescript::api-prose-check")
        self.assertIn("no code changed since HEAD", out)
        code, out = self.just("typescript::api-prose-check", "--base", "HEAD~1")
        self.assertEqual(code, 0, out)
        self.assertIn("the API pages app, the module comment of src/app.ts, of the files changed since HEAD~1", out)
        code, out = self.just("typescript::api-prose-check", "--base", "nothing")
        self.assertEqual(code, 2, out)
        self.assertIn("no commit nothing", out)
        self.assertFalse(list((self.root / ".agents/skills").rglob("__pycache__")))

    def test_a_base_without_the_gate_of_nossaifd_fails(self) -> None:
        self.prose_role()
        code, out = self.just("typescript::api-prose-check", "--base", "main")
        self.assertEqual(code, 2, out)
        self.assertIn("needs base_commit", out)


class ModuleCommentTests(unittest.TestCase):
    def test_the_module_comment_follows_the_rule_of_smalldocs(self) -> None:
        steps = load_steps()
        cases = {
            '/** M. */\nimport x from "y";\n': "M.",
            "/** D. */\nexport function f() {}\n": None,
            '/** The mod. */\nexport * as ns from "./a.js";\n': "The mod.",
            '/** The mod. */\nexport type * from "./a.js";\n': "The mod.",
            '/**/\n/** The mod. */\nimport x from "y";\n': "The mod.",
            "/** The mod. */\nexport type { A };\n": None,
            "/**\n * T.\n * @module\n */\nexport const a = 1;\n": "T.",
            "/** A. */\n/** B. */\nexport const b = 1;\n": "A.",
            '#!/usr/bin/env node\n/* MIT */\n// x\n/** L. */\n"use client";\n': "L.",
        }
        with tempfile.TemporaryDirectory() as folder:
            for text, want in cases.items():
                with self.subTest(text=text):
                    path = Path(folder) / "f.ts"
                    path.write_text(text)
                    self.assertEqual(steps.module_comment(path), want)


class ProfileTests(unittest.TestCase):
    def test_the_code_and_test_globs_of_the_steps_are_those_of_the_profile(self) -> None:
        steps = load_steps()
        self.assertEqual(list(steps.CODE), PROFILE["code"])
        self.assertEqual(list(steps.TESTS), PROFILE["tests"])

    def test_each_package_of_docstring_check_that_typescript_eslint_releases_is_pinned(self) -> None:
        # eslint-plugin-jsdoc takes the utils of typescript-eslint as ^8.72.0. A release whose own packages npm cannot
        # find yet stopped the step, so the utils are pinned to the version of the parser.
        steps = load_steps()
        pins = dict(package.rsplit("@", 1) for package in steps.ESLINT)
        self.assertEqual(pins["@typescript-eslint/utils"], pins["@typescript-eslint/parser"])

    def test_each_step_is_in_the_verify_of_its_tool(self) -> None:
        tools = PROFILE["tools"]
        self.assertEqual(tools["lint"]["verify"], ["fmt-check", "lint"])
        self.assertEqual(tools["typecheck"]["verify"], ["typecheck"])
        self.assertEqual(tools["test"]["verify"], ["test", "coverage-check"])
        self.assertEqual(tools["docstring"]["verify"], ["docstring-check"])
        self.assertEqual(tools["integration"]["verify"], ["integration"])
        self.assertEqual(tools["integration"]["recipes"], "integration.just")
        self.assertEqual(tools["integration"]["packages"], tools["test"]["packages"])
        self.assertEqual(tools["integration"]["lines"], tools["test"]["lines"])
        self.assertIn("c8@12", tools["test"]["packages"])
        self.assertIn(".jnprofile-typescript/", tools["test"]["lines"][".gitignore"])
        self.assertEqual(PROFILE["default_tools"], ["lint", "typecheck", "test", "docstring", "api"])
        self.assertEqual(tools["api"]["verify"], ["api-check"])
        self.assertEqual(tools["api"]["recipes"], "api.just")
        self.assertEqual(tools["api"]["packages"], [])

    def test_the_package_installs_the_recipes_and_the_language_layer(self) -> None:
        package = json.loads((REPO / "skill-package.json").read_text())
        self.assertEqual(package["install_extras"]["files"], [".agents/just/typescript", ".agents/targets/typescript"])
        for name in ("review", "test-review", "docs", "prose"):
            self.assertTrue((REPO / f".agents/targets/typescript/{name}.md").is_file(), name)

    @unittest.skipUnless(shutil.which("just"), "needs just")
    def test_no_step_is_a_shebang_recipe_or_has_a_dash_line_or_no_cd(self) -> None:
        steps = ("fmt-check", "lint", "typecheck", "test", "coverage-check", "integration", "docstring-check",
                 "docs-check", "prose-check", "diff-check")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(FOLDER, root / "typescript")
            (root / "typescript.just").write_text(MODULE.replace("import? ", "import ") +
                                                  "import 'typescript/typecheck.just'\n"
                                                  "import 'typescript/integration.just'\n"
                                                  "import 'typescript/api.just'\n")
            dump = json.loads(subprocess.run(["just", "--justfile", str(root / "typescript.just"), "--dump",
                                              "--dump-format", "json"], capture_output=True, text=True,
                                             check=True).stdout)
        recipes = dump["recipes"]
        found = [name for name in steps if name in recipes]
        self.assertEqual(found, ["fmt-check", "lint", "typecheck", "test", "coverage-check", "integration",
                                 "docstring-check"])
        todo = list(found)
        while todo:
            recipe = recipes[todo.pop()]
            with self.subTest(recipe=recipe["name"]):
                self.assertFalse(recipe["shebang"])
                self.assertNotIn("no-cd", recipe["attributes"])
                self.assertFalse(any(isinstance(a, dict) and "working-directory" in a for a in recipe["attributes"]))
                for line in recipe["body"]:
                    self.assertFalse(isinstance(line[0], str) and line[0].lstrip("@").startswith("-"), line)
            todo += [dep["recipe"] for dep in recipe["dependencies"]]


RULE = FOLDER / "api_rule.py"
# The script that loads the rule as the gate does: from a copy outside the project, in a Python of its own, with the
# top of the repository as the current folder. It prints the paths of standard input that is_api accepts.
LOADER = ("import importlib.util, sys\n"
          "spec = importlib.util.spec_from_file_location('api_rule', sys.argv[1])\n"
          "module = importlib.util.module_from_spec(spec)\n"
          "spec.loader.exec_module(module)\n"
          "for path in sys.stdin.read().split():\n"
          "    print(path, module.is_api(path))\n")
# The script that prints the key api of the docs config, as the rule reads it, as JSON.
PARSE = ("import importlib.util, json, sys\n"
         "spec = importlib.util.spec_from_file_location('api_rule', sys.argv[1])\n"
         "module = importlib.util.module_from_spec(spec)\n"
         "spec.loader.exec_module(module)\n"
         "print(json.dumps(module._api_settings()))\n")
# The same, as PyYAML reads it.
YAML_API = ("import json, yaml\n"
            "print(json.dumps((yaml.safe_load(open('docs/_smalldocs.yml')) or {}).get('api')))\n")
ON = {"tools": ["typescript:lint", "typescript:api"], "choices": {"docs": True}}


class CleanEnvTests(unittest.TestCase):
    def test_the_variables_of_ci_and_git_do_not_reach_a_project(self) -> None:
        # GitHub Actions sets CI and GITHUB_*, which would give api-prose-check a base. A test that needs one sets it.
        environ = {"CI": "true", "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/x", "GIT_DIR": "/x",
                   "JLOG_RUN": "r", "PATH": "/bin", "HOME": "/h"}
        self.assertEqual(clean_env(environ), {"PATH": "/bin", "HOME": "/h"})


class ApiRuleTests(unittest.TestCase):
    """api_rule.py, as the commit gate loads it, in a project in a temporary folder."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(os.path.realpath(temp.name)) / "app"
        self.root.mkdir()
        # The gate loads the rule of the parent commit, so the copy is outside the project.
        self.rule = Path(temp.name) / "rule.py"
        shutil.copy(RULE, self.rule)
        self.stack(ON)
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", "-c",
                               "commit.gpgsign=false", *args], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout

    def commit(self) -> None:
        """Commit the project, so that it is the parent commit of the next change."""
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "c")

    def write(self, name: str, text: str = "export const x = 1;\n") -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def stack(self, record) -> None:
        self.write(".agents/stack.json", json.dumps(record))

    def accepted(self, *paths: str, python: list = None) -> set:
        """The PATHS that is_api accepts, from a run of the rule as the gate runs it."""
        before = sorted(str(path) for path in self.root.rglob("*"))
        run = subprocess.run([*(python or [sys.executable]), "-I", "-B", "-c", LOADER, str(self.rule)],
                             input="\n".join(paths), cwd=self.root, capture_output=True, text=True, check=True)
        self.assertEqual(sorted(str(path) for path in self.root.rglob("*")), before, "the rule wrote a file")
        answers = dict(line.rsplit(" ", 1) for line in run.stdout.splitlines())
        self.assertEqual(set(answers), set(paths), run.stderr)
        return {path for path, answer in answers.items() if answer == "True"}

    def test_the_index_and_the_files_that_it_reaches_are_the_api(self) -> None:
        self.write("src/index.ts", '/** The package. */\nexport * from "./app.js";\nexport { b } from "./lib";\n')
        self.write("src/app.ts", 'import { u } from "./util/helper.js";\nimport type { T } from "./types.js";\n'
                                 'export const a = u;\n')
        self.write("src/util/helper.ts")
        self.write("src/types.ts", "export type T = 1;\n")
        self.write("src/lib/index.ts", "export const b = 1;\n")
        self.write("src/internal.ts")
        self.write("src/app.test.ts", 'import { a } from "./app.js";\n')
        self.write("src/shapes.d.ts", "export type S = 1;\n")
        self.write("src/gen/out.ts")
        self.write("src/app.ts", 'import { u } from "./util/helper.js";\nimport "./gen/out.js";\nexport const a = u;\n'
                                 'import type { T } from "./types.js";\n')
        self.write(".agents/generated.txt", "# generated\nsrc/gen\n")
        self.commit()
        paths = ("src/index.ts", "src/app.ts", "src/util/helper.ts", "src/types.ts", "src/lib/index.ts",
                 "src/internal.ts", "src/app.test.ts", "src/shapes.d.ts", "src/gen/out.ts", "README.md",
                 ".agents/just/x.ts", "./src/app.ts")
        self.assertEqual(self.accepted(*paths), {"src/index.ts", "src/app.ts", "src/util/helper.ts", "src/types.ts",
                                                 "src/lib/index.ts", "./src/app.ts"})

    def test_an_index_tsx_is_the_entry_and_a_jsx_import_names_a_tsx_file(self) -> None:
        self.write("src/index.tsx", 'export * from "./Button.jsx";\n')
        self.write("src/Button.tsx")
        self.write("src/other.ts")
        self.assertEqual(self.accepted("src/index.tsx", "src/Button.tsx", "src/other.ts"),
                         {"src/index.tsx", "src/Button.tsx"})

    def test_without_an_index_each_code_file_in_src_is_the_api(self) -> None:
        self.write("src/a.ts")
        self.write("src/deep/b.mts")
        self.write("lib/c.ts")
        # A file that is gone, as a deleted path that the gate gets, is in src all the same.
        self.assertEqual(self.accepted("src/a.ts", "src/deep/b.mts", "src/gone.ts", "lib/c.ts", "src/a.test.ts"),
                         {"src/a.ts", "src/deep/b.mts", "src/gone.ts"})

    def test_the_typescript_sections_of_the_docs_config_name_the_entry(self) -> None:
        self.write("src/index.ts", 'export * from "./a.js";\n')
        self.write("src/a.ts")
        self.write("lib/main.ts", 'export * from "./part.js";\n')
        self.write("lib/part.ts")
        self.write("tools/x.ts")
        configs = (
            "api:\n  language: typescript\n  entry: ../lib/main.ts\n  out: api\n",
            "api: {language: typescript, entry: '../lib/main.ts', out: api}\n",
            "api:\n  - packages: [mypkg]\n    out: py\n  - language: \"typescript\"  # the TypeScript API\n"
            "    entry:\n      - ../lib/main.ts\n    out: ts\n",
            "project:\n  type: website\napi:\n  - {language: typescript, entry: [../lib/main.ts]}\n",
        )
        for config in configs:
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                self.assertEqual(self.accepted("lib/main.ts", "lib/part.ts", "src/a.ts", "tools/x.ts"),
                                 {"lib/main.ts", "lib/part.ts"})
        # An entry that is a folder holds the API.
        self.write("docs/_smalldocs.yml", "api:\n  language: typescript\n  entry: ../tools\n")
        self.assertEqual(self.accepted("tools/x.ts", "lib/main.ts"), {"tools/x.ts"})

    def test_a_config_with_no_typescript_section_or_no_api_key_takes_the_default(self) -> None:
        self.write("src/a.ts")
        for config in ("api:\n  packages: [mypkg]\n", "project:\n  type: website\n"):
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                self.assertEqual(self.accepted("src/a.ts", "lib/b.ts"), {"src/a.ts"})

    def test_a_broken_docs_config_makes_each_code_file_count(self) -> None:
        self.write("src/a.ts")
        self.write("lib/b.ts")
        self.write("src/gen.ts")
        self.write(".agents/generated.txt", "src/gen.ts\n")
        self.commit()
        for config in ("api: [unclosed\n", "api:\n\tlanguage: typescript\n", "api:\n  language: typescript\n x: 1\n"):
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                self.assertEqual(self.accepted("src/a.ts", "lib/b.ts", "src/a.test.ts", "src/s.d.ts", "src/gen.ts",
                                               ".agents/x.ts", "node_modules/p/i.ts", "README.md"),
                                 {"src/a.ts", "lib/b.ts"})

    def test_a_broken_stack_record_gives_false(self) -> None:
        self.write("src/a.ts")
        for record in ("{not json", "[1, 2]"):
            with self.subTest(record=record):
                self.write("docs/_smalldocs.yml", "project:\n  type: website\n")
                self.write(".agents/stack.json", record)
                self.assertEqual(self.accepted("src/a.ts"), set())

    def test_without_the_api_tool_or_the_docs_role_no_path_is_the_api(self) -> None:
        self.write("src/a.ts")
        for record in ({"tools": ["typescript:lint"], "choices": {"docs": True}},
                       {"tools": ["typescript:api"], "choices": {"docs": False}}, {}):
            with self.subTest(record=record):
                self.stack(record)
                self.assertEqual(self.accepted("src/a.ts"), set())
        (self.root / ".agents/stack.json").unlink()
        self.assertEqual(self.accepted("src/a.ts"), set())

    def test_the_yaml_forms_of_pyyaml_name_the_entry(self) -> None:
        self.write("src/index.ts", 'export * from "./a.js";\n')
        self.write("src/a.ts")
        self.write("lib/main.ts", 'export * from "./part.js";\n')
        self.write("lib/part.ts")
        configs = (
            "api: # the API\n  language: typescript\n  entry: ../lib/main.ts\n",
            "api:\n  language: typescript\n  entry: # the entries\n    - ../lib/main.ts\n",
            "api:\n  language: typescript\n  entry:\n  - ../lib/main.ts\n  out: api\n",
            "api:\n- language: typescript\n  entry:\n  - ../lib/main.ts\n",
            "api:\n  language: typescript\n  entry: [\n    ../lib/main.ts,\n    ../lib/part.ts\n  ]\n",
            "api: {\n  language: typescript,\n  entry: ../lib/main.ts\n}\n",
            "api:\n  language: typescript\n  entry: [../lib/main.ts]  # don't follow src\n",
            "api:\n  -   language: typescript\n      entry: ../lib/main.ts\n",
            "---\napi:\n  language: 'typescript'\n  entry: \"../lib/main.ts\"\n...\n",
            "api:\n  language: typescript\n  entry: ../src/a.ts\n"
            "api:\n  language: typescript\n  entry: ../lib/main.ts\n",
            "api:\r\n  language: typescript\r\n  entry: ../lib/main.ts\r\n",
        )
        for config in configs:
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                self.assertEqual(self.accepted("lib/main.ts", "lib/part.ts", "src/a.ts"),
                                 {"lib/main.ts", "lib/part.ts"})

    def test_the_parser_reads_the_api_key_as_pyyaml_reads_it(self) -> None:
        python = ["uv", "run", "--no-project", "--quiet", "--with", "pyyaml", "python"]
        if not shutil.which("uv"):
            self.skipTest("no uv to run PyYAML")
        configs = (
            "api:\n  language: typescript\n  entry: ../src/a.ts\n  out: api\n",
            "api: # c\n  - packages: [a, 'b c']\n    out: py\n  - language: \"typescript\"  # c\n    entry:\n"
            "    - ../a.ts\n    - '../b # c.ts'\n",
            "project:\n  type: website\napi:\n  - {language: typescript, entry: [../a.ts, \"../b.ts\"], out: x}\n"
            "nav:\n  - a.md\n",
            "api: {language: typescript,\n  entry: [../a.ts,\n    ../b.ts]}\n",
            "api:\n  -   language: typescript\n      entry: ../a.ts\n  - language: python\n",
            "api: ~\n", "api:\n", "api: null\n", "project: {a: 1}\n",
            "api:\n  entry: ../it's.ts\n  language: typescript\n",
        )
        for config in configs:
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                ours = subprocess.run([sys.executable, "-I", "-B", "-c", PARSE, str(self.rule)], cwd=self.root,
                                      capture_output=True, text=True, check=True).stdout
                theirs = subprocess.run([*python, "-I", "-c", YAML_API], cwd=self.root, capture_output=True, text=True,
                                        check=True).stdout
                self.assertEqual(json.loads(ours), json.loads(theirs))

    def test_yaml_that_the_rule_does_not_read_makes_each_code_file_count(self) -> None:
        self.write("src/a.ts")
        self.write("lib/b.ts")
        for config in ("api: &ts\n  language: typescript\n", "api: !!map\n  language: typescript\n",
                       "api:\n  entry: |\n    ../src/a.ts\n", "api:\n  language: typescript\n  entry: '../a.ts\n"):
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                self.assertEqual(self.accepted("src/a.ts", "lib/b.ts", "src/a.test.ts"), {"src/a.ts", "lib/b.ts"})
        # Without the tool api, the rule stays off.
        self.stack({"tools": ["typescript:lint"], "choices": {"docs": True}})
        self.assertEqual(self.accepted("src/a.ts"), set())

    def test_a_folder_of_the_config_counts_its_test_and_declaration_files(self) -> None:
        # A real run of smalldocs 0.5.12 with entry: ../src put the items of src/app.test.ts and src/shapes.d.ts on
        # the API pages, because TypeDoc expands the folder. The default entry src leaves them out, as api-check does.
        for name in ("src/a.ts", "src/a.test.ts", "src/s.d.ts", "src/gen.ts", "lib/c.test.ts"):
            self.write(name)
        self.write(".agents/generated.txt", "src/gen.ts\n")
        self.commit()
        self.write("docs/_smalldocs.yml", "api:\n  language: typescript\n  entry: ../src\n")
        self.assertEqual(self.accepted("src/a.ts", "src/a.test.ts", "src/s.d.ts", "src/gen.ts", "lib/c.test.ts"),
                         {"src/a.ts", "src/a.test.ts", "src/s.d.ts"})
        # A test file that the config names as an entry counts too.
        self.write("docs/_smalldocs.yml", "api:\n  language: typescript\n  entry: [../src, ../lib/c.test.ts]\n")
        self.assertEqual(self.accepted("lib/c.test.ts"), {"lib/c.test.ts"})

    def test_the_default_folder_leaves_out_test_and_declaration_files(self) -> None:
        for name in ("src/a.ts", "src/a.test.ts", "src/s.d.ts"):
            self.write(name)
        self.assertEqual(self.accepted("src/a.ts", "src/a.test.ts", "src/s.d.ts"), {"src/a.ts"})

    def test_a_null_api_key_takes_the_default(self) -> None:
        self.write("src/a.ts")
        for config in ("api:\n", "api: ~\n", "api: null\n", "api:\n  language: typescript\n"):
            with self.subTest(config=config):
                self.write("docs/_smalldocs.yml", config)
                self.assertEqual(self.accepted("src/a.ts", "lib/b.ts"), {"src/a.ts"})

    def test_the_generated_list_of_the_parent_counts_as_git_reads_it(self) -> None:
        self.write("src/index.ts", 'export * from "./lib/a.js";\nexport * from "./generated/b.js";\n'
                                   'export * from "./x.js";\n')
        self.write("src/lib/a.ts")
        self.write("src/generated/b.ts")
        self.write("src/x.ts")
        # src/gen* names no folder, and src/**.d is a plain * between two slashes, which names no file here.
        self.write(".agents/generated.txt", "src/x.ts\nsrc/gen*\nsrc/**.d\n")
        self.commit()
        self.assertEqual(self.accepted("src/index.ts", "src/lib/a.ts", "src/generated/b.ts", "src/x.ts"),
                         {"src/index.ts", "src/lib/a.ts", "src/generated/b.ts"})
        # A change of the list in the commit itself does not count: the gate reads the list of the parent.
        self.write(".agents/generated.txt", "src\n")
        self.assertEqual(self.accepted("src/lib/a.ts", "src/x.ts"), {"src/lib/a.ts"})

    def test_a_generated_index_is_no_entry(self) -> None:
        self.write("src/index.ts")
        self.write("src/b.ts")
        self.write(".agents/generated.txt", "src/index.ts\n")
        self.commit()
        self.assertEqual(self.accepted("src/index.ts", "src/b.ts"), {"src/b.ts"})

    def test_require_and_odd_paths(self) -> None:
        self.write("src/index.ts", 'import y = require("./y");\nexport import z = require("./z.js");\n'
                                   'export {\n  a,\n} from "./a.js";\n')
        self.write("src/y.ts")
        self.write("src/z.ts")
        self.write("src/a.ts")
        self.assertEqual(self.accepted("src/y.ts", "src/z.ts", "src/a.ts", "src//a.ts", "src/./y.ts", "src\\z.ts",
                                       "../app/src/a.ts"),
                         {"src/y.ts", "src/z.ts", "src/a.ts", "src//a.ts", "src/./y.ts", "src\\z.ts"})

    def test_the_rule_is_python_3_9(self) -> None:
        ast.parse(RULE.read_text(), feature_version=(3, 9))
        python = ["uv", "run", "--no-project", "--quiet", "--python", "3.9", "python"]
        if not (shutil.which("uv") and subprocess.run([*python, "-c", "pass"], capture_output=True).returncode == 0):
            if not shutil.which("python3.9"):
                self.skipTest("no Python 3.9: uv cannot fetch it and python3.9 is not on the PATH")
            python = [shutil.which("python3.9")]
        self.write("src/a.ts")
        self.write("docs/_smalldocs.yml", "api:  # the API\n  - {language: typescript, entry: [\n      ../src/a.ts,\n"
                                          "    ]}\n")
        self.assertEqual(self.accepted("src/a.ts", "lib/b.ts", python=python), {"src/a.ts"})

    def test_the_package_installs_the_rule_with_the_recipes(self) -> None:
        # The installer keeps .agents/just/ for itself, so a tool of profile.json cannot own a file there. The rule
        # comes with the folder of the recipes, which skill-package.json installs.
        package = json.loads((REPO / "skill-package.json").read_text())
        self.assertIn(".agents/just/typescript", package["install_extras"]["files"])
        self.assertTrue(RULE.is_file())


class VersionTests(unittest.TestCase):
    """The recipe typescript::version, which prints the version of package.json for the release tag."""

    def run_on(self, text=None, raw=None, folder=False):
        """The exit code, the output and the errors of version on a package.json with TEXT, or the bytes RAW, or
        that is a folder. With none of them, there is no package.json."""
        steps = load_steps()
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "package.json"
            if folder:
                manifest.mkdir()
            elif raw is not None:
                manifest.write_bytes(raw)
            elif text is not None:
                manifest.write_text(text)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = steps.version(manifest)
            made = text is not None or raw is not None or folder
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ["package.json"] if made else [],
                             "version wrote a file")
            return code, out.getvalue(), err.getvalue()

    def test_a_version_prints_on_one_line(self) -> None:
        self.assertEqual(self.run_on('{"name": "a", "version": "1.2.3"}'), (0, "1.2.3\n", ""))

    def test_a_prerelease_prints_as_it_is(self) -> None:
        for version in ("1.2.0-beta.1", "2.0.0-rc.1+build.5", "0.0.0"):
            self.assertEqual(self.run_on(json.dumps({"version": version})), (0, version + "\n", ""), version)

    def test_a_byte_order_mark_is_no_part_of_the_file(self) -> None:
        self.assertEqual(self.run_on(raw=b'\xef\xbb\xbf{"version": "1.0.0"}'), (0, "1.0.0\n", ""))

    def test_no_manifest_or_no_version_prints_nothing(self) -> None:
        self.assertEqual(self.run_on(), (0, "", ""))
        self.assertEqual(self.run_on('{"name": "a"}'), (0, "", ""))
        self.assertEqual(self.run_on('{"name": "a", "version": null}'), (0, "", ""))
        # A version in another object, such as that of a dependency, is not the version of the project.
        self.assertEqual(self.run_on('{"dependencies": {"version": "1.0.0"}}'), (0, "", ""))

    def test_an_unreadable_file_exits_2_with_a_message(self) -> None:
        cases = [dict(raw=b'{"version": '), dict(raw=b"\xff\xfe"), dict(raw=b""), dict(raw=b"[1]"),
                 dict(raw=b'"1.0.0"'), dict(raw=b'{"version": 5}'), dict(raw=b'{"version": ""}'),
                 dict(raw=b'{"version": "1.0.0\\n2.0.0"}'), dict(raw=b'{"version": " 1.0.0"}'),
                 dict(raw=b"[" * 100000 + b"]" * 100000), dict(folder=True),
                 dict(raw='{"version": "1.0.0-\u03b2eta"}'.encode()), dict(raw='{"version": "1.0.0\u00a0"}'.encode()),
                 dict(raw=b'{"version": "1.0.0\\u0007"}'), dict(raw=b'{"version": "\\ud800"}')]
        for case in cases:
            code, out, err = self.run_on(**case)
            self.assertEqual((code, out), (2, ""), case if "folder" in case else case["raw"][:40])
            self.assertTrue(err.startswith("version: "), err)

    def test_a_link_to_no_file_exits_2(self) -> None:
        # A release would read a broken link as no version, so the recipe says that it cannot read the file.
        steps = load_steps()
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "package.json"
            manifest.symlink_to(Path(temp) / "nowhere.json")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = steps.version(manifest)
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertTrue(err.getvalue().startswith("version: cannot read"), err.getvalue())

    def test_a_link_to_a_file_prints_its_version(self) -> None:
        steps = load_steps()
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "real.json").write_text('{"version": "4.0.0"}')
            (Path(temp) / "package.json").symlink_to(Path(temp) / "real.json")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(steps.version(Path(temp) / "package.json"), 0)
        self.assertEqual(out.getvalue(), "4.0.0\n")

    def test_the_recipe_has_one_line_of_comment_for_just_list(self) -> None:
        # just --list shows only the last line of the comment above a recipe, so the whole comment is one line.
        lines = (FOLDER / "base.just").read_text().splitlines()
        at = lines.index("version:")
        self.assertTrue(lines[at - 1].startswith("# Print the version of package.json"), lines[at - 1])
        self.assertFalse(lines[at - 2].startswith("#"), lines[at - 2])

    def test_the_recipe_prints_the_version_through_just(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "package.json").write_text('{"version": "3.1.4-alpha.2"}\n')
            done = subprocess.run(["just", "--justfile", str(FOLDER / "base.just"), "--working-directory", temp,
                                   "version"], capture_output=True, text=True, env=clean_env(os.environ), check=False)
            self.assertEqual((done.returncode, done.stdout), (0, "3.1.4-alpha.2\n"), done.stderr)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ["package.json"])
            (Path(temp) / "package.json").write_text("{")
            done = subprocess.run(["just", "--justfile", str(FOLDER / "base.just"), "--working-directory", temp,
                                   "version"], capture_output=True, text=True, env=clean_env(os.environ), check=False)
            self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr)
            self.assertIn("version: cannot read package.json", done.stderr)

    def test_the_recipe_reads_with_python_3_11_or_later_and_no_node(self) -> None:
        text = (FOLDER / "base.just").read_text()
        recipe = text.split("\nversion:\n", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(recipe.strip(), "{{python_run}} {{ts_steps}} version")
        self.assertIn("python_run := \"uv run --no-project --quiet --python '>=3.11' python\"", text)
        # The function reads with json only: it starts no process.
        steps = load_steps()
        with unittest.mock.patch.object(subprocess, "run", side_effect=AssertionError("a process")), \
                tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "package.json").write_text('{"version": "1.0.0"}')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(steps.version(Path(temp) / "package.json"), 0)

    def test_version_is_no_step_of_just_check(self) -> None:
        for tool in PROFILE["tools"].values():
            self.assertNotIn("version", tool.get("verify", []))


if __name__ == "__main__":
    unittest.main()
