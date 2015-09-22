#!/usr/bin/env node
var fs = require("fs");
var path = require("path");
var argv = require("minimist")(process.argv.slice(2));

var lesshint = require("./");
var file = argv._[0];

if (!file) {
    console.log("USAGE: lesshint [file] [--reporter module]");
    process.exit(1);
}

var code = fs.readFileSync(file, "utf-8");
var reporter;
if (argv.reporter) {
    // Attempt to require the reporter as specified from the command line
    reporter = require(argv.reporter).reporter;
}

var options = {
    ignore: ["third_party"],
    reporter: reporter,
};

// chdir() into the file's directory to make relative @import statements work
process.chdir(path.dirname(file));
lesshint(file, code, options);
