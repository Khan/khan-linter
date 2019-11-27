const t = require("@babel/types");

const isReactClassComponent = node => {
    if (t.isClassDeclaration(node)) {
        const {superClass} = node;
        if (t.isMemberExpression(superClass)) {
            const {object, property} = superClass;
            if (
                t.isIdentifier(object, {name: "React"}) &&
                t.isIdentifier(property, {name: "Component"})
            ) {
                return true;
            }
        }
    }
    return false;
};

const isReactFunctionalComponent = node => {
    if (t.isArrowFunctionExpression(node)) {
        if (
            node.params.length === 1 &&
            t.isIdentifier(node.params[0], {name: "props"})
        ) {
            return true;
        }
    }
};

module.exports = {
    isReactClassComponent: isReactClassComponent,
    isReactFunctionalComponent: isReactFunctionalComponent,
};
