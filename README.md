# mtg15-nx — Magic: The Gathering — Duels of the Planeswalkers 2015 for Nintendo Switch

Static recompilation of Xbox 360 XBLA title `5841141F`, with Title Update `0.0.6.2`,
built with ReXGlue and Renut/deko3d. The PC translates the game's PowerPC code to C++
and compiles a native Switch NRO.

**Source and installer only. No game, original scripts, texture captures, generated game
code, translated shader cache, data pack, DLC or NRO is distributed.** Supply your own game.

## Important: this game uses encrypted ZED archives

The 2012/2013 offline WAD installation recipe does not apply. This installer also needs
three decrypted Lua chunks, 211 captured shader containers and two converted textures
from your own execution of this exact game build. The profile in `install/games/mtg15.json`
contains their fingerprints, not their contents. It does not decrypt ZED archives.

This release is intended for users who can supply those runtime captures. Automatic
capture collection and a complete bootstrap from just the encrypted game packages are
not implemented. See [docs/BUILD.md](docs/BUILD.md).

## Requirements and install

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

```bat
py -3 install/install.py --game mtg15 ^
  --data "C:\my-game-with-TU" --xexp "C:\my-game-with-TU\default.xexp" ^
  --lua-dump "C:\my-captures\lua" --shader-dump "C:\my-captures\shaders" ^
  --texture-dump "C:\my-captures\textures" ^
  --thirdparty "C:\port-dependencies" --spirv-cross-source "C:\SPIRV-Cross" ^
  --out "C:\mtg15-output" --jobs 6
```

`--dlc <folder>` and `--icon <image>` are optional. `--help`, `--list-steps`, `--dry-run`
and `--only verify` describe or check the inputs. Use output/staging folders outside this
repository and a fresh work tree for a full installation. `--rexglue`, `--xenos-recomp`
and `--deko-tools` can reuse existing compatible host tools.

The installer checks hashes, stages the game, builds the current menu wrappers, generates
Switch glyph overrides from your own captured textures and the port's geometric drawings,
translates shaders, packs the data, generates C++, builds the NRO and writes
`switch/mtg15-nx/` with a SHA256 manifest. Copy that folder to `sdmc:/switch/` while
preserving your saves. Use title takeover (hold R while opening an installed game);
Album applet mode does not provide enough memory.

## Current behavior and known limitations

- The latest menu fixes preserve enumeration but hide its dialog and avoid the white transition hang.
- Online/store/promotional entries are filtered and reward notifications are processed without recursive dialogs.
- The Garruk Expansion carousel entry is deliberately hidden, matching the development port's current configuration.
- Extras contains the local Multiverse galleries. A playable duel was reached in PC testing.
- The optional DLC input is **one** Garruk's Revenge package with 42 extracted files, not 42 DLC packages.
- Switch glyphs are applied through a generated texture-override file. Language and button-style dropdowns
  have not been added to the 2015 Options pages. System/config language behavior remains as in the port.
- Some thin horizontal battlefield lines remain. The development notes report exits after about ten minutes
  of play in some PC sessions. A full match and the new package need hardware validation.
- Videos are skipped. `mtg15_test_win` and enumeration-skip diagnostics default to false.
- This is a source preparation, not a claim that the player's complete-port checklist is satisfied.

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
