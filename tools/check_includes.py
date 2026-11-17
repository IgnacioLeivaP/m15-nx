#!/usr/bin/env python3
"""Checks that every `#include "..."` in the port's code points at something that exists.

    py -3 -I tools/check_includes.py [--repo .]

Catches what is not obvious when copying a source tree around: a .cpp that was left out because only a game file
used it, a header that got lost along the way. `#include <...>` lines are not checked.

An include is considered resolved if it is in the repository (by relative path or by name anywhere under
`app/src`) or if the build generates it: the game's code (`generated/`), the SPIR-V headers CMake makes from the
.hlsl files (`host_shaders/`), the compiled config header and whatever arrives via `--thirdparty`.
"""
import argparse
import os
import re
import sys

EXT = ('.c', '.cc', '.cpp', '.h', '.hpp', '.inc', '.in')
INCLUDE = re.compile(r'^\s*#\s*include\s*"([^"]+)"')
IGNORADAS = {'.git', '__pycache__'}

# What is not in the repository because the build produces it or it is supplied separately.
EXTERNOS = (
    'generated/',            # written by the ReXGlue code generator (the translated game)
    'host_shaders/',         # the SPIR-V/DXIL headers CMake makes from the renderer's .hlsl files
    'mtg15_builtin_config.h',  # configure_file of src/mtg15_builtin_config.h.in
    'imgui', 'xxhash.h', 'shader_common.h', 'renderdoc_app.h', 'lz4.h', 'spirv_cross',
)


def externo(objetivo):
    o = objetivo.replace('\\', '/')
    return any(x in o for x in EXTERNOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--quiet', action='store_true', help='only the problems')
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    src = os.path.join(repo, 'app', 'src')

    # Everything under app/: to resolve `#include "shader_cache.h"` even from another subfolder.
    presentes = set()
    for base, dirs, files in os.walk(os.path.join(repo, 'app')):
        dirs[:] = [d for d in dirs if d not in IGNORADAS and d != 'thirdparty']
        for nombre in files:
            presentes.add(os.path.join(base, nombre).replace(os.sep, '/'))
            presentes.add(os.path.basename(nombre))

    fuera, externos, revisados, total = [], [], 0, 0
    for base, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in IGNORADAS)
        for nombre in sorted(files):
            if not nombre.endswith(EXT):
                continue
            ruta = os.path.join(base, nombre)
            rel = os.path.relpath(ruta, repo).replace(os.sep, '/')
            total += 1
            try:
                with open(ruta, encoding='utf-8') as f:
                    lineas = f.readlines()
            except UnicodeDecodeError:
                fuera.append('%s: not UTF-8' % rel)
                continue
            for numero, linea in enumerate(lineas, 1):
                m = INCLUDE.match(linea)
                if not m:
                    continue
                objetivo = m.group(1)
                revisados += 1
                candidatos = [os.path.join(base, objetivo).replace(os.sep, '/'),
                              os.path.join(os.path.dirname(ruta), objetivo).replace(os.sep, '/')]
                if any(c in presentes for c in candidatos) or os.path.basename(objetivo) in presentes:
                    continue
                if externo(objetivo):
                    externos.append('%s:%d  %s' % (rel, numero, objetivo))
                else:
                    fuera.append('%s:%d  missing: %s' % (rel, numero, objetivo))
    if not a.quiet:
        print('check_includes: %d source files, %d #include "..." checked' % (total, revisados))
        print('  %d come from the build or --thirdparty (not here, and they must not be)'
              % len(externos))
    if fuera:
        print('')
        print('%d UNRESOLVED:' % len(fuera))
        for f in fuera:
            print('  - %s' % f)
        return 1
    if not a.quiet:
        print('  all local includes resolve inside the repository')
    return 0


if __name__ == '__main__':
    sys.exit(main())
