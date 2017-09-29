"""Lint rules to make sure we don't add GAE features missing from Flex.

We are planning to move our codebase from AppEngine Classic to
AppEngine Flex.  As we go through that process, we'll be
removing/rewriting API calls that are classic-specific, and don't
exist in appengine flex.  We want to make sure people don't add in new
API calls of that nature before we actually do the switchover!  This
lint test ensures that.
"""

from __future__ import absolute_import

import re

from shared.testutil import lintutil


# Each pair is the bad module, and the replacement.
_BAD_MODULES = (
    ('blobstore', 'gcs (third_party.cloudstorage)'),
    )

_BAD_MODULES_RES = tuple([
    (re.compile(r'import %s' % re.escape(l[0])), l[0], l[1])
    for l in _BAD_MODULES])


def lint_gae_specific_code(files_to_lint):
    """Enforce that we do not add new code that will not work on flex.

    This lint check is only for the 'main' webapp service; other services
    (in services/) may be running on appengine classic, and can use this
    functionality.  In fact, sometimes we separated them out into services
    for just that reason!
    """
    files_to_lint = lintutil.filter(
        files_to_lint, suffix='.py', exclude_substrings=['/services/'])
    for (bad_module_re, bad_module, replacement) in _BAD_MODULES_RES:
        for (f, linenum, _) in lintutil.find_lines(files_to_lint,
                                                   bad_module_re):
            yield (f, linenum,
                   'Do not import %s -- use %s instead.'
                   % (bad_module, replacement))

