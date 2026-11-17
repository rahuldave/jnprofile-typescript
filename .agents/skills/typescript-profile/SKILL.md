---
name: typescript-profile
description: Use when you run, add or remove the recipes of a TypeScript project that jnterfaces set up, such as just typescript lint, just test or just install typecheck. It says which tool gives which recipe, and where the files are.
---

# The typescript profile

The typescript profile of jnterfaces sets up a TypeScript project with npm.
`uv` runs node and npm from the `nodejs-wheel` package, so the machine needs
`just` and `uv` only. A tool is one unit of the setup, for example `lint`.
`just install lint` adds the packages of the tool to `devDependencies`,
adds its parts to the config files, and adds its recipes. `just uninstall lint` takes
them out.

## The tools and their recipes

| Tool | Packages | Recipes | Parts in config files | Lines in `.gitignore` and `.worktreedisposable` |
|---|---|---|---|---|
| none, always there | none | `setup`, `version` | none | `node_modules/`, `*.tsbuildinfo`; also `dist/` and `.local/` in `.gitignore` |
| `lint` | `@biomejs/biome@2` | `fmt`, `fmt-check`, `lint` | `biome.json` | none |
| `typecheck` | `typescript@7`, `@types/node@24` | `typecheck` | `tsconfig.json` | none |
| `test` | `typescript@7`, `@types/node@24`, `c8@12` | `build`, `test`, `coverage-check`, `cov`, `test-paths` | `tsconfig.json` | `.jnprofile-typescript/` |
| `docstring` | none: `npm exec` runs eslint | `docstring-check` | none | none |

The default tools are `lint`, `typecheck`, `test` and `docstring`. When `tsconfig.json` finds
no code yet, `just typecheck` and `just test` pass. tsc then stops with the
error TS18003, and the recipes look for it. `just test` compiles into a new
`.jnprofile-typescript/build` each time, and runs every `*.test.js`,
`*.test.mjs` and `*.test.cjs` file there.

## The steps of just check

- **`test`** writes the coverage as LCOV to `.jnprofile-typescript/lcov.info`, with c8.
- **`coverage-check`** fails on each changed line of code that no test runs.
  On the first commit, each line must run. Put `/* c8 ignore next */` above a
  line that no test can run. A file of generated code goes in
  `.agents/generated.txt`, in a commit of its own before the code.
- **`docstring-check`** fails on each class, method, function or arrow
  function with no JSDoc comment `/** ... */`, exported or not. It names the
  file and the line, so write a comment for each line that it lists.
- **`fmt-check`** fails when `just fmt` would change a file.

## Parts in shared files

A tool adds a part to a file that other profiles and you share, such as
`.gitignore` or `biome.json`. `profile.json` lists the lines of a tool under
`lines`, and its other parts under `parts`. `just install` writes the lines
of each tool in a block of their own, at the start of the file.

A config
file gets an include, such as an `extend` or an `extends`, that reads an own
file under `.agents/config/typescript/`. The key `parts` in `.agents/stack.json`
records each part. `just uninstall` of the tool takes its parts out again,
unless another tool needs them. Your own lines and settings stay, and your
settings win over the settings of the own file.

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
- **`.agents/config/typescript/`** holds the own files, such as `lint.json`. The
  installer writes them. Do not edit them. Put a setting of yours in
  `biome.json`, where it wins.

## Rules for agents

- Run the recipes, not the tools. Write `just test`, not `npm test`.
- To add a tool, run `just install NAME`. Do not run `npm install` for the
  packages of a tool, because then the installer does not own them.
