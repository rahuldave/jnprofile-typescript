"""The live lab of api_rule.py: install the profile into a new project with the installer of jnterfaces, commit, change
only a JSDoc comment, and ask is_api of the parent commit about the file, as the commit gate does.

just test runs it with JNPROFILE_LIVE=1, and then a missing installer fails the lab. JNTERFACES_INSTALLER names the
installer. By default it is jnterfaces/scripts/install_stack.py in SKILL_PACKAGES_DIR, or in ~/Projects. The
installer takes the other packages from SKILL_PACKAGES_DIR, or from the folder that holds its clone. It needs uv,
git, jlog and node.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent
PACKAGES = Path(os.environ.get("SKILL_PACKAGES_DIR") or Path.home() / "Projects")
INSTALLER = Path(os.environ.get("JNTERFACES_INSTALLER") or PACKAGES / "jnterfaces/scripts/install_stack.py")
LIVE = os.environ.get("JNPROFILE_LIVE") == "1"
# The variables of a session of an agent, which the installer reads, and which a lab leaves out.
AGENT = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_PROJECT_DIR")
CODE = ('/** The arithmetic of the app. */\n\n/** Add A and B. */\n'
        'export function add(a: number, b: number): number {\n  return a + b;\n}\n')
TEST = ('import assert from "node:assert/strict";\nimport { test } from "node:test";\nimport { add } from "./app.js";\n'
        '\ntest("add", () => {\n  assert.equal(add(1, 2), 3);\n});\n')
# The gate loads the rule from the parent commit and runs it with python -I -B, in the top of the repository.
ASK = ("import importlib.util, json, subprocess, sys, tempfile, os\n"
       "text = subprocess.run(['git', 'show', 'HEAD:.agents/just/typescript/api_rule.py'], capture_output=True,\n"
       "                      text=True, check=True).stdout\n"
       "folder = tempfile.mkdtemp()\npath = os.path.join(folder, 'api_rule.py')\nopen(path, 'w').write(text)\n"
       "spec = importlib.util.spec_from_file_location('api_rule', path)\n"
       "rule = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(rule)\n"
       "print(json.dumps({name: rule.is_api(name) for name in sys.argv[1:]}))\n")


@unittest.skipUnless(LIVE, "the live lab runs with JNPROFILE_LIVE=1, as just test sets it")
class LiveApiRuleTests(unittest.TestCase):
    def run_in(self, root: Path, *command: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if k not in AGENT and k != "CI" and not k.startswith(("GIT_", "GITHUB_"))}
        # The installer runs from a clone that the lab does not own, so Python writes no bytecode into it.
        env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(command, cwd=root, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                              check=False)

    def test_a_change_of_only_a_jsdoc_comment_is_a_change_of_the_api(self) -> None:
        for program in ("uv", "git", "jlog", "node"):
            self.assertTrue(shutil.which(program), f"the live lab needs {program} on the PATH")
        self.assertTrue(INSTALLER.is_file(), f"no installer of jnterfaces at {INSTALLER}: set JNTERFACES_INSTALLER "
                                             "or SKILL_PACKAGES_DIR")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / "src/index.ts").write_text('/** The app. */\nexport * from "./app.js";\n')
            (root / "src/app.ts").write_text(CODE)
            (root / "src/help.ts").write_text("/** The help. */\n\n/** One. */\nexport const one = 1;\n")
            (root / "src/app.test.ts").write_text(TEST)
            self.run_in(root, "git", "init", "-q", "-b", "main")
            installed = self.run_in(root, "uv", "run", "--quiet", "--script", str(INSTALLER), "--target", ".",
                                    # The lab needs no tasker, whose package needs gest, which CI does not have.
                                    "--defaults", "--without", "tasker", "--profile", "typescript", "--clone",
                                    f"jnprofile-typescript={REPO}", "--answer", "integration=check", "--answer",
                                    "docs-publish=no", "docs")
            self.assertEqual(installed.returncode, 0, installed.stdout[-4000:] + installed.stderr[-4000:])
            record = json.loads((root / ".agents/stack.json").read_text())
            self.assertIn("typescript:api", record["tools"])
            self.assertTrue(record["choices"]["docs"])
            self.assertTrue((root / ".agents/just/typescript/api_rule.py").is_file())
            self.run_in(root, "git", "add", "-A")
            committed = self.run_in(root, "git", "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "m")
            self.assertEqual(committed.returncode, 0, committed.stderr)
            (root / "src/app.ts").write_text(CODE.replace("Add A and B.", "Add the numbers A and B."))
            changed = self.run_in(root, "git", "diff", "--name-only").stdout.split()
            self.assertEqual(changed, ["src/app.ts"])
            asked = self.run_in(root, "python3", "-I", "-B", "-c", ASK, "src/app.ts", "src/index.ts", "src/help.ts",
                                "src/app.test.ts", "README.md")
            self.assertEqual(asked.returncode, 0, asked.stderr)
            self.assertEqual(json.loads(asked.stdout), {"src/app.ts": True, "src/index.ts": True, "src/help.ts": False,
                                                        "src/app.test.ts": False, "README.md": False})


if __name__ == "__main__":
    unittest.main()
