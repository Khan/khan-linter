/**
 * Tests that color values are backed by a variable
 */
var async = require("async");
var intersection = require("lodash.intersection");
var parseColor = require("parse-color");
var path = require("path");
var traverse = require("traverse");

var indexToLocation = require("./index-to-location");
var walk = require("./walker").walk;

// Extract color values from a given rule
function getColorValues(rule) {
    var colors = [];

    // Scan the `rule.value` subtree for color values, and add them to the
    // colors array as 4-arrays (red, green, blue, and alpha).
    traverse(rule.value).forEach(function(node) {
        // Detect #RGB and #RRGGBB values, which are leaves in the tree.
        if (this.isLeaf) {
            if (/(#[0-9A-Fa-f]{3,6})/.test(node)) {
                // TODO: Can we point to this #?
                colors.push(parseColor(RegExp.$1).rgba);
            }
        } else {
            try {
                function getArgValue(arg) {
                    // Arguments are listed in the form:
                    //   {"args": [{"value": [{"value": X}]}, ...]}
                    var value = arg.value[0].value;

                    // If they're not, such as mathematical arguments pass to
                    // rgb() like "10 * 4", throw an error that we'll catch
                    // and ignore.
                    if (Number.isNaN(value) || !Number.isFinite(value)) {
                        throw new Error(
                            "Non-numeric value found for argument");
                    } else {
                        return value;
                    }
                }

                // Detect rgb() functions
                if (node.name === "rgb") {
                    var rgb = node.args.map(getArgValue);
                    // Concat an alpha value of 1
                    colors.push(rgb.concat([1]));

                // Detect rgba() functions
                } else if (node.name === "rgba") {
                    var rgba = node.args.map(getArgValue);
                    colors.push(rgba);

                // Detect {"rgb": [...], "alpha": X} nodes, which appear when
                // colors are passed as an argument to functions like mix()
                // and lighten()
                } else if (node.rgb) {
                    var rgba = node.rgb.concat([node.alpha]);
                    colors.push(rgba);
                }
            } catch (e) {
                // We assume the structure of rgb()/rgba() nodes. Which is the
                // case for normal usage such as rgb(0, 0, 0). Edge cases such
                // as rgb(10 + 20, 0, 0) we do not account for.
                //
                // Catch any exceptions and ignore them.
            }
        }
    });

    return colors;
}

// Walk the AST and store references to any color variables
function readColorVariables(root, reportColorVariable, callback) {
    walk(root, function(rule, depth, done) {
        // rule.variable might be a function
        if (rule.variable === true) {
            getColorValues(rule).forEach(function(color) {
                reportColorVariable(rule, color);
            });
        }

        done();
    }, callback, true);     // true => walk @imported files too
}

// Walk the AST and report any inline colors
function findInlineColors(root, reportInlineColor, callback) {
    walk(root, function(rule, depth, done) {
        // Ignore variables
        if (!rule.variable) {
            // Extract the colors from the rule and invoke
            // `reportInlineColor()` on each one.
            getColorValues(rule).forEach(function(inlineColor) {
                reportInlineColor(inlineColor, rule.index);
            });
        }

        done();
    }, callback);
}

// A very naive color distance formula, using the euclidean distance in
// 4-space
function euclideanColorDistance(colorA, colorB) {
    return Math.sqrt(
        // RGB
        Math.pow(colorA[0] - colorB[0], 2) +
        Math.pow(colorA[1] - colorB[1], 2) +
        Math.pow(colorA[2] - colorB[2], 2) +

        // Alpha, multiplied by 255 to give it the same importance as an
        // individual channel value
        Math.pow(colorA[3] * 255 - colorB[3] * 255, 2)
    );
}

// Find the closest match to a given color from a list of colors as extracted
// from color variables
function findClosestColor(inlineColor, storedColors) {
    var closestColor, closestColorDistance;

    // Cycle through the stored colors, keeping track of the closest color
    // via a 4-space euclidean distance, and its distance
    for (var i = 0; i < storedColors.length; i++) {
        var distance = euclideanColorDistance(
            storedColors[i].color, inlineColor);

        if (closestColorDistance === undefined ||
                distance < closestColorDistance) {
            closestColorDistance = distance;
            closestColor = storedColors[i];
        }

        // Break if we find an exact color
        if (closestColorDistance === 0) {
            break;
        }
    }

    return {
        color: closestColor,
        distance: closestColorDistance,
    };
}

function colorVariableLint(code, ast, options, callback) {
    var ignoreDirectories = options.ignore || [];
    var storedColors = [];
    var violations = [];

    // Run two tasks in series
    async.series([
        // First, read (and store) any color variables in the AST. We'll use
        // these values to suggest colors close to the ones found inline.
        function(done) {
            readColorVariables(ast, function(rule, color) {
                var file = null;
                var currentDirectory = rule.currentFileInfo.currentDirectory;

                // currentDirectory will be non-empty if we have traversed
                // into another file
                if (currentDirectory) {
                    file = rule.currentFileInfo.filename;

                    // Determine if the current directory contains any of the
                    // directories whose color variables we should ignore.
                    //
                    // TODO: Handle ignoring directories in the walker module
                    // to prevent even looking in them.
                    if (intersection(
                            currentDirectory.split(path.sep),
                            ignoreDirectories).length) {
                        return;
                    }
                }

                storedColors.push({
                    name: rule.name,
                    index: rule.index,
                    file: file,
                    color: color,
                });
            }, done);
        },

        // Then, scan the AST for inline colors, and attempt to suggest a
        // matching color backed by a variable.
        function(done) {
            // TODO: Use the inline color as it's written, instead of its
            // conversion to rgba.
            findInlineColors(ast, function(inlineColor, index) {
                var location = indexToLocation(code, index);

                var rgba = "rgba(" + inlineColor.join(",") + ")";
                var hex = parseColor(rgba).hex;
                var message = "Inline color " + hex + " found";

                // See if there is a matching color from our stored colors.
                // A distance of "35" is chosen somewhat arbitrarily.
                var match = findClosestColor(inlineColor, storedColors);
                if (match && match.distance < 35) {
                    // Display where we can find this variable, either the
                    // filename of where its defined, or the line number if
                    // the variable is in the current file
                    //
                    // TODO: Display a line number for external files as well
                    var matchIndex = match.color.index;
                    var whereToFind = (match.color.file) ?
                        match.color.file :
                        "line " + indexToLocation(code, matchIndex).line;

                    message += ". Did you mean " + match.color.name +
                        " from " + whereToFind + "?";
                }

                violations.push({
                    line: location.line,
                    character: location.column,
                    code: "E04",
                    reason: message,
                });
            }, done);
        },
    ], function(err) {
        callback(err, violations);
    });
}

module.exports = colorVariableLint;
