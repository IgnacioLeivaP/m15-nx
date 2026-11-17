#!/usr/bin/env python3
"""Checks that this repository carries nothing of the game (no data, no art, no generated code).

    py -3 tools/check_clean.py [--repo .] [--ref DIR ...] [--quiet]

Fails (code 1) if it finds inside the repository:
  - game-data or build-artifact extensions (.xex, .xexp, .wad, .nxpack, .nro, .bin, .TDX, .lua, ...)
  - headers: XEX2, WAD (0x1234 version 0x0201/0x0202), TDX (0x0200), STFS (LIVE / PNG) or Lua bytecode (\\x1bLua)
  - `generated` folders (the game's code translated to C++)
  - files over 5 MB
  - personal paths (C:\\Users, D:\\Juegos, /home/...), email addresses or strings that look like keys
  - comments that are a PowerPC instruction listing (the game's disassembly pasted next to the code)
  - any file whose SHA256 matches one in the reference folders (--ref: by default ../game,
    ../tu, the DLC packages at the project root and ../nx/out/pack)

Magic 2015 keeps its menus as Lua text, so `.lua` is also forbidden: the scripts are generated at install
time (`install/lua13.py`), they do not travel here.

The SHA256 of the game's files CAN be published (they are verification pointers, not game data): the installer
carries them in install/games/<game>.json, the README repeats them in its table, and here they are tolerated in
those two places. Outside them, a 64-character hexadecimal string is only accepted if the line says it is a
fingerprint (sha256 / hash) of a function or of a generated file.

`sdk/` is third-party code copied as-is (ReXGlue and its small dependencies): there only the things that can
never be there are checked -- binaries, game data, size and SHA256 --, not the text heuristics (those files carry
their author's email in the license header, documentation images and non-UTF-8 test data). The documentation logos
and tests of those folders are theirs, not the game's.
"""
import argparse
import hashlib
import os
import re
import sys

MAX_BYTES = 5 << 20
ZONA_VENDIDA = ('sdk/',)   # third-party code as-is: only binaries, data and sizes are checked

EXT_PROHIBIDAS = {
    '.zed', '.xex', '.xexp', '.xbe', '.xap', '.wad', '.nxpack', '.nxidx', '.pack', '.nsp', '.xci', '.nro', '.nso', '.nca',
    '.bin', '.tdx', '.dds', '.luac', '.lua', '.lob', '.xma', '.wmv', '.bik', '.ogg', '.wav', '.mp3', '.iso',
    '.stfs', '.elf', '.kip', '.pak', '.zip', '.7z', '.rar', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico',
    '.raw', '.ttf', '.otf', '.pdb', '.dll', '.exe', '.obj', '.lib', '.a', '.o',
}
# In the sold zone only what is a binary or game data is forbidden: their documentation images and test data are
# their authors'.
EXT_VENDIDA = {
    '.zed', '.xex', '.xexp', '.xbe', '.xap', '.wad', '.nxpack', '.nxidx', '.pack', '.nsp', '.xci', '.nro', '.nso', '.nca',
    '.bin', '.tdx', '.dds', '.luac', '.lua', '.lob', '.xma', '.wmv', '.bik', '.ogg', '.wav', '.mp3', '.iso',
    '.stfs', '.elf', '.kip', '.pak', '.zip', '.7z', '.rar', '.pdb', '.dll', '.exe', '.obj', '.lib', '.a', '.o',
}
CARPETAS_PROHIBIDAS = {'generated', 'obj', 'bin', 'build', 'out'}
CARPETAS_IGNORADAS = {'.git', '__pycache__'}   # the ones Python leaves when running the tools
TEXTO = {'.py', '.md', '.toml', '.json', '.txt', '.cmake', '.cpp', '.h', '.hpp', '.inc', '.hlsl', '.hlsli', '.sh',
         '.ps1', '.yml', '.yaml', '.gitignore', '.in'}

CABECERAS_JUEGO = [
    (b'XEX2', 'XEX2 (ejecutable de Xbox 360)'),
    (b'XEX1', 'XEX1 (ejecutable de Xbox 360)'),
    (b'\x1bLua', 'bytecode Lua'),
    (b'LIVE', 'STFS (paquete de Xbox 360)'),
]
CABECERAS_ARTE = [
    (b'\x89PNG', 'PNG (imagen)'),
    (b'DDS ', 'DDS (textura)'),
]

RUTAS_PERSONALES = [
    (re.compile(r'[A-Za-z]:\\\\?Users\\\\?', re.I), 'path C:\\Users'),
    (re.compile(r'[A-Za-z]:\\\\?Juegos\\\\?', re.I), 'path D:\\Juegos'),
    (re.compile('Programming' + ' projects', re.I), 'path of another project'),
    (re.compile(r'/home/[a-z0-9_.-]+/'), 'path /home/...'),
    (re.compile(r'/Users/[a-z0-9_.-]+/'), 'path /Users/...'),
]
CORREO = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
CLAVES = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'), 'private key'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), 'AWS key'),
    (re.compile(r'(?i)(password|passwd|contrase[ñn]a|secret|api[_-]?key|token|bearer|authorization)\s*[:=]\s*'
                r'["\']?[A-Za-z0-9_\-./+]{12,}'), 'string that looks like a key'),
    (re.compile(r'(?i)(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}'), 'GitHub token'),
]
HEX_LARGO = re.compile(r'\b[0-9a-fA-F]{64}\b')

# A comment that is a PowerPC instruction: the game's disassembly pasted next to the code. It counts only if it
# starts with a real mnemonic followed by a register or an address, to avoid prose that starts with "and", "or" or
# "not".
PPC_MNEMOS = set('''
b bctr bl blr bctrl blrl bdnz beq bne ble bge bgt blt beqlr bnelr ba bla bclr bdz
mflr mtlr mfctr mtcrf mtctr mfcr mtmsr mfspr mtspr mftb
li lis lwz lwzu lwzx lwzux lhz lha lhzx lbz lbzx lfs lfsx lfd lfdx lwarx lhbrx lwbrx
stw stwu stwux stwx sth sthbrx stwbrx stb stfs stfsx stfd stfdx stwcx std stdu
mr addi addis add ori oris andi andis xori xor clrlwi clrrwi slwi srwi rlwinm rlwimi
extsb extsh extlw cntlzw cmpwi cmplwi cmpw cmplw cmpd cmpl crxor crand cror creqv
fmr fmuls fadds fsubs fadd fsub fmadds fmsubs fnmsubs fmadd fdivs fdiv fneg fabs frsp
fcmpo fcmpu fres fsel fctiwz fctidz fcfid psq_l psq_st
mullw mulhw mulhd mulli divw divwu subf subfc subfic neg nop sync isync subfe adde
and or not slw srw srawi sraw dcbf dcbst dcbt dcbz icbi eieio
xxlor xxlxor xxpermdi xxspltw lvx stvx lvsl lvsr vspltw vmrghw vmrglw vperm vcmpgefp
vaddfp vmaddfp vsubfp vandc vxor vor vcmpeqfp vrefp vcmpgtfp
'''.split())
PPC_LINEA = re.compile(r'^\s*(?://+|#)\s*(?:0x[0-9A-Fa-f]{8}\s+)?([A-Za-z]{1,9})\s*(.*)$')
PPC_OPERANDO = re.compile(r'^(?:[rf]\d{1,2}\b|cr\d\b|0x[0-9A-Fa-f]+)')
PPC_AMBIGUOS = {'and', 'or', 'not'}   # ordinary words: they only count with a register list
PPC_SUELTOS = {'bctr', 'blr', 'bctrl', 'blrl', 'nop', 'sync', 'isync', 'beqlr', 'bnelr'}


def listado_powerpc(linea):
    """True if the line is a comment transcribing game instructions."""
    m = PPC_LINEA.match(linea)
    if not m:
        return False
    mnemotecnico, resto = m.group(1).lower(), m.group(2)
    if mnemotecnico not in PPC_MNEMOS:
        return False
    if mnemotecnico in PPC_SUELTOS and not resto.strip():
        return True
    if mnemotecnico in PPC_AMBIGUOS and ',' not in resto:
        return False
    return bool(PPC_OPERANDO.match(resto))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            piece = f.read(1 << 20)
            if not piece:
                break
            h.update(piece)
    return h.hexdigest()


def cabecera(ruta, solo_juego=False):
    """(name, reason) if the file starts like something of the game."""
    with open(ruta, 'rb') as f:
        d = f.read(16)
    if len(d) < 4:
        return None
    for magic, motivo in (CABECERAS_JUEGO if solo_juego else CABECERAS_JUEGO + CABECERAS_ARTE):
        if d.startswith(magic):
            # LIVE also appears inside texts: it only counts at the start and with a package header.
            if magic == b'LIVE' and not (len(d) >= 8 and d[4:6] in (b'\x00\x00', b'\x00\x01')):
                continue
            return motivo
    # Saga WAD: u16 0x1234 and then the version (0x0201 in 2009/2012, 0x0202 in 2013/2014)
    if d[0:2] == b'\x34\x12' and d[2:4] in (b'\x01\x02', b'\x02\x02'):
        return 'WAD (0x1234)'
    # Xbox 360 TDX: u16 0x0200 and a reasonable size after it
    if d[0:2] == b'\x00\x02':
        w = int.from_bytes(d[2:4], 'little')
        h = int.from_bytes(d[4:6], 'little')
        if 1 <= w <= 4096 and 1 <= h <= 4096:
            return 'TDX (0x0200)'
    return None


def referencias(raiz):
    """Original user data, including the 2012 DLC folders kept beside the project."""
    project = os.path.dirname(os.path.abspath(raiz))
    candidates = [os.path.join(project, name) for name in ('game', 'tu', 'dlc', 'nx/out/pack')]
    for name in os.listdir(project):
        if name.startswith('Magic - The Gathering'):
            candidates.append(os.path.join(project, name))
    return list(dict.fromkeys(path for path in candidates if os.path.isdir(path)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='carpeta del repositorio a revisar (por defecto, la de este script)')
    ap.add_argument('--ref', action='append', default=[], help='carpeta de referencia con datos del juego '
                                                             '(se puede repetir; por defecto game/, tu/, dlc y el pack)')
    ap.add_argument('--quiet', action='store_true', help='solo los problemas')
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)

    problemas = []
    archivos = []
    for base, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in CARPETAS_IGNORADAS)
        for d in dirs:
            if d.lower() in CARPETAS_PROHIBIDAS:
                problemas.append('forbidden folder: %s' % os.path.relpath(os.path.join(base, d), repo))
        for nombre in sorted(files):
            archivos.append(os.path.join(base, nombre))

    hashes = {}
    powerpc = 0
    for ruta in archivos:
        rel = os.path.relpath(ruta, repo).replace(os.sep, '/')
        ext = os.path.splitext(ruta)[1].lower()
        tam = os.path.getsize(ruta)
        vendido = rel.startswith(ZONA_VENDIDA)
        # A license file is named COPYING.LIB and is not a library.
        licencia = os.path.basename(ruta).lower().startswith(('copying', 'license', 'licence'))
        if ext in (EXT_VENDIDA if vendido else EXT_PROHIBIDAS) and not licencia:
            problemas.append('forbidden extension %s: %s' % (ext, rel))
        if tam > MAX_BYTES:
            problemas.append('file of %d bytes (max %d): %s' % (tam, MAX_BYTES, rel))
        motivo = cabecera(ruta, solo_juego=vendido)
        if motivo:
            problemas.append('header of %s: %s' % (motivo, rel))
        if vendido:
            # Third-party code as-is: their license headers, their images and their test data are not ours, and
            # the disassembly they bring is of their own material (the Xbox kernel, their recompiler).
            hashes[sha256(ruta)] = rel
            continue
        if ext in TEXTO or os.path.basename(ruta).lower().startswith('.git'):
            try:
                with open(ruta, encoding='utf-8') as f:
                    texto = f.read()
            except UnicodeDecodeError:
                problemas.append('text file that is not UTF-8: %s' % rel)
                texto = ''
            for patron, que in RUTAS_PERSONALES:
                if patron.search(texto):
                    problemas.append('%s: %s' % (que, rel))
            for m in CORREO.finditer(texto):
                if not m.group(0).lower().endswith(('.png', '.jpg', '.wad', '.exe')):
                    problemas.append('email "%s": %s' % (m.group(0), rel))
            for patron, que in CLAVES:
                if patron.search(texto):
                    problemas.append('%s: %s' % (que, rel))
            for numero, linea in enumerate(texto.splitlines(), 1):
                if listado_powerpc(linea):
                    problemas.append('comment with a PowerPC listing in %s:%d' % (rel, numero))
                    powerpc += 1
            # The SHA256 of the game's files are published in install/games/*.json and in the README table.
            if not rel.endswith('.json') and rel != 'README.md':
                # A fingerprint (SHA256 of a game function, quoted with its name) is acceptable; an unexplained
                # long hexadecimal string is not.
                for linea in texto.splitlines():
                    if not HEX_LARGO.search(linea):
                        continue
                    if re.search(r'(?i)sha-?256|hash|huella|fnv|crc', linea):
                        continue
                    problemas.append('long hexadecimal string (%s...) outside a JSON: %s'
                                     % (HEX_LARGO.search(linea).group(0)[:12], rel))
        hashes[sha256(ruta)] = rel

    refs = a.ref or referencias(repo)
    comparados = 0
    for carpeta in refs:
        if os.path.abspath(carpeta) == repo:
            continue
        for base, _, files in os.walk(carpeta):
            for nombre in files:
                ruta = os.path.join(base, nombre)
                h = sha256(ruta)
                comparados += 1
                if h in hashes:
                    problemas.append('same SHA256 as %s: %s' % (os.path.join(base, nombre), hashes[h]))

    total = sum(os.path.getsize(r) for r in archivos)
    if not a.quiet:
        print('check_clean: %s' % repo)
        print('  %d files, %.2f MB' % (len(archivos), total / (1 << 20)))
        print('  %d reference files compared by SHA256 (%d folders)' % (comparados, len(refs)))
        print("  %d comments with a PowerPC listing in the port's code" % powerpc)
    if problemas:
        print('')
        print('%d PROBLEM(S):' % len(problemas))
        for p in problemas:
            print('  - %s' % p)
        return 1
    print('  clean: no game data, no generated code, no personal paths')
    return 0


if __name__ == '__main__':
    sys.exit(main())
