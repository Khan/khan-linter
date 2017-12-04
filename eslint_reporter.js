/** Similar to eslint's built-in 'unix' mode, but the ruleId comes first. */
const utf8 = require("utf8");

/**
 * Given a character offset within a string, return the byte offset of the
 * corresponding character, assuming we were to encode the string as UTF-8.
 */
function convertCharOffsetToByteOffset(str, charOffset) {
    // Get the substring preceding the character offset, encode it as UTF-8,
    // and count the "byte" length.
    return utf8.encode(str.substr(0, charOffset)).length;
}

module.exports = function(results) {
    results.forEach(function(result) {
        const source = result.source || result.output;
        if (!source) {
            // No errors/warnings. Short-circuit.
            return;
        }

        const sourceLines = source.split("\n");
        result.messages.forEach(function(message) {
            let code = "W";
            if (message.fatal || message.severity === 2) {
                code = "E";
            }
            // eslint uses string id's.  The only requirement we have
            // is that they not include spaces.
            code = code + String(message.ruleId).replace(/ /g, "_");

            // khan-linter wants the byte column, not character column, of the
            // error. (This is because `arc lint` wants the byte column, not
            // the character column.) So, convert from characters to bytes.
            // Additionally, an error's "column" is one-indexed, but the
            // conversion function's API makes more sense zero-indexed, so we
            // convert between "column" and "offset" by subtracting/adding 1.
            //
            // NOTE(mdr): This trick only works if the source file was UTF-8
            //     encoded. If the file were instead UTF-16 encoded, for
            //     example, then this would yield incorrect byte offsets. But
            //     UTF-8 files seems like a strong assumption for our codebase.
            const sourceLine = sourceLines[message.line - 1];
            const charColumn = message.column || 0;
            const charOffset = charColumn - 1;
            const byteOffset = convertCharOffsetToByteOffset(
                sourceLine, charOffset);
            const byteColumn = byteOffset + 1;

            // <file>:<line>:<col>: <E|W><code> <msg>
            process.stdout.write(
                result.filePath + ":" +
                    (message.line || 0) + ":" + byteColumn + ": " +
                    code + " " + message.message + "\n");
        });
    });
};
