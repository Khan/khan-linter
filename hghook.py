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

import hook_lib


def main():
    """Run a Mercurial pre-commit lint-check."""
    # If we're a merge, don't try to do a lint-check.
    try:
        # We just want to know how many parents there are.
        # This will output one x for one parent, and two xs for two parents
        # (i.e. a merge)
        heads_output = subprocess.check_output([
            'hg', 'parents', '--template', 'x'
        ])
    except subprocess.CalledProcessError:
        # hg heads must have bonked. Just proceed and do the lint.
        heads_output = ''
    if len(heads_output) > 1:
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

    num_errors = hook_lib.lint_files(files_to_lint)

    # Lint the commit message itself!
    commit_message = subprocess.check_output(['hg', 'tip',
                                              '--template', '{desc}'])
    num_errors += hook_lib.lint_commit_message(commit_message)

    # Report what we found, and exit with the proper status code.
    hook_lib.report_errors_and_exit(num_errors, commit_message,
                                    os.path.join('.hg', 'commit.save'))


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() not in ('1', 'true'):
        sys.exit(main())
