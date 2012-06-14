#!/usr/bin/env python

"""Pre-commit hook for mercurial that does lint testing.

It runs the lint checker (runlint.py) on all the open files in
the current commit.

To install, add the following line to your .hgrc:
  [hooks]
  pretxncommit.lint = /path/to/khan-linter/hghook.py

"""

import os
import subprocess
import sys

import runlint


def main():
    """Run a Mercurial pre-commit lint-check."""
    # If we're a merge, don't try to do a lint-check.
    try:
        heads_output = subprocess.check_output(['hg', 'heads'])
    except subprocess.CalledProcessError:
        # hg heads must have bonked. Just proceed and do the lint.
        heads_output = ''
    if heads_output.count('\nparent:') > 1:
        print "Skipping lint on merge..."
        return 0

    # Go through all modified or added files.
    try:
        status_output = subprocess.check_output(['hg', 'status', '-a', '-m',
                                                 '--change', 'tip'])
    except subprocess.CalledProcessError, e:
        print >> sys.stderr, "Error calling 'hg status':", e
        return 1

    files_to_lint = []
    if status_output:
        for line in status_output.strip().split('\n'):
            # each line has the format "M path/to/filename.js"
            status, filename = line.split(' ', 1)
            files_to_lint.append(filename)

    num_errors = runlint.main(files_to_lint, blacklist='yes')

    if num_errors:
        # save the commit message so we don't need to retype it
        f = open(os.path.join('.hg', 'commit.save'), 'w')
        subprocess.call(['hg', 'tip', '--template', '{desc}'], stdout=f)
        f.close()
        print >> sys.stderr, ('\n--- %s lint errors ---\n'
                              'Commit message saved to .hg/commit.save'
                              % num_errors)
        return 1
    return 0


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() not in ('1', 'true'):
        sys.exit(main())
