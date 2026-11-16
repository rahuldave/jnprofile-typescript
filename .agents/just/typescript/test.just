# The test tool of the typescript profile: tsc, node --test and c8. just install test adds it, and
# jnprofile-typescript installs this file.

# Compile the code into dist, with tsconfig.json
build:
    {{npm}} exec -- tsc

# Compile into .jnprofile-typescript/build, then run each *.test.js, *.test.mjs and *.test.cjs file there with
# node --test and c8, which writes the coverage to .jnprofile-typescript/lcov.info. Extra arguments are options of
# node --test: just test --test-name-pattern=add.
# Alone, a project whose tsconfig.json finds no code yet passes, and the run saves JLOG_RUN for coverage-check
test *args:
    {{python_run}} {{ts_steps}} begin "$@"
    just --justfile {{quote(module_file())}} _test test "$@"
    {{python_run}} {{ts_steps}} stamp

# Fail on each changed line of code that no test runs, and on the first commit on each line. It reads the report of
# test only from the same run of just, JLOG_RUN, and the same tree. Otherwise it runs the tests first
coverage-check:
    {{python_run}} {{ts_steps}} fresh || just --justfile {{quote(module_file())}} test
    {{python_run}} {{ts_steps}} coverage

# Compile, run the tests, and show which lines they ran. Alone, a project with no code yet passes, as for just test
cov *args:
    just --justfile {{quote(module_file())}} _test cov "$@"

# Run only the test files FILES, such as src/app.test.ts, for test-parent of the commit gates. It compiles the
# project into .jnprofile-typescript/test-paths, and runs the output of each file with node --test. It exits with 0
# when tests ran and passed, with 1 when a test fails or a test file does not build, as a new test of new code on the
# parent commit, and with 5 when no test runs, as for a file whose tests are all skipped or todo. Any other code
# means that npm, tsc or node itself failed, or that a test ended the run. With no file, it exits with 5 and runs
# nothing. The output has one line for each test. It is no step, so it runs without jlog, as in a worktree of the
# parent commit
test-paths *files:
    #!/usr/bin/env sh
    # A shebang recipe of a module runs in the folder of the module, and the paths start at the project.
    cd {{quote(justfile_directory())}} || exit 2
    exec {{python_run}} {{ts_steps}} test-paths "$@"

# The script of test and cov: tsc, then node --test under c8. test writes the LCOV report for coverage-check, and
# cov shows the lines. test is a step of just check, and jlog logs only the lines of a recipe with no shebang line,
# so test runs this script in one line, through just. module_file() is the file of this module, and
# just runs it in the folder of the project, so the line works also when another Justfile loads this project.
# tsc stops with error TS18003 when the include list of tsconfig.json finds no file: a project with no code yet.
# The build goes to a new folder each run, so the output of a test that you deleted from src does not run, and
# no old coverage counts: c8 runs with --clean, whatever a .c8rc of the project says. With jsx set to preserve, the
# output of a .test.tsx file is a .test.jsx file.
_test name *args:
    #!/usr/bin/env sh
    name="$1"; shift
    build=.jnprofile-typescript/build
    # steps.py build compiles into the build with the flags that the build needs, and fails on a test file with no
    # output. It exits with 3 when the include of tsconfig.json finds no file.
    {{python_run}} {{ts_steps}} build || code=$?
    if [ "${code:-0}" -eq 3 ]; then
        if [ "$#" -eq 0 ]; then echo "just $name: no code yet"; exit 0; fi
        echo "just $name: tsconfig.json finds no code"; exit 1
    fi
    if [ "${code:-0}" -ne 0 ]; then exit "$code"; fi
    # The excludes take the place of the default list of c8, which also leaves out code files such as
    # src/__tests__/helper.ts and src/ab-test.ts. They leave out only the test files of the profile.
    if [ "$name" = cov ]; then
        exec {{npm}} exec -- c8 --clean --exclude='**/*.test.{js,mjs,cjs,jsx}' --exclude='**/node_modules/**' \
            --reporter=text --temp-directory=.jnprofile-typescript/c8-cov \
            {{node}} --test "$@" "$build/**/*.test.js" "$build/**/*.test.mjs" "$build/**/*.test.cjs" "$build/**/*.test.jsx"
    fi
    exec {{npm}} exec -- c8 --clean --exclude='**/*.test.{js,mjs,cjs,jsx}' --exclude='**/node_modules/**' \
        --reporter=lcovonly --report-dir=.jnprofile-typescript --temp-directory=.jnprofile-typescript/c8 \
        {{node}} --test "$@" "$build/**/*.test.js" "$build/**/*.test.mjs" "$build/**/*.test.cjs" "$build/**/*.test.jsx"
