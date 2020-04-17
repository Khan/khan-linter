#!/usr/bin/env python

"""Run some linters on files of various types."""


USAGE = """%prog [options] [files] ...

Run linters over the given files, or the current directory tree.

By default -- if no commandline arguments are given -- this runs the
linters on all non-blacklisted source files under the current
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
import logging
import optparse
import os
import re
import subprocess
import sys
import threading
import time
import traceback

import linters
import lint_util
import six

from six.moves import xrange


_DEFAULT_BLACKLIST_PATTERN = '<ancestor>/lint_blacklist.txt'
_DEFAULT_EXTRA_LINTER = '<ancestor_within_repo>/tools/runlint.sh'
_CWD = lint_util.get_real_cwd()

_BLACKLIST_CACHE = {}    # map from filename to its parsed contents (a set)

_LINTERS_BY_LANG = {}    # a cache of linters by language
# This will ultimately be overwritten by either the custom khan-linter
# logger setup in main or the root logger at logging time.
_LOGGER = None


# Used to distinguish error output from normal output from the extra-linters.
_LINTLINE_RE = re.compile(r'^[^:]*:\d+:', re.MULTILINE)


def _setup_custom_logger(verbose=False):
    """Configure logging to go to both stdout/stderr and a separate logfile.

    This logfile captures all logs from DEBUG level and up, which
    includes lint performance and timing stats which we need for profiling.
    """
    logger = logging.getLogger("khan-linter")
    logger.setLevel(logging.DEBUG)
    # Make sure that if a root-logger is set up, we don't send our messages
    # out via that root-logger as well.  I'm not sure why this happens, but
    # I think it can if one of our custom linters (say) calls logging.foo().
    logger.propagate = False
    formatter = logging.Formatter('%(message)s')

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    parent_dir = os.path.dirname(os.path.realpath(__file__))
    fh = logging.FileHandler(os.path.join(parent_dir, "lint_logfile.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def _get_logger():
    """Return either custom khan-lint logger or the root logger.

    We get the logger at time of logging and give the root
    logger as a backup option to account for when khan-linter
    functions are called within a subprocess from webapp.
    """
    return _LOGGER or logging.getLogger()


def _extended_fnmatch_compile(pattern):
    """RE-ify *, ?, etc, and also **.

    It also turns '*' into [^/]*, '?' into ., etc.  This is what
    fnmatch is supposed to do, but fnmatch turns '*' into '.*' which
    is not what we want.  We support '**', which turns into '.*',
    instead.

    For both * and ** we make sure that it doesn't match directories
    or files beginning with `.`.
    """
    retval = ''
    i = 0
    while i < len(pattern):
        if pattern[i] in '*?[':
            if retval.endswith('/'):
                # If we're at the start of a directory make sure we
                # don't match a dotfile (for *, **, ?, and [...]).
                retval += r'(?!\.)'

        if pattern[i] == '*':
            if pattern.startswith('**', i):
                # Match everything as long as it doesn't have a /. in it.
                retval += r'((?!/\.).)*'
                i += 1
            else:
                retval += '[^/]*'
        elif pattern[i] == '?':
            retval += '.'
        elif pattern[i] == '[':
            # Find the end of the [...]
            j = i + 1
            if pattern.startswith('!', j):     # [!...]
                j += 1
            if pattern.startswith(']', j):     # []...]
                j += 1
            j = pattern.find(']', j)
            if j == -1:   # must have something like 'a[b'
                retval += '\\['
            else:
                match = pattern[i + 1:j].replace('\\', '\\\\')
                if match[0] == '!':
                    match = '^' + match[1:]
                elif match[0] == '^':
                    match = '\\' + match
                retval += '[%s]' % match
                i = j
        else:
            retval += re.escape(pattern[i])
        i += 1

    return re.compile(retval + '$')


# If the code below this line has horrible syntax highlighting, check
# this out:  http://stackoverflow.com/questions/13210816/sublime-texts-syntax-highlighting-of-regexes-in-python-leaks-into-surrounding-c
_METACHAR_RE = re.compile(r'[[*?!]')


def _parse_one_blacklist_line(line):
    # We don't know if the blacklist line is intended to match a
    # directory or not, so we add both `line` and `line/**`, just in
    # case.  Even if line ends with a `/`, so we know it's a
    # directory, we still add `line` (with the trailing / cut off) to
    # make pruning easier.  As an optimization, if the file actually
    # exists, we check if it's a directory or not that way.
    retval = set()
    line = line.rstrip('/')
    if _METACHAR_RE.search(line):
        retval.add(_extended_fnmatch_compile(line))
        retval.add(_extended_fnmatch_compile(line + '/**'))
        # A leading '**/' is interpreted as '(.*/)?' -- that is,
        # '**/foo' matches 'foo', even though the regexp has a leading
        # '/'.  We just do that as multiple regexps.
        if line.startswith('**/'):
            retval.add(_extended_fnmatch_compile(line[len('**/'):]))
            retval.add(_extended_fnmatch_compile(line[len('**/'):] + '/**'))
    else:
        retval.add(os.path.normpath(line))
        if not os.path.isfile(line):
            retval.add(_extended_fnmatch_compile(line + '/**'))

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


def _is_toplevel_repository_dir(directory):
    """Returns if a directory is a git or mercurial directory.

    This works by searching for a file or directory named `.git` or `.hg` in
    the directory. This works for both submodules and normal repositories.
    """
    return (os.path.exists(os.path.join(directory, ".git")) or
            os.path.exists(os.path.join(directory, ".hg")))


# Map of a directory to the ancestor filename in the closest parent
# directory to the given directory (or possibly the given directory
# itself).  Ancestor-filenames are ones that can start with
# '<ancestor>/' or '<ancestor_within_repo>/'.
_ANCESTOR_DIR_CACHE = {}


def _resolve_ancestor(ancestor_pattern, file_to_lint):
    """If a_p starts with '<ancestor>/', replace based on file_to_lint.

    The rule is that we start at file_to_lint's directory, and replace
    '<ancestor>/' with that directory.  If the resulting filepath exists,
    return it.  Otherwise, go up one level in the directory tree and
    try again, replacing '<ancestor>/' with the parent-dir.  Continue
    until we succeed or get to /, at which point we return None.

    If ancestor_pattern starts with '<ancestor_within_repo>/', then we do the
    same thing as above except we also stop if we reach the top level of a
    repository or submodule.
    """
    if not ancestor_pattern:
        return None

    if ancestor_pattern.startswith('<ancestor>/'):
        ancestor_basename = ancestor_pattern[len('<ancestor>/'):]
        stop_at_repository = False
    elif ancestor_pattern.startswith('<ancestor_within_repo>/'):
        ancestor_basename = ancestor_pattern[len('<ancestor_within_repo>/'):]
        stop_at_repository = True
    else:
        return ancestor_pattern   # the 'pattern' is an actual filename

    # The hard case: resolve '<ancestor>/' or '<ancestor_within_repo>/' to the
    # proper directory.
    ancestor_dir = None
    if os.path.isdir(file_to_lint):
        d = file_to_lint
    else:
        d = os.path.dirname(file_to_lint)
    d = os.path.abspath(d)
    while os.path.dirname(d) != d:  # not at the root level (/) yet
        if (ancestor_pattern, d) in _ANCESTOR_DIR_CACHE:
            return _ANCESTOR_DIR_CACHE[(ancestor_pattern, d)]
        if os.path.exists(os.path.join(d, ancestor_basename)):
            ancestor_dir = d
            break
        if stop_at_repository and _is_toplevel_repository_dir(d):
            break
        d = os.path.dirname(d)

    # Now update _ANCESTOR_DIR_CACHE for all directories that need it.
    # We now know the proper ancestor file to use for ancestor_dir and
    # all the directories we saw beneath it.
    if ancestor_dir is None:   # never found a ancestor
        d = os.path.dirname(file_to_lint)
        while d != os.path.dirname(d):
            _ANCESTOR_DIR_CACHE[(ancestor_pattern, d)] = None
            if stop_at_repository and _is_toplevel_repository_dir(d):
                break
            d = os.path.dirname(d)
        return None
    else:
        ancestor_filename = os.path.join(ancestor_dir, ancestor_basename)
        d = os.path.dirname(file_to_lint)
        while d != os.path.dirname(ancestor_dir):
            _ANCESTOR_DIR_CACHE[(ancestor_pattern, d)] = ancestor_filename
            d = os.path.dirname(d)
        return ancestor_filename


def _file_in_blacklist(fname, blacklist_pattern):
    """True if fname, an absolute path, matches any entry in blacklist."""
    # The blacklist entries are taken to be relative to
    # blacklist_filename-root, so we need to relative-ize basename here.
    # TODO(csilvers): use os.path.relpath().
    blacklist_filename = _resolve_ancestor(blacklist_pattern, fname)
    if not blacklist_filename:
        return False
    blacklist_dir = os.path.abspath(os.path.dirname(blacklist_filename))
    fname = os.path.abspath(fname)
    if not fname.startswith(blacklist_dir):
        _get_logger().warning('WARNING: %s is not under the directory '
                              'containing the blacklist (%s), so we are '
                              'ignoring the blacklist'
                              % (fname, blacklist_dir))
    fname = fname[len(blacklist_dir) + 1:]   # +1 for the trailing '/'

    blacklist = _parse_blacklist(blacklist_filename)
    if fname in blacklist:
        return True

    # The blacklist can have regexp patterns in it, so we need to
    # check those too, one by one:
    for blacklist_entry in blacklist:
        if not isinstance(blacklist_entry, six.string_types):
            if blacklist_entry.match(fname):
                return True

    return False


def _files_under_directory(rootdir, blacklist_pattern):
    """Return a set of files under rootdir not in the blacklist."""
    retval = set()
    for root, dirs, files in os.walk(rootdir):
        # Prune the subdirs that are in the blacklist.  We go
        # backwards so we can use del.  (Weird os.walk() semantics:
        # calling del on an element of dirs suppresses os.walk()'s
        # traversal into that dir.)
        for i in xrange(len(dirs) - 1, -1, -1):
            absdir = os.path.join(root, dirs[i])
            if os.path.islink(absdir):
                _get_logger().debug('... skipping directory %s: is a symlink'
                                    % absdir)
                del dirs[i]
            elif _file_in_blacklist(absdir, blacklist_pattern):
                _get_logger().debug('... skipping directory %s: in blacklist'
                                    % absdir)
                del dirs[i]
        # Prune the files that are in the blacklist.
        for f in files:
            abspath = os.path.join(root, f)
            if _file_in_blacklist(abspath, blacklist_pattern):
                _get_logger().debug('... skipping file %s: in blacklist'
                                    % abspath)
                continue
            elif os.path.islink(abspath):
                _get_logger().debug('... skipping file %s: is a symlink'
                                    % abspath)
                continue
            retval.add(abspath)

    return retval


def find_files_to_lint(files_and_directories,
                       blacklist='auto',
                       blacklist_pattern=_DEFAULT_BLACKLIST_PATTERN,
                       verbose=None):
    if blacklist == 'yes':
        file_blacklist = blacklist_pattern
        dir_blacklist = blacklist_pattern
        _get_logger().debug('Using blacklist %s for all files'
                            % blacklist_pattern)
    elif blacklist == 'auto':
        file_blacklist = None
        dir_blacklist = blacklist_pattern
        _get_logger().debug('Using blacklist %s for files under directories'
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
        _get_logger().debug('Considering %s: blacklist %s'
                            % (f, blacklist_filename))

        if _file_in_blacklist(f, blacklist_for_f):
            _get_logger().debug('... skipping (in blacklist)')
        elif os.path.islink(f):
            _get_logger().debug('... skipping (is a symlink)')
        elif os.path.isdir(f):
            _get_logger().debug('... LINTING %s files under this directory' % (
                         'non-blacklisted' if dir_blacklist else 'all'))
            directories_to_lint.append(f)
        else:
            _get_logger().debug('... LINTING')
            files_to_lint.append(f)

    # TODO(csilvers): log if we skip a file in a directory because
    # it's in the blacklist?
    for directory in directories_to_lint:
        files_to_lint.extend(_files_under_directory(directory, dir_blacklist))

    files_to_lint.sort()    # just to be pretty
    return files_to_lint


_EXTENSION_DICT = {'.py': 'python',
                   '.js': 'javascript',
                   '.html': 'html',
                   '.jsx': 'javascript',
                   '.less': 'less',
                   '.yaml': 'yaml',
                   '.kt': 'kotlin',
                   '.go': 'go',
                   '.graphql': 'sdl',   # graphql "schema definition language"
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

    for (linter_filename, files) in six.iteritems(linter_to_files):
        if not os.access(linter_filename, os.R_OK | os.X_OK):
            continue
        files = sorted(files)
        _get_logger().debug('--- running extra linter %s on these files: %s'
                            % (linter_filename, files))
        # We always run this subprocess in verbose mode so that we get timing
        # stats for our logfile, but then we use the khan-linter logger and the
        # verbose flag to decide what to send to the console.
        p = subprocess.Popen([linter_filename, '--verbose', '-'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (stdout, stderr) = p.communicate(
            input='\n'.join(f.decode('utf-8') for f in files).encode('utf-8'))

        stdout = stdout.decode('utf-8')
        stderr = stdout.decode('utf-8')

        # If the subprocess returned 1, it's possible this was due to a
        # raised exception rather than a lint error.  We try to detect
        # this by checking if stdout has anything looking like a lint
        # log-line; if not, the output must be an exception.
        if p.returncode > 0 and not _LINTLINE_RE.search(stdout):
            _get_logger().error('ERROR running the extra linter %s on these '
                                'files: %s: %s' % (linter_filename, files,
                                                   stderr))
            num_framework_errors += 1
        else:
            # Log the stdout (lint errors) and stderr (timing stats and
            # other non-lint errors) seen by our subprocesses.
            _get_logger().debug(stdout + stderr)
            num_lint_errors += p.returncode
            if not verbose:
                # If we aren't in verbose mode, the debug logs above won't make
                # it to the console, so we print just the lint errors.
                lint_util.print_(stdout)

    return (num_lint_errors, num_framework_errors)


def _run_command_with_timeout(timeout_sec, *popen_args, **popen_kwargs):
    """Execute `cmd` in a subprocess and enforce timeout `timeout_sec` seconds.

    Return subprocess exit code on natural completion of the subprocess.
    Raise an exception if timeout expires before subprocess completes.

    Note that in python 3.2 (or the backported subprocess32 module) we
    could use the timeout arg to popen instead.

    Taken from http://www.ostricher.com/2015/01/python-subprocess-with-timeout/
    """
    proc = subprocess.Popen(*popen_args, **popen_kwargs)
    proc_thread = threading.Thread(target=proc.communicate)
    proc_thread.start()
    proc_thread.join(timeout_sec)
    if proc_thread.is_alive():
        # Process still running - kill it and raise timeout error
        try:
            proc.kill()
        except OSError:
            # The process finished between the `is_alive()` and `kill()`
            return proc.returncode
        # OK, the process was definitely killed
        raise RuntimeError('Timeout running %s/%s'
                           % (popen_args, popen_kwargs))
    # Process completed naturally - return exit code
    return proc.returncode


def _maybe_pull():
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

    # If we're not able to query the remote git repo, fail.
    with open(os.devnull, 'wb') as devnull:
        try:
            rc = _run_command_with_timeout(
                3,
                # This is an arbitrary git command that definitely
                # needs to contact the remote.  If you know of a
                # faster one, feel free to sub it in!
                ['git', 'ls-remote', 'origin', 'master'],
                stdout=devnull, stderr=devnull)
            if rc != 0:
                raise RuntimeError('git ls-remote returned %s' % rc)
        except RuntimeError as why:
            _get_logger().warning('Non-fatal error: not updating the '
                                  'khan-linter repo: %s' % why)
            return False

    # Update the last-pull time, and create an fd for the lockf call.
    with open('/tmp/khan-linter.pull', 'w') as f:
        # Phabricator often runs two linters at the same time, meaning
        # they could both contend for the 'git pull' call.  This lock
        # prevents that.  (It does mean that we pull twice, but that's
        # the safest way to make sure neither linter runs before the
        # update is complete.)
        fcntl.lockf(f, fcntl.LOCK_EX)
        _get_logger().debug('Updating the khan-linter repo')

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


def _find_base_config(file_to_lint, config_filename):
    """Return `config_filename` in the repo's root directory if it exists.

    If this file exists, it will replace khan-linter's default config file.

    Example use: for eslintc.

    If you'd like a repo to use khan-linter's eslintrc plus other stuff,
    create a .eslintrc in the root directory of that repo and have it
    include a field: "extends": "../devtoools/khan-linter/eslintrc"`

    If the custom eslintrc depends on any extra node modules, for
    plugins or parsers, these node modules should be referenced as
    relative to the eslintrc file, but without the preceeding "./" often
    used to denote relative paths. For example, if the parser module
    `babel-eslint` is in `repo/javascript/node_modules/babel-eslint` and
    the custom `.eslint` file is in `repo/.eslint`, then the path in the
    eslint file should be `javascript/node_modules/babel-eslint`.
    """
    if not file_to_lint:
        return None

    base_git = _resolve_ancestor('<ancestor>/.git', file_to_lint)
    if not base_git:
        return None
    base_directory = os.path.dirname(base_git)
    base_config = os.path.join(base_directory, config_filename)
    if os.path.exists(base_config):
        return base_config
    return None


def _get_linters_for_file(file_to_lint, lang, propose_arc_fixes):
    """Return the linters we wish to run for this file.

    We keep a cache of linters so that we can run each linter just one time
    against a set of files (rather than each file individually).

    For most languages, this is a simple mapping of lang -> list of linters,
    however for javascript and jsx we support each repo having a different
    eslintrc for configuring style. We need to do a bit more work to find the
    appropriate config file and cache the resulting Eslint objects.
    """
    if not _LINTERS_BY_LANG:
        # Initialize our linter cache based on runtime params.

        # A dict that maps from language (output of _lang) to a list of
        # processors.  None means that we skip files of this language.
        processor_dict = {
            'python': (linters.Flake8(logger=_get_logger(),
                                      propose_arc_fixes=propose_arc_fixes),
                       linters.CustomPythonLinter(logger=_get_logger()),
                       linters.Git(logger=_get_logger()),
                       ),
            # Note: this is the default eslinter, but see below for
            # how we override it for repos with their own eslintrc.
            'javascript': (linters.Eslint(os.path.join(_CWD, "eslintrc"),
                                          _get_logger(), propose_arc_fixes),
                           linters.Git(logger=_get_logger()),
                           ),
            'html': (linters.HtmlLinter(logger=_get_logger()),
                     linters.Git(logger=_get_logger()),
                     ),
            'less': (linters.LessHint(logger=_get_logger()),
                     linters.Git(logger=_get_logger()),
                     ),
            'kotlin': (linters.KtLint(logger=_get_logger()),
                       linters.Git(logger=_get_logger()),
                       ),
            'go': (linters.GoLint(logger=_get_logger()),
                   linters.Git(logger=_get_logger()),
                   ),
            # Note: this is the default yaml linter (which is a noop), but see
            # below for how we override it for repos with their own yaml linter
            # binary.
            'yaml': (linters.DelegatingLinter(None, logger=_get_logger()),
                     linters.Git(logger=_get_logger()),
                     ),
            'sdl': (
                linters.GraphqlSchemaLint(
                    os.path.join(_CWD, "graphql-schema-linterrc"),
                    _get_logger(), propose_arc_fixes),
                linters.Git(logger=_get_logger()),
            ),
            'unknown': (linters.Git(logger=_get_logger()),
                        ),
        }
        _LINTERS_BY_LANG.update(processor_dict)

    file_lang = _lang(file_to_lint, lang)

    # We support multiple configuration files for eslint and our graphql
    # schema linter, , which allows runlint to run against subrepos with
    # different configurations.
    if file_lang == 'javascript':
        eslint_config = _find_base_config(file_to_lint, '.eslintrc')
        if eslint_config:
            cache_key = "js-%s" % eslint_config
            if cache_key not in _LINTERS_BY_LANG:
                # Use the javascript linters, but replace the eslint
                # linter with one that uses the config for our repo.
                _LINTERS_BY_LANG[cache_key] = list(
                    _LINTERS_BY_LANG['javascript'])
                _LINTERS_BY_LANG[cache_key][0] = (
                    linters.Eslint(eslint_config, _get_logger(),
                                   propose_arc_fixes))
            return _LINTERS_BY_LANG[cache_key]

    if file_lang == 'sdl':
        schema_config = _find_base_config(
            file_to_lint, '.graphql-schema-linterrc')
        if schema_config:
            cache_key = "sdl-%s" % schema_config
            if cache_key not in _LINTERS_BY_LANG:
                # Use the sdl linters, but replace the schema
                # linter with one that uses the config for our repo.
                _LINTERS_BY_LANG[cache_key] = list(_LINTERS_BY_LANG['sdl'])
                _LINTERS_BY_LANG[cache_key][0] = (
                    linters.GraphqlSchemaLint(schema_config, _get_logger(),
                                              propose_arc_fixes))
            return _LINTERS_BY_LANG[cache_key]

    if file_lang == 'yaml':
        yaml_lint_binary = _find_base_config(
            file_to_lint, 'testing/yaml-test.js')
        if yaml_lint_binary:
            cache_key = "yaml-%s" % yaml_lint_binary
            if cache_key not in _LINTERS_BY_LANG:
                _LINTERS_BY_LANG[cache_key] = list(_LINTERS_BY_LANG['yaml'])
                _LINTERS_BY_LANG[cache_key][0] = (
                    linters.DelegatingLinter(argv=[yaml_lint_binary],
                                             logger=_get_logger()))
            return _LINTERS_BY_LANG[cache_key]

    return _LINTERS_BY_LANG.get(file_lang, None)


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
      propose_arc_fixes: append special strings to the end of lint lines where
        we know how to automatically fix the problem. `arc lint` consumes these
        special strings and prompts the user to see if they want to accept the
        patch.
      verbose: currently only used to determine printing stdout from the extra
        linter. Otherwise, khan-linter gets its verbose output by running
        _setup_custom_logger in __main__. Other callers cannot be verbose.

    Returns:
      A pair: (number of lint errors seen, number of unlintable files seen).
      (0, 0) means lint-cleanliness.  If the second value is non-zero, it
      means there was a problem in the lint framework itself somewhere.
    """
    files_to_lint = find_files_to_lint(files_and_directories, blacklist,
                                       blacklist_pattern)
    _get_logger().debug('Beginning to lint %s file(s)' % len(files_to_lint))
    # Dict of {lint_processor: [(filename, contents)]}
    files_by_linter = {}

    num_lint_errors = 0
    num_framework_errors = 0
    for f in files_to_lint:
        lint_processors = _get_linters_for_file(f, lang, propose_arc_fixes)

        if lint_processors is None:
            _get_logger().debug('--- skipping %s (language unknown)' % f)
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
            _get_logger().debug('--- Running %s:'
                                % lint_processor.__class__.__name__)

            start_time = time.time()
            num_new_errors = lint_processor.process_files(files)
            num_lint_errors += num_new_errors
            elapsed = time.time() - start_time
            _get_logger().debug('%d errors (%.2f seconds)'
                                % (num_new_errors, elapsed))
        except Exception:
            _get_logger().error(u"ERROR linting %r with %s:\n%s" % (
                          files, type(lint_processor), traceback.format_exc()))
            num_framework_errors += 1
            continue

    # If they asked for an extra linter to run over these files, do that.
    if extra_linter_filename:
        start_time = time.time()
        (extra_lint_errors, extra_framework_errors) = (
            _run_extra_linter(extra_linter_filename, files_to_lint, verbose))
        num_lint_errors += extra_lint_errors
        num_framework_errors += extra_framework_errors

        elapsed = time.time() - start_time
        _get_logger().debug('%d errors (%.2f seconds)'
                            % (extra_lint_errors, elapsed))

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
                      choices=[''] + list(set(_EXTENSION_DICT.values())),
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
        # We used to lint the whole directory-tree when args was null,
        # but we want to be able to run
        #   git ls-files ... | xargs runlint.py
        # and we want it to be a noop if git does not find any files.
        # (If we were linux-only we'd use `xargs -r`, but we are os x.)
        sys.exit(0)

    _LOGGER = _setup_custom_logger(options.verbose)

    # Once a day, we do a 'git pull' in our repo to make sure we are
    # the most up-to-date khan-linter we can be.
    if not options.no_auto_pull and _maybe_pull():
        # We have to re-exec ourselves since we may have changed.
        os.execv(sys.argv[0], sys.argv)
        # We should also clear the lint logfile here so it doesn't get
        # too long. TODO(jacqueline): Upload the logfile to GCS before
        # clearing to send data for our profiler.
        open(os.path.join(_CWD, 'lint_logfile.log'), 'w').close()

    # normal operation
    (num_lint_errors, num_framework_errors) = main(
        args,
        options.blacklist, options.blacklist_filename,
        options.extra_linter, options.lang, options.verbose,
        options.propose_arc_fixes)

    if options.always_exit_0:
        # If the framework itself had an error, we want to report that.
        sys.exit(num_framework_errors)
    else:
        # Don't exit with error code of 128+, which means 'killed by a signal'
        sys.exit(min(num_lint_errors + num_framework_errors, 127))
