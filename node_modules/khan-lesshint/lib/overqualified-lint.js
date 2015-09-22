/**
 * Tests that selectors are not overqualified (in the form of element.class or
 * element#id)
 */
var parser = require("postcss-selector-parser");

function overqualifiedLint(cssAST, sourceMap, options, callback) {
    var violations = [];

    cssAST.walkRules(function(rule) {
        var startIndex = rule.source.start;

        parser(function(selectors) {
            // A single `rule.selector` may consist of multiple selectors
            // separated by a comma
            selectors.each(function(selector) {
                // Local variables to keep track of the state of our selector
                // "part" (continguous CSS selector such as tag#id.class with
                // no combinators)
                var hasElement, hasId, hasClass;
                var part = "";

                // Loop through the individual "nodes" of the selector, which
                // represent single items such a tag ("p"), class (".error")
                // or combinator ("+")
                for (var node, i = 0; i < selector.nodes.length; i++) {
                    node = selector.nodes[i];

                    if (node.type === "combinator") {
                        // Reset the part and state variables
                        hasElement = hasId = hasClass = false;
                        part = "";
                    } else if (node.type === "tag") {
                        hasElement = true;
                        part += node.value;
                    } else if (node.type === "id") {
                        hasId = true;
                        part += "#" + node.value;
                    } else if (node.type === "class") {
                        hasClass = true;
                        part += "." + node.value;
                    }

                    // Check if the part contains an element AND either an id
                    // or class
                    if (hasElement && (hasId || hasClass)) {
                        var index = node.source.start;

                        // From the source map consumer, fetch the original
                        // position of where this extra class/id is defined
                        var lessIndex = sourceMap.originalPositionFor({
                            line: startIndex.line + index.line - 1,
                            column: startIndex.column + index.column - 1,
                        });

                        // Prevent @keyframes percentages from being reported
                        // as overqualified selectors
                        var isPercentage = /%$/.test(part);

                        // Ignore overqualified selectors from imported files
                        //
                        // TODO: We may want to do this at the index.js level
                        // if we add several more compiled-CSS linters
                        var isImportedRule = lessIndex.source !== "input";

                        if (!isPercentage && !isImportedRule) {
                            violations.push({
                                line: lessIndex.line,
                                character: lessIndex.column,
                                code: "E03",
                                reason:
                                    "Overqualified selector (" + part + ")",
                            });

                            // Only report one error per selector part,
                            // meaning div.class.extra will have one error
                            return;
                        }
                    }
                }
            });
        }).process(rule.selector);
    });

    // cssAST.walkRules accepts a callback to run on each node, but the
    // function as a whole is synchronous. Let's make this function async.
    process.nextTick(function() {
        callback(null, violations);
    });
}

module.exports = overqualifiedLint;
