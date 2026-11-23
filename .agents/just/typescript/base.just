# The recipes of the typescript profile that every TypeScript project has. jnprofile-typescript installs this file.

export npm_config_cache := ".local/npm-cache"

# uv runs node and npm from the nodejs-wheel package, so the machine needs just and uv only
node := "uvx --from 'nodejs-wheel==24.*' node"
npm := "uvx --from 'nodejs-wheel==24.*' npm"

# uv runs the helper script of the steps, steps.py, with Python 3.11 or later and no package
python_run := "uv run --no-project --quiet --python '>=3.11' python"
ts_steps := quote(source_directory() / "steps.py")

# Install every dependency into node_modules, as package-lock.json says
setup:
    {{npm}} install

# Print the version of package.json, such as 1.2.0-beta.1, for the release tag. It prints nothing when there is none
version:
    {{python_run}} {{ts_steps}} version

# Run the quick checks of a fix round, with no coverage: fmt-check, lint, typecheck, and the unit tests with a plain
# node --test, without c8. Each check runs only when its tool is installed: when the module, module_file(), has its
# recipe. The first check that fails stops the rest. The tests are those of just test, in a build of their own, and
# write no report, so coverage-check does not read them. Extra arguments are options of node --test:
# just typescript::quick --test-name-pattern=add. Run just check once on the final tree
quick *args:
    @if just --justfile {{quote(module_file())}} --summary | tr ' ' '\n' | grep -qx fmt-check; then just --justfile {{quote(module_file())}} fmt-check; fi
    @if just --justfile {{quote(module_file())}} --summary | tr ' ' '\n' | grep -qx lint; then just --justfile {{quote(module_file())}} lint; fi
    @if just --justfile {{quote(module_file())}} --summary | tr ' ' '\n' | grep -qx typecheck; then just --justfile {{quote(module_file())}} typecheck; fi
    @if just --justfile {{quote(module_file())}} --summary | tr ' ' '\n' | grep -qx test; then just --justfile {{quote(module_file())}} _test quick "$@"; fi

# The script of test, cov and integration: tsc, then node --test under c8. test and integration write their LCOV
# reports for coverage-check, and cov shows the lines. test and integration are steps of just check, and jlog logs
# only the lines of a recipe with no shebang line, so each runs this script in one line, through just. module_file()
# is the file of this module, and just runs it in the folder of the project, so the line works also when another
# Justfile loads this project.
# steps.py build compiles into the build of the run, with the flags that the build needs, and fails on a test file
# with no output. It exits with 3 when there is nothing to run and the recipe got no argument: tsconfig.json finds
# no code, or tests/integration has no test. With the integration tool, the build of test and cov has no output of
# tests/integration, and integration builds into a folder of its own and runs only the tests there.
# The build goes to a new folder each run, so the output of a test that you deleted does not run, and no old
# coverage counts: c8 runs with --clean, whatever a .c8rc of the project says. With jsx set to preserve, the output
# of a .test.tsx file is a .test.jsx file.
_test name *args:
    #!/usr/bin/env sh
    name="$1"; shift
    build=.jnprofile-typescript/build
    where=$build
    report=.jnprofile-typescript
    raw=.jnprofile-typescript/c8
    if [ "$name" = integration ]; then
        build=.jnprofile-typescript/integration-build
        where=$build/tests/integration
        report=.jnprofile-typescript/integration
        raw=.jnprofile-typescript/c8-integration
    fi
    [ "$name" = quick ] && where=.jnprofile-typescript/quick-build
    {{python_run}} {{ts_steps}} build "$name" {{quote(module_file())}} "$#" || code=$?
    if [ "${code:-0}" -eq 3 ]; then exit 0; fi
    if [ "${code:-0}" -ne 0 ]; then exit "$code"; fi
    # The excludes take the place of the default list of c8, which also leaves out code files such as
    # src/__tests__/helper.ts and src/ab-test.ts. They leave out only the test files of the profile.
    # quick runs node --test with no c8, so it measures no coverage and writes no report.
    if [ "$name" = quick ]; then
        exec {{node}} --test "$@" "$where/**/*.test.js" "$where/**/*.test.mjs" "$where/**/*.test.cjs" "$where/**/*.test.jsx"
    fi
    if [ "$name" = cov ]; then
        exec {{npm}} exec -- c8 --clean --exclude='**/*.test.{js,mjs,cjs,jsx}' --exclude='**/node_modules/**' \
            --reporter=text --temp-directory=.jnprofile-typescript/c8-cov \
            {{node}} --test "$@" "$where/**/*.test.js" "$where/**/*.test.mjs" "$where/**/*.test.cjs" "$where/**/*.test.jsx"
    fi
    exec {{npm}} exec -- c8 --clean --exclude='**/*.test.{js,mjs,cjs,jsx}' --exclude='**/node_modules/**' \
        --reporter=lcovonly --report-dir="$report" --temp-directory="$raw" \
        {{node}} --test "$@" "$where/**/*.test.js" "$where/**/*.test.mjs" "$where/**/*.test.cjs" "$where/**/*.test.jsx"
