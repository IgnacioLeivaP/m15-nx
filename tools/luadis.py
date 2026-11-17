"""(Copia de duels_nx/tools/luadis.py, 2026-11-08: lee tambien el orden de bytes de la cabecera;
Magic 2015 de Xbox 360 es big-endian.)
Desensamblador de bytecode Lua 5.1, tal como lo guarda el juego.

    python luadis.py fichero.luac            # listado completo
    python luadis.py fichero.luac --strings  # solo las constantes de texto

El juego usa Lua 5.1 con una sola diferencia en la cabecera: el byte de
formato vale 0x5f en vez de 0. Las instrucciones son las normales. Los scripts
vienen sin informacion de depuracion (ni lineas ni nombres de variables
locales), pero las constantes —nombres de funciones globales, campos, textos—
estan todas, y con eso se entiende que hace cada funcion.
"""
import struct
import sys

OPNAMES = [
    "MOVE", "LOADK", "LOADBOOL", "LOADNIL", "GETUPVAL", "GETGLOBAL", "GETTABLE",
    "SETGLOBAL", "SETUPVAL", "SETTABLE", "NEWTABLE", "SELF", "ADD", "SUB", "MUL",
    "DIV", "MOD", "POW", "UNM", "NOT", "LEN", "CONCAT", "JMP", "EQ", "LT", "LE",
    "TEST", "TESTSET", "CALL", "TAILCALL", "RETURN", "FORLOOP", "FORPREP",
    "TFORLOOP", "SETLIST", "CLOSE", "CLOSURE", "VARARG",
]
# Formato de cada instruccion: iABC, iABx o iAsBx.
ABX = {"LOADK", "GETGLOBAL", "SETGLOBAL", "CLOSURE"}
ASBX = {"JMP", "FORLOOP", "FORPREP"}


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.e = "<" if len(data) > 6 and data[6] else ">"  # byte 6: 1 little, 0 big

    def byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def int(self):
        v = struct.unpack_from(self.e + "i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def size_t(self):
        v = struct.unpack_from(self.e + "I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def number(self):
        v = struct.unpack_from(self.e + "d", self.data, self.pos)[0]
        self.pos += 8
        return v

    def string(self):
        n = self.size_t()
        if n == 0:
            return None
        s = self.data[self.pos:self.pos + n - 1]  # sin el cero final
        self.pos += n
        return s.decode("latin-1")


class Function:
    """Un prototipo: codigo, constantes y funciones anidadas."""

    def __init__(self, r, parent_source="=?"):
        self.offset = r.pos
        self.source = r.string() or parent_source
        self.linedefined = r.int()
        self.lastlinedefined = r.int()
        self.nups = r.byte()
        self.numparams = r.byte()
        self.is_vararg = r.byte()
        self.maxstacksize = r.byte()
        n = r.int()
        self.code_offset = r.pos
        self.code = [struct.unpack_from(r.e + "I", r.data, r.pos + 4 * i)[0] for i in range(n)]
        r.pos += 4 * n
        n = r.int()
        self.constants = []
        self.const_offsets = []  # donde empieza cada una (para luapatch --cadena)
        for _ in range(n):
            self.const_offsets.append(r.pos)
            t = r.byte()
            if t == 0:
                self.constants.append(None)
            elif t == 1:
                self.constants.append(bool(r.byte()))
            elif t == 3:
                self.constants.append(r.number())
            elif t == 4:
                self.constants.append(r.string())
            else:
                raise ValueError(f"constante de tipo {t} en {r.pos:#x}")
        n = r.int()
        self.protos = [Function(r, self.source) for _ in range(n)]
        # Informacion de depuracion (vacia en los scripts del juego).
        n = r.int()
        self.lineinfo = [r.int() for _ in range(n)]
        n = r.int()
        self.locvars = []
        for _ in range(n):
            self.locvars.append((r.string(), r.int(), r.int()))
        n = r.int()
        self.upvalues = [r.string() for _ in range(n)]
        self.end = r.pos


def load(data):
    if data[:4] != b"\x1bLua" or data[4] != 0x51:
        raise ValueError("no es bytecode de Lua 5.1")
    r = Reader(data)
    r.pos = 12
    return Function(r)


def rk(f, x):
    if x & 0x100:
        return "K:" + repr(f.constants[x & 0xFF])
    return f"R{x}"


def decode(i):
    op = i & 0x3F
    a = (i >> 6) & 0xFF
    c = (i >> 14) & 0x1FF
    b = (i >> 23) & 0x1FF
    bx = i >> 14
    return op, a, b, c, bx, bx - 131071


def describe(f, pc, i):
    op, a, b, c, bx, sbx = decode(i)
    name = OPNAMES[op] if op < len(OPNAMES) else f"OP{op}"
    if name in ABX:
        text = f"{name:9s} R{a} {bx}"
        if name in ("LOADK", "GETGLOBAL", "SETGLOBAL"):
            text += f"    ; {f.constants[bx]!r}"
        else:
            text += f"    ; funcion #{bx}"
    elif name in ASBX:
        text = f"{name:9s} R{a} {sbx:+d}    ; -> {pc + 1 + sbx}"
    else:
        text = f"{name:9s} R{a} {b} {c}"
        if name in ("GETTABLE", "SELF"):
            text += f"    ; [{rk(f, c)}]"
        elif name == "SETTABLE":
            text += f"    ; [{rk(f, b)}] = {rk(f, c)}"
        elif name in ("EQ", "LT", "LE", "ADD", "SUB", "MUL", "DIV", "MOD", "POW"):
            text += f"    ; {rk(f, b)} {rk(f, c)}"
        elif name == "CALL":
            text += f"    ; {b - 1 if b else 'var'} args, {c - 1 if c else 'var'} resultados"
    return text


def dump(f, path="0", depth=0, only_strings=False):
    pad = "  " * depth
    if only_strings:
        textos = [k for k in f.constants if isinstance(k, str)]
        print(f"{pad}funcion {path}: {textos}")
    else:
        print(f"{pad}; funcion {path}  params={f.numparams} vararg={f.is_vararg} "
              f"upvalues={f.nups} pila={f.maxstacksize} instrucciones={len(f.code)} "
              f"(codigo en {f.code_offset:#x})")
        for pc, ins in enumerate(f.code):
            print(f"{pad}  {pc:4d}  {describe(f, pc, ins)}")
    for n, p in enumerate(f.protos):
        dump(p, f"{path}.{n}", depth + 1, only_strings)


def main():
    data = open(sys.argv[1], "rb").read()
    f = load(data)
    dump(f, only_strings="--strings" in sys.argv)


if __name__ == "__main__":
    main()
