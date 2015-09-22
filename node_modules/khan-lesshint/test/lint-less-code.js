/**
 * Utility function to parse less code, run a particular linter, and report
 * the violations
 */
var async = require("async");
var less = require("less");

function lintLessCode(linter) {
    // After accepting a linter, return a function that can be invoked with
    // some Less code, and a callback function
    return function(code, callback, options) {
        options = options || {};

        // Waterfall two async functions into each other, the less parsing
        // step, followed by the linting step
        async.waterfall([
            function(next) {
                // Instead of simply putting `next` as the last argument, we
                // pass a function that calls `next` with exactly `err` and
                // `ast`. Otherwise, the next function in the waterfall would
                // need to specify whatever else `less.parse` invokes its
                // callback with.
                less.parse(code, function(err, ast) {
                    next(err, ast);
                });
            },

            function(ast, next) {
                linter(code, ast, options, next);
            },
        ], function(err, violations) {
            // Throwing errors does not have the desired effect in mocha
            // land, so we'll print the error and exit with a
            if (err) {
                throw err;
            }

            // Invoke the callback with just the violations
            callback(violations);
        });
    };
}

module.exports = lintLessCode;
