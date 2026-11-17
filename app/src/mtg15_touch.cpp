// Controles tactiles: en the reference port llamaban a los TouchBegan/Moved/Ended del propio juego
// (direcciones de the reference port). Magic 2012 de Xbox no tiene ese camino: por ahora no hacen nada.
// La version original esta en ref/the reference port/app/src/mtg15_touch.cpp.

#include "mtg15_touch.h"

namespace mtg15::touch {

void OnWindowMouse(MouseKind, float, float) {}

void Dispatch(PPCContext&, uint8_t*) {}

}  // namespace mtg15::touch
