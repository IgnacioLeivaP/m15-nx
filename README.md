# mtg15-nx — Magic: The Gathering — Duels of the Planeswalkers 2015 for Nintendo Switch

<!-- magic-series:start -->
## Other Magic / Duels ports for Nintendo Switch

Each project uses its own game files and installation method. The two 2015 ports are
separate projects; Xbox 360 files cannot be used with the Android port or vice versa.

| Game | Original version | Project and installation guide |
|---|---|---|
| Duels of the Planeswalkers (2009) | Xbox 360 + required PC data | [m09-nx](https://github.com/IgnacioLeivaP/m09-nx#start-here) |
| Magic 2012 | Xbox 360 | [m12-nx](https://github.com/IgnacioLeivaP/m12-nx#start-here) |
| Magic 2013 | Xbox 360 | [m13-nx](https://github.com/IgnacioLeivaP/m13-nx#start-here) |
| Magic 2014 | Android 1.5.0 | [Duels14_nx](https://github.com/IgnacioLeivaP/Duels14_nx#start-here) |
| Magic 2015 | Android 1.4.4959 | [duels_nx](https://github.com/IgnacioLeivaP/duels_nx#start-here) |
| Magic 2015 | Xbox 360 | [m15-nx](https://github.com/IgnacioLeivaP/m15-nx#start-here) |

Otros años: los enlaces llevan a las instrucciones de cada port. Comprueba la versión
de origen antes de preparar los archivos; las versiones Android y Xbox 360 son distintas.
<!-- magic-series:end -->

Static recompilation of Xbox 360 XBLA title `5841141F`, with Title Update `0.0.6.2`,
built with ReXGlue and Renut/deko3d. The PC translates the game's PowerPC code to C++
and compiles a native Switch NRO.

**Source and installer only. No game, original scripts, texture captures, generated game
code, translated shader cache, data pack, DLC or NRO is distributed.** Supply your own game.

## Start here

This is the **Xbox 360** 2015 source port. It needs a PC capture pass before the Switch
installation can be built. Follow these steps in order:

1. [Prepare the tools and original game](#step-1--check-requirements).
2. [Obtain and verify the captures](#step-2--obtain-the-pc-captures): PC build → run → rebuild
   as needed → collect **3 Lua, 211 shaders and 2 textures**.
3. [Build the Switch installation](#step-3--build-the-switch-installation), choosing its language.
4. [Copy to SD and launch](#step-4--copy-to-sd-and-launch).

## Why this game needs a capture pass

The 2012/2013 offline WAD installation recipe does not apply. This installer also needs
three decrypted Lua chunks, 211 shader containers from the executable image and runtime captures and two converted textures
from your own copy of this exact game build. The profile in `install/games/mtg15.json`
contains their fingerprints, not their contents. It does not decrypt ZED archives.

This release is intended for users who can supply those runtime captures. Automatic
capture collection and a complete bootstrap from just the encrypted game packages are
not implemented. Follow the [capture guide](docs/CAPTURES.md), including PC staging/codegen,
shader seeding, PC build commands, runtime dumping and hash verification.

## Step 1 — check requirements

- Windows, Python 3.9+, CMake 3.25+, native Windows Ninja, LLVM clang, and bash.
- devkitPro: devkitA64, libnx, deko3d.
- `py -3 -m pip install Pillow==11.3.0 numpy xxhash zstandard` (Pillow version tested locally).
- The original base XEX, chosen TU patch, 13 ZED files and metadata listed in the profile.
- Optional: your Garruk's Revenge STFS package and an NRO icon.
- SDK libraries filled with `tools/fetch_thirdparty.py --source <local SDK checkout>`, or
  fetched separately by that tool. Network access is not part of running the installer.
- Port-compatible `plume`, `uam`, `imgui`, `reblue-XenosRecomp` with submodules and DXC,
  supplied through `--thirdparty`. See [THIRD_PARTY.md](THIRD_PARTY.md).
- SPIRV-Cross sources for host shader tools, or the optional prebuilt tool arguments.

## Step 2 — obtain the PC captures

Follow [docs/CAPTURES.md](docs/CAPTURES.md) before running the full installer. It explains
how to prepare a PC capture build without already having the captures, then select and
verify them with `tools/collect_captures.py`. Continue only when its report says **3/3 Lua,
211/211 shaders, 2/2 textures**. No complete automatic traversal is supplied.

## Step 3 — build the Switch installation

Open **cmd.exe** in the current repository root. The `^` continuations below are cmd syntax.
Replace example paths with your own. Use a fresh output folder outside the source and a
different folder from the PC capture build:

```bat
py -3 install/install.py --game mtg15 ^
  --data "C:\my-game-with-TU" --xexp "C:\my-game-with-TU\default.xexp" ^
  --lua-dump "C:\mtg15-captures\lua" --shader-dump "C:\mtg15-captures\shader" ^
  --texture-dump "C:\mtg15-captures\texture" ^
  --thirdparty "C:\port-dependencies" --spirv-cross-source "C:\SPIRV-Cross" ^
  --out "C:\mtg15-output" --language es --jobs 6
```

`--language es` builds Spanish into the NRO and writes matching startup settings.
Choices: `system`, `en`, `es`, `fr`, `de`, `it`, `ja`, `pt`, `ko`, `ru`.
Without the option a fresh build follows the Switch system language. Partial build/package
runs retain the previous selection; change it with the `nro` step, not just `assemble`.
Button glyphs are always Nintendo Switch, with no style selector.

`--dlc <folder>` and `--icon <image>` are optional. `--help`, `--list-steps`, `--dry-run`
and `--only verify` describe or check the inputs. Use output/staging folders outside this
repository and a fresh work tree for a full installation. `--rexglue`, `--xenos-recomp`
and `--deko-tools` can reuse existing compatible host tools.

The installer checks hashes, stages the game, builds the current menu wrappers, generates
Switch glyph overrides from your own captured textures and the port's geometric drawings,
translates shaders, packs the data, generates C++, builds the NRO and writes
`switch/mtg15-nx/` with a SHA256 manifest.

## Step 4 — copy to SD and launch

Copy that folder to `sdmc:/switch/` while
preserving your saves. Use title takeover (hold R while opening an installed game);
Album applet mode does not provide enough memory.

## Current behavior and known limitations

- The latest menu fixes preserve enumeration but hide its dialog and avoid the white transition hang.
- Online/store/promotional entries are filtered and reward notifications are processed without recursive dialogs.
- The Garruk Expansion carousel entry is deliberately hidden, matching the development port's current configuration.
- Extras contains the local Multiverse galleries. A playable duel was reached in PC testing.
- The optional DLC input is **one** Garruk's Revenge package with 42 extracted files, not 42 DLC packages.
- Switch glyphs are applied through a generated texture-override file. There is no controller-style selector.
  Choose the language with `--language` when building; no in-game language menu is required.
- Some thin horizontal battlefield lines remain. The development notes report exits after about ten minutes
  of play in some PC sessions. A full match and the new package need hardware validation.
- Videos are not deliberately skipped: the inherited 2013 skip hook is disabled. The
  introduction was observed playing in PC development tests; this is not a new Switch video test.
- `mtg15_test_win` and enumeration-skip diagnostics default to false.
- Validation here covers the installer, shader conversion and a compiled private NRO.
  A complete campaign, every DLC, long-session stability and all player-facing functions have
  not been revalidated on Switch with this public build. See the validation record below.

See [docs/VALIDATION.md](docs/VALIDATION.md) for the exact validation performed.

## Layout, credits and licenses

`app/` is the current 2015 port, `sdk/` its runtime fork, `install/` the profile and
capture-based installer, `tools/` build/conversion tools, and `docs/` build/validation notes.
The inactive copied 2013 worker and other games' hot guest-function copies are excluded.
Shared renderer/helper names and upstream attribution are retained.

Own code: GPL-3.0-or-later, Nispero 2026, [LICENSE](LICENSE). The SDK retains BSD-3-Clause
and its third-party notices. Credits and dependency origins: [THIRD_PARTY.md](THIRD_PARTY.md).

This fan project is unaffiliated with Wizards of the Coast, Hasbro, Stainless Games,
Microsoft or Nintendo. Game assets and trademarks belong to their owners. Do not redistribute
runtime captures or the generated installation folder.

