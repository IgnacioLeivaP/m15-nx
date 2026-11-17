#!/usr/bin/env bash
# banjo-nx (deko3d renderer, docs/deko3d-renderer.md): the PC tools the deko3d shader chain needs, built into
# out/deko3d_tools: SPIRV-Cross (from UnleashedRecomp-NX's MoltenVK copy, Apache-2.0; a PC tool only) and uam
# (app/thirdparty/uam, SwitchWakerHD's patched 1.1.0) with devkitPro's MSYS2 clang (MinGW).
#   bash tools/deko3d_build_tools.sh [SPIRV-Cross source]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -lt 1 ]]; then
    echo "Usage: bash tools/deko3d_build_tools.sh <SPIRV-Cross source>" >&2
    exit 2
fi
SPIRV_CROSS_SRC="$(cygpath -u "$1" 2>/dev/null || printf '%s' "$1")"
OUT="$ROOT/out/deko3d_tools"
export PATH="/c/devkitPro/msys2/clang64/bin:/c/devkitPro/msys2/usr/bin:$PATH"

mkdir -p "$OUT/spirv-cross-build" "$OUT/uam-build"
cmake -S "$SPIRV_CROSS_SRC" -B "$OUT/spirv-cross-build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DSPIRV_CROSS_ENABLE_TESTS=OFF -DSPIRV_CROSS_SHARED=OFF \
    -DSPIRV_CROSS_ENABLE_C_API=OFF -DCMAKE_EXE_LINKER_FLAGS=-static
ninja -C "$OUT/spirv-cross-build" -j "${CMAKE_BUILD_PARALLEL_LEVEL:-6}" spirv-cross
cmake -S "$ROOT/app/thirdparty/uam" -B "$OUT/uam-build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_EXE_LINKER_FLAGS=-static
ninja -C "$OUT/uam-build" -j "${CMAKE_BUILD_PARALLEL_LEVEL:-6}" uam_tool
"$OUT/uam-build/uam.exe" --version
