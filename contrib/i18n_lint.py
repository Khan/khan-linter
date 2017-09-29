# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E124,E127,E129,E271
"""Linters that warn about common problems with i18n markup."""

from __future__ import absolute_import

import logging
import os
import re
import subprocess
import sys
import tokenize

from google.appengine.tools import appcfg
from shared import ka_root
from shared.testutil import lintutil
from third_party import i18nize_templates
from third_party.babel.messages import jslexer

import intl.data
import intl.english_only
import intl.locale
import kake.make
import modules_util


# This catches all the jinja2 function calls: it matches {{.*(.*}}
# TODO(csilvers): handle " and ' so we can have }}'s inside them.
_J2_FUNCTION_RE = re.compile(r'{{(}?[^}])*\((}?[^}])*}}')

# This catch i18n._() (or the obsolete $._()) being used inside of
# jinja2.  We should use {{ _js("..") }} when marking up text inside a
# <script/> tag in jinja2 instead.
_BAD_JS_MARKUP = re.compile(r'(?:i18n|\$)\._\(([^\)])')

# This captures a _() call when the input is a jinja2 function call.
# The string is in group(1) and any |-modifiers are in group(2).
# Any keyword arguments to _() are in group(3).
# TODO(csilvers): modify group(3) so nested parens or parens in "..."
# don't trip it up.  Nested parens is hardest, so I didn't bother.
_GETTEXT_RE = re.compile(r'\b(?:_|gettext)\('
                         r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
                         r'([^,)]*)([^)]*)',
                         re.DOTALL)

# This captures a bad i18n_do_not_translate() call that is not a literal string
# when the input is a jinja2 function call. The args to the
# i18n_do_not_translate() function are in group(1) and may contain any number
# of non-nested function calls. As this is just used for reporting and there
# is not a good way to do nested parens this is good enough.
_BAD_DO_NOT_TRANSLATE_RE = re.compile(r'\bi18n_do_not_translate\s*\(\s*('
                                      r'(?![\'"])'
                                      r'(?:[^\(\)]*(?:\([^\)]*\))*)*)\)',
                                      re.DOTALL)

# This captures a ngettext() call when the input is a jinja2 function call.
# The two string are in group(1) and group(3), and their |-modifiers (if
# any) are in group(2) and group(4).  ngettext keyword args are in group(5).
_NGETTEXT_RE = re.compile(r'\bngettext\('
                          r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
                          r'([^,)]*)'
                          r'\s*,\s*'
                          r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
                          r'([^,)]*)([^)]*)',
                          re.DOTALL)

# This captures string arguments in the kwargs.
# The string is in group(1) and any |-modifiers are in group(2).
_KWARG_RE = re.compile(r',\s*\w+\s*=\s*'
                       r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
                       r'([^,)]*)')


# These are the characters that require us to add |safe, because
# otherwise they'd be html-escaped.
_NEED_SAFE_RE = re.compile(r'[<>&]')


def _needs_safe(string, post_string):
    """True if 'string' has html chars in it, and post_string lacks |safe."""
    # String includes the leading and trailing "'s, which aren't part
    # of the string proper.
    assert string[0] in '"\'' and string[-1] in '"\'', string
    return _NEED_SAFE_RE.search(string[1:-1]) and '|safe' not in post_string


def lint_missing_safe_in_jinja2(files_to_lint):
    """Find instances where we translate html but don't mark it |safe.

    We html-escape the output of {{ _("...") }} in html templates, which
    is safe but can cause problems when the text is {{ _("<b>hi</b>") }}.
    In that case, the user needs to do {{ _("<b>hi</b>")|safe }}.

    We detect instances where the user does {{ _("...<..") }} in jinja2
    templates but lacks the |safe afterwards.  Unless that line is marked
    with {{# @Nolint #}}, we flag it as a lint error.

    Returns:
       List of triples: (filename, lineno, error message)
    """
    # Limit files-to-lint to html and txt files under templates/.
    files = lintutil.filter(files_to_lint,
                            prefix='templates/', suffix=('.html', '.txt'))

    for filename in files:
        contents = lintutil.file_contents(filename)
        for fn_match in _J2_FUNCTION_RE.finditer(contents):
            # Make sure there's no @Nolint anywhere around this function.
            newline = contents.find('\n', fn_match.end())
            newline = newline if newline > -1 else len(contents)
            if '@Nolint' in contents[fn_match.start():newline]:
                continue

            for m in _GETTEXT_RE.finditer(fn_match.group(0)):
                if _needs_safe(m.group(1), m.group(2)):
                    linenum = 1 + contents.count('\n', 0,
                                                 fn_match.start() + m.start(1))
                    yield (filename, linenum,
                           'Replace %s with _("..."|safe) to avoid escaping'
                           'the tag/attr inside the _().' % m.group(1))
                for km in _KWARG_RE.finditer(m.group(3)):
                    if _needs_safe(km.group(1), km.group(2)):
                        linenum = 1 + contents.count('\n', 0,
                                                     fn_match.start() +
                                                     m.start() + km.start(1))
                        yield (filename, linenum,
                               'Replace %s with _(..., foo="..."|safe) to '
                               'avoid escaping the tag/attr inside foo.'
                               % km.group(1))

            for m in _NGETTEXT_RE.finditer(fn_match.group(0)):
                if _needs_safe(m.group(1), m.group(2)):
                    linenum = 1 + contents.count('\n', 0,
                                                 fn_match.start() + m.start(1))
                    yield (filename, linenum,
                           'Replace %s with ngettext("..."|safe, ...) to '
                           'avoid escaping the tag/attr inside the _().'
                           % m.group(1))
                if _needs_safe(m.group(3), m.group(4)):
                    linenum = 1 + contents.count('\n', 0,
                                                 fn_match.start() + m.start(3))
                    yield (filename, linenum,
                           'Replace %s with ngettext(..., "..."|safe) to '
                           'avoid escaping the tag/attr inside the _().'
                           % m.group(3))
                for km in _KWARG_RE.finditer(m.group(5)):
                    if _needs_safe(km.group(1), km.group(2)):
                        linenum = 1 + contents.count('\n', 0,
                                                     fn_match.start() +
                                                     m.start() + km.start(1))
                        yield (filename, linenum,
                               'Replace %s with ngettext(..., foo="..."|safe)'
                               ' to avoid escaping the tag/attr inside foo.'
                               % km.group(1))


def lint_no_wrong_i18n_markup_in_jinja2(files_to_lint):
    """Find where we mark js within html with i18n._ instead of {{ _js()

    Returns:
       List of triples: (filename, lineno, error message)
    """
    files = lintutil.filter(files_to_lint, prefix='templates/', suffix='.html')
    for filename in files:
        contents = lintutil.file_contents(filename)
        for fn_match in _BAD_JS_MARKUP.finditer(contents):
            # Make sure there's no @Nolint anywhere around this function.
            newline = contents.find('\n', fn_match.end())
            newline = newline if newline > -1 else len(contents)
            if '@Nolint' in contents[fn_match.start():newline]:
                continue

            for m in _BAD_JS_MARKUP.finditer(fn_match.group(0)):
                linenum = 1 + contents.count('\n', 0,
                                             fn_match.start() + m.start(1))
                yield (filename, linenum,
                       'Do {{ _js("%s") }} instead of %s inside <script> '
                       'tags within jinja2.' % (m.group(1), m.group(0)))


def lint_non_literal_i18n_do_not_translate(files_to_lint):
    """Find where we mark html as not needing translation but its non-literal

    We require anything we mark with i18n_do_not_translate to be only a string
    literal. i18n_do_not_translate marks the string as "safe" (that is jinja2
    won't autoescape it) so we need to be extra careful we don't create a
    potential XSS attack vector if we end up marking some variable as
    safe.

    Unless that line is marked with {{# @Nolint #}}, we flag it as a lint
    error.

    Returns:
       List of triples: (filename, lineno, error message)
    """
    # Limit files-to-lint to files under templates/ that are html or txt.
    files = lintutil.filter(files_to_lint,
                            prefix='templates/', suffix=('.html', '.txt'))

    for filename in files:
        contents = lintutil.file_contents(filename)
        for fn_match in _J2_FUNCTION_RE.finditer(contents):
            # Make sure there's no @Nolint anywhere around this function.
            newline = contents.find('\n', fn_match.end())
            newline = newline if newline > -1 else len(contents)
            if '@Nolint' in contents[fn_match.start():newline]:
                continue

            for m in _BAD_DO_NOT_TRANSLATE_RE.finditer(fn_match.group(0)):
                linenum = 1 + contents.count('\n', 0,
                                             fn_match.start() + m.start(1))
                yield (filename, linenum,
                       '%s contains something that is not just a '
                       'literal string. Only literal strings can be '
                       'inside i18n_do_not_translate.' % m.group(1))


# State machine when lexing uses of i18n._ in source code.
# Keys are what token we're currently looking at, value is what tokens
# should come next.  Tokens can either be a type (tokenize.XXX) or a
# literal value.  Key of None indicates when to start parsing; value
# of None terminates a successful parse.  Newlines and comments are
# always elided when looking at tokens.
_START_TOKENS = ('_', 'gettext', 'ngettext', 'cached_gettext',
                 'cached_ngettext', 'mark_for_translation')
_GETTEXT_STATE_MACHINE = {
    None: _START_TOKENS,
    '_': ('(',),
    'gettext': ('(',),
    'ngettext': ('(',),
    'cached_gettext': ('(',),
    'cached_ngettext': ('(',),
    'mark_for_translation': ('(',),
    '(': (tokenize.STRING,),
    # comma introduces the keyword args for the gettext call.
    tokenize.STRING: ('+', ',', ')', tokenize.STRING),
    '+': (tokenize.STRING,),
    # Once we are at keywords, the function call is ok.
    # TODO(csilvers): for ngettext we want to stop after the second comma.
    ',': None,
    ')': None
    }


def lint_non_literal_i18n_in_python(files_to_lint):
    """Complain about uses of i18n._() on something other than a string.

    i18n._(variable) is dangerous -- you don't know if the variable
    has been translated or not.  Sometimes it's ok, but usually it's a
    mistake, and a better solution is to pass in translated_variable
    instead.  (The OK cases can be marked with @Nolint.)
    """
    current_state = None    # not currently in a gettext context
    gettext_linenum = None  # linenum of current gettext call
    has_nolint = False      # any line of the i18n._ may have @nolint

    # Only need to lint python files, but not test files.
    files = lintutil.filter(files_to_lint, suffix='.py',
                            exclude_substrings=['_test.py'])

    for (fname, ttype, token, (linenum, _), _, line) in (
            lintutil.python_tokens(files)):
        # Don't lint *definitions* of these methods.
        if line.strip().startswith('def '):
            continue

        # The state machine may transition on either the type
        # of the token, or its literal value.
        if token in _GETTEXT_STATE_MACHINE[current_state]:
            current_state = token
            gettext_linenum = gettext_linenum or linenum
            has_nolint = has_nolint or '@Nolint' in line
        elif ttype in _GETTEXT_STATE_MACHINE[current_state]:
            current_state = ttype
            gettext_linenum = gettext_linenum or linenum
            has_nolint = has_nolint or '@Nolint' in line
        elif current_state is None:
            # We weren't in gettext before, and we're still not.
            pass
        else:
            # We're in gettext, but can't transition: we're bad.
            # Give ourselves *one more* chance for nolint.
            has_nolint = has_nolint or '@Nolint' in line
            if current_state in _START_TOKENS:
                # BUT: If we last saw _ or ngettext and can't
                # transition because we're not a '(', that
                # means it's not a function call, so we can
                # ignore it.  e.g. '(f, _) = file_and_line()'.
                pass
            elif not has_nolint:
                yield (fname, gettext_linenum,
                       'gettext-like calls should only have '
                       'literal strings as their arguments')
            current_state = None
            gettext_linenum = None
            has_nolint = False

        # If we've happily ended a gettext call, clear the state.
        if _GETTEXT_STATE_MACHINE[current_state] is None:
            current_state = None
            gettext_linenum = None
            has_nolint = False


def lint_non_literal_i18n_in_javascript(files_to_lint):
    """Complain about uses of i18n._() on something other than a string.

    i18n._(variable) is dangerous -- you don't know if the variable
    has been translated or not.
    """
    files_to_lint = lintutil.filter(
        files_to_lint, suffix=('.js', '.jsx'),
        exclude_substrings=('/i18n.js', '/i18n_test.js'))

    # This regexp pattern captures a string, possibly concatenated with +'s.
    js_str = (r'(?:' +
              r'"(?:\\.|[^"])*"|' +
              r"'(?:\\.|[^'])*'|" +
              r'`(?:\\.|[^`])*`' +
              ')')
    js_concat_str = '\s*%s(?:\s*\+\s*%s)*\s*' % (js_str, js_str)

    gettext_occurrences = re.compile(r'\b(i18n._|i18n.ngettext)\(')
    valid_gettext_occurrences = re.compile(
        r'\bi18n._\(%(str)s[,)]|\bi18n.ngettext\(%(str)s,\s*%(str)s[,)]'
        % {'str': js_concat_str})

    for f in files_to_lint:
        contents = lintutil.file_contents(f)
        all_occurrences = {
            m.start(): m for m in gettext_occurrences.finditer(contents)}
        valid_occurrences = {
            m.start(): m for m in valid_gettext_occurrences.finditer(contents)}

        for (startpos, m) in all_occurrences.iteritems():
            i18n_fn = m.group(1)
            msg = None      # set to non-None if there's a problem.

            if startpos not in valid_occurrences:
                msg = ('%s must have string literals as arguments, '
                       'with no variables or templates' % i18n_fn)
            else:
                # Then we're ok with this!  *Unless* it's a template string
                # with $(...) inside it, then we're not ok.
                m2 = valid_occurrences[startpos]
                if m2.group().count(r'${') > m2.group().count(r'\${'):
                    msg = ('You must use %' + '(...)s with template strings '
                           'inside %s, not ${...}' % i18n_fn)

            if msg:
                start_lineno = 1 + contents.count('\n', 0, startpos)
                # Doing a real regexp to find the end of this function call
                # is tough, we just do something simple and pray.
                end_paren = contents.find(')', startpos)
                if end_paren == -1:
                    end_paren = len(contents)
                end_lineno = 1 + contents.count('\n', 0, end_paren)
                if any(lintutil.has_nolint(f, lineno)
                       for lineno in xrange(start_lineno, end_lineno + 1)):
                    continue
                yield (f, start_lineno, msg)


def lint_templates_are_translated(files_to_lint):
    """Verify that nltext in the input templates are marked for translation.

    All natural-language text in jinja2 and handlebars files should be
    marked for translation, using {{ _("...") }} or {{#_}}...{{/_}}.
    i18nize_templates.py is a tool that can do this for you automatically.
    We run this tool in 'check' mode to verify that every input file
    is already marked up appropriately.

    Since i18nize_templates isn't perfect (it thinks you need to
    translate text like 'Lebron James' or 'x' when used on a 'close'
    button), you can use nolint-like functionality to tell this linter
    it's ok if some text is not marked up to be translated.  Unlike
    other tests though, we do not use the @Nolint directive for this,
    but instead wrap the relevant text in
       {{ i18n_do_not_translate(...) }}
    or
       {{#i18nDoNotTranslate}}...{{/i18nDoNotTranslate}}
    """
    # Add some ka-specific function we know do not have nltext arguments.
    i18nize_templates.mark_function_args_lack_nltext(
        'js_css_packages.package',
        'js_css_packages.script',
        'handlebars_template',
        'youtube.player_embed',
        'log.date.strftime',
        'emails.tracking_image_url',
        'templatetags.to_canonical_url',
        'render_react',
    )

    for f in files_to_lint:
        abs_f = f
        f = ka_root.relpath(f)

        # Exclude files that we don't need to translate: we don't care
        # if those files are 'properly' marked up or not.
        if intl.english_only.should_not_translate_file(f):
            continue

        if (f.startswith('templates' + os.sep) and
            (f.endswith('.html') or f.endswith('.txt'))):
            # jinja2 template
            parser = i18nize_templates.get_parser_for_file(f)
            correction = 'wrap the text in {{ i18n_do_not_translate() }}'
        elif f.endswith('.handlebars'):
            # handlebars template
            parser = i18nize_templates.get_parser_for_file(f)
            correction = ('wrap the text in {{#i18nDoNotTranslate}}...'
                          '{{/i18nDoNotTranslate}}')
        else:
            continue

        file_contents = lintutil.file_contents(abs_f)
        try:
            parsed_output = parser.parse(
                file_contents.decode('utf-8')).encode('utf-8')
        except i18nize_templates.HTMLParser.HTMLParseError, why:
            m = re.search(r'at line (\d+)', str(why))
            linenum = int(m.group(1)) if m else 1
            yield (abs_f, linenum,
                   '"i18nize_templates.py %s" fails: %s' % (f, why))
            continue

        orig_lines = file_contents.splitlines()
        parsed_lines = parsed_output.splitlines()
        for i in xrange(len(orig_lines)):
            if orig_lines[i] != parsed_lines[i]:
                yield (abs_f, i + 1,
                       'Missing _(); run tools/i18nize_templates.py or %s '
                       '(expecting "%s")'
                       % (correction, parsed_lines[i].strip()))


def _lint_js_content(filename, content):
    """Verify that nltext in the js content is marked for translation.

    All natural-language text in js files should be marked for
    translation using i18n._ or i18n.ngettext.  It is very hard though
    to figure out if a string in js should be translated or not. So we
    check for strings that we know should be translated.  For now this
    just checks to make sure that string arguments inside a function
    called Text() or React.Dom.* are marked for translation.

    filename should be an absolute path.

    Returns:
       List of triples: (filename, lineno, error message)

    """
    line_number = None
    last_argument = None
    is_first_argument_within_func = False
    concatenate_next_argument = False
    call_stack = []
    last_maybe_func_name = None
    concatenate_next_name = None

    if ".jsx" in filename:
        correct_wrappers = ("<$_> .. </$_> or "
                            "<$i18nDoNotTranslate> .. "
                            "</$i18nDoNotTranslate>")
    else:
        correct_wrappers = "i18n._(..) or i18n.i18nDoNotTranslate(..)"

    def func_string_args_should_be_translated(func_name):
        """Return true if string args should be translated.

        eg. React.DOM.strong({style:{color:"red"}}, "Test")
        The first argument is an object, but the second is an untranslated
        string that should be wrapped in i18n._()
        """
        if not func_name:
            return False

        # Old versions of react have React.creatElement().  Newer ones
        # hae _react2.default.createElement().
        if ((func_name == "React.createElement" or
             'react' in func_name and 'createElement' in func_name) and
                not is_first_argument_within_func):
            # The first arg within CreateElement can be a string like "div"
            # all others must be translated
            return True
        elif func_name.startswith("React.DOM.") or func_name == "Text":
            return True

        return False

    for token in jslexer.tokenize(content):
        if token.type == 'operator' and token.value in  ["(", "{", "["]:
            call_stack.append(last_maybe_func_name)
            is_first_argument_within_func = True

        elif (token.type == 'string' and
                call_stack and
                func_string_args_should_be_translated(call_stack[-1])):
            # Collect any string that is an immediate child of Text - there
            # should not be any, it should be wrapped in i18n._
            new_value = jslexer.unquote_string(token.value.decode('utf-8'))
            line_number = token.lineno
            if concatenate_next_argument:
                last_argument = (last_argument or '') + new_value
                concatenate_next_argument = False
            else:
                last_argument = new_value

        elif token.type == 'operator' and token.value == '+':
            concatenate_next_argument = True

        elif token.type == 'operator':
            last_func = call_stack[-1] if call_stack else None
            if (func_string_args_should_be_translated(last_func) and
                    last_argument and
                    not intl.english_only.should_not_translate_string(
                        last_argument) and
                        token.value in [")", "}", "]", ",", ":"]
                    ):

                yield (filename, line_number,
                       "The string '%s' inside of a %s() is not translated. "
                       "Please wrap it in %s or add the file to "
                       "intl/english_only.py" % (
                           last_argument.encode("utf-8"),
                           last_func.encode("utf-8"),
                           correct_wrappers))
            is_first_argument_within_func = False
            last_argument = None
            if token.value in [")", "}", "]"] and call_stack:
                call_stack.pop()

        # Keep track of last full func name eg. React.DOM.div
        if token.type == 'name':
            # This could also be variable, keyword, or something else, but
            # we will keep it around just in case it is followed by a (
            if last_maybe_func_name and concatenate_next_name:
                last_maybe_func_name += ".%s" % token.value
                concatenate_next_name = True
            else:
                last_maybe_func_name = token.value

        elif token.type == 'operator' and token.value == '.':
            concatenate_next_name = True

        else:
            concatenate_next_name = False
            last_maybe_func_name = None


def lint_js_files_are_translated(files_to_lint):
    """Verify that nltext in the js files are marked for translation.

    See docstring of: _lint_js_content

    Returns:
       List of triples: (filename, lineno, error message)
    """
    # Make sure jsx files are compiled first, then we will lint the resulting
    # js.
    kake.make.build_many([('genfiles/compiled_jsx/en/%s.js' %
                           ka_root.relpath(f), {})
                          for f in files_to_lint if f.endswith('.jsx')])

    files_to_lint = lintutil.filter(files_to_lint, suffix=('.js', '.jsx'))
    for f in files_to_lint:
        abs_f = f
        f = ka_root.relpath(f)

        # Exclude files that we don't need to translate: we don't care
        # if those files are 'properly' marked up or not.
        if intl.english_only.should_not_translate_file(f):
            continue

        if f.endswith(".jsx"):
            abs_f = "%s/genfiles/compiled_jsx/en/%s.js" % (ka_root.root, f)
            f = ka_root.relpath(abs_f)

        file_contents = lintutil.file_contents(abs_f)

        for error in _lint_js_content(abs_f, file_contents):
            yield error


def lint_have_needed_babel_locales(files_to_lint):
    """Make sure we have all the locales we need, in third_party/babel.

    third_party/babel/localedata comes with 664 languages, which is
    great for coverage but bad for deploy time.

    So to speed things up, I added to app.yaml's skip_files all
    language files that aren't used by either a locale in all_ka_locales or
    a YouTube locale.
    This lint check makes sure that when we update those lists (or update the
    babel subrepo), we upload any localedata languages that we need to.
    """
    if (ka_root.join('intl', 'i18n.py') not in files_to_lint and
            not any(f.startswith(intl.data.INTL_VIDEO_PLAYLISTS_DIR)
                    for f in files_to_lint) and
            ka_root.join('third_party', 'babel-khansrc') not in files_to_lint):
        return

    config = modules_util.module_yaml('default')

    # Take only the rules for third_party/babel/localedata, and strip
    # off that prefix since we're starting the FileIterator in the
    # localedata directory rather than ka-root.
    # Note this depends on the babel rules starting with ^ and ending with $.
    localedata_root = 'third_party/babel/localedata'
    prefix = re.escape(r'(?:.*/webapp/)?')
    babel_regexps = [s for s in re.findall(r'\^(?:%s)?([^$]*)\$' % prefix,
                                           config['skip_files'].regex.pattern)
                     if s.startswith(localedata_root + '/')]
    skip_files = [s.replace('%s/' % localedata_root, '^')
                  for s in babel_regexps]
    skip_re = re.compile('|'.join('(?:%s)' % p for p in skip_files))

    orig_level = logging.getLogger().level
    try:
        logging.getLogger().setLevel(logging.ERROR)
        localedata_files = appcfg.FileIterator(ka_root.join(localedata_root),
                                               skip_re, config['runtime'])
        localedata_files = list(localedata_files)
    finally:
        logging.getLogger().setLevel(orig_level)

    # Remove the '.dat' extension.
    all_locales_for_babel = frozenset(os.path.splitext(f)[0]
                                      for f in localedata_files)

    needed_locales = intl.data.all_ka_locales(include_english=True)

    babel_locales = set([b for b in [intl.locale.ka_locale_to_babel(l)
                                     for l in needed_locales] if b])

    for babel_locale in babel_locales:
        # We need to check zh_Hans_CN.dat exists, but also zh_Hans.dat, etc.
        for prefix in intl.locale.locale_prefixes(babel_locale):
            # We need to convert from KA-style - to babel-style _.
            prefix = prefix.replace('-', '_')
            if prefix not in all_locales_for_babel:
                yield ('skip_files.yaml', 1,
                       "We need babel locale info for %s but it's been added"
                       " to skip-files (need to whitelist it)." % prefix)


def lint_not_using_gettext_at_import_time(files_to_lint):
    """Make sure we don't use i18n._/etc in a static context.

    If you have a global variable such as '_FOO = i18n._("bar")', at
    the top of some .py file, it won't work the way you intend because
    i18n._() needs to be called while handling a request in order to
    know what language to translate to.  (Instead, you'd need to do
        _FOO = lambda: i18n._("bar")
    or some such.)

    This tests for this by mocking i18n._ et al., and then importing
    everything (but running nothing).  Any i18n._ calls that happen
    during this import are problematic!  We have to spawn a new
    python process to make sure we do the importing properly (and
    without messing with the currently running python environment!)
    """
    candidate_files_to_lint = lintutil.filter(files_to_lint, suffix='.py')
    files_to_lint = []

    for filename in candidate_files_to_lint:
        contents = lintutil.file_contents(filename)

        # Check that it's plausible this file uses i18n._ or similar.
        # This also avoids importing random third-party files that may
        # have nasty side-effects at import time (all our code is too
        # well-written to do that!)
        if 'import intl' in contents or 'from intl' in contents:
            files_to_lint.append(filename)

    program = """\
import os                # @Nolint(linter can't tell this is in a string!)
import sys               # @Nolint(linter can't tell this is in a string!)
import traceback

import intl.request      # @Nolint(seems unused to our linter but it's used)

_ROOT = "%s"

def add_lint_error(f):
    # We assume code in 'intl' doesn't make this mistake, and thus
    # the first stack-frame before we get into 'intl' is the
    # offending code.  ctx == '<string>' means the error occurred in
    # this pseudo-script.
    for (ctx, lineno, fn, line) in reversed(traceback.extract_stack()):
        if os.path.isabs(ctx):
            ctx = os.path.relpath(ctx, _ROOT)
        if ctx != '<string>' and not ctx.startswith('intl/'):
            if ctx == f:
                print 'GETTEXT ERROR {} {}'.format(ctx, lineno)
            break
    return 'en'     # a fake value for intl.request.ka_locale

""" % ka_root.root

    if not files_to_lint:
        return

    for filename in files_to_lint:
        modulename = ka_root.relpath(filename)
        modulename = os.path.splitext(modulename)[0]  # nix .py
        modulename = modulename.replace('/', '.')
        # Force a re-import.
        program += 'sys.modules.pop("%s", None)\n' % modulename
        program += ('intl.request.ka_locale = lambda: add_lint_error("%s")\n'
                    % ka_root.relpath(filename))
        program += 'import %s\n' % modulename

    p = subprocess.Popen(
        ['env', 'PYTHONPATH=%s' % ':'.join(sys.path),
         sys.executable, '-c', program],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    p.wait()
    lint_output = p.stdout.read()
    for line in lint_output.splitlines():
        if line.startswith('GETTEXT ERROR '):
            line = line[len('GETTEXT ERROR '):]
            (filename, linenum) = line.rsplit(' ', 1)
            yield (ka_root.join(filename), int(linenum),
                   'Trying to translate at import-time, but '
                   'translation only works at runtime! '
                   'Use intl.i18n.mark_for_translation() instead.')


_SKIP_FILES_RE = None


def _does_not_upload(f):
    """True if f, relative to ka-root, is not uploaded to appengine."""
    global _SKIP_FILES_RE
    if not _SKIP_FILES_RE:
        config = modules_util.module_yaml('default', for_production=True)
        _SKIP_FILES_RE = config['skip_files'].regex

    assert not os.path.isabs(f), f     # or the while will never terminate
    while f:
        if _SKIP_FILES_RE.match(f):
            return True
        f = os.path.dirname(f)         # see if we skip this whole directory
    return False


def lint_strftime(files_to_lint):
    """Complain if you use strftime() instead of i18n.format_date()."""
    _BAD_REGEXPS = (
        # Javascript
        r'toDateString\(\)',
        # Jinja2 and python.  These are all the modifiers that depend
        # on the current locale (e.g. %B).
        r'strftime\([\'\"][^\'\"]*%[aAbBcDhpPrxX+]',
        # These are modifiers that are numbers, but used in contexts that
        # indicate they're probably US-specific, e.g. '%d,', which means
        # the current day-of-month followed by a comma, or day before
        # month.
        r'strftime\([\'\"][^\'\"]*(?:%d,|%d.%m)',
        )
    bad_re = re.compile('|'.join('(?:%s)' % b for b in _BAD_REGEXPS))

    for f in files_to_lint:
        relpath = ka_root.relpath(f)

        # Ignore third_party code. Normally third_party code wouldn't wind up
        # being linted in the first place because all of third_party is in
        # webapp's lint_blacklist.txt, but for code that lives in third_party
        # that has its own lint_blacklist.txt (e.g. live-editor), webapp's lint
        # blacklist.txt gets overridden.
        if relpath.startswith('third_party'):
            continue

        if intl.english_only.should_not_translate_file(relpath):
            continue

        # Ignore python files we're not uploading to appengine.  (We
        # can't use this rule with all files since js and html files
        # aren't uploaded directly, but we still want to lint them.)
        if f.endswith('.py') and _does_not_upload(ka_root.relpath(f)):
            continue

        badline = lintutil.line_number(f, bad_re, default=None)
        if badline is not None:
            yield (f, badline,
                   'Using U.S.-specific date formatting. '
                   'Use intl.i18n.format_date() and friends instead.')
