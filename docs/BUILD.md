# Building the 2015 source release

The game stores data in encrypted ZED archives. The port's executable can read them, but
this repository has no offline ZED decryptor. Runtime captures are therefore explicit user
inputs; the installer must not be described as a complete automatic bootstrap from ZED.

## Capture inputs

A working PC build can produce the original inputs with:

- `mtg15_lua_dump=true`: original Lua chunks in `lua_dump/`.
- `renut_shader_capture_dir` and the renderer's shader-capture/dump controls: Xenos containers.
- `mtg15_renut_tex_dump=true`: converted texture levels in `texdump/`.

Run PC tests with `audio_mute=true`. This repository does not automatically launch the
PC game or drive it through gameplay to collect complete captures. The hashes and names
of the inputs expected for this build are in `install/games/mtg15.json`.

The three Lua modules are `dialogue_boxes.content_enumeration`,
`frontend.press_start.press_start` and `frontend.main_menu.main_menu`. Name each input
`<module>.luac`; trailing padding is removed by parsing the original Lua 5.1 chunk before
hash verification. The generated wrappers retain the original chunk's return value.

The two texture inputs retain their port-generated hash/dimension filenames. The icon
builder uses geometric labels and Pillow's built-in font. It does not import another
port's raw icon sheets. Its output is `mtg15_texturas.bin` with two MT15 records.

## Pipeline

1. Verify original XEX, TU patch, ZED/metadata files, optional DLC and supplied captures.
2. Copy verified files and source into a separate work tree. Originals are read only.
3. Generate the texture overrides and three current Lua wrappers from the user's captures.
4. Pack the staged game into `game_root.nxpack` and `.nxidx`.
5. Build/reuse a host ReXGlue generator, then generate game C++. No 2012 worker patch or
   another game's post-codegen hot-function pipeline is applied.
6. Translate captured shader containers with XenosRecomp, SPIRV-Cross and uam, optimize
   the GLSL, and create the external shader package and release cache table.
7. Configure/build the native Switch NRO with Renut/deko3d, LTO off by default.
8. Assemble the SD folder and its SHA256 manifest.

The public SDK adds `REXGLUE_OUTPUT_ROOT` so its build products can go into the external
work tree instead of `sdk/out/` inside the source repository. Its current 2015 runtime
changes and the port's November 13 Lua/life hooks are preserved. A diagnostic forced win
only activates when explicitly enabled or invoked; it is off by default.

## Source packaging

`py -3 tools/make_release_zip.py --version v1.0.0` runs source-cleanliness and include
checks before creating the ZIP outside the repository. Original .ZED/.XEX/.XEXP files,
runtime captures, generated Lua/C++, shaders, NRO, packs and game art must stay outside
this tree. See VALIDATION.md for current results and limits.

## Language and Switch-only controls

Pass `--language es` to build Spanish into the NRO. Available codes are `system`, `en`,
`es`, `fr`, `de`, `it`, `ja`, `pt`, `ko`, `ru`. A fresh build defaults to `system`.
Before CMake configuration, the installer updates both staged configuration templates;
CMake embeds them in the NRO. Assembly writes the same language to mtg15.toml.
The stage records the selection in out/build_options.json, so a later assemble-only run
does not reset it. A different language requires rerunning the nro step. Existing legacy
menu preferences do not override the system/build language choice.

The texture override always uses Nintendo Switch glyphs. Xbox/PlayStation selection is
not part of this Switch-specific port.
