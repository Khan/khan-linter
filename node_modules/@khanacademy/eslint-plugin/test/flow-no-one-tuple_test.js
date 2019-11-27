const {rules} = require("../lib/index.js");
const RuleTester = require("eslint").RuleTester;

const parserOptions = {
    parser: "babel-eslint",
};

const ruleTester = new RuleTester(parserOptions);
const rule = rules["flow-no-one-tuple"];

const message = rule.__message;
const errors = [message];

ruleTester.run("flow-no-one-tuple", rule, {
    valid: [
        {
            code: "type foo = { bar: Array<number> }",
            options: ["always"],
        },
        {
            code: "type foo = { bar: [number, number] }",
            options: ["always"],
        },
    ],
    invalid: [
        {
            code: "type foo = { bar: [number] }",
            options: ["always"],
            errors: errors,
            output: "type foo = { bar: Array<number> }",
        },
        {
            code: "type foo = { bar: [[number]] }",
            options: ["always"],
            // Two errors are reported because there are two one-tuples,
            // they just happen to be nested.
            errors: [message, message],
            // This is a partial fix.  Multiple runs of eslint --fix are needed
            // to fix nested 1-tuples completely.
            output: "type foo = { bar: Array<[number]> }",
        },
    ],
});
