/**
 * Entry point configuration for the react-native animation linter.
 */

const allRules = {
  "must-tear-down-animations": require("./lib/rules/must-tear-down-animations")
};

// Set up rules to trigger errors (rather than warnings)
function configureAsError(rules) {
  const result = {};
  for (const key in rules) {
    if (!rules.hasOwnProperty(key)) {
      continue;
    }
    result["react-native-animation-linter/" + key] = 2;
  }
  return result;
}

module.exports = {
  rules: allRules,
  configs: {
    // default "all" configuration treats all rules as errors
    all: {
      parserOptions: {
        ecmaFeatures: {
          jsx: true
        }
      },
      rules: configureAsError(allRules)
    }
  }
};
