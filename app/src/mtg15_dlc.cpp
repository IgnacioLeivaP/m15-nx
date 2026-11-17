// Downloadable content (see mtg15_dlc.h). From sa2-nx's sa2_dlc.cpp (2026-10-21).
//
// Peggle's DLC is "Peggle Nights" (content type 0x00000002, marketplace content; package
// 6AE5772224F8D86683B03E3A1B7509A48D1D4AAE58, holding content.pak, spa.bin and this_is_nights). Copy your own package
// into dlc/ next to the executable: on the next start it is extracted into the content store (user data folder,
// 0000000000000000/58410889/00000002/<package>/) with its .header, and the game finds it through
// XamContentCreateEnumerator. Packages already in the store are skipped. Title Update #3's nightstu.pak, which the
// game reads as update:/nightstu.pak or d:/nightstu.pak, goes into the game folder itself.

#include "mtg15_dlc.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <algorithm>
#include <fstream>
#include <functional>
#include <map>
#include <string>
#include <vector>
#include <system_error>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>
#include <rex/runtime.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xcontent.h>
#include <rex/system/xam/content_device.h>
#include <rex/system/xam/content_manager.h>

REXCVAR_DEFINE_BOOL(mtg15_dlc_rename, false, "Mtg15",
                    "Rename the installed packages' Expansion_NNNN.wad to Data_DLC_NNNN.wad (the name this executable "
                    "reads). Off for now: with them read, the deck selector comes up empty (2026-11-09; the packages "
                    "probably need the game's Title Update)");
REXCVAR_DEFINE_STRING(mtg15_dlc_dir, "", "Mtg15",
                      "Folder with Xbox 360 DLC packages to install at startup (empty = dlc/ next to the executable)");

namespace mtg15::dlc {
namespace {

// STFS packages start with "LIVE", "PIRS" or "CON ".
bool IsContentPackage(const std::filesystem::path& path) {
  char magic[4] = {};
  std::FILE* f = rex::filesystem::OpenFile(path, "rb");
  if (!f) {
    return false;
  }
  const bool read = std::fread(magic, 1, 4, f) == 4;
  std::fclose(f);
  const std::string m(magic, 4);
  return read && (m == "LIVE" || m == "PIRS" || m == "CON ");
}


// Magic 2012 (2026-11-09): this executable looks in each mounted package for DATA_DLC_* and reads it as
// game:\Data_DLC_000N\Data_All_Platforms\Data_Required\...; the Xbox Live packages hold Expansion_000N.wad with a
// top folder EXPANSION_000N, which it never sees. Each one is rewritten as Data_DLC_000N.wad with the folder renamed
// (tools/dlc_nombres.py does the same on the PC). The new name is a byte shorter: the name table keeps its length
// (a zero at its end) and only the tree's references to the names after it change. WAD 0x0201 (2012): u16 0x1234,
// u16 0x0201, u32; u32 names length, names; u32 n, n * 8; u32 n, u32 0x10, u32 n, n * u32 file positions; the tree
// (16-byte records: folder = name, files, folders, 0; file = name, size, index, 0) up to the first file.
uint32_t Le32(const std::vector<uint8_t>& b, size_t o) {
  return o + 4 <= b.size() ? uint32_t(b[o]) | uint32_t(b[o + 1]) << 8 | uint32_t(b[o + 2]) << 16 | uint32_t(b[o + 3]) << 24
                           : 0;
}
void SetLe32(std::vector<uint8_t>& b, size_t o, uint32_t v) {
  for (int i = 0; i < 4; ++i) b[o + i] = uint8_t(v >> (8 * i));
}

bool RenameWadFolder(std::vector<uint8_t>& wad) {
  if (wad.size() < 16 || (uint32_t(wad[2]) | uint32_t(wad[3]) << 8) != 0x0201) return false;
  size_t o = 8;
  const uint32_t length = Le32(wad, o);
  if (o + 4 + length > wad.size()) return false;
  const std::vector<uint8_t> table(wad.begin() + o + 4, wad.begin() + o + 4 + length);
  std::vector<uint8_t> renamed;
  std::map<uint32_t, uint32_t> moved;
  for (size_t pos = 0; pos < table.size();) {
    size_t end = pos;
    while (end < table.size() && table[end]) ++end;
    std::string name(table.begin() + pos, table.begin() + end);
    if (name.size() == 14 && (name.compare(0, 10, "EXPANSION_") == 0 || name.compare(0, 10, "expansion_") == 0)) {
      name = "DATA_DLC_" + name.substr(10);
    }
    moved[uint32_t(pos)] = uint32_t(renamed.size());
    renamed.insert(renamed.end(), name.begin(), name.end());
    renamed.push_back(0);
    pos = end + 1;
  }
  if (renamed.size() > length) return false;
  renamed.resize(length, 0);
  std::copy(renamed.begin(), renamed.end(), wad.begin() + o + 4);
  o += 4 + length;
  o += 4 + size_t(Le32(wad, o)) * 8;
  const uint32_t count = Le32(wad, o + 8);
  uint32_t first = UINT32_MAX;
  for (uint32_t i = 0; i < count; ++i) first = std::min(first, Le32(wad, o + 12 + 4 * size_t(i)));
  o += 12 + size_t(count) * 4;
  if (first > wad.size()) return false;
  bool ok = true;
  auto remap = [&](size_t at) {
    auto it = moved.find(Le32(wad, at));
    if (it == moved.end()) ok = false; else SetLe32(wad, at, it->second);
  };
  std::function<size_t(size_t)> folder = [&](size_t at) -> size_t {
    remap(at);
    const uint32_t files = Le32(wad, at + 4), folders = Le32(wad, at + 8);
    at += 16;
    for (uint32_t i = 0; i < folders && ok && at + 16 <= first; ++i) at = folder(at);
    for (uint32_t i = 0; i < files && ok && at + 16 <= first; ++i, at += 16) remap(at);
    return at;
  };
  while (ok && o + 16 <= first) o = folder(o);
  return ok;
}

// The installed packages' Expansion_NNNN.wad -> Data_DLC_NNNN.wad (once: the old file is removed after).
void RenameForThisExecutable(rex::system::xam::ContentManager* content, uint32_t title_id) {
  if (!REXCVAR_GET(mtg15_dlc_rename)) return;
  const auto installed = content->ListContent(uint32_t(rex::system::xam::DummyDeviceId::HDD), 0,
                                              rex::system::XContentType::kMarketplaceContent, title_id);
  std::error_code ec;
  for (const auto& item : installed) {
    const auto folder = content->ResolvePackagePath(0, item);
    for (const auto& entry : std::filesystem::directory_iterator(folder, ec)) {
      const std::string name = rex::path_to_utf8(entry.path().filename());
      if (name.size() != 18 || (name.compare(0, 10, "Expansion_") != 0 && name.compare(0, 10, "EXPANSION_") != 0)) {
        continue;
      }
      const auto target = folder / ("Data_DLC_" + name.substr(10));
      std::ifstream in(entry.path(), std::ios::binary);
      std::vector<uint8_t> wad((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
      in.close();
      if (!RenameWadFolder(wad)) {
        REXLOG_WARN("[dlc] {}: not a WAD this port can rename", rex::path_to_utf8(entry.path()));
        continue;
      }
      {
        std::ofstream out(target, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char*>(wad.data()), std::streamsize(wad.size()));
        if (!out) {
          REXLOG_WARN("[dlc] could not write {}", rex::path_to_utf8(target));
          continue;
        }
      }
      std::filesystem::remove(entry.path(), ec);
      REXLOG_INFO("[dlc] {}: {} -> {} (the name this executable looks for)", item.file_name(), name,
                  rex::path_to_utf8(target.filename()));
    }
  }
}

}  // namespace

std::vector<int> InstalledPacks() {
  std::vector<int> out;
  auto* kernel = rex::system::kernel_state();
  auto* content = kernel ? kernel->content_manager() : nullptr;
  if (!content) return out;
  const auto installed = content->ListContent(uint32_t(rex::system::xam::DummyDeviceId::HDD), 0,
                                              rex::system::XContentType::kMarketplaceContent, kernel->title_id());
  std::error_code ec;
  for (const auto& item : installed) {
    for (const auto& entry : std::filesystem::directory_iterator(content->ResolvePackagePath(0, item), ec)) {
      std::string name = rex::path_to_utf8(entry.path().filename());
      std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return char(std::tolower(c)); });
      // expansion_000N.wad (Xbox Live) or data_dlc_000N.wad (renamed by mtg15_dlc_rename)
      const bool wad = name.size() > 8 && name.compare(name.size() - 4, 4, ".wad") == 0 &&
                       (name.rfind("expansion_", 0) == 0 || name.rfind("data_dlc_", 0) == 0);
      if (!wad) continue;
      const int n = std::atoi(name.substr(name.rfind('_') + 1).c_str());
      if (n > 0) out.push_back(n);
    }
  }
  std::sort(out.begin(), out.end());
  out.erase(std::unique(out.begin(), out.end()), out.end());
  return out;
}

void InstallPackages(rex::Runtime* runtime) {
  auto* kernel = runtime ? runtime->kernel_state() : nullptr;
  auto* content = kernel ? kernel->content_manager() : nullptr;
  if (!content) {
    return;
  }
  std::string dir = REXCVAR_GET(mtg15_dlc_dir);
  std::erase(dir, '"');  // string cvars can come back quoted
  const std::filesystem::path folder =
      dir.empty() ? rex::filesystem::GetExecutableFolder() / "dlc" : std::filesystem::path(dir);
  std::error_code ec;
  if (!std::filesystem::is_directory(folder, ec)) {
    RenameForThisExecutable(content, kernel->title_id());
    return;
  }
  const auto installed = content->ListContent(uint32_t(rex::system::xam::DummyDeviceId::HDD), 0,
                                              rex::system::XContentType::kMarketplaceContent,
                                              kernel->title_id());
  for (const auto& entry : std::filesystem::directory_iterator(folder, ec)) {
    if (!entry.is_regular_file(ec) || !IsContentPackage(entry.path())) {
      continue;
    }
    const std::string name = rex::path_to_utf8(entry.path().filename());
    bool present = false;
    for (const auto& item : installed) {
      present = present || item.file_name() == name;
    }
    if (present) {
      REXLOG_INFO("[dlc] {} already installed", name);
      continue;
    }
    const auto result = content->InstallContent(entry.path());
    if (result == 0) {
      REXLOG_INFO("[dlc] installed {}", name);
    } else {
      REXLOG_WARN("[dlc] could not install {}: {:08X}", name, result);
    }
  }
  RenameForThisExecutable(content, kernel->title_id());
}

}  // namespace mtg15::dlc
