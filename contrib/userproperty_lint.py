"""Linter that warns about using the dangerous UserProperty.

UserProperty's user_id value can change depending on whether or not Google
currently has a Google account registered w/ an email address that matches
UserProperty's email property. That means when a user changes email settings
in their Google account it can change the behavior of our queries. We don't
want that.
"""
from __future__ import absolute_import

import re

from shared.testutil import lintutil


# This captures any use of UserProperty on a db or ndb model. It will not
# capture subclasses of UserProperty, but we don't expect any of those to be
# around.
_USERPROPERTY_RE = re.compile(r'\bn?db\.UserProperty\(', re.DOTALL)


def lint_no_user_property(files_to_lint):
    """Enforce that nobody uses UserProperty.

    ...unless marked as an explicitly approved legacy usage via @Nolint.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')
    for filename in files_to_lint:
        contents = lintutil.file_contents(filename)
        for fn_match in _USERPROPERTY_RE.finditer(contents):
            # Make sure there's no @Nolint anywhere around this function.
            newline = contents.find('\n', fn_match.end())
            newline = newline if newline > -1 else len(contents)
            if '@Nolint' in contents[fn_match.start():newline]:
                continue

            linenum = 1 + contents.count('\n', 0, fn_match.start())
            yield (filename, linenum,      # filename and linenum
                   "Do not use UserProperty, it is not safe. Use UserData's "
                   "key as its foreign key, instead.")

