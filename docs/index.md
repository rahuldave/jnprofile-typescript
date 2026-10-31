---
title: jnprofile-typescript
---

jnprofile-typescript is the TypeScript profile of [jnterfaces](https://rahuldave.github.io/jnterfaces/). A profile sets up a project in one language. It has tools, for example `lint`, and each tool brings its packages, its parts of the config files and its recipes. A recipe is a command of the project's Justfile, such as `just lint`.

The profile is for a TypeScript project with npm. The installer finds such a project by its `package.json` or `tsconfig.json`.

## Install

Run this command in a project that has the jnterfaces installer:

```bash
just install --profile typescript
```

The command installs the tools `lint` and `typecheck`. It also turns on the default roles of the profile, `tasker` and `prose`, unless you choose otherwise. [The roles](https://rahuldave.github.io/jnterfaces/#roles) in the jnterfaces guide tells what each role installs. In a folder with no `package.json`, it first runs `npm init --yes`.

Then add or remove a tool:

```bash
just install test
just uninstall lint
```

The machine needs `just` and `uv`. `uv` runs node and npm from the `nodejs-wheel` package, so you do not install node. To install every dependency into `node_modules`, run `just setup`.

## The tools

| Tool | Packages | Recipes |
|---|---|---|
| `lint` | biome | `just fmt`, `just lint` |
| `typecheck` | typescript, @types/node | `just typecheck` |
| `test` | typescript, @types/node | `just build`, `just test` |

[The tools](tools.md) gives each recipe and each part that a tool adds to a config file.

## How the parts work

A part is the piece of a shared config file that a tool owns. `just install` adds the part, and `just uninstall` takes out only that part. Your own settings stay.

- **`biome.json` and `tsconfig.json` get an include.** The installer writes the settings of the profile to a file under `.agents/config/typescript/`, and adds that file to `extends` in your file. A setting in your file wins over the setting of the profile. When the project has a `biome.jsonc` and no `biome.json`, the include goes to `biome.jsonc`.
- **`.gitignore` and `.worktreedisposable` get a block of lines.** A block starts and ends with a comment that names its owner.

Do not edit a file under `.agents/config/`. Only the installer writes it. [Shared files and the record](https://rahuldave.github.io/jnterfaces/stack-guide.html#shared-files-and-the-record) in the jnterfaces guide tells you how the installer keeps a record of each part.

## The other sites

- [jnterfaces](https://rahuldave.github.io/jnterfaces/): the installer, and the `just`, `jagt-protocol` and `cx` skills.
- [jnprofile-python](https://rahuldave.github.io/jnprofile-python/): the Python profile.
- [agent_gest_git_skills](https://rahuldave.github.io/agent_gest_git_skills/): the tasker role and its g skills.
