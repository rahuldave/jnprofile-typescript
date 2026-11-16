# TypeScript rules for the prose

These rules add to the base task for the prose of the TypeScript docs of the change.

- **JSDoc comments are prose.** Apply the guide to the text of each changed JSDoc comment, as to a page. Keep the
  code in `@example`, the tags such as `@param` and `@returns`, and the names of the parameters as they are.
- **The first line.** The first line of a comment is one sentence that ends with a period. An editor shows it
  alone when you point at the name, so it makes sense without the rest of the comment.
- **Names in code.** Write the name of a module, a class, a function or a parameter in backticks, as in
  `parse()`, so that the check of the guide and the reader see it as code.
