#!/usr/bin/env node
var transform = require("react-tools").transform;

process.stdin.resume();
process.stdin.setEncoding("utf-8");

var js = "";
process.stdin.on("data", function(data) {
    js += data;
});
process.stdin.on("end", function() {
    process.stdout.write(transform(js));
});
