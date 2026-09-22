#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Check the relative links in README.md and docs/.

Fails on a relative link whose file doesn't exist, and on an anchor that
isn't a heading in the page it points to.

docs/ is also published as part of the images repository's MkDocs site, where
nothing outside docs/ exists. So a link from docs/ that leaves docs/ is an
error, and so is an anchor that GitHub and MkDocs spell differently: the two
turn headings into anchors by slightly different rules. External URLs are
not fetched.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / 'docs'

FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')
CODE_SPAN = re.compile(r'(`+)(?:(?!\1).)+?\1')
# [text](target "title") and ![alt](target); the text may hold one level of
# brackets, as in [`--flag [x]`](page.md).
INLINE_LINK = re.compile(
    r'!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>]*>|[^\s)]+)'
    r'(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\)))?\s*\)')
REFERENCE_DEF = re.compile(r'^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)')
HEADING = re.compile(r'^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$')
SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')


def strip_code(lines):
    """Yield (number, line) for lines outside fenced code blocks."""
    fence = None
    for number, line in enumerate(lines, 1):
        match = FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
                continue
            yield number, line
        elif match and match.group(1)[0] == fence[0] \
                and len(match.group(1)) >= len(fence) \
                and not line.strip()[len(match.group(1)):].strip():
            fence = None


def heading_text(raw):
    """The visible text of a heading, as both renderers see it."""
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', raw)  # links -> text
    text = re.sub(r'<[^>]+>', '', text)                    # inline HTML
    text = text.replace('`', '')
    text = re.sub(r'(\*\*|__|\*|\b_|_\b)', '', text)       # emphasis
    return text.strip()


def github_slug(text):
    """GitHub's anchor for a heading."""
    text = text.lower()
    text = re.sub(r'[^\w\- ]', '', text)
    return text.replace(' ', '-')


def mkdocs_slug(text):
    """Python-Markdown's default toc slug, which MkDocs uses."""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text)


def anchors(path, cache={}):
    """Anchors that work in both renderers, and those that work in one."""
    if path not in cache:
        both, either = set(), set()
        seen_gh, seen_md = {}, {}
        lines = path.read_text(encoding='utf-8').splitlines()
        for _, line in strip_code(lines):
            match = HEADING.match(line)
            if not match:
                continue
            text = heading_text(match.group(2))
            gh, md = github_slug(text), mkdocs_slug(text)
            # Repeated headings get numbered suffixes, differently in each.
            n = seen_gh.get(gh, 0)
            seen_gh[gh] = n + 1
            gh = gh if n == 0 else '{}-{}'.format(gh, n)
            n = seen_md.get(md, 0)
            seen_md[md] = n + 1
            md = md if n == 0 else '{}_{}'.format(md, n)
            either.update((gh, md))
            if gh == md:
                both.add(gh)
        cache[path] = (both, either)
    return cache[path]


def links(path):
    """Yield (line number, target) for every link in a markdown file."""
    lines = path.read_text(encoding='utf-8').splitlines()
    for number, line in strip_code(lines):
        line = CODE_SPAN.sub('', line)
        for match in INLINE_LINK.finditer(line):
            yield number, match.group(1).strip('<>')
        match = REFERENCE_DEF.match(line)
        if match:
            yield number, match.group(1).strip('<>')


def is_within(path, directory):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def check_link(source, target):
    """Return an error message for a broken link, or None."""
    if SCHEME.match(target) or target.startswith('//'):
        return None
    path_part, _, anchor = target.partition('#')
    in_docs = is_within(source, DOCS)

    if path_part:
        if path_part.startswith('/'):
            return 'absolute path; use a relative link or a full URL'
        dest = (source.parent / unquote(path_part)).resolve()
        if not dest.exists():
            return 'no such file'
        if in_docs and not is_within(dest, DOCS):
            return ('leaves docs/, which the site does not have; link to '
                    'https://github.com/smarobix/smarobix-colcon-buildx/'
                    'blob/main/... instead')
        if in_docs and dest.is_dir():
            return 'links to a directory; link to a page in it'
    else:
        dest = source

    if anchor:
        if dest.suffix != '.md' or not dest.is_file():
            return 'anchor on something that is not a markdown page'
        both, either = anchors(dest)
        if anchor not in either:
            return 'no heading with anchor #' + anchor
        if in_docs and anchor not in both:
            return ('anchor #{} differs between GitHub and MkDocs; link to '
                    'a heading without punctuation').format(anchor)
    return None


def default_files():
    files = [REPO_ROOT / 'README.md']
    files += sorted(DOCS.rglob('*.md'))
    return [f for f in files if f.is_file()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        'files', nargs='*', type=Path,
        help='markdown files to check (default: README.md and docs/)')
    args = ap.parse_args(argv)

    files = [f.resolve() for f in args.files] or default_files()
    errors = 0
    checked = 0
    for source in files:
        shown = source.relative_to(REPO_ROOT) \
            if is_within(source, REPO_ROOT) else source
        for number, target in links(source):
            if SCHEME.match(target) or target.startswith('//'):
                continue
            checked += 1
            error = check_link(source, target)
            if error:
                errors += 1
                print('{}:{}: {}: {}'.format(shown, number, target, error),
                      file=sys.stderr)
    print('{} relative links in {} files, {} broken'.format(
        checked, len(files), errors))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
