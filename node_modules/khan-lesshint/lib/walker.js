/**
 * A series of utility functions for walking the Less AST.
 */
var async = require("async");


/**
 * Walk through the nodes of the AST and run a callback on each node with a
 * "selectors" field, representing a proper Less rule like "tag { ... }"
 *
 * @param {object} node - the Less AST node
 * @param {function} nodeCallback - an async function to run on each node that
 *      accepts the node, the current traversal depth, and a callback
 * @param {function} doneCallback - a callback to run when the node has been
 *      traversed
* @param {boolean?} traverseRoots - whether to follow nested roots, which
 *      appear for @imported files (default: false)
 * @param {number?} depth - the depth of the traversal (default: 0)
 */
function walk(node, nodeCallback, doneCallback, traverseRoots, depth) {
    if (depth === undefined) {
        depth = 0;
    }

    var callbacks = [];

    callbacks.push(function(done) {
        nodeCallback(node, depth, done);
    });

    // Recursively check nested rules
    if (node.rules) {
        node.rules.forEach(function(rule) {
            // Queue up another call to walkRules, this time assigning the
            // `doneCallback` to the `done` as required by `async.parallel`
            callbacks.push(function(done) {
                walk(rule, nodeCallback, done, traverseRoots, depth + 1);
            });
        });
    }

    if (traverseRoots && node.root) {
        callbacks.push(function(done) {
            walk(node.root, nodeCallback, done, traverseRoots, depth + 1);
        });
    }

    // Run the callbacks in parallel
    return async.parallel(callbacks, doneCallback);
}


// A specialized version of walk that only invokes a callback on nodes with
// a "selectors" field. This walks the colloquial "rules" of the structure,
// which represent Less declarations such as "a.active { ... }"
function walkRules(node, nodeCallback, doneCallback, traverseRoots, depth) {
    walk(node, function(node, depth, done) {
        // While we will hit every "rule" as defined by the Less AST, we only
        // concern ourselves with actual Less rules (e.g. "a { ... }"), which
        // have a "selectors" field.
        if (node.selectors) {
            nodeCallback(node, depth, done);
        } else {
            // Otherwise, just invoke the `done` callback right away
            done();
        }
    }, doneCallback, traverseRoots, depth);
}


module.exports = {
    walk: walk,
    walkRules: walkRules,
};
