#!/usr/bin/env python3
"""Select and verify user-owned Magic 2015 captures; never decrypt game archives."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, default=repo / 'install/games/mtg15.json')
    ap.add_argument('--lua-dump', action='append', default=[], type=Path)
    ap.add_argument('--shader-dump', action='append', default=[], type=Path)
    ap.add_argument('--texture-dump', action='append', default=[], type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    out = args.out.resolve()
    if out == repo or repo in out.parents:
        ap.error('--out must be outside the source repository')
    sources = {'lua': args.lua_dump, 'shader': args.shader_dump, 'texture': args.texture_dump}
    for folders in sources.values():
        for folder in folders:
            if not folder.is_dir():
                ap.error('Capture directory does not exist: ' + str(folder))
    sys.path.insert(0, str(repo / 'install'))
    from menus import normalize
    profile = json.loads(args.profile.read_text(encoding='utf-8'))
    report = {'complete': True, 'categories': {}}
    for kind, folders in sources.items():
        target_dir = out / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        missing, rejected, verified = [], [], 0
        for entry in profile[kind + '_captures']:
            name = entry.get('name', entry.get('file'))
            target = target_dir / name
            candidates = [target]
            for folder in folders:
                candidates.append(folder / name)
                if kind == 'lua':
                    candidates.extend(sorted(folder.glob('*_' + name)))
            match = None
            for candidate in dict.fromkeys(candidates):
                if not candidate.is_file():
                    continue
                data = candidate.read_bytes()
                if kind == 'lua':
                    try:
                        data = normalize(data)
                    except Exception as exc:
                        rejected.append({'file': str(candidate), 'reason': str(exc)})
                        continue
                if len(data) == entry['size'] and hashlib.sha256(data).hexdigest() == entry['sha256']:
                    match = data
                    break
                rejected.append({'file': str(candidate), 'reason': 'size or SHA256 mismatch'})
            if match is None:
                missing.append(name)
                continue
            if target.exists() and target.read_bytes() != match:
                ap.error('Refusing to overwrite a different file: ' + str(target))
            if not target.exists():
                target.write_bytes(match)
            verified += 1
        expected = len(profile[kind + '_captures'])
        report['categories'][kind] = {'verified': verified, 'expected': expected,
                                       'missing': missing, 'rejected': rejected}
        report['complete'] = report['complete'] and not missing
        print('%s: %d/%d verified; %d missing' % (kind, verified, expected, len(missing)))
    report_file = out / 'capture_report.json'
    report_file.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Report: ' + str(report_file))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
