module.exports = {
    meta: {
        docs: {
            description: "Ensure that methods aren't used as jsx attributes",
            category: "react",
            recommended: false,
        },
        schema: [],
    },

    create(context) {
        const methods = new Map();
        const classProperties = new Map();

        return {
            ClassDeclaration(node) {
                for (const child of node.body.body) {
                    if (
                        child.type === "ClassProperty" &&
                        child.key.type === "Identifier"
                    ) {
                        classProperties.set(child.key.name, child);
                    } else if (
                        child.type === "MethodDefinition" &&
                        child.kind === "method" &&
                        child.key.type === "Identifier"
                    ) {
                        methods.set(child.key.name, child);
                    }
                }
            },
            "ClassDeclaration:exit"(node) {
                for (const child of node.body.body) {
                    if (
                        child.type === "ClassProperty" &&
                        child.key.type === "Identifier"
                    ) {
                        classProperties.delete(child.key.name);
                    } else if (
                        child.type === "MethodDefinition" &&
                        child.kind === "method" &&
                        child.key.type === "Identifier"
                    ) {
                        methods.delete(child.key.name);
                    }
                }
            },
            JSXAttribute(node) {
                const {value} = node;
                // value doesn't exist for boolean shorthand attributes
                if (value && value.type === "JSXExpressionContainer") {
                    const {expression} = node.value;
                    if (expression.type === "MemberExpression") {
                        const {object, property} = expression;
                        if (
                            object.type === "ThisExpression" &&
                            property.type === "Identifier"
                        ) {
                            const {name} = property;
                            if (methods.has(name)) {
                                context.report({
                                    node: methods.get(name),
                                    message:
                                        "Methods cannot be passed as props, use a class property instead.",
                                });
                            }
                        }
                    }
                }
            },
        };
    },
};
