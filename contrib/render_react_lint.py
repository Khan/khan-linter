"""Linters that warn about common problems with {{ render_react() }}."""

from __future__ import absolute_import

import os
import re

from shared import ka_root
from shared.testutil import lintutil


RENDER_REACT_RE = re.compile(r'{{\s*render_react\s*\(\s*[\"\']([^\"\']*)')


def lint_every_rendered_component_has_a_fixture(files_to_lint):
    """Check that every component we render has an associated fixture file.

    In order to test that a particular react component can be
    server-side rendered, we need to actually try to render it with a
    particular value for props.  This is what component.fixture.js
    files are for.  We just make sure the people write them!

    For now, we allow the fixture file to be empty (just `[]`).  Later
    we may insist on actually useful fixtures.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.html')

    for f in files_to_lint:
        contents_of_f = lintutil.file_contents(f)
        for m in RENDER_REACT_RE.finditer(contents_of_f):
            component_file = m.group(1)
            # To be server-side renderable, the fixture file has to be
            # a javascript file, not jsx or something else.
            fixture_file = component_file + '.fixture.js'
            if not os.path.exists(ka_root.join(fixture_file)):
                linenum = contents_of_f.count('\n', 0, m.start()) + 1
                yield (f, linenum,
                       '%s must have an associated fixture file %s'
                       % (component_file, fixture_file))
