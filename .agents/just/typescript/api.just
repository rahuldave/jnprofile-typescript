# The api tool of the typescript profile: smalldocs api check, for the API pages of the docs site. just install api
# adds it, and jnprofile-typescript installs this file. uv runs smalldocs with node from the nodejs-wheel package, and
# smalldocs reads the API with TypeDoc.

# Fail on each exported function, class, interface, type or constant with no JSDoc comment, on each file with no
# module comment, and on each parameter and return with no comment. The settings are the key api of
# docs/_smalldocs.yml, or else the entry src/index.ts, or each code file in src when there is no src/index.ts. Then
# run api-prose-check. The step docs-check of the docs role runs this recipe. Without that role, no step runs it
api-check:
    {{python_run}} {{ts_steps}} api check
    just --justfile {{quote(module_file())}} api-prose-check

# Check the API page of each changed file with the checker of nossaifd. The page goes into a temporary folder,
# outside the project. A changed file changed since HEAD. In CI, or with --base REF, it changed since the base that
# check-changed of nossaifd takes, in the commits or in the working tree. Without the prose role, which installs the
# checker, it passes. When it passed before in this run of just, on this tree and with the same base, it does not
# run again, so api-check and prose-check can both call it
[positional-arguments]
api-prose-check *args:
    {{python_run}} {{ts_steps}} ran prose "$@" || just --justfile {{quote(module_file())}} _api-prose-check "$@"

# The run of api-prose-check: the run ID, the tree and the base go into .jnprofile-typescript, so that it runs once
# in a run
[positional-arguments]
_api-prose-check *args:
    {{python_run}} {{ts_steps}} begin prose "$@"
    {{python_run}} {{ts_steps}} api prose "$@"
    {{python_run}} {{ts_steps}} stamp prose
