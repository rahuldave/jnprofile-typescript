# The docstring tool of the typescript profile: eslint with the rule jsdoc/require-jsdoc. just install docstring adds
# it, and jnprofile-typescript installs this file. npm exec installs eslint into the cache of npm on the first run.

# Fail on each class, method, function or arrow function with no JSDoc comment, exported or not, and name its file
# and line
docstring-check:
    {{python_run}} {{ts_steps}} docs
