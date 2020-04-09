const t = require("@babel/types");

/**
 * Find and return the `beforeEach` call node inside a describe block if one exists.
 *
 * @param {CallExpression} describeCall the node for a call to `describe`.
 */
const findBeforeEach = describeCall => {
    const funcExpr = describeCall.arguments[1];
    if (
        funcExpr &&
        (t.isArrowFunctionExpression(funcExpr) ||
            t.isFunctionExpression(funcExpr)) &&
        t.isBlockStatement(funcExpr.body)
    ) {
        for (const stmt of funcExpr.body.body) {
            if (t.isExpressionStatement(stmt)) {
                const expr = stmt.expression;
                if (
                    t.isCallExpression(expr) &&
                    t.isIdentifier(expr.callee, {name: "beforeEach"})
                ) {
                    return expr;
                }
            }
        }
    }
    return null;
};

/**
 * Determine if a `beforeEach` or `it` block has called jest.useRealTimers().
 *
 * NOTE: The call cannot be inside a control flow statement.
 *
 * @param {CallExpression} call the node for a call to `beforeEach` or `it`.
 * @param {number} closureArgIndex the arg index of the closure passed to `call`.
 */
const usesRealTimers = (call, closureArgIndex = 0) => {
    if (call == null) {
        return false;
    }
    const funcExpr = call.arguments[closureArgIndex];

    if (
        funcExpr &&
        (t.isArrowFunctionExpression(funcExpr) ||
            t.isFunctionExpression(funcExpr)) &&
        t.isBlockStatement(funcExpr.body)
    ) {
        for (const stmt of funcExpr.body.body) {
            if (t.isExpressionStatement(stmt)) {
                const expr = stmt.expression;
                if (
                    t.isCallExpression(expr) &&
                    t.isMemberExpression(expr.callee)
                ) {
                    const {object, property} = expr.callee;
                    if (
                        t.isIdentifier(object, {name: "jest"}) &&
                        t.isIdentifier(property, {name: "useRealTimers"})
                    );
                    return true;
                }
            }
        }
    }
    return false;
};

const isAsync = itCall => {
    return (
        t.isArrowFunctionExpression(itCall.arguments[1], {async: true}) ||
        t.isFunctionExpression(itCall.arguments[1], {async: true})
    );
};

module.exports = {
    meta: {
        docs: {
            description:
                "Require a call to jest.useRealTimers() before or in all async tests.",
            category: "react",
            recommended: false,
        },
    },

    create(context) {
        const stack = [];

        return {
            CallExpression(node) {
                if (t.isIdentifier(node.callee, {name: "describe"})) {
                    stack.push(usesRealTimers(findBeforeEach(node), 0));
                } else if (
                    t.isIdentifier(node.callee, {name: "it"}) &&
                    isAsync(node)
                ) {
                    // an `it` should always be inside a `describe`
                    if (stack.length > 0) {
                        if (!stack.some(Boolean) && !usesRealTimers(node, 1)) {
                            context.report({
                                node,
                                message:
                                    "Async tests require jest.useRealTimers().",
                            });
                        }
                    }
                }
            },
            "CallExpression:exit"(node) {
                if (t.isIdentifier(node.callee, {name: "describe"})) {
                    stack.pop();
                }
            },
        };
    },
};
