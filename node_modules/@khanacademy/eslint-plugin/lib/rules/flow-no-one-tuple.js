const message =
    "One-tuples can be confused with shorthand syntax for array types.  " +
    "Using Array<> avoids this confusion.";

module.exports = {
    meta: {
        docs: {
            description: "Disallow one-tuple",
            category: "flow",
            recommended: false,
        },
        fixable: "code",
        schema: [
            {
                enum: ["always", "never"],
            },
        ],
    },

    create(context) {
        const configuration = context.options[0] || "never";
        const sourceCode = context.getSource();

        return {
            TupleTypeAnnotation(node) {
                if (configuration === "always" && node.types.length === 1) {
                    context.report({
                        fix(fixer) {
                            const type = node.types[0];
                            const typeText = sourceCode.slice(...type.range);
                            const replacementText = `Array<${typeText}>`;

                            return fixer.replaceText(node, replacementText);
                        },
                        node: node,
                        message: message,
                    });
                }
            },
        };
    },

    __message: message,
};
