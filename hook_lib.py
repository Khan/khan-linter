#!/usr/bin/env python

"""Library for code shared by hghook.py and githook.py.

This library does the actual linting, after the VCS-specific commands
to get the data that needs linting.
"""

import re
import subprocess
import sys

import six


def lint_files(files_to_lint):
    """Given a list of filenames in the commit, lint them all.

    We use `ka_lint` to lint them all, which in most repos will call
    runlint.py (in this directory) but in other repos -- notably webapp
    -- will do its own thing.  In all cases, ka_lint will emit lint
    errors to stdout, lint-framework errors to stderr, and have an rc of
    0 if linting was successful or 1 if there were lint or framework
    errors.

    This helper also returns 0 if linting was successful or 1 otherwise.
    """
    # We could pass in the files-to-lint on the commandline, but using
    # --stdin means we don't need to worry about how many files there are.
    p = subprocess.Popen(['ka-lint', '--stdin', '--blacklist=yes'],
                         stdin=subprocess.PIPE)
    p.communicate(input='\n'.join(files_to_lint))
    return p.wait()


def lint_commit_message(commit_message):
    """Given the text of a commit message, lint it for correctness.

    Every non-merge commit must list either a test plan or a review
    that it's part of (the first commit in a review must have a test
    plan, but subsequent ones don't need to restate it).
    TODO(csilvers): should we do anything special with substate-update
    commits?

    Emits errors it sees to stderr.

    Returns the number of lint errors seen in the commit message.
    """
    num_errors = 0

    if not re.search('^(test plan|review):', commit_message, re.I | re.M):
        six.print_('Missing "Test plan:" or "Review:" section '
                   'in the commit message.', file=sys.stderr)
        num_errors += 1

    elif re.search('^    <see below>$', commit_message, re.M):
        six.print_('Must enter a "Test plan:" (or "Review:") '
                   'in the commit message.', file=sys.stderr)
        num_errors += 1

    if re.search('^<one-line summary, followed by ', commit_message, re.M):
        six.print_('Must enter a summary in the commit message.',
                   file=sys.stderr)
        num_errors += 1

    # TODO(csilvers): verify the first-line summary is actually 1 line long?

    return num_errors


def report_errors_and_exit(num_errors, commit_message, save_filename):
    """If num_errors > 0, print a summary message and exit 1.

    In that case, we save the commit message to save_filename.
    """
    if num_errors:
        # save the commit message so we don't need to retype it
        with open(save_filename, 'w') as f:
            f.write(commit_message)
        six.print_('\n--- %s commit message errors ---\n'
                   'Commit message saved to %s'
                   % (num_errors, save_filename),
                   file=sys.stderr)
        six.print_('Use "git commit -a --template .git/commit.save" to commit'
                   ' with a fixed message.', file=sys.stderr)
        sys.exit(1)
    six.print_('khan-linter: commit message passed', file=sys.stderr)
    sys.exit(0)
