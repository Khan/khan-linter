"""Common utility functions used across the application."""

import os
import re
import sys


def print_(text, end=None):
    """Always emit text as utf-8.  Useful when piping output elsewhere."""
    if end is None:
        end = os.linesep
    if isinstance(text, str):
        text = (text + end).encode('utf-8')
    else:    # already bytes
        text += end.encode('utf-8')
    sys.stdout.buffer.write(text)


def get_real_cwd():
    """Return the CWD of script in a symlink aware fashion."""
    return os.path.dirname(os.path.realpath(__file__))


def add_arc_fix_str(lintline, bad_line, to_remove, to_add,
                    search_backwards=False, limit_to_80=True):
    """Return lintline augmented by arc's autopatching functionality.

    This gets picked up as part of the regex used by arc to present
    linting results. When it sees the added strings, it prompts if
    you'd like to apply the patch.

    See "config/linter.scriptandregex.regex" in your project's .arclint.

    The way this works is we use lintline to find the first occurrence of
    'to_remove' in bad_line (after the column number specified in lintline),
    and munge lintline to set the column number correctly to remove+add.
    to_remove can be a basestring or a regexp. If search_backwards is True, we
    find the first occurrence of 'to_remove' *before* the listed column number.
    This is for lint errors that report something was bad after it happened
    (e.g. "this is indented too far", pointing to the end of the indented
    region).

    If limit_to_80 is True, then we do not suggest a change that
    would increase the linelength beyond 80 chars.
    """
    # Ensure that the input strings are all encoded byte strings. This ensures
    # that they can interoperate, and ensures that we use byte indexes instead
    # of Unicode character indexes (because the autopatcher expects the
    # former).
    if isinstance(lintline, str):
        lintline = lintline.encode('utf-8')
    if isinstance(bad_line, str):
        bad_line = bad_line.encode('utf-8')
    if isinstance(to_add, str):
        to_add = to_add.encode('utf-8')
    if isinstance(to_remove, str):
        to_remove = to_remove.encode('utf-8')

    (location, errcode, msg) = lintline.split(' ', 2)
    location_info = location.split(':')
    if len(location_info) < 4:       # No column info
        return lintline              # arc can't autofix without a column
    (fname, line, col, _) = location_info
    col = int(col) - 1               # Move from 1-indexed to 0-indexed

    # Special case: no need to search around for the empty string.
    if not to_remove:
        return lintline + "\0\0%s\0" % to_add

    if not isinstance(to_remove, str):
        # `to_remove` is a regexp.
        if search_backwards:
            # Match the last instance of `to_remove` before col.
            pattern = to_remove.pattern
            if not pattern.startswith('^') and not pattern.endswith('$'):
                # Make sure we find the *last* occurrence in the line.
                to_remove = re.compile(pattern + r'(?!.*' + pattern + r')')
            sub_line = bad_line[:col]
            col_offset = 0
        else:
            sub_line = bad_line[col:]
            col_offset = col
        match = re.search(to_remove, sub_line)
        if match is None:
            return lintline
        to_remove = match.group()
        new_col = match.start() + col_offset
    elif '\n' in to_remove:
        # We are maybe removing multiple lines.  We just check the
        # first (which is all we have available to us, and just
        # assume everything after the newline matches as well.
        to_remove_firstline = to_remove.split('\n', 1)[0]
        if bad_line.endswith(to_remove_firstline):
            new_col = len(bad_line) - len(to_remove_firstline)
        else:
            new_col = -1
    elif search_backwards:
        new_col = bad_line.rfind(to_remove, 0, col)
    else:
        new_col = bad_line.find(to_remove, col)

    too_long = limit_to_80 and (
        len(bad_line) - len(to_remove) + len(to_add) >= 80)
    if new_col == -1 or too_long:
        # Could not find `to_remove`, or line is too long; don't fix.
        return lintline

    return ('%s:%s:%s: %s %s\0%s\0%s\0'
            % (fname, line, new_col + 1, errcode, msg, to_remove, to_add))
