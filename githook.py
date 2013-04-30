#!/usr/bin/env python

"""Commit hook for git that does lint testing.

It runs the lint checker (runlint.py) on all the open files in
the current commit.

To install (for git >= 1.7.1), run the following:
   % git config --global init.templatedir '~/.git_template'
and then create a symlink from
   ~/.git_template/hooks/commit-msg
to this file.
"""

import os
import re
import subprocess
import sys

import runlint


def main():
    """Run a Mercurial pre-commit lint-check."""
    # Go through all modified or added files.
    try:
        subprocess.check_output(['git', 'rev-parse', '--verify', 'HEAD'],
                                stderr=subprocess.STDOUT)
        parent = 'HEAD'
    except subprocess.CalledProcessError:
        parent = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'  # empty repo

    # Look at Added, Modified, and Renamed files.
    files = subprocess.check_output(['git', 'diff', '--cached', '--name-only',
                                     '--diff-filter=AMR', '-z', parent])
    files_to_lint = files.strip('\0').split('\0')    # that's what -z is for

    num_errors = runlint.main(files_to_lint, blacklist='yes')

    # Lint the commit message itself!  Every non-merge commit must
    # list either a test plan or a review that it's part of (the first
    # commit in a review must have a test plan, but subsequent ones
    # don't need to restate it).  TODO(csilvers): should we do anything
    # special with substate-update commits?
    commit_message = open(sys.argv[1]).read()
    if not re.search('^(test plan|review):', commit_message, re.I | re.M):
        print >> sys.stderr, ('Missing "Test plan:" or "Review:" section '
                              'in the commit message.')
        num_errors += 1
    # TODO(csilvers): have a commit template that makes these tests useful.
    elif re.search('^    <see below>$', commit_message, re.M):
        print >> sys.stderr, ('Must enter a "Test plan:" (or "Review:") '
                              'in the commit message.')
        num_errors += 1
    if re.search('^<one-line summary, followed by ', commit_message, re.M):
        print >> sys.stderr, 'Must enter a summary in the commit message.'
        num_errors += 1
    # TODO(csilvers): verify the first-line summary is actually 1 line long?

    if num_errors:
        # save the commit message so we don't need to retype it
        f = open(os.path.join('.git', 'commit.save'), 'w')
        f.write(commit_message)
        f.close()
        print >> sys.stderr, ('\n--- %s lint errors ---\n'
                              'Commit message saved to .git/commit.save'
                              % num_errors)
        return 1
    return 0


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() not in ('1', 'true'):
        sys.exit(main())
