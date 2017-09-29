from __future__ import absolute_import

import mock

import import_lint
from shared import ka_root
import shared.testutil.lintutil


class TestBase(shared.testutil.lintutil.LintTest):
    def setUp(self):
        super(TestBase, self).setUp()

    def set_file_contents(self, *args, **kwargs):
        import_lint._g_import_line_cache.clear()
        import_lint._first_party_package_cache.clear()
        import_lint._module_cache.clear()
        import_lint._direct_top_level_imports.clear()
        import_lint._direct_late_imports.clear()
        import_lint._transitive_top_level_imports.clear()
        return super(TestBase, self).set_file_contents(*args, **kwargs)


class GetImportLinesTest(TestBase):
    def _imports(self, content):
        self.set_file_contents(ka_root.join('content/test.py'), content)
        return import_lint._get_import_lines(ka_root.join('content/test.py'))

    def test_simple_import(self):
        actual = self._imports("import json\nimport api.internal")
        self.assertEqual(actual[0].filename, ka_root.join("content/test.py"))
        self.assertEqual(actual[0].lineno, 1)
        self.assertEqual(actual[0].is_toplevel, True)
        self.assertEqual(actual[0].module, "json")
        self.assertEqual(actual[0].name, "json")
        self.assertEqual(actual[0].level, 0)
        self.assertEqual(actual[0].has_comma, False)
        self.assertFalse(actual[0].has_from, False)
        self.assertFalse(actual[0].has_as, False)

        self.assertEqual(actual[1].filename, ka_root.join("content/test.py"))
        self.assertEqual(actual[1].lineno, 2)
        self.assertEqual(actual[1].is_toplevel, True)
        self.assertEqual(actual[1].module, "api.internal")
        self.assertEqual(actual[1].name, "api.internal")
        self.assertEqual(actual[0].level, 0)
        self.assertEqual(actual[0].has_comma, False)
        self.assertFalse(actual[0].has_from, False)
        self.assertFalse(actual[0].has_as, False)

    def test_relative_imports(self):
        actual = self._imports("from . import frozen_model\n"
                               "from .articles import frozen_article\n"
                               "from .. import import_lint\n"
                               "from ..emails import send")
        self.assertEqual(actual[0].module, "content.frozen_model")
        self.assertEqual(actual[1].module, "content.articles.frozen_article")
        self.assertEqual(actual[2].module, "import_lint")
        self.assertEqual(actual[3].module, "emails.send")
        self.assertEqual(actual[0].level, 1)
        self.assertEqual(actual[1].level, 1)
        self.assertEqual(actual[2].level, 2)
        self.assertEqual(actual[3].level, 2)

    def test_from(self):
        actual = self._imports("from api.internal import test")
        self.assertEqual(actual[0].module, "api.internal.test")
        self.assertEqual(actual[0].name, "test")
        self.assertEqual(actual[0].level, 0)
        self.assertEqual(actual[0].has_comma, False)
        self.assertEqual(actual[0].has_from, True)
        self.assertEqual(actual[0].has_as, False)

    def test_star(self):
        actual = self._imports("from api.internal import *")
        self.assertEqual(actual[0].module, "api.internal.*")
        self.assertEqual(actual[0].name, "*")
        self.assertEqual(actual[0].level, 0)
        self.assertEqual(actual[0].has_comma, False)
        self.assertEqual(actual[0].has_from, True)
        self.assertEqual(actual[0].has_as, False)

    def test_as(self):
        actual = self._imports("from api.internal import test as api_test\n"
                               "import json as json_for_test\n")
        self.assertEqual(actual[0].lineno, 1)
        self.assertEqual(actual[0].module, "api.internal.test")
        self.assertEqual(actual[0].name, "api_test")
        self.assertEqual(actual[0].has_comma, False)
        self.assertEqual(actual[0].has_from, True)
        self.assertEqual(actual[0].has_as, True)

        self.assertEqual(actual[1].lineno, 2)
        self.assertEqual(actual[1].module, "json")
        self.assertEqual(actual[1].name, "json_for_test")
        self.assertEqual(actual[1].has_comma, False)
        self.assertEqual(actual[1].has_from, False)
        self.assertEqual(actual[1].has_as, True)

    def test_parens(self):
        actual = self._imports("from api.internal import (\ntest as api2)\n"
                               "import  json\n")
        self.assertEqual(actual[0].lineno, 1)
        self.assertEqual(actual[0].module, "api.internal.test")
        self.assertEqual(actual[0].name, "api2")
        self.assertEqual(actual[0].has_comma, False)

        self.assertEqual(actual[1].lineno, 3)
        self.assertEqual(actual[1].module, "json")
        self.assertEqual(actual[1].name, "json")
        self.assertEqual(actual[1].has_comma, False)

    def test_comma(self):
        actual = self._imports("from api.internal import test, test2\n"
                               "import json, htmlson\n"
                               "from foo import bar as baz, qux as quux\n")
        self.assertTrue(actual[0].has_comma)
        self.assertTrue(actual[1].has_comma)
        self.assertTrue(actual[2].has_comma)

    def test_import_in_function(self):
        actual = self._imports("def foo():\n   import json\n")
        self.assertEqual(actual[0].lineno, 2)
        self.assertEqual(actual[0].is_toplevel, False)
        self.assertEqual(actual[0].module, "json")
        self.assertEqual(actual[0].name, "json")
        self.assertEqual(actual[0].has_comma, False)

    def test_import_in_try(self):
        actual = self._imports("try:\n   import json\nexcept ImportError:\n")
        self.assertEqual(actual[0].lineno, 2)
        self.assertEqual(actual[0].is_toplevel, True)
        self.assertEqual(actual[0].module, "json")
        self.assertEqual(actual[0].name, "json")
        self.assertEqual(actual[0].has_comma, False)

    def test_in_strings(self):
        actual = self._imports('s = """\\\n   import foo"""')
        self.assertEqual([], actual)

    def test_in_comments(self):
        actual = self._imports('# import foo first\ns = foo')
        self.assertEqual([], actual)

    def test_invalid_file(self):
        actual = self._imports('import')
        self.assertEqual([], actual)

    def test_missing_file(self):
        actual = import_lint._get_import_lines(ka_root.join('notafile.py'))
        self.assertEqual(None, actual)


class BackslashTest(TestBase):
    def _lint(self, contents):
        self.set_file_contents(ka_root.join('test.py'), contents)
        return import_lint.lint_no_backslashes([ka_root.join('test.py')])

    def test_no_backslash(self):
        self.assert_no_error('from json import myfunc')

    def test_backslash(self):
        self.assert_error('from json \\\n    import myfunc')


class AbsoluteImportTest(TestBase):
    def _lint(self, contents):
        self.set_file_contents(ka_root.join('test.py'), contents)
        return import_lint.lint_absolute_import([ka_root.join('test.py')])

    def test_ok(self):
        self.assert_no_error('"""\nfoo\n"""\n'
                             'from __future__ import absolute_import\n\n'
                             'import json\n')

    def test_bad(self):
        self.assert_error('"""\nfoo\n"""\n'
                          'import json\n')

    def test_no_import(self):
        self.assert_no_error('"""\nfoo\n"""\n'
                             'def foo():\n   pass\n')

    def test_indented_import(self):
        self.assert_error('"""\nfoo\n"""\n'
                          'def foo():\n   import json\n')


class CommaTest(TestBase):
    def _lint(self, contents):
        self.set_file_contents(ka_root.join('test.py'), contents)
        return import_lint.lint_comma([ka_root.join('test.py')])

    def test_ok(self):
        self.assert_no_error('import json')

    def test_bad(self):
        self.assert_error('import json, html')

    def test_as(self):
        self.assert_error('import json as json2, html as html2')

    def test_from(self):
        self.assert_error('from api import json, html')

    def test_from_and_as(self):
        self.assert_error('from api import json, html as html2')
        self.assert_error('from api import json as json2, html')

    def test_parens(self):
        self.assert_error('from foo import (json as json2, html as html2)')

    def test_newline(self):
        self.assert_error('from foo import (\njson as json2, html as html2)')


class PackageImportTest(TestBase):
    def setUp(self):
        super(PackageImportTest, self).setUp()
        files = {
            ka_root.join('content/__init__.py'),
            ka_root.join('content/frozen_model.py'),
            ka_root.join('content/videos/__init__.py'),
            ka_root.join('content/videos/frozen_video.py'),
            ka_root.join('content/articles/__init__.py'),
            ka_root.join('content/articles/frozen_article.py'),
            ka_root.join('content/articles/testdata/__init__.py'),
            ka_root.join('content/articles/testdata/mytest.py'),
            ka_root.join('emails/__init__.py'),
            ka_root.join('emails/send.py'),
            ka_root.join('emails/templates/__init__.py'),
            ka_root.join('third_party/boto/__init__.py'),
            ka_root.join('third_party/boto/auth.py'),
            ka_root.join('third_party/vendored/third_party/idna/__init__.py'),
            ka_root.join('third_party/vendored/third_party/idna/codec.py'),
            ka_root.join('import_lint.py'),
            '/usr/lib/python/lxml/__init__.py',
            '/usr/lib/python/lxml/parse.py',
        }
        patcher = mock.patch('os.path.exists', lambda f: f in files)
        self.addCleanup(patcher.stop)
        patcher.start()

    def _lint(self, contents):
        fname = ka_root.join("content", "test.py")
        self.set_file_contents(fname, contents)
        return import_lint.lint_package_imports([fname])

    def test_ok(self):
        self.assert_no_error("import import_lint\n"
                             "import content.videos.frozen_video\n")

    def test_toplevel_bad(self):
        self.assert_error("import content")

    def test_nested_bad(self):
        self.assert_error("import content.articles")

    def test_ignore_third_party(self):
        self.assert_no_error("import third_party.boto\n")

    def test_ignore_future(self):
        self.assert_no_error("from __future__ import print_statement")

    def test_ignore_system(self):
        self.assert_no_error("import lxml")

    def test_relative_imports(self):
        self.assert_no_error("from . import frozen_model")
        self.assert_no_error("from .articles import frozen_article")
        self.assert_no_error("from .. import import_lint")
        self.assert_no_error("from ..emails import send")
        self.assert_error("from . import articles")
        self.assert_error("from .articles import testdata")
        self.assert_error("from .. import emails")
        self.assert_error("from ..emails import templates")

    def test_relative_imports_into_third_party(self):
        self.assert_no_error("from ..third_party import boto")
        self.assert_no_error("from ..third_party import idna")


class RedundantImportTest(TestBase):
    def _lint(self, contents):
        self.set_file_contents(ka_root.join('test.py'), contents)
        return import_lint.lint_redundant_imports([ka_root.join('test.py')])

    def test_no_errors(self):
        self.assert_no_error("import foo.bar\n"
                             "import foo.barr\n"
                             "from foo import baz")

    def test_duplicate_import(self):
        self.assert_error("import foo.bar\n"
                          "import foo.barr\n"
                          "import foo.bar")

    def test_duplicate_with_second_one_indented(self):
        self.assert_error("import foo.bar\n"
                          "def foo():\n"
                          "   import foo.bar\n")

    def test_duplicate_with_both_in_functions(self):
        self.assert_no_error("def foo():\n"
                             "   import foo.bar\n\n"
                             "def bar():\n"
                             "   import foo.bar\n")

    def test_duplicate_in_exception(self):
        self.assert_no_error("try:\n"
                             "   import foo.bar\n"
                             "except ImportError:\n"
                             "   munge_path()\n"
                             "   import foo.bar\n")

    def test_from(self):
        self.assert_error("import foo.bar\n"
                          "import foo.barr\n"
                          "from foo import bar")

    def test_as(self):
        self.assert_error("import foo.bar\n"
                          "import foo.barr\n"
                          "import foo.bar as foo_bar")


class SymbolImportTest(TestBase):
    def setUp(self):
        super(SymbolImportTest, self).setUp()

        files = {
            ka_root.join('content/__init__.py'),
            ka_root.join('content/cool_module.so'),
            ka_root.join('content/frozen_model.py'),
            ka_root.join('content/videos/__init__.py'),
            ka_root.join('content/videos/frozen_video.py'),
            ka_root.join('content/articles/__init__.py'),
            ka_root.join('content/articles/frozen_article.py'),
            ka_root.join('content/articles/testdata/__init__.py'),
            ka_root.join('content/articles/testdata/mytest.py'),
            ka_root.join('emails/__init__.py'),
            ka_root.join('emails/send.py'),
            ka_root.join('emails/templates/__init__.py'),
            ka_root.join('third_party/__init__.py'),
            ka_root.join('third_party/boto/__init__.py'),
            ka_root.join('third_party/boto/auth.py'),
            ka_root.join('third_party/vendored/__init__.py'),
            ka_root.join('third_party/vendored/third_party/__init__.py'),
            ka_root.join('third_party/vendored/third_party/idna/__init__.py'),
            ka_root.join('third_party/vendored/third_party/idna/codec.py'),
            ka_root.join('import_lint.py'),
            '/usr/lib/python/lxml/__init__.py',
            '/usr/lib/python/lxml/parser.py',
        }
        patcher = mock.patch('os.path.exists', lambda f: f in files)
        self.addCleanup(patcher.stop)
        patcher.start()

        patcher = mock.patch('os.listdir', lambda d: ['idna', 'urllib3'])
        self.addCleanup(patcher.stop)
        patcher.start()

        patcher = mock.patch(
            'os.stat',
            lambda f: mock.Mock(st_size=(0 if '__init__.py' in f else 1000)))
        self.addCleanup(patcher.stop)
        patcher.start()

        patcher = mock.patch('sys.path', [ka_root.root,
                                          ka_root.join('third_party/vendored'),
                                          '/usr/lib/python'])
        self.addCleanup(patcher.stop)
        patcher.start()

    def _lint(self, contents):
        fname = ka_root.join("content", "test.py")
        self.set_file_contents(fname, contents)
        return import_lint.lint_symbol_imports([fname])

    def test_importing_modules(self):
        self.assert_no_error('from content.videos import frozen_video')
        self.assert_no_error('from third_party.boto import auth')
        self.assert_no_error('from third_party.idna import codec')
        self.assert_no_error('from lxml import parser')

    def test_importing_packages(self):
        self.assert_no_error('from content import videos')
        self.assert_no_error('from third_party import boto')
        self.assert_no_error('from third_party import idna')
        self.assert_no_error('import lxml')

    def test_non_existent_package_or_module(self):
        self.assert_no_error('from notadir import lexer')
        self.assert_no_error("from ..emails.templates import new_user")

    def test_relative_imports(self):
        self.assert_no_error("from . import frozen_model")
        self.assert_no_error("from .articles import frozen_article")
        self.assert_no_error("from .. import import_lint")
        self.assert_no_error("from ..emails import send")
        self.assert_error("from .articles.frozen_article import Article")
        self.assert_error("from ..import_lint import LintBase")
        self.assert_error("from ..emails.send import Sender")

    def test_ignores_non_from(self):
        self.assert_no_error('import content.notathing')
        self.assert_no_error('import third_party.boto.notathing as boto')

    def test_first_party(self):
        self.assert_error('from content.videos.frozen_video import Video')

    def test_star(self):
        self.assert_error('from content.videos.frozen_video import *')

    def test_third_party(self):
        self.assert_error('from third_party.boto.auth import Parser')
        self.assert_error('from third_party.idna.codec import sha256')

    def test_system(self):
        self.assert_error('from lxml.parser import EParser')

    def test_shared_library(self):
        self.assert_error('from content.cool_module import MySymbol')
        self.assert_no_error('from content import cool_module')

    def test_builtin(self):
        self.assert_error('from sys import path')


class UnusedImportTest(TestBase):
    def _lint(self, contents):
        self.set_file_contents(ka_root.join('test.py'), contents)
        for (file, line, msg) in import_lint.lint_unused_and_missing_imports(
                [ka_root.join('test.py')]):
            # We ignore missing imports; we have a different test for that.
            if msg.startswith('Unused import:'):
                yield (file, line, msg)

    def test_no_errors_on_use(self):
        self.assert_no_error("import foo\nimport api.bar\n"
                             "foo.var = True\napi.bar.var = True")

    def test_error_on_no_use(self):
        self.assert_error("import foo.ball\nimport api.bar\n"
                          "foo.ball.var = True")

    def test_adjacent_uses(self):
        self.assert_no_error("import foo.ball\nimport api.bar\n"
                             "foo.ball\napi.bar\n")

    def test_package(self):
        self.assert_error("import foo.bar.bang\nfoo.bar.baz = 1")

    def test_multiple_errors(self):
        self.assert_error("import foo.ball\nimport api.bar", count=2)

    def test_from(self):
        self.assert_no_error("from api import json\nx = json.var")
        # This is not an error because pyflakes correctly finds it.
        self.assert_no_error("from api import json\nx = api.json.var")

    def test_as(self):
        self.assert_no_error("import api.json as json2\nx = json2.var")
        # This is not an error because pyflakes correctly finds it.
        self.assert_no_error("import api.json as json2\nx = api.json.var")

    def test_seeming_use(self):
        self.assert_error("import json.value\nx = self.json.value")

    def test_ignore_future(self):
        self.assert_no_error("from __future__ import print_statement")

    def test_multiline_use(self):
        self.assert_no_error("import api.bar\n"
                             "x = (api.\nbar.myvar)")
        self.assert_no_error("import api.bar\n"
                             "x = (api\n.bar.myvar)")

    def test_unused_import_decorator(self):
        self.assert_no_error("import api.bar   # @UnusedImport")

    def test_do_not_warn_when_pyflakes_will(self):
        # pyflakes correctly warns for these, so we don't have to.
        self.assert_no_error("import json")
        self.assert_no_error("from api.internal import json")
        self.assert_no_error("import api.internal.json as json")

    def test_importing_a_package(self):
        # TODO(csilvers): these should report that jinja2.ext is unused.
        self.assert_no_error("import jinja2\nimport jinja2.ext\n"
                             "jinja2.context = None")
        self.assert_no_error("import jinja2.ext\nimport jinja2\n"
                             "jinja2.context = None")
        self.assert_error("import jinja2.ext\n"
                          "jinja2.context = None")


class MissingImportTest(TestBase):
    def _lint(self, contents):
        self.set_file_contents(ka_root.join('test.py'), contents)
        for (file, line, msg) in import_lint.lint_unused_and_missing_imports(
                [ka_root.join('test.py')]):
            # We ignore unused imports; we have a different test for that.
            if msg.startswith('Missing import:'):
                yield (file, line, msg)

    def test_no_errors_on_definition(self):
        self.assert_no_error("import foo\nimport api.bar\n"
                             "foo.var = True\napi.bar.var = True")

    def test_error_on_no_definition(self):
        self.assert_error("import foo.ball\nimport api.bar\n"
                          "foo.bar.var = True")

    def test_adjacent_uses(self):
        self.assert_no_error("import foo.ball\nimport api.bar\n"
                             "foo.ball\napi.bar\n")

    def test_package(self):
        self.assert_error("import foo.bar.bang\nfoo.bar.baz = 1")

    def test_multiple_errors(self):
        self.assert_error("import foo.bar\nimport api.baz\n"
                          "foo.ball\napi.bar", count=2)

    def test_seeming_use(self):
        self.assert_no_error("import json.parse\nx = self.json.value")

    def test_multiline_use(self):
        self.assert_no_error("import api.bar\n"
                             "x = (api.\nbar.myvar)")
        self.assert_no_error("import api.bar\n"
                             "x = (api\n.bar.myvar)")
        self.assert_error("import api.bar\n"
                          "x = (api\n.baz.myvar)")
        self.assert_error("import api.bar\n"
                          "x = (api.\nbaz.myvar)")

    def test_importing_a_package(self):
        self.assert_no_error("import jinja2\nimport jinja2.ext\n"
                             "jinja2.context = None")
        self.assert_no_error("import jinja2.ext\nimport jinja2\n"
                             "jinja2.context = None")
        self.assert_error("import jinja2.ext\n"
                          "jinja2.context = None")


class CircuitFinderTest(TestBase):
    def test_simple(self):
        #          V4      V2
        #    +-<---o---<---o---<--+
        #    |             |      |
        # V0 o             ^      o V3
        #    |           V1|      |
        #    +------>------o--->--+
        #                 / \
        #                |   |
        #                +->-+
        adjacency_matrix = [[1], [1, 2, 3], [4], [2], [0]]
        actual = list(import_lint._CircuitFinder().run(adjacency_matrix))
        self.assertItemsEqual(
            [[0, 1, 2, 4, 0], [0, 1, 3, 2, 4, 0], [1, 1]],
            actual)


class CircularImportTest(TestBase):
    def _lint(self, contents_map):
        for (fname, imports) in contents_map.iteritems():
            import_lines = []
            for i in imports:
                if i.startswith(' '):    # indicates a late import
                    import_lines.append('def foo():\n   import %s' % i.strip())
                else:
                    import_lines.append('import %s' % i)
            self.set_file_contents(ka_root.join(fname),
                                   '\n'.join(import_lines))
        return import_lint.lint_circular_imports(
            [ka_root.join(fname) for fname in contents_map])

    def test_no_cycles(self):
        self.assert_no_error({'a.py': {'b', 'c'},
                              'b.py': {'c'},
                              'c.py': {}
                              })

    def test_simple_cycle(self):
        self.assert_error({'a.py': {'b'},
                           'b.py': {'c'},
                           'c.py': {'a'},
                           })

    def test_more_complex_cycle(self):
        self.assert_error({'a.py': {'b', 'c'},
                           'b.py': {'c', 'd'},
                           'c.py': {'d'},
                           'd.py': {'a'},
                           },
                          3)     # there are 3 cycles here!

    def test_multiple_cycles_again(self):
        self.assert_error({'a.py': {'b'},
                           'b.py': {'c'},
                           'c.py': {'d', 'e'},
                           'd.py': {'a'},
                           'e.py': {'a'},
                           },
                          2)     # there are 2 cycles here

    def test_self_cycle(self):
        self.assert_error({'a.py': {'a'}})

    def test_third_party(self):
        self.assert_no_error({'a.py': {'third_party.b'},
                              'third_party/b.py': {'whatevs'},
                              })

    def test_second_party(self):
        self.assert_no_error({'a.py': {'google.appengine.ext.db'},
                              })

    def test_path_to_module(self):
        self.assert_no_error({'a.py': {'b.c'},
                              'b/c.py': {},
                              })
        self.assert_error({'a.py': {'b.c'},
                           'b/c.py': {'a'},
                           })

    def test_ignore_late_imports(self):
        self.assert_no_error({'a.py': {'b'},
                              'b': {' a'},
                              })


class LateImportTest(TestBase):
    def _lint(self, contents_map):
        for (fname, imports) in contents_map.iteritems():
            import_lines = []
            for i in imports:
                if i.startswith(' '):    # indicates a late import
                    import_lines.append('def foo():\n   import %s' % i.strip())
                else:
                    import_lines.append('import %s' % i)
            self.set_file_contents(ka_root.join(fname),
                                   '\n'.join(import_lines))
        return import_lint._lint_unnecessary_late_imports(
            [ka_root.join(fname) for fname in contents_map])

    def test_simple(self):
        self.assert_error({'a.py': {' b'},
                           'b.py': {'c'},
                           })

    def test_system_import(self):
        self.assert_error({'a.py': {' subprocess'},
                           })

    def test_no_error(self):
        # No error because it's not safe to remove the late import.
        self.assert_no_error({'a.py': {' b'},
                              'b.py': {'a'},
                              })

    def test_longer_chain_no_error(self):
        self.assert_no_error({'a.py': {' b'},
                              'b.py': {'c'},
                              'c.py': {'a'},
                              })
        self.assert_no_error({'a.py': {'b'},
                              'b.py': {' c'},
                              'c.py': {'a'},
                              })

    def test_mutually_exclusive_errors(self):
        # We only suggest one of these, since making both of them
        # top-level would introduce a cycle.
        self.assert_error({'a.py': {' b'},
                           'b.py': {' c'},
                           'c.py': {'a'},
                           },
                          1)

    def test_complex_mutually_exclusive_errors(self):
        # Ideally we'd suggest making c and d top-level, but not b
        # (maybe?)  But as it is we suggest a's import of b (which
        # comes first in alphabetical order).
        self.assert_error({'a.py': {' b'},
                           'b.py': {' c', ' d'},
                           'c.py': {'a'},
                           'd.py': {'a'},
                           },
                          1)

    def test_unused_import(self):
        self.assert_no_error({'a.py': {' b  # @UnusedImport'}})

