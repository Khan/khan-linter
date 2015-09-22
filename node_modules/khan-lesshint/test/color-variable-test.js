/**
 * Tests the Color Variable Linter.
 */
var assert = require("assert");

var colorVariableLint = require("../lib/color-variable-lint");
var lintCode = require("./lint-less-code")(colorVariableLint);

describe("Color variable linter", function() {
    it("should pass when no colors are used", function(done) {
        var lessCode = `
            body {
                margin: 0;
                padding: 60px;
            }

            #main {
                margin: 0 auto;
                width: 800px;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should pass when color declarations use a variable", function(done) {
        var lessCode = `
            @red: rgb(255, 0, 100);
            a {
                color: @red;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should fail when color declarations do not use a variable", function(done) {
        var lessCode = `
            a {
                color: rgb(255, 0, 100);
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 1);
            assert.equal(violations[0].line, 2);
            done();
        });
    });

    it("should fail when inline colors are used in functions", function(done) {
        var lessCode = `
            @green: #23ee23;

            a {
                color: darken(rgb(255, 0, 100), 20%);
                background-color: darken(#cccccc, 50%);
                border-color: @green;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 2);
            assert.equal(violations[0].line, 4);
            assert.equal(violations[1].line, 5);
            done();
        });
    });

    it("should pass when color variables are used in functions", function(done) {
        var lessCode = `
            @red: rgb(255, 0, 100);

            a {
                color: darken(@red, 20%);
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should extract colors from anywhere in a declaration", function(done) {
        var lessCode = `
            @green: #0e0;

            a {
                border: 1px solid #000;
                box-shadow: 2px 2px 2px 2px rgba(0, 255, 0, 0.9);
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert(violations[0].reason.indexOf("#000000") > -1);
            assert(violations[1].reason.indexOf("@green") > -1);
            done();
        });
    });

    it("should fail when inline colors are mixed with variables", function(done) {
        var lessCode = `
            @red: rgb(255, 0, 100);

            a {
                color: mix(@red, #ff00ff);
                background-color: mix(#ff00ff, @red);
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 2);
            assert.equal(violations[0].line, 4);
            assert.equal(violations[1].line, 5);
            done();
        });
    });

    it("should suggest a variable when an inline color matches", function(done) {
        var lessCode = `
            @red: rgb(255, 0, 0);
            @blue: rgb(0, 0, 255);

            a {
                color: rgb(255, 0, 0);

                &:hover {
                    color: #00f;
                }
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 2);
            assert(violations[0].reason.indexOf("@red") > -1);
            assert(violations[0].reason.indexOf("line 1") > -1);

            assert(violations[1].reason.indexOf("@blue") > -1);
            assert(violations[1].reason.indexOf("line 2") > -1);
            done();
        });
    });

    it("should suggest a variable when an inline color is close", function(done) {
        var lessCode = `
            @red: rgba(255, 10, 20, 0.9);
            @green: #00ff00;

            a {
                border-color: lighten(rgb(10, 245, 13), 10%);
                color: #f00;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 2);

            assert(violations[0].reason.indexOf("@green") > -1);
            assert(violations[0].reason.indexOf("line 2") > -1);

            assert(violations[1].reason.indexOf("@red") > -1);
            assert(violations[1].reason.indexOf("line 1") > -1);
            done();
        });
    });

    it("should report inline colors in hex format", function(done) {
        var lessCode = `
            a {
                color: rgb(0, 0, 255);
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 1);
            assert(violations[0].reason.indexOf("#0000ff") > -1);
            done();
        });
    });

    it("should not suggest a variable that is too far", function(done) {
        var lessCode = `
            @red: rgb(255, 10, 20);

            a {
                color: #f77;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 1);
            assert.equal(violations[0].reason.indexOf("@red"), -1);
            done();
        });
    });

    it("should ignore inline rgb() values with math in them", function(done) {
        var lessCode = `
            a {
                color: rgb(10 * 20, 0, 0);
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 0);
            done();
        });
    });

    it("should look in imported files for color variable suggestions", function(done) {
        var lessCode = `
            @import "test/colors.less";

            a {
                color: #000;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 1);
            assert(violations[0].reason.indexOf("@black") > -1);
            assert(violations[0].reason.indexOf("colors.less") > -1);
            done();
        });
    });

    it("should not suggest colors from ignored directories", function(done) {
        var lessCode = `
            @import "test/colors.less";

            a {
                color: #000;
            }
        `.trim();

        lintCode(lessCode, function(violations) {
            assert.equal(violations.length, 1);
            assert.equal(violations[0].reason.indexOf("@black"), -1);
            assert.equal(violations[0].reason.indexOf("colors.less"), -1);
            done();
        }, {
            ignore: ["test"],
        });
    });
});
