"""Common utility functions used across the application."""
import os


def get_real_cwd():
    """Return the CWD of script in a symlink aware fashion."""
    return os.path.dirname(os.path.realpath(__file__))


def propose_arc_fix_str(to_remove, to_add):
    """Return a string to be matched by arc's autopatching functionality.

    This gets picked up as part of the regex used by arc to present linting
    results. When it seems these null delimited strings, it prompts if you'd
    like to apply the patch.

    See "config/linter.scriptandregex.regex" in your ~/.arcrc.
    """
    return "\0%s\0%s\0" % (to_remove, to_add)
