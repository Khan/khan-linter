/**
 * Tests the nesting linter.
 */
var assert = require("assert");
var less = require("less");
var postcss = require("postcss");
var sourceMap = require("source-map");

var overqualifiedLint = require("../lib/overqualified-lint");

// Run the nesting linter on a given snippet of Less code
function lintCode(code, callback) {
    var options = {
        sourceMap: {
            outputSourceFiles: true,
        },
    };

    less.render(code, options, function(err, result) {
        if (err) {
            throw err;
        }

        var smc = new sourceMap.SourceMapConsumer(result.map);
        var ast = postcss.parse(result.css);
        overqualifiedLint(ast, smc, {}, function(err, violations) {
            if (err) {
                throw err;
            }

            callback(violations);
        });
    });
}

describe("Overqualified linter", function() {
    it("should pass for elements without ids and classes", function(done) {
        var lessCode = `
            ul {
                color: red;

                li {
                    padding: 0;
                }
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should pass for ids and classes without elements", function(done) {
        var lessCode = `
            #id {
                color: red;
            }

            .class1.class2 {
                color: green;
            }

            #main.class {
                color: gray;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should fail for element#id", function(done) {
        var lessCode = `
            div#main {
                color: black;
            }

            div {
                p,
                &#id {
                    color: red;
                }
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 2);

            assert.equal(violations[0].line, 1);
            assert(violations[0].reason.indexOf("div#main") > -1);

            assert.equal(violations[1].line, 7);
            assert(violations[1].reason.indexOf("div#id") > -1);

            done();
        });
    });

    it("should fail for element.class", function(done) {
        var lessCode = `
            div.centered {
                margin: 0 auto;
            }

            .main > div {
                &.class,

                &.second {
                    color: green;
                }
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 3);

            assert.equal(violations[0].line, 1);
            assert(violations[0].reason.indexOf("div.centered") > -1);

            assert.equal(violations[1].line, 6);
            assert(violations[1].reason.indexOf("div.class") > -1);

            done();
        });
    });

    it("should fail once per selector part", function(done) {
        var lessCode = `
            div.centered.padded {
                margin: 0 auto;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 1);
            assert.equal(violations[0].reason.indexOf("padded"), -1);
            done();
        });
    });

    it("should pass for nested selectors", function(done) {
        // NOTE: "div #id" is still unnecessary, but not for the purposes of
        // this linter
        var lessCode = `
            div {
                #id {
                    color: red;
                }
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should not detect percentages as selectors", function(done) {
        var lessCode = `
            @grayLighter: #ccc;

            div {
                width: 85.5%;
            }

            @keyframes block6 {
                0% { background: @grayLighter; }
                12.5% { background: @grayLighter; }
                25% { background: @grayLighter; }
                37.5% { background: @grayLighter; }
                50% { background: @grayLighter; }
                62.5% { background: @grayLighter; }
                75% { background: @grayLighter; }
                87.5% { background: @grayLighter; }
                100% { background: @grayLighter; }
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should not report overqualified selectors in imported files", function(done) {
        var lessCode = `
            @import "test/overqualified.less";

            #main {
                padding: 60px;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });
});
