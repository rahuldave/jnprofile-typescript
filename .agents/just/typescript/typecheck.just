# The typecheck tool of the typescript profile: tsc, with tsconfig.json. just install typecheck adds it, and
# jnprofile-typescript installs this file.

# Check the types with tsc and tsconfig.json. A project whose tsconfig.json finds no code yet passes
typecheck:
    just --justfile {{quote(module_file())}} _typecheck

# The script of typecheck. typecheck is a step of just check, and jlog logs only the lines of a recipe with no shebang
# line, so typecheck runs this script in one line, through just. module_file() is the file of this module, and
# just runs it in the folder of the project, so the line works also when another Justfile loads this project.
# tsc stops with error TS18003 when the include list of tsconfig.json finds no file: a project with no code yet.
_typecheck:
    #!/usr/bin/env sh
    out=$({{npm}} exec -- tsc --noEmit 2>&1) && { [ -z "$out" ] || printf '%s\n' "$out"; exit 0; } || code=$?
    if printf '%s\n' "$out" | grep -q 'error TS18003'; then echo "just typecheck: no code yet"; exit 0; fi
    printf '%s\n' "$out"
    exit "$code"
