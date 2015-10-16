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


def main(commit_message_file):
    """Run a git pre-commit lint-check."""
    # If we're a merge, don't try to do a lint-check.
    git_root = subprocess.check_output(['git', 'rev-parse', '--git-dir'])
    # read the commit message contents from the file specified
    commit_message = open(commit_message_file).read()
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

    is_merge_commit = os.path.exists(os.path.join(git_root.strip(),
                                                  'MERGE_HEAD'))

    # Go through all modified or added files.  We handle the case
    # separately if we're a merge or a 'normal' commit.  If we're a
    # merge, the pre-commit hook will only trigger if the merge had
    # conflicts; in this case we only care about linting the files
    # that were edited to resolve the conflict.  For a normal commit,
    # we of course care about linting *all* the changes files.
    if is_merge_commit:
        # I used to run
        #    git diff-tree -r --cc --name-only --diff-filter=AMR -z HEAD
        # but this wouldn't catch changes made to resolve conflicts, so
        # I try this other approach instead.  It doesn't properly ignore
        # files that have changed in both branches but the system was
        # able to do an automatic merge though, sadly.
        a_files = subprocess.check_output(['git', 'diff', '--cached',
                                         '--name-only', '--diff-filter=AMR',
                                         '-z', 'ORIG_HEAD'])
        b_files = subprocess.check_output(['git', 'diff', '--cached',
                                         '--name-only', '--diff-filter=AMR',
                                         '-z', 'MERGE_HEAD'])
        a_files = frozenset(a_files.strip('\0').split('\0'))
        b_files = frozenset(b_files.strip('\0').split('\0'))
        files_to_lint = list(a_files & b_files)
    else:
        # Look at Added, Modified, and Renamed files.
        # When no commit is specified, it defaults to HEAD which is
        # what we want.
        files = subprocess.check_output(['git', 'diff', '--cached',
                                         '--name-only', '--diff-filter=AMR',
                                         '-z'])
        files_to_lint = files.strip('\0').split('\0')  # that's what -z is for

    if not files_to_lint or files_to_lint == ['']:
        return 0

    lint_errors = hook_lib.lint_files(files_to_lint)

    # Lint the commit message itself!
    # For the phabricator workflow, some people always have the git
    # commit message be 'WIP', and put in the actual message at 'arc
    # diff' time.  We don't require a 'real' commit message in that
    # case.
    msg_errors = 0
    if not is_merge_commit and not commit_message.lower().startswith('wip'):
        msg_errors += hook_lib.lint_commit_message(commit_message)

    num_errors = lint_errors + msg_errors

    if lint_errors:
        recommendation = ('Running `arc lint` may help to autofix the errors.'
                          '\nUse "git recommit -a" when the errors'
                          ' are fixed, to re-use this commit message.')
    elif msg_errors:
        recommendation = ('Use "git commit -a --template .git/commit.save"'
                          ' to commit with a fixed message.')
    else:
        recommendation = None

    # Report what we found, and exit with the proper status code.
    hook_lib.report_errors_and_exit(num_errors, commit_message,
                                    os.path.join('.git', 'commit.save'),
                                    recommendation=recommendation)


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() not in ('1', 'true'):
        sys.exit(main(sys.argv[1]))
