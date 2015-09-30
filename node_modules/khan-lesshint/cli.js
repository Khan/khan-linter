#!/usr/bin/env node
var async = require("async");
var fs = require("fs");
var path = require("path");
var argv = require("minimist")(process.argv.slice(2));

var lesshint = require("./");
var files = argv._;

if (!files.length) {
    console.log("USAGE: lesshint [file ...] [--reporter module]");
    process.exit(1);
}

var reporter;
if (argv.reporter) {
    // Attempt to require the reporter as specified from the command line
    reporter = require(argv.reporter).reporter;
}

var options = {
    ignore: ["third_party"],
    reporter: reporter,
};

var callbackSeries = [];
files.forEach(function(file) {
    var code = fs.readFileSync(file, "utf-8");

    callbackSeries.push(function(next) {
        // chdir() into the file's directory to make relative @import
        // statements work
        var cwd = process.cwd();
        process.chdir(path.dirname(file));

        // Lint the file, sending a callback that will report the number of
        // errors to `async.series`
        lesshint(file, code, options, function(count) {
            // chdir back to the previous cwd
            process.chdir(cwd);
            next(null, count);
        });
    });
});

async.series(callbackSeries, function(err, counts) {
    var totalErrors = counts.reduce(function(a, b) {
        return a + b;
    }, 0);

    if (totalErrors) {
        process.exit(1);
    } else {
        process.exit(0);
    }
});
