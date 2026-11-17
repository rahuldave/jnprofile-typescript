"""The live lab of the recipe typescript::version: install the profile into a new project with the installer of
jnterfaces, then run just typescript::version in it, as the release of agent_gest_git_skills does.

just test runs it with JNPROFILE_LIVE=1, and then a missing installer fails the lab. JNTERFACES_INSTALLER names the
installer. By default it is jnterfaces/scripts/install_stack.py in SKILL_PACKAGES_DIR, or in ~/Projects. It needs uv,
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


@unittest.skipUnless(LIVE, "the live lab runs with JNPROFILE_LIVE=1, as just test sets it")
class LiveVersionTests(unittest.TestCase):
    def run_in(self, root: Path, *command: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if k not in AGENT and k not in ("CI", "JLOG_RUN") and not k.startswith(("GIT_", "GITHUB_"))}
        env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(command, cwd=root, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                              check=False)

    def status(self, root: Path) -> str:
        """The short status of git, with the ignored files, so that a file that the recipe writes shows. The logs of
        jlog in .agents/log, which the shell of the module writes for each recipe, do not count."""
        out = self.run_in(root, "git", "status", "--porcelain", "--ignored", "--untracked-files=all").stdout
        return "".join(line for line in out.splitlines(keepends=True) if not line[3:].startswith(".agents/log/"))

    def test_the_installed_recipe_prints_the_version_of_package_json(self) -> None:
        for program in ("uv", "git", "jlog", "node"):
            self.assertTrue(shutil.which(program), f"the live lab needs {program} on the PATH")
        self.assertTrue(INSTALLER.is_file(), f"no installer of jnterfaces at {INSTALLER}: set JNTERFACES_INSTALLER "
                                             "or SKILL_PACKAGES_DIR")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.run_in(root, "git", "init", "-q", "-b", "main")
            installed = self.run_in(root, "uv", "run", "--quiet", "--script", str(INSTALLER), "--target", ".",
                                    # The lab needs no tasker, whose package needs gest, which CI does not have.
                                    "--defaults", "--without", "tasker", "--profile", "typescript", "--clone",
                                    f"jnprofile-typescript={REPO}")
            self.assertEqual(installed.returncode, 0, installed.stdout[-4000:] + installed.stderr[-4000:])
            self.assertTrue((root / ".agents/just/typescript/base.just").is_file())
            manifest = root / "package.json"
            package = json.loads(manifest.read_text())

            package["version"] = "1.2.0-beta.1"
            manifest.write_text(json.dumps(package, indent=2) + "\n")
            before = self.status(root)
            done = self.run_in(root, "just", "typescript::version")
            self.assertEqual((done.returncode, done.stdout), (0, "1.2.0-beta.1\n"), done.stderr)
            self.assertEqual(self.status(root), before, "the recipe wrote a file")

            del package["version"]
            manifest.write_text(json.dumps(package, indent=2) + "\n")
            done = self.run_in(root, "just", "typescript::version")
            self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)

            manifest.write_text('{"version": ')
            done = self.run_in(root, "just", "typescript::version")
            self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr)
            self.assertIn("version: cannot read package.json", done.stderr)

            manifest.unlink()
            done = self.run_in(root, "just", "typescript::version")
            self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)


if __name__ == "__main__":
    unittest.main()
