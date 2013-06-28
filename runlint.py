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
as well, passing in all the files listed on the commandline.
Any such program must give output in the canonical form:
   filename:linenum: E<error_code> error message
and its exit code should be the number of lint errors seen.

This script automatically determines the linter to run based on the
filename extension.  (This can be overridden with the --lang flag.)
Files with unknown or unsupported extensions will be skipped.
"""

import cStringIO
import fnmatch
import optparse
import os
import re
import subprocess
import sys

import closure_linter.gjslint
import static_content_refs
try:
    import pep8
except ImportError, why:
    # TODO(csilvers): don't die yet, only if trying to lint python.
    sys.exit('FATAL ERROR: %s.  Install pep8 via "pip install pep8"' % why)
try:
    from pyflakes.scripts import pyflakes
except ImportError, why:
    sys.exit('FATAL ERROR: %s.  Install pyflakes via "pip install pyflakes"'
             % why)


_DEFAULT_BLACKLIST_PATTERN = '<ancestor>/lint_blacklist.txt'
_DEFAULT_EXTRA_LINTER = '<ancestor>/tools/runlint.py'
# TODO(csilvers): delete the next line to enable the extra linter, once
#                 it's faster to start up.
_DEFAULT_EXTRA_LINTER = ''


# TODO(csilvers): move python stuff to its own file, so this file
# is just the driver.

# W291 trailing whitespace
# W293 blank line contains whitespace
# W391 blank line at end of file
_DEFAULT_PEP8_ARGS = ['--repeat',
                      '--ignore=W291,W293,W391']


def _capture_stdout_of(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) and return (fn_retval, fn_stdout_output_fp)."""
    try:
        orig_stdout = sys.stdout
        sys.stdout = cStringIO.StringIO()
        retval = fn(*args, **kwargs)
        sys.stdout.reset()    # so new read()/readlines() calls will return
        return (retval, sys.stdout)
    finally:
        sys.stdout = orig_stdout


class Pep8(object):
    """Linter for python.  process() processes one file."""
    def __init__(self, pep8_args):
        pep8.process_options(pep8_args + ['dummy'])
        self._num_errors = 0

    def _munge_output_line(self, line):
        """Modify the line to have the canonical form for lint lines."""
        # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
        # Pep8 already has that form, so we're good.  We only need to
        # strip the trailing newline.
        return line.rstrip()

    def _process_one_line(self, output_line, contents_lines):
        """If line is an 'error', print it and return 1.  Else return 0.

        pep8 prints all errors to stdout.  But we want to ignore some
        'errors' that are ok for us but cannot be suppressed via pep8
        flags, such as lines marked with @Nolint.  To do this, we
        intercept stdin and remove these lines.

        Arguments:
           output_line: one line of the pep8 error-output
           contents_lines: the contents of the file being linted,
              as a list of lines.

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        # Get the lint message to a canonical format so we can parse it.
        lintline = self._munge_output_line(output_line)

        bad_linenum = int(lintline.split(':', 2)[1])   # first line is '1'
        bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index

        if '@Nolint' in bad_line:
            return 0

        # We allow lines to be arbitrarily long if they are urls,
        # since splitting urls at 80 columns can be annoying.
        if ('E501 line too long' in lintline and
            ('http://' in bad_line or 'https://' in bad_line)):
            return 0

        # We sometimes embed json in docstrings (as documentation of
        # command output), and don't want to have to do weird
        # line-wraps for that.
        # We do a cheap check for a plausible json-like line: starts
        # and ends with a ".  (The end-check is kosher because only
        # strings can be really long in our use-case.)  If that check
        # passes, we do a simple syntax-check that we're in a
        # docstring: going up until we see a line with a """, the line
        # above it starts with 'def' or 'class' (we do some simple
        # checking for multi-line def's).  This can be fooled, but
        # should work well enough.
        if ('E501 line too long' in lintline and
            bad_line.lstrip().startswith('"') and
            bad_line.rstrip(',\n').endswith('"')):
            for linenum in xrange(bad_linenum - 1, 0, -1):
                if (contents_lines[linenum].lstrip().startswith('"""') or
                    contents_lines[linenum].lstrip().startswith("'''")):
                    break
            # Now check that the line before the """ is a def or class.
            # Since def's (and classes) can be multiple lines long, we
            # may have to check backwards a few lines.  We basically look
            # at previous lines until we reach a line that starts with
            # def or class (good), a line with a """ (bad, it means the
            # """ above was ending a docstring, not starting one) or a
            # blank line (bad, it means the """ is in some random place).
            for prev_linenum in xrange(linenum - 1, -1, -1):
                prev = contents_lines[prev_linenum].strip()
                if (not prev or
                    prev.startswith('"""') or prev.startswith("'''")):
                    break
                if prev.startswith('def ') or prev.startswith('class '):
                    return 0

        # OK, looks like it's a legitimate error.
        print lintline
        return 1

    def process(self, f, contents_of_f):
        contents_lines = contents_of_f.splitlines(True)

        (num_candidate_errors, pep8_stdout) = _capture_stdout_of(
            pep8.Checker(f, lines=contents_lines).check_all)

        # Go through the output and remove the 'actually ok' lines.
        if num_candidate_errors == 0:
            return

        for output_line in pep8_stdout.readlines():
            self._num_errors += self._process_one_line(output_line,
                                                       contents_lines)

    def num_errors(self):
        """A count of all the errors we've seen (and emitted) so far."""
        return self._num_errors


class Pyflakes(object):
    """Linter for python.  process() processes one file."""
    def __init__(self):
        self._num_errors = 0

    def _munge_output_line(self, line):
        """Modify the line to have the canonical form for lint lines."""
        # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
        # pyflakes just needs to add the "E<code>" or "W<code>".  For
        # now we only use E, since everything we print is an error.
        # pyflakes doesn't have an error code, so we just use
        # 'pyflakes'.  We also strip the trailing newline.
        (file, line, error) = line.rstrip().split(':')
        return '%s:%s: E=pyflakes=%s' % (file, line, error)

    def _process_one_line(self, output_line, contents_lines):
        """If line is an 'error', print it and return 1.  Else return 0.

        pyflakes prints all errors to stdout.  But we want to ignore
        some 'errors' that are ok for us: code like
          try:
             import unittest2 as unittest
          except ImportError:
             import unittest
        To do this, we intercept stdin and remove these lines.

        Arguments:
           output_line: one line of the pyflakes error-output
           contents_lines: the contents of the file being linted,
              as a list of lines.

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        # The 'try/except ImportError' example described above.
        if 'redefinition of unused' in output_line:
            return 0

        # We follow python convention of allowing an unused variable
        # if it's named '_' or starts with 'unused_'.
        if ('assigned to but never used' in output_line and
            ("local variable '_'" in output_line or
             "local variable 'unused_" in output_line)):
            return 0

        # Get rid of some warnings too.
        if 'unable to detect undefined names' in output_line:
            return 0

        # -- The next set of warnings need to look at the error line.
        # Get the lint message to a canonical format so we can parse it.
        lintline = self._munge_output_line(output_line)

        bad_linenum = int(lintline.split(':', 2)[1])   # first line is '1'
        bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index

        # If the line has a nolint directive, ignore it.
        if '@Nolint' in bad_line:
            return 0

        # An old nolint directive that's specific to imports
        if ('@UnusedImport' in bad_line and
            'imported but unused' in lintline):
            return 0

        # OK, looks like it's a legitimate error.
        print lintline
        return 1

    def process(self, f, contents_of_f):
        # pyflakes's ast-parser fails if the file doesn't end in a newline,
        # so make sure it does.
        if not contents_of_f.endswith('\n'):
            contents_of_f += '\n'
        (num_candidate_errors, pyflakes_stdout) = _capture_stdout_of(
            pyflakes.check, contents_of_f, f)

        # Now go through the output and remove the 'actually ok' lines.
        if num_candidate_errors == 0:
            return

        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in pyflakes_stdout.readlines():
            self._num_errors += self._process_one_line(output_line,
                                                       contents_lines)

    def num_errors(self):
        """A count of all the errors we've seen (and emitted) so far."""
        return self._num_errors


class ClosureLinter(object):
    """Linter for javascript.  process() processes one file."""
    def __init__(self):
        self._num_errors = 0

    _MUNGE_RE = re.compile(r'\((?:New Error )?-?(\d+)\)', re.I)

    def _munge_output_line(self, line):
        """Modify the line to have the canonical form for lint lines."""
        # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
        # Closure --unix_mode form: <file>:<line>:(<code>) <msg>
        # We just need to remove some parens and add an E.
        # We also strip the trailing newline.
        return self._MUNGE_RE.sub(r'E\1', line.rstrip(), count=1)

    def _process_one_line(self, output_line, contents_lines,
                          console_log_is_ok):
        """If line is an 'error', print it and return 1.  Else return 0.

        closure-linter prints all errors to stdout.  But we want to
        ignore some 'errors' that are ok for us, in particular ones
        that have been commented out with @Nolint.

        Arguments:
           output_line: one line of the closure-linter error-output
           contents_lines: the contents of the file being linted,
              as a list of lines.

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        # We often have console.log in development code, so don't treat
        # it as an error.
        if ('reference to console.log - Leftover debug code?' in output_line
            and console_log_is_ok):
            return 0

        # Get the lint message to a canonical format so we can parse it.
        lintline = self._munge_output_line(output_line)

        bad_linenum = int(lintline.split(':', 2)[1])   # first line is '1'
        bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index

        # If the line has a nolint directive, ignore it.
        if '@Nolint' in bad_line:
            return 0

        # Otherwise, it's a legitimate error.
        print lintline
        return 1

    def process(self, f, contents_of_f):
        (has_any_errors, closure_linter_stdout) = _capture_stdout_of(
            closure_linter.gjslint.main,
            # TODO(csilvers): could pass in contents_of_f, though it's
            # work to thread it through main() and Run() and into Check().
            argv=[closure_linter.gjslint.__file__,
                  '--nobeep', '--unix_mode', f])

        # Now go through the output and remove the 'actually ok' lines.
        if not has_any_errors:
            return

        # We allow console.log messages in the deploy/ directory, and
        # in javascript/test/.
        console_log_is_ok = (
            ('deploy' + os.sep) in f or (os.sep + 'test' + os.sep) in f)

        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in closure_linter_stdout.readlines():
            self._num_errors += self._process_one_line(output_line,
                                                       contents_lines,
                                                       console_log_is_ok)

    def num_errors(self):
        """A count of all the errors we've seen (and emitted) so far."""
        return self._num_errors


class HtmlLinter(object):
    """Linter for html.  process() processes one file.

    The main thing we look for with html is that the static images
    are properly escaped using the |static_url filter.  This is
    applied only to files in the 'templates' directory.
    """
    def __init__(self):
        self._num_errors = 0

    def process(self, f, contents_of_f):
        if ('templates' + os.sep) in f:
            # s_c_r.lint_one_file() happily ignores @Nolint lines for us.
            errors = static_content_refs.lint_one_file(f, contents_of_f)
            for (fname, linenum, colnum, unused_endcol, msg) in errors:
                # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
                print ('%s:%s:%s: E=static_url= %s'
                       % (fname, linenum, colnum, msg))
            self._num_errors += len(errors)

    def num_errors(self):
        """A count of all the errors we've seen (and emitted) so far."""
        return self._num_errors


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


def _file_in_blacklist(fname, blacklist_pattern):
    """Checks whether fname matches any entry in blacklist."""
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


def _files_under_directory(rootdir, blacklist_pattern):
    """Return a set of files under rootdir not in the blacklist."""
    retval = set()
    for root, dirs, files in os.walk(rootdir):
        # Prune the subdirs that are in the blacklist.  We go
        # backwards so we can use del.  (Weird os.walk() semantics:
        # calling del on an element of dirs suppresses os.walk()'s
        # traversal into that dir.)
        for i in xrange(len(dirs) - 1, -1, -1):
            if _file_in_blacklist(os.path.join(root, dirs[i]),
                                  blacklist_pattern):
                del dirs[i]
        # Prune the files that are in the blacklist.
        for f in files:
            if _file_in_blacklist(os.path.join(root, f), blacklist_pattern):
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
        files_to_lint.extend(_files_under_directory(directory, dir_blacklist))

    files_to_lint.sort()    # just to be pretty
    return files_to_lint


_EXTENSION_DICT = {'.py': 'python',
                   '.js': 'javascript',
                   '.html': 'html',
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
    num_errors = 0

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
        group_size = 100
        files = sorted(files)
        while files:
            if verbose:
                print ('--- running extra linter: %s %s'
                       % (linter_filename, ' '.join(files[:group_size])))
            rc = subprocess.call([linter_filename] + files[:group_size])
            # extra_linter should return the number of errors seen
            num_errors += rc
            files = files[group_size:]

    return num_errors


def main(files_and_directories,
         blacklist='auto', blacklist_pattern=_DEFAULT_BLACKLIST_PATTERN,
         extra_linter_filename=_DEFAULT_EXTRA_LINTER, lang='', verbose=False):
    """Call the appropriate linters on all given files and directory trees.

    Arguments:
      files_and_directories: a list/set/etc of files to lint, and/or
         a list/setetc of directories to lint all files under
      blacklist: 'yes', 'no', or 'auto', as described by --help
      blacklist_pattern: where to read the blacklist, as described by --help
      extra_linter_filename: what auxilliary linter to run, described by --help
      lang: the language to interpret all files to be in, or '' to auto-detect
      verbose: print messages about what we're doing, to stdout

    Returns:
      The number of errors seen while linting.  0 means lint-cleanliness!
    """
    # A dict that maps from language (output of _lang) to a list of processors.
    # None means that we skip files of this language.
    processor_dict = {
        'python': (Pep8([sys.argv[0]] + _DEFAULT_PEP8_ARGS),
                   Pyflakes(),
                   ),
        'javascript': (ClosureLinter(),
                       ),
        'html': (HtmlLinter(),
                 ),
        'unknown': None,
        }

    files_to_lint = find_files_to_lint(files_and_directories,
                                       blacklist, blacklist_pattern, verbose)

    num_errors = 0
    for f in files_to_lint:
        file_lang = _lang(f, lang)
        lint_processors = processor_dict.get(file_lang, None)
        if lint_processors is None:
            if verbose:
                print '--- skipping %s (language unknown)' % f
            continue

        try:
            contents = open(f, 'U').read()
        except (IOError, OSError), why:
            print "SKIPPING lint of %s: %s" % (f, why.args[1])
            num_errors += 1
            continue

        if verbose:
            print '--- linting %s (%s)' % (f, file_lang)
        for lint_processor in lint_processors:
            # To make the lint errors look nicer, let's pass in the
            # filename relative to the current-working directory,
            # rather than using the abspath.
            try:
                lint_processor.process(os.path.relpath(f), contents)
            except Exception, why:
                print "ERROR linting %s: %s" % (f, why)
                num_errors += 1
                continue

    # Count up all the errors we've seen:
    for lint_processors in processor_dict.itervalues():
        for lint_processor in (lint_processors or []):
            num_errors += lint_processor.num_errors()

    # If they asked for an extra linter to run over these files, do that.
    if extra_linter_filename:
        num_errors += _run_extra_linter(extra_linter_filename, files_to_lint,
                                        verbose)

    return num_errors


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
    parser.add_option('--always-exit-0', action='store_true', default=False,
                      help=('Exit 0 even if there are lint errors. '
                            'Only useful when used with phabricator.'))
    parser.add_option('--verbose', '-v', action='store_true', default=False,
                      help='Print information about what is happening.')

    options, args = parser.parse_args()
    if not args:
        args = ['.']
    num_errors = main(args,
                      options.blacklist, options.blacklist_filename,
                      options.extra_linter, options.lang,
                      options.verbose)

    if options.always_exit_0:
        sys.exit(0)
    else:
        # Don't exit with error code of 128+, which means 'killed by a signal'
        sys.exit(min(num_errors, 127))
