#!/usr/bin/env python

"""Run some linters on python files.

The current linters run are pep8 and pyflakes.

TODO(benkomalo): get rid of the version in https://github.com/Khan/analytics
    (or use a sub-repo?)
"""


USAGE = """%prog [options] [files] ...

Run linters over the given files, or the current directory tree.

By default -- if no commandline arguments are given -- this runs the
linters on all non-blacklisted python file under the current
directory.  The blacklist is in runlint_blacklist.txt

If commandline arguments are given, this runs the linters on all the
files listed on the commandline, regardless of their presence in the
blacklist.

This script automatically determines the linter to run based on the
filename extension.  (This can be overridden with the --lang flag.)
Files with unknown or unsupported extensions will be skipped.
"""

import cStringIO
import fnmatch
import optparse
import os
import re
import sys

import closure_linter.gjslint
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


_BLACKLIST_FILE = os.path.join(os.path.dirname(__file__),
                               'runlint_blacklist.txt')


# TODO(csilvers): move python stuff to its own file, so this file
# is just the driver.

# W291 trailing whitespace
# W293 blank line contains whitespace
# W391 blank line at end of file
_DEFAULT_PEP8_ARGS = ['--repeat',
                      '--ignore=W291,W293,W391']


def _parse_blacklist(blacklist_filename):
    """Read from blacklist filename and returns a set of the contents.

    Blank lines and those that start with # are ignored.

    Arguments:
       blacklist_filename: the name of the blacklist file

    Returns:
       A set of all the paths listed in blacklist_filename.
       These paths may be filename strings, directory name strings,
       or re objects (for blacklist entries with '*'/etc in them).
    """
    retval = set()
    contents = open(blacklist_filename).readlines()
    for line in contents:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if re.search(r'[[*?!]', line):   # has a char meaningful to glob()
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
            retval.add(re.compile(re_prefix + fnmatch_re))
        else:
            retval.add(line)
    return retval


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

    def _process_one_line(self, output_line, contents_lines):
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

        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in closure_linter_stdout.readlines():
            self._num_errors += self._process_one_line(output_line,
                                                       contents_lines)

    def num_errors(self):
        """A count of all the errors we've seen (and emitted) so far."""
        return self._num_errors


def _file_in_blacklist(fname, blacklist):
    """Checks whether fname matches any entry in blacklist."""
    # The blacklist entries must be normalized, so normalize fname too.
    fname = os.path.normpath(fname)
    if fname in blacklist:
        return True

    # The blacklist can have regexp patterns in it, so we need to
    # check those too, one by one:
    for blacklist_entry in blacklist:
        if not isinstance(blacklist_entry, basestring):
            if blacklist_entry.match(fname):
                return True

    return False


def _files_under_directory(rootdir, blacklist):
    """Return a set of files under rootdir not in the blacklist."""
    retval = set()
    for root, dirs, files in os.walk(rootdir):
        # Prune the subdirs that are in the blacklist.  We go
        # backwards so we can use del.  (Weird os.walk() semantics:
        # calling del on an element of dirs suppresses os.walk()'s
        # traversal into that dir.)
        for i in xrange(len(dirs) - 1, -1, -1):
            if _file_in_blacklist(os.path.join(root, dirs[i]), blacklist):
                del dirs[i]
        # Prune the files that are in the blacklist.
        for f in files:
            if _file_in_blacklist(os.path.join(root, f), blacklist):
                continue
            retval.add(os.path.join(root, f))
    return retval


_EXTENSION_DICT = {'.py': 'python',
                   '.js': 'javascript',
                   }


def _lang(filename, lang_option):
    """Returns a string representing the language filename is written in."""
    if lang_option:            # the user specified the langauge explicitly
        return lang_option
    extension = os.path.splitext(filename)[1]
    return _EXTENSION_DICT.get(extension, 'unknown')


def main(files, directories, options):
    """Calls the appropriate linters on all given files and directory trees."""
    # A dict that maps from language (output of _lang) to a list of processors.
    # None means that we skip files of this language.
    processor_dict = {
        'python': (Pep8([sys.argv[0]] + _DEFAULT_PEP8_ARGS),
                   Pyflakes(),
                   ),
        'javascript': (ClosureLinter(),
                       ),
        'unknown': None,
        }

    if options.blacklist == 'yes':
        blacklist = _parse_blacklist(_BLACKLIST_FILE)
        files = [f for f in files if os.path.normpath(f) not in blacklist]
    else:
        blacklist = None

    # Log explicitly listed files that we're skipping because we don't
    # know how to lint them.  (But don't log implicitly found files
    # found in directory-trees.)
    known_language_files = []
    for f in files:
        lang = _lang(f, options.lang)
        if processor_dict.get(lang, None) is None:
            print ("SKIPPING %s: can't lint language '%s' (c.f. --lang)"
                   % (f, lang))
        else:
            known_language_files.append(f)
    files = known_language_files

    for directory in (directories or []):
        # We pass in the blacklist here to make it easy to blacklist dirs.
        files.extend(_files_under_directory(directory, blacklist or []))

    num_errors = 0
    for f in files:
        lang = _lang(f, options.lang)
        lint_processors = processor_dict.get(lang, None)
        if lint_processors is None:
            continue

        try:
            contents = open(f, 'U').read()
        except (IOError, OSError), why:
            print "SKIPPING %s: %s" % (f, why.args[1])
            num_errors += 1
            continue

        for lint_processor in lint_processors:
            lint_processor.process(f, contents)

    # Count up all the errors we've seen:
    for lint_processors in processor_dict.itervalues():
        for lint_processor in (lint_processors or []):
            num_errors += lint_processor.num_errors()
    return num_errors


if __name__ == '__main__':
    parser = optparse.OptionParser(USAGE)
    parser.add_option('--blacklist', choices=['yes', 'no'],
                      # By default, we ignore the blacklist for explicitly
                      # specified files, but not when traversing under '.'.
                      # TODO(csilvers): ignore --flags when doing this check.
                      default='no' if sys.argv[1:] else 'yes',
                      help=('If yes, ignore files that are on the blacklist. '
                            'If no, do not consult the blacklist.')),
    parser.add_option('--lang',
                      choices=[''] + list(set(_EXTENSION_DICT.itervalues())),
                      default='',
                      help=('Treat all input files as written in the given '
                            'language.  If empty, guess from extension.'))
    parser.add_option('--always-exit-0', action='store_true', default=False,
                      help=('Exit 0 even if there are lint errors. '
                            'Only useful when used with phabricator.'))

    options, args = parser.parse_args()
    if args:
        num_errors = main(files=args, directories=[], options=options)
    else:
        num_errors = main(files=[], directories=['.'], options=options)

    if options.always_exit_0:
        sys.exit(0)
    else:
        # Don't exit with error code of 128+, which means 'killed by a signal'
        sys.exit(min(num_errors, 127))
