#!/usr/bin/env python

import subprocess
import unittest


class TestPy2Py3Compat(unittest.TestCase):
    """We need to be compatible with both python2 and 3.

    Test that we can at least import runlint.py under both.
    """
    def test_python2_compat(self):
        subprocess.check_call(['python2', '-c',  'import runlint'])

    def test_python3_compat(self):
        subprocess.check_call(['python3', '-c',  'import runlint'])
