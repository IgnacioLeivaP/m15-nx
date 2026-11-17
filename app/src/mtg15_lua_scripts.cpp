// The game's Lua scripts (LUBE menus, .LOB in Data_Core.wad), replaced by our own text versions.
//
// sub_823AC9F0 is the game's script loader (2026-11-08): r3 = the script's object, r4 = lua_State*. The object holds
// +0 the chunk name (char*), +8 the data and +0xC its size; the loader hands {data, size} to luaD_protectedparser
// (sub_8225C4B8) through its reader sub_823AC5E0. f_parser (sub_8226BAF8) takes text chunks too (luaY_parser,
// sub_822A2E48), so a replacement can be plain Lua.
//
// A replacement is <exe folder>/lua/<module>.lua (Lua text) or <module>.luac (the game bytecode patched by
// tools/luapatch.py), for any module that has one (the chunk name is the module, "menus.help_options.settings.basic [a] [b]")
// (BASIC.LOB -> lua/menus.help_options.settings.basic.lua). For the call the object's data and size point at a
// copy in guest memory; they are restored afterwards (the object owns its own buffer).
// mtg15_lua_log = true logs every chunk name the loader sees (once each).

#include <algorithm>
#include <csetjmp>
#include <memory>
#include <vector>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <set>
#include <string>
#include <unordered_map>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/hook.h>
#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>

#include "mtg15_dlc.h"
#include "mtg15_opciones.h"

REXCVAR_DEFINE_BOOL(mtg15_lua_catch_errors, true, "Mtg15",
                    "Lua errors caught as on the console (luaD_rawrunprotected / luaD_throw with setjmp and longjmp) "
                    "instead of ending the game (the runtime cannot unwind the C++ exception the game throws)");
// M16 fase 7 (2026-11-13): the layer's traces are luaD_throw too and used up the 40, hiding the errors after them.
REXCVAR_DEFINE_INT32(mtg15_lua_errors_max, 40, "Mtg15", "Lua errors written to the log (luaD_throw); later ones are not");
REXCVAR_DEFINE_BOOL(mtg15_lua_log, false, "Mtg15", "Log the name of every Lua script the game loads (once each)");
REXCVAR_DEFINE_BOOL(mtg15_lua_probe, true, "Mtg15",
                    "Note the first calls of the script loader the port hooks (proof that the address is the loader)");
REXCVAR_DEFINE_BOOL(mtg15_lua_dump, false, "Mtg15",
                    "Write every Lua chunk the game loads to <exe folder>/lua_dump/NNN.luac, to patch it offline");

namespace {

uint8_t* Guest(uint32_t address) {
  return address ? rex::system::kernel_state()->memory()->TranslateVirtual<uint8_t*>(address) : nullptr;
}
// Guest(address) only when the `size` bytes from it are mapped and readable (2026-11-13, M16 fase 5f): the error
// logger below follows pointers out of a Lua stack it cannot trust (a CallInfo whose func slot is not a function, a
// stale coroutine frame), and an unmapped read there ended the game (mtg15.exe+0x106C5, +0x107A2; guest 0x67657467).
uint8_t* GuestR(uint32_t address, uint32_t size) {
  if (address < 0x10000u || size == 0 || uint64_t(address) + size > 0x100000000ull) return nullptr;
  auto* memory = rex::system::kernel_state()->memory();
  auto* heap = memory->LookupHeap(address);
  if (!heap) return nullptr;
  const auto access = heap->QueryRangeAccess(address, address + size - 1);
  if ((uint32_t(access) & uint32_t(rex::memory::PageAccess::kReadOnly)) == 0) return nullptr;
  return memory->TranslateVirtual<uint8_t*>(address);
}
uint32_t Be32(const uint8_t* p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; }
void SetBe32(uint8_t* p, uint32_t v) {
  p[0] = uint8_t(v >> 24);
  p[1] = uint8_t(v >> 16);
  p[2] = uint8_t(v >> 8);
  p[3] = uint8_t(v);
}

// Is the guest address mapped for reading? The probe below follows words of the loader's object, and an unmapped
// one would fault the host.
bool Readable(uint32_t address, uint32_t size) {
  auto* kernel = rex::system::kernel_state();
  auto* memory = kernel ? kernel->memory() : nullptr;
  auto* heap = memory ? memory->LookupHeap(address) : nullptr;
  return heap && heap->QueryRangeAccess(address, address + size - 1) != rex::memory::PageAccess::kNoAccess;
}

bool IsLuaHeader(uint32_t address);

// The loader's object, as the probe of 2026-11-11 found it (the 2014's layout is not this one):
//   +0  the chunk (a Lua 5.1 binary)   +4  its size   +8  the name, as the game's std::string (16-byte small-string
// buffer: the text inline, or a pointer to it for longer names)   +0x18/+0x1C  that string's size and capacity.
// The 2014 has the name at +0 and the chunk at +8/+0xC, so that is the fallback.
struct Script {
  std::string name;
  uint32_t data = 0;
  uint32_t size = 0;
};

Script ReadObject(uint32_t object) {
  Script s;
  const uint8_t* o = Guest(object);
  if (!o) return s;
  const uint32_t data = Be32(o), size = Be32(o + 4);
  if (IsLuaHeader(data)) {
    s.data = data;
    s.size = size;
  } else {
    s.data = Be32(o + 8);
    s.size = Be32(o + 0xC);
  }
  const uint32_t field = Be32(o + 8);
  const uint8_t* text = o + 8;  // the small-string buffer, inline
  if (field >= 0x40000000u && field < 0x60000000u && Readable(field, 2)) text = Guest(field);
  for (int i = 0; text && i < 96; ++i) {
    const char c = char(text[i]);
    if (!c) break;
    s.name += (c >= 32 && c < 127) ? c : '?';
  }
  return s;
}

inline bool IsLuaHeader(uint32_t address) {
  const uint8_t* b = Readable(address, 16) ? Guest(address) : nullptr;
  return b && b[0] == 0x1B && b[1] == 'L' && b[2] == 'u' && b[3] == 'a';
}

// A module name as a file name: the 2015's names are paths ("system/auxiliary"), the file lives flat in lua/.
std::string Safe(const std::string& module) {
  std::string out;
  for (const char c : module) out += (c == '/' || c == '\\') ? '_' : c;
  return out;
}

// "menus.help_options.settings.basic [407D1848] [421878C0]" -> "menus.help_options.settings.basic": the 2014's chunk
// name is the Lua module's, then two addresses. The 2015's names look like file paths ("system/auxiliary").
std::string Module(const std::string& name) {
  std::string m = name.substr(0, name.find(' '));
  for (char& c : m) c = char(std::tolower(uint8_t(c)));
  return m;
}

// A C string in guest memory, as a chunk name arrives in lua_load.
std::string ReadCString(uint32_t address) {
  std::string out;
  const uint8_t* p = (address && Readable(address, 1)) ? Guest(address) : nullptr;
  for (int i = 0; p && i < 160; ++i) {
    const char c = char(p[i]);
    if (!c) break;
    out += (c >= 32 && c < 127) ? c : '?';
  }
  return out;
}

// <exe folder>/lua_dump/NNN_<module>.luac, one per distinct chunk (a mapped window; tools/mods15.py cuts it with
// tools/luadis.py, which walks the chunk to its end).
std::string Dump(const Script& s) {
  static std::set<uint32_t> seen;
  if (!s.data || !seen.insert(s.data).second) return {};
  std::string safe;
  for (const char c : Module(s.name)) safe += (c == '.') ? c : ((c == '/' || c == '\\') ? '_' : c);
  const auto folder = rex::filesystem::GetExecutableFolder() / "lua_dump";
  std::error_code ec;
  std::filesystem::create_directories(folder, ec);
  const auto path = folder / fmt::format("{:03}_{}.luac", seen.size() - 1, safe);
  const uint8_t* b = Guest(s.data);
  if (!b) return {};
  uint32_t window = 4096;  // the game's chunks are far smaller; the window only has to hold one
  while (window < (1u << 17) && Readable(s.data, window * 2)) window *= 2;
  std::ofstream out(path, std::ios::binary);
  out.write(reinterpret_cast<const char*>(b), window);
  REXLOG_INFO("[lua] dumped {} ({} bytes read, chunk {} bytes)", path.filename().string(), window, s.size);
  return path.filename().string();
}

// What our Settings menu needs from the port, as Lua put before its text: the options in use and the new rows'
// labels in the game's language (the game's text tables have none for them).
std::string SettingsHeader() {
  const std::string current = mtg15::opciones::CurrentLanguage();
  std::string chosen = mtg15::opciones::Get("idioma");
  if (chosen.empty()) chosen = current;
  // Lua text read as Latin-1: accents as \ddd escapes.
  struct Labels {
    const char* lang; const char* idioma; const char* botones; const char* reinicio; const char* dlc; const char* ninguno;
  };
  static const Labels kLabels[] = {
      {"es", "Idioma", "Iconos de botones", "Idioma e iconos cambian al volver a abrir el juego", "Contenido descargable",
       "Ninguno"},
      {"fr", "Langue", "Ic\\244nes des boutons", "Langue et icones au prochain lancement du jeu",
       "Contenu t\\233l\\233chargeable", "Aucun"},
      {"de", "Sprache", "Tastensymbole", "Sprache und Symbole wechseln beim n\\228chsten Spielstart", "Zusatzinhalte",
       "Keine"},
      {"it", "Lingua", "Icone dei pulsanti", "Lingua e icone cambiano al prossimo avvio del gioco", "Contenuti scaricabili",
       "Nessuno"},
      {"en", "Language", "Button icons", "Language and button icons change after restarting the game", "Downloadable content",
       "None"},
  };
  const Labels* l = &kLabels[4];
  for (const Labels& k : kLabels)
    if (current == k.lang) l = &k;
  // DLC check (the user's request, 2026-11-09): "OK" and the packs found in the content store.
  std::string packs;
  for (int n : mtg15::dlc::InstalledPacks()) packs += (packs.empty() ? "" : ", ") + std::to_string(n);
  const std::string dlc = packs.empty() ? std::string(l->ninguno) : "Instalados: " + packs + " (sin verificar)";
  return std::string("local MTG15 = { idioma = '") + chosen + "', estilo = '" + mtg15::opciones::ButtonStyle() +
         "', txt_idioma = '" + l->idioma + "', txt_botones = '" + l->botones + "', txt_reinicio = '" + l->reinicio +
         "', txt_dlc = '" + l->dlc + "', dlc = '" + dlc + "' }\n";
}

struct Replacement {
  uint32_t guest = 0;  // the text in guest memory (kept for the whole run)
  uint32_t size = 0;
};

std::mutex g_mutex;
std::set<std::string> g_logged;
std::unordered_map<std::string, Replacement> g_loaded;  // by chunk name; size 0: no file

// The script's replacement, read once.
const Replacement* Find(const std::string& name) {
  const std::string module = Module(name);
  if (module.empty()) return nullptr;
  auto it = g_loaded.find(module);
  if (it == g_loaded.end()) {
    Replacement r;
    // Lua text (.lua) or the game's bytecode patched by tools/luapatch.py (.luac); f_parser takes both.
    const auto folder = rex::filesystem::GetExecutableFolder() / "lua";
    auto path = folder / (Safe(module) + ".lua");
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec)) path = folder / (Safe(module) + ".luac");
    std::ifstream in(path, std::ios::binary);
    if (in) {
      std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
      if (module == "menus.help_options.settings.basic" || module == "menus/help_options/settings/basic")
        text = SettingsHeader() + text;
      if (!text.empty()) {
        auto* memory = rex::system::kernel_state()->memory();
        r.guest = memory->SystemHeapAlloc(uint32_t(text.size()), 16);
        if (uint8_t* p = Guest(r.guest)) {
          std::memcpy(p, text.data(), text.size());
          r.size = uint32_t(text.size());
          REXLOG_INFO("[lua] {} replaced by {} ({} bytes)", name, path.string(), text.size());
        }
      }
    }
    it = g_loaded.emplace(module, r).first;
  }
  return it->second.size ? &it->second : nullptr;
}

}  // namespace

// MAGIC 2015 (2026-11-12): sub_82BC69F0 serves only "system/auxiliary" — the menus come in through another caller —
// so the port also hooks lua_load, which every script load goes through:
//   int lua_load(lua_State* L, lua_Reader reader, void* data, const char* chunkname)   r3 / r4 / r5 / r6
// The game's one-shot reader hands Lua { char* chunk; size_t size; } at `data` (reader sub_82BC5E30: *size = data[1],
// returns data[0], then data[1] = 0), so a replacement is the same swap the loader hook does, one level lower and for
// every chunk. Only a buffer that starts with the Lua signature is replaced (a text chunk of the game's own is left
// alone), and the pair is put back after the call.
extern "C" REX_FUNC(__imp__sub_82407A68);
REX_HOOK_RAW(sub_82407A68) {  // int lua_load(lua_State*, lua_Reader, void*, const char*)
  const uint32_t data = ctx.r5.u32;
  const std::string name = ReadCString(ctx.r6.u32);
  const uint8_t* pair = (data && Readable(data, 8)) ? Guest(data) : nullptr;
  const uint32_t chunk = pair ? Be32(pair) : 0;
  const uint32_t size = pair ? Be32(pair + 4) : 0;
  if (!name.empty()) {
    static std::set<std::string> seen;
    std::lock_guard<std::mutex> lock(g_mutex);
    if (REXCVAR_GET(mtg15_lua_log) && seen.insert(name).second) {
      REXLOG_INFO("[lua] lua_load '{}' ({} bytes{})", name, size, IsLuaHeader(chunk) ? ", bytecode" : "");
    }
  }
  const Replacement* replacement = nullptr;
  if (IsLuaHeader(chunk)) {
    std::lock_guard<std::mutex> lock(g_mutex);
    replacement = Find(name);
  }
  if (!replacement) {
    __imp__sub_82407A68(ctx, base);
    return;
  }
  uint8_t* m = Guest(data);
  SetBe32(m, replacement->guest);
  SetBe32(m + 4, replacement->size);
  __imp__sub_82407A68(ctx, base);
  const int32_t result = int32_t(ctx.r3.u32);
  SetBe32(m, chunk);
  SetBe32(m + 4, size);
  REXLOG_INFO("[lua] {}: the replacement was loaded, result {}", name, result);
}

// MAGIC 2015: el cargador de scripts del 2015 es sub_82BC69F0. Localizado por la forma de la funcion del 2014
// (sub_82AB9158): la ventana de instrucciones de 26 palabras es unica en la imagen del 2015 (tools/tu_global.py con
// la imagen del 2014 como base: los dos juegos enlazan el mismo XDK). El mapa 2013->2015 daba 82BC6980, que es la
// funcion anterior: no servia. La funcion se agrego a [functions] de overrides.toml para que el generador la emita.
extern "C" REX_FUNC(__imp__sub_82BC69F0);
REX_HOOK_RAW(sub_82BC69F0) {  // int (ScriptObject*, lua_State*)
  const uint32_t object = ctx.r3.u32;
  const Script script = ReadObject(object);
  const std::string& name = script.name;
  // Is this address the script loader at all? The runs of 2026-11-10 never logged a chunk name with the log switched
  // on; the probe of 2026-11-11 found the object's layout (ReadObject) and this note stays as proof of the address.
  {
    static int probes = 0;
    if (REXCVAR_GET(mtg15_lua_probe) && probes < 8) {
      ++probes;
      REXLOG_INFO("[lua] loader probe 0x{:08X}: chunk '{}', {} bytes", object, name, script.size);
    }
  }
  if (REXCVAR_GET(mtg15_lua_dump)) Dump(script);
  const Replacement* replacement = nullptr;
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (REXCVAR_GET(mtg15_lua_log) && g_logged.insert(name).second) {
      REXLOG_INFO("[lua] load '{}' ({} bytes)", name, script.size);
    }
    if (!name.empty()) replacement = Find(name);
  }
  uint8_t* o = replacement ? Guest(object) : nullptr;
  if (!o) {
    __imp__sub_82BC69F0(ctx, base);
    return;
  }
  // The object's chunk pointer and size, wherever this build keeps them (ReadObject found them).
  const uint32_t data_at = (Be32(o) == script.data) ? 0 : 8;
  const uint32_t data = Be32(o + data_at), size = Be32(o + data_at + 4);
  SetBe32(o + data_at, replacement->guest);
  SetBe32(o + data_at + 4, replacement->size);
  __imp__sub_82BC69F0(ctx, base);
  SetBe32(o + data_at, data);
  SetBe32(o + data_at + 4, size);
  REXLOG_INFO("[lua] {}: loaded the replacement, result {}", name, int32_t(ctx.r3.u32));
}

// Lua errors (2026-11-09). The game's Lua is built as C++: luaD_rawrunprotected (sub_8226AA90) is
//   lj.previous = L->errorJmp (+0x70); lj.status (+8) = 0; L->errorJmp = &lj; try { f(L, ud); } catch (...) {}
//   L->errorJmp = lj.previous; return lj.status;
// and luaD_throw sets L->errorJmp->status and throws lua_longjmp*. The runtime cannot unwind a guest C++ exception
// (the SDK's HandleCppException stops), so every Lua error ended the game; on the console a pcall catches it and the
// game goes on. Here the pair is done the way Lua built as C does it: luaD_rawrunprotected keeps a host jmp_buf for its
// lua_longjmp (made on the guest stack below the caller's frame) and luaD_throw longjmps to it. The guest frames in
// between are left as they are (their nonvolatile registers are host locals, gone with them); the guest state at the
// call is restored from a copy of the context.
namespace {
struct ProtectedCall {
  uint32_t lj = 0;
  std::jmp_buf buf;
};
thread_local std::vector<ProtectedCall*> g_protected;
uint32_t g_errors_logged = 0;
}  // namespace

extern "C" REX_FUNC(__imp__sub_8240C7C0);
REX_HOOK_RAW(sub_8240C7C0) {  // int luaD_rawrunprotected(lua_State* L, Pfunc f, void* ud)
  if (!REXCVAR_GET(mtg15_lua_catch_errors)) {
    __imp__sub_8240C7C0(ctx, base);
    return;
  }
  const uint32_t L = ctx.r3.u32, f = ctx.r4.u32, ud = ctx.r5.u32, r1 = ctx.r1.u32;
  uint8_t* const l = Guest(L);
  const uint32_t lj = (r1 - 0x40) & ~0xFu;
  uint8_t* const j = Guest(lj);
  PPCFunc* const fn = rex::runtime::ResolveIndirectFunction(f);
  if (!l || !j || !fn) {
    __imp__sub_8240C7C0(ctx, base);
    return;
  }
  SetBe32(j + 0, Be32(l + 0x70));  // lj.previous
  SetBe32(j + 4, 0);
  SetBe32(j + 8, 0);  // lj.status
  SetBe32(l + 0x70, lj);
  const std::unique_ptr<PPCContext> saved = std::make_unique<PPCContext>(ctx);
  ProtectedCall call;
  call.lj = lj;
  g_protected.push_back(&call);
  if (setjmp(call.buf) == 0) {
    ctx.r1.u32 = lj;  // the callee's frame goes below the lua_longjmp
    ctx.r3.u64 = L;
    ctx.r4.u64 = ud;
    fn(ctx, base);
  } else {
    ctx = *saved;  // the guest state at the call (luaD_throw jumped here)
  }
  g_protected.pop_back();
  SetBe32(l + 0x70, Be32(j + 0));
  ctx.r1.u32 = r1;
  ctx.r3.u64 = Be32(j + 8);
}

// luaD_throw (sub_8226A988, 2026-11-09): r3 = lua_State*, r4 = the error code. The game's Lua is built as C++: an
// error is a `throw lua_longjmp*`, which the runtime cannot unwind (the SDK's HandleCppException stops), so every Lua
// error ends the game. The message is logged first: L->top (+8) - 1 is a TValue of 16 bytes (value +0, type +8; a
// string, type 4, is a TString* whose text starts at +16 and whose length is at +12).
extern "C" REX_FUNC(__imp__sub_8240C6B8);
REX_HOOK_RAW(sub_8240C6B8) {
  const uint32_t L = ctx.r3.u32, code = ctx.r4.u32;
  std::string message = "(not a string)";
  if (const uint8_t* l = GuestR(L, 0x74)) {
    const uint32_t top = Be32(l + 8);
    if (const uint8_t* tv = GuestR(top - 16, 16)) {
      if (Be32(tv + 8) == 4) {
        if (const uint8_t* ts = GuestR(Be32(tv), 16)) {
          const uint32_t len = std::min<uint32_t>(Be32(ts + 12), 400);
          if (GuestR(Be32(tv), 16 + len)) message.assign(reinterpret_cast<const char*>(ts + 16), len);
        }
      }
    }
  }
  const bool log = int64_t(g_errors_logged) < int64_t(REXCVAR_GET(mtg15_lua_errors_max));
  if (log) {
    ++g_errors_logged;
    REXLOG_ERROR("[lua] error {} (luaD_throw): {}", code, message);
  }
  // Where (the scripts carry no debug info): the running Lua functions from L->ci (+0x14; CallInfo 0x18 bytes, func
  // at +4) down, each with its first text constants, and the instruction that failed (L->savedpc, +0x18). Lua 5.1:
  // LClosure: isC +6, p +16; Proto: k +8, code +12, sizek +40, sizecode +44; instruction: op 6 bits, A 8, C 9, B 9.
  // Every pointer is checked with GuestR (mapped and readable) and a CallInfo's func slot must hold a function
  // (TValue type +8 == 6, LUA_TFUNCTION) before it is read as a closure: the walk used to take any value there.
  if (const uint8_t* l = log ? GuestR(L, 0x74) : nullptr) {
    auto string_of = [](const uint8_t* tv) -> std::string {
      if (!tv || Be32(tv + 8) != 4) return {};
      const uint8_t* ts = GuestR(Be32(tv), 16);
      if (!ts) return {};
      const uint32_t len = std::min<uint32_t>(Be32(ts + 12), 60);
      return GuestR(Be32(tv), 16 + len) ? std::string(reinterpret_cast<const char*>(ts + 16), len) : "";
    };
    uint32_t ci = Be32(l + 0x14);
    const uint32_t base_ci = Be32(l + 0x28);
    uint32_t pc = Be32(l + 0x18);
    for (int depth = 0; depth < 6 && ci >= base_ci && ci; ++depth, ci -= 0x18) {
      const uint8_t* c = GuestR(ci, 0x18);
      if (!c) break;
      const uint8_t* func = GuestR(Be32(c + 4), 16);
      if (!func || Be32(func + 8) != 6) {
        REXLOG_ERROR("[lua]   #{}: (no function in this frame)", depth);
        if (depth == 0) pc = 0;
        continue;
      }
      const uint8_t* cl = GuestR(Be32(func), 20);
      if (!cl || cl[6]) {
        REXLOG_ERROR("[lua]   #{}: C function", depth);
        if (depth == 0 && c) pc = 0;
        continue;
      }
      const uint8_t* proto = GuestR(Be32(cl + 16), 48);
      if (!proto) break;
      const uint32_t k = Be32(proto + 8), code = Be32(proto + 12), sizek = Be32(proto + 40),
                     sizecode = Be32(proto + 44);
      std::string consts;
      for (uint32_t i = 0, shown = 0; i < sizek && i < 400 && shown < 8; ++i) {
        const std::string t = string_of(GuestR(k + 16 * i, 16));
        if (!t.empty()) consts += "'" + t + "' ", ++shown;
      }
      if (depth > 0 && c) pc = Be32(c + 12);  // the caller's saved pc
      std::string where;
      if (pc > code && pc <= code + 4 * sizecode) {
        const uint8_t* ip = GuestR(pc - 4, 4);
        const uint32_t ins = ip ? Be32(ip) : 0;
        const uint32_t op = ins & 0x3F, a = (ins >> 6) & 0xFF, cc = (ins >> 14) & 0x1FF, b = ins >> 23;
        where = fmt::format("pc {} of {}, op {} A {} B {} C {}", (pc - code) / 4 - 1, sizecode, op, a, b, cc);
        if (cc >= 256) where += " key '" + string_of(GuestR(k + 16 * (cc - 256), 16)) + "'";
        if (op == 5) where += " global '" + string_of(GuestR(k + 16 * (ins >> 14), 16)) + "'";
      }
      REXLOG_ERROR("[lua]   #{}: {} | constants {}", depth, where, consts);
    }
  }
  // Caught by our luaD_rawrunprotected: back to it, as a pcall on the console.
  if (const uint8_t* l = Guest(L); l && REXCVAR_GET(mtg15_lua_catch_errors)) {
    const uint32_t lj = Be32(l + 0x70);
    for (auto it = g_protected.rbegin(); lj && it != g_protected.rend(); ++it) {
      if ((*it)->lj == lj) {
        if (uint8_t* j = Guest(lj)) SetBe32(j + 8, code);
        if (log) REXLOG_INFO("[lua]   caught (as the console's pcall does); the game goes on");
        std::longjmp((*it)->buf, 1);
      }
    }
  }
  __imp__sub_8240C6B8(ctx, base);
}

// ---- Vida inicial del duelo y victoria forzada (2026-11-13, para Magic Duels / M16; inofensivo en el 2015) ----
// Analisis: M16 work/deepseek_informe_m16_fase5m.md. La vida de reglas de un jugador es int32 BE en Player+0x64;
// Player* = [0x8310D1E0 + 4*i] (i = 0..3); Player+0x118 == 0 = humano local. sub_82D25E58(Player*) es la comprobacion
// de estado "vida <= 0 -> eliminar" (llama a sub_82D254D0) que el paso de reglas hace por cada jugador.
// - customDuel:setPlayerLife / setAILife (sub_82EC5CF0 / sub_82EC5CA0, ficha +0xc / +0x14) guardan la vida pero el
//   motor no la usa en un duelo normal: aqui se recuerda y, si no es 20, se escribe en la primera comprobacion de
//   estado de cada jugador del duelo siguiente.
// - cheats:Cheat_WinGame (sub_82EC61B0, un talon `li r3,0; blr` en el juego) y la cvar mtg15_test_win dejan la vida
//   del rival en 0 en la proxima comprobacion: el motor lo elimina por su camino normal (victoria de verdad).
#include <atomic>
REXCVAR_DEFINE_BOOL(mtg15_test_win, false, "Mtg15",
                    "Pruebas: el rival de cada duelo de campana pierde al empezar (vida 0) para probar la victoria");

namespace {
std::atomic<int32_t> g_life_human{20}, g_life_ai{20};
std::atomic<uint32_t> g_life_pending{0};  // bit 1 humano, bit 2 IA: falta poner su vida
std::atomic<bool> g_force_win{false};

void RememberDuelLife(uint32_t sheet) {
  const uint8_t* f = GuestR(sheet, 0x18);
  if (!f) return;
  const int32_t human = int32_t(Be32(f + 0xc)), ai = int32_t(Be32(f + 0x14));
  g_life_human = human;
  g_life_ai = ai;
  const bool custom = (human > 0 && human != 20) || (ai > 0 && ai != 20);
  g_life_pending = custom ? 3u : 0u;
  if (REXCVAR_GET(mtg15_test_win)) g_force_win = true;
  REXLOG_INFO("[duel] vida pedida: jugador {} IA {}{}{}", human, ai, custom ? " (se aplicara)" : "",
              REXCVAR_GET(mtg15_test_win) ? "; mtg15_test_win: el rival perdera" : "");
}
}  // namespace

extern "C" REX_FUNC(__imp__sub_82EC5CF0);
REX_HOOK_RAW(sub_82EC5CF0) {  // customDuel:setPlayerLife(n)
  const uint32_t sheet = ctx.r3.u32;
  __imp__sub_82EC5CF0(ctx, base);
  RememberDuelLife(sheet);
}

extern "C" REX_FUNC(__imp__sub_82EC5CA0);
REX_HOOK_RAW(sub_82EC5CA0) {  // customDuel:setAILife(n)
  const uint32_t sheet = ctx.r3.u32;
  __imp__sub_82EC5CA0(ctx, base);
  RememberDuelLife(sheet);
}

extern "C" REX_FUNC(__imp__sub_82EC61B0);
REX_HOOK_RAW(sub_82EC61B0) {  // cheats:Cheat_WinGame()
  g_force_win = true;
  REXLOG_INFO("[duel] Cheat_WinGame: el rival quedara con vida 0");
  __imp__sub_82EC61B0(ctx, base);
}

extern "C" REX_FUNC(__imp__sub_82D25E58);
REX_HOOK_RAW(sub_82D25E58) {  // comprobacion de estado de un jugador (vida <= 0 -> eliminar)
  const uint32_t player = ctx.r3.u32;
  if (uint8_t* p = GuestR(player, 0x11C)) {
    const bool human = Be32(p + 0x118) == 0;
    const uint32_t role = human ? 1u : 2u;  // bit 1 = humano, bit 2 = IA (el indice no se encuentra fiable)
    if (g_life_pending.load() & role) {
      g_life_pending.fetch_and(~role);
      const int32_t want = human ? g_life_human.load() : g_life_ai.load();
      if (want > 0) {
        SetBe32(p + 0x64, uint32_t(want));
        REXLOG_INFO("[duel] {}: vida inicial {}", human ? "humano" : "IA", want);
      }
    }
    if (!human && g_force_win.load() && int32_t(Be32(p + 0x64)) > 0) {
      g_force_win = false;
      SetBe32(p + 0x64, 0);
      REXLOG_INFO("[duel] IA: vida 0 para la victoria forzada");
    }
  }
  __imp__sub_82D25E58(ctx, base);
}

// M16 fase 7c (2026-11-13, DeepSeek 7c + Claude): sub_82CAF8D0 is the only way into the content enumeration (it calls
// user.show_content_enumeration, latches "must enumerate" and starts the enumeration thread). Magic Duels' collection
// asks for one on its on_push; with no game:\Content the 2015 engine then drops every menu and restarts the front-end,
// so the collection closed itself. true = the call returns at once (no DLC is enumerated: only for M16, which has none).
REXCVAR_DEFINE_BOOL(mtg15_skip_content_enumeration, false, "Mtg15",
                    "Never enumerate downloadable content (sub_82CAF8D0 returns at once); for Magic Duels' data");
extern "C" REX_FUNC(__imp__sub_82CAF8D0);
REX_HOOK_RAW(sub_82CAF8D0) {  // starts the content enumeration (user.show_content_enumeration + thread)
  static uint32_t calls = 0;
  const bool skip = REXCVAR_GET(mtg15_skip_content_enumeration);
  if (++calls <= 20) REXLOG_INFO("[content] enumeration requested ({}){}", calls, skip ? ": skipped" : "");
  if (skip) {
    ctx.r3.u64 = 0;
    return;
  }
  __imp__sub_82CAF8D0(ctx, base);
}
