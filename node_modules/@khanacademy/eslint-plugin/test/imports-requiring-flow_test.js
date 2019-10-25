const path = require("path");

const rule = require("../lib/rules/imports-requiring-flow");
const RuleTester = require("eslint").RuleTester;

const parserOptions = {
    parser: "babel-eslint",
};

const ruleTester = new RuleTester(parserOptions);
const message = rule.__message;
const errors = [message];
const rootDir = "/Users/nyancat/project";

const importFooPkgFlow = `
// @flow
import foo from "foo";
`;

const importFooPkgNoflow = `
// @noflow
import foo from "foo";
`;

const importBarModFlow = `
// @flow
import bar from "../package-2/bar.js";
`;

const importBarModNoflow = `
// @noflow
import bar from "../package-2/bar.js";
`;

const requireFooPkgFlow = `
// @flow
const foo = require("foo");
`;

const requireFooPkgNoflow = `
// @noflow
const foo = require("foo");
`;

const requireBarModFlow = `
// @flow
const bar = require("../package-2/bar.js");
`;

const requireBarModNoflow = `
// @noflow
const bar = require("../package-2/bar.js");
`;

const dynamicImportFooPkgFlow = `
// @flow
const fooPromise = import("foo");
`;

const dynamicImportFooPkgNoflow = `
// @noflow
const fooPromise = import("foo");
`;

const dynamicImportBarModFlow = `
// @flow
const barPromise = import("../package-2/bar.js");
`;

const dynamicImportBarModNoflow = `
// @noflow
const barPromise = import("../package-2/bar.js");
`;

ruleTester.run("imports-requiring-flow", rule, {
    valid: [
        {
            code: importFooPkgFlow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["foo"],
                    rootDir,
                },
            ],
        },
        {
            code: importBarModFlow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["src/package-2/bar.js"],
                    rootDir,
                },
            ],
        },
        {
            code: requireFooPkgFlow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["foo"],
                    rootDir,
                },
            ],
        },
        {
            code: dynamicImportBarModFlow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["src/package-2/bar.js"],
                    rootDir,
                },
            ],
        },
        {
            code: dynamicImportFooPkgFlow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["foo"],
                    rootDir,
                },
            ],
        },
        {
            code: requireBarModFlow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["src/package-2/bar.js"],
                    rootDir,
                },
            ],
        },
        {
            code: importFooPkgNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["baz"], // isn't imported so it's okay
                    rootDir,
                },
            ],
        },
        {
            code: importBarModNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["baz"], // isn't imported so it's okay
                    rootDir,
                },
            ],
        },
        {
            code: requireFooPkgNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["baz"], // isn't imported so it's okay
                    rootDir,
                },
            ],
        },
        {
            code: requireBarModNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["baz"], // isn't imported so it's okay
                    rootDir,
                },
            ],
        },
        {
            code: dynamicImportBarModNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["baz"], // isn't imported so it's okay
                    rootDir,
                },
            ],
        },
        {
            code: dynamicImportFooPkgNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["baz"], // isn't imported so it's okay
                    rootDir,
                },
            ],
        },
    ],
    invalid: [
        {
            code: importFooPkgNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["foo"],
                    rootDir,
                },
            ],
            errors: ['Importing "foo" requires using flow.'],
        },
        {
            code: importBarModNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["src/package-2/bar.js"],
                    rootDir,
                },
            ],
            errors: ['Importing "../package-2/bar.js" requires using flow.'],
        },
        {
            code: requireFooPkgNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["foo"],
                    rootDir,
                },
            ],
            errors: ['Importing "foo" requires using flow.'],
        },
        {
            code: requireBarModNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["src/package-2/bar.js"],
                    rootDir,
                },
            ],
            errors: ['Importing "../package-2/bar.js" requires using flow.'],
        },
        {
            code: dynamicImportFooPkgNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["foo"],
                    rootDir,
                },
            ],
            errors: ['Importing "foo" requires using flow.'],
        },
        {
            code: dynamicImportBarModNoflow,
            filename: path.join(rootDir, "src/package-1/foobar.js"),
            options: [
                {
                    modules: ["src/package-2/bar.js"],
                    rootDir,
                },
            ],
            errors: ['Importing "../package-2/bar.js" requires using flow.'],
        },
    ],
});
