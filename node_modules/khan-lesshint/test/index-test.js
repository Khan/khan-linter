/**
 * Tests the entire Lesshint module.
 *
 * Specifically, tests edge-case inputs to the entire Lesshint module.
 */
var assert = require("assert");
var lesshint = require("../");

function lintCode(code, callback) {
    lesshint("test.less", code, { reporter: () => {} }, callback);
}

describe("Lesshint", function() {
    it("should return 0 errors for empty code", function(done) {
        var lessCode = "";
        lintCode(lessCode, function(count) {
            assert.equal(count, 0);
            done();
        });
    });

    it("should return 0 errors for blank code", function(done) {
        var lessCode = "\n    \n";
        lintCode(lessCode, function(count) {
            assert.equal(count, 0);
            done();
        });
    });

    it("should return 0 errors for code with empty output", function(done) {
        var lessCode = `
            @green: rgb(0, 200, 0);

            .mixin() {
                border: none;
            }

            .allGreen(@radius) {
                border-color: @green;
                color: @green;
            }
        `;

        lintCode(lessCode, function(count) {
            assert.equal(count, 0);
            done();
        });
    });

    it("should work with custom reporter functions", function(done) {
        var lessCode = `
            .has-abc-error {
                opacity: 0.8;
                color: red;
            }

            a#overqualified {
                font-weight: bold;
            }
        `;

        // Custom reporter that simply counts errors
        var errorCounter = 0;
        var reporter = function(errors) {
            errorCounter += errors.length;
        };

        lesshint("test.less", lessCode, { reporter: reporter }, function() {
            assert.equal(errorCounter, 2);
            done();
        });
    });

    it("should call out @imported files that cannot be parsed", function(done) {
        var lessCode = `
            @import "test/cannot-parse.less";
        `;

        var errors = [];
        var reporter = function(reportedErrors) {
            errors = errors.concat(reportedErrors);
        };

        lesshint("test.less", lessCode, { reporter: reporter }, function() {
            assert.equal(errors.length, 1);

            assert.equal(errors[0].file, "test.less");
            assert.equal(errors[0].error.line, 1);
            assert.equal(errors[0].error.character, 1);

            // Test the error message
            assert(errors[0].error.reason.indexOf("cannot-parse.less") > -1);
            assert(errors[0].error.reason.indexOf(".bold is undefined") > -1);

            done();
        });
    });
});
