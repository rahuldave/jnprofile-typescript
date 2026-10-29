# The typecheck tool of the typescript profile: tsc, with tsconfig.json. just install typecheck adds it, and
# jnprofile-typescript installs this file.

# Check the types with tsc and tsconfig.json. A project with no .ts file in src yet passes
typecheck:
    #!/usr/bin/env sh
    if [ -z "$(find src -name '*.ts' 2>/dev/null | head -n 1)" ]; then echo "just typecheck: no code in src yet"; exit 0; fi
    exec {{npm}} exec -- tsc --noEmit
