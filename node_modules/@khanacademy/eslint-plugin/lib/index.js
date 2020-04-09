module.exports = {
    rules: {
        "flow-array-type-style": require("./rules/flow-array-type-style.js"),
        "flow-exact-props": require("./rules/flow-exact-props.js"),
        "flow-exact-state": require("./rules/flow-exact-state.js"),
        "flow-no-one-tuple": require("./rules/flow-no-one-tuple.js"),
        "imports-requiring-flow": require("./rules/imports-requiring-flow.js"),
        "jest-async-use-real-timers": require("./rules/jest-async-use-real-timers.js"),
        "react-no-method-jsx-attribute": require("./rules/react-no-method-jsx-attribute.js"),
        "react-no-subscriptions-before-mount": require("./rules/react-no-subscriptions-before-mount.js"),
        "react-svg-path-precision": require("./rules/react-svg-path-precision.js"),
    },
};
