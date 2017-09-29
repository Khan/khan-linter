#!/usr/bin/env python
# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E129,E721

"""Run linters for App Engine apps.

By default, this looks at all files under the current directory for
those named *_lint.py, and runs all functions named lint_*() inside
those files.  Each lint_*() function is passed a list of files to
lint, which by default is all files under the current directory.
"""

import argparse
import importlib
import os
import subprocess
import sys
import time
import types

# This is needed so the import_module() below can succeed.
import appengine_tool_setup
appengine_tool_setup.fix_sys_path()

from shared import ka_root
from shared.testutil import lintutil

# We can't do a normal import here because 'khan-linter-src' has
# dashes in it.  We could fix that, but we don't want people
# importing khan-linter-src in general; we're a special case.
sys.path.insert(0, ka_root.join('third_party', 'khan-linter-src'))
import runlint as khan_linter


LINT_FILE_SUFFIX = '_lint.py'


def _get_lint_py_files(use_vcs, verbose=False):
    """All *_lint.py files in the current repo."""
    # The fastest way to find out what files are in the current repo is
    # to ask the version control system.  Only if that fails do we ask
    # the filesystem.  This can be disabled by setting use_vcs to False.
    if use_vcs:
        try:
            if verbose:
                print >>sys.stderr, 'Finding linter modules using git ...',
            # This git command essentially lists files in the stage or HEAD.
            # TODO(benkraft): we should also filter out unstaged deletions.
            files = subprocess.check_output(
                ['git', 'ls-files', '--full-name', '-z'])
            files = files.split('\0')
            if verbose:
                print >>sys.stderr, 'done'
            return [f for f in files if f.endswith(LINT_FILE_SUFFIX)]
        except subprocess.CalledProcessError:    # probably not a git repo
            if verbose:
                print >>sys.stderr, '(not a git repo)'

        try:
            if verbose:
                print >>sys.stderr, 'Finding linter modules using hg ...',
            files = subprocess.check_output(['hg', 'locate', '-0',
                                             LINT_FILE_SUFFIX])
            if verbose:
                print >>sys.stderr, 'done'
            return files.split('\0')
        except subprocess.CalledProcessError:    # probably not an hg repo
            if verbose:
                print >>sys.stderr, '(not a mercurial repo)'

    # We could speed this up by taking a list of sub-directories to
    # look under, rather than always looking under '.', but we don't
    # bother because a) we should 'never' get to this case anyway, and
    # b) 99% of the time the user is asking to lint under '.' anyway.
    files = []
    if verbose:
        print >>sys.stderr, 'Finding linter modules using `find` ...',
    for (root, dirnames, filenames) in os.walk('.'):
        for f in filenames:
            if f.endswith(LINT_FILE_SUFFIX):
                files.append(os.path.join(root, f))
    if verbose:
        print >>sys.stderr, 'done'
    return files


def find_linter_files(files_and_dirs, use_vcs=True, verbose=False):
    """Return a list of all files named *_lint.py under the given dirs."""
    all_lint_py_files = _get_lint_py_files(use_vcs, verbose)

    retval = set()
    for d in files_and_dirs:
        if d == '.':
            retval.update(all_lint_py_files)
        elif os.path.isdir(d):
            retval.update(f for f in all_lint_py_files
                          if f.startswith(d.rstrip(os.sep) + os.sep))
        else:
            retval.add(d)     # if they specified a file, just use it
    return retval


def run_lint(linter_files, files_to_lint, verbose=False):
    """Run all the linters in linter_files on all files in files_to_lint.

    Arguments:
        linter_files: a list of files with linter function in it.  Every
          function named lint_* in this file will be run.  Each such
          function returns a list of error-triples:
             (filename, lineno, error_message)
        files_to_lint: a list of files to lint, or None to lint 'all' files
          (whatever that means for a given linter).

    Returns:
        A list of
           ((filename, lineno, errormsg), linter_fn_name)
        tuples.  linter_fn_name is the name of the function (including
        the module) that had the linter error.  filename:lineno is where
        the lint error was identified, and errormsg is a description of
        the error.
    """
    linter_modules = {}
    # First, import all the linters.
    if verbose:
        print >>sys.stderr, "Importing linters...",
    for f in linter_files:
        module_name = os.path.relpath(f).replace(os.sep, '.')
        if module_name.endswith('.py'):
            module_name = module_name[:-len('.py')]
        module = importlib.import_module(module_name)
        linter_modules[module_name] = module
    if verbose:
        print >>sys.stderr, "done"

    # Now, go through each linter file and find the functions to run.
    linter_functions = {}
    for (module_name, module) in linter_modules.iteritems():
        for fn_name in dir(module):
            if ((fn_name.startswith('lint_') or fn_name == 'lint') and
                type(getattr(module, fn_name)) == types.FunctionType):

                linter_functions['%s.%s' % (module_name, fn_name)] = (
                    getattr(module, fn_name))

    # Now, run all the linter functions.
    errors = []
    for (fn_name, fn) in linter_functions.iteritems():
        if verbose:
            print >>sys.stderr, 'Running %s ...' % fn_name,

        num_errors_previously = len(errors)
        start = time.time()
        for (filename, lineno, error) in fn(files_to_lint):
            if (error.endswith(lintutil.NOLINT_NOT_ALLOWED) or
                    not lintutil.has_nolint(filename, lineno)):
                errors.append(((filename, lineno, error), fn_name))
        elapsed = time.time() - start
        num_errors = len(errors) - num_errors_previously

        if verbose:
            print >>sys.stderr, ('%d errors (%.2f seconds)'
                                 % (num_errors, elapsed))

    return errors


def print_lint_errors(errors, use_abspath, verbose, fout):
    """Print to stdout all errors returned by run_lint."""
    if verbose and errors:
        print >>fout, '-- LINT ERRORS:'
    errors.sort()
    for ((filename, lineno, error), linter_fn) in errors:
        if filename is None:
            filename = '<none>'
        if lineno is None:
            lineno = 0
        if not use_abspath:
            filename = os.path.relpath(filename)
        # The 'E314' is to fit this regexp format to what 'arc lint' expects.
        print >>fout, '%s:%s: E314 %s (%s)' % (filename, lineno, error,
                                               linter_fn)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run linters for App Engine apps.')
    parser.add_argument('--blacklist', choices=['yes', 'no', 'auto'],
                        default='auto',
                        help=('If yes, ignore files that are on the blacklist.'
                              ' If no, do not consult the blacklist.'
                              ' If auto, use the blacklist for directories'
                              ' listed on the commandline, but not for files.'
                              ' (default: %(default)s)'))
    parser.add_argument('--blacklist-filename',
                        default=khan_linter._DEFAULT_BLACKLIST_PATTERN,
                        help=('The file to use as a blacklist. If the filename'
                              ' starts with "<ancestor>/", then, for each file'
                              ' to be linted, we take its blacklist to be from'
                              ' the closest parent directory that contains'
                              ' the (rest of the) blacklist filename.'
                              ' (default: %(default)s)'))
    parser.add_argument('--lint-spec', '-l', action='append', default=[],
                        help=("Specify lint-spec by directory or file.  May "
                              "specify more than once."
                              "  Directory name: "
                              "recursively search for files named *_lint.py."
                              "  File name: "
                              "run all methods named `lint_*' in this file."
                              "  (default: ['.'])"))
    parser.add_argument('--abspath', '-a', action='store_true', default=False,
                        help=("When printing lint errors, make all filenames "
                              "absolute paths"))
    parser.add_argument('--no-vcs', action='store_true', default=False,
                        help=("Don't ask git/hg where the lint files are,"
                              " but rather look at the filesystem directly."
                              " This is slower but can be more accurate."))
    parser.add_argument('--verbose', '-v', action='store_true', default=False,
                        help=("More verbose output."))
    parser.add_argument('files_to_lint', nargs='*', default=['.'],
                        metavar='FILE_OR_DIR_TO_LINT',
                        help=('The files or directories to run the linters'
                              ' over; - to read files/data via stdin, one'
                              ' per line (default: %(default)s'))
    args = parser.parse_args()

    lint_specs = args.lint_spec or ['.']
    linter_files = find_linter_files(lint_specs, not args.no_vcs,
                                     args.verbose)

    files_to_lint = args.files_to_lint
    if '-' in files_to_lint:
        files_to_lint.remove('-')
        files_to_lint.extend(sys.stdin.read().splitlines())

    files_to_lint = khan_linter.find_files_to_lint(files_to_lint,
                                                   args.blacklist,
                                                   args.blacklist_filename,
                                                   args.verbose)
    errors = run_lint(linter_files, files_to_lint, args.verbose)
    print_lint_errors(errors, args.abspath, args.verbose, sys.stdout)

    # Clamp, since exitcode of 128+ is reserved for signals.
    sys.exit(min(len(errors), 127))
