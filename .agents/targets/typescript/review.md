# TypeScript rules for the review

These rules add to the review lenses for the TypeScript code of the change.

- **Errors.** Check each new `catch`. A `catch` that drops the error is a finding, unless it logs the error or
  throws it again. `new Error(message, { cause: err })` keeps the cause. A promise that no code awaits, and that
  has no `.catch`, loses its error.
- **Types.** Each new `any`, `as` cast and non-null assertion `!` hides a type from `typecheck`. Each one is a
  finding, unless a comment gives the reason. Prefer `unknown` and a check of the value.
- **Paths and processes.** Build paths with `node:path`, not with `+`. A child process takes a list of
  arguments with `execFile` or `spawn`, not a string through a shell, unless the shell is the point and the input
  is not from a user.
- **Exports.** A new `export` is part of the API of the module. Check that it must be exported.
- **The docs lens.** A JSDoc comment says what the item is for, beyond what its name says. A stub, for example
  `/** Returns the result. */`, is a finding.
- **Lint and type pragmas.** Each new `// @ts-ignore`, `// @ts-expect-error`, `// biome-ignore` or
  `// eslint-disable` comment names its rule and a reason. A disable of `jsdoc/require-jsdoc` hides an item from
  `docstring-check`, so each one is a finding. A bare `/* eslint-disable */` with no rule turns off every rule,
  also that one, so it is a finding too.
