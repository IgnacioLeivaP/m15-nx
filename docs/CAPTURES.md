# Magic 2015: obtaining the required captures

These steps are for the Xbox 360 game `5841141F`, base `0.0.0.2` with TU `0.0.6.2`.
Use your own game and Title Update. Do not download
or redistribute another person's dumps. The game itself decrypts its ZED contents at runtime;
the installer and capture collector do not decrypt ZED archives offline.

## 1. Prepare the source and Windows tools

Get the current repository (`git clone https://github.com/IgnacioLeivaP/m15-nx.git`, or
Code → Download ZIP), not just the original v1.0.0 archive: the current source includes
`tools/collect_captures.py` and this guide. Open an **x64 Visual Studio 2022 tools command
prompt** with the Windows SDK, LLVM clang/clang++, native Windows CMake/Ninja and Python
on PATH. The capture application needs a graphics driver supported by plume (Vulkan for
the port's PC renderer). Commands below use **cmd.exe**, where `^` continues a line.

Install the Python modules and fill the SDK's dependencies once:

```bat
py -3 -m pip install Pillow==11.3.0 numpy xxhash zstandard
py -3 tools/fetch_thirdparty.py
```

The fetcher uses the network; `--source "C:\local-rexglue-sdk"` instead copies from an
existing SDK checkout with its submodules. Also prepare `C:\port-dependencies` containing
the port-compatible `plume`, `uam`, `imgui` and `reblue-XenosRecomp`, including its submodules
and DXC package. See [THIRD_PARTY.md](../THIRD_PARTY.md). Stock plume alone is not the
Switch-compatible fork. Use the same compatible dependencies for capture and Switch builds.

Put the extracted base files and TU data in `C:\my-game-with-TU`, with `default.xexp`
from the selected TU. If your originals are STFS packages, the series' standalone
[STFS extractor](https://github.com/IgnacioLeivaP/m13-nx/blob/main/tools/stfs_extract.py)
can unpack them: save the script outside this repository and run
`py -3 C:\tools\stfs_extract.py "C:\my-package" "C:\extracted-files"` separately
for the base and TU packages. Copy the required extracted files to your input folder;
STFS extraction does not decrypt the ZED archives inside. The
expected filenames, sizes and SHA256 hashes are in [the profile](../install/games/mtg15.json).
Keep originals unchanged. No Lua/shader/texture dumps are needed for the next step.

## 2. Stage a PC capture build and generate the game code

From the repository root, use a **new**, external output directory:

```bat
py -3 install/install.py --game mtg15 ^
  --data "C:\my-game-with-TU" --xexp "C:\my-game-with-TU\default.xexp" ^
  --thirdparty "C:\port-dependencies" --out "C:\mtg15-capture-build" ^
  --only verify,stage,codegen --jobs 6
```

This verifies your original files, copies them and the port into the work tree, and builds
or runs ReXGlue. It does **not** require the captures being collected. It produces generated
C++ in `C:\mtg15-capture-build\stage\app\generated` and a decrypted executable image at
`C:\mtg15-capture-build\stage\out\default_image.bin`. This image is produced from your
XEX by codegen; it is not a decrypted copy of the ZED archives.

## 3. Seed the PC shader cache, then compile the capture application

Extract the shaders already present in that executable image:

```bat
py -3 tools/renut_shader_dump.py ^
  --image "C:\mtg15-capture-build\stage\out\default_image.bin" ^
  --out "C:\mtg15-capture-build\stage\out\renut_shader_dump"
```

The selected local image yielded **71 unique shader containers**, not all 211. The others
must be captured as the game creates or loads them. This initial cache avoids requiring
all final captures before building the PC application.

```bat
cmake -S "C:\mtg15-capture-build\stage\app" ^
  -B "C:\mtg15-capture-build\stage\out\capture-pc" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ ^
  -DCMAKE_C_FLAGS=-march=x86-64-v2 -DCMAKE_CXX_FLAGS=-march=x86-64-v2 ^
  -DREXSDK_DIR="C:\sources\m15-nx\sdk" ^
  -DREXGLUE_OUTPUT_ROOT="C:\mtg15-capture-build\stage\out\sdk-capture" ^
  -DCMAKE_RUNTIME_OUTPUT_DIRECTORY="C:\mtg15-capture-build\stage\out\capture-pc" ^
  -DRENUT_SHADER_CAPTURE_DIR="C:\mtg15-capture-build\stage\out\capture-pc\shader_capture" ^
  -DBANJO_RENUT_EARLY_ALPHA=OFF -DMTG15_RENUT_PORT_SHADERS=OFF
cmake --build "C:\mtg15-capture-build\stage\out\capture-pc" --target mtg15 -j 6
```

Replace **`C:\sources\m15-nx\sdk`** with your current repository's actual `sdk` path.
Keep the produced runtime DLLs beside `mtg15.exe`; the SDK's post-link step stages them.
If CMake cannot find the Windows SDK, compiler, dependencies or DXC, resolve that error
before continuing. Do not copy an executable or cache from a different Magic year.

## 4. Run with dumping enabled

```bat
"C:\mtg15-capture-build\stage\out\capture-pc\mtg15.exe" ^
  --game_data_root="C:\mtg15-capture-build\stage\assets\game_root" ^
  --user_data_root="C:\mtg15-capture-profile" ^
  --mtg15_renderer=renut --audio_mute=true ^
  --mtg15_lua_dump=true --mtg15_renut_tex_dump=true ^
  --renut_shader_capture_dir="C:\mtg15-capture-build\stage\out\capture-pc\shader_capture"
```

Let startup finish, pass the press-start screen, and enter the main menu. Visit menus,
help/options, galleries and gameplay, including a duel. The folders beside the executable are:

| Folder | What the game writes | What the installer needs |
|---|---|---|
| `lua_dump/` | Numbered `NNN_<module>.luac` files, potentially with trailing memory padding | The three original modules below, with padding removed |
| `shader_capture/` | Missing Xenos shaders as `vs_<hash>.bin` or `ps_<hash>.bin` | The profile's 211 shaders, combined with the executable-image seed |
| `texdump/` | Converted texture levels as hash/dimension `.bin` files | The two exact texture files below |

Lua modules: `dialogue_boxes.content_enumeration`, `frontend.press_start.press_start`,
`frontend.main_menu.main_menu`. Texture files:

- `1DB9701401F62775_128x128_f61_b16_s4.bin`
- `F1C436C1BEA8F4A9_256x256_f20_b4_s1.bin`

Capture the **original** scripts and textures, before installing the generated Lua wrappers
or button overrides into this PC work tree. Renut captures shaders **missing from its cache**;
an already populated cache will not dump them all again.

## 5. Rebuild and repeat when shaders are missing

A first run can have incomplete graphics: a shader captured during that run is available
to the **next build**, not translated into the running executable. Close the game, rerun
the CMake configure command from step 3, then its build command, and start it again.
The configured capture directory is collected into the shader dump directory by the build.
Keep that directory and the raw captures between iterations. Repeat while visiting content
that has not rendered yet. A shader count alone does not prove completeness; use SHA256
verification in the next step. There is no automated gameplay traversal in this release.

## 6. Collect only the expected files and verify completeness

Run from the current source repository:

```bat
py -3 tools/collect_captures.py ^
  --lua-dump "C:\mtg15-capture-build\stage\out\capture-pc\lua_dump" ^
  --shader-dump "C:\mtg15-capture-build\stage\out\renut_shader_dump" ^
  --shader-dump "C:\mtg15-capture-build\stage\out\capture-pc\shader_capture" ^
  --texture-dump "C:\mtg15-capture-build\stage\out\capture-pc\texdump" ^
  --out "C:\mtg15-captures"
```

The collector recognizes the numbered Lua filenames, parses each Lua 5.1 chunk to remove
padding, and checks **size and SHA256** against the profile. It copies only matching files
to `C:\mtg15-captures\lua`, `shader` and `texture`. Originals are left untouched. Multiple
`--shader-dump` arguments combine sources. Rerunning preserves already collected matches;
a different existing output file is never overwritten.

Success is **Lua 3/3, shader 211/211 and texture 2/2**, with exit code 0. Exit code 2 means
incomplete: `capture_report.json` lists missing filenames and rejected candidates. Continue
capturing/rebuilding; do not rename a wrong shader, alter the profile or bypass verification.
A Lua mismatch can mean the wrong TU or a script already patched; a texture mismatch can
mean an override was active. Use a clean capture tree with the exact game build.

The exact sequence of screens needed to obtain all 211 shaders has **not** been validated
from a completely fresh public PC build. This guide documents the code's capture/rebuild
workflow; it is not a claim of an unattended or fully tested first-time installation.
If progress stops, retain the report and logs: they identify which captures remain missing.

## 7. Build the Switch installation

Return to [the README's build step](../README.md#step-3--build-the-switch-installation).
Use a **different, new** output folder for the full Switch installation, passing:

```text
--lua-dump C:\mtg15-captures\lua
--shader-dump C:\mtg15-captures\shader
--texture-dump C:\mtg15-captures\texture
```

The capture tree already exists, so do not rerun the full installer's `stage` step over it.
No captured files, decrypted image, generated game code or prepared SD folder belong in a
public repository or release.
