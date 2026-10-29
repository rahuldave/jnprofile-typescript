# The recipes of the typescript profile that every TypeScript project has. jnprofile-typescript installs this file.

export npm_config_cache := ".local/npm-cache"

# uv runs node and npm from the nodejs-wheel package, so the machine needs just and uv only
node := "uvx --from 'nodejs-wheel==24.*' node"
npm := "uvx --from 'nodejs-wheel==24.*' npm"

# Install every dependency into node_modules, as package-lock.json says
setup:
    {{npm}} install
