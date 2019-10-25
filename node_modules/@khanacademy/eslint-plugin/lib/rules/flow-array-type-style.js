const message =
    "Shorthand syntax for array types can appear ambiguous.  " +
    "Please use the long-form: Array<>";

module.exports = {
    meta: {
        docs: {
            description: "Prefer Array<T> to T[]",
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
            ArrayTypeAnnotation(node) {
                if (configuration === "always") {
                    context.report({
                        fix(fixer) {
                            const type = node.elementType;
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
