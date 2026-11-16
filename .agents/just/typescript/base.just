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
    {{python_run}} {{ts_steps}} build "$name" {{quote(module_file())}} "$#" || code=$?
    if [ "${code:-0}" -eq 3 ]; then exit 0; fi
    if [ "${code:-0}" -ne 0 ]; then exit "$code"; fi
    # The excludes take the place of the default list of c8, which also leaves out code files such as
    # src/__tests__/helper.ts and src/ab-test.ts. They leave out only the test files of the profile.
    if [ "$name" = cov ]; then
        exec {{npm}} exec -- c8 --clean --exclude='**/*.test.{js,mjs,cjs,jsx}' --exclude='**/node_modules/**' \
            --reporter=text --temp-directory=.jnprofile-typescript/c8-cov \
            {{node}} --test "$@" "$where/**/*.test.js" "$where/**/*.test.mjs" "$where/**/*.test.cjs" "$where/**/*.test.jsx"
    fi
    exec {{npm}} exec -- c8 --clean --exclude='**/*.test.{js,mjs,cjs,jsx}' --exclude='**/node_modules/**' \
        --reporter=lcovonly --report-dir="$report" --temp-directory="$raw" \
        {{node}} --test "$@" "$where/**/*.test.js" "$where/**/*.test.mjs" "$where/**/*.test.cjs" "$where/**/*.test.jsx"
