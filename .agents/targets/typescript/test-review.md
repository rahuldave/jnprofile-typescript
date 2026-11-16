# TypeScript rules for the test review

These rules add to the base task for the TypeScript tests of the change.

- **Where the tests are.** A test file has a name such as `NAME.test.ts`, next to its code in `src/`. It uses
  `node:test`. `test-parent` copies only these files into the parent commit, so a new test of new code fails there.
- **Each test checks a result.** A test uses `assert` from `node:assert/strict` on a value, or `assert.throws`
  or `assert.rejects` with a pattern for the error. A test that only calls the code and checks nothing is a
  finding.
- **The pragma.** `/* c8 ignore next */` leaves the next line out of `coverage-check`. `/* c8 ignore next N */`
  leaves N lines out, and `/* c8 ignore start */` with `/* c8 ignore stop */` leaves a block out. Each new pragma
  needs a reason in the same comment, for example `/* c8 ignore next -- only runs on Windows */`. A pragma on logic
  that a test can reach is a finding.
- **The lists.** A change to a file that the parent commit lists in `.agents/generated.txt` or
  `.agents/coverage-exclude.txt` passes `coverage-check` without a test. Each new entry needs a reason in a comment
  line above it. Judge each such change, and report new logic in it that a test can reach.
- **The coverage config.** The settings of c8 in `.c8rc`, `.c8rc.json`, `.nycrc`, `.nycrc.json` or the key `c8` of
  `package.json` come from the commit itself, not from its parent. A new `exclude` or `include` can hide new code
  from the report. The steps run c8 with `--clean`, so a `clean: false` there adds no old coverage. `coverage-check` then fails on a changed file that is not in the report, but each change to that
  config is a finding, unless it has a reason.
- **Skips and todo.** A new `test.skip`, `test.todo`, `{ skip: true }` or `{ todo: true }` names its reason. A
  test that is skipped on every machine of the project proves nothing.
- **Mocks.** A mock from `node:test`, such as `mock.fn()` or `mock.method()`, stands in for a slow or outside
  service, not for the code under test. A test whose mocks give back the answer that it checks is a finding.
