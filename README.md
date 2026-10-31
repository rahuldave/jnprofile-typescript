# jnprofile-typescript

jnprofile-typescript is the TypeScript profile of
[jnterfaces](https://github.com/rahuldave/jnterfaces). A profile sets up a
project in one language. It has tools, for example `lint`, and each tool
brings its packages, its parts of the config files and its recipes.

The documentation site is https://rahuldave.github.io/jnprofile-typescript/. It is built from `docs/`.
`just docs` previews it, and `just docs-publish` publishes it to the branch `gh-pages`.

## Install

Run this command in a project that has the jnterfaces installer:

```bash
just install --profile typescript
```

Then add or remove a tool:

```bash
just install test
just uninstall lint
```

The machine needs `just` and `uv`. `uv` runs node and npm from the
`nodejs-wheel` package.

## What is here

| Path | What it holds |
|---|---|
| `profile.json` | The profile: its manifest, the commands that add and remove packages, and its tools. |
| `.agents/just/typescript/` | One recipe file for each tool. The installer copies the folder into the project. |
| `files/` | The sources of the parts. `just install` copies each source to an own file under `.agents/config/` and adds an include of it to the config file. `just uninstall` takes them out. |
| `.agents/skills/typescript-profile/` | The skill that tells an agent how to use the recipes. |

## License

MIT. See [LICENSE](LICENSE).
