// This set of rules is a conservative list that every repo should
// have no problem satisfying.  Individual repos will want their own
// config file that has a larger set of rules.  See
//    https://github.com/cjoudrey/graphql-schema-linter#built-in-rules
// for the complete set of rules.  See
//    https://github.com/cjoudrey/graphql-schema-linter#built-in-rules
// for different ways to name/format your config file.

module.exports = {
    "rules": [
        "deprecations-have-a-reason",
        "enum-values-all-caps",
        "fields-are-camel-cased",
        "input-object-values-are-camel-cased",
        "types-are-capitalized",
    ]
};
