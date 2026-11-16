"""Run the steps fmt-check, test, coverage-check and docstring-check, and test-paths, with real just, uv, git and node.

The projects of the tests share one node_modules and one cache of npm, which the first test installs, so that each
project needs no install of its own. Each project links them in.
"""

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
TEST = ('import { test } from "node:test";\nimport assert from "node:assert/strict";\nimport { add } from "./app.js";\n\n'
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
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "JLOG_RUN"}
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
        for env, change in ((dict(self.env, JLOG_RUN="run-2"), False), (env, True)):
            if change:
                self.write("src/app.ts", CODE + ONLY_INTEGRATION + "\n")
            code, out = self.just("typescript::integration", env=env)
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
        self.assertIn("with the api settings of docs/_smalldocs.yml", out)
        self.assertEqual(sorted(path.name for path in (self.root / "docs").iterdir()), ["_smalldocs.yml"])
        (self.root / "docs/_smalldocs.yml").unlink()
        code, out = self.just("typescript::api-check")
        self.assertEqual(code, 1, out)
        self.assertIn("other", out)
        self.assertNotIn("docs/api", self.git("status", "--porcelain", "--untracked-files=all"))

    def checked(self, out: str) -> list:
        """The pages that the checker of the tests got, as their paths, from the output OUT."""
        return [line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("PAGE ")]

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
        self.assertIn("api-prose-check: the API pages app, of the files changed since HEAD", out)
        self.assertIn("the WRONGWORD number", out)
        self.assertNotIn("function other", out)
        pages = [line.split()[1] for line in out.splitlines() if line.startswith("PAGE ")]
        self.assertEqual(len(pages), 1, out)
        self.assertFalse(Path(pages[0]).resolve().is_relative_to(self.root), pages)
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
        self.assertIn("the API pages app, of the files changed since HEAD", out)
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
        self.assertIn("the API pages app, of the files changed since HEAD~1", out)
        code, out = self.just("typescript::api-prose-check", "--base", "nothing")
        self.assertEqual(code, 2, out)
        self.assertIn("no commit nothing", out)
        self.assertFalse(list((self.root / ".agents/skills").rglob("__pycache__")))

    def test_a_base_without_the_gate_of_nossaifd_fails(self) -> None:
        self.prose_role()
        code, out = self.just("typescript::api-prose-check", "--base", "main")
        self.assertEqual(code, 2, out)
        self.assertIn("needs base_commit", out)


class ProfileTests(unittest.TestCase):
    def test_the_code_and_test_globs_of_the_steps_are_those_of_the_profile(self) -> None:
        steps = load_steps()
        self.assertEqual(list(steps.CODE), PROFILE["code"])
        self.assertEqual(list(steps.TESTS), PROFILE["tests"])

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


if __name__ == "__main__":
    unittest.main()
