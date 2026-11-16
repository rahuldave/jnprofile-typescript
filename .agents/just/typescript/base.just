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
