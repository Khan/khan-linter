#!/usr/bin/env node
/* eslint-disable no-console, max-len */
//
// Update eslint-disable messages
//
// usage (from khan/webapp):
//   ../devtools/khan-linter/update_eslint_disable_lines.js ./javascript
//
// The updated message will appear the top of the file and look like:
//   /* eslint-disable ... */
//   /* TODO(csilvers): fix these lint errors ... */
//   /* To fix, remove an entry above, run ka-lint, and fix the errors. */
//
// If the file include the '// @flow' on any lines, we add it back in below
// the updated message.
//
// TODO(kevinb): add --todo_target option to control the name in the TODO
// We want to avoid changing the name in messages where the list of rules
// hasn't changed so we'll want to parse existing eslint-disable lines.
//
const eslint = require('eslint');
const fs = require('fs');
const path = require('path');
const process = require('process');

/**
 * Recursively walk the given path, and add any relevant .js or .jsx files to
 * the given `filelist` array. `filelist` is updated in-place.
 */
const getFilePaths = (dirOrFile, filelist) => {
    if (fs.statSync(dirOrFile).isDirectory()) {
        // It's a directory!
        const dir = dirOrFile;

        // Skip node_modules.
        if (dir === 'node_modules') {
            return;
        }

        // Recurse into the directory's contents.
        const childFileNames = fs.readdirSync(dir);
        for (const childFileName of childFileNames) {
            const childFilePath = path.join(dir, childFileName);
            getFilePaths(childFilePath, filelist);
        }
    } else {
        // It's a file!
        const file = dirOrFile;

        // Skip symbolic links.
        if (fs.lstatSync(file).isSymbolicLink()) {
            return;
        }

        // Skip non-JS and non-JSX files.
        if (!/\.jsx?$/.test(file)) {
            return;
        }

        // Add the file to the list of files to update.
        filelist.push(file);
    }
};


if (process.argv.length < 3) {
    console.warn('usage: update_lint_message.js file_or_dir_1 [file_or_dir_2] [...]');
    process.exit(1);
}

const filePaths = [];
for (let i = 2; i < process.argv.length; i++) {
    getFilePaths(process.argv[i], filePaths);
}

const FIX_TEXT = '/* To fix, remove an entry above, run ka-lint, and fix errors. */';
const TODO_TEXT = '/* TODO(csilvers): fix these lint errors (http://eslint.org/docs/rules): */';

const cli = new eslint.CLIEngine({
    configFile: path.join(__dirname, "eslintrc"),
});

const total = filePaths.length;

filePaths.forEach((filePath, index) => {
    const originalSource = fs.readFileSync(filePath, {encoding: 'utf-8'});
    const originalLines = originalSource.split('\n');

    let usesFlow = false;

    // Remove existing lint message.
    let inHeader = true;
    const filteredLines = originalLines.filter((line) => {
        if (!inHeader) {
            return true;
        } else if (line.startsWith('/* eslint-disable ')) {
            return false;
        } else if (line === TODO_TEXT) {
            return false;
        } else if (line.startsWith('/* To fix, remove an entry above')) {
            return false;
        } else if (line.startsWith('// @flow')) {
            usesFlow = true;
            return false;
        } else if (line.match(/^\s*$/)) {
            // Empty lines immediately below the header count as part of the
            // header, and are removed.
            return false;
        } else {
            inHeader = false;
            return true;
        }
    });

    const report = cli.executeOnText(filteredLines.join('\n'));
    const result = report.results[0];

    const rules = {};
    result.messages.forEach((message) => {
        // TODO(kevinb): check that the ruleIds match for @Nolint(ruleId)
        // The source line for a max-lines violation is the first line of the
        // file, but the violation itself applies to the whole file so ignore
        // @Nolint in that situation.
        if (/\@Nolint/.test(message.source) && message.ruleId !== 'max-lines') {
            return;
        } else if (message.ruleId === 'max-len' &&
            /require\(['"][^'"]+['"]\)| from ['"]/.test(message.source)) {
            return;
        } else if (message.ruleId === 'max-len' &&
            /\.fixture\.jsx?$/.test(filePath)) {
            return;
        } else {
            rules[message.ruleId] = true;
        }
    });
    const violations = Object.keys(rules).sort();

    const headerLines = [];
    if (violations.length > 0) {
        headerLines.push(`/* eslint-disable ${violations.join(', ')} */`);
        headerLines.push(TODO_TEXT);
        headerLines.push(FIX_TEXT);
    }
    if (usesFlow) {
        headerLines.push('// @flow');
    }

    const updatedLines = headerLines.concat(filteredLines);
    const updatedSource = updatedLines.join('\n');

    if (originalSource !== updatedSource) {
        fs.writeFileSync(filePath, updatedSource, {encoding: 'utf-8'});
    }

    process.stdout.write(`progress: ${index + 1} of ${total}\r`);
});

console.log('');
