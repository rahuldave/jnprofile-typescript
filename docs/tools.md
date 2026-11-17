---
title: The tools
---

Each tool of the profile brings its packages, its recipes and its parts. The installer adds the packages to the `devDependencies` of `package.json` with npm.

The default tools are `lint`, `typecheck`, `test`, `docstring` and `api`. The first four fill six steps of `just check`, which are `fmt-check`, `lint`, `typecheck`, `test`, `coverage-check` and `docstring-check`. The tool `integration` is not a default tool. It fills the step `integration`. The tool `api` runs in the step `docs-check` of the docs role.

A step is one recipe that `just check` runs. No step has a shebang line, so jlog, the program that logs each line of a recipe, logs the line of each step and its exit code.

## The base

Every project of the profile gets the base, even a project with no tool.

| Recipe | What it does |
|---|---|
| `just setup` | Installs every dependency into `node_modules`, as `package-lock.json` says |
| `just typescript::version` | Prints the version of `package.json`, for the release tag. See [version](#version) |

The recipes run node and npm with `uvx --from 'nodejs-wheel==24.*'`. The cache of npm is in `.local/npm-cache`. The installer checks that uv can run node 24 before it writes anything. The helper script of the steps, `steps.py`, runs with `uv run --no-project` and Python 3.11 or later.

The base adds `node_modules/`, `dist/`, `.local/` and `*.tsbuildinfo` to `.gitignore`. It adds `node_modules/` and `*.tsbuildinfo` to `.worktreedisposable`. That file lists the ignored files that a command can make again. `just worktrees-prune` keeps a worktree that has ignored files, but it does not count these files.

### version

The release of agent_gest_git_skills makes a tag from the version of the project. The tag must agree with the manifest, which is `package.json`. So each language profile has a recipe `version`. It is a recipe of the base, and not a step of `just check`.

- **A version.** The recipe prints the value of the key `version` of `package.json` on one line, and exits with 0. It prints a prerelease as it is, for example `1.2.0-beta.1`.
- **No version.** When the project has no `package.json`, or the file has no key `version`, the recipe prints nothing and exits with 0.
- **A file that it cannot read.** The recipe exits with 2 and writes a message that starts with `version:`. A file that is not JSON, or not a JSON object, is such a file. So is a version that is not a string, or that has a character other than a printable ASCII character, such as a space. A link to no file is such a file too.

The recipe reads the file with the `json` module of Python, through `steps.py`. It runs with Python 3.11 or later, as the other recipes run `steps.py`. It needs no node, and it writes no file.

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
| `just test` | Compiles into `.jnprofile-typescript/build/`, then runs the tests there with `node --test` under c8. c8 writes the coverage as LCOV to `.jnprofile-typescript/lcov.info`. Extra arguments are options of `node --test`: `just test --test-name-pattern=add`. With no arguments, a project in which `tsconfig.json` matches no code yet passes. With the tool `integration`, the tests in `tests/integration` do not run, because `just integration` runs them. It is a step of `just check` |
| `just coverage-check` | Fails on each changed line of code that no test runs. It is a step of `just check` |
| `just cov` | Compiles, runs the tests, and shows the lines that they ran. With the tool `integration`, the tests in `tests/integration` do not run |
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
- **The integration tests.** A line that only the integration tests run counts as run when two things are true. The project has the tool `integration`. The key `steps` of `.agents/stack.json` has `integration`, so `just check` runs it. Then `coverage-check` reads the reports of `test` and of `integration`, and a line counts as run when one of them runs it. When the report of `integration` is not from the same run, `coverage-check` runs the integration tests first. With the answer `integration=verify`, `just check` does not run `integration`, so its report does not count.

### test-paths

`test-parent` of the commit gates runs `just typescript::test-paths` in a worktree of the parent commit, on each changed test file. A worktree has no `node_modules`, so the recipe runs `npm ci` first. It compiles the project into `.jnprofile-typescript/test-paths/`, then runs the output of each file that you name with `node --test`, in one process. Its exit code says what happened:

| Code | Meaning |
|---|---|
| 0 | The tests ran and passed |
| 1 | A test failed, or a test file does not build, as a new test of new code on the parent commit. tsc writes the other files also when one file has an error, so a file that does not build hides no other file |
| 5 | No test ran, as for a file whose tests are all skipped or todo, or a file with no test. With no file, it runs nothing and exits with 5 |
| any other | npm, tsc or node itself failed, a test file is outside the `include` of `tsconfig.json`, or a test ended the run, as with `process.exit()` |

The output has one line for each test, so a test that passes next to one that fails shows. The recipe counts the tests from the JUnit report of node, so the count does not depend on the terminal output.

## integration

The packages are `typescript@7`, `@types/node@24` and `c8@12`, as for the tool `test`. The tool is not a default tool. Add it with `just install integration`.

| Recipe | What it does |
|---|---|
| `just integration` | Compiles into `.jnprofile-typescript/integration-build/`, then runs the tests of `tests/integration` there with `node --test` under c8. c8 writes the coverage as LCOV to `.jnprofile-typescript/integration/lcov.info`. Extra arguments are options of `node --test`, as for `just test`. With no test file in `tests/integration`, it passes. It is a step of `just check` |

Put each integration test in `tests/integration`, with a name such as `tests/integration/app.test.ts`. A test imports the code from `src` with a relative path and the `.js` ending, for example `import { add } from "../../src/app.js"`.

The default `tsconfig.json` finds only `src`. So the build of `integration` adds each test file of `tests/integration` to the files that `tsconfig.json` finds. It does so with a config file of its own, which extends `tsconfig.json`. That file is at the top of the project only while tsc runs. An `exclude` of the project does not leave these files out.

`just typecheck` reads only `tsconfig.json`. To check the types of the integration tests too, add `tests/integration` to the `include`.

`just check` runs `integration` before `coverage-check`. So `coverage-check` reads the report of the step `integration` of the same run, and does not run the integration tests again. When `just integration` runs after it passed in the same run, on the same tree, it says "it passed before in this run" and does not run the tests again.

Without the tool, `just test` and `just cov` run the tests in `tests/integration` too, and their build adds the folder to the `include` in the same way. A file in `tests/integration` whose name does not end in `.test.ts` is code, such as a helper. So `coverage-check` and `docstring-check` check it.

The tool adds the same lines to `.gitignore` and to `.worktreedisposable` as the tool `test`.

## docstring

The tool has no package in `package.json`. `npm exec` runs eslint with eslint-plugin-jsdoc and the parser of typescript-eslint, at fixed versions, from the cache of npm. That parser needs a TypeScript older than 6.1, and the project has TypeScript 7, so the tool keeps them out of the project. The first run downloads the packages.

| Recipe | What it does |
|---|---|
| `just docstring-check` | Fails on each class, method, function or arrow function with no JSDoc comment, exported or not. It names the file and the line. It is a step of `just check` |

The only rule is `jsdoc/require-jsdoc`, from the config `docstring.eslint.mjs` in `.agents/just/typescript/`. The step does not read an eslint config of your project.

A constructor and a setter do not count, because the comment of the class and of the getter say what they do. An inline callback, such as the function in `xs.map((x) => x + 1)`, does not count either. Nor do an overload signature, a method signature of an interface and a namespace, because the implementation and the type document them. An abstract method counts, and so does a function in a type expression, as in `const f = (() => 1) as F`.

The test files, the declaration files, the files in `.agents`, `.claude` and `.codex`, the files in a folder `node_modules`, and the files that `.agents/generated.txt` of the parent commit names do not count.

The profile names its files for the commit gates. The code is `**/*.ts`, `**/*.tsx`, `**/*.mts` and `**/*.cts`. The test files are `**/*.test.ts`, `**/*.test.tsx`, `**/*.test.mts` and `**/*.test.cts`. `test-parent` copies only the test files into the parent commit, so no new code reaches it.

## api

The tool has no package in `package.json`. uv runs smalldocs 0.5.12 with node from the `nodejs-wheel` package. smalldocs reads the API with TypeDoc. When the project has no TypeDoc, npx fetches TypeDoc 0.28 into `.local/npm-cache`. The tool is a default tool, and its check runs in a project with the docs role of jnterfaces.

| Recipe | What it does |
|---|---|
| `just api-check` | Runs `smalldocs api check`. It fails on each exported function, class, interface, type or constant with no JSDoc comment. It also fails on each file with no module comment, and on each parameter or return with no comment. It names the file and the item, for example `app:add(a): no comment`. Then it runs `api-prose-check` |
| `just api-prose-check` | Checks the API page of each changed file with the checker of nossaifd. A changed file is a code file with a change against `HEAD`, or each code file on the first commit. In CI, or with `--base REF`, it is a file with a change since the base, as for `prose-check`: `just api-prose-check --base main` |

What `api-check` needs:

- **A module comment** for each file. Put a JSDoc comment at the top of the file, before its imports. A JSDoc comment right before a declaration is the comment of that declaration. So in a file with no imports, give the first declaration a JSDoc comment of its own, after the module comment.
- **A JSDoc comment** for each exported item.
- **A comment for each parameter.** Put a `//` comment after the parameter, on its line, or a `@param` line in the JSDoc comment.
- **A comment for the return.** Put a `@returns` line in the JSDoc comment. smalldocs also reads a `//` comment after the `{` of the body, but biome moves that comment into the body, so `fmt-check` fails on it. A function that returns `void` needs no comment on its return.

```ts
/** The arithmetic of the app. */
import { round } from "./round.js";

/**
 * Add two numbers.
 * @returns the sum
 */
export function add(
  a: number, // the first number
  b: number, // the second number
): number {
  return round(a + b);
}
```

The settings of `api-check`:

- **With a TypeScript section in the key `api` of `docs/_smalldocs.yml`**, smalldocs reads its settings there. A TypeScript section has `language: typescript`, and its key `entry` names the entry points. The step takes only the TypeScript sections, so a Python section of the same file does not count. A key `api` with no TypeScript section does not count either. When PyYAML cannot read the file, the step fails with exit 2.
- **Otherwise**, the step writes a temporary config, with `language: typescript`. Its entry is the index of `src`, which is `src/index.ts`, `src/index.tsx`, `src/index.mts` or `src/index.cts`, when one exists. Then the API is what the index exports. Without an index, the entry is each code file in `src/`, and each file gets its own page. The test files, the declaration files and the files that `.agents/generated.txt` of the parent commit names do not count.
- **With no index and no code file in `src/`**, the step passes and says that there is no API to check.
- **When TypeDoc fails**, smalldocs exits with 2, and the step says so. An example is an entry that `tsconfig.json` does not find.

The rule of the API files:

- **The file.** The profile installs `.agents/just/typescript/api_rule.py` with its recipes. The installer keeps `.agents/just/` for itself, so a tool of `profile.json` cannot own a file there. The file comes with the folder that `skill-package.json` installs, also without the `api` tool.
- **The function.** `is_api(path)` is True when the path, relative to the top of the project, is a source file of the API pages. The commit gate of agent_gest_git_skills loads the file from the parent commit. It calls `is_api` on each changed path, to fill the alias `@api`.
- **How it runs.** It uses only the Python standard library, on Python 3.9 or later, under `python -I -B`, at the top of the project. It reads git with `git show` and `git ls-files`, and it writes no file.
- **Without the `api` tool or the docs role**, as `.agents/stack.json` records them, `is_api` is False for each path.
- **The entry** comes from the TypeScript sections of the key `api` of `docs/_smalldocs.yml`. Without a TypeScript section, the entry is the same as for `api-check`. It is the index of `src`, or else the folder `src`. A TypeScript section with no `entry` also takes that entry. The rule reads the file without PyYAML. It reads maps, lists, flow lists such as `[a, b]` and flow maps such as `{a: 1}`, also over several lines. It reads plain or quoted values and comments.
- **A broken docs config.** When the rule cannot read `docs/_smalldocs.yml`, `is_api` is True for each code file. So the gate does not turn off without notice. Test files, declaration files and the files that never count stay out. The rule does not read anchors such as `&name`, tags such as `!!map` or block values such as `|`. A config with one of them is a config that the rule cannot read.
- **A broken record.** When the rule cannot read `.agents/stack.json`, it cannot know that the `api` tool is on. Then `is_api` is False for each path. No error stops the gate.
- **The files that count.** An entry file counts. A file that an entry file imports or exports again with a relative path, such as `./app.js` or `require("./app")`, also counts, and so do the files that those files import. In a folder that the docs config names as an entry, each code file counts, and each test file and declaration file counts too. In the default folder `src`, test files and declaration files do not count, as for `api-check`.
- **A run of smalldocs 0.5.12** settled the folder entry. The entry was `../src`, a folder with `app.test.ts` and `shapes.d.ts`. TypeDoc expanded the folder. `smalldocs api check` reported the items of both files, and `smalldocs api build` wrote a page for each. So a test file in that folder feeds the API pages.
- **The files that never count** are the files that `.agents/generated.txt` of the parent commit names and the files in `.agents/`, `.claude/`, `.codex/` and `node_modules`.
- **A limit.** The rule follows only relative paths. An import through a path alias of `tsconfig.json`, such as `@/app`, does not count. Then name the file as an entry, or name its folder.

Where the checks run:

- **`api-check`** runs in the step `docs-check` of the docs role of jnterfaces. That step runs the `api-check` of each language that has one. The comments are a check of the docs site, so without the docs role no step of `just check` runs `api-check`. You can still run `just api-check`, and `just verify` runs it.
- **`api-prose-check`** runs in `api-check`. The step `prose-check` of nossaifd runs it too. It runs once in a run. When it passed before in the same run of `just check`, on the same tree and with the same base, it says so and does not run again. A call with another base runs again.

The changed files of `api-prose-check`:

- **On a machine**, without CI and without `--base`, the step does not load `prose_gate.py`. A changed file has a change against `HEAD`, in the index or the working tree, or is a new file.
- **In CI**, a checkout is clean, so the changes against `HEAD` hold no file. So in CI the step takes the base that `prose-check` of nossaifd takes. On a pull request, the base is the merge base of the base branch and `HEAD`. CI is on when the variable `CI` is set to a value other than empty, `false` and `0`.
- **With `--base REF`**, the base is the merge base of `REF` and `HEAD`, also outside CI. As in `check-changed` of nossaifd, the last `--base` counts, and `-v` does nothing here.
- **The rule of the base** is not in this profile. The step loads `.agents/skills/nossaifd/scripts/prose_gate.py`, which the prose role installs, and calls its `base_commit`. So in CI, both steps compare with the same commit. The load writes no bytecode into the skill.
- **An error of the base**, as a shallow clone or a base that is not a commit, fails the step with exit 2 and the message of nossaifd. An install of nossaifd with no `base_commit` fails the step with exit 2 in CI or with `--base`, and asks you to run `just install`.

`api-prose-check` builds the API pages in a temporary folder outside the project, with the TypeScript sections of the settings. The page of a changed file is each page with an item from that file. A page holds the first paragraph of the module comment in its front matter, where the checker does not read it. So the step also checks the module comment of each changed file with a page, and of each changed entry file, such as an index that only exports again. A changed file that is no entry and has no item on a page is not in the API, so the step does not check it.

Then the step runs `.agents/skills/nossaifd/scripts/check.py` on those pages. A hard problem fails the step. Fix it in the JSDoc comment or the comment that it comes from. Without the prose role, which installs the checker, the step passes and says so.

The tool adds `.jnprofile-typescript/` to `.gitignore` and to `.worktreedisposable`. That folder holds the run ID of `api-prose-check`.

## The language layer

The profile installs `.agents/targets/typescript/`. It holds the TypeScript rules that the agentic targets add to their base task, in the files `review.md`, `test-review.md`, `docs.md` and `prose.md`. For example, `test-review.md` says that each new `/* c8 ignore */` needs a reason.
