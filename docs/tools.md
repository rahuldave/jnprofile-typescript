---
title: The tools
---

Each tool of the profile brings its packages, its recipes and its parts. The installer adds the packages to the `devDependencies` of `package.json` with npm.

The default tools are `lint`, `typecheck`, `test` and `docstring`. Together they fill six steps of `just check`, which are `fmt-check`, `lint`, `typecheck`, `test`, `coverage-check` and `docstring-check`. A step is one recipe that `just check` runs. No step has a shebang line, so jlog, the program that logs each line of a recipe, logs the line of each step and its exit code.

## The base

Every project of the profile gets the base, even a project with no tool.

| Recipe | What it does |
|---|---|
| `just setup` | Installs every dependency into `node_modules`, as `package-lock.json` says |

The recipes run node and npm with `uvx --from 'nodejs-wheel==24.*'`. The cache of npm is in `.local/npm-cache`. The installer checks that uv can run node 24 before it writes anything. The helper script of the steps, `steps.py`, runs with `uv run --no-project` and Python 3.11 or later.

The base adds `node_modules/`, `dist/`, `.local/` and `*.tsbuildinfo` to `.gitignore`. It adds `node_modules/` and `*.tsbuildinfo` to `.worktreedisposable`. That file lists the ignored files that a command can make again. `just worktrees-prune` keeps a worktree that has ignored files, but it does not count these files.

## lint

The package is `@biomejs/biome@2`.

| Recipe | What it does |
|---|---|
| `just fmt` | Formats the code. Extra arguments go to biome: `just fmt src` |
| `just fmt-check` | Fails when biome would change the format of a file. It changes no file. It is a step of `just check` |
| `just lint` | Checks the code against the rules of biome. Extra arguments go to biome: `just lint --write` |

The part is an include in `biome.json`. Its `extends` names `./.agents/config/typescript/lint.json`. That file makes biome read the ignore file of git, so biome skips the files that git ignores. It leaves out `dist`, `node_modules`, `.agents`, `.claude` and `.codex`, and the Markdown pages, which `prose-check` checks. A project that sets its own `files.includes` in `biome.json` replaces that list, so it must repeat these exclusions. It also sets the formatter to indent with spaces and to keep lines to at most 120 characters.

## typecheck

The packages are `typescript@7` and `@types/node@24`.

| Recipe | What it does |
|---|---|
| `just typecheck` | Checks the types with tsc and `tsconfig.json`. A project in which `tsconfig.json` matches no code yet passes. It is a step of `just check` |

The part is an include in `tsconfig.json`. Its `extends` names `./.agents/config/typescript/tsconfig.json`. That file compiles `src/` into `dist/` for `ES2023` and `NodeNext` modules, in strict mode, with source maps and the types of node. Its paths start with `${configDir}`, so they are paths in your project, not in `.agents/config/`.

## test

The packages are `typescript@7`, `@types/node@24` and `c8@12`. c8 records which lines the tests run. The tool has the same part in `tsconfig.json` as `typecheck`. When both tools are on, the include stays until both are off.

| Recipe | What it does |
|---|---|
| `just build` | Compiles the code into `dist/`, with `tsconfig.json` |
| `just test` | Compiles into `.jnprofile-typescript/build/`, then runs the tests there with `node --test` under c8. c8 writes the coverage as LCOV to `.jnprofile-typescript/lcov.info`. Extra arguments are options of `node --test`: `just test --test-name-pattern=add`. With no arguments, a project in which `tsconfig.json` matches no code yet passes. It is a step of `just check` |
| `just coverage-check` | Fails on each changed line of code that no test runs. It is a step of `just check` |
| `just cov` | Compiles, runs the tests, and shows the lines that they ran |
| `just typescript::test-paths FILE...` | Runs only the test files that you name, for `test-parent` of the commit gates. See [test-paths](#test-paths) |

Put the code and the tests in `src/`. Name each test file `NAME.test.ts`, for example `src/app.test.ts`.

`just test` removes `.jnprofile-typescript/build/` and compiles into it again, so the old output of a test that you deleted from `src` does not run. It runs each file there whose name ends in `.test.js`, `.test.mjs`, `.test.cjs` or `.test.jsx`. A test imports the code with the `.js` ending, for example `import { add } from "./app.js"`, because the code runs from the build.

The build reads `tsconfig.json` with `tsc --showConfig`, and sets these flags in place of the settings of the project:

- **The output.** The output goes to the build, with the folders of the project, such as `build/src/app.js`. `noEmit` and `emitDeclarationOnly` are off, so tsc writes JavaScript.
- **The declarations.** When `declaration` or `composite` is on, the declarations go to `build/types`, not to the `declarationDir` of the project. So a run writes no file outside the build.
- **Source maps and build info.** The build has source maps and its own build info, whatever `tsconfig.json` says about `sourceMap` and `tsBuildInfoFile`. So c8 maps the coverage back to `src`, and an incremental project writes all of its output again.
- **A test file that tsc does not compile** fails `just test`, because its tests would never run. An example is a file in `tests/` when the `include` names only `src`. Add its folder to the `include`. A test file that another runner owns, such as an end-to-end test, needs a name that the key `tests` does not match, such as `checkout.e2e.ts`.

Some things work differently when the code runs from the build:

- **Fixtures.** The build holds only the output of tsc. A test that reads a data file next to it, through `import.meta.dirname`, does not find it. Build the path from the top of the project, such as `path.join(process.cwd(), "src/fixtures/a.json")`.
- **Path aliases.** tsc does not rewrite the aliases of `paths`, so node cannot find them. The `imports` of `package.json` name files in `dist`, not in the build. So use relative imports, such as `"./lib/a.js"`, in the code that the tests load.
- **JSX.** With `jsx` set to `preserve`, tsc writes a `.test.tsx` file as `.test.jsx`, and node cannot run it, so `just test` fails on it. Set `jsx` to `react-jsx` for the tests.
- **Other test names.** Only the names of the key `tests` of `profile.json` are test files. A file such as `app.spec.ts` counts as code, so `coverage-check` and `docstring-check` check it, and `just test` does not run it.

c8 runs with `--clean`, so no coverage of an old run counts, whatever a `.c8rc.json` of the project says. It leaves out only the test files and `node_modules`, so a code file such as `src/__tests__/helper.ts` counts.

The tool adds `.jnprofile-typescript/` to `.gitignore` and to `.worktreedisposable`. That folder holds the report and the run ID.

### coverage-check

`coverage-check` compares the coverage report with the parent commit. It runs diff-cover with a limit of 100%.

- **A line that no test runs** fails. Put `/* c8 ignore next */` above a line that no test can run, and the line counts as run. `/* c8 ignore next 3 */` leaves 3 lines out, and `/* c8 ignore start */` with `/* c8 ignore stop */` leaves a block out. c8 marks a whole function as not run, from its first line to its closing brace, so one line of ignore is not enough for a function. A function that never runs fails on its first line too, also a one-line arrow function such as `export const f = () => 1`.
- **A changed file that no test imports** fails, because the report does not have it. A file of types only, such as a file with only an `interface`, does not count, because tsc writes no code for it, so no test can load it. A code file outside the `include` of `tsconfig.json`, such as a config file at the top of the project, is in no report. Put such a file in `.agents/coverage-exclude.txt`.
- **No report** fails, with the message "write tests". When no test runs, the report is missing or has no file.
- **The first commit** has no parent. Then each line of code must run in the tests, a limit of 100%.
- **The files that do not count** are the test files, the declaration files such as `types.d.ts`, the files in `.agents`, `.claude` and `.codex`, and the files in a folder `node_modules`. The files that `.agents/generated.txt` or `.agents/coverage-exclude.txt` names do not count either. The step reads both lists from the parent commit, so a commit cannot exempt its own code with them. The config of c8, such as `exclude` in `.c8rc.json`, comes from the commit itself, so `test-review` judges each change to it.
- **The report of the same run.** `test` saves the run ID of `just check`, `JLOG_RUN`, with the tree of the worktree. `coverage-check` reads the report only when both match. Otherwise it runs the tests first.

### test-paths

`test-parent` of the commit gates runs `just typescript::test-paths` in a worktree of the parent commit, on each changed test file. A worktree has no `node_modules`, so the recipe runs `npm ci` first. It compiles the project into `.jnprofile-typescript/test-paths/`, then runs the output of each file that you name with `node --test`, in one process. Its exit code says what happened:

| Code | Meaning |
|---|---|
| 0 | The tests ran and passed |
| 1 | A test failed, or a test file does not build, as a new test of new code on the parent commit. tsc writes the other files also when one file has an error, so a file that does not build hides no other file |
| 5 | No test ran, as for a file whose tests are all skipped or todo, or a file with no test. With no file, it runs nothing and exits with 5 |
| any other | npm, tsc or node itself failed, a test file is outside the `include` of `tsconfig.json`, or a test ended the run, as with `process.exit()` |

The output has one line for each test, so a test that passes next to one that fails shows. The recipe counts the tests from the JUnit report of node, so the count does not depend on the terminal output.

## docstring

The tool has no package in `package.json`. `npm exec` runs eslint with eslint-plugin-jsdoc and the parser of typescript-eslint, at fixed versions, from the cache of npm. That parser needs a TypeScript older than 6.1, and the project has TypeScript 7, so the tool keeps them out of the project. The first run downloads the packages.

| Recipe | What it does |
|---|---|
| `just docstring-check` | Fails on each class, method, function or arrow function with no JSDoc comment, exported or not. It names the file and the line. It is a step of `just check` |

The only rule is `jsdoc/require-jsdoc`, from the config `docstring.eslint.mjs` in `.agents/just/typescript/`. The step does not read an eslint config of your project.

A constructor and a setter do not count, because the comment of the class and of the getter say what they do. An inline callback, such as the function in `xs.map((x) => x + 1)`, does not count either. Nor do an overload signature, a method signature of an interface and a namespace, because the implementation and the type document them. An abstract method counts, and so does a function in a type expression, as in `const f = (() => 1) as F`.

The test files, the declaration files, the files in `.agents`, `.claude` and `.codex`, the files in a folder `node_modules`, and the files that `.agents/generated.txt` of the parent commit names do not count.

The profile names its files for the commit gates. The code is `**/*.ts`, `**/*.tsx`, `**/*.mts` and `**/*.cts`. The test files are `**/*.test.ts`, `**/*.test.tsx`, `**/*.test.mts` and `**/*.test.cts`. `test-parent` copies only the test files into the parent commit, so no new code reaches it.

## The language layer

The profile installs `.agents/targets/typescript/`. It holds the TypeScript rules that the agentic targets add to their base task, in the files `review.md`, `test-review.md`, `docs.md` and `prose.md`. For example, `test-review.md` says that each new `/* c8 ignore */` needs a reason.

## No API pages yet

smalldocs 0.5.5 reads the API of Python only. So the profile has no `api` tool and no `api` step, and `docs-check` checks the pages of the site alone. An `api` tool comes after the release of smalldocs that reads JSDoc.
