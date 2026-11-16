# The integration tool of the typescript profile: tsc, node --test and c8, for the tests in tests/integration. just
# install integration adds it, and jnprofile-typescript installs this file.

# Compile into .jnprofile-typescript/integration-build, then run the output of each test file in tests/integration
# with node --test and c8, which writes the coverage to .jnprofile-typescript/integration/lcov.info. The build adds
# tests/integration to the include of tsconfig.json. Extra arguments are options of node --test, as for just test.
# With no test in tests/integration, it passes. When the tests passed before in this run of just, on this tree, they do
# not run again
integration *args:
    {{python_run}} {{ts_steps}} ran integration "$@" || just --justfile {{quote(module_file())}} _integration "$@"

# The run of integration: the run ID and the tree go into .jnprofile-typescript, for coverage-check
_integration *args:
    {{python_run}} {{ts_steps}} begin integration "$@"
    just --justfile {{quote(module_file())}} _test integration "$@"
    {{python_run}} {{ts_steps}} stamp integration
