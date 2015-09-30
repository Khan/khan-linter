/**
 * Tests that rules are not nested too deeply.
 */
var indexToLocation = require("./index-to-location");
var walkRules = require("./walker").walkRules;

var NESTING_LIMIT = 4;

function nestingLint(code, ast, options, callback) {
    var violations = [];

    walkRules(ast, function(rule, depth, done) {
        if (depth > NESTING_LIMIT) {
            // Fetch the character index of this rule, which is the index of
            // the first element (i.e. "p") of the first selector
            // (i.e. ".first, .second { }").
            var index = rule.selectors[0].elements[0].index;

            // Nested @media queries create element fields with no index.
            // Nesting these doesn't contribute to specificity, so we'll just
            // ignore them.
            if (index === undefined) {
                return done();
            }

            var location = indexToLocation(code, index);

            violations.push({
                line: location.line,
                character: location.column,
                code: "E02",
                reason: "Nesting limit (" + NESTING_LIMIT + ") exceeded",
            });
        }

        done();
    }, function(err) {
        if (err) {
            callback(err);
        } else {
            callback(null, violations);
        }
    });
}

module.exports = nestingLint;
