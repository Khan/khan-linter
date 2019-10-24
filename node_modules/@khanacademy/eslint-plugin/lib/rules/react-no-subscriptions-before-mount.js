const message =
    "Subscriptions (eg. event listeners) should not be set before the " +
    "component has mounted. This is to avoid firing them on the server, " +
    "as well as to ensure compatibility with React 16.\n\n" +
    "Please consider moving this subscription to `componentDidMount`.";

const subscriptionNames = [
    "then",
    "catch",
    "addEventListener",
    "setTimeout",
    "setInterval",
];

const beforeMountMethods = ["constructor", "componentWillMount"];

//------------------------------------------------------------------------------
// Rule Definition
//------------------------------------------------------------------------------
module.exports = {
    meta: {
        docs: {
            // eslint-disable-next-line max-len
            description:
                "Avoid subscriptions in `constructor` and `componentWillMount`",
            category: "react",
            recommended: false,
        },
        schema: [],
    },
    create(context) {
        return {
            CallExpression(node) {
                // Is this a function (eg. 'setTimeout()'), or a method
                // (eg. 'window.setTimeout()')?
                const isMethod = node.callee.type === "MemberExpression";

                // Grab the function-call bit (setTimeout)
                const identifier = isMethod
                    ? node.callee.property
                    : node.callee;

                // Bail early if this identifier isn't forbidden.
                if (!subscriptionNames.includes(identifier.name)) {
                    return;
                }

                // Are we in one of the before-mount methods?
                // To answer this question, we need to find the ancestor
                // MethodDefinition.
                const ancestors = context.getAncestors(node.callee).reverse();
                const ancestorMethodDef = ancestors.find(
                    a => a.type === "MethodDefinition",
                );

                // If there _is_ no parent MethodDefinition, bail early.
                // This subsciption is just fine.
                if (!ancestorMethodDef) {
                    return;
                }

                // Check if this is one of the pre-mount methods.
                if (beforeMountMethods.includes(ancestorMethodDef.key.name)) {
                    return context.report({
                        node,
                        message,
                    });
                }

                // TODO (josh): We aren't currently checking for 'deep' subs.
                // For example, we aren't catching this:
                /*
                    class Whatever extends Component {
                        componentWillMount() {
                            this.fetchData();
                        }

                        fetchData() {
                            someApi.fetch().then(...);
                        }
                    }
                */
                // To do that, we need to find invocations of our ancestor
                // MethodDefinition, and see if it's called from within one
                // of the pre-mount methods.
                //
                // I haven't been able to figure out how to do this in a way
                // that doesn't seem like total overkill, so I'm punting on
                // this for now.
            },
        };
    },
    __message: message,
};
