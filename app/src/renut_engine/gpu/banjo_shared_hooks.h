// the reference port (tools/renut_hook_remap.py): the addresses both Renut's renderer and the reference port's own code
// hook. the reference port's hook calls renut_native_sub_X first when Renut's renderer is chosen
// (BANJO_RENUT_YIELD_SHARED).
#pragma once

#include <cstdint>

#include <rex/ppc.h>

extern "C" void renut_native_sub_8248F4F8(PPCContext& ctx, uint8_t* base);
