# The test tool of the typescript profile: tsc and node --test. just install test adds it, and jnprofile-typescript
# installs this file.

# Compile src into dist
build:
    {{npm}} exec -- tsc

# Compile, then run the tests in dist with node --test. Alone, a project with no .ts file in src yet passes
test *args:
    #!/usr/bin/env sh
    if [ "$#" -eq 0 ] && [ -z "$(find src -name '*.ts' 2>/dev/null | head -n 1)" ]; then echo "just test: no code in src yet"; exit 0; fi
    {{npm}} exec -- tsc || exit $?
    if [ "$#" -eq 0 ]; then set -- 'dist/**/*.test.js'; fi
    exec {{node}} --test "$@"
