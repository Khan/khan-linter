#!/usr/bin/env python

import unittest

import runlint


class TestBlacklist(unittest.TestCase):
    _BLACKLIST = 'lint_blacklist_for_testing.txt'

    def assert_in_blacklist(self, fname):
        self.assertTrue(runlint._file_in_blacklist(fname, self._BLACKLIST))

    def assert_not_in_blacklist(self, fname):
        self.assertFalse(runlint._file_in_blacklist(fname, self._BLACKLIST))

    def test_simple(self):
        self.assert_in_blacklist('main.py')
        self.assert_not_in_blacklist('main.p')
        self.assert_not_in_blacklist('main.pyy')

    def test_directory(self):
        self.assert_in_blacklist('.git')
        self.assert_in_blacklist('.git/foo/bar')
        self.assert_in_blacklist('vendor')
        self.assert_in_blacklist('vendor/baz/bang')

    def test_leading_starstar(self):
        self.assert_in_blacklist('compressed.js')
        self.assert_in_blacklist('foo/compressed.js')
        self.assert_in_blacklist('foo/bar/compressed.js')

    def test_dir_detection(self):
        self.assert_in_blacklist('runlint.py')
        self.assert_not_in_blacklist('runlint.py/foo')

        self.assert_in_blacklist('main.py')
        # This is in the blacklist because main.py does not exist.
        self.assert_in_blacklist('main.py/foo')


if __name__ == '__main__':
    unittest.main()
