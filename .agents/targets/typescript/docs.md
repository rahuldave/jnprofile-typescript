# TypeScript rules for the docs

These rules add to the base task for the docs of the TypeScript code of the change.

- **A JSDoc comment for each item.** Write a comment `/** ... */` above each class, method, function and arrow
  function that has a name, exported or not. `docstring-check` fails on an item without one. An abstract method
  needs one too. A constructor, a setter, an overload signature, a method signature of an interface, a namespace and
  an inline callback, such as the function in `xs.map((x) => x + 1)`, need none.
- **The first line.** The first line of a comment is one sentence that says what the item is for, beyond what its
  name says.
- **The parts.** Say what each parameter is for with `@param` when its name does not, what the function returns
  with `@returns`, and which error it throws with `@throws`, and on which input. Give an example with `@example` for
  an exported function whose use is not plain from its signature.
- **Types.** Give the types in the signature, not in the comment, so that `typecheck` checks them. Do not repeat
  them in `@param {type}`.
