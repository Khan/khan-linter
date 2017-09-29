"""Linter to check for duplicate functions in test files."""
from __future__ import absolute_import

import collections
import re

from shared.testutil import lintutil


_TEST_FN_RE = re.compile(r'^\s{4}def (\w*test\w*)\(', re.MULTILINE)
_CLASS_NAME_RE = re.compile(r'^class (\w*)', re.MULTILINE)


def _matches_with_line_numbers(regexp, string):
    return [(match.group(1), 1 + string.count('\n', 0, match.start()))
            for match in regexp.finditer(string)]


def _find_class_at_line(classes, line):
    defined_before_line = [name for name, c_line in classes if c_line < line]
    return (defined_before_line or [None])[-1]


def lint_duplicate_test_functions(files_to_lint):
    """Enforce that no two test functions in the same class have the same name.

    This prevents one test from not running because another test overwrites it.
    """
    files = lintutil.filter(files_to_lint, suffix='_test.py')

    for filename in files:
        contents = lintutil.file_contents(filename)

        functions = _matches_with_line_numbers(_TEST_FN_RE, contents)
        classes = _matches_with_line_numbers(_CLASS_NAME_RE, contents)

        lines = collections.defaultdict(list)

        for fname, line in functions:
            cls = _find_class_at_line(classes, line)
            if cls is None:
                continue
            qualified_fname = cls + '.' + fname
            lines[qualified_fname] += [line]

        for fname, dup_lines in lines.iteritems():
            if len(dup_lines) > 1:
                if any(lintutil.has_nolint(filename, line)
                       for line in dup_lines):
                    continue

                yield (filename, max(dup_lines),
                       'Duplicate test function name %(name)s'
                       ' at lines %(lines)s' % {
                           'name': fname,
                           'lines': ', '.join(str(l) for l in dup_lines)
                       })
