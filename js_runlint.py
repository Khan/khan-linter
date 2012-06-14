#!/usr/bin/env python

import optparse
import sys

import closure_linter.checker
import closure_linter.error_fixer
import closure_linter.gjslint


USAGE = """%prog [options] [file1] [file2]...

Run a JavaScript linter on one or more files.

This will invoke the linter, and optionally attempt to auto-fix
style-violations on the specified JavaScript files.
"""


def check_files(filenames):
    fake_args = [closure_linter.gjslint.__file__, '--nobeep'] + filenames
    return closure_linter.gjslint.main(argv=fake_args) == 0


def fix_files(filenames):
    style_checker = closure_linter.checker.JavaScriptStyleChecker(
        closure_linter.error_fixer.ErrorFixer())

    for filename in filenames:
        style_checker.Check(filename)
    return 0


def main():
    parser = optparse.OptionParser(USAGE)
    parser.add_option('--autofix', action='store_true', default=False,
                      help='Whether or not to autofix')
    options, args = parser.parse_args()
    if options.autofix:
        return fix_files(args)
    else:
        return check_files(args)


if __name__ == '__main__':
    sys.exit(main())
