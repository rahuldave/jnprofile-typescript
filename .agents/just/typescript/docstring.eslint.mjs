// The eslint config of docstring-check: only the rule jsdoc/require-jsdoc, for each class, method, function and
// arrow function, exported or not. steps.py runs eslint with npm exec, so the packages are in the cache of npm, not
// in the project. require() looks for them next to the program of eslint, process.argv[1].
import { createRequire } from "node:module";

const require = createRequire(process.argv[1]);
const jsdoc = require("eslint-plugin-jsdoc");
const parser = require("@typescript-eslint/parser");

export default [
  {
    files: ["**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts"],
    languageOptions: { parser },
    // A disable comment for another rule names a rule that this config does not have, so it is no problem.
    linterOptions: { reportUnusedDisableDirectives: "off", reportUnusedInlineConfigs: "off" },
    plugins: { jsdoc },
    rules: {
      "jsdoc/require-jsdoc": [
        "error",
        {
          publicOnly: false,
          // A constructor and a setter need no comment: the comment of the class and of the getter say what they do.
          checkConstructors: false,
          checkSetters: false,
          // An abstract method has no body, so the default contexts leave it out. An overload signature, a method
          // signature of an interface and a namespace need no comment: the implementation and the type document them.
          // A function in a type expression, as in const f = (() => 1) as F, is a function of the variable too.
          contexts: [
            "TSAbstractMethodDefinition",
            "VariableDeclarator > :matches(TSAsExpression, TSSatisfiesExpression, TSNonNullExpression, TSTypeAssertion)" +
              " > :matches(ArrowFunctionExpression, FunctionExpression)",
          ],
          require: {
            ArrowFunctionExpression: true,
            ClassDeclaration: true,
            ClassExpression: true,
            FunctionDeclaration: true,
            FunctionExpression: true,
            MethodDefinition: true,
          },
        },
      ],
    },
  },
];
