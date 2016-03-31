/* jshint node: true */

// This reporter is used within eslint, I don't know that it supports ES6-isms
/* eslint-disable no-var */

module.exports = {
    reporter: function(res) {
        res.forEach(function(r) {
            var file = r.file;
            var err = r.error;

            // <file>:<line>:<col>: <E|W><code> <msg>
            process.stdout.write(
                    file + ":" +
                    err.line + ":" + err.character + ": " +
                    err.code + " " + err.reason + "\n");
        });
    },
};
