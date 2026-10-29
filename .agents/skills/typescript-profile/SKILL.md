---
name: typescript-profile
description: Use when you run, add or remove the recipes of a TypeScript project that jnterfaces set up, such as just typescript lint, just test or just install typecheck. It says which tool gives which recipe, and where the files are.
---

# The typescript profile

The typescript profile of jnterfaces sets up a TypeScript project with npm.
`uv` runs node and npm from the `nodejs-wheel` package, so the machine needs
`just` and `uv` only. A tool is one unit of the setup, for example `lint`.
`just install lint` adds the packages of the tool to `devDependencies`,
copies its config files, and adds its recipes. `just uninstall lint` takes
them out.

## The tools and their recipes

| Tool | Packages | Recipes | Config files |
|---|---|---|---|
| none, always there | none | `setup` | `.gitignore` |
| `lint` | `@biomejs/biome@2` | `fmt`, `lint` | `biome.json` |
| `typecheck` | `typescript@7`, `@types/node@24` | `typecheck` | `tsconfig.json` |
| `test` | `typescript@7`, `@types/node@24` | `build`, `test` | `tsconfig.json` |

The default tools are `lint` and `typecheck`. With no `.ts` file in `src`
yet, `just typecheck` and `just test` pass.

## How to run a recipe

- **`just typescript lint`** runs the recipe of the typescript profile.
- **`just lint`** runs the `lint` of each language of the project.
- **`just verify`** runs every installed check of each language, then `git
  diff --check`.

If the Justfile of the project has its own recipe with the same name, that
recipe runs. Then `just typescript NAME` runs the recipe of the profile.

## Where the files are

- **`.agents/just/typescript/`** holds the recipe files. The installer
  writes them. Do not edit them, because the next `just install` names an
  edited file and does not update it. Put your own recipes in the Justfile.
- **The config files**, for example `biome.json`, are yours after the first
  install. A later install leaves them alone.

## Rules for agents

- Run the recipes, not the tools. Write `just test`, not `npm test`.
- To add a tool, run `just install NAME`. Do not run `npm install` for the
  packages of a tool, because then the installer does not own them.
