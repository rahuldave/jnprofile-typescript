# The test tool of the typescript profile: tsc and node --test. just install test adds it, and jnprofile-typescript
# installs this file.

# Compile the code into dist, with tsconfig.json
build:
    {{npm}} exec -- tsc

# Compile, then run the tests in dist with node --test. Alone, a project whose tsconfig.json finds no code yet passes
test *args:
    #!/usr/bin/env sh
    # tsc stops with error TS18003 when the include list of tsconfig.json finds no file: a project with no code yet
    out=$({{npm}} exec -- tsc 2>&1) || code=$?
    if [ -n "${code:-}" ]; then
        if [ "$#" -eq 0 ] && printf '%s\n' "$out" | grep -q 'error TS18003'; then echo "just test: no code yet"; exit 0; fi
        printf '%s\n' "$out"
        exit "$code"
    fi
    if [ "$#" -eq 0 ]; then set -- 'dist/**/*.test.js'; fi
    exec {{node}} --test "$@"
