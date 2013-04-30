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
import subprocess
import sys

import hook_lib


def main():
    """Run a git pre-commit lint-check."""
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
    if not files_to_lint or files_to_lint == ['']:
        return 0

    num_errors = hook_lib.lint_files(files_to_lint)

    # Lint the commit message itself!
    commit_message = open(sys.argv[1]).read()
    num_errors += hook_lib.lint_commit_message(commit_message)

    # Report what we found, and exit with the proper status code.
    hook_lib.report_errors_and_exit(num_errors, commit_message,
                                    os.path.join('.git', 'commit.save'))


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() not in ('1', 'true'):
        sys.exit(main())
