# The recipes of the profile's own repository. The five recipes lint, test, prose-check, docs-check and check are the
# same in each language profile, and CI runs just check.

# The documentation site, from docs/, with smalldocs, at the pin of jnterfaces.
smalldocs := "uvx --quiet smalldocs@0.5.12"
# The checker of nossaifd, for prose-check.
nossaifd_check := env("NOSSAIFD_CHECK", home_directory() / "Projects/nossaifd/check.py")

# Lint the profile's own code and files: ruff for the Python scripts, and the recipe files with just
lint:
  uvx --quiet ruff@0.17.5 check .
  python3 scripts/lint_recipes.py

# Run all the tests of the profile, with real just, uv, git and node, the live lab included. In CI a skip fails
test:
  JNPROFILE_LIVE=1 python3 scripts/run_tests.py

# Check the Markdown pages with the checker of nossaifd. It fails on a hard note. NOSSAIFD_CHECK names the checker
prose-check:
  python3 {{quote(nossaifd_check)}} README.md docs/*.md .agents/skills/typescript-profile/SKILL.md .agents/targets/typescript/*.md

docs-check:
  {{smalldocs}} check docs

# Run every check of the repository: lint, test, prose-check and docs-check, in that order
check: lint test prose-check docs-check

docs:
  {{smalldocs}} preview docs

docs-build:
  {{smalldocs}} render docs --strict

# Build the site in strict mode, then push it to the branch gh-pages
docs-publish: docs-build
  {{smalldocs}} publish gh-pages docs --no-render
