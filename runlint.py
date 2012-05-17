#!/usr/bin/env python

import optparse
import sys

from closure_linter import checker
from closure_linter import error_fixer
from closure_linter import gjslint


USAGE = """%prog [options] [file1] [file2]...

Run a JavaScript linter on one or more files.

This will invoke the linter, and optionally attempt to auto-fix style-violations on the specified JavaScript files.
"""


def check_files(filenames):
    fake_args = [gjslint.__file__, '--nobeep'] + filenames
    return gjslint.main(argv=fake_args) == 0


def fix_files(filenames):
    style_checker = checker.JavaScriptStyleChecker(error_fixer.ErrorFixer())

    for filename in filenames:
        style_checker.Check(filename)
    return 0


def main():
    parser = optparse.OptionParser(USAGE)
    parser.add_option('--autofix',
                      dest='autofix',
                      action='store_true',
                      default=False,
                      help='Whether or not to autofix')
    options, args = parser.parse_args()
    if options.autofix:
        return fix_files(args)
    else:
        return check_files(args)


if __name__ == '__main__':
    sys.exit(main())
