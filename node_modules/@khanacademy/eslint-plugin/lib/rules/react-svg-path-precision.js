const t = require("@babel/types");

module.exports = {
    meta: {
        docs: {
            description:
                "Ensure that SVG paths don't use too many decimal places",
            category: "react",
            recommended: false,
        },
        fixable: "code",
        schema: [
            {
                type: "object",
                properties: {
                    precision: {
                        type: "number",
                    },
                },
                additionalProperties: false,
            },
        ],
    },

    create(context) {
        let precision = 2;
        for (const option of context.options) {
            if (typeof option === "object") {
                if (option.hasOwnProperty("precision")) {
                    precision = Math.max(option.precision, 0);
                }
            }
        }
        const pattern = `\\d*\\.\\d{${precision},}\\d+`;
        const regex = new RegExp(pattern, "g");

        return {
            JSXAttribute(node) {
                if (
                    t.isJSXAttribute(node) &&
                    t.isJSXIdentifier(node.name, {name: "d"})
                ) {
                    if (
                        t.isJSXOpeningElement(node.parent) &&
                        t.isJSXIdentifier(node.parent.name, {name: "path"})
                    ) {
                        const d = node.value.value;

                        if (regex.test(d)) {
                            context.report({
                                fix(fixer) {
                                    const replacementText = d.replace(
                                        regex,
                                        match =>
                                            parseFloat(match).toFixed(
                                                precision,
                                            ),
                                    );

                                    return fixer.replaceText(
                                        node.value,
                                        `"${replacementText}"`,
                                    );
                                },
                                node,
                                message:
                                    "This path contains numbers with too many decimal places.",
                            });
                        }
                    }
                }
            },
        };
    },
};
