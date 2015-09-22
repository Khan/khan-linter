/**
 * Tests the walker module
 */
var assert = require("assert");
var less = require("less");

var walker = require("../lib/walker");

// Async function that invokes a callback with a count representing the number
// of times a given `walkFn` will reach a node
function countInvocations(walkFn, lessCode, callback) {
    less.parse(lessCode, function(err, ast) {
        if (err) {
            return callback(err);
        }

        var count = 0;
        walkFn(ast, function(node, depth, done) {
            // For each node traversed, increase count by 1
            count++;
            done();
        }, function() {
            // When all is said and done, invoke callback with the count
            callback(count);
        });
    });
}

describe("Node walker", function() {
    it("should always invoke on the root", function(done) {
        var lessCode = "";

        countInvocations(walker.walk, lessCode, function(count) {
            assert(count === 1);
            done();
        });
    });

    it("should invoke for variables and properties", function(done) {
        var lessCode = `
            @var1: 10px;
            @var2: 20px;

            p {
                background-color: red;
            }
        `;

        countInvocations(walker.walk, lessCode, function(count) {
            // * `root`
            // * @var1
            // * @var2
            // * p
            // * background-color
            assert(count === 5);
            done();
        });
    });

    it("should invoke for nested statements", function(done) {
        var lessCode = `
            p {
                background-color: red;

                & + ul {
                    background-color: green;
                }
            }
        `;

        countInvocations(walker.walk, lessCode, function(count) {
            // * `root`
            // * p
            // * background-color
            // * & + ul
            // * background-color
            assert(count === 5);
            done();
        });
    });

    it("should invoke for comments", function(done) {
        var lessCode = `
            // This is a comment, and the walker will catch it
            /* This is another comment */
            a {}
        `;

        countInvocations(walker.walk, lessCode, function(count) {
            // * `root`
            // * comment
            // * comment
            // * a
            assert(count === 4);
            done();
        });
    });

    it("should not invoke on operations", function(done) {
        var lessCode = `
            @a: 10px + 5px;
            @b: lighten(blue, 25%);
        `;

        countInvocations(walker.walk, lessCode, function(count) {
            // * `root`
            // * @a:
            // * @b:
            assert(count === 3);
            done();
        });
    });
});

describe("Rule walker", function() {
    it("should only invoke a callback on Less rules", function(done) {
        var lessCode = `
            @var1: 10px;
            @var2: 20px;

            p {
                background-color: red;
            }
        `;

        countInvocations(walker.walkRules, lessCode, function(count) {
            // * p {}
            assert(count === 1);
            done();
        });
    });

    it("should invoke for nested rules", function(done) {
        var lessCode = `
            div {
                background-color: red;

                div {
                    background-color: orange;

                    div {
                        background-color: yellow;
                    }
                }

                div {
                    background-color: green;
                }
            }
        `;

        countInvocations(walker.walkRules, lessCode, function(count) {
            // * div {}
            // * div {}
            // * div {}
            // * div {}
            assert(count === 4);
            done();
        });
    });

    it("should not invoke for the root", function(done) {
        var lessCode = "";

        countInvocations(walker.walkRules, lessCode, function(count) {
            assert(count === 0);
            done();
        });
    });

    it("should not invoke for comments", function(done) {
        var lessCode = `
            // Hello
            /* Hello */
            div {
                background-color: red;
            }
        `;

        countInvocations(walker.walkRules, lessCode, function(count) {
            // * div {}
            assert(count === 1);
            done();
        });
    });
});
