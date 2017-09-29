# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E127
from __future__ import absolute_import

from shared import ka_root
from shared.testutil import lintutil
from shared.testutil import testsize

import jinja2_lint


@testsize.tiny
class LintNoJinja2MarkupInPythonTest(lintutil.LintTest):
    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('foo.py')
        self.set_file_contents(path, python_contents)
        return jinja2_lint.lint_no_jinja2_markup_in_python([path])

    def test_bad_use(self):
        self.assert_error('def foo():\n  return jinja2.Markup("foo")')

    def test_two_lines(self):
        self.assert_error('def foo():\n  return jinja2.Markup(\n   "foo")')
        self.assert_error('def foo():\n  return jinja2. \\\nMarkup("foo")')

    def test_ok_use(self):
        self.assert_no_error('def foo():\n  jinja2.Markup.escape("foo")')

    def test_import(self):
        self.assert_error('from jinja2 import Markup')
        self.assert_error('from jinja2 import escape, Markup, unescape')
        self.assert_error('from google.lib.jinja2 import Markup')

    def test_nolint(self):
        self.assert_no_error('from jinja2 import Markup   # @Nolint')
        self.assert_no_error('def foo():\n  return jinja2.Markup("foo")'
                             '  # @Nolint')
        self.assert_no_error('def foo():\n  return jinja2.Markup( # @Nolint\n'
                             '   "foo")')
        # The @Nolint directive has to be on the line with the word 'Markup'.
        self.assert_error('def foo():\n  return jinja2.Markup(\n'
                          '   "foo")    # @Nolint')


@testsize.tiny
class LintNoTemlpatetagsCallsInPythonTest(lintutil.LintTest):
    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('foo.py')
        self.set_file_contents(path, python_contents)
        return jinja2_lint.lint_no_templatetags_calls_in_python([path])

    def assert_error(self, python_contents, count=1):
        errors = super(LintNoTemlpatetagsCallsInPythonTest, self).assert_error(
            python_contents, count)
        # Make sure the error message matches the input.
        # This is a pretty loose test, but better than nothing.
        if count > 0:
            if 'templatetags' in python_contents:
                self.assertTrue(any('templatetags' in msg
                                    for (_, _, msg) in errors),
                                (python_contents, errors))
                if 'templatefilters' in python_contents:
                    self.assertTrue(any('templatefilters' in msg
                                        for (_, _, msg) in errors),
                                    (python_contents, errors))

    def _assert_no_error(self, python_contents):
        self.assert_error(python_contents, count=0)

    def test_bad_use(self):
        self.assert_error('import templatetags')
        self.assert_error('import templatetags\n')
        self.assert_error('import js_css_templates.templatefilters')
        self.assert_error('   import js_css_templates.templatefilters')

    def test_from(self):
        self.assert_error('from js_css_templates import templatefilters')
        self.assert_error('from templatefilters import slugify')
        self.assert_error('   from templatefilters import slugify')
        self.assert_error('from js_css_templates.templatetags import slugify')

    def test_ok_use(self):
        self.assert_no_error('importation of templatetags')

    def test_nolint(self):
        self.assert_no_error('import templatetags   # @Nolint')
        self.assert_no_error('from templatetags import slugify  # @Nolint')


class LintJavascriptInHtml(lintutil.LintTest):
    def _lint(self, html_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('templates', 'foo.html')
        self.set_file_contents(path, html_contents)
        return jinja2_lint.lint_javascript_in_html([path])

    def test_no_javascript(self):
        self.assert_no_error('<html>hello, world</html>\n')

    def test_empty_javascript(self):
        self.assert_no_error('<script src="foo.js"></script>\n')

    def test_fake_javascript(self):
        self.assert_no_error('<script type="text/plain">error</script>\n')

    def test_correct_javascript(self):
        self.assert_no_error(
            '<script>var a = 4;'
            'setTimeout(function(){}, a);</script>')

    def test_incorrect_javascript(self):
        self.assert_error('<script>a = 4;</script>')

    def test_es6_javascript(self):
        self.assert_error('<script>const a = 4;</script>')

    def test_incorrect_javascript_in_each_branch(self):
        self.assert_no_error(
            '<script>'
            '{% if x %}var a = 4;{% else %}var a = 5;{% endif %}'
            'setTimeout(function(){}, a);'
            '</script>')
        self.assert_error('<script>'
                          '{% if x %}var a = 4{% else %}var a = 5;{% endif %}'
                          'setTimeout(function(){}, a);'
                          '</script>')
        self.assert_error('<script>'
                          '{% if x %}var a = 4;{% else %}var a = 5{% endif %}'
                          'setTimeout(function(){}, a);'
                          '</script>')

    def test_correct_javascript_with_markup(self):
        self.assert_no_error('<script>var a = {{ _("A string") }};'
                             'setTimeout(function(){}, a);</script>')

    def test_malformed_html(self):
        self.assert_error('<script type=">a = 4;</script>')


class LintIIFEInHtmlJavascript(lintutil.LintTest):
    def _lint(self, html_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('templates', 'foo.html')
        self.set_file_contents(path, html_contents)
        return jinja2_lint.lint_iife_in_html_javascript([path])

    def test_no_javascript(self):
        self.assert_no_error('Hello world')

    def test_no_vars(self):
        self.assert_no_error('<script>document.write("Hello world")</script>')

    def test_has_iife(self):
        self.assert_no_error('<script>(function() {var x = 1;})();</script>')

    def test_weird_spacing_iife(self):
        self.assert_no_error('<script>(function () {var x = 1;})();</script>')

    def test_lacks_iife(self):
        self.assert_error('<script>var x = foo;</script>')

    def test_has_iife_with_whitespace(self):
        self.assert_no_error('<script>\n(function() {var x = 1;})();</script>')

    def test_has_iife_with_comments(self):
        self.assert_error('<script>\n'
                             '/* Who knows what this function does?\n'
                             ' * Not me.\n'
                             ' */\n'
                             '(function() { var x = some_function(); })();\n'
                             '</script>\n')
