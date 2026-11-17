#!/usr/bin/env python3
"""Build the external deko3d shader package and a release cache table from user-provided game shaders."""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import renut_port_shaders  # noqa: E402


def package(glsl_dir, names, out_dir):
    """tools/deko3d_shader_package.py over the given shaders only."""
    os.makedirs(out_dir, exist_ok=True)
    src = os.path.join(out_dir, 'glsl')
    shutil.rmtree(src, ignore_errors=True)
    os.makedirs(src)
    for n in names:
        shutil.copyfile(os.path.join(glsl_dir, n), os.path.join(src, n))
    subprocess.run([sys.executable, '-P' if sys.version_info >= (3, 11) else '-I', os.path.join(ROOT, 'tools', 'deko3d_shader_package.py'), '--glsl', src,
                    '--out', out_dir], check=True)
    shutil.rmtree(src)


def strip_spirv(text):
    """shader_cache_switch.cpp without the SPIR-V: the assembler's .incbin goes, its sizes are 0, and every entry's
    SPIR-V offset and size (the 4th and 5th numbers of g_shaderCacheEntries' lines) are 0."""
    text, n = re.subn(r'// banjo-nx: the compressed SPIR-V.*?\.previous\\n"\);\n',
                      'const uint8_t g_compressedSpirvCache[] = {0};  // peggle2-nx: no SPIR-V (deko3d reads none)\n',
                      text, flags=re.S)
    if n != 1:
        sys.exit('renut_release_shaders: the SPIR-V block of shader_cache_switch.cpp not found')
    text = re.sub(r'(g_spirvCache(?:Compressed|Decompressed)Size\s*=\s*)\d+', r'\g<1>0', text)

    def entry(m):
        fields = m.group(2).split(', ')
        fields[3] = fields[4] = '0'
        return m.group(1) + ', '.join(fields)
    text = re.sub(r'^(\t\{ )(0x[0-9A-F]+, \d+, \d+, \d+, \d+)', entry, text, flags=re.M)
    return text


def stored_in_image(path):
    """The shaders stored in the decompressed default.xex image, as GLSL file names: the containers the web installer
    finds (tools/extract_stored_shaders.py's scan, the installer's lib/containers.js), named by the XXH3 of the
    container like the translated shaders."""
    import struct
    import xxhash
    image = open(path, 'rb').read()
    names = set()
    for off in range(0, len(image) - 12, 4):
        magic = struct.unpack_from('>I', image, off)[0]
        if magic not in (0x102A1101, 0x102A1100):
            continue
        header, ucode = struct.unpack_from('>II', image, off + 4)
        if header < 12 or header > 1 << 16 or ucode == 0 or ucode > 1 << 20 or ucode % 4 or off + header + ucode > len(image):
            continue
        h = xxhash.xxh3_64_intdigest(image[off:off + header + ucode])
        names.add(f'{"vs" if magic == 0x102A1101 else "ps"}_{h:016X}.glsl')
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glsl', default=os.path.join(ROOT, 'out', 'deko3d_release', 'glsl_opt'))
    ap.add_argument('--cache', default=os.path.join(ROOT, 'out', 'renut_switch', 'shader_cache_switch.cpp'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'out', 'renut_switch_release'))
    # bejeweled3-nx (2026-10-22, the user's choice for the release): the shaders the game compiles while it runs (D3DX
    # effects: 18 of Bejeweled 3's 89, in no file a browser can read) are built into the NRO; the web installer makes
    # the ones stored in default.xex. With --image, every translated shader not stored in the image is built in.
    ap.add_argument('--image', default='', help='the decompressed default.xex image (out/default_image.bin)')
    a = ap.parse_args()
    all_names = sorted(f for f in os.listdir(a.glsl) if re.fullmatch(r'(vs|ps)_[0-9A-F]{16}\.glsl', f))
    port = set(all_names) - stored_in_image(a.image) if a.image else set()  # peggle1-nx: no port shaders
    missing = port - set(all_names)
    if missing:
        sys.exit(f'renut_release_shaders: {sorted(missing)} not in {a.glsl}')
    stored = [n for n in all_names if n not in port]
    if port:
        package(a.glsl, sorted(port), a.out)
    package(a.glsl, stored, os.path.join(a.out, 'sd'))
    os.remove(os.path.join(a.out, 'sd', 'deko3d_glsl_switch.cpp'))  # the installer's file is never built in
    text = open(a.cache, encoding='utf-8').read()
    with open(os.path.join(a.out, 'shader_cache_switch.cpp'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(strip_spirv(text))
    print(f'renut_release_shaders: built in {len(port)} port shaders, beside the NRO {len(stored)} stored ones '
          f'({", ".join(stored)}) -> {a.out}')


if __name__ == '__main__':
    main()
