/**
 * Tests that Less properties are listed in alphabetical order.
 */
var indexToLocation = require("./index-to-location");
var walkRules = require("./walker").walkRules;

function abcLint(code, ast, options, callback) {
    var violations = [];

    walkRules(ast, function(rule, depth, done) {
        var lastName = "";
        var maybeDecl;

        // `rule.rules` corresponds to _all_ of the things inside of the rule,
        // including declarations (i.e. "color: red"), variables, or even
        // nested rules.
        for (var i = 0; i < rule.rules.length; i++) {
            maybeDecl = rule.rules[i];

            // TODO: Check the order of variables as well
            if (maybeDecl.variable) {
                continue;
            }

            // Declarations have a name field, which is a single-item array
            // containining { value: "someName" }.
            if (maybeDecl.name && maybeDecl.name.length) {
                // Check that the declaration names appear alphabetically
                if (maybeDecl.name[0].value < lastName) {
                    var location = indexToLocation(code, maybeDecl.index);

                    violations.push({
                        line: location.line,
                        character: location.column,
                        code: "E01",
                        reason: "Property \"" + maybeDecl.name[0].value +
                            "\" is not listed alphabetically",
                    });

                    // Only report once per rule
                    return done();
                } else {
                    lastName = maybeDecl.name[0].value;
                }
            }
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

module.exports = abcLint;
