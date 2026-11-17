"""Generate Magic 2015 Switch glyph overrides from user-supplied converted textures."""
import io
import os
import struct
import sys

import numpy as np
from PIL import Image

import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import button_drawings as iconos12
ORIG = ''
SALIDA = ''
HOJA = 'F1C436C1BEA8F4A9'
GRANDES = '1DB9701401F62775'
# (fila, columna) en la cuadricula de 12x12 de la hoja (work/texdump_png/_botones.png).
CASILLAS = {'LB': (6, 10), 'RB': (6, 11), 'LT': (7, 0), 'RT': (7, 1), 'A': (7, 2), 'B': (7, 3), 'X': (7, 4),
            'Y': (7, 5)}


def caja(im, umbral=40):
    a = np.array(im)[:, :, 3]
    ys, xs = np.nonzero(a > umbral)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None


def hoja_simbolos(d):
    datos = open(os.path.join(ORIG, HOJA + '_256x256_f20_b4_s1.bin'), 'rb').read()
    hoja = Image.frombytes('RGBA', (256, 256), datos)
    for boton, (fila, col) in CASILLAS.items():
        x0, x1 = round(col * 256 / 12), round((col + 1) * 256 / 12)
        y0, y1 = round(fila * 256 / 12), round((fila + 1) * 256 / 12)
        celda = hoja.crop((x0 + 1, y0 + 1, x1 - 1, y1 - 1))
        c = caja(celda)
        if not c:
            raise ValueError('Empty button cell: ' + boton)
            continue
        bx0, by0, bx1, by1 = c[0] + x0 + 1, c[1] + y0 + 1, c[2] + x0 + 1, c[3] + y0 + 1
        hoja.paste((0, 0, 0, 0), (bx0, by0, bx1, by1))
        hoja.alpha_composite(iconos12.encajar(d[boton], bx1 - bx0, by1 - by0), (bx0, by0))
    return hoja


def dds_a_imagen(datos, w, h):
    hdr = struct.pack('<4sIIIIIII44x', b'DDS ', 124, 0x81007, h, w, len(datos), 0, 1)
    pf = struct.pack('<II4sIIIII', 32, 0x4, b'DXT5', 0, 0, 0, 0, 0)
    caps = struct.pack('<IIIII', 0x1000, 0, 0, 0, 0)
    return Image.open(io.BytesIO(hdr + pf + caps + datos)).convert('RGBA')


def bc3(im):
    b = io.BytesIO()
    im.save(b, format='DDS', pixel_format='DXT5')
    datos = b.getvalue()
    return datos[128:]  # cabecera DDS sin DX10


def botones_grandes(d):
    datos = open(os.path.join(ORIG, GRANDES + '_128x128_f61_b16_s4.bin'), 'rb').read()
    orig = dds_a_imagen(datos, 128, 128)
    nueva = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    for nombre, (fila, col) in {'A': (0, 0), 'AGREY': (0, 1), 'B': (1, 0), 'BGREY': (1, 1)}.items():
        x, y = col * 64, fila * 64
        c = caja(orig.crop((x, y, x + 64, y + 64))) or (2, 2, 62, 62)
        nueva.alpha_composite(iconos12.encajar(d[nombre], c[2] - c[0], c[3] - c[1]), (x + c[0], y + c[1]))
    return nueva


def main():
    global ORIG, SALIDA
    ap = argparse.ArgumentParser(description='Generate Switch texture overrides from your own runtime texture dumps')
    ap.add_argument('--source', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    ORIG = os.path.abspath(args.source)
    SALIDA = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    d = iconos12.dibujos()['switch']
    hoja = hoja_simbolos(d)
    grandes = botones_grandes(d)
    entradas = [(int(HOJA, 16), hoja.tobytes(), 256, 256), (int(GRANDES, 16), bc3(grandes), 128, 128)]
    assert len(entradas[1][1]) == 128 * 128, len(entradas[1][1])
    with open(SALIDA, 'wb') as f:
        f.write(b'MT15' + struct.pack('<I', len(entradas)))
        for clave, datos, w, h in entradas:
            f.write(struct.pack('<QIHH', clave, len(datos), w, h) + datos)
    print(SALIDA, os.path.getsize(SALIDA), 'bytes')


if __name__ == '__main__':
    main()
