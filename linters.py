"""Linters process files or lists of files for correctness."""

import cStringIO
import itertools
import os
import re
import subprocess
import sys

import lint_util

# Add vendor path so we can find (our packaged versions of) pep8 and pyflakes.
_CWD = lint_util.get_real_cwd()
_parent_dir = os.path.abspath(_CWD)
_vendor_dir = os.path.join(_parent_dir, 'vendor')
sys.path.append(_vendor_dir)

import static_content_refs
import pep8
from pyflakes.scripts import pyflakes


class Linter(object):
    """Superclass for all linters.

    When subclassing, override either process_files or process (or both,
    though if you override process_files then it doesn't matter what
    process does).
    """
    def process_files(self, files):
        """Print lint errors for a list of filenames and return error count."""
        num_errors = 0
        for f in files:
            try:
                contents = open(f, 'U').read()
            except (IOError, OSError), why:
                print "SKIPPING lint of %s: %s" % (f, why.args[1])
                num_errors += 1
                continue
            num_errors += self.process(f, contents)
        return num_errors

    def process(self, file, contents):
        """Lint one file given its path and contents, returning error count."""
        raise NotImplementedError("Subclasses must override process()")


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


class Pep8(Linter):
    """Linter for python.  process() processes one file."""
    def __init__(self, pep8_args, propose_arc_fixes=False):
        pep8.process_options(pep8_args + ['dummy'])
        self._propose_arc_fixes = propose_arc_fixes

    def _munge_output_line(self, line):
        """Modify the line to have the canonical form for lint lines."""
        # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
        # Pep8 already has that form, so we're good.  We only need to
        # strip the trailing newline.
        return line.rstrip()

    def _maybe_add_arc_fix(self, lintline, bad_line):
        """Optionally add a patch for arc lint to use for autofixing."""
        if not self._propose_arc_fixes:
            return lintline

        errcode = lintline.split(' ')[1]

        # expected 2 blank lines, found 1
        if errcode == 'E302':
            return lintline + lint_util.propose_arc_fix_str('', '\n')

        # at least two spaces before inline comment
        if errcode == 'E261':
            return lintline + lint_util.propose_arc_fix_str('', ' ')

        return lintline

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
            bad_line.rstrip(',\n').endswith('"') and
            bad_linenum):

            for linenum in xrange(bad_linenum, 0, -1):
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
        print self._maybe_add_arc_fix(lintline, bad_line)
        return 1

    def process(self, f, contents_of_f):
        contents_lines = contents_of_f.splitlines(True)

        (num_candidate_errors, pep8_stdout) = _capture_stdout_of(
            pep8.Checker(f, lines=contents_lines).check_all)

        # Go through the output and remove the 'actually ok' lines.
        if num_candidate_errors == 0:
            return 0

        num_errors = 0
        for output_line in pep8_stdout.readlines():
            num_errors += self._process_one_line(output_line,
                                                 contents_lines)
        return num_errors


class Pyflakes(Linter):
    """Linter for python.  process() processes one file."""
    def __init__(self, propose_arc_fixes=False):
        self._propose_arc_fixes = propose_arc_fixes

    def _munge_output_line(self, line):
        """Modify the line to have the canonical form for lint lines."""
        # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
        # pyflakes just needs to add the "E<code>" or "W<code>".  For
        # now we only use E, since everything we print is an error.
        # pyflakes doesn't have an error code, so we just use
        # 'pyflakes'.  We also strip the trailing newline.
        (file, line, error) = line.rstrip().split(':')
        return '%s:%s:1: E=pyflakes=%s' % (file, line, error)

    def _maybe_add_arc_fix(self, lintline, bad_line):
        """Optionally add a patch for arc lint to use for autofixing."""
        if not self._propose_arc_fixes:
            return lintline

        if 'imported but unused' in lintline:
            return lintline + lint_util.propose_arc_fix_str(bad_line + '\n',
                                                            '')

        return lintline

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
        print self._maybe_add_arc_fix(lintline, bad_line)
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
            return 0

        num_errors = 0
        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in pyflakes_stdout.readlines():
            num_errors += self._process_one_line(output_line,
                                                 contents_lines)
        return num_errors


class CustomPythonLinter(Linter):
    """A linter for generic python errors that are not caught by pep8/pyflakes.

    This is a linter for general (as opposed to application-specific)
    python errors that are not caught by third-party linters.  We add
    those checks here.
    """
    def _bad_super(self, line):
        # We don't want this linter to fire on this line itself!
        return ('super(type(self)' in line or      # @Nolint
                'super(self.__class__' in line)    # @Nolint

    def process(self, f, contents_of_f):
        num_errors = 0
        for (linenum_minus_1, line) in enumerate(contents_of_f.splitlines()):
            if '@Nolint' in line:
                continue

            if self._bad_super(line):
                # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
                print ('%s:%s: E999 first argument to super() must be '
                       'an explicit classname, not type(self)'
                       % (f, linenum_minus_1 + 1))
                num_errors += 1

        return num_errors


class Git(Linter):
    """Complain if the file has git merge-conflict markers in it.

    git will merrily let you 'resolve' a file that still has merge
    conflict markers in it.  This lint check will hopefully catch
    that.
    """
    # We don't check for ======= because it might legitimately be in
    # a file (for purposes other than as a git conflict marker).
    _MARKERS = ('<' * 7, '|' * 7, '>' * 7)
    _MARKERS_RE = re.compile(r'^(%s)( |$)'
                             % '|'.join(re.escape(m) for m in _MARKERS),
                             re.MULTILINE)

    def process(self, f, contents_of_f):
        # Ignore files that git thinks are binary; those don't ever
        # get merge conflict markers.  This is how we check, sez
        # http://stackoverflow.com/questions/6119956/how-to-determine-if-git-handles-a-file-as-binary-or-as-text:
        if '\0' in contents_of_f[:8000]:
            return 0      # a binary file

        num_errors = 0
        for m in self._MARKERS_RE.finditer(contents_of_f):
            linenum = contents_of_f.count('\n', 0, m.start()) + 1
            print ('%s:%s:1: E1 git conflict marker "%s" found'
                   % (f, linenum, m.group(1)))
            num_errors += 1
        return num_errors


class JsHint(Linter):
    """Linter for javascript.  process() processes one file."""
    def __init__(self, propose_arc_fixes=False):
        self._propose_arc_fixes = propose_arc_fixes

    def _maybe_add_arc_fix(self, lintline, bad_line):
        """Optionally add a patch for arc lint to use for autofixing."""
        if not self._propose_arc_fixes:
            return lintline

        errcode = lintline.split(' ')[1]

        # W033: Missing semicolon
        if errcode == 'W033':
            return lintline + lint_util.propose_arc_fix_str('', ';')

        return lintline

    def _process_one_line(self, filename, output_line, contents_lines):
        """If line is an 'error', print it and return 1.  Else return 0.

        jshint prints all errors to stdout.  But we want to
        ignore some 'errors' that are ok for us, in particular ones
        that have been commented out with @Nolint.

        Arguments:
           filename: path to file being linted
           output_line: one line of the jshint error-output
           contents_lines: the contents of the file being linted,
              as a list of lines.

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        # output_line is like:
        #   <file>:<line>:<col>: W<code> <message>
        # which is just what we need!
        bad_linenum = int(output_line.split(':', 2)[1])   # first line is '1'
        bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index

        # If the line has a nolint directive, ignore it.
        if '@Nolint' in bad_line:
            return 0

        print self._maybe_add_arc_fix(output_line, bad_line)
        return 1

    def process(self, f, contents_of_f, jshint_lines):
        num_errors = 0
        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in jshint_lines:
            num_errors += self._process_one_line(f, output_line,
                                                 contents_lines)
        return num_errors

    def process_files(self, files):
        num_errors = 0
        jshint_output = jshint_files(files)
        for f in files:
            if f in jshint_output:
                lintlines = jshint_output[f]
                try:
                    contents = open(f, 'U').read()
                except (IOError, OSError), why:
                    print "SKIPPING lint of %s: %s" % (f, why.args[1])
                    num_errors += 1
                    continue
                num_errors += self.process(f, contents, lintlines)
        return num_errors


def jshint_files(files):
    """Given a list of files, return jshint stdout for each file.

    Arguments:
        files: list of files as [(filename, contents)]

    Returns:
        dict of {f: stdout_lines} from filename to stdout as an array of stdout
        lines only containing files that had output; if there are no lint
        errors, an empty dict
    """

    jshint_executable = os.path.join(_CWD,
        'node_modules', '.bin', 'jshint')
    assert os.path.isfile(jshint_executable), ("The linter jshint is missing. "
                                               "Expected it at '%s'" %
                                               jshint_executable)
    config = os.path.join(_CWD,
        'jshintrc')
    reporter = os.path.join(_CWD,
        'jshint_reporter.js')

    pipe = subprocess.Popen([
        jshint_executable,
        '--config', config,
        '--reporter', reporter,
        ] + files,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = pipe.communicate()

    if stderr:
        raise Exception("Unexpected stderr from jshint:\n%s" % stderr)

    output = {}

    key = lambda line: line.split(':', 1)[0]
    lines = sorted(stdout.splitlines(), key=key)
    for filename, flines in itertools.groupby(lines, key):
        output[filename] = list(flines)

    return output


def jshint(contents_of_f):
    jshint_executable = os.path.join(_CWD,
        'node_modules', '.bin', 'jshint')
    config = os.path.join(_CWD, 'jshintrc')
    reporter = os.path.join(_CWD, 'jshint_reporter.js')

    pipe = subprocess.Popen([
        jshint_executable,
        '--config', config,
        '--reporter', reporter,
        '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = pipe.communicate(contents_of_f)

    if stderr:
        raise Exception("Unexpected stderr from jshint:\n%s" % stderr)
    return stdout


class JsxLinter(Linter):
    """Linter for jsx files.  process() processes one file."""
    _JSX_ERROR_MESSAGE_RE = re.compile(r'Error: Line (\d+): (.*)')

    def __init__(self, verbose, propose_arc_fixes=False):
        self._verbose = verbose
        self._propose_arc_fixes = propose_arc_fixes

    def process(self, f, contents_of_f):
        num_errors = 0
        num_errors += self._check_line_length(f, contents_of_f)
        num_errors += self._lint_generated_js(f, contents_of_f)
        return num_errors

    def _check_line_length(self, f, contents_of_f):
        num_errors = 0
        lineno = 1
        for line in contents_of_f.splitlines():
            if len(line) >= 80 and not (
                    '@Nolint' in line or
                    'http://' in line or
                    'https://' in line or
                    'require(' in line):
                num_errors += 1
                print ('%s:%s: W101 Line is too long.' % (f, lineno))
            lineno += 1
        return num_errors

    def _lint_generated_js(self, f, contents_of_f):
        # Pipe the source of the file to `jsx` and get the result from stdout
        # as `transformed_source`. Ignore when it prints out "build Module" to
        # stderr.
        jsx_executable = os.path.join(_CWD, 'compile_jsx_file')
        process = subprocess.Popen([jsx_executable],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        transformed_source, err = process.communicate(contents_of_f)
        result = process.wait()

        if result != 0:
            # If jsx failed to even process the file due to a parse
            # error that it found, report that error.
            m = self._JSX_ERROR_MESSAGE_RE.search(err)
            if m:
                # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
                print '%s:%s: E=parse= %s' % (f, m.group(1), m.group(2))
                return 1
            else:
                raise RuntimeError('%s: jsx exited with error code %d:\n%s' %
                                   (f, result, indent(err)))

        # TODO(alpert): Run all the jshint calls in one invocation for speed
        stdout = jshint(transformed_source)

        num_errors = 0
        # need these for filtering
        contents_lines = transformed_source.splitlines()
        # guard against errors on the last line
        contents_lines.append("")
        for output_line in stdout.splitlines():
            num_errors += self._process_one_line(f, output_line,
                                                 contents_lines)
        return num_errors

    def _maybe_add_arc_fix(self, lintline, bad_line):
        """Optionally add a patch for arc lint to use for autofixing."""
        if not self._propose_arc_fixes:
            return lintline

        errcode = lintline.split(' ')[1]

        # W033: Missing semicolon
        if errcode == 'W033':
            return lintline + lint_util.propose_arc_fix_str('', ';')

        return lintline

    def _process_one_line(self, filename, output_line, contents_lines):
        """If line is an 'error', print it and return 1.  Else return 0.

        closure-linter prints all errors to stdout.  But we want to
        ignore some 'errors' that are ok for us, in particular ones
        that have been commented out with @Nolint and errors the jsx compiler
        is known to create.

        Arguments:
           filename: path to file being linted
           output_line: one line of the closure-linter error-output
           contents_lines: the contents of the file being linted,
              as a list of lines.

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        # output_line is like:
        #   stdin:<line>:<col>: W<code> <message>
        # so replace `stdin` with the actual filename before doing more
        lintline = "%s:%s" % (filename, output_line.split(':', 1)[1])
        bad_linenum = int(lintline.split(':', 2)[1])   # first line is '1'
        bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index

        # If the line has a nolint directive, ignore it.
        if '@Nolint' in bad_line:
            return 0

        # Otherwise, it's a legitimate error.
        print self._maybe_add_arc_fix(lintline, bad_line)
        if self._verbose:
            # TODO(joel) consider using a real color library
            print '\033[93mCompiled jsx:\033[0m'
            print line_with_context(contents_lines, bad_linenum - 1, 2)
        return 1


def indent(string, n=4):
    return ('\n' + ' ' * n).join(string.splitlines())


def line_with_context(lines, line_no, context_size):
    """Surround the specified line with a context, like grep -C.

    This also highlights the specified line with an error color.
    """
    message = ''
    for i in xrange(max(line_no - context_size, 0),
                    min(line_no + context_size, len(lines))):
        if i == line_no:
            message += '\033[91m' + lines[i] + '\033[0m'
        else:
            message += lines[i]
        message += '\n'
    return message


class HtmlLinter(Linter):
    """Linter for html.  process() processes one file.

    The main thing we look for with html is that the static images
    are properly escaped using the |static_url filter.  This is
    applied only to files in the 'templates' directory.
    """
    def process(self, f, contents_of_f):
        if ('templates' + os.sep) in f:
            # s_c_r.lint_one_file() happily ignores @Nolint lines for us.
            errors = static_content_refs.lint_one_file(f, contents_of_f)
            for (fname, linenum, colnum, unused_endcol, msg) in errors:
                # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
                print ('%s:%s:%s: E=static_url= %s'
                       % (fname, linenum, colnum, msg))
            return len(errors)
        else:
            return 0
