/**
 * Tests the indexToLocation module
 */
var assert = require("assert");
var indexToLocation = require("../lib/index-to-location");

describe("Index to location", function() {
    var code =
        "01234\n" +
        "56789\n" +
        "01234\n" +
        "56789";

    it("should correctly point to the first line", function() {
        // First character
        assert(1 === indexToLocation(code, 0).line);
        assert(1 === indexToLocation(code, 0).column);

        // Last character
        assert(1 === indexToLocation(code, 4).line);
        assert(5 === indexToLocation(code, 4).column);
    });

    it("should correctly point to subsequent lines", function() {
        assert(2 === indexToLocation(code, 6).line);
        assert(3 === indexToLocation(code, 12).line);
        assert(4 === indexToLocation(code, 18).line);
    });

    it("should interpret newline characters on the next line", function() {
        // Newline characters are on the next line, at the 1st column
        assert(2 === indexToLocation(code, 5).line);
        assert(1 === indexToLocation(code, 5).column);

        assert(3 === indexToLocation(code, 11).line);
        assert(1 === indexToLocation(code, 5).column);
    });

    it("should cap off extreme values", function() {
        assert(1 === indexToLocation(code, -1).line);
        assert(1 === indexToLocation(code, -1).column);

        assert(1 === indexToLocation(code, -1000).line);
        assert(1 === indexToLocation(code, -1000).column);

        assert(4 === indexToLocation(code, 1000).line);
        assert(1 === indexToLocation(code, 1000).column);
    });
});
