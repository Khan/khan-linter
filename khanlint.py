#!/usr/bin/env python

# Pre-commit checks to check for readability.
# Add to .hgrc to use:
#
# [hooks]
# pretxncommit.lint = /path/to/this/file.py
#
# If a forced commit is required, set the environment variable
# FORCE_COMMIT to 1 prior to calling 'hg commit' (there doesn't
# seem to be a way to pass args to a pretxncommit script otherwise)

import commands
import os
import re
import sys

from closure_linter import gjslint

def check_file(filename):
    fake_args = [gjslint.__file__, '--nobeep', filename]
    return gjslint.main(argv=fake_args) == 0

def main():
    """ Runs a Mercurial pre-commit check to ensure all affected files adhere
    to readability guidelines.

    Currently only enforces JavaScript files.
    """
    failed = []

    blacklisted = set([l.strip() for l in open('lint-blacklist.txt', 'r')])

    # Go through all modified or added files.
    for line in commands.getoutput('hg status -a -m --change tip').split('\n'):
        # each line of the format "M path/to/filename.js"
        status, filename = line.split(' ')
        if not filename.endswith('.js'):
            continue

        if status == 'M' and filename in blacklisted:
            # Blacklisted legacy file - don't lint.
            continue
        if not check_file(filename):
            failed.append(filename)

    if failed:
        # save the commit message so we don't need to retype it
        commands.getoutput('hg tip --template "{desc}" > .hg/commit.save')
        print >> sys.stderr, (("\n\033[01;31m%s files failed linting\033[0m" +
                              "\nCommit message saved to .hg/commit.save") %
                              len(failed))
        sys.exit(1)

if __name__ == '__main__':
    force = os.getenv('FORCE_COMMIT')
    if force is None or force.lower() not in ['1', 'true']:
        main()
