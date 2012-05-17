#!/usr/bin/env python

# Pre-commit checks to check for readability.

from closure_linter import gjslint
from subprocess import Popen, PIPE

import commands
import os
import re
import sys


def check_file(filename):
    fake_args = [gjslint.__file__, '--nobeep', filename]
    return gjslint.main(argv=fake_args) == 0

def main():
    """ Runs a Mercurial pre-commit check to ensure all affected files adhere
    to readability guidelines.

    Currently only enforces JavaScript files.
    """
    failed = []

    try:
        blacklisted = set([l.strip() for l in open('lint-blacklist.txt', 'r')])
    except IOError:
        # Can't find blacklist file? Oh well.
        blacklisted = set()

    try:
        p1 = Popen(["hg", "heads"], stdout=PIPE)
        p2 = Popen(['grep', '-c', '"^parent:"'], stdin=p1.stdout, stdout=PIPE)
        num_heads = int(p2.communicate()[0] or 1)
    except Exception:
        num_heads = 1 # hg heads must have bonked. Just proceed and do the lint.
    if num_heads > 1:
        # Don't run on merges
        print "Skipping lint on merge..."
        return 0

    # Go through all modified or added files.
    try:
        filelist = Popen(["hg", "status", "-a", "-m", "--change", "tip"], stdout=PIPE).communicate()[0].rstrip('\n')
    except OSError, e:
        print >> sys.stderr, "Error calling hg status:", e
        return 1

    if filelist != "":
        for line in filelist.split('\n'):
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
        return 1
    return 0

if __name__ == '__main__':
    force = os.getenv('FORCE_COMMIT')
    if force is None or force.lower() not in ['1', 'true']:
        sys.exit(main())
