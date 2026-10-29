# The lint tool of the typescript profile: biome. just install lint adds it, and jnprofile-typescript installs this file.

# Format the code. Extra arguments go to biome: just fmt src
fmt *args:
    {{npm}} exec -- biome format --write "$@"

# Check the code against the rules in biome.json. Extra arguments go to biome: just lint --write
lint *args:
    {{npm}} exec -- biome check "$@"
