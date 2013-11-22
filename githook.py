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


def _normalized_commit_message(text):
    """Remove lines starting with '#' and other stuff that git ignores."""
    lines = text.splitlines(True)
    lines = [l for l in lines if not l.startswith('#')]
    return ''.join(lines).strip()


def main():
    """Run a git pre-commit lint-check."""
    # If we're a merge, don't try to do a lint-check.
    git_root = subprocess.check_output(['git', 'rev-parse', '--git-dir'])
    if os.path.exists(os.path.join(git_root.strip(), 'MERGE_HEAD')):
        print "Skipping lint on merge..."
        return 0

    commit_message = open(sys.argv[1]).read()
    # Get rid of the comment lines, and leading and trailing whitespace.
    commit_message = _normalized_commit_message(commit_message)

    # If the commit message is empty or unchanged from the template, abort.
    if not commit_message:
        print "Aborting commit, empty commit message"
        return 1

    try:
        with open(os.path.join(git_root.strip(), 'commit_template')) as f:
            template = f.read()
    except (IOError, OSError):       # user doesn't have a commit template
        pass
    else:
        if commit_message == _normalized_commit_message(template):
            print "Aborting commit, commit message unchanged"
            return 1

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
    # For the phabricator workflow, some people always have the git
    # commit message be 'WIP', and put in the actual message at 'arc
    # diff' time.  We don't require a 'real' commit message in that
    # case.
    if not commit_message.lower().startswith('wip'):
        num_errors += hook_lib.lint_commit_message(commit_message)

    # Report what we found, and exit with the proper status code.
    hook_lib.report_errors_and_exit(num_errors, commit_message,
                                    os.path.join('.git', 'commit.save'))


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() not in ('1', 'true'):
        sys.exit(main())
