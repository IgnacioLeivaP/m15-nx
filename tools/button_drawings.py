"""Geometric controller labels, without external art or system font files."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

AZUL = (58, 106, 200, 255)

ROJO = (206, 60, 60, 255)

ROSA = (216, 96, 176, 255)

VERDE = (66, 172, 96, 255)

GRIS = (86, 92, 104, 255)

CLARO = (240, 242, 246, 255)

def _fuente(alto):
    """Una fuente de mapa de bits de PIL, ampliada al tamano pedido (sin ficheros de fuente del sistema)."""
    return ImageFont.load_default()

def texto(txt, ancho, alto, color):
    """El texto, lo mayor que entra en ancho x alto, centrado en un lienzo de ese tamano."""
    f = _fuente(alto)
    lienzo = Image.new('RGBA', (max(1, ancho), max(1, alto)), (0, 0, 0, 0))
    caja = f.getbbox(txt)
    tw, th = caja[2] - caja[0], caja[3] - caja[1]
    if tw <= 0 or th <= 0:
        return lienzo
    # Se dibuja pequeno y se amplia: el resultado queda suave y no depende de una fuente externa.
    base = Image.new('RGBA', (tw + 2, th + 2), (0, 0, 0, 0))
    ImageDraw.Draw(base).text((1 - caja[0], 1 - caja[1]), txt, font=f, fill=color)
    f2 = min(ancho / base.width, alto / base.height)
    nuevo = base.resize((max(1, round(base.width * f2)), max(1, round(base.height * f2))), Image.LANCZOS)
    lienzo.alpha_composite(nuevo, ((ancho - nuevo.width) // 2, (alto - nuevo.height) // 2))
    return lienzo

def forma(tipo, ancho, alto, color):
    """Un dibujo propio de la forma pedida, lo mayor que entra en ancho x alto."""
    esc = 4  # se dibuja grande y se reduce: bordes suaves
    W, H = max(1, ancho) * esc, max(1, alto) * esc
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    g = max(2, min(W, H) // 10)
    if tipo == 'cruz':
        w = max(2, (W - 2 * g) // 3)
        d.rectangle((W // 2 - w // 2, g, W // 2 + w // 2, H - g), fill=color)
        d.rectangle((g, H // 2 - w // 2, W - g, H // 2 + w // 2), fill=color)
    elif tipo == 'circulo':
        d.ellipse((g, g, W - g, H - g), outline=color, width=max(2, (W - 2 * g) // 6))
    elif tipo == 'cuadrado':
        d.rectangle((g, g, W - g, H - g), outline=color, width=max(2, (W - 2 * g) // 6))
    elif tipo == 'triangulo':
        d.polygon([(W // 2, g), (W - g, H - g), (g, H - g)], outline=color, width=max(2, (W - 2 * g) // 6))
    elif tipo == 'redondo':  # el fondo de una tecla: se lee igual sobre menus claros y oscuros
        d.ellipse((0, 0, W - 1, H - 1), fill=color)
    elif tipo == 'pastilla':
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=max(2, H // 3), fill=color)
    return im.resize((max(1, ancho), max(1, alto)), Image.LANCZOS)

def tecla(txt, ancho, alto, letra=CLARO, fondo=GRIS, forma_fondo='redondo'):
    """Una tecla dibujada: el fondo (circulo o pastilla) y el texto encima."""
    im = forma(forma_fondo, ancho, alto, fondo)
    im.alpha_composite(texto(txt, int(ancho * 0.72), int(alto * 0.72), letra),
                       (int(ancho * 0.14), int(alto * 0.14)))
    return im

def tecla_forma(tipo, ancho, alto, color, fondo=GRIS):
    """Una tecla con una forma dentro (la cruz, el circulo, el cuadrado o el triangulo de PlayStation)."""
    im = forma('redondo', ancho, alto, fondo)
    dentro = int(ancho * 0.60)
    im.alpha_composite(forma(tipo, dentro, dentro, color), ((ancho - dentro) // 2, (alto - dentro) // 2))
    return im

def dibujos():
    """{estilo: {boton: imagen}} con las formas y las letras de cada estilo."""
    ps = {
        'A': tecla_forma('cruz', 64, 64, AZUL),
        'B': tecla_forma('circulo', 64, 64, ROJO),
        'X': tecla_forma('cuadrado', 64, 64, ROSA),
        'Y': tecla_forma('triangulo', 64, 64, VERDE),
        'LB': tecla('L1', 64, 64), 'RB': tecla('R1', 64, 64),
        'LT': tecla('L2', 64, 64, forma_fondo='pastilla'), 'RT': tecla('R2', 64, 64, forma_fondo='pastilla'),
        'BACK': tecla('SEL', 64, 64, forma_fondo='pastilla'), 'START': tecla('STA', 64, 64, forma_fondo='pastilla'),
    }
    switch = {
        'A': tecla('A', 64, 64), 'B': tecla('B', 64, 64),
        'X': tecla('X', 64, 64), 'Y': tecla('Y', 64, 64),
        'LB': tecla('L', 64, 64), 'RB': tecla('R', 64, 64),
        'LT': tecla('ZL', 64, 64, forma_fondo='pastilla'), 'RT': tecla('ZR', 64, 64, forma_fondo='pastilla'),
        'BACK': tecla('-', 64, 64, forma_fondo='pastilla'), 'START': tecla('+', 64, 64, forma_fondo='pastilla'),
    }
    for style in (ps, switch):
        for key in ('A', 'B', 'X', 'Y'):
            original = style[key]
            grey = ImageOps.grayscale(original).convert('RGBA')
            grey.putalpha(original.getchannel('A'))
            style[key + 'GREY'] = grey
    for style in (ps, switch):
        style['LS'] = tecla('L3', 64, 64)
        style['RS'] = tecla('R3', 64, 64)
    return {'ps': ps, 'switch': switch}

def caja(im):
    """(x0, y0, x1, y1) de lo que no es transparente."""
    a = np.array(im)[:, :, 3]
    ys, xs = np.nonzero(a > 40)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else (0, 0, im.width, im.height)

def encajar(icono, w, h):
    """El icono del mayor tamano que entra en w x h sin deformarse, centrado en un lienzo w x h."""
    f = min(w / icono.width, h / icono.height)
    nuevo = icono.resize((max(1, round(icono.width * f)), max(1, round(icono.height * f))), Image.LANCZOS)
    lienzo = Image.new('RGBA', (max(1, w), max(1, h)), (0, 0, 0, 0))
    lienzo.alpha_composite(nuevo, (((w - nuevo.width) // 2), ((h - nuevo.height) // 2)))
    return lienzo
