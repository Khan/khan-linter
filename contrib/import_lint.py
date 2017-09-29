"""Verifies that our `import` lines comport to our style guide.

Our style guide has various rules that are above and beyond what pep8
requires, for instance:
* We import `absolute_import` in every (first-party) module
* We have only one import per line, no commas
* We only import modules, not packages/directories (first-party code only)
* We only import whole modules, not symbols within modules

We also fix a bug in pyflakes dealing with imports of modules inside
packages, which makes it not properly identify when such imports
are unused, and when they're missing.
"""

from __future__ import absolute_import

import collections
import os
import re
import sys
import tokenize

from shared import ka_root
from shared.testutil import lintutil


def lint_no_backslashes(files_to_lint):
    """Complain if any import lines use backslashes for line continuation.

    While our style guide discourages end-of-line backslashes for line
    continuation, it's not normally something we'd lint on.  But I do
    in this case because the regexp for other import-linters will get
    confused in the presense of backslashes, and it's easy enough to
    use parens instead.
    """
    backslash_re = re.compile(r'^\s*(from|import)\b.*\\$', re.MULTILINE)

    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    for (filename, linenum, _) in lintutil.find_lines(files_to_lint,
                                                      backslash_re):
        yield (filename, linenum,
               "Use parens instead of backslash for line-continuation")


# filename: the file the import-line is found in
# lineno: line in the file where the input line starts
# colno: column where the import starts (0 for top-level imports)
# module: the parsed-out module being imported.  e.g. for
#     from foo.bar import baz as bang
#   module would be "foo.bar.baz".  For
#     from foo.bar import (baz, bang)
#   module would be "foo.bar.baz", which is not complete.  We're ok
#   with that since this line violates our style guide.
# name: what variable-name this import is assigned to.  For
#     from foo.bar import baz as bang
#   name would be "bang".
# level: 0 for "normal" imports, 1 for relative imports like '.a' or '.'
#   2 for relative imports liek '..a' or '..', etc.
# is_toplevel: True if the import is executed when the module is loaded,
#   False if it's executed later (because it's in a `def`).
# has_comma: true if we are importing multiple symbols on this import-line
# has_from: true the import has a `from` clause
# has_as: true the import has an `as` clause
ImportLine = collections.namedtuple(
    "ImportLine",
    ("filename", "lineno", "colno", "module", "name", "level", "is_toplevel",
     "has_comma", "has_from", "has_as"))


# NOTE: This is a complex regexp, but doesn't necessarily capture
# all the permutations of importing.  It's merely good enough to
# properly parse all the imports that our style guide allows, and
# if it's a non-style-guide compliant import (e.g. has a comma),
# to parse enough of it to know what the violation is.
# TODO(csilvers): would it be easier to parse the AST than to do
# this complex regexp?  That would also auto-handle imports in
# comments and strings, so we could remove the 'org.foo' special case.
_g_import_line_cache = {}    # from filename to pos-sorted list of import-lines


def _add_import_line(filename, il_dict):
    # All legal imports should have an import-part.
    assert 'import_part' in il_dict, il_dict

    from_part = il_dict.get('from_part')
    import_part = il_dict.get('import_part')
    as_part = il_dict.get('as_part')

    name = as_part if as_part else import_part

    # "level" is how many leading dots there are (for a
    # relative import like "from ..foo import bar").
    module_parts = []
    if from_part:
        level = len(from_part) - len(from_part.lstrip('.'))
        from_name = from_part[level:]
        if level > 0:
            # Handle relative paths.  Each dot is one dir-level up.
            filename_parts = ka_root.relpath(filename).split(os.sep)
            module_parts.extend(filename_parts[:-level])
        if from_name:
            module_parts.append(from_name)
    else:
        level = 0      # only "from" imports can be relative.
    module_parts.append(import_part)
    module = '.'.join(module_parts)

    import_line = ImportLine(filename=filename,
                             lineno=il_dict['lineno'],
                             colno=il_dict['colno'],
                             module=module,
                             name=name,
                             level=level,
                             is_toplevel=il_dict['is_toplevel'],
                             has_comma=il_dict.get('has_comma', False),
                             has_from=bool(from_part),
                             has_as=bool(as_part))
    _g_import_line_cache[filename].append(import_line)


def _get_import_lines(filename):
    """filename is an absolute path (as per the input to the linters)."""
    if filename not in _g_import_line_cache:
        # First, check for file-not-found.  We do it this way so we fill
        # the token-cache at the same time, which is useful later.
        try:
            next(lintutil.python_tokens([filename]), None)
        except IOError:   # file not found
            _g_import_line_cache[filename] = None
            return

        _g_import_line_cache[filename] = []

        # This would be a lot simpler using the AST visitor, but also
        # a lot slower.  We do simplify the state machine by assuming
        # legal python syntax.

        # il_dict holds information about this ImportLine:
        # * lineno, colno: the line and column where the import starts
        # * is_toplevel: True if the import is executed when the
        #   module is loaded, False if not (because it's in a `def`)
        # * from_part: the text following 'from', for from-imports
        # * import_part: the text following 'import'
        # * as_part: the text following 'as', if present
        # * has_comma: true if there's a comma in this import statement
        #   (indicating multiple modules being imported at once)
        il_dict = {}

        # next_field can be
        # * start: we're looking for a leading 'from' or 'import'
        # * from_part: we've seen 'from' and are looking for the
        #      text that comes after the `from`
        # * import_part: we've seen 'import' and are looking for
        #      the text that comes after the `import`.
        # * as_part: we've seen 'as' and are looking for
        #      the token that comes after the `as`.
        # * end: we've seen an 'as' and read the as-text, and
        #      we are now looking for a comma or the end of the
        #      import statement.
        next_field = 'start'
        inside_def = False
        for (_, ttype, token, (lineno, colno), _, line) in (
                lintutil.python_tokens([filename])):
            if token in ('(', ')') or ttype == tokenize.NEWLINE:
                continue    # ignore parens and newlines

            # Update inside_def.  If we see a `def`, we assume all code
            # that follows it is inside the def until we see another
            # unindented line (at col 0) that doesn't start with `def`.
            # This is very conservative, but good enough for us.
            if token == 'def':
                inside_def = True
            elif colno == 0 and not token.isspace():
                inside_def = False

            # The state machine cascades, except for 'start' which
            # we can cascade to from 'end', so we handle last.

            if next_field == 'from_part':
                if token == 'import':
                    assert il_dict['from_part'], il_dict
                    next_field = 'import_part'
                else:
                    il_dict['from_part'] = il_dict.get('from_part', '') + token
                continue

            if next_field == 'import_part':
                if token == 'as':
                    assert il_dict['import_part'], il_dict
                    next_field = 'as_part'
                    continue
                elif token == '.':
                    # We are in the middle of 'a.b.c'
                    il_dict['import_part'] += token
                    continue
                elif ('import_part' not in il_dict or
                      il_dict['import_part'].endswith('.')):
                    il_dict['import_part'] = (il_dict.get('import_part', '') +
                                              token)
                    continue
                else:
                    assert il_dict['import_part'], il_dict
                    next_field = 'end'         # we'll parse it below

            if next_field == 'as_part':
                il_dict['as_part'] = token
                next_field = 'end'
                continue

            if next_field == 'end':
                il_dict['has_comma'] = (token == ',')
                _add_import_line(filename, il_dict)
                il_dict = {}
                next_field = 'start'

            if next_field == 'start':   # NOTE: can fall through from above
                if token == 'from' and line.lstrip().startswith('from'):
                    il_dict['lineno'] = lineno
                    il_dict['colno'] = colno
                    # If our `from` occurs at the start of a line we're
                    # definitely a top-level import.  But we can be even
                    # if it's not:
                    # try:
                    #    import lxml
                    # except ImportError: ...
                    # This is why we maintain `inside_def`, which is only
                    # true if we've seen a `def` more recently than we
                    # saw a (non-def) unindented line (including this one).
                    # This is conservative but works well in practice.
                    il_dict['is_toplevel'] = not inside_def
                    next_field = 'from_part'
                    continue
                elif token == 'import' and line.lstrip().startswith('import'):
                    il_dict['lineno'] = lineno
                    il_dict['colno'] = colno
                    il_dict['is_toplevel'] = not inside_def
                    next_field = 'import_part'
                    continue
                else:
                    continue

    return _g_import_line_cache[filename]


_first_party_package_cache = {}
_module_cache = {}       # module to True/False if its file exists on the path


def _is_a_first_party_package(module_name):
    """Return true if module_name is a first-party package (aka dir).

    A package is a directory, as opposed to a module which is a filename.
    We say whether module_name, when interpreted relative to ka_root is
    a package or not.  It only is if
        ka_root/module/converted/to/path/__init__.py
    exists.
    """
    if module_name not in _first_party_package_cache:
        package = ka_root.join(*(module_name.split('.') + ['__init__.py']))
        _first_party_package_cache[module_name] = os.path.exists(package)
    return _first_party_package_cache[module_name]


def _is_a_module_or_package(module_name):
    """Return true if module_name is a module or package (dir).

    For every entry in sys.path, we look at
       path_root/module/converted/to/path.py
    (However, we only consider absolute paths on sys.path, so the
    results of this script do not depend on where it is run.
    fix_sys_path(), which runlint.py imports, makes sure that ka-root
    is in sys.path as an absolute path, which is the most important thing.)
    """
    # I wanted to cache where each package lives in sys.path to speed
    # up this for-loop, but it's possible to "merge" path entries (via
    # `package.__path__`), meaning third_party.boto and
    # third_party.idna, say, are found relative to different sys.path
    # entries.  Thus, we have to check every entry for every module.
    if module_name not in _module_cache:
        if module_name in sys.builtin_module_names:
            # This is quick enough that we don't bother to cache it.
            return True

        module_parts = module_name.split('.')
        for root in sys.path:
            if not os.path.isabs(root):
                continue
            module_paths = (os.path.join(root, *module_parts) + '.py',
                            os.path.join(root, *module_parts) + '.so',
                            os.path.join(root, *module_parts) + '/__init__.py')
            if any(os.path.exists(p) for p in module_paths):
                _module_cache[module_name] = True
                break
        else:
            _module_cache[module_name] = False

    return _module_cache[module_name]


def lint_absolute_import(files_to_lint):
    """Make sure we use absolute imports everywhere.

    Suppose you have code like a top-level util.py and also
    email/util.py, and you do "import util".  If you're doing that
    from email/foo.py, then it will import email/util.py instead of
    the top-level util.py.  Using absolute imports everywhere avoids
    the risk of that problem.  It also makes it more obvious to those
    looking at the code, exactly what's being imported.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    for f in files_to_lint:
        import_lines = _get_import_lines(f)

        if not import_lines:
            # No imports?  Then no need for an absolute-import directive.
            continue

        if any(i.module == '__future__.absolute_import' for i in import_lines):
            # Has an absolute-import, we're happy.
            continue

        contents = lintutil.file_contents(f)
        if contents.startswith('#!'):
            # If the file can be run as a script, then absolute-import
            # doesn't always work since we don't automatically have
            # webapp-root in the pythonpath for scripts.  So we don't
            # require absolute-import in that case.
            continue

        # __future__ imports come first, so the best line number to
        # report for the error is the first import line.
        yield (f, import_lines[0].lineno,
               'Modules must use: from __future__ import absolute_import')


def lint_comma(files_to_lint):
    """Find imports that use a comma to import multiple things on one line.

    KA style is we only have one import per line, so we just complain.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    for f in files_to_lint:
        import_lines = _get_import_lines(f)
        for import_line in import_lines:
            if import_line.has_comma:
                yield (f, import_line.lineno,
                       "Use one import per line, rather than a comma.")


def lint_package_imports(files_to_lint):
    """Find cases where we import a package (directory) rather than a module.

    For instance, "import emails".  That is not a module, it's a
    directory.

    Sometimes importing a directory is correct, for third-party
    modules with non-trivial __init__.py's.  But it's never right for
    our code.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    for f in files_to_lint:
        import_lines = _get_import_lines(f)
        for import_line in import_lines:
            if import_line.module.startswith(('__future__', 'third_party')):
                # The rules are different for third-party code, and
                # __future__'s aren't even real modules.
                continue
            if _is_a_first_party_package(import_line.module):
                contents = lintutil.file_contents(f)
                corrections = re.findall(r'%s\.[\w_]+' % import_line.name,
                                         contents)
                yield (f, import_line.lineno,
                       "Do not import the whole directory '%s'; "
                       "import the modules inside it, possibly: %s"
                       % (import_line.module,
                          ', '.join(sorted(set(corrections)))))


def lint_redundant_imports(files_to_lint):
    """You don't need to do both `import a.b` and `from a import b`!"""
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    for f in files_to_lint:
        import_lines = _get_import_lines(f)
        import_modules = {}    # map from module to import_line

        for import_line in import_lines:
            other_import = import_modules.get(import_line.module, None)
            if other_import:
                yield (f, import_line.lineno,
                       "Already imported on line %s"
                       % other_import.lineno)
            else:
                # It's common to import the same module multiple times
                # if it's within functions (the import only exists in
                # a limited scope) or try/except blocks, so we don't
                # complain if something shadows another non-top-level
                # import.
                if import_line.colno == 0:
                    import_modules[import_line.module] = import_line


def lint_symbol_imports(files_to_lint):
    """Find cases where we import a symbol rather than a module.

    For instance, "from main import application".  That is not a module,
    it's a variable defined within a module.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    for f in files_to_lint:
        import_lines = _get_import_lines(f)
        for import_line in import_lines:
            # You can only import a symbol via the 'from ... import' syntax
            if not import_line.has_from:
                continue
            if import_line.module.startswith('__future__'):  # not a real dir
                continue

            # TODO(csilvers): our style guide has an exception
            # allowing the import of individual symbols from
            # third-party packages which document this as a best
            # practice.  Add a special-case to ignore those, here.
            # (Or amend the style guide to remove the exception :-) )

            if not _is_a_module_or_package(import_line.module):
                # While we may not be a module or a package, the thing
                # containing us should definitely be.  If it's not, or
                # if it's a package but an empty one, then we're
                # importing something that doesn't (now) exist,
                # probably an auto-generated package.  We just ignore
                # it; we can't say anything useful about it.
                module_parent = import_line.module.rsplit('.', 1)[0]
                module_parent_as_package = ka_root.join(
                    module_parent.replace('.', os.sep),
                    '__init__.py')
                if (not _is_a_module_or_package(module_parent) or
                    (os.path.exists(module_parent_as_package) and
                     os.stat(module_parent_as_package).st_size == 0)):
                    continue

                actual_module = import_line.module.rsplit('.', 1)[0]
                yield (f, import_line.lineno,
                       "Import the whole module %s, not individual symbols "
                       "inside it" % actual_module)


def lint_unused_and_missing_imports(files_to_lint):
    """Report on import errors that pyflakes should catch, but doesn't.

    In theory, pyflakes can detect when an import is unused ("unused
    import"), and when an import is needed but missing ("undefined
    symbol"), but it does not deal well with modules inside packages.
    Consider the following code:
        import login.dupeaccount                # @Nolint(for demonstration)
        import login.postlogin                  # @Nolint(for demonstration)
        a = login.dupeaccount.DupeAccount
        b = login.oauth.OAuthApproval
    pyflakes won't complain about either a) the unnecessary postlogin
    import, or b) the missing oauth import.  See
        https://github.com/PyCQA/pyflakes/issues/137
    This lint check checks for both of them.

    Experimentation shows that pyflakes does fine for all `from`
    imports and `as` imports, but if you just do `import
    pkg.something`, then if you use pkg.somethingelse in your code
    then pyflakes doesn't detect it.  So we only focus on those
    imports.

    Because both lints depend on how symbols are used in code, we
    use the tokenizer rather than raw regexps, so we skip uses of
    symbols inside comments and strings.  Otherwise we have way too
    many errors!
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    pyflakes_can_handle = lambda il: ('.' not in il.module or
                                      il.name != il.module)   # 'as' or 'from'

    for f in files_to_lint:
        import_lines = _get_import_lines(f)

        # If we see both content.foo and content.foo.bar as imports,
        # we just keep the more general of the two: content.foo.  This
        # should only happen for third-party code (which is the only
        # case we're allowed to import directories).  This means we
        # won't do a great job of telling if content.foo.bar is used
        # or not, sadly.
        # TODO(csilvers): at least check that content.foo.bar is used.
        import_lines = [il for il in import_lines
                        if not any(il.name.startswith(other_il.name + '.')
                                   for other_il in import_lines)]

        # We skip import-lines with commas; they are difficult to deal
        # with here, so let's let the no-comma linter resolve them first.
        # We also skip `__future__` which is not a real import.
        # Finally, we skip import-lines that we have determined pyflakes
        # can correctly say "unused import" for.
        import_lines = [il for il in import_lines
                        if (not il.has_comma and
                            not il.module.startswith('__future__') and
                            not pyflakes_can_handle(il))]

        # Break up the import names into a trie, with leaf nodes saying
        # the line-no of the import-line in the file.
        # So for content.foo.bar, content.foo.baz, and content.qux:
        #    {'content': {'foo': {'bar': 0, 'baz': 3}, 'qux': 6}}
        # (Later, some of these leaf nodes will be changed to "SEEN".)
        import_trie = {}
        for import_line in import_lines:
            root = import_trie
            for part in import_line.name.split('.'):
                root.setdefault(part, {})
                (last_root, last_part) = (root, part)   # used below
                root = root[part]
            last_root[last_part] = import_line.lineno

        # We now go through the file in token-order.  For every import
        # we look at the "package", which is the first level of the
        # trie.  Here's what we look for:
        #    a) We ignore "import <package>", which is our definition
        #       We also ignore "from <package>", which is a definition
        #       of another import.
        #    b) We ignore "'.' <package>", which looks like a use of
        #       our package but must be some other symbol (a class var).
        #    c) If we see "'not-.' <package> 'not-.'" it means our
        #       package-name is (probably) being redefined as a variable,
        #       so we stop checking for package-name for the rest of the
        #       file.  (If we were really good we'd try to figure out
        #       when the var went out of scope, but...)
        #    d) If we see 'not-.' <package> '.' <not-in-trie>
        #       we complain about a missing import.  We do this for
        #       every level of the trie.
        #    e) If we see 'not-.' <full-path-through-trie> it means
        #       that import is used, so we mark that fact in the trie
        #       by changing the import-pos from an integer to 'USED'.
        # Note that because the package must occur after a non-`.` but
        # every other level of the trie must occur after a `.`, there
        # can never be overlapping matches, making our algorithm much
        # simpler!

        token_infos = list(lintutil.python_tokens([f]))
        tokens = [token for (_, _, token, _, _, _) in token_infos]
        i = -1
        while i + 1 < len(tokens):
            # We do this here so we don't have to do it for each `continue`.
            i += 1

            # At this point, we're not in the middle of matching
            # anything in the trie, but it's time to start!
            # But first consider cases (a) and (b).
            if i > 0 and tokens[i - 1] in ('.', 'import', 'from'):
                continue

            # Are we ready to start matching?
            if tokens[i] not in import_trie:   # ...I guess not
                continue

            # If we get here, we *are* ready to start matching!  But
            # before we get too excited, let's consider case (c).  If
            # it applies, we "stop checking for package-name" by just
            # deleting the package-name from the trie.
            if i + 1 < len(tokens) and tokens[i + 1] != '.':
                del import_trie[tokens[i]]
                continue

            # OK, let's see how far this match goes by traversing the trie.
            current_trie_pos = import_trie
            module_parts_so_far = []
            while True:
                if tokens[i] not in current_trie_pos:
                    # We want to traverse the trie some more and can't.
                    # That means we are using a module that was never
                    # imported.  Complain!
                    (lineno, _) = token_infos[i][3]
                    yield (f, lineno,
                           'Missing import: maybe %s'
                           % '.'.join(module_parts_so_far + [tokens[i]]))
                    break

                if not isinstance(current_trie_pos[tokens[i]], dict):
                    # We've successfully traversed the trie all the way
                    # to a leaf!  Mark this import as being used.
                    current_trie_pos[tokens[i]] = "USED"
                    break

                if i + 2 >= len(tokens) or tokens[i + 1] != '.':
                    # There's no more room to extend our identifier,
                    # but we haven't made it to a leaf.  This means
                    # we're referencing something in a package
                    # (directory) and not a module.  In theory, that
                    # shouldn't happen.
                    (lineno, _) = token_infos[i][3]
                    yield (f, lineno,
                           'Unexpectedly referencing a non-module: %s'
                           % '.'.join(module_parts_so_far))
                    break

                # Otherwise, let's continue down the trie.
                current_trie_pos = current_trie_pos[tokens[i]]
                module_parts_so_far.append(tokens[i])
                i += 2         # 1 for our token, 1 for the following dot

        # We've parsed the entire file!  Let's see which trie entries
        # were never used.
        def _find_unused_imports(root, module_parts_so_far):
            """Yields (module_name, lineno) pairs of errors."""
            for (part, subtree) in root.iteritems():
                if isinstance(subtree, dict):  # Recurse
                    for error in _find_unused_imports(
                            subtree, module_parts_so_far + [part]):
                        yield error
                elif subtree == 'USED':        # Used import
                    pass
                else:                          # Unused import
                    contents = lintutil.file_contents(f)
                    lines = contents.splitlines(True)
                    # Here, `subtree` stores the line the import was on
                    lineno = subtree
                    # If it has an "@UnusedImport" decorator, unused == ok!
                    if '@UnusedImport' not in lines[lineno - 1]:
                        yield (".".join(module_parts_so_far + [part]), lineno)

        for (module_name, lineno) in _find_unused_imports(import_trie, []):
            yield (f, lineno, "Unused import: %s" % module_name)


# A map from module-name to module-name of top level imports.  (We
# have another map for "late" imports: imports inside functions.)
# These are for first-party code; other code may have a key in this
# dict but the value will be empty.
_direct_top_level_imports = {}
_direct_late_imports = {}
_transitive_top_level_imports = {}


def _get_top_level_imports(module):
    if module not in _direct_top_level_imports:
        # We only care about first-party files here, so we assume
        # that this module is relative to ka-root.  If not, then
        # it's safe to ignore it anyway!  We also ignore third-party
        # files explicitly.
        if module.startswith('third_party.'):
            path = ''                                  # force a file-ignore
        else:
            path = module.replace('.', os.sep) + '.py'
        import_lines = _get_import_lines(ka_root.join(path))
        if import_lines is None:                       # file not found
            _direct_top_level_imports[module] = None
            _direct_late_imports[module] = None
        else:
            _direct_top_level_imports[module] = frozenset([
                il.module for il in import_lines if il.is_toplevel])
            _direct_late_imports[module] = frozenset([
                il.module for il in import_lines if not il.is_toplevel])
    return _direct_top_level_imports[module] or set()


def _get_late_imports(module):
    if module not in _direct_late_imports:
        _get_top_level_imports(module)   # also initializes the late imports
    return _direct_late_imports[module] or set()


def _calculate_transitive_imports(module):
    """Calculate all imports this module imports, directly or indirectly.

    This may fill the _transitive_top_level_imports cache for other
    modules as well.
    """
    if module not in _transitive_top_level_imports:
        direct_imports = _get_top_level_imports(module)

        # We initialize the transitive-imports cache with the direct
        # imports.  This protects against cycles.  Then we recurse.
        _transitive_top_level_imports[module] = set(direct_imports)
        for direct_import in direct_imports:
            _transitive_top_level_imports[module] |= (
                _calculate_transitive_imports(direct_import))

    return _transitive_top_level_imports[module]


def _add_edge(module, importee):
    """Add a module -> importee edge to all the transitive-imports."""
    # Update the direct-import cache.
    _direct_top_level_imports[module] = frozenset(
        _get_top_level_imports(module) | {importee})

    # Update the transitive-import cache.  Basically, when we add the
    # edge A -> B, everyone who had A in their transitive imports now
    # has B and all its transitive imports as well.
    new_transitive_imports = (_calculate_transitive_imports(importee) |
                              {importee})
    for transitive_imports in _transitive_top_level_imports.itervalues():
        if module in transitive_imports:
            transitive_imports.update(new_transitive_imports)


class _CircuitFinder(object):
    """Implements Donald B. Johnson's algorithm for finding all cycles.

    The paper describing the algorithm (inscrutably) is here:
    http://www.cs.tufts.edu/comp/150GA/homeworks/hw1/Johnson%2075.PDF

    This version is based on the code at
    https://github.com/hellogcc/circuit-finding-algorithm/blob/master/CircuitFinder.h
    """
    def unblock(self, v):
        self.blocked[v] = False
        while self.blockages[v]:
            w = self.blockages[v].pop()
            if self.blocked[w]:
                self.unblock(w)

    def find_paths(self, start_vertex, target_vertex):
        self.path.append(start_vertex)
        self.blocked[start_vertex] = True

        saw_a_cycle = False
        for adjacent_vertex in self.adjacency_matrix[start_vertex]:
            if adjacent_vertex < target_vertex:
                # Not in the subgraph we're considering.
                continue
            elif adjacent_vertex == target_vertex:
                saw_a_cycle = True
                yield self.path + [self.path[0]]
            elif not self.blocked[adjacent_vertex]:
                for circuit in self.find_paths(adjacent_vertex, target_vertex):
                    saw_a_cycle = True
                    yield circuit

        if saw_a_cycle:
            self.unblock(start_vertex)
        else:
            for adjacent_vertex in self.adjacency_matrix[start_vertex]:
                if start_vertex not in self.blockages[adjacent_vertex]:
                    self.blockages[adjacent_vertex].add(start_vertex)

        self.path.pop()

    def find_circuits(self, s):
        self.path = []
        self.blocked = [False] * self.n
        self.blockages = [set() for _ in xrange(self.n)]
        return self.find_paths(s, s)

    def run(self, adjacency_matrix):
        """adjacency_matrix is a list of list-of-small-ints.

        If adjacency_matrix[0] = [4, 7] that means that node 0
        had edges to node 4 and node 7.  In our case, nodes are
        modules and edges are imports; the caller must map
        the modules to small integers.
        """
        self.adjacency_matrix = adjacency_matrix
        self.n = len(self.adjacency_matrix)
        for v in xrange(self.n):
            for cycle in self.find_circuits(v):
                yield cycle


def _normalized_import_cycle(cycle_as_list, sort_candidates):
    """Given an import cycle specified as a list, return a normalized form.

    You represent a cycle as a list like so: [A, B, C, A].  This is
    equivalent to [B, C, A, B]: they're both the same cycle.  But they
    don't look the same to python `==`.  So we normalize this list to
    a data structure where different representations of the cycle
    *are* equal.  We do this by rearranging the cycle so that a
    canonical node comes first.  We pick the node to be the node in
    cycle_as_list that is also in sort_candidates.  If there are
    multiple such nodes, we take the one that's first alphabetically.

    We assume a simple cycle (that is, one where each node has only
    one incoming edge and one outgoing edge), which means that each
    node only occurs here once, so the sort order is uniquely defined.
    """
    sort_elts = [node for node in cycle_as_list if node in sort_candidates]
    if not sort_elts:     # probably impossible, but best to be safe
        sort_elts = cycle_as_list
    min_index = cycle_as_list.index(min(sort_elts))
    # The weird "-1" here is because A occurs twice in the input
    # cycle_as_list, but we want min_elt to occur twice in the output.
    return tuple(cycle_as_list[min_index:-1] + cycle_as_list[:min_index + 1])


def _find_all_cycles(modules):
    """Use Donald B Johnson's algorithm to find all cycles in our import graph.

    Most work is done in _CircuitFinder.  We just have to convert all
    our modules to small integers and back, and create the adjacency
    matrix holding all the imports.
    """
    # Initialize with the modules we're linting.
    module_to_index = {}
    index_to_module = []
    adjacency_matrix = []

    def _add_imports_to_mappings(module):
        if module in module_to_index:
            return module_to_index[module]

        my_index = len(index_to_module)     # we're going to add ourselves
        module_to_index[module] = my_index
        index_to_module.append(module)
        adjacency_matrix.append([])

        for i in _get_top_level_imports(module):
            import_index = _add_imports_to_mappings(i)
            adjacency_matrix[my_index].append(import_index)

        return my_index

    # This isn't necessarily a complete graph of our codebase, but it
    # includes every module that is related to one of the files we're
    # linting.
    for module in modules:
        _add_imports_to_mappings(module)

    for cycle_indices in _CircuitFinder().run(adjacency_matrix):
        cycle = [index_to_module[i] for i in cycle_indices]
        cycle = _normalized_import_cycle(cycle, sort_candidates=modules)
        yield cycle


def lint_circular_imports(files_to_lint):
    """Report on all circular imports found in files_to_lint.

    A circular import is when A imports B imports C imports A.  We
    focus only on *simple* cycles, where each node occurs only once in
    a cycle (so a figure-8 would be two cycles, one for the top circle
    and one for the bottom, not a single, more complicated cycle).
    The rule is that we report all cycles that include any files in
    files_to_lint.  (For reproducibility, we always print the cycle
    starting with the file in the cycle that comes first
    alphabetically.)

    It's very possible for a single file to have multiple circular
    imports.  We report them all.

    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')
    module_to_file = {
        ka_root.relpath(os.path.splitext(f)[0]).replace(os.sep, '.'): f
        for f in files_to_lint
    }

    saw_a_cycle = False
    for cycle in sorted(_find_all_cycles(module_to_file.keys())):
        saw_a_cycle = True
        # We report the line-number where cycle[0] imports cycle[1].
        f = module_to_file.get(cycle[0])
        if f is None:    # means this cycle does not include any files-to-lint
            continue
        import_lines = _get_import_lines(f)
        desired_import_line = next(il for il in import_lines
                                   if il.module == cycle[1])
        yield (f, desired_import_line.lineno,
               ('Resolve this import cycle (by making a late import): %s'
                % ' -> '.join(cycle)))

    if not saw_a_cycle:
        # This is only safe to do when there are no cycles already!
        for error in _lint_unnecessary_late_imports(files_to_lint):
            yield error


def _lint_unnecessary_late_imports(files_to_lint):
    """Report on all late imports that could safely be top-level.

    We make an import "late" -- that is, inside a function rather than
    at the top level -- when it's needed to avoid circular imports.
    However, sometimes a refactor makes it so an import doesn't need to
    be late anymore.  That's hard to tell by inspection, so this linter
    does it for you!

    Conceptually, this is a standalone linter, so I wrote it like that.
    However, it doesn't deal well with cycles so we only want to run it
    when there are no cycles.  Thus, we run it at the end of the
    cycle-checking linter, and then only if there are no cycles.
    """
    files_to_lint = lintutil.filter(files_to_lint, suffix='.py')

    # Files we shouldn't check for late imports for some reason.
    # Can end with `.` to match all modules starting with this prefix.
    MODULE_BLACKLIST = frozenset([
        # Is imported first, must do minimal work
        'appengine_config',
        # Minimize deps so new code can import it without fear.
        'users.current_user',
        # Minimize deps to keep `make tesc` output small.
        'testutil.gae_model',
        'testutil.mapreduce_stub',
        # Does a bunch of importing after fixing up sys.path
        'tools.appengine_tool_setup',
        'tools.devservercontext',
        'tools.devshell',
        # TODO(csilvers): remove this and move the babel routines to their
        # own file instead.
        'shared_jinja',
        # Does importing after modifying modules.
        'pickle_util_test',
        # Has its own style rule stating late imports are preferred
        'kake.',
    ])

    # Imports that are allowed to be late for some reason.
    LATE_IMPORT_BLACKLIST = frozenset([
        # Can only import once we've verified we're not running in prod
        'sandbox_util',
        'mock',
        'kake.server_client',
        'kake.make',
    ])

    for f in files_to_lint:
        module = ka_root.relpath(os.path.splitext(f)[0]).replace(os.sep, '.')
        # Some files are expected to have late imports.
        if (module in MODULE_BLACKLIST or
                module.startswith(
                    tuple(m for m in MODULE_BLACKLIST if m.endswith('.')))):
            continue

        for late_import in _get_late_imports(module):
            # Some modules can *only* be late-imported,
            if late_import in LATE_IMPORT_BLACKLIST:
                continue

            # If late_import transitively imports us, then it's not safe
            # to move it to the top level: that would introduce a cycle.
            if module in _calculate_transitive_imports(late_import):
                continue

            # If a module is marked `@UnusedImport` or `@Nolint`, then
            # it's being imported for its side effects, and we don't
            # want to move it to the top level.
            import_lines = _get_import_lines(f)
            late_import_line = next(il for il in import_lines
                                    if (il.module == late_import and
                                        not il.is_toplevel))
            contents = lintutil.file_contents(f)
            lines = contents.splitlines(True)
            if ('@UnusedImport' in lines[late_import_line.lineno - 1] or
                '@Nolint' in lines[late_import_line.lineno - 1]):
                continue

            # If we get here, it's safe to move this import to the top level!
            yield (f, late_import_line.lineno,
                   "Make this a top-level import: it doesn't cause cycles")

            # For the rest of our analysis, assume that `module` has
            # moved the import of `late_import` to the top level.
            # TODO(csilvers): figure out the "best" edge to add, rather
            # than just doing first come first served.
            _add_edge(module, late_import)
