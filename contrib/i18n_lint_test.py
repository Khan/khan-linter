# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E265
from __future__ import absolute_import

import json
import os
import shutil
import subprocess
import sys
import tempfile

import mock
from shared import ka_root
from shared.testutil import lintutil
from shared.testutil import testsize

from intl import i18n_lint
import kake.make


@testsize.tiny
class LintMissingSafeInJinaj2Test(lintutil.LintTest):
    def _lint(self, html):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('templates', 'd.html')
        self.set_file_contents(path, html)
        return i18n_lint.lint_missing_safe_in_jinja2([path])

    def test_no_safe_needed(self):
        self.assert_no_error(r'Hi {{ _("partner") }}!')

    def test_safe_needed(self):
        self.assert_error(r'Hi {{ _("<b>partner</b>") }}!')
        self.assert_error(r'Hi {{ _("partner & other partner") }}!')

    def test_safe_needed_single_quotes(self):
        self.assert_error(r"Hi {{ _('<b>partner</b>') }}!")

    def test_safe_provided(self):
        self.assert_no_error(r'Hi {{ _("<b>partner</b>"|safe) }}!')

    def test_safe_after_other_modifiers(self):
        self.assert_no_error(r'Hi {{ _("<b>partner</b>"|capitalize|safe) }}!')

    def test_safe_in_the_wrong_place(self):
        self.assert_error(r'Hi {{ _("<b>partner</b>")|safe }}!')
        self.assert_error(r'Hi {{ _("<b>partner</b>") }}! {{unrelated|safe}}')

    def test_internal_quotes(self):
        self.assert_error(r'Hi {{ _("\"jo\" <b>partner</b>") }}!')
        self.assert_error(r'Hi {{ _("<b>partner</b> \"jo\"") }}!')
        self.assert_error(r"Hi {{ _('<b>partner</b> \'jo\'') }}!")
        self.assert_no_error(r'Hi {{ _("\"jo\" partner") }}!')
        self.assert_no_error(r'Hi {{ _("partner \"jo\"") }}!')

    def test_arguments(self):
        self.assert_error(r'Hi {{ _("<b>%(partner)s</b>", partner="foo") }}!')

    def test_safe_arguments(self):
        self.assert_no_error(r'Hi {{ _("%(p)s", p="partner") }}!')

    def test_unsafe_arguments(self):
        self.assert_error(r'Hi {{ _("%(p)s", p="<b>partner</b>") }}!')

    def test_safe_provided_arguments(self):
        self.assert_no_error(r'Hi {{ _("%(p)s", p="<b>partner</b>"|safe) }}!')
        self.assert_no_error(r'Hi {{ _("%(p)s", p="<b>part</b>"|nr|safe) }}!')

    def test_unsafe_i18n_arguments(self):
        self.assert_error(r'Hi {{ capitalize(_("<b>partner</b>")) }}!')
        self.assert_error(r'Hi {{ capitalize(2, _("<b>partner</b>")) }}!')
        self.assert_error(r'Hi {{ capitalize(_("<b>partner</b>", 2)) }}!')
        self.assert_error(r'Hi {{ capitalize(2, _("<b>partner</b>", 2)) }}!')

    def test_ngettext_no_safe_needed(self):
        self.assert_no_error(r'Hi {{ ngettext("partner", "partners", p) }}!')

    def test_ngettext_safe_needed(self):
        self.assert_error(r'Hi {{ ngettext("<b>partner</b>",'
                          r'               "partners", p) }}!')
        self.assert_error(r'Hi {{ ngettext("partner",'
                          r'               "<b>partners</b>", p) }}!')
        self.assert_error(r'Hi {{ ngettext("<b>partner</b>",'
                          r'               "<b>partners</b>", p) }}!',
                          count=2)

    def test_nolint(self):
        self.assert_no_error(r'Hi {{ ngettext("<b>partner</b>",'
                             r'"partners", p) }}! {# @Nolint #}')
        self.assert_no_error(r'Hi {{ _("<b>foo</b> %(bar)s",   {# @Nolint #}\n'
                             r'        bar="monkey") }}')


@testsize.tiny
class LintNoWrongI18nMarkupInJina2Test(lintutil.LintTest):
    def _lint(self, html):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('templates', 'd.html')
        self.set_file_contents(path, html)
        return i18n_lint.lint_no_wrong_i18n_markup_in_jinja2([path])

    def test_no_dollar_sign(self):
        # We need to use {{ _js("..")}} instead
        self.assert_error(r'<script>var test = i18n._("bad");</script>')

    def test_nolint(self):
        self.assert_no_error(r'<script>var test = i18n._("bad");</script> '
                             r'{# @Nolint #}')


@testsize.tiny
class LintI18NDoNotTranslate(lintutil.LintTest):
    def _lint(self, html):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('templates', 'd.html')
        self.set_file_contents(path, html)
        return i18n_lint.lint_non_literal_i18n_do_not_translate([path])

    def test_ok_use(self):
        self.assert_no_error(r'Hi {{ i18n_do_not_translate("partner") }}!')
        self.assert_no_error(r"Hi {{ i18n_do_not_translate('partner') }}!")

    def test_var(self):
        self.assert_error(r'Hi {{ i18n_do_not_translate(func("partner")) }}!')
        self.assert_error(r'Hi {{ i18n_do_not_translate(func("a") +'
                          r'func("b") + "asdf") }}!')
        self.assert_error(r'Hi {{ i18n_do_not_translate(func(nested(d))) }}!')

    def test_nolint(self):
        self.assert_no_error(r'Hi {{ i18n_do_not_translate(func("part")) }}'
                             r'!  {# @Nolint #}')
        self.assert_no_error(r'Hi {{ i18n_do_not_translate(func("part"))'
                             r'  {# @Nolint #}\n) }}')


@testsize.tiny
class LintNonLiteralI18NForPythonTest(lintutil.LintTest):
    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('foo.py')
        self.set_file_contents(path, python_contents)
        return i18n_lint.lint_non_literal_i18n_in_python([path])

    def test_ok_use(self):
        self.assert_no_error('def foo():\n  i18n._("Literal text")')
        self.assert_no_error('def foo():\n  i18n.gettext("Literal text")')
        self.assert_no_error(
            'def foo():\n  i18n.cached_gettext("Literal text")')
        self.assert_no_error('def foo():\n  i18n.ngettext("Lit", "text", 4)')
        self.assert_no_error(
            'def foo():\n  i18n.cached_ngettext("Lit", "text", 4)')

    def test_var(self):
        self.assert_error('def foo():\n  i18n._(literal_text)')
        self.assert_error('def foo():\n  i18n.gettext(literal_text)')
        self.assert_error('def foo():\n  i18n.cached_gettext(literal_text)')
        # TODO(csilvers): test second arg of ngettext as well.
        #self.assert_error('def foo():\n  i18n.ngettext("Lit", text, 4)')
        self.assert_error('def foo():\n  i18n.ngettext(lit, "text", 4)')
        self.assert_error('def foo():\n  i18n.cached_ngettext(lit, "text", 4)')
        self.assert_error('def foo():\n  i18n.ngettext(lit, text, 4)')
        self.assert_error('def foo():\n  i18n.cached_ngettext(lit, text, 4)')

    def test_string_concat(self):
        self.assert_no_error('def foo():\n  i18n._("Literal" "text")')
        self.assert_no_error('def foo():\n  i18n._("Literal"\n"text")')
        self.assert_no_error('def foo():\n  i18n._("Literal" + "text")')
        self.assert_no_error('def foo():\n  i18n._("Literal"+\n   "text")')
        self.assert_error('def foo():\n  i18n._("Literal" + text)')

    def test_string_interpolation(self):
        self.assert_no_error('def foo():\n  i18n._("%(l)s text", l=literal)')

    def test_bad_string_interpolation(self):
        self.assert_error('def foo():\n  i18n._("%s text" % literal)')
        self.assert_error('def foo():\n  i18n.mark_for_translation('
                          '   "%s text" % literal)')

    def test_quote_style(self):
        self.assert_no_error('def foo():\n  i18n._("literal text")')
        self.assert_no_error("def foo():\n  i18n._('literal text')")
        self.assert_no_error('def foo():\n  i18n._("""literal text""")')
        self.assert_no_error("def foo():\n  i18n._('''literal text''')")
        self.assert_no_error('def foo():\n  i18n._("""literal\ntext""")')

    def test_non_function_calls(self):
        self.assert_no_error('def foo():\n  (x, _, y) = fn()')
        self.assert_no_error('from i18n import _')

    def test_nolint(self):
        self.assert_no_error('def foo():\n  i18n._(literal_text)  # @Nolint')
        self.assert_no_error('def foo():\n  i18n._(   # @Nolint\n'
                             '   literal_text)')
        self.assert_no_error('def foo():\n  i18n._(\n'
                             '   literal_text)   # @Nolint\n')
        self.assert_no_error('def foo():\n  i18n._(\n'
                             '   literal_text)   # @Nolint')


@testsize.tiny
class LintNonLiteralI18NForJavascriptTest(lintutil.LintTest):
    def _lint(self, js_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('foo.js')
        self.set_file_contents(path, js_contents)
        return i18n_lint.lint_non_literal_i18n_in_javascript([path])

    def test_ok_use(self):
        self.assert_no_error('var a = i18n._("Literal text")')
        self.assert_no_error('var a = i18n.ngettext("Lit", "text", 4)')

    def test_var(self):
        self.assert_error('var a = i18n._(literal_text)')
        self.assert_error('var a = i18n.ngettext("Lit", text, 4)')
        self.assert_error('var a = i18n.ngettext(lit, "text", 4)')
        self.assert_error('var a = i18n.ngettext(lit, text, 4)')

    def test_string_concat(self):
        self.assert_no_error('var a = i18n._("Literal" + "text")')
        self.assert_no_error('var a = i18n._("Literal"+\n   "text")')
        self.assert_no_error('var a = i18n._("Literal" + \'text\')')
        self.assert_no_error('var a = i18n._(\'Literal\'+\n   "text")')
        self.assert_error('var a = i18n._("Literal" + text)')

    def test_string_interpolation(self):
        self.assert_no_error('var a = i18n._("%(l)s text", l=literal)')

    def test_quote_style(self):
        self.assert_no_error(r'var a = i18n._("literal \"text\"")')
        self.assert_no_error(r"var a = i18n._('literal \'text\'')")
        self.assert_no_error(r"var a = i18n._(`literal \`text\``)")

    def test_template_strings(self):
        self.assert_no_error("var a = i18n._(`Simple case`)")
        self.assert_no_error("var a = i18n._(`An $\{example}`)")
        self.assert_no_error("var a = i18n._(`An \${example}`)")
        self.assert_error("var a = i18n._(`An ${example}`)")
        self.assert_no_error("var a = i18n._(`An %{example}s`, {example: 4})")

    def test_nolint(self):
        self.assert_no_error('var a = i18n._(literal_text)  # @Nolint')
        self.assert_no_error('var a = i18n._(   # @Nolint\n'
                             '   literal_text)')
        self.assert_no_error('var a = i18n._(\n'
                             '   literal_text)   # @Nolint\n')
        self.assert_no_error('var a = i18n._(\n'
                             '   literal_text)   # @Nolint')


@testsize.tiny
class LintTemplatesAreTranslatedJinja2Test(lintutil.LintTest):
    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error() call this."""
        path = ka_root.join('templates', 'foo.html')
        self.set_file_contents(path, python_contents)
        return i18n_lint.lint_templates_are_translated([path])

    def test_simple_lint(self):
        self.assert_error('This is a jinja2 template')
        self.assert_no_error('<a id="This is a jinja2 template">{{var}}</a>')

    def test_already_marked_up(self):
        self.assert_no_error('{{ _("This is a jinja2 template") }}')
        self.assert_no_error('{{ i18n_do_not_translate('
                             '     "This is a jinja2 template") }}')

    def test_parse_error(self):
        self.assert_error('{{ _("This is a jinja2 template")')


@testsize.tiny
class LintTemplatesAreTranslatedHandlebarsTest(lintutil.LintTest):
    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error() call this."""
        path = ka_root.join('foo.handlebars')
        self.set_file_contents(path, python_contents)
        return i18n_lint.lint_templates_are_translated([path])

    def test_simple_lint(self):
        self.assert_error('This is a hbars template')
        self.assert_no_error('<a id="This is a hbars template">{{var}}</a>')

    def test_already_marked_up(self):
        self.assert_no_error('{{#_}}This is a hbars template{{/_}}')
        self.assert_no_error('{{#i18nDoNotTranslate}}This is a hbars template'
                             '{{/i18nDoNotTranslate}}')

    def test_parse_error(self):
        self.assert_error('{{#_}}This is a handlebars template')


@testsize.tiny
class LintTemplatesAreTranslatedWhitelistTest(lintutil.LintTest):
    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error() call this."""
        path = ka_root.join('templates', 'intl', 'foo.html')
        self.set_file_contents(path, python_contents)
        return i18n_lint.lint_templates_are_translated([path])

    def test_ignored_due_to_whitelist(self):
        self.assert_no_error('This is a jinja2 template')


@testsize.tiny
class LintJsFilesAreTranslated(lintutil.LintTest):
    def _lint(self, js):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('javascript', 'd.js')
        self.set_file_contents(path, js)
        return i18n_lint.lint_js_files_are_translated([path])

    # React.DOM can still be called manually and shows up in some of our files,
    # though the compiler now only uses CreateElement tested below
    def test_non_translated_react_dom_node_contents_linted(self):
        js = 'React.DOM.strong({style:{color:"red"}}, "Test")'
        self.assert_error(js)

    def test_non_translated_non_alpha_characters_ok(self):
        js = 'React.DOM.strong({style:{color:"red"}}, " )")'
        self.assert_no_error(js)

    def test_translated_react_dom_node_contents_ok(self):
        js = 'React.DOM.strong({style:{color:"red"}}, i18n._(null, "Test"))'
        self.assert_no_error(js)

    def test_translated_react_with_utf8_ok(self):
        js = ('React.DOM.span({className: "discussion-meta-separator"}, '
              '"\xe2\x80\xa2")')
        self.assert_no_error(js)

    def test_non_translated_create_element_node_contents_linted(self):
        js = 'React.createElement("strong", {style:{color:"red"}}, "Test")'
        self.assert_error(js)

    def test_non_translated_create_element_node_middle_string_linted(self):
        js = ('React.createElement("div", {someProp: true}, <span />, '
              '"string", <span />)')
        self.assert_error(js)

    def test_non_translated_create_element_non_alpha_characters_ok(self):
        js = 'React.createElement("strong", {style:{color:"red"}}, " )")'
        self.assert_no_error(js)

    def test_translated_create_element_node_contents_ok(self):
        js = ('React.createElement("strong", {style:{color:"red"}},'
              'i18n._(null, "Test"))')
        self.assert_no_error(js)

    def test_translated_create_element_node_with_utf8_ok(self):
        js = ('React.createElement("div", {someProp: true}, <span />, '
              '"\xe2\x80\xa2", <span />)')
        self.assert_no_error(js)

    def test_comments_outside_of_curly_braces_linted(self):
        # TODO(csilvers): this comment was originally "// @Nolint".
        # Should we still see an error in that case?  Probably.
        js = 'React.createElement("div", {}, " // foo", i18n._("text"));'
        self.assert_error(js)

    def test_string_in_boolean_not_translated_ok(self):
        js = ('React.createElement("div", {}, this.state.status === "new" && '
              ' i18n._("newbies only text"));')
        self.assert_no_error(js)

    def test_untranslated_string_in_remainder_not_ok(self):
        js = ('React.createElement("div", {}, this.state.status === "new" && '
              ' "newbies only text");')
        self.assert_error(js)

    def test_string_in_ternary_linted(self):
        js = 'React.createElement("div", {}, doIt ? "yes" : i18n._("no"))'
        self.assert_error(js)

    def test_non_translated_text_argument_linted(self):
        msg = '''
var MasteredLabel = React.createClass({displayName: 'MasteredLabel',
    render: function() {
        var fontSize = 16;
        return this.transferPropsTo(
          Text({font: ("normal " + fontSize + "px 'Proxima Nova', sans-serif"),
                  fill: skillColors["mastery3"],
                  alignment: "center",
                  y: this.props.y - fontSize / 2},
                "mastered" + " skill"
          ));
    }
});
'''
        self.assert_error(msg)

    def test_translated_text_argument_ok(self):
        msg = '''
var MasteredLabel = React.createClass({displayName: 'MasteredLabel',
    render: function() {
        var fontSize = 16;
        return this.transferPropsTo(
          Text({font: ("normal " + fontSize + "px 'Proxima Nova', sans-serif"),
                  fill: skillColors["mastery3"],
                  alignment: "center",
                  y: this.props.y - fontSize / 2},
                $_(null, "mastered")
          ));
    }
});
'''
        self.assert_no_error(msg)

    @testsize.small
    def test_actual_react_code(self):
        contents = """\
import React, {Component} from "react";
export class Dashboard extends Component {
    render() {
        return <div data-test-id="coach-dashboard">Should translate!</div>;
    }
};
        """
        kake.make.build('genfiles/node_modules/babel-core/package.json')
        tmpdir = os.path.realpath(
            tempfile.mkdtemp(prefix=(self.__class__.__name__ + '.')))
        try:
            # We make our tmpdir look like genfiles.
            for f in os.listdir(ka_root.join('genfiles')):
                os.symlink(ka_root.join('genfiles', f),
                           os.path.join(tmpdir, f))
            fname = ka_root.join(tmpdir, 'bad.jsx')
            with open(fname, 'w') as f:
                f.write(contents)

            p = subprocess.Popen(
                ['node', ka_root.join('kake', 'compile_js.js')],
                stdin=subprocess.PIPE,
                cwd=ka_root.root)
            p.communicate(input=json.dumps([[fname, fname + '.js']]))
            self.assertEqual(0, p.returncode)

            with open(fname + '.js') as f:
                compiled_jsx = f.read()

            self.assert_error(compiled_jsx)
        finally:
            shutil.rmtree(tmpdir)


@testsize.tiny
class LintUsingGettextAtImportTime(lintutil.LintTest):
    def setUp(self):
        super(LintUsingGettextAtImportTime, self).setUp()

        self.tmpdir = os.path.realpath(
            tempfile.mkdtemp(prefix=(self.__class__.__name__ + '.')))
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir))

        patcher = mock.patch('sys.path', sys.path[:])
        self.addCleanup(patcher.stop)
        patcher.start()
        sys.path.append(self.tmpdir)

        patcher = mock.patch('shared.ka_root.root', self.tmpdir)
        self.addCleanup(patcher.stop)
        patcher.start()

    def _lint(self, python_contents):
        """Superclass's assert_error() and assert_no_error call this."""
        path = ka_root.join('using_gettext_at_import_time_file.py')
        self.set_file_contents(path, python_contents)
        # We also actually have to write the file to make it importable.
        with open(os.path.join(self.tmpdir, os.path.basename(path)), 'w') as f:
            print >>f, python_contents

        with mock.patch('shared.ka_root.root', self.tmpdir):
            return i18n_lint.lint_not_using_gettext_at_import_time([path])

    def test_sanity(self):
        self.assert_no_error('a = 4')

    def test_global(self):
        self.assert_error('import intl.i18n; a = intl.i18n._("hello")')

    def test_class_variable(self):
        self.assert_error('import intl.i18n\n'
                          'class Foo(object):\n'
                          '   a = intl.i18n._("hello")')

    def test_function(self):
        self.assert_no_error('import intl.i18n\n'
                             'def foo():\n'
                             '   a = intl.i18n._("hello")')

    def test_do_not_report_in_imported_file(self):
        with open(os.path.join(self.tmpdir, 'cause_lint_fail.py'), 'w') as f:
            print >>f, 'import intl.i18n'
            print >>f, 'a = intl.i18n._("hello")'

        self.assert_no_error('import cause_lint_fail\n'
                             'import intl.i18n\n'   # bypass lint shortcut
                             'a = 4')
