This repository contains linting tools for Khan Academy's codebase.

It uses existing linting tools (pep8, pyflakes, jshint, etc), but has been
modified to suit Khan Academy's slightly different style guides.

This repository also contains a wrapper scripts that can be used as a
pre-commit hook for Git.

Installation
============
You should add the local `bin/` directory to your system $PATH, for example:

    export PATH=$PATH:~/path/to/khan-linter/bin

All dependencies are vendored within the repository itself, so no installation
beyond cloning this repository is required.

Usage
=====

Manual
------
If you would like to lint manually, invoke `/path/to/runlint.py` or `ka-lint`.

By default, this will lint all files under the current directory.  Alternately,
you can specify files on the command line to lint.  See

    ka-lint --help

for more options.

Automatic
---------
You can update the blacklist file in this repository to control what files
should not be linted at all.  Alternately, you can create a blacklist of your
own, and use the `--blacklist_file` flag to `runlint.py` (you'll have to modify
`hghook.py` or `githook.py` to pass in the name of the blacklist file as well).

To suppress the lint check, set the environment variable `FORCE_COMMIT=1` prior
to calling `git commit`.

Testing opening a diff.