#!/usr/bin/env python
"""Hooks for git that perform linting.

This file contains two git hooks:

1. A commit-msg hook, to lint the commit message. If lint fails, the commit
   is aborted, and the message is saved in a temporary file.
2. A pre-push hook, to lint files that will remotely change as a result of the
   push. If lint fails, the push is aborted.

These hooks are automatically installed in linted KA repositories, by the
`ka-clone` tool.

This script accepts an optional argument "--hook=<hook>", which specifies which
hook to run (commit-msg or pre-push). If omitted, defaults to "commit-msg", to
preserve legacy behavior (from back when that was the only hook this script
contained).

The remaining positional arguments are assumed to be provided by git, and are
forwarded to the hook's handler function as the argument list. (For example,
the commit-msg git hook has a single positional argument: the path to the
commit message file.) Note, too, that some git hooks provide additional input
on STDIN.

The user can choose to skip this hook, by running `git push --no-verify` (in
which case, git won't call this script at all), or specifying FORCE_COMMIT=1
in the environment (in which case, this script will be a no-op).

TODO(mdr): In addition to linting the commit message, the commit-msg hook
    currently lints the commit's changed files, and rejects the commit if lint
    fails - but this use case is now effectively covered by the pre-push hook.
    Stop linting file changes on commit, and remove the corresponding dead
    code in hook_lib.py. (JSBUILD-160)

NOTE(mdr): If you're here to remove a hook, be aware that existing ka-clone'd
    repositories on developers' machines might still attempt to call the hook.
    Instead of deleting the hook outright and triggering a crash, consider
    replacing the hook's handler with a message explaining how to upgrade.
"""

import argparse
import os
import subprocess
import sys

import six

import hook_lib


def _normalized_commit_message(text):
    """Remove lines starting with '#' and other stuff that git ignores."""
    lines = text.splitlines(True)
    lines = [l for l in lines if not l.startswith('#')]
    return ''.join(lines).strip()


def commit_msg_hook(commit_message_file):
    """Run a git pre-commit lint-check."""
    # If we're a merge, don't try to do a lint-check.
    git_root = subprocess.check_output(
        ['git', 'rev-parse', '--git-dir']).decode('utf-8')
    # read the commit message contents from the file specified
    commit_message = open(commit_message_file).read()
    # Get rid of the comment lines, and leading and trailing whitespace.
    commit_message = _normalized_commit_message(commit_message)

    # If the commit message is empty or unchanged from the template, abort.
    if not commit_message:
        six.print_("Aborting commit, empty commit message")
        return 1

    try:
        with open(os.path.join(git_root.strip(), 'commit_template')) as f:
            template = f.read()
    except (IOError, OSError):       # user doesn't have a commit template
        pass
    else:
        if commit_message == _normalized_commit_message(template):
            six.print_("Aborting commit, commit message unchanged")
            return 1

    is_merge_commit = os.path.exists(os.path.join(
        git_root.strip(), 'MERGE_HEAD'))

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
        a_files = subprocess.check_output(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=AMR',
             '-z', 'ORIG_HEAD']).decode('utf-8')
        b_files = subprocess.check_output(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=AMR',
             '-z', 'MERGE_HEAD']).decode('utf-8')
        a_files = frozenset(a_files.strip('\0').split('\0'))
        b_files = frozenset(b_files.strip('\0').split('\0'))
        files_to_lint = list(a_files & b_files)
    else:
        # Look at Added, Modified, and Renamed files.
        # When no commit is specified, it defaults to HEAD which is
        # what we want.
        files = subprocess.check_output(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=AMR',
             '-z']).decode('utf-8')
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


def pre_push_hook(_unused_arg_remote_name, _unused_arg_remote_location):
    """Run a git pre-push lint-check.

    The pre-push hook has a test script: test_githook_pre_push.sh. If you're
    making significant changes to this function, consider running the test!
    """
    for line in sys.stdin:
        # For each branch we're trying to push, the git hook will tell us the
        # local branch name, local sha, remote branch name, and remote sha.
        # For our purposes, we only care about the local sha.
        (_, local_sha, _, _) = line.split()

        # To find files that have been changed locally, we'll use `git log` to
        # find commits that are present in the branch state we intend to push,
        # but aren't present on any remote-tracking branch. We'll then format
        # the list of files changed in each such commit.
        #
        # This filtering is based on the assumption that any change already on
        # the remote server, and therefore in a remote-tracking branch, has
        # been linted by a previous `git push` hook.
        #
        # This filtering is just an optimization, and it's okay if we re-lint
        # a few extra files... but we should try not to lint *too* many extra
        # files, or else the process will be annoyingly slow.
        #
        # NOTE(mdr): This filtering won't recognize changes that are already on
        #     on remote, but were *copied* to the local branch, for example by
        #     `git cherry-pick`. The `--cherry-pick` filtering option for
        #     `git log` claims to be able to detect this, but only works for
        #     symmetric difference filtering, which isn't what we're using.
        #     Thankfully, this isn't a big deal in standard workflows for
        #     merging or rebasing master's work into a feature branch. Merging
        #     will use the original commits from both branches. Rebasing is
        #     liable to copy the feature branch's commits, but those are likely
        #     to have a much smaller surface area, so re-linting them shouldn't
        #     take very long.
        #
        # NOTE(mdr): A simpler filtering strategy might be to just compare the
        #     local and remote state of the current branch. However, this would
        #     lead to unnecessarily slow linting for merge commits: e.g., you
        #     merge origin/master into local branch foobar, then push to
        #     origin/foobar. This push might contain many commits from
        #     origin/master which aren't yet in origin/foobar, but that *have*
        #     been linted already.
        files_to_lint = subprocess.check_output([
            'git', 'log',

            # We "format" each commit by hiding its commit details, and listing
            # the name of each added/modified/removed file, separated by NUL.
            '--pretty=format:', '--name-only', '--diff-filter=AMR', '-z',

            # Include commits that are reachable from the local state we intend
            # to push.
            local_sha,

            # Do not include commits that are reachable from any
            # remote-tracking branch's state. (The `--remotes` flag is
            # equivalent to manually listing `origin/master`, `origin/foobar`,
            # etc. The `--not` flag negates all subsequent references.)
            '--not', '--remotes',
        ]).decode('utf-8')

        # Parse files to lint: split at NUL characters, remove blank entries,
        # and remove duplicates.
        files_to_lint = list({f for f in files_to_lint.split('\0') if f})

        # Lint the files, if any. If there are any errors, print a helpful
        # message, and return a nonzero status code to abort the push.
        if files_to_lint:
            num_errors = hook_lib.lint_files(files_to_lint)
            if num_errors > 0:
                six.print_(
                    '\n--- %s lint errors. Push aborted. ---' % num_errors,
                    file=sys.stderr)
                six.print_(
                    'Running `arc lint` may help to autofix the errors.',
                    file=sys.stderr)
                return 1

        # Yay, everything went okay! Return a zero status code, in order to
        # allow the push.
        six.print_('khan-linter: all lint checks passed', file=sys.stderr)
        return 0


if __name__ == '__main__':
    suppress_lint = os.getenv('FORCE_COMMIT', '')
    if suppress_lint.lower() in ('1', 'true'):
        sys.exit(0)

    parser = argparse.ArgumentParser(description='Perform lint git hooks.')
    parser.add_argument('--hook', type=str, choices=['commit-msg', 'pre-push'],
                        default='commit-msg', help='which hook to perform')
    parser.add_argument('hook_args', nargs='*',
                        help='The arguments provided by the git hook.')

    args = parser.parse_args()
    if args.hook == 'commit-msg':
        status_code = commit_msg_hook(*args.hook_args)
    elif args.hook == 'pre-push':
        status_code = pre_push_hook(*args.hook_args)
    else:
        raise AssertionError("unrecognized hook name - should've been caught "
                             "by argparse?")

    sys.exit(status_code)
