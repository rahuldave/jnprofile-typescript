---
title: The tools
---

Each tool of the profile brings its packages, its recipes and its parts. The installer adds the packages to the `devDependencies` of `package.json` with npm.

## The base

Each project of the profile gets the base, with no tool.

| Recipe | What it does |
|---|---|
| `just setup` | Installs every dependency into `node_modules`, as `package-lock.json` says |

The recipes run node and npm with `uvx --from 'nodejs-wheel==24.*'`. The cache of npm is in `.local/npm-cache`.

The base adds `node_modules/`, `dist/`, `.local/` and `*.tsbuildinfo` to `.gitignore`. It adds `node_modules/` and `*.tsbuildinfo` to `.worktreedisposable`, the list of files that a command makes again, so that they do not keep a worktree.

## lint

The package is `@biomejs/biome@2`.

| Recipe | What it does |
|---|---|
| `just fmt` | Formats the code. Extra arguments go to biome: `just fmt src` |
| `just lint` | Checks the code against the rules of biome. Extra arguments go to biome: `just lint --write` |

The part is an include in `biome.json`. Its `extends` names `./.agents/config/typescript/lint.json`. That file turns on the git integration of biome, so biome skips the files that git ignores. It leaves out `dist`, `node_modules`, `.agents`, `.claude` and `.codex`, and sets an indent of spaces and lines of at most 120 characters.

## typecheck

The packages are `typescript@7` and `@types/node@24`.

| Recipe | What it does |
|---|---|
| `just typecheck` | Checks the types with tsc and `tsconfig.json`. A project whose `tsconfig.json` finds no code yet passes |

The part is an include in `tsconfig.json`. Its `extends` names `./.agents/config/typescript/tsconfig.json`. That file compiles `src/` into `dist/` for `ES2023` and `NodeNext` modules, in strict mode, with source maps and the types of node. Its paths start with `${configDir}`, so they are paths in your project, not in `.agents/config/`.

## test

The packages are `typescript@7` and `@types/node@24`, as for `typecheck`. The tool has the same part in `tsconfig.json`. When both tools are on, the include stays until both are off.

| Recipe | What it does |
|---|---|
| `just build` | Compiles the code into `dist/`, with `tsconfig.json` |
| `just test` | Compiles, then runs the tests in `dist/` with `node --test`. A project whose `tsconfig.json` finds no code yet passes |

Put the code and the tests in `src/`. Name each test file `NAME.test.ts`, for example `src/app.test.ts`. The build writes it as `dist/app.test.js`, and `node --test` finds each file of that name. A test imports the code with the `.js` ending, for example `import { add } from "./app.js"`, because the code runs from `dist/`.
