# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E129
"""Utilities to help write linters.

tools/runlint.py runs all functions named lint_* in all files named
*_lint.py.  Each of these functions takes a list of files to lint.
They often need to do the same thing: tokenize python source, for
instance.  This file has routines to help with that.

It also has routines for helping with lint unittests, which often
need to do the same thing (like mock open()).

PRIMER ON WRITING LINTERS:

Each lint function takes a list of filenames to lint.  These are
absolute paths.  It should then yield each error as a tuple:
   (filename, line_number, message)

To get the file-contents from a filename, use file_contents().
"""

from __future__ import absolute_import

import cStringIO
import threading
import tokenize
import unittest

from shared import ka_root
import shared.util.decorator

# We will probably need to lint the same files over and over again,
# so cache them.  This maps filename to content.
_FILE_CACHE = {}


# Put this decorator on a linter-function if you don't want people to
# be able to use @Nolint to disable the lint check.  This is useful
# for lint checks that are really correctness checks (e.g. you have
# all your needed dependencies.)
NOLINT_NOT_ALLOWED = (
    ' (NOTE: you cannot use @Nolint to disable this lint check!)')

# Keeps track of whether the current linter has disallowed nolint or
# not.  We want to be safe if linting in multiple threads at once!
THREAD_LOCAL = threading.local()


def disallow_nolint(func):
    @shared.util.decorator.wraps(func)
    def wrapper(*args, **kwargs):
        THREAD_LOCAL.nolint_disallowed = True
        try:
            for (filename, lineno, error) in func(*args, **kwargs):
                if has_nolint(filename, lineno):
                    error = error + NOLINT_NOT_ALLOWED
                yield (filename, lineno, error)
        finally:
            THREAD_LOCAL.nolint_disallowed = False

    return wrapper


def file_contents(filename):
    """filename should be an absolute path."""
    if filename not in _FILE_CACHE:
        with open(filename) as f:
            _FILE_CACHE[filename] = f.read()
    return _FILE_CACHE[filename]


def filter(files_to_lint, prefix='', suffix='', exclude_substrings=[]):
    """Return a filtered version of files to lint matching prefix AND suffix.

    First it converts each file in files_to_lint to a relative
    filename (relative to ka_root).  Then it makes sure
    relpath.startswith(prefix) and relpath.endswith(suffix).
    exclude_substrings is a list: all files which include any
    substring in that list is excluded.  For exclude_substrings,
    the full abspath of the file is considered.

    It then converts matching files back to an abspath and returns them.

    prefix and suffix can be the same as for startswith and endswith:
    either a single string, or a list of strings which are OR-ed
    together.
    """
    without_excludes = [f for f in files_to_lint
                        if not any(s in f for s in exclude_substrings)]
    relpaths = [ka_root.relpath(f) for f in without_excludes]
    filtered = [f for f in relpaths
                if f.startswith(prefix) and f.endswith(suffix)]
    filtered_abspaths = [ka_root.join(f) for f in filtered]

    return filtered_abspaths


def find_lines(files, regexp):
    """Yields (filename, linenum, line) for lines matching regexp.

    Note the regexp must be contained in a single line, as this function
    does line-by-line matching.

    Ignores lines with @Nolint on them.
    """
    for filename in files:
        for (i, line) in enumerate(file_contents(filename).splitlines(True)):
            if regexp.search(line) and not _matches_nolint(line):
                yield (filename, i + 1, line)


def line_number_in_contents(contents, regex, default=1):
    """Find the line number where regex first occurs inside contents.

    If regex has a matching group, the line number of the start of the
    matching group will be returned.  If the regex is not found,
    'default' is returned.
    """
    m = regex.search(contents)
    if not m:
        return default

    if m.groups():
        startpos = m.start(1)       # start of group 1 (the paren section)
    else:
        startpos = m.start(0)       # start of the entire regexp

    return contents.count('\n', 0, startpos) + 1


def line_number(filename, regex, default=1):
    """Find the line number where regex first occurs inside filename.

    If regex has a matching group, the line number of the start of the
    matching group will be returned.  If the regex is not found,
    default is returned.  filename should be an absolute path.

    Unlike find_lines(), the regex here can span multiple lines.
    """
    return line_number_in_contents(file_contents(filename), regex, default)


def has_nolint(filename, line_number):
    """True if the given file:line has the text '@Nolint' in it."""
    line_number -= 1         # python arrays are 0-indexed
    # TODO(csilvers): ignore "@Nolint"'s that are inside strings.
    return '@Nolint' in file_contents(filename).splitlines(True)[line_number]


def _matches_nolint(line):
    """True if `line` contains "@Nolint", except when nolint is disallowed."""
    if getattr(THREAD_LOCAL, "nolint_disallowed", False):
        return False
    return '@Nolint' in line


def python_tokens(files):
    """Like tokenize.generate_tokens(), but over a bunch of files.

    This routine automatically ignores content-less tokens: NL
    (newline) and COMMENT.

    Returns:
       Yields tuples as in generate_tokens():
          (filename, token_type, token_value, (start_line, start_col),
           (end_line, end_col), line)
       token_type is taken from tokenize.
    """
    for filename in files:
        cache_key = ('TOKENS', filename)
        if cache_key not in _FILE_CACHE:
            f = cStringIO.StringIO(file_contents(filename)).readline
            _FILE_CACHE[cache_key] = [
                (filename, ttype, token, start, end, line)
                for (ttype, token, start, end, line) in (
                        tokenize.generate_tokens(f))
                if ttype not in (tokenize.NL, tokenize.COMMENT)
            ]
        for token_info in _FILE_CACHE[cache_key]:
            yield token_info


def find_token_streams(files, token_stream, ignore_nolint=True):
    """Yield each token-stream we find within the input files.

    For each python file given, we tokenize the file (using the
    tokenize module), and then look at the tokens one by one, and see
    if any subsequence of tokens matches token_stream.  If so, we
    return (yield) it.

    If ignore_nolint is set, ignores tokens on lines with @Nolint on them.

    Arguments:
       files: a list of filenames to process
       token_stream: a list of tokens to match, for instance:
           ('i18n', tokenize.DOT, '_').  Each entry of the list
           may be either an integer representing a token-type (taken
           from tokenize) or a string representing a token value.
           An entry may also be a list of int/strings beginning with
           ':OR:', to accept any token in the list:
               ('i18n', tokenize.DOT, (':OR:', '_', 'ngettext'))
           or beginning with ':NOT:', to accept anything except what's
           in the list:
               ('i18n', tokenize.DOT, (':NOT:', '_', 'ngettext'))

    Returns:
       Yields a list of tuples.  The list has length
       len(token_stream), which each element corresponding to one
       element of the input token-stream.  Each entry is:
           (filename, token-type, token-value,
            (start-lineno, start-colno), (end-lineno, end-colno), line)
       as in python_tokens()
    """
    assert token_stream, "Must pass a non-empty token stream"

    # We could be clever and do boyer-moore or some such, but we
    # do something simple instead.  The initial value of -1 means
    # 'check to see if we're starting a new stream (at state 0).'
    current_states = set((-1,))    # an NFA!
    end_state = len(token_stream) - 1
    last_n_tokens = []

    for (fname, ttype, token, startpos, endpos, line) in python_tokens(files):
        new_states = set((-1,))    # we're always ready to start anew
        for state in current_states:
            next_state = token_stream[state + 1]
            if ttype == next_state or token == next_state:
                new_states.add(state + 1)
            elif (next_state[0] == ':OR:' and
                  any(ttype == s or token == s for s in next_state[1:])):
                new_states.add(state + 1)
            elif (next_state[0] == ':NOT:' and
                  all(ttype != s and token != s for s in next_state[1:])):
                new_states.add(state + 1)
        current_states = new_states

        if len(current_states) > 1:    # more than just the '-1' entry
            # If we're potentially in a match, we need to keep track of
            # the tokens we've been looking at.
            last_n_tokens.append((fname, ttype, token, startpos, endpos, line))
            if len(last_n_tokens) > len(token_stream):
                del last_n_tokens[0]

        if end_state in new_states:    # a match! -- got to the end
            if ignore_nolint:
                has_nolint = any(_matches_nolint(t[4]) for t in last_n_tokens)
            else:
                has_nolint = False     # means we'll always yield this match
            if not has_nolint:
                yield last_n_tokens
            current_states.remove(end_state)

        if len(current_states) == 1:
            last_n_tokens = []


class LintTest(unittest.TestCase):
    def setUp(self):
        super(LintTest, self).setUp()
        _FILE_CACHE.clear()

    def set_file_contents(self, filename, contents):
        _FILE_CACHE[filename] = contents
        _FILE_CACHE.pop(('TOKENS', filename), None)

    def _lint(self, content):
        raise NotImplementedError('Subclasses must define')

    def assert_error(self, input, count=1):
        # We simulate the @Nolint check in tools/runlint.py
        errors = [(filename, lineno, error)
                  for (filename, lineno, error) in self._lint(input)
                  if (error.endswith(NOLINT_NOT_ALLOWED) or
                      not has_nolint(filename, lineno))]
        self.assertEqual(count, len(errors), errors)
        return errors

    def assert_no_error(self, input):
        return self.assert_error(input, count=0)
