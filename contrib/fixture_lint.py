"""Verify that all fixtures have components."""

from __future__ import absolute_import

import os

from shared.testutil import lintutil


def lint_all_fixtures_match_components(files_to_lint):
    files = lintutil.filter(files_to_lint,
                            prefix='javascript/', suffix='.fixture.js')
    for f in files:
        component_path = f[:-len(".fixture.js")]
        if not os.path.isfile(component_path):
            yield(f, 1,
                  "Expected to find a React component at '{}'. If you just "
                  "moved that component, be sure to move "
                  "this fixture too.".format(component_path))
