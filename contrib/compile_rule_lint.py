"""Linters that warn about common problems with kake rules."""

from __future__ import absolute_import

import inspect
import re
import sys

from shared import ka_root

from kake.lib import compile_rule
from kake.lib import computed_inputs


# captures "'foo' in context", "context['foo']", and
# context.get('foo').  We also get the remainder of the line to catch
# '@Nolint' directives.
_CONTEXT_USE_RE = re.compile(
    '(?:'
    r'[\'\"](\w+)[\'\"]\s+in\s+context'
    r'|context\[[\'\"](\w+)[\'\"]\]'
    r'|context\.get\(\s*[\'\"](\w+)[\'\"]'
    ').*')


def _all_subclasses(cls, seen=None):
    """Return all subclasses of cls, not just direct ones."""
    if seen is None:
        seen = set()
    try:
        subclasses = cls.__subclasses__()
    except TypeError:                  # fails only when cls is type
        subclasses = cls.__subclasses__(cls)

    for subclass in subclasses:
        if subclass not in seen:
            seen.add(subclass)
            yield subclass
            for recurse in _all_subclasses(subclass, seen):
                yield recurse


def lint_missing_used_context_keys(files_to_lint):
    """Attempts to find places the user failed to update used_context_keys().

    If you write a compile_rule that uses context['foo'], you're
    supposed to advertise that fact by including 'foo' in your
    used_context_keys() method.  But it's easy to forget to do that.
    This rule attempts to remind you by looking at the source code for
    your class and trying to find all uses.

    This isn't perfect, which is why it's a lint rule and we don't
    just automatically extract uses of context['foo'], but it's better
    than nothing!  If it's claiming a line is a use of context when
    it's not, just stick a @Nolint at the end of the line.
    """
    # Only files under the kake directory might have compile rules.
    relfiles_to_lint = [ka_root.relpath(f) for f in files_to_lint
                        if ka_root.relpath(f).startswith('kake/')]

    if not relfiles_to_lint:
        return

    # This forces us to import all the kake compile_rules.
    from kake import make                # @UnusedImport

    classes = (list(_all_subclasses(compile_rule.CompileBase)) +
               list(_all_subclasses(computed_inputs.ComputedInputsBase)))
    for cls in classes:
        class_file = cls.__module__.replace('.', '/') + '.py'
        if class_file not in relfiles_to_lint:
            continue

        claimed_used_context_keys = set(cls.used_context_keys())
        actual_used_context_keys = {}     # map from key to linenum where used

        class_source = inspect.getsource(cls)
        module_source = inspect.getsource(sys.modules[cls.__module__])

        # Find what line-number the class we're linting starts on.
        class_source_pos = module_source.find(class_source)
        class_startline = module_source.count('\n', 0, class_source_pos) + 1

        # Find what line-number class.used_context_keys() starts on.
        used_context_keys_pos = class_source.find('def used_context_keys')
        if used_context_keys_pos == -1:
            used_context_keys_line = 1
        else:
            used_context_keys_line = (class_source.count('\n', 0,
                                                         used_context_keys_pos)
                                      + class_startline)

        for m in _CONTEXT_USE_RE.finditer(class_source):
            if '@Nolint' not in m.group(0):
                key = m.group(1) or m.group(2) or m.group(3)
                linenum = (class_source.count('\n', 0, m.start())
                           + class_startline)
                actual_used_context_keys.setdefault(key, linenum)

        must_add = set(actual_used_context_keys) - claimed_used_context_keys
        must_remove = claimed_used_context_keys - set(actual_used_context_keys)

        for key in must_add:
            # We don't require people to register system keys (start with _)
            # or glob vars (start with '{').
            if not key.startswith(('_', '{')):
                yield (ka_root.join(class_file),
                       actual_used_context_keys[key],       # linenum
                       'Build rule uses "%s" but it is not listed in'
                       ' used_context_keys().  Add it there or mark'
                       ' it with @Nolint if this is in error.' % key)

        for key in must_remove:
            yield (ka_root.join(class_file),
                   used_context_keys_line,
                   'Build rule does not use "%s" but it is listed in'
                   ' used_context_keys().  Add it there or fix this'
                   ' linter if it is in error.' % key)
