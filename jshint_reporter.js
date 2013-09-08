/* jshint node: true */

module.exports = {
    reporter: function (res) {
        res.forEach(function (r) {
            var file = r.file;
            var err = r.error;

            // <file>:<line>:<col>: <E|W><code> <msg>
            process.stdout.write(
                    file + ":" +
                    err.line + ":" + err.character + ": " +
                    err.code + " " + err.reason + "\n");
        });
    }
};
