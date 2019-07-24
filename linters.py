# -*- coding: utf-8 -*-
"""Linters process files or lists of files for correctness."""

import itertools
import logging
import os
import re
import signal
import subprocess
import sys

import lint_util
import six
import six.moves

from six.moves import cStringIO as StringIO

# Add vendor path so we can find (our packaged versions of) flake8
_CWD = lint_util.get_real_cwd()
_parent_dir = os.path.abspath(_CWD)
if six.PY2:
    _vendor_version = 'py2'
else:
    _vendor_version = 'py3'

_vendor_dir = os.path.join(_parent_dir, 'vendor', _vendor_version)
sys.path.insert(0, _vendor_dir)

import static_content_refs
import flake8.api.legacy
import flake8.formatting.default
import yaml


def _is_verbose(logger):
    """Does this logger log to stdout/stderr at the DEBUG level?"""
    # First we check if the logger itself processes anything at the
    # debug level.  If not, then the handlers won't even see it.
    if not logger.isEnabledFor(logging.DEBUG):
        return False

    for handler in getattr(logger, 'handlers', []):
        if (getattr(handler, '__class__', None) == logging.StreamHandler and
                handler.level <= logging.DEBUG and
                handler.stream in (sys.stdout, sys.stderr)):
            return True
    return False


def _has_nolint(line):
    """We can turn off linting for a line via `@Nolint` or `NoQA`.

    Unlike flake8, we care about case for NoQA.

    TODO(csilvers): return the list of error-codes that we nolint for,
    and have callers respect that.
    """
    return "@Nolint" in line or "# NoQA" in line


class Linter(object):
    """Superclass for all linters.

    When subclassing, override either process_files or process (or both,
    though if you override process_files then it doesn't matter what
    process does).
    """
    def __init__(self, logger):
        self.logger = logger
        self.verbose = _is_verbose(logger)

    def process_files(self, files):
        """Print lint errors for a list of filenames and return error count."""
        num_errors = 0
        for f in files:
            try:
                contents = open(f, 'U').read()
            except (IOError, OSError) as why:
                self.logger.warning("SKIPPING lint of %s: %s"
                                    % (f, why.args[1]))  # get the errno-string
                num_errors += 1
                continue
            except UnicodeDecodeError as why:
                self.logger.warning("SKIPPING lint of %s: %s" % (f, why))
                num_errors += 1
                continue
            num_errors += self.process(f, contents)
        return num_errors

    def process(self, file, contents):
        """Lint one file given its path and contents, returning error count."""
        raise NotImplementedError("Subclasses must override process()")

    def report(self, lint):
        """Report the output to both stdout/stderr and logfile."""
        self.logger.debug(lint)
        if not self.verbose:
            lint_util.print_(lint)


def _capture_stdout_of(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) and return (fn_retval, fn_stdout_output_fp)."""
    try:
        orig_stdout = sys.stdout
        sys.stdout = StringIO()
        retval = fn(*args, **kwargs)
        sys.stdout.seek(0)    # so new read()/readlines() calls will return
        return (retval, sys.stdout)
    finally:
        sys.stdout = orig_stdout


class Flake8(Linter):
    """Linter for python.  process() processes one file."""
    GLOBAL_IGNORES = frozenset((
        'E266',  # too many leading '#' for block comment
        'E402',  # module level import not at top of file
        'W503',  # line break before binary operator
        'E731',  # do not assign a lambda expression
    ))

    def __init__(self, logger, propose_arc_fixes=False):
        super(Flake8, self).__init__(logger=logger)
        self._propose_arc_fixes = propose_arc_fixes
        # A map from filename of a file to lint, to the error codes that
        # we should ignore for this file.  We always ignore error codes
        # in GLOBAL_IGNORES, but each file can add more codes to ignore
        # via a `# pep8-disable` line in the file.
        self._files_to_ignored_errors = {}

    def _maybe_add_arc_fix(self, lintline, bad_line):
        """Optionally add a patch for arc lint to use for autofixing."""
        if not self._propose_arc_fixes:
            return lintline

        errcode = lintline.split(' ')[1]

        # expected 2 blank lines, found 1
        if errcode == 'E302':
            return lint_util.add_arc_fix_str(lintline, bad_line, '', '\n')

        # at least two spaces before inline comment
        if errcode == 'E261':
            return lint_util.add_arc_fix_str(lintline, bad_line, '', ' ')

        # module imported but not used
        if errcode == 'F401':
            return lint_util.add_arc_fix_str(lintline, bad_line,
                                             bad_line + '\n', '')

        return lintline

    def _process_one_line(self, lintline, bad_line, ignored_rules):
        """If line is an 'error', print it and return 1.  Else return 0.

        pep8 prints all errors to stdout.  But we want to ignore some
        'errors' that are ok for us but cannot be suppressed via pep8
        flags, such as lines marked with @Nolint.  To do this, we
        intercept stdin and remove these lines.

        Arguments:
           lintline: one line of the flake8 error-output
           bad_line: the line that the lintline is referring to
           ignored_rules: a list of rules (like 'E501') that will be
              ignored

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        if _has_nolint(bad_line):
            return 0

        if any(rule in lintline for rule in ignored_rules):
            return 0

        # We allow lines to be arbitrarily long if they are urls,
        # since splitting urls at 80 columns can be annoying.
        if ('E501 line too long' in lintline and
                ('http://' in bad_line or 'https://' in bad_line)):
            return 0

        # We follow python convention of allowing an unused variable
        # if it's named '_' or starts with 'unused_'.
        if ('F841 local variable' in lintline and
            ("local variable '_'" in lintline or
             "local variable 'unused_" in lintline)):
            return 0

        # It's OK to redefine variables that are unused by convention.
        if ('F812 list comprehension redefines' in lintline and
            ("redefines '_'" in lintline or
             "redefines 'unused_" in lintline)):
            return 0

        # Get rid of some warnings too.
        if 'unable to detect undefined names' in lintline:
            return 0

        # An old nolint directive that's specific to imports.
        if ('@UnusedImport' in bad_line and
                'imported but unused' in lintline):   # F401
            return 0

        # OK, looks like it's a legitimate error.
        self.report(self._maybe_add_arc_fix(lintline, bad_line))

        return 1

    def _get_file_level_nolint_rules(self, contents_lines):
        """Get a list of rules disabled at the file-level.

        This allows us to upgrade linter without having to fix all the lint
        immediately.

        We check the first three lines (three to allow for a shebang, and a
        TODO to fix the lint) for a comment that looks like:
        # pep8-disable:E101,E102,W405
        where the part following the colon is a comma-separated list of rules
        to ignore in the file.  These must all start with E or W.
        """
        for line in contents_lines[:3]:
            match = re.search(r'pep8-disable:([\S]+)', line)
            if match:
                return {rule for rule in match.group(1).split(',')}

        return set()

    def process(self, f, contents_of_f):
        """Just collect files and their file-level nolint rules.

        This is called by the default process_files(), but in our case
        it just does some pre-processing.  The actual error-detection
        is done in process2(), below.
        """
        contents_lines = contents_of_f.splitlines(True)
        self._files_to_ignored_errors[f] = (
            self.GLOBAL_IGNORES |
            self._get_file_level_nolint_rules(contents_lines)
        )
        return 0    # we cannot create any errors

    def process2(self):
        linter = self     # because we override `self` inside Reporter
        num_errors = [0]  # in a list so we can mutate it

        class Reporter(flake8.formatting.default.Default):
            def beginning(self, filename):
                self.ignored_errors = linter._files_to_ignored_errors[filename]

            def show_source(self, error):
                return error.physical_line

            def write(self, line, source):
                num_errors[0] += linter._process_one_line(
                    line.strip(), source, self.ignored_errors)

        # We do not pass in any `exclude` parameter here, because we
        # don't want to override the default excludes for the parent
        # repo.  Instead, we filter out errors we want to ignore
        # in `_process_one_line`, above.
        # We force flake8 to run in serial until process-leaking is
        # fixed, e.g. when flake8 has merged
        #    https://gitlab.com/pycqa/flake8/merge_requests/228
        # TODO(csilvers): remove `jobs=1` after we update vendor/.
        style_guide = flake8.api.legacy.get_style_guide(jobs='1')
        style_guide.init_report(Reporter)
        style_guide.check_files(self._files_to_ignored_errors.keys())

        return num_errors[0]

    def process_files(self, files):
        """Print lint errors for a list of filenames and return error count."""
        # The first line calls process() to set things up, the second
        # calls process2() to actually do the processing.
        num_errors = super(Flake8, self).process_files(files)
        num_errors += self.process2()
        return num_errors


class CustomPythonLinter(Linter):
    """A linter for generic python errors that are not caught by flake8.

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
            if _has_nolint(line):
                continue

            if self._bad_super(line):
                # Canonical form: <file>:<line>[:<col>]: <E|W><code> <msg>
                self.report(('%s:%s: E999 first argument to super() must be '
                             'an explicit classname, not type(self)'
                             % (f, linenum_minus_1 + 1)))
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
            self.report(('%s:%s:1: E1 git conflict marker "%s" found'
                         % (f, linenum, m.group(1))))
            num_errors += 1
        return num_errors


class Eslint(Linter):
    """Linter for javascript.  process() processes one file.

    Arguments:
        config_path: the path of the eslintrc file
    """
    def __init__(self, config_path, logger, propose_arc_fixes=False):
        super(Eslint, self).__init__(logger=logger)
        self._config_path = config_path
        self._propose_arc_fixes = propose_arc_fixes

    def _maybe_add_arc_fix(self, lintline, bad_line):
        """Optionally add a patch for arc lint to use for autofixing."""
        if not self._propose_arc_fixes:
            return lintline

        (file_line_col, errcode, msg) = lintline.split(' ', 2)

        if errcode == 'Esemi':
            return lint_util.add_arc_fix_str(lintline, bad_line, '', ';')
        if errcode == 'Eno-extra-semi':
            return lint_util.add_arc_fix_str(lintline, bad_line, ';', '')
        if errcode == 'Ecomma-dangle':
            return lint_util.add_arc_fix_str(lintline, bad_line, '', ',')
        if errcode == 'Ecomma-spacing':
            return lint_util.add_arc_fix_str(lintline, bad_line, ',', ', ')
        if errcode == 'Espace-before-function-paren':
            return lint_util.add_arc_fix_str(lintline, bad_line,
                                             re.compile(r' +'), '')
        if errcode == 'Eprefer-const':
            return lint_util.add_arc_fix_str(lintline, bad_line,
                                             'let', 'const',
                                             search_backwards=True)

        if errcode == 'Ereact/jsx-closing-bracket-location':
            try:
                col = file_line_col.split(':')[2]
            except IndexError:
                col = None
            m = re.search(r'\(expected column (\d+)\)', msg)

            if col is not None and m is not None:
                spaces_to_add = int(m.group(1)) - int(col)
                if spaces_to_add > 0:
                    return lint_util.add_arc_fix_str(
                        lintline, bad_line, '', ' ' * spaces_to_add)
                else:
                    return lint_util.add_arc_fix_str(
                        lintline, bad_line, ' ' * -spaces_to_add, '',
                        search_backwards=True)

            # Also handle the case the \> should go on the next line
            m = re.search(r'\(expected column (\d+) on the next line\)', msg)
            if m:
                indent = int(m.group(1)) - 1
                if indent >= 0:
                    return lint_util.add_arc_fix_str(
                        lintline, bad_line, '', '\n' + ' ' * indent)

        if errcode == 'Eindent':
            m = re.search(r'Expected indentation of (\d+) space characters '
                          r'but found (\d+)',
                          msg)
            if m:
                spaces_to_add = int(m.group(1)) - int(m.group(2))
                if spaces_to_add > 0:
                    return lint_util.add_arc_fix_str(
                        lintline, bad_line, '', ' ' * spaces_to_add)
                else:
                    return lint_util.add_arc_fix_str(
                        lintline, bad_line, ' ' * -spaces_to_add, '',
                        search_backwards=True)

        if errcode in {'Ecomputed-property-spacing', 'Earray-bracket-spacing',
                       'Eobject-curly-spacing'}:
            search_backwards = 'space before' in lintline
            return lint_util.add_arc_fix_str(lintline, bad_line,
                                             re.compile(r' +'), '',
                                             search_backwards=search_backwards)

        if errcode == 'Espace-in-parens':
            try:
                col = int(file_line_col.split(':')[2]) - 2
            except IndexError:
                col = None

            if col is not None:
                paren = bad_line[col]
                search_backwards = {'(': False, ')': True}.get(paren)

                if search_backwards is not None:
                    return lint_util.add_arc_fix_str(
                        lintline, bad_line, re.compile(r' +'), '',
                        search_backwards=search_backwards)

        if errcode == 'Eprettier/prettier':
            ascii_lintline = self._ascii_prettier_string(lintline)

            insert = re.search(r'Insert `(.*?)`?$', msg)
            if insert:
                to_add = self._clean_prettier_string(insert.group(1))
                return lint_util.add_arc_fix_str(
                    ascii_lintline, bad_line, '',
                    to_add, limit_to_80=False)

            remove = re.search(r'Delete `(.*?)`?$', msg)
            if remove:
                return lint_util.add_arc_fix_str(
                    ascii_lintline, bad_line,
                    self._clean_prettier_string(remove.group(1)), '',
                    limit_to_80=False)

            replace = re.search(r'Replace `(.*?)` with `(.*?)`?$', msg)
            if replace:
                to_add = self._clean_prettier_string(replace.group(2))
                return lint_util.add_arc_fix_str(
                    ascii_lintline, bad_line,
                    self._clean_prettier_string(replace.group(1)),
                    to_add,
                    limit_to_80=False)

        return lintline

    def _ascii_prettier_string(self, prettier_string):
        return prettier_string.replace(u'·', ' ').replace(
            u'↹', '\\t').replace(u'⏎', '\\n')

    def _clean_prettier_string(self, prettier_string):
        return prettier_string.replace(u'·', ' ').replace(
            u'↹', '\t').replace(u'⏎', '\n')

    def _process_one_line(self, filename, output_line, contents_lines):
        """If line is an 'error', print it and return 1.  Else return 0.

        eslint prints all errors to stdout.  But we want to
        ignore some 'errors' that are ok for us, in particular ones
        that have been commented out with @Nolint.

        Arguments:
           filename: path to file being linted
           output_line: one line of the eslint error-output
           contents_lines: the contents of the file being linted,
              as a list of lines.

        Returns:
           1 (indicating one error) if we print the error line, 0 else.
        """
        # output_line is like:
        #   <file>:<line>:<col>: W<code> <message>
        # which is just what we need!
        bad_linenum = int(output_line.split(':', 2)[1])   # first line is '1'
        if 1 <= bad_linenum <= len(contents_lines):
            bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index
        else:
            # If we can't figure out what line it's on (e.g. it's an error in
            # an empty file), try our best to report anyway.
            bad_line = ''

        # If the line has a nolint directive, ignore it.
        if _has_nolint(bad_line):
            return 0

        # Allow long lines in fixture files, which just hold test data.
        if (' Emax-len ' in output_line and
                filename.endswith(('.fixture.js', 'fixture.jsx'))):
            return 0

        # I don't know why it prints this.  Shrug.
        if 'File ignored because of your .eslintignore file' in output_line:
            return 0

        (file_line_col, errcode, msg) = output_line.split(' ', 2)

        err_type = errcode[1:]
        if err_type != "prettier/prettier":
            output_line += " (Mute with // eslint-disable-line %s)" % (
                err_type)

        self.report(self._maybe_add_arc_fix(output_line, bad_line))
        return 1

    def process(self, f, contents_of_f, eslint_lines):
        num_errors = 0
        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in eslint_lines:
            num_errors += self._process_one_line(f, output_line,
                                                 contents_lines)
        return num_errors

    def _run_eslint(self, files):
        """Run eslint on the given files and returns stdout, sans header."""
        exec_path = os.path.join(_CWD, 'node_modules', '.bin', 'eslint')
        reporter_path = os.path.join(_CWD, 'eslint_reporter.js')
        assert os.path.isfile(exec_path), (
            "Vendoring error: eslint is missing from '%s'" % exec_path)

        # TODO(csilvers): split out files based on whether they're intended
        # for node.js or not, and use eslintrc.node for the node.js files.
        # Two ways to tell:
        #    1) shebang line at the top of the file
        #    2) '"use strict";' in the file somewhere
        subprocess_args = [exec_path, '--config', self._config_path,
                           '-f', reporter_path, '--no-color'] + files

        env = os.environ.copy()
        if 'NODE_PATH' in env:
            env['NODE_PATH'] += ':' + os.path.dirname(self._config_path)
        else:
            env['NODE_PATH'] = os.path.dirname(self._config_path)

        for _ in range(3):
            process = subprocess.Popen(
                subprocess_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env)
            stdout, stderr = process.communicate()
            # eslint (or rather, the node process running it) is crashing
            # some small percentage of the time, for reasons we don't
            # understand.  Normally this is a segfault but sometimes it's a
            # SIGILL; I'm guessing it's jumping to some bad location.
            # (See INFRA-1000.)  Until we figure out how to fix
            # this, if we see a segfault, just retry a couple of times.
            # TODO(benkraft): If the segfault ever gets fixed, remove this
            # retry logic.
            if -process.returncode not in (signal.SIGSEGV, signal.SIGILL):
                break

        stdout, stderr = stdout.decode('utf-8'), stderr.decode('utf-8')

        if stderr:
            raise RuntimeError(
                "Unexpected stderr from linter (exited %s):\n%s\nstdout:\n%s"
                % (process.returncode, stderr, stdout))

        # Check for the "Lint results:" message outputted as the first line of
        # eslint_reporter.js. This helps us distinguish between two "failure"
        # cases: ESLint successfully linting but yielding errors, and ESLint
        # crashing.
        if not stdout.strip():
            raise RuntimeError("Expected stdout from linter (exited %s), "
                               "got none." % process.returncode)
        stdout_lines = stdout.splitlines()
        if stdout_lines[0].strip() != 'Lint results:':
            raise RuntimeError("Unexpected stdout from linter (exited %s):\n%s"
                               % (process.returncode, stdout))
        return stdout_lines[1:]

    def lint_files(self, files):
        """Execute a linter on a list of files and return the stdout for each.

        Arguments:
            exec_path: A path to the linter's executable
            files: A list of filenames
            extra_flags: (optional) A list of commandline flags to include in
                         the subprocess call

        Returns:
            dict of {f: stdout_lines} from filename to stdout as an array of
            stdout lines only containing files that had output; if there are
            no lint errors, an empty dict.
        """
        stdout_lines = []
        # We need to keep sum(|files|) less than about 250k for OS X's
        # commandline limit.  2000 files at a time should do that.
        for i in six.moves.range(0, len(files), 2000):
            stdout_lines.extend(self._run_eslint(files[i:i + 2000]))

        # eslint_reporter specifies that errors are reported on
        # individual lines starting with "filename:line:col".  It
        # converts all filenames to an absolute path; we convert them
        # back to relpaths here.
        lint_lines = []
        for line in stdout_lines:
            parts = line.split(':', 1)
            if len(parts) != 2:
                raise RuntimeError("Unexpected stdout from linter:\n%s" %
                                   stdout_lines)
            lint_lines.append('%s:%s' % (os.path.relpath(parts[0]), parts[1]))

        get_filename = lambda line: line.split(':', 1)[0]
        lines = sorted(lint_lines, key=get_filename)
        output = {}
        for filename, flines in itertools.groupby(lines, get_filename):
            output[filename] = list(flines)

        return output

    def process_files(self, files):
        """Lint a series of files, and self.process() each with an error."""
        num_errors = 0
        file_to_lint_output = self.lint_files(files)
        for filename in files:
            if filename in file_to_lint_output:
                lintlines = file_to_lint_output[filename]
                try:
                    contents = open(filename, 'U').read()
                except (IOError, OSError, UnicodeDecodeError) as why:
                    self.logger.warning("SKIPPING lint of %s: %s"
                                        % (filename, why.args[1]))
                    num_errors += 1
                    continue
                num_errors += self.process(filename, contents, lintlines)
        return num_errors


class LessHint(Linter):
    """Linter for less."""
    def _process_one_line(self, filename, output_line, contents_lines):
        # output_line is like:
        #   <file>:<line>:<col>: W<code> <message>
        bad_linenum = int(output_line.split(':', 2)[1])   # first line is '1'
        bad_line = contents_lines[bad_linenum - 1]     # convert to 0-index

        # If the line has a nolint directive, ignore it.
        if _has_nolint(bad_line):
            return 0

        self.report(output_line)
        return 1

    def process(self, f, contents_of_f, lesshint_lines):
        num_errors = 0
        contents_lines = contents_of_f.splitlines()  # need these for filtering
        for output_line in lesshint_lines:
            num_errors += self._process_one_line(f, output_line,
                                                 contents_lines)
        return num_errors

    def lint_files(self, files):
        """Execute a linter on a list of files and return the stdout for each.

        Returns:
            dict of {f: stdout_lines} from filename to stdout as an array of
            stdout lines only containing files that had output; if there are
            no lint errors, an empty dict.
        """
        exec_path = os.path.join(_CWD, 'node_modules', '.bin', 'lesshint')
        reporter_path = os.path.join(_CWD, 'lesshint_reporter.js')
        assert os.path.isfile(exec_path), (
            "Vendoring error: lesshint is missing from '%s'" % exec_path)

        subprocess_args = [exec_path, '--reporter', reporter_path] + files

        pipe = subprocess.Popen(
            subprocess_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = pipe.communicate()

        if stderr:
            raise RuntimeError("Unexpected stderr from lesshint:\n%s" % stderr)

        output = {}

        # lesshint_reporter specifies that errors are reported on individual
        # lines starting with "filename:line:col"
        get_filename = lambda line: line.split(':', 1)[0]
        lines = sorted(stdout.splitlines(), key=get_filename)
        for filename, flines in itertools.groupby(lines, get_filename):
            output[filename] = list(flines)

        return output

    def process_files(self, files):
        """Lint a series of files, and self.process() each with an error."""
        num_errors = 0
        file_to_lint_output = self.lint_files(files)
        for filename in files:
            if filename in file_to_lint_output:
                lintlines = file_to_lint_output[filename]
                try:
                    contents = open(filename, 'U').read()
                except (IOError, OSError, UnicodeDecodeError) as why:
                    self.logger.warning("SKIPPING lint of %s: %s"
                                        % (filename, why.args[1]))
                    num_errors += 1
                    continue
                num_errors += self.process(filename, contents, lintlines)
        return num_errors


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
                self.report('%s:%s:%s: E=static_url= %s'
                            % (fname, linenum, colnum, msg))
            return len(errors)
        else:
            return 0


class YamlLinter(Linter):
    """Linter for .yaml files.  process() processes one file.

    We just make sure the file has no syntax errors, and can be successfully
    loaded.
    """
    def process(self, f, contents_of_f):
        try:
            yaml.safe_load(contents_of_f)
            return 0
        except yaml.parser.ParserError as e:
            self.report(('%s:%s:%s: E=yaml= Error parsing yaml: %s %s'
                         % (f,
                            e.problem_mark.line + 1,  # yaml.Mark is 0-indexed
                            1,
                            e.problem, e.context)))
            return 1


class KtLint(Linter):
    """Linter for kotlin, using the vendored copy of `ktlint`.

    TODO(colin): add autofixing using `ktlint -F`
    """

    def _is_not_skipped(self, file, lint_err_lines):
        """For each lint error in the given file check if it's nolinted.

        Args:
            lint_err_lines: a list of (line (0-indexed), message) tuples
        Returns:
            a list of booleans, one per input, True if that lint error has
            not been skipped via `@Nolint`.
        """
        with open(file) as f:
            lines = f.readlines()
            line_count = len(lines) - 1
            # Cap the indexing at the max number of lines in the file
            return [not _has_nolint(lines[min(lint_err[0], line_count)])
                    for lint_err in lint_err_lines]

    def process_files(self, files):
        exec_path = os.path.abspath(os.path.join(_CWD, 'vendor', 'ktlint'))
        assert os.path.isfile(exec_path), (
            "Vendoring error: ktlint is missing from '%s'" % exec_path)

        version_info_pipe = subprocess.Popen(
            ['java', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        # Apparently java version info is printed to stderr...
        _, version_info = version_info_pipe.communicate()
        version_re = r'\w+ version "(\d\.\d)'
        matchobj = re.search(version_re, version_info.decode('utf-8'))
        assert matchobj is not None, (
            "Unable to determine version of java for running ktlint.")
        version = matchobj.group(1)

        # Between java 8 and java 9, java changed its version numbering scheme
        # to go from 1.x.y to x.y.
        if version == '1.8':
            ktlint_command = [exec_path] + files
        else:
            raise AssertionError('Unsupported version of java, %s' % version)

        pipe = subprocess.Popen(
            ktlint_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        stdout, stderr = pipe.communicate()
        stdout, stderr = stdout.decode('utf-8'), stderr.decode('utf-8')

        if stderr:
            raise RuntimeError("Unexpected stderr from linter:\n%s" % stderr)

        num_errors = 0
        lint_by_file = {}
        for line in stdout.splitlines():
            # Lint line format is file:line:col:message
            # Message could contain ':' so only split up to 3 times
            parts = line.split(':', 3)
            if len(parts) != 4:
                raise RuntimeError("Unexpected stdout from linter:\n%s" %
                                   stdout)
            file, line_number, _, _ = parts

            lint_by_file.setdefault(file, [])
            lint_by_file[file].append((int(line_number) - 1, line))

        for file, lint in lint_by_file.items():
            for _, lint_err in itertools.compress(
                    lint, self._is_not_skipped(file, lint)):
                self.report(lint_err)
                num_errors += 1

        return num_errors
