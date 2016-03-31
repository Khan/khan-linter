/** Similar to eslint's built-in 'unix' mode, but the ruleId comes first. */

// This reporter is used within eslint, I don't know that it supports ES6-isms
/* eslint-disable no-var */

module.exports = function(results) {
    results.forEach(function(result) {
        result.messages.forEach(function(message) {
            var code = "W";
            if (message.fatal || message.severity === 2) {
                code = "E";
            }
            // eslint uses string id's.  The only requirement we have
            // is that they not include spaces.
            code = code + String(message.ruleId).replace(/ /g, "_");

            // <file>:<line>:<col>: <E|W><code> <msg>
            process.stdout.write(
                result.filePath + ":" +
                    (message.line || 0) + ":" + (message.column || 0) + ": " +
                    code + " " + message.message + "\n");
        });
    });
};
