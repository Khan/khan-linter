#!/usr/bin/env python

"""Run some linters on files of various types."""


USAGE = """%prog [options] [files] ...

Run linters over the given files, or the current directory tree.

By default -- if no commandline arguments are given -- this runs the
linters on all non-blacklisted python file under the current
directory.  By default, the blacklist is in a file called
lint_blacklist.txt, in some directory in or above the files being
linted.

If commandline arguments are given, this runs the linters on all the
files listed on the commandline, regardless of their presence in the
blacklist (this behavior is controlled by the --blacklist flag).

If --extra-linter-filename is set (as it is by default), and that
file exists and is executable, then this script will run that program
as well, passing in '-' on the commandline and all the files listed on
stdin.  Any such program must support the '-' argument and also give
output in the canonical form:
   filename:linenum: E<error_code> error message
and its exit code should be the number of lint errors seen.

This script automatically determines the linter to run based on the
filename extension.  (This can be overridden with the --lang flag.)
Files with unknown or unsupported extensions will be skipped.
"""

import fcntl
import fnmatch
import optparse
import os
import re
import subprocess
import sys
import time

import linters
import lint_util

_DEFAULT_BLACKLIST_PATTERN = '<ancestor>/lint_blacklist.txt'
_DEFAULT_EXTRA_LINTER = '<ancestor>/tools/runlint.py'
_CWD = lint_util.get_real_cwd()

_BLACKLIST_CACHE = {}    # map from filename to its parsed contents (a set)


def _parse_one_blacklist_line(line):
    if line.endswith('/'):
        # When blacklisting a directory, we add two entries: one for the
        # directory name itself (to make pruning easier), and one for the
        # entire directory tree (as a regexp).  This recursive call does
        # the first of these.
        retval = _parse_one_blacklist_line(line[:-1])
    # If the code below this line has horrible syntax highlighting, check
    # this out:  http://stackoverflow.com/questions/13210816/sublime-texts-syntax-highlighting-of-regexes-in-python-leaks-into-surrounding-c
    elif not re.search(r'[[*?!]', line):
        # Easy case: no char meaningful to glob()
        return set((os.path.normpath(line),))
    else:
        retval = set()

    # If we get here, the pattern is a glob pattern.
    if line.startswith('**/'):   # magic 'many directory' matcher
        fnmatch_line = line[len('**/'):]
        re_prefix = '.*'
    else:
        fnmatch_line = line
        re_prefix = ''

    fnmatch_re = fnmatch.translate(fnmatch_line)   # glob -> re
    # For some unknown reason, fnmatch.translate tranlates '*'
    # to '.*' rather than '[^/]*'.  We have to fix that.
    fnmatch_re = fnmatch_re.replace('.*', '[^/]*')
    # fnmatch.translate also puts in a \Z (same as $, basically).
    # But if the blacklist pattern is a directory, we don't want
    # that, since we want to do exactly a prefix match.
    if fnmatch_line.endswith('/'):
        fnmatch_re = fnmatch_re.replace(r'\Z', '')

    retval.add(re.compile(re_prefix + fnmatch_re))
    return retval


def _parse_blacklist(blacklist_filename):
    """Read from blacklist filename and returns a set of the contents.

    Blank lines and those that start with # are ignored.

    Arguments:
       blacklist_filename: the full path of the blacklist file

    Returns:
       A set of all the paths listed in blacklist_filename.
       These paths may be filename strings, directory name strings,
       or re objects (for blacklist entries with '*'/etc in them).
    """
    if not blacklist_filename:
        return set()

    if blacklist_filename in _BLACKLIST_CACHE:
        return _BLACKLIST_CACHE[blacklist_filename]

    retval = set()
    contents = open(blacklist_filename).readlines()
    for line in contents:
        line = line.strip()
        if line and not line.startswith('#'):
            retval.update(_parse_one_blacklist_line(line))
    _BLACKLIST_CACHE[blacklist_filename] = retval
    return retval


# Map of a directory to the ancestor filename in the closest parent
# directory to the given directory (or possibly the given directory
# itself).  Ancestor-filenames are ones that can start with
# '<ancestor>/'.
_ANCESTOR_DIR_CACHE = {}


def _resolve_ancestor(ancestor_pattern, file_to_lint):
    """If a_p starts with '<ancestor>/', replace based on file_to_lint.

    The rule is that we start at file_to_lint's directory, and replace
    '<ancestor>/' with that directory.  If the resulting filepath exists,
    return it.  Otherwise, go up one level in the directory tree and
    try again, replacing '<ancestor>/' with the parent-dir.  Continue
    until we succeed or get to /, at which point we return None.
    """
    if not ancestor_pattern:
        return None

    if not ancestor_pattern.startswith('<ancestor>/'):
        return ancestor_pattern   # the 'pattern' is an actual filename

    # The hard case: resolve '<ancestor>/' to the proper directory.
    ancestor_basename = ancestor_pattern[len('<ancestor>/'):]
    ancestor_dir = None
    if os.path.isdir(file_to_lint):
        d = file_to_lint
    else:
        d = os.path.dirname(file_to_lint)
    d = os.path.abspath(d)
    while os.path.dirname(d) != d:     # not at the root level (/) yet
        if (ancestor_pattern, d) in _ANCESTOR_DIR_CACHE:
            return _ANCESTOR_DIR_CACHE[(ancestor_pattern, d)]
        if os.path.exists(os.path.join(d, ancestor_basename)):
            ancestor_dir = d
            break
        d = os.path.dirname(d)

    # Now update _ANCESTOR_DIR_CACHE for all directories that need it.
    # We now know the proper ancestor file to use for ancestor_dir and
    # all the directories we saw beneath it.
    if ancestor_dir is None:   # never found a ancestor
        d = os.path.dirname(file_to_lint)
        while d != os.path.dirname(d):
            _ANCESTOR_DIR_CACHE[(ancestor_pattern, d)] = None
            d = os.path.dirname(d)
        return None
    else:
        ancestor_filename = os.path.join(ancestor_dir, ancestor_basename)
        d = os.path.dirname(file_to_lint)
        while d != os.path.dirname(ancestor_dir):
            _ANCESTOR_DIR_CACHE[(ancestor_pattern, d)] = ancestor_filename
            d = os.path.dirname(d)
        return ancestor_filename


def _file_in_blacklist_helper(fname, blacklist_pattern):
    # The blacklist entries are taken to be relative to
    # blacklist_filename-root, so we need to relative-ize basename here.
    # TODO(csilvers): use os.path.relpath().
    blacklist_filename = _resolve_ancestor(blacklist_pattern, fname)
    if not blacklist_filename:
        return False
    blacklist_dir = os.path.abspath(os.path.dirname(blacklist_filename))
    fname = os.path.abspath(fname)
    if not fname.startswith(blacklist_dir):
        print ('WARNING: %s is not under the directory containing the '
               'blacklist (%s), so we are ignoring the blacklist'
               % (fname, blacklist_dir))
    fname = fname[len(blacklist_dir) + 1:]   # +1 for the trailing '/'

    blacklist = _parse_blacklist(blacklist_filename)
    if fname in blacklist:
        return True

    # The blacklist can have regexp patterns in it, so we need to
    # check those too, one by one:
    for blacklist_entry in blacklist:
        if not isinstance(blacklist_entry, basestring):
            if blacklist_entry.match(fname):
                return True

    return False


def _file_in_blacklist(fname, blacklist_pattern):
    """True if fname, an absolute path, matches any entry in blacklist."""
    if _file_in_blacklist_helper(fname, blacklist_pattern):
        return True
    # If fname is a symlink, resolve the symlink and check again.
    if os.path.islink(fname):
        if _file_in_blacklist_helper(os.path.realpath(fname),
                                     blacklist_pattern):
            return True
    return False


def _files_under_directory(rootdir, blacklist_pattern, verbose):
    """Return a set of files under rootdir not in the blacklist."""
    retval = set()
    for root, dirs, files in os.walk(rootdir):
        # Prune the subdirs that are in the blacklist.  We go
        # backwards so we can use del.  (Weird os.walk() semantics:
        # calling del on an element of dirs suppresses os.walk()'s
        # traversal into that dir.)
        for i in xrange(len(dirs) - 1, -1, -1):
            absdir = os.path.join(root, dirs[i])
            if _file_in_blacklist(absdir, blacklist_pattern):
                if verbose:
                    print '... skipping directory %s: in blacklist' % absdir
                del dirs[i]
        # Prune the files that are in the blacklist.
        for f in files:
            abspath = os.path.join(root, f)
            if _file_in_blacklist(abspath, blacklist_pattern):
                if verbose:
                    print '... skipping file %s: in blacklist' % abspath
                continue
            retval.add(os.path.join(root, f))
    return retval


def find_files_to_lint(files_and_directories,
                       blacklist='auto',
                       blacklist_pattern=_DEFAULT_BLACKLIST_PATTERN,
                       verbose=False):
    if blacklist == 'yes':
        file_blacklist = blacklist_pattern
        dir_blacklist = blacklist_pattern
        if verbose:
            print 'Using blacklist %s for all files' % blacklist_pattern
    elif blacklist == 'auto':
        file_blacklist = None
        dir_blacklist = blacklist_pattern
        if verbose:
            print ('Using blacklist %s for files under directories'
                   % blacklist_pattern)
    else:
        file_blacklist = None
        dir_blacklist = None

    # Ignore explicitly-listed files that are in the blacklist.
    files_to_lint = []
    directories_to_lint = []
    for f in files_and_directories:
        f = os.path.abspath(f)
        if os.path.isdir(f):
            blacklist_for_f = dir_blacklist
        else:
            blacklist_for_f = file_blacklist
        blacklist_filename = _resolve_ancestor(blacklist_for_f, f)
        if verbose:
            print 'Considering %s: blacklist %s' % (f, blacklist_filename),

        if _file_in_blacklist(f, blacklist_for_f):
            if verbose:
                print '... skipping (in blacklist)'
        elif os.path.isdir(f):
            if verbose:
                print ('... LINTING %s files under this directory'
                       % ('non-blacklisted' if dir_blacklist else 'all'))
            directories_to_lint.append(f)
        else:
            if verbose:
                print '... LINTING'
            files_to_lint.append(f)

    # TODO(csilvers): log if we skip a file in a directory because
    # it's in the blacklist?
    for directory in directories_to_lint:
        files_to_lint.extend(_files_under_directory(directory, dir_blacklist,
                                                    verbose))

    files_to_lint.sort()    # just to be pretty
    return files_to_lint


_EXTENSION_DICT = {'.py': 'python',
                   '.js': 'javascript',
                   '.html': 'html',
                   '.jsx': 'jsx',
                   '.less': 'less',
                   }


def _lang(filename, lang_option):
    """Returns a string representing the language filename is written in."""
    if lang_option:            # the user specified the langauge explicitly
        return lang_option
    extension = os.path.splitext(filename)[1]
    return _EXTENSION_DICT.get(extension, 'unknown')


def _run_extra_linter(extra_linter_filename, files, verbose):
    """Run extra_linter_filename if it exists and is executable.

    extra_linter_filename can start with <ancestor>, in which case
    we use the same rule we use for the blacklist: for each file
    in files, we go up the directory tree until we find the linter.
    This means we could actually run several linter scripts for a
    set of files (if, for instance, they're in different repos).

    extra_linter_filename is passed a list of files; the same list
    of files that is used for the blacklist.  We limit each run to
    100 files at a time to avoid shell overflow.
    """
    num_lint_errors = 0
    num_framework_errors = 0

    # Probably all these files will use the same linter, but let's
    # make sure.
    linter_to_files = {}
    for f in files:
        linter = _resolve_ancestor(extra_linter_filename, f)
        if linter:
            linter_to_files.setdefault(linter, set()).add(f)

    for (linter_filename, files) in linter_to_files.iteritems():
        if not os.access(linter_filename, os.R_OK | os.X_OK):
            continue
        files = sorted(files)
        if verbose:
            print ('--- running extra linter %s on these files: %s'
                   % (linter_filename, files))
        p = subprocess.Popen([linter_filename, '-'], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = p.communicate(input='\n'.join(files))
        # If the subprocess returned 1, it's possible this was due to a
        # raised exception rather than a lint error.  We try to detect
        # this by checking if stdout is empty: if so, it means that there
        # was no actual lint error found, so this must be an exception.
        if p.returncode > 0 and not stdout:
            print ('ERROR running the extra linter %s on these files: %s: %s'
                   % (linter_filename, files, stderr))
            num_framework_errors += 1
        else:
            print stdout + stderr   # print the lint errors seen
            num_lint_errors += p.returncode

    return (num_lint_errors, num_framework_errors)


def _maybe_pull(verbose):
    """If the repo hasn't been updated in 24 hours, pull. If the working copy
    changed as a result, return True. If no pull was done or there were no
    changes, return False.
    """
    # If we're not a git repo, we can't pull.
    if not os.path.isdir(os.path.join(_CWD, '.git')):
        return False

    try:
        last_pull_time = os.stat('/tmp/khan-linter.pull').st_mtime
    except (IOError, OSError):
        last_pull_time = 0
    if last_pull_time + 24 * 60 * 60 >= time.time():
        return False

    # Update the last-pull time, and create an fd for the lockf call.
    with open('/tmp/khan-linter.pull', 'w') as f:
        # Phabricator often runs two linters at the same time, meaning
        # they could both contend for the 'git pull' call.  This lock
        # prevents that.  (It does mean that we pull twice, but that's
        # the safest way to make sure neither linter runs before the
        # update is complete.)
        fcntl.lockf(f, fcntl.LOCK_EX)
        if verbose:
            print 'Updating the khan-linter repo'

        old_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=_CWD)
        subprocess.check_call(
            ['git', 'pull', '-q', '--no-rebase', '--ff-only'],
            cwd=_CWD)
        new_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=_CWD)

    return new_sha != old_sha


# W291 trailing whitespace
# W293 blank line contains whitespace
# W391 blank line at end of file
_DEFAULT_PEP8_ARGS = ['--repeat',
                      '--ignore=W291,W293,W391']


def _find_base_eslint_config(files_to_lint, default_location):
    """Return a .eslintrc file in the repo's root directory if it exists.

    If this file exists, it will replace khan-linter's `eslintrc` as the
    config file used for javascript linting. If you'd like a repo to use
    khan-linter's eslintrc plus other stuff, create a .eslintrc in the root
    directory of that repo and have it include a field:
        "extends": "../devtoools/khan-linter/eslintrc"`

    If the custom eslintrc depends on any extra node modules, for plugins or
    parsers, these node modules should be referenced as relative to the
    eslintrc file, but without the preceeding "./" often used to denote
    relative paths. For example, if the parser module `babel-eslint` is in
    `repo/javascript/node_modules/babel-eslint` and the custom `.eslint` file
    is in `repo/.eslint`, then the path in the eslint file should be
    `javascript/node_modules/babel-eslint`.
    """
    if not files_to_lint:
        return default_location

    def _find_eslint_for_path(path):
        base_git = _resolve_ancestor('<ancestor>/.git', path)
        base_directory = os.path.dirname(base_git)

        base_eslint_config = os.path.join(base_directory, '.eslintrc')
        if os.path.exists(base_eslint_config):
            return base_eslint_config
        return default_location

    config_path = _find_eslint_for_path(files_to_lint[0])
    for path in files_to_lint[1:]:
        if _find_eslint_for_path(path) != config_path:
            # TODO(jared): partition files_to_lint by config file, and run
            # eslint once for each config file instead of bailing.
            raise Exception("Files to lint depend on multiple custom eslint "
                    "config files. This is currently unsupported.")

    return config_path


def main(files_and_directories,
         blacklist='auto', blacklist_pattern=_DEFAULT_BLACKLIST_PATTERN,
         extra_linter_filename=_DEFAULT_EXTRA_LINTER, lang='', verbose=False,
         propose_arc_fixes=False):
    """Call the appropriate linters on all given files and directory trees.

    Arguments:
      files_and_directories: a list/set/etc of files to lint, and/or
         a list/setetc of directories to lint all files under
      blacklist: 'yes', 'no', or 'auto', as described by --help
      blacklist_pattern: where to read the blacklist, as described by --help
      extra_linter_filename: what auxilliary linter to run, described by --help
      lang: the language to interpret all files to be in, or '' to auto-detect
      verbose: print messages about what we're doing, to stdout
      propose_arc_fixes: append special strings to the end of lint lines where
        we know how to automatically fix the problem. `arc lint` consumes these
        special strings and prompts the user to see if they want to accept the
        patch.

    Returns:
      A pair: (number of lint errors seen, number of unlintable files seen).
      (0, 0) means lint-cleanliness.  If the second value is non-zero, it
      means there was a problem in the lint framework itself somewhere.
    """
    files_to_lint = find_files_to_lint(files_and_directories,
                                       blacklist, blacklist_pattern, verbose)

    default_eslint_config = os.path.join(_CWD, "eslintrc")
    base_eslint_config = _find_base_eslint_config(files_to_lint,
            default_eslint_config)

    # A dict that maps from language (output of _lang) to a list of processors.
    # None means that we skip files of this language.
    processor_dict = {
        'python': (linters.Pep8([sys.argv[0]] + _DEFAULT_PEP8_ARGS,
                        propose_arc_fixes=propose_arc_fixes),
                   linters.Pyflakes(propose_arc_fixes=propose_arc_fixes),
                   linters.CustomPythonLinter(),
                   linters.Git(),
                   ),
        'javascript': (linters.Eslint(base_eslint_config, propose_arc_fixes),
                       linters.Git(),
                       ),
        'html': (linters.HtmlLinter(),
                 linters.Git(),
                 ),
        'jsx': (linters.Eslint(default_eslint_config, propose_arc_fixes),
                linters.Git(),
                ),
        'less': (linters.LessHint(),
                 linters.Git(),
                 ),
        'unknown': (linters.Git(),
                    ),
        }

    # Dict of {lint_processor: [(filename, contents)]}
    files_by_linter = {}

    num_lint_errors = 0
    num_framework_errors = 0
    for f in files_to_lint:
        file_lang = _lang(f, lang)
        lint_processors = processor_dict.get(file_lang, None)
        if lint_processors is None:
            if verbose:
                print '--- skipping %s (language unknown)' % f
            continue

        for lint_processor in lint_processors:
            # To make the lint errors look nicer, let's pass in the
            # filename relative to the current-working directory,
            # rather than using the abspath.
            files_by_linter.setdefault(lint_processor, []).append(
                    os.path.relpath(f))

    for lint_processor in files_by_linter:
        files = files_by_linter[lint_processor]
        try:
            if verbose:
                print '--- Running %s:' % lint_processor.__class__.__name__

            start_time = time.time()
            num_new_errors = lint_processor.process_files(files)
            num_lint_errors += num_new_errors
            elapsed = time.time() - start_time

            if verbose:
                print '%d errors (%.2f seconds)' % (num_new_errors, elapsed)
        except Exception, why:
            print "ERROR linting %r: %s" % (files, why)
            num_framework_errors += 1
            continue

    # If they asked for an extra linter to run over these files, do that.
    if extra_linter_filename:
        (extra_lint_errors, extra_framework_errors) = (
            _run_extra_linter(extra_linter_filename, files_to_lint, verbose))
        num_lint_errors += extra_lint_errors
        num_framework_errors += extra_framework_errors

    return (num_lint_errors, num_framework_errors)


if __name__ == '__main__':
    parser = optparse.OptionParser(USAGE)
    parser.add_option('--blacklist', choices=['yes', 'no', 'auto'],
                      default='auto',
                      help=('If yes, ignore files that are on the blacklist. '
                            'If no, do not consult the blacklist. '
                            'If auto, use the blacklist for directories listed'
                            ' on the commandline, but not for files. '
                            'Default: %default'))
    parser.add_option('--blacklist-filename',
                      default=_DEFAULT_BLACKLIST_PATTERN,
                      help=('The file to use as a blacklist. If the filename '
                            'starts with "<ancestor>/", then, for each file '
                            'to be linted, we take its blacklist to be from '
                            'the closest parent directory that contains '
                            'the (rest of the) blacklist filename.'
                            ' Default: %default'))
    parser.add_option('--extra-linter',
                      default=_DEFAULT_EXTRA_LINTER,
                      help=('A program to run more lint tests against.  It '
                            'can start with "<ancestor>/", like '
                            '--blacklist-filename.  Every file we lint '
                            'against, we also pass to the extra linter, '
                            'if it exists and is executable.'
                            ' Default: %default'))
    parser.add_option('--lang',
                      choices=[''] + list(set(_EXTENSION_DICT.itervalues())),
                      default='',
                      help=('Treat all input files as written in the given '
                            'language.  If empty, guess from extension.'))
    parser.add_option('--no-auto-pull', action='store_true', default=False,
                      help=("Don't try to update this repo once a day."))
    parser.add_option('--always-exit-0', action='store_true', default=False,
                      help=('Exit 0 even if there are lint errors (though we '
                            'will still exit non-zero if there are errors in '
                            'the lint framework itself). '
                            'Only useful when used with phabricator.'))
    parser.add_option('--propose-arc-fixes', action='store_true',
                      default=False,
                      help=('Propose patches that arc can apply to fix lint'
                            'errors. Only useful when used with phabricator.'))
    parser.add_option('--verbose', '-v', action='store_true', default=False,
                      help='Print information about what is happening.')

    options, args = parser.parse_args()
    if not args:
        args = ['.']

    # Once a day, we do a 'git pull' in our repo to make sure we are
    # the most up-to-date khan-linter we can be.
    if not options.no_auto_pull and _maybe_pull(options.verbose):
        # We have to re-exec ourselves since we may have changed.
        os.execv(sys.argv[0], sys.argv)

    # normal operation
    (num_lint_errors, num_framework_errors) = main(
        args,
        options.blacklist, options.blacklist_filename,
        options.extra_linter, options.lang,
        options.verbose, options.propose_arc_fixes)

    if options.always_exit_0:
        # If the framework itself had an error, we want to report that.
        sys.exit(num_framework_errors)
    else:
        # Don't exit with error code of 128+, which means 'killed by a signal'
        sys.exit(min(num_lint_errors + num_framework_errors, 127))
