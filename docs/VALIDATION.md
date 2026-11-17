# Validation of the prepared 2015 source release

Checked on 2026-11-17. This is separate from the development package last built that day.

| Check | Result |
|---|---|
| Python syntax, CLI help and complete dry run | Passed |
| XEX/TU, 13 ZED files, metadata, original Garruk DLC | Installer SHA256 checks passed |
| Runtime capture inputs | 3 normalized Lua chunks, 211 shader containers, 2 textures verified by SHA256 |
| Generated menu wrappers | All three byte-identical to the current development port, including November 17 changes |
| Lua 5.1 checks | Wrapper syntax, enumeration completion, hidden alpha and bounded timeout passed |
| Geometric icon overrides | Two MT15 records, 278568 bytes; no external art sheets read |
| Fresh code generation | 427 files produced; pre-existing unresolved-branch warning noted below |
| Shader pipeline | 211/211 compiled, 0 failures; 100 VS and 111 PS; GLSL optimization checked |
| Asset pack | 17 verified files, approximately 1053 MiB; data checksum checked by rereading |
| Full native Switch build | Compiled and linked with GCC 15.2.0, Ninja, 6 jobs, LTO off |
| NRO metadata and recent hooks | Magic 2015 / Nispero / 1.0.0; November 13 Lua/life hook strings present |
| Installer SD-folder assembly | Passed: 10 files including one original DLC package; SHA256 manifest written |
| Original-only bootstrap and automatic capture collection | Not implemented for encrypted ZED |
| Fresh PC host-tool/dependency compilation | Not run during preparation; existing compatible host tools and local dependencies reused |
| New package on Nintendo Switch | Not tested; no console delivery performed |

The actual installer was used for input verification, icons, Lua wrappers, shader translation,
pack generation and the Switch configure/build. Source staging and fresh code generation were
prepared separately in an isolated work tree. The shader package was regenerated from user
captures; it was not copied from the previous release cache. The generic existing FNV hashing
DLL was reused while the Switch compiler was running; its C source is included in tools/.

Codegen still reports a branch from `0x825CE01C` to `0x825CDF78` that cannot be resolved.
The same unresolved-call fatal path is already present in the development tree's generated
`mtg15_recomp.158.cpp`; preparation did not introduce or repair it. Compilation is not proof
that this path or a complete match works at runtime.

Known development limits remain: hidden Garruk Expansion entry by request, no language/icon
Options dropdowns, battlefield line artifacts, and reported exits in some longer PC sessions.
The source release does not claim that the complete player checklist has passed.

Before packaging, make_release_zip.py requires check_clean.py and check_includes.py to pass.
Original ZED/data, runtime captures, generated game C++/Lua, NRO, packs and translated shaders
are excluded from both the tracked source and source ZIP.
