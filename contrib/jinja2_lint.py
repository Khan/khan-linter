# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E128
"""Linters that warn about common problems with jinja2 templates.

This category includes people using jinja2 functionality inside python
when they shouldn't -- the linters that keep the separation between
presentation (jinja2) and logic (python).

We also lint javascript found inside jinja2 templates.
"""

from __future__ import absolute_import

import os
import re
import subprocess

from shared import ka_root
from shared.testutil import lintutil

from js_css_packages import js_in_html
import url_util


_JINJA2_MARKUP_TOKENS = ('jinja2', '.', 'Markup', '(')
# We also need to make sure 'Markup' isn't called without a leading 'jinja2.'.
# This can be fooled by 'from jinja2 \\\nimport Markup', but we don't care
# enough to do better here.
_IMPORT_MARKUP_RE = re.compile(r'^\s*from.*import.*\bMarkup\b')


def lint_no_jinja2_markup_in_python(files_to_lint):
    """Enforce that python code does not call jinja2.Markup().

    jinja2.Markup(s) says that jinja2 should not auto-escape s.  This
    is certainly useful to be able to do, but we shouldn't be doing it
    in python code (unless we're writing a jinja2 filter or tag)!
    Instead, the jinja2 template itself should be using the |safe
    modifier.  We enforce that this happens.

    The reason is that Markup() objects look like unicode but have
    these magical properties that can explode and cause trouble
    unexpectedly -- usually html-escaping things that are interpolated
    into it, without us wanting to.  As one example of the trouble it
    can cause, there's this code in api/jsonify.py:

        if isinstance(obj, jinja2.Markup):
            # Use the plain str representation of jinja2 Markup for jsonify.
            # Otherwise jinja2's Markup object will try to improperly encode
            # the double quotes that jsonify wraps around all strings.
            return unicode(obj)

    Needing to sprinkle special-case code like that everywhere is
    ugly; figuring out where such code needs to be sprinkled is a
    nightmare.

    As always, code that needs to override this check can use @Nolint.
    """
    # Only need to lint python files, but not test files.
    # And Markup() is expected in template-tags and template-filters.
    exclude = ('_test.py', '/templatetags.py', '/templatefilters.py')
    files = lintutil.filter(files_to_lint, suffix='.py',
                            exclude_substrings=exclude)

    for tokens in lintutil.find_token_streams(files, _JINJA2_MARKUP_TOKENS):
        yield (tokens[0][0], tokens[0][3][0],      # filename and linenum
               'Do not call jinja2.Markup() from code'
               ' (except in templatetags/filters).'
               ' Use |safe in templates instead.')

    for (fname, linenum, _) in lintutil.find_lines(files, _IMPORT_MARKUP_RE):
        yield (fname, linenum,
               'Import full modules, not classes from modules (Markup)')


_IMPORT_TEMPLATETAGS_RE = re.compile(
    r'^\s*import\b.*\b(templatetags|templatefilters)\b'
    r'|^\s*from\b.*\bimport\b.*\b(templatetags|templatefilters)\b'
    r'|^\s*from\b.*\b(templatetags|templatefilters)\s+import')


def lint_no_templatetags_calls_in_python(files_to_lint):
    """Enforce that python code does not call code in templatetags/filters.

    templatetags.py and templatefilters.py are intended to hold code
    that emits to jinja2 templates.  For that reason, we allow things
    there that are hard to use correctly in python logic, such as
    jinja2.Markup() objects.  To make sure we keep the distinction
    between jinja2 objects and python objects separate, we check that
    python code never calls stuff in templatetags/templatefilters.

    Such dual-use code can, if needed, be moved to a separate file,
    where it can be called by both 'normal' python code and functions
    in templatetags.  For instance, templatefilters.py:static_url()
    just calls url_util.static_url().
    """
    # Only need to lint python files, but not test files.  Also:
    # templatetags and templatefilters routines can call each other,
    # config_jinja can reference them to add them to the jinja2 config.
    exclude = ('_test.py', '/templatetags.py', '/templatefilters.py',
               '/config_jinja.py')
    files = lintutil.filter(files_to_lint, suffix='.py',
                            exclude_substrings=exclude)
    for (fname, linenum, line) in lintutil.find_lines(files,
                                                      _IMPORT_TEMPLATETAGS_RE):
        m = _IMPORT_TEMPLATETAGS_RE.search(line)
        module = m.group(1) or m.group(2) or m.group(3)
        yield (fname, linenum,
               '%s is for jinja2; do not call from Python code' % module)


def lint_static_url_modifier(files_to_lint):
    """Be sure every static url in an .html file uses |static_url or static().

    We serve static urls such as images and fonts from kastatic.org,
    for efficiency.  The |static_url and static_url() jinja2 modifiers are ways
    to rewrite urls to use that.  This linter makes sure people remember to do
    that for new code.
    """
    files = lintutil.filter(files_to_lint, prefix='templates/', suffix='.html')
    if not files:
        return

    # generate_static_urls_regexp matches standalone urls, but we need
    # to match them in the context of a line, so we need to mess with
    # ^ and $ a bit.  We just get rid of $, which could yield false
    # positives in theory but doesn't in practice.  We replace ^ with
    # something that matches 'things you might find before the start
    # of a static url but not before something like an API route name."
    static_url_regexp = url_util.STATIC_URL_REGEX
    static_url_regexp = static_url_regexp.replace('$', '')
    # The '%s' in the regexp below is to catch jinja2 html like:
    #   <img src="{{ "https://%s/images/..." % hostname }}">
    static_url_regexp = static_url_regexp.replace(
        '^/', r'([^\w_./-]["\'/]|khanacademy.org/|%s/)')

    # It's good when the static-url is followed by '|static_url' (it
    # needs to be in a '{{ ... }}' for that) or preceded by 'static_url('.
    # We say the regexp is bad if neither case is present.
    # This is cheaper than using a negative lookahead (I think).
    good_regexp = (r'(static_url\s*\(\s*)?(%s)([^}]*\|static_url)?'
                   % static_url_regexp)

    # We do two checks: one for the static url by name, and one for
    # any src= parameter (or poster=, which is used for videos).
    static_url_re = re.compile(good_regexp)
    # We take advantage of the fact we don't use spaces in our static urls.
    src_regex = re.compile(r'\b(src|poster)=((?:\{[^\}]*\}|[^ >])*)')

    for f in files:
        contents_of_f = lintutil.file_contents(f)
        error_lines = set()   # just to avoid duplicate error messages

        for m in static_url_re.finditer(contents_of_f):
            if not m.groups()[0] and not m.groups()[-1]:
                lineno = 1 + contents_of_f.count('\n', 0, m.start())
                # STATIC_URL_REGEX matches the character before the url-string,
                # and also the opening quote, so get rid of them both.
                url_prefix = m.group(2)[1:].strip('\'\"')
                yield (f, lineno,
                       ('The static url "%s..." should use "|static_url" '
                       + 'after the url or call "static_url()" with the url ' +
                       'passed in') % url_prefix)
                error_lines.add(lineno)

        # emails maybe want to point to ka.org to avoid confusion.
        # TODO(csilvers): should we point them to kastatic.org too?
        if '/emails/' not in f:
            for m in src_regex.finditer(contents_of_f):
                url = m.group(2).strip('\'\"{} ')
                if not url:
                    continue
                # A simple, but effective, effort to find urls that point to
                # non-ka domains.  (Most ka domains we use are .org!)
                if '.com' in url and '.appspot.com' not in url:
                    continue
                if url.startswith('data:'):
                    continue
                # If it's already a url that we serve off the CDN, don't
                # complain.
                if any(u in url for (_, u) in url_util.FASTLY_URL_MAP):
                    continue
                # If it's an <iframe src=...>, don't complain; those are
                # never static resources.  We just do a cheap check.
                end_of_line = contents_of_f.index('\n', m.end())
                if '</iframe>' in contents_of_f[m.end():end_of_line]:
                    continue

                if '|static_url' not in url:
                    lineno = 1 + contents_of_f.count('\n', 0, m.start())
                    if lineno not in error_lines:  # a new error
                        yield (f, lineno,
                               'Use |static_url with "%s" attributes'
                               % m.group(1))


def run_eslint(js_filename_contents_pairs):
    """Run eslint on the given content, given as (filename, content) pairs.

    The output is an array of (<filename>, <linenum>, <error message>)
    triples.

    This re-uses the eslint params that khan-linter uses.  We prefer
    the khan-linter version in devtools, but use the one in
    third-party if needed.
    """
    eslintrc = os.path.join(ka_root.root, '..',
                            'devtools', 'khan-linter', 'eslintrc.browser')
    if not os.path.exists(eslintrc):
        eslintrc = ka_root.join('third_party', 'khan-linter-src',
                                'eslintrc.browser')

    # Our eslint runner expects a file that looks like:
    #    <eslint filename>
    #    -- LINT_JAVASCRIPT_IN_HTML SEPARATOR: filename\n
    #    <file contents>
    #    -- LINT_JAVASCRIPT_IN_HTML SEPARATOR: filename\n
    #    ...
    eslint_input = [eslintrc + '\n']

    for (f, contents) in js_filename_contents_pairs:
        eslint_input.append('-- LINT_JAVASCRIPT_IN_HTML SEPARATOR: %s\n' % f)
        # Make sure when we join the strings together, each is on its own line.
        if not contents.endswith('\n'):
            contents += '\n'
        eslint_input.append(contents)

    eslint_runner = ka_root.join('testutil', 'lint_javascript_in_html.js')
    p = subprocess.Popen(['node', eslint_runner],
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate(''.join(eslint_input))
    if stderr:
        raise RuntimeError("Unexpected stderr from eslint:\n%s" % stderr)
    return [tuple(l.split(':', 2)) for l in stdout.splitlines()]


def lint_javascript_in_html(files_to_lint):
    """Run eslint on javascript content inside html files.

    We want to make sure that the js in our html files has no unused
    variables/etc, so we can do better dependency analysis on it.
    """
    files = lintutil.filter(files_to_lint, prefix='templates/', suffix='.html')

    lint_inputs = []      # list of filename/contents pairs

    for f in files:
        contents_of_f = lintutil.file_contents(f)

        # extract_js_from_html actually can return several versions
        # of the js contents, each with a different branch of an
        # if/else commented out.  (So for input like
        #  <script>var x = { {%if c%}y: 4{%else%}y: 5{%endif%} };</script>
        # we'd see both 'var x = { y: 4 };' and 'var x = { y: 5 }')
        # We lint all such strings and combine the output.
        js_contents_iter = js_in_html.extract_js_from_html(contents_of_f,
                                                           "jinja2",
                                                           file_name=f)

        try:
            for js_contents in js_contents_iter:
                lint_inputs.append((f, js_contents))
        except Exception, why:
            yield (f, 1, 'HTML parse error: %s' % why)
            continue

    errors = run_eslint(lint_inputs)
    # We sort and uniquify at the same time.  Unique is an issue because
    # often each of the js_contents_iters give the same error.
    errors = sorted(set(errors), key=lambda l: (l[0], int(l[1]), l[2:]))
    for (fname, bad_linenum, msg) in errors:
        yield (fname, int(bad_linenum), msg)


# We don't even allow comments before the IIFE block, because such
# comments confuse maybe_defer_inline_js.
_IIFE_RE = re.compile(r'^\s*\(function\s*\(\)', re.DOTALL)


def lint_iife_in_html_javascript(files_to_lint):
    """Make sure js in <script> tags doesn't leak globals by using an IIFE.

    IIFE is when you surround js code in '(function() { ... })();'.
    This prevents any variable declarations from polluting the global
    scope.  We require all <script> tags to have an IIFE if they
    declare a variable.
    """
    files = lintutil.filter(files_to_lint, prefix='templates/', suffix='.html')

    # For determining if we need an IIFE, we only care about 'var'
    # statements.
    var_re = re.compile(r'\bvar\b')

    for f in files:
        contents_of_f = lintutil.file_contents(f)

        # extract_js_from_html actually can return several versions
        # of the js contents, each with a different branch of an
        # if/else commented out.  (So for input like
        #  <script>var x = { {%if c%}y: 4{%else%}y: 5{%endif%} };</script>
        # we'd see both 'var x = { y: 4 };' and 'var x = { y: 5 }')
        # We lint all such strings and combine the output.
        js_contents_iter = js_in_html.extract_js_from_html(contents_of_f,
                                                           "jinja2",
                                                           keep_re=var_re,
                                                           file_name=f)
        try:
            for js_contents in js_contents_iter:
                if (not _IIFE_RE.match(js_contents) and
                        var_re.search(js_contents)):
                    # Our script is the first non-blank line in the
                    # extracted output.
                    lineno = len(js_contents) - len(js_contents.lstrip('\n'))
                    if not lintutil.has_nolint(f, lineno + 1):
                        yield (f, lineno + 1,
                               "Must wrap this script's contents in "
                               "'(function() { ... })();' (IIFE) to "
                               "avoid leaking vars to global state")
        except Exception, why:
            yield (f, 1, 'HTML parse error: %s' % why)
            continue
