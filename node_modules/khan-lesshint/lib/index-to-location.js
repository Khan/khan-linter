/**
 * Convert a character index to a location, represented by an object with a
 * line and column.
 */
function indexToLocation(code, index) {
    var lines = code.split("\n");

    for (var lineNo = 0; lineNo < lines.length; lineNo++) {
        if (index < lines[lineNo].length) {
            return {
                // plus 1 to be 1-indexed
                line: lineNo + 1,
                column: Math.max(1, index + 1),
            };
        } else {
            // Substract the number of characters in the line, plus 1 for "\n"
            index -= lines[lineNo].length + 1;
        }
    }

    return {
        line: lines.length,
        column: 1,
    };
}

module.exports = indexToLocation;
