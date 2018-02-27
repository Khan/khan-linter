#!/usr/bin/env python

"""Fix all references to static content in .html files to use |static_url.

TODO(csilvers): verify input .html is a jinja file, and bail if it's not.

The static_url filter, in url_util.py, is designed for any 'static'
content on our site; that is, content that is served via a static
handler in app.yaml, or otherwise is known to not either need or set
cookies.  Cookies don't do any good for static content, so there's no
reason to send them as part of the request, or as part of the
response; the static_url filter makes this happen (by serving the
images from a separate-but-equal domain name that doesn't have cookies
on it).  Since cookies can be rather large, this speeds up the serving
of images.

The KA code that embeds <script> and <style> tags in our emitted html
is written to automatically apply static_url() when putting filenames
in those tags, so .js and .css files already take advantage of this
functionality.  But other static content, particularly images, tend to
be specified directly in our html templates, where it's harder for the
code to automatically fix them up.  Instead, we use a lint check to
ensure that static content in .html files are marked with the
static-url filter, like so:
   <img width="100%" src="{{"/images/toolkit/summary.jpg"|static_url}}" />
   .container { background-image:url({{"/images/indicator.png"|static_url}}); }

As with all linters -- and the reason we use a linter rather than
doing this automatically, at least until the quality of the linter is
better -- you can disable the lint check for a given line via the
'@Nolint' directive:
   <img width="100%" src="/images/foo.jpg" />  {# @Nolint #}

USAGE:
   $0 [file or directory to lint] ...

If no file/directory is specified, defaults to 'templates/'.
"""

import optparse
import os
import re
import sys

import six

_DEFAULT_DIRS = ['templates/']

USAGE = """\
%%prog [file or directory to lint] ...
       If no file/directory is specified, defaults to %s
""" % ' + '.join(_DEFAULT_DIRS)


# Regular expressions matching what static urls look like.
# I could just do '/*.png' and so forth, but that would run the risk
# of catching images on third-party sites.  That's not *terrible*
# (static_url is a noop in that case), but it's extra work for the
# template renderer, so I try to match more carefully.
_STATIC_PATTERNS = (
    # images
    r'/gtv/images/\S*\.(png|gif|jpg|jpeg)',
    r'/images/\S*\.(png|gif|jpg|jpeg)',
    r'/khan-exercises/images/\S*\.(png|gif|jpg|jpeg)',
    r'/gae_bingo/static/img/\S*\.(png|gif|jpg|jpeg)',
    r'/stylesheets/\S*\.(png|gif|jpg|jpeg)',
    # fonts
    r'/khan-exercises/\S*\.(eot|otf|svg)',
    r'/files/\S*\.(eot|otf|svg)',
    r'/stylesheets/\S*\.(eot|otf|svg)',
    # sound files
    r'/sounds/\S*.(wav|mp3|ogg)',
    )

# Sometimes we put a query string at the end of a static resource to
# bust caches ("/images/profile-link-in-header.png?1").  So we allow
# the url to either end with just '.png'/etc, or with '.png?...'/etc.
_STATIC_RE = re.compile('^(%s)($|\?)' % ')|('.join(_STATIC_PATTERNS), re.I)

# To avoid (bad) false positives, we're conservative and
# only look for static-urls after src=, href=, url(, url(', or url(".
_CANDIDATE_STATIC_RE = re.compile(
    r'src\s*=\s*"([^"]*)"|'
    r"src\s*=\s*'([^']*)'|"
    r'href\s*=\s*"([^"]*)"|'
    r"href\s*=\s*'([^']*)'|"
    r'[\s:]url\([\'\"]?([^)]*)[\'\"]?\)',
    re.I)


def lint_one_file(filename, file_contents=None):
    """Return a list of error-tuples: (fname, linenum, colnum, endcol, msg)."""
    if not file_contents:
        with open(filename) as f:
            file_contents = f.read()

    retval = []
    for (linenum_minus_one, line) in enumerate(file_contents.splitlines()):
        if '@Nolint' in line or 'NoQA' in line:
            continue
        for m in _CANDIDATE_STATIC_RE.finditer(line):
            # _CANDIDATE_STATIC_RE has lots of parens, so m has lots
            # of groups.  Only one of them will have content in it at
            # any one time, though.  Let's find it.
            url_groupnum = [i for i in xrange(1, len(m.groups()) + 1)
                            if m.group(i) is not None][0]
            if _STATIC_RE.match(m.group(url_groupnum)):
                retval.append((filename, linenum_minus_one + 1,
                               m.start(url_groupnum), m.end(url_groupnum),
                               'expecting |static_url after "%s"'
                               % m.group(url_groupnum)))

    return retval


def lint(file_or_directory_names, extensions=('.html', '.htm')):
    """Lint the given files, or, for dirs, all files under the dir with ext."""
    retval = []
    for f in file_or_directory_names:
        if os.path.isdir(f):
            for (root, _, files) in os.walk(f):
                for filename in files:
                    if os.path.splitext(filename)[1] in extensions:
                        retval.extend(lint_one_file(os.path.join(root,
                                                                 filename)))
        else:
            retval.extend(lint_one_file(f))
    return retval


def fix(errors):
    """Add |static_url after all the places identified as needing it."""
    # Group errors by filename:
    errors_by_file = {}
    for (filename, linenum, colnum, endcol, unused_error) in errors:
        errors_by_file.setdefault(filename, []).append((linenum,
                                                        colnum, endcol))

    for (filename, errors) in errors_by_file.iteritems():
        six.print_('FIXING %s errors in %s' % (len(errors), filename))
        with open(filename) as f:
            lines = f.read().splitlines(True)
        # Since we change the line-length every time we munge a line,
        # sort the errors so the later columns go first.
        errors.sort(key=lambda e: e[1], reverse=True)   # e[1] is colnum
        for (linenum, colnum, endcol) in errors:
            line = lines[linenum - 1]     # -1 because lines[] is 0-indexed
            assert line[colnum - 1] in '\"\'(', (filename, linenum, colnum)
            assert line[endcol] in '\"\')', (filename, linenum, endcol)
            lines[linenum - 1] = ('%s{{"%s"|static_url}}%s'
                                  % (line[:colnum],
                                     line[colnum:endcol],
                                     line[endcol:]))
        with open(filename, 'w') as f:
            f.writelines(lines)


def main(file_or_directory_names, should_fix):
    errors = lint(file_or_directory_names)

    for (filename, linenum, colnum, unused_endcol, error) in errors:
        six.print_('%s:%s:%s: %s' % (filename, linenum, colnum, error))

    if should_fix:
        six.print_()
        fix(errors)

    return len(errors)


if __name__ == '__main__':
    parser = optparse.OptionParser(USAGE)
    parser.add_option('--fix', action='store_true',
                      help='Fix all errors found (by inserting |static_url)')
    options, args = parser.parse_args()

    num_errors = main(args or _DEFAULT_DIRS, options.fix)
    # Error codes >= 128 are reserved for signals.
    sys.exit(min(num_errors, 127))
