#!/usr/bin/env python2
"""A script to add linter ignore lines to python files within webapp.

Use this when upgrading the linter so that you don't have to fix all the
existing violations of new rules immediately.

Important: ensure that `make lint` gives no violations before running this so
that you don't accidentally ignore any existing lint problems!

TODO(colin): support javascript too?
"""
import argparse
import os.path
import re
import subprocess

import runlint as khan_linter

lint_violation_re = re.compile(r'(?:W|E)\d+')
pep8_error_code_link = 'http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes'


def lint_with_todo_target(files, todo_target):
    files_to_lint = [
        file for file in khan_linter.find_files_to_lint(files)
        if file.endswith('.py')]
    for file in files_to_lint:
        try:
            # This is very slow!
            # But we don't have to run this often, and this is more
            # straightforward that patching and restoring stdout in this
            # process.
            # TODO(colin): use tools.io_util.send_output_to instead.
            lint = subprocess.check_output(
                [os.path.join('.', 'runlint.py'), file],
                stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            lint = e.output
        rules_violated = ','.join(sorted(set(
            lint_violation_re.findall(lint))))
        if rules_violated:
            with open(file) as f:
                contents = f.readlines()
            lint_disable_lines = [
                '# TODO(%s): fix these lint errors (%s)\n' % (
                    todo_target, pep8_error_code_link),
                '# pep8-disable:%s\n' % rules_violated,
            ]
            # A shebang or a `# coding:` line needs to come first
            if (contents[0].startswith('#!') or
                    contents[0].startswith('#') and 'coding' in contents[0]):
                contents = [contents[0]] + lint_disable_lines + contents[1:]
            else:
                contents = lint_disable_lines + contents
            with open(file, 'w') as f:
                f.writelines(contents)
            print 'Added lint ignore line to %s' % file
        else:
            print 'No lint problems in %s' % file


def main():
    parser = argparse.ArgumentParser(
        description='Add python lint rule ignore lines')
    parser.add_argument(
        '--todo_target',
        default='infrastructure',
        help='person to whom the lint fix TODO should be assigned')
    parser.add_argument(
        'files_to_lint', nargs='*', default=['.'],
        help='the files or directories check')
    args = parser.parse_args()
    lint_with_todo_target(args.files_to_lint, args.todo_target)


if __name__ == '__main__':
    main()
