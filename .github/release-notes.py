#!/usr/bin/env python3
"""Print the GitHub Release notes for one version, taken from CHANGELOG.md.

    python3 .github/release-notes.py v0.8.0      # or 0.8.0

The body is that version's `## [X.Y.Z]` section, verbatim, plus the footer
every release carries. Exit 1, printing nothing to stdout, when the section
is missing or empty: .github/workflows/release.yml must fail rather than
publish a Release with no notes, and the selftest runs this against the
plugin.json version so CI fails before such a tag can be cut (github-5659d).
"""
import os
import re
import sys

FOOTER = (
    'Install and upgrade steps are in the '
    '[README](https://github.com/Kaimoku-Technologies/beads-roadmap#install). '
    'Earlier releases are in the '
    '[CHANGELOG](https://github.com/Kaimoku-Technologies/beads-roadmap/blob/main/CHANGELOG.md).'
)


def notes(changelog, version):
    """The section body for `version`, or None when absent or empty."""
    parts = re.split(r'^## \[([^\]]+)\][^\n]*\n', changelog, flags=re.M)
    sections = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    body = sections.get(version)
    if body is None:
        return None
    # Keep-a-Changelog link references belong to the file, not one release.
    body = re.sub(r'^\[[^\]]+\]: \S+\s*$', '', body, flags=re.M).strip()
    return body or None


def main(argv):
    if len(argv) != 2:
        print('usage: release-notes.py <vX.Y.Z | X.Y.Z>', file=sys.stderr)
        return 2
    version = argv[1][1:] if argv[1].startswith('v') else argv[1]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'CHANGELOG.md'), encoding='utf-8') as fh:
        body = notes(fh.read(), version)
    if body is None:
        print(f'release-notes: no non-empty "## [{version}]" section in CHANGELOG.md',
              file=sys.stderr)
        return 1
    print(body + '\n\n' + FOOTER)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
