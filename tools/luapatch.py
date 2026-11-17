"""(Copia de duels_nx/tools/luapatch.py, 2026-11-08: respeta el orden de bytes de la cabecera, byte 6;
Magic 2015 de Xbox 360 es big-endian. Usa tools/luadis.py de este proyecto.)
Quita entradas de los menus del juego, tocando su bytecode Lua.

    python luapatch.py script.luac                      # lista las entradas
    python luapatch.py script.luac --quitar A B -o salida.luac
    python luapatch.py script.luac --saltar 0.48 6 80 -o salida.luac
    python luapatch.py script.luac --cadena 0 12 "ANDROID PC" -o salida.luac

`--saltar funcion pc destino` pone un salto en la instruccion `pc` de esa
funcion (la numeracion de luadis.py) que lleva a `destino`. Sirve para forzar
un camino que el propio script ya tiene: por ejemplo, que `user.update_sign`
tome siempre la rama de la version de Amazon, que esconde los botones de
Google. Se puede repetir.

`--cadena funcion indice texto` cambia una constante de texto de esa funcion
(la K:indice de luadis.py). Puede cambiar de largo: en el bytecode de Lua 5.1
nada guarda posiciones absolutas, cada cosa lleva delante su tamano, asi que
basta con reescribir el de la cadena. Sirve para listas de plataformas como
`lube.platform{ 'ANDROID', ... }`. Se puede repetir.

Los menus del juego son listas que se llenan una entrada por sentencia:

    table.insert(lista, carousel_button{ id = id.EXPANSION, image = ..., text = ... })

Cada sentencia deja la lista como estaba mas una entrada, y no deja nada vivo
en los registros. Asi que quitar una entrada es **saltarse su sentencia**: se
cambia su primera instruccion por un salto a la siguiente, y nada mas. El
resto del script queda identico, byte a byte; el verificador de bytecode de
Lua 5.1 lo acepta porque todas las instrucciones siguen siendo validas y el
salto cae dentro de la funcion.

El menu se construye sin esas entradas: el carrusel las reparte, las anima y
las recorre como si nunca hubieran existido.

Reconoce cualquier funcion `algo{...}` que reciba una tabla con `id = id.X`
(carousel_button, pip_button, etc.), y tambien las que se meten en la lista
sin `table.insert`, directamente en su constructor.
"""
import struct
import sys

from luadis import OPNAMES, decode, load

E = "<"  # orden de bytes del script (main lo toma de la cabecera)

OP = {name: i for i, name in enumerate(OPNAMES)}


def k(f, x):
    return f.constants[x & 0xFF] if x & 0x100 else None


def functions(f, path="0"):
    yield path, f
    for n, p in enumerate(f.protos):
        yield from functions(p, f"{path}.{n}")


def entradas(f):
    """Sentencias `table.insert(lista, constructor{ id = id.X, ... })`.

    Devuelve (inicio, fin, id): inicio es el GETGLOBAL de `table` y fin el
    CALL que hace el insert, ambos incluidos.
    """
    code = f.code
    out = []
    for pc, ins in enumerate(code):
        op, a, b, c, bx, sbx = decode(ins)
        if op != OP["GETGLOBAL"] or f.constants[bx] != "table":
            continue
        if pc + 1 >= len(code):
            continue
        op2, a2, b2, c2, _, _ = decode(code[pc + 1])
        if op2 != OP["GETTABLE"] or a2 != a or k(f, c2) != "insert":
            continue
        # El insert es el primer CALL sobre el registro `a` con 0 resultados.
        fin = None
        ident = None
        for q in range(pc + 2, min(len(code), pc + 200)):
            opq, aq, bq, cq, bxq, _ = decode(code[q])
            if ident is None and opq == OP["GETGLOBAL"] and f.constants[bxq] == "id":
                opn, an, bn, cn, _, _ = decode(code[q + 1])
                if opn == OP["GETTABLE"]:
                    ident = k(f, cn)
            if opq == OP["CALL"] and aq == a and cq == 1:
                fin = q
                break
        if fin is not None and ident is not None:
            out.append((pc, fin, ident))
    return out


def salto(desde, hasta):
    """JMP en `desde` que cae en `hasta`."""
    sbx = hasta - (desde + 1)
    return ((sbx + 131071) << 14) | OP["JMP"]


def main():
    args = sys.argv[1:]
    path = args[0]
    data = bytearray(open(path, "rb").read())
    global E
    E = "<" if data[6] else ">"
    root = load(bytes(data))
    quitar = set()
    salida = None
    if "--quitar" in args:
        i = args.index("--quitar") + 1
        while i < len(args) and not args[i].startswith("-"):
            quitar.add(args[i])
            i += 1
    if "-o" in args:
        salida = args[args.index("-o") + 1]
    saltos = []
    cadenas = []
    for i, a in enumerate(args):
        if a == "--saltar":
            saltos.append((args[i + 1], int(args[i + 2]), int(args[i + 3])))
        if a == "--cadena":
            cadenas.append((args[i + 1], int(args[i + 2]), args[i + 3]))

    todas = dict(functions(root))
    for fpath, pc, destino in saltos:
        f = todas[fpath]
        if not (0 <= pc < len(f.code) and 0 <= destino < len(f.code)):
            raise SystemExit(f"funcion {fpath}: {pc} -> {destino} se sale del codigo")
        struct.pack_into(E + "I", data, f.code_offset + 4 * pc, salto(pc, destino))
        print(f"funcion {fpath}: salto en {pc} -> {destino}")

    hechos = set()
    for fpath, f in functions(root):
        lista = entradas(f)
        if not lista:
            continue
        print(f"funcion {fpath}:")
        for inicio, fin, ident in lista:
            marca = ""
            if ident in quitar:
                struct.pack_into(E + "I", data, f.code_offset + 4 * inicio, salto(inicio, fin + 1))
                hechos.add(ident)
                marca = "   <- QUITADA"
            print(f"  {inicio:4d}-{fin:4d}  {ident}{marca}")

    faltan = quitar - hechos
    if faltan:
        print(f"no encontradas: {sorted(faltan)}")

    # Las cadenas, al final y de atras hacia delante: cambian el tamano, y asi
    # las posiciones de lo que queda por tocar siguen valiendo.
    cambios = []
    for fpath, indice, texto in cadenas:
        f = todas[fpath]
        if not (0 <= indice < len(f.constants)) or not isinstance(f.constants[indice], str):
            raise SystemExit(f"funcion {fpath}: la constante {indice} no es un texto")
        cambios.append((f.const_offsets[indice], fpath, indice, texto))
    for off, fpath, indice, texto in sorted(cambios, reverse=True):
        largo = struct.unpack_from(E + "I", data, off + 1)[0]
        nuevo = texto.encode("latin-1")
        data[off:off + 1 + 4 + largo] = (bytes([4]) + struct.pack(E + "I", len(nuevo) + 1)
                                          + nuevo + bytes([0]))
        viejo = todas[fpath].constants[indice]
        print(f"funcion {fpath}: K{indice} {viejo!r} -> {texto!r}")
    if salida:
        load(bytes(data))  # que siga siendo un script valido para el cargador
        open(salida, "wb").write(data)
        print(f"escrito {salida}")


if __name__ == "__main__":
    main()
