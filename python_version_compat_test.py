#!/usr/bin/env python

import os
import subprocess
import unittest


class TestPy2Py3Compat(unittest.TestCase):
    """We need to be compatible with both python2 and 3.

    Test that we can at least import runlint.py under both.
    """
    def test_python2_compat(self):
        # If we're running this test from an external directory (e.g., from
        # webapp), take care to set the working directory for the subprocess
        # call. Note that if we're running this test from within
        # khan-linter-src, we need the cwd to be None, rather than the empty
        # string.
        cwd = os.path.dirname(__file__) or None
        subprocess.check_call(['python2', '-c',  'import runlint'], cwd=cwd)

    def test_python3_compat(self):
        cwd = os.path.dirname(__file__) or None
        subprocess.check_call(['python3', '-c',  'import runlint'], cwd=cwd)
