# The test tool of the typescript profile: tsc, node --test and c8. just install test adds it, and
# jnprofile-typescript installs this file.

# Compile the code into dist, with tsconfig.json
build:
    {{npm}} exec -- tsc

# Compile into .jnprofile-typescript/build, then run each *.test.js, *.test.mjs and *.test.cjs file there with
# node --test and c8, which writes the coverage to .jnprofile-typescript/lcov.info. Extra arguments are options of
# node --test: just test --test-name-pattern=add.
# Alone, a project whose tsconfig.json finds no code yet passes, and the run saves JLOG_RUN for coverage-check. The
# integration tests in tests/integration run here only without the integration tool, which runs them
test *args:
    {{python_run}} {{ts_steps}} begin test "$@"
    just --justfile {{quote(module_file())}} _test test "$@"
    {{python_run}} {{ts_steps}} stamp test

# Fail on each changed line of code that no test runs, and on the first commit on each line. It reads the report of
# test only from the same run of just, JLOG_RUN, and the same tree. Otherwise it runs the tests first. When the key
# steps of .agents/stack.json has integration and the integration tool is there, a line that only the integration
# tests run counts as run, and it runs them too when their report is not from this run
coverage-check:
    {{python_run}} {{ts_steps}} fresh test {{quote(module_file())}} || just --justfile {{quote(module_file())}} test
    {{python_run}} {{ts_steps}} fresh integration {{quote(module_file())}} || just --justfile {{quote(module_file())}} integration
    {{python_run}} {{ts_steps}} coverage {{quote(module_file())}}

# Compile, run the tests, and show which lines they ran. Alone, a project with no code yet passes, as for just test.
# The integration tests run here only without the integration tool, as for just test
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
