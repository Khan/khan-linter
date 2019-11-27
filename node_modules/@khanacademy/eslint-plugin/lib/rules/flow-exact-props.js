const t = require("@babel/types");

const {
    isReactClassComponent,
    isReactFunctionalComponent,
} = require("../react-utils.js");

const maybeReport = (node, typeAnnotation, typeAliases, context) => {
    if (t.isGenericTypeAnnotation(typeAnnotation)) {
        const {name} = typeAnnotation.id;
        const alias = typeAliases.get(name);
        if (alias && !alias.right.exact) {
            const sourceCode = context.getSource();
            context.report({
                fix(fixer) {
                    const right = alias.right;
                    const rightText = sourceCode.slice(
                        right.range[0] + 1,
                        right.range[1] - 1,
                    );
                    const replacementText = `{|${rightText}|}`;

                    return fixer.replaceText(alias.right, replacementText);
                },
                node: alias,
                message: `"${name}" type should be exact`,
            });
        }
    }
};

module.exports = {
    meta: {
        docs: {
            description: "Prefer exact object type for react props",
            category: "flow",
            recommended: false,
        },
        fixable: "code",
    },

    create(context) {
        const configuration = context.options[0] || "never";
        const typeAliases = new Map();

        return {
            TypeAlias(node) {
                const ancestors = context.getAncestors();
                if (
                    t.isProgram(node.parent) &&
                    t.isObjectTypeAnnotation(node.right)
                ) {
                    typeAliases.set(node.id.name, node);
                }
            },
            ClassDeclaration(node) {
                if (isReactClassComponent(node)) {
                    const {superTypeParameters} = node;
                    if (t.isTypeParameterInstantiation(superTypeParameters)) {
                        const props = superTypeParameters.params[0];
                        maybeReport(node, props, typeAliases, context);
                    }
                }
            },
            ArrowFunctionExpression(node) {
                if (isReactFunctionalComponent(node)) {
                    const {typeAnnotation} = node.params[0];
                    if (t.isTypeAnnotation(typeAnnotation)) {
                        const props = typeAnnotation.typeAnnotation;
                        maybeReport(node, props, typeAliases, context);
                    }
                }
            },
        };
    },
};
