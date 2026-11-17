# Third-party notices

The port is built on other projects. This file lists every one of them, where it comes from, its license, and whether
that license lets this repository redistribute it. **DUDOSO** means the license could not be established from the
sources available while preparing this repository: ask the author before publishing.

Nothing of the game itself is listed here, because nothing of the game is in this repository.

## 1. Projects this port is derived from

| Project | Used for | License | Redistributable here? |
|---|---|---|---|
| [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) by Tom Clay, with portions of [Xenia](https://xenia.jp) (Ben Vanik and the Xenia contributors) | the code generator (PowerPC to C++), the Xbox 360 kernel and runtime, GPU command processing, virtual file system | BSD-3-Clause (the SDK's own `LICENSE` is kept in `sdk/`) | Yes. The fork this port builds against is in `sdk/` and is documented in `sdk/README.md`; it is distributed under the same BSD-3-Clause with all upstream and third-party copyright notices kept intact. |
| Horizon (Switch) layer of the SDK | guest memory, exception handling, threading, input, audio, presentation, clocks | BSD-3-Clause as part of the SDK fork | Yes. It lives in `sdk/src`, `sdk/include` and `sdk/switch_compat`; the Horizon layer is by StevenSND, as stated in `sdk/README.md`. |
| [reNut](https://github.com/masterspike52/reNut) by masterspike52, in banjo-nx's Switch port of it | `app/src/renut_engine`: the Direct3D-level renderer (the game's Direct3D calls drawn directly) | reuse and redistribution in this port permitted by its author (written permission, confirmed) | Yes. The author's permission to redistribute `app/src/renut_engine` is confirmed; a license text is not attached, so the author's terms prevail. |
| [plume](https://github.com/renderbag/plume) by renderbag and contributors, with banjo-nx's deko3d back end | the rendering layer Renut draws through (deko3d on the Switch) | MIT | Yes. Not distributed here (`--thirdparty`), so its `LICENSE` must be kept when it is copied next to a build. |
| [uam](https://github.com/devkitPro/uam) by fincs, with code imported from Mesa | the deko3d shader compiler | zlib (own code) and MIT (the code imported from Mesa) | Yes. Same as plume: supplied with `--thirdparty`. |
| [XenosRecomp](https://github.com/hedge-dev/XenosRecomp) by hedge-dev and contributors, in Renut's version | the shader translator (Xenos microcode to HLSL/SPIR-V) | MIT | Yes. Same as plume: supplied with `--thirdparty`. |
| [Dear ImGui](https://github.com/ocornut/imgui) by Omar Cornut | the overlay Renut draws | MIT | Yes. Same as plume: supplied with `--thirdparty`. |

The application scaffolding and build tools also derive from peggle1-nx/peggle2-nx
(ChanseyIsTheBest) and NFSMW Recompiled (madelrandel-blip), under GPL-3.0.
Their attribution is retained; the old game-specific hot functions and renderer branches
are excluded from this source distribution.

## 2. Libraries inside `sdk/thirdparty/`

The small ones are copied here with their license file. The large ones have a public repository and are **not** copied:
`tools/fetch_thirdparty.py` fetches the pinned upstream tree and its submodules, preserving the fork files. Use `--help` for local-source and destination options.

### 2a. Copied here (small)

| Library | License | License file in this repository |
|---|---|---|
| [libmspack](https://www.cabextract.org.uk/libmspack/) by Stuart Caie (cabinet/CHM decompression) | LGPL-2.1 | `libmspack/libmspack/COPYING.LIB` |
| [spdlog](https://github.com/gabime/spdlog) | MIT | `spdlog/LICENSE` |
| [utfcpp](https://github.com/nemtrif/utfcpp) | BSL-1.0 | `utfcpp/LICENSE` |
| [CLI11](https://github.com/CLIUtils/CLI11) | BSD-3-Clause | `cli11/LICENSE` |
| [o1heap](https://github.com/pavel-kirienko/o1heap) | MIT | `o1heap/LICENSE` |
| aes_128, tiny-aes-c (AES for the STFS/XContent reader) | public domain / MIT, as stated in their headers | `aes_128/LICENSE` |
| `crypto` (DES and SHA-1) | as stated in its headers | `crypto/des/LICENSE` |
| stb (single-header image/utility code) | MIT or public domain (dual), as stated in the header | header of `stb/stb_image.h` |
| disruptorplus, the RenderDoc API header, the PowerPC disassembler (`disasm`), the DXBC/DXC headers, the `pe` and `ffmpeg-overlay` glue | **DUDOSO**: no license file shipped with them in the SDK tree; the two that look like vendored third-party code (disasm, disruptorplus) carry no copyright notice at all | — |

### 2b. Fetched on demand (large, one public repository each)

| Library | License | Upstream |
|---|---|---|
| FFmpeg (libavcodec, libavutil: the XMA audio decoder) | LGPL-2.1-or-later, configured without GPL parts. The SDK tree modifies a few files (`fft_template.c`, `mdct_template.c`, its `config.h` and the codec list); that stays in the fetched tree, not here. | <https://github.com/FFmpeg/FFmpeg> |
| glslang | BSD-3-Clause and others (see its `LICENSE.txt`) | <https://github.com/KhronosGroup/glslang> |
| SPIRV-Tools, SPIRV-Headers, Vulkan-Headers, Vulkan-Loader, MoltenVK | Apache-2.0 (SPIRV-Headers and Vulkan-Headers also MIT) | <https://github.com/KhronosGroup> |
| Vulkan Memory Allocator | MIT | <https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator> |
| fmt | MIT | <https://github.com/fmtlib/fmt> |
| xxHash | BSD-2-Clause | <https://github.com/Cyan4973/xxHash> |
| SIMDe | MIT | <https://github.com/simd-everywhere/simde> |
| toml++ | MIT | <https://github.com/marzer/tomlplusplus> |
| Inja (template engine of the code generator) | MIT | <https://github.com/pantor/inja> |
| Dear ImGui | MIT | <https://github.com/ocornut/imgui> |
| Catch2 (SDK tests) | BSL-1.0 | <https://github.com/catchorg/Catch2> |
| Tracy profiler | BSD-3-Clause | <https://github.com/wolfpld/tracy> |
| SDL3 (PC build of the runtime) | Zlib | <https://github.com/libsdl-org/SDL> |

## 3. Tools the installer needs from outside

| Library | License |
|---|---|
| [deko3d](https://github.com/devkitPro/deko3d) by fincs (devkitPro) | zlib |
| [libnx](https://github.com/switchbrew/libnx) and the devkitA64 runtime (newlib, libstdc++) | ISC; newlib and the GCC runtime licenses |
| [SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross) (built by `tools/deko3d_build_tools.sh`) | Apache-2.0 |
| [Pillow](https://python-pillow.org) (the tools' image handling) | MIT-CMU |
| [numpy](https://numpy.org) (the icon tool reads the alpha channel with it) | BSD-3-Clause |
| [xxhash](https://pypi.org/project/xxhash/) (Python binding, the tools) | BSD-2-Clause |

## 4. Assets written for this port

| What | Origin | License |
|---|---|---|
| `tools/button_drawings.py` and `tools/iconos15.py`'s drawings (PlayStation and Switch button glyphs) | drawn by this repository's code with plain geometry and Pillow's built-in bitmap font: circles, crosses, squares, triangles, rounded rectangles and letters. **No third-party art and no system font file** is read. | GPL-3.0-or-later, like the rest of this repository (see `LICENSE`) |

The earlier tool for these icons read PNG art from another of the author's projects and `arialbd.ttf` from the Windows
font folder. Neither is used here: Arial is not redistributable, and the glyph sheets were of unknown provenance.

## 5. Trademarks

*Magic: The Gathering* and *Duels of the Planeswalkers* are trademarks of Wizards of the Coast LLC. *Xbox 360* is a
trademark of Microsoft Corporation. *Nintendo Switch* is a trademark of Nintendo. *PlayStation* is a trademark of Sony
Interactive Entertainment. This project is not affiliated with, endorsed by or supported by any of them.
