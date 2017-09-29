"""Lint rules to make sure we can parse GAE config files.

These files are uploaded to App Engine, and the upload will fail if they're not
valid.  We check that they're at least parseable as yaml, and a few other
things; see the linters below for details.

TODO(benkraft): Some or all of the tests in yaml_test.py should be converted to
linters and move here.
"""
from __future__ import absolute_import

import ast
import importlib
import os.path

from shared import ka_root
from shared.testutil import lintutil
import yaml

import modules_util


def lint_yamls_are_parseable(files_to_lint):
    """Enforce that any yamls to be uploaded to app engine are parseable."""
    files_to_lint = lintutil.filter(files_to_lint, suffix='.yaml')
    for filename in files_to_lint:
        with open(filename) as f:
            try:
                yaml.safe_load(f)
            except yaml.parser.ParserError as e:
                yield (filename,
                       e.problem_mark.line + 1,  # yaml.Mark is 0-indexed
                       'Error parsing yaml: %s %s.' % (e.problem, e.context))


def _lint_single_wsgi_entrypoint_import(filename):
    """Returns a lint-error tuple, or None if the file is ok."""
    with open(ka_root.join(filename)) as f:
        module_ast = ast.parse(f.read())
        for stmt in module_ast.body:
            # If we see a string first, that's the docstring; that's ok, we'll
            # check the next one.
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Str):
                continue
            # We also allow __future__ imports first, because python wants it
            # that way.  Those have to be in 'from __future__ import *' format.
            elif (isinstance(stmt, ast.ImportFrom) and
                  stmt.module == '__future__'):
                continue
            # If the first import is appengine_config, we're happy!  Since
            # appengine_config is toplevel, we don't have to worry about
            # from-imports.
            elif (isinstance(stmt, ast.Import) and
                  stmt.names[0].name == 'appengine_config'):
                return None
            # Otherwise, we're sad.  Return a lint error.
            else:
                return (filename, stmt.lineno,
                        "Must import appengine_config before any other "
                        "(non-__future__) imports.")
        # If the file has nothing other than docstrings and __future__ imports,
        # something has gone horribly wrong; consider it an error to be safe.
        return (filename, 1,
                "This file doesn't look like a WSGI entrypoint!  Are you sure "
                "handlers-*.yaml is set up right?")


def lint_all_wsgi_entrypoint_imports(files_to_lint):
    """Enforce that every WSGI entrypoint imports appengine_config first.

    On App Engine Standard, appengine_config is guaranteed to be imported
    before anything else.  But this isn't guaranteed on VM, which is bad
    because our code assumes it!  So we require every WSGI entrypoint to
    manually import it first thing, before any other imports.  (It likely only
    matters that it's before all first-party and shared imports, but we require
    that it be first to keep things simple.  We do allow __future__ imports
    first, since those are easy to check and python wants them first.)
    """
    entrypoint_filenames = set()
    for gae_module_name in modules_util.all_modules:
        entrypoint_module_names = (
            modules_util.app_yaml_entrypoint_modules(gae_module_name))
        for entrypoint_module_name in entrypoint_module_names:
            filename = importlib.import_module(entrypoint_module_name).__file__
            # replace .pyc, .pyo etc.
            filename = os.path.splitext(filename)[0] + '.py'
            entrypoint_filenames.add(ka_root.relpath(filename))

    if lintutil.filter(files_to_lint, suffix='.yaml'):
        # If any yaml files were modified, we need to recheck all entrypoints.
        # TODO(benkraft): We should really only need to do this if any
        # module-yaml, or any yaml included by one, has changed, but
        # determining which those are is tricky, so we assume they all are.
        filenames_to_check = entrypoint_filenames
    else:
        # Otherwise, we just need to check changed entrypoints.
        files_to_lint = set(ka_root.relpath(f) for f in files_to_lint)
        filenames_to_check = entrypoint_filenames & files_to_lint

    for filename in filenames_to_check:
        if filename.startswith('third_party/'):
            continue
        maybe_error = _lint_single_wsgi_entrypoint_import(filename)
        if maybe_error:
            yield maybe_error
