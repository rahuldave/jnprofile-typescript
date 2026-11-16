# jnprofile-typescript

jnprofile-typescript is the TypeScript profile of
[jnterfaces](https://github.com/rahuldave/jnterfaces). A profile sets up a
project in one language. It has tools, for example `lint`, and each tool
brings its packages, its parts of the config files and its recipes. A part is
the piece of a shared config file that a tool owns. A recipe is a command of
the project's Justfile, such as `just lint`.

The documentation site is https://rahuldave.github.io/jnprofile-typescript/. Its
pages are in `docs/`. `just docs` shows a preview of the site, and
`just docs-publish` publishes it to the branch `gh-pages`.

## Install

Run this command in a project that has the jnterfaces installer:

```bash
just install --profile typescript
```

Then add or remove a tool:

```bash
just install test
just uninstall lint
```

The machine needs `just` and `uv`. `uv` runs node and npm from the
`nodejs-wheel` package.

## What is here

| Path | What it holds |
|---|---|
| `profile.json` | The profile: its manifest, the commands that add and remove packages, and its tools. |
| `.agents/just/typescript/` | One recipe file for each tool, and `steps.py`, the helper script of `coverage-check`, `docstring-check` and `test-paths`. The installer copies the folder into the project. A step of `just check`, such as `test` and `typecheck`, has no shebang line, so that jlog, the program that logs each line of a recipe, logs the line of the step and its exit code. Its script is in a private recipe, which the step runs in one line with `just`. |
| `files/` | The sources of the parts. `just install` copies each source to a file of its own under `.agents/config/` and adds an include of that file to the config file. `just uninstall` takes the parts out. |
| `.agents/targets/typescript/` | The language layer: the TypeScript rules that the agentic targets, such as `review` and `test-review`, add to their base task. The installer copies the folder into the project. |
| `tests/` | The tests of the recipes, with real just, uv, git and node, and the live lab, which installs the profile with the installer of jnterfaces. `just test` runs them. |
| `scripts/lint_recipes.py` | The lint of the recipe files. `just lint` runs it. |
| `.github/workflows/verify.yml` | The CI. It runs `just check`. |
| `.agents/skills/typescript-profile/` | The skill that tells an agent how to use the recipes. |

## The checks of this repository

The Justfile of this repository has the same five checks as the other language profiles:

| Recipe | What it does |
|---|---|
| `just lint` | Runs ruff on the Python scripts, with `ruff.toml`. Then it checks that each recipe file parses with `base.just` alone, and that all the recipe files parse together. |
| `just test` | Runs all the tests, and the live lab too, with `scripts/run_tests.py`. In CI, a test that skips fails the run, so a missing program cannot pass. |
| `just prose-check` | Runs the checker of nossaifd on the Markdown pages. A hard note fails it. The variable `NOSSAIFD_CHECK` names the checker. The default is `~/Projects/nossaifd/check.py`. |
| `just docs-check` | Runs `smalldocs check docs` with smalldocs 0.5.12. |
| `just check` | Runs `lint`, `test`, `prose-check` and `docs-check`, in that order. |

The live lab installs the profile into a new project, and it needs uv, git, jlog and node. It finds the installer and the other packages in the folder that `SKILL_PACKAGES_DIR` names, or else in `~/Projects`. `JNTERFACES_INSTALLER` can name the installer.

The CI runs `just check` on each push and on each pull request. It installs node and jlog v0.1.1. It clones jnterfaces and nossaifd at fixed commits. The live lab installs the profile without the tasker role, so it needs no other package. No agent and no model runs in CI.

## License

The license is MIT. See [LICENSE](LICENSE).
