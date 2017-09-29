"""Linters that warn about common problems with handlebars templates.

We also lint javascript found inside handlebars templates.
"""

from __future__ import absolute_import

import re

from shared.testutil import lintutil

import jinja2_lint       # for its run_eslint() helper
from js_css_packages import js_in_html


def lint_javascript_in_handlebars(files_to_lint):
    """Run eslint on javascript content inside handlebars files.

    We want to make sure that the js in our handlebars files has no
    unused variables/etc, so we can do better dependency analysis on
    it.
    """
    files = lintutil.filter(files_to_lint, suffix='.handlebars')

    lint_inputs = []      # list of filename/contents pairs

    for f in files:
        contents_of_f = lintutil.file_contents(f)

        # extract_js_from_html actually can return several versions
        # of the js contents, each with a different branch of an
        # if/else commented out.  (So for input like
        #  <script>var x = { {%if c%}y: 4{%else%}y: 5{%endif%} };</script>
        # we'd see both 'var x = { y: 4 };' and 'var x = { y: 5 }')
        # We lint all such strings and combine the output.
        js_contents_iter = js_in_html.extract_js_from_html(contents_of_f,
                                                           "handlebars",
                                                           file_name=f)

        try:
            for js_contents in js_contents_iter:
                lint_inputs.append((f, js_contents))
        except Exception, why:
            yield (f, 1, 'HTML parse error: %s' % why)
            continue

    errors = jinja2_lint.run_eslint(lint_inputs)
    # We sort and uniquify at the same time.  Unique is an issue because
    # often each of the js_contents_iters give the same error.
    errors = sorted(set(errors), key=lambda l: (l[0], int(l[1]), l[2:]))
    for (fname, bad_linenum, msg) in errors:
        yield (fname, bad_linenum, msg)


_HANDLEBARS_DEBUGGER_RE = re.compile(r'\{\{\s*debugger\s*\}\}')


def lint_handlebars_debugger_statement(files_to_lint):
    """Make sure we don't have any stray {{debugger}} statements."""
    files = lintutil.filter(files_to_lint, suffix='.handlebars')
    for (fname, linenum, _) in lintutil.find_lines(
            files, _HANDLEBARS_DEBUGGER_RE):
        yield (fname, linenum,
               'All {{debugger}} statements should be removed.')
