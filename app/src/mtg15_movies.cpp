// Videos (WMV/XMV) de Magic 2012.
//
// Con el renderer de Renut, el primer video (el logo de WotC, ~fotograma 58) hace perder el
// dispositivo Vulkan ("device lost") y no se dibuja nada mas (2026-11-08, sin resolver: ver
// BITACORA "Renut dibuja Magic en PC"). Mientras tanto, con Renut los videos se saltan: el
// juego los pide desde Lua con playMovie (tabla de funciones Lua en 0x82CAAB60:
// playMovie -> sub_82B8C620, isMoviePlaying -> sub_82B849E8, stopMovie -> sub_82B849C0).
// playMovie lee el nombre, llama a sub_82B8C428 (arma la ruta y arranca el video con
// sub_823685E0) y devuelve a Lua su true/false. Se intercepta sub_82B8C428 para que
// responda false ("no se pudo"): la parte Lua queda intacta. (Interceptar playMovie entero
// y no devolver nada terminaba en un DbgBreak del kernel.)
// Con la GPU emulada los videos funcionan y se reproducen siempre.

#include <cstdint>
#include <string>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>
#include <rex/system/kernel_state.h>

#include "mtg15_opciones.h"

#if MTG15_RENUT_RENDERER
#include "renut_engine/gpu/banjo_renut_select.h"
#endif

REXCVAR_DEFINE_BOOL(mtg15_movies_renut, false, "Mtg15",
                    "Renut's renderer: play the game's videos (false = skip them; they lose the Vulkan "
                    "device for now). The emulated GPU always plays them");

namespace {
// An MSVC std::string of the game (32-bit): the text in place when its capacity (+0x14) is under 16, else a pointer at
// +0; its size at +0x10.
std::string GuestString(uint32_t address) {
  auto* memory = rex::system::kernel_state()->memory();
  const uint8_t* s = address ? memory->TranslateVirtual<const uint8_t*>(address) : nullptr;
  if (!s) return {};
  auto be32 = [](const uint8_t* p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; };
  const uint32_t size = be32(s + 0x10), capacity = be32(s + 0x14);
  if (size > 256) return {};
  const uint8_t* text = capacity < 16 ? s : memory->TranslateVirtual<const uint8_t*>(be32(s));
  return text ? std::string(reinterpret_cast<const char*>(text), size) : std::string();
}

bool SaltarVideos() {
#if MTG15_RENUT_RENDERER
  return ::banjo::renut_gpu::Active() && !REXCVAR_GET(mtg15_movies_renut);
#else
  return false;
#endif
}
}  // namespace

// MAGIC 2015: APAGADO. sub_82B21D50 era el playMovie interno del 2013 y en el 2015 no se pudo localizar (mapa por
// forma y tools/tu_global.py fallan). Con la direccion del 2013 el gancho caeria en otra funcion. Sin el, los
// videos los reproduce el juego por su cuenta y el mensaje "mtg15:estilo=..." del menu de Opciones no se atiende.
#if 0
extern "C" REX_FUNC(__imp__sub_82B21D50);
REX_HOOK_RAW(sub_82B21D50) {  // bool (const std::string* nombre)
  // Our Settings menu's messages (mtg15_opciones.h): game:playMovie("mtg15:estilo=ps").
  if (mtg15::opciones::HandleMessage(GuestString(ctx.r3.u32))) {
    ctx.r3.u64 = 0;
    return;
  }
  if (SaltarVideos()) {
    static bool avisado = false;
    if (!avisado) {
      avisado = true;
      REXLOG_INFO("[movies] Renut: los videos se saltan (mtg15_movies_renut = false)");
    }
    ctx.r3.u64 = 0;  // false: el video no arranco
    return;
  }
  __imp__sub_82B21D50(ctx, base);
}
#endif  // MAGIC 2015: playMovie interno del 2013 apagado
