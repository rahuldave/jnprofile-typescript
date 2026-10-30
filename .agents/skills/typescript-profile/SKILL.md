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

| Tool | Packages | Recipes | Config files | Lines in `.gitignore` and `.worktreedisposable` |
|---|---|---|---|---|
| none, always there | none | `setup` | none | `node_modules/`, `*.tsbuildinfo`; also `dist/` and `.local/` in `.gitignore` |
| `lint` | `@biomejs/biome@2` | `fmt`, `lint` | `biome.json` | none |
| `typecheck` | `typescript@7`, `@types/node@24` | `typecheck` | `tsconfig.json` | none |
| `test` | `typescript@7`, `@types/node@24` | `build`, `test` | `tsconfig.json` | none |

The default tools are `lint` and `typecheck`. When `tsconfig.json` finds
no code yet, `just typecheck` and `just test` pass. tsc then stops with the
error TS18003, and the recipes look for it. `just test` runs every `*.test.js` file in
`dist`, also the file of a test that you deleted from `src`. Remove `dist`
to drop the old files.

## Lines in shared files

A tool can also add lines to a file that other profiles and you share, such
as `.gitignore`. `profile.json` lists these lines under `lines`. `just
install` writes the lines of each tool in a block of their own, at the start
of the file. The begin comment of a block names the tool, the command and
the entry in `.agents/stack-log.jsonl`. `just uninstall` of the tool takes
its lines out again, unless another profile needs them. Your own lines come
after the blocks, and the installer does not change them.

## How to run a recipe

- **`just typescript lint`** runs the recipe of the typescript profile.
- **`just lint`** runs the `lint` of each language of the project.
- **`just verify`** runs every installed check of each language, then `git
  diff --check`.
- **With more than one language**, a combined recipe such as `just test x`
  gives the same arguments to each language. To give arguments to one
  language, run `just typescript test x`.

A project that jnterfaces started has the combined recipes, such as `just
lint` and `just verify`. If its Justfile has its own recipe with the
same name, that recipe runs. A project with a Justfile of its own gets the
module only, so it runs `just typescript NAME`.

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
