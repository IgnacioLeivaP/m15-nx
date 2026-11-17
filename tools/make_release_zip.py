#!/usr/bin/env python3
"""Packages the public repository into the zip attached to the GitHub release.

    py -3 tools/make_release_zip.py [--repo <dir>] [--out <dir>] [--version v1.0.0]

The zip carries the root mtg15-nx-<version>/ with the repository contents (app/, install/, sdk/, tools/,
docs/, LICENSE, README.md, THIRD_PARTY.md and .gitignore). It contains nothing of the game: the repository
is already verified with tools/check_clean.py before packaging.

The zip is written OUTSIDE the repository (by default ../work/release/) because check_clean forbids .zip
files inside the repository.
"""
import argparse
import os
import sys
import zipfile
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='repository folder to package (default: the one containing this script)')
    ap.add_argument('--out', default=None,
                    help='output folder (default ../work/release next to the repository)')
    ap.add_argument('--version', default='v1.0.0', help='release version (default v1.0.0)')
    a = ap.parse_args()

    repo = os.path.abspath(a.repo)
    for checker in ('check_clean.py', 'check_includes.py'):
        subprocess.run([sys.executable, os.path.join(repo, 'tools', checker), '--repo', repo], check=True)
    root = 'mtg15-nx-' + a.version
    out_dir = a.out or os.path.join(os.path.dirname(repo), 'work', 'release')
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, root + '.zip')

    ignored = {'__pycache__', '.git'}
    total = 0
    total_bytes = 0
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(repo):
            dirs[:] = sorted(d for d in dirs if d not in ignored)
            for nombre in sorted(files):
                src = os.path.join(base, nombre)
                rel = os.path.relpath(src, repo).replace(os.sep, '/')
                arc = root + '/' + rel
                z.write(src, arc)
                total += 1
                total_bytes += os.path.getsize(src)

    size = os.path.getsize(dst)
    print('release: %s' % dst)
    print('  %d files, %.2f MB (%.2f MB compressed)' % (total, total_bytes / (1 << 20), size / (1 << 20)))
    print('  inner root: %s/' % root)
    return 0


if __name__ == '__main__':
    sys.exit(main())
