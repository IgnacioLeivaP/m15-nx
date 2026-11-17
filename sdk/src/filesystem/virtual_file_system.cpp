/**
 ******************************************************************************
 * Xenia : Xbox 360 Emulator Research Project                                 *
 ******************************************************************************
 * Copyright 2020 Ben Vanik. All rights reserved.                             *
 * Released under the BSD license - see LICENSE in the root for more details. *
 ******************************************************************************
 *
 * @modified    Tom Clay, 2026 - Adapted for ReXGlue runtime
 */

#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/string.h>

#include <rex/filesystem/devices/host_path_entry.h>

#include <atomic>
#include <chrono>

REXCVAR_DEFINE_BOOL(allow_game_relative_writes, false, "Filesystem",
                    "Not useful to non-developers. Allows code to write to paths "
                    "relative to game://. Used for "
                    "generating test data to compare with original hardware.");

REXCVAR_DEFINE_STRING(update_wad_variant, "", "Filesystem",
                      "Magic 2013 port: read mtg13_buttons_<variant>.bin in place of Update_Data_Core.wad when it exists "
                      "(the button icon style: ps, switch)");

REXCVAR_DEFINE_INT32(fs_slow_ms, 8, "Filesystem",
                     "Logs a lookup that waited more than this many ms for the process-wide critical region, or spent "
                     "it resolving, with both figures (0 = never).");

namespace rex::filesystem {

namespace {

/*
 * Where a slow lookup's time goes.
 *
 * The whole emulator shares ONE critical region (rex::thread::global_critical_region is a single recursive_mutex, see
 * rex/thread/mutex.h: "all activity done while in the critical region must be extremely fast (no IO!)"), and every
 * lookup here takes it. The console showed opens of game:\DATA_000.ZED of 120-260 ms (work/consola/mtg15_001.log)
 * while the pack device answers that name from memory, so either the lookup is waiting for the region or the thread
 * is not being scheduled; the two figures below tell them apart, and on the PC they are always microseconds.
 */
inline uint64_t NowUs() {
  return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                                   std::chrono::steady_clock::now().time_since_epoch())
                                   .count());
}

std::atomic<uint32_t> g_fs_slow_logged{0};

void NoteSlowLookup(const char* what, const std::string_view path, uint64_t lock_us,
                    uint64_t body_us) {
  // A lookup under 2 ms has nothing to say, and the cvar is not read on every call for it.
  if (lock_us < 2000 && body_us < 2000) {
    return;
  }
  const int32_t limit_ms = REXCVAR_GET(fs_slow_ms);
  if (limit_ms <= 0 || (lock_us < uint64_t(limit_ms) * 1000ull && body_us < uint64_t(limit_ms) * 1000ull)) {
    return;
  }
  if (g_fs_slow_logged.fetch_add(1, std::memory_order_relaxed) >= 200) {
    return;
  }
  REXFS_WARN("[fs] {}('{}'): waited {:.1f} ms for the global region, {:.2f} ms resolving", what, path,
             lock_us / 1000.0, body_us / 1000.0);
}

// Declared before the lock so that it reports after the region is released: logging inside it would put the SD write
// of the line in everyone else's way, which is exactly what is being measured.
struct LookupTiming {
  const char* what;
  std::string_view path;
  uint64_t lock_us = 0;
  uint64_t body_start_us = 0;
  ~LookupTiming() { NoteSlowLookup(what, path, lock_us, NowUs() - body_start_us); }
};

}  // namespace

VirtualFileSystem::VirtualFileSystem() {}

VirtualFileSystem::~VirtualFileSystem() {
  // Delete all devices.
  // This will explode if anyone is still using data from them.
  devices_.clear();
  symlinks_.clear();
}

bool VirtualFileSystem::RegisterDevice(std::unique_ptr<Device> device) {
  auto global_lock = global_critical_region_.Acquire();
  devices_.emplace_back(std::move(device));
  return true;
}

bool VirtualFileSystem::UnregisterDevice(const std::string_view path) {
  auto global_lock = global_critical_region_.Acquire();
  for (auto it = devices_.begin(); it != devices_.end(); ++it) {
    if ((*it)->mount_path() == path) {
      REXFS_DEBUG("Unregistered device: {}", (*it)->mount_path());
      devices_.erase(it);
      return true;
    }
  }
  return false;
}

bool VirtualFileSystem::RegisterSymbolicLink(const std::string_view path,
                                             const std::string_view target) {
  auto global_lock = global_critical_region_.Acquire();
  symlinks_.insert({std::string(path), std::string(target)});
  REXFS_DEBUG("Registered symbolic link: {} => {}", path, target);

  return true;
}

bool VirtualFileSystem::UnregisterSymbolicLink(const std::string_view path) {
  auto global_lock = global_critical_region_.Acquire();
  auto it = std::find_if(symlinks_.cbegin(), symlinks_.cend(), [&](const auto& s) {
    return rex::string::utf8_equal_case(path, s.first);
  });
  if (it == symlinks_.end()) {
    return false;
  }
  REXFS_DEBUG("Unregistered symbolic link: {} => {}", it->first, it->second);

  symlinks_.erase(it);
  return true;
}

bool VirtualFileSystem::FindSymbolicLink(const std::string_view path, std::string& target) {
  auto it = std::find_if(symlinks_.cbegin(), symlinks_.cend(), [&](const auto& s) {
    return rex::string::utf8_starts_with_case(path, s.first);
  });
  if (it == symlinks_.cend()) {
    return false;
  }
  target = (*it).second;
  return true;
}

bool VirtualFileSystem::ResolveSymbolicLink(const std::string_view path, std::string& result) {
  result = path;
  bool was_resolved = false;
  while (true) {
    auto it = std::find_if(symlinks_.cbegin(), symlinks_.cend(), [&](const auto& s) {
      return rex::string::utf8_starts_with_case(result, s.first);
    });
    if (it == symlinks_.cend()) {
      break;
    }
    // Found symlink!
    auto target_path = (*it).second;
    auto relative_path = result.substr((*it).first.size());
    result = target_path + relative_path;
    was_resolved = true;
  }
  return was_resolved;
}

// Magic 2013 port (2026-11-09): the button icon style. The game reads its title update's data only as Update_Data_Core.wad;
// with update_wad_variant = "ps" it gets mtg13_buttons_ps.bin (WAD data plus other icons) instead, when that file
// exists next to it. Null: not that file, or no variant.
// The variant's name for a path ending in Update_Data_Core.wad ("" when it does not, or there is no variant).
static std::string UpdateVariantName(std::string_view name) {
  const std::string variant = REXCVAR_GET(update_wad_variant);
  constexpr std::string_view kUpdateWad = "update_data_core.wad";
  if (variant.empty() || name.size() < kUpdateWad.size() ||
      !rex::string::utf8_equal_case(name.substr(name.size() - kUpdateWad.size()), kUpdateWad)) {
    return {};
  }
  // Keep the variants out of the game's Update*.wad discovery. Otherwise it
  // mounts every style and the last archive wins, regardless of the selection.
  return std::string(name.substr(0, name.size() - kUpdateWad.size())) +
         "mtg13_buttons_" + variant + ".bin";
}

static Entry* ResolveUpdateVariant(Device* device, const std::string& relative_path, std::string_view path) {
  const std::string other = UpdateVariantName(relative_path);
  if (other.empty()) return nullptr;
  Entry* entry = device->ResolvePath(other);
  static bool logged = false;
  if (!logged) {
    logged = true;
    REXFS_INFO("VFS: '{}' -> {}", path, entry ? other : std::string("(no variant file: the original)"));
  }
  return entry;
}

Entry* VirtualFileSystem::ResolvePath(const std::string_view path) {
  LookupTiming timing{"ResolvePath", path, 0, 0};
  const uint64_t wait_start_us = NowUs();
  auto global_lock = global_critical_region_.Acquire();
  timing.lock_us = NowUs() - wait_start_us;
  timing.body_start_us = NowUs();

  // Resolve relative paths
  auto normalized_path(rex::string::utf8_canonicalize_guest_path(path));

  // Resolve symlinks.
  std::string resolved_path;
  bool had_symlink = ResolveSymbolicLink(normalized_path, resolved_path);
  if (had_symlink) {
    normalized_path = resolved_path;
  }

  // Find the device.
  auto it = std::find_if(devices_.cbegin(), devices_.cend(), [&](const auto& d) {
    return rex::string::utf8_starts_with_case(normalized_path, d->mount_path());
  });
  if (it == devices_.cend() && normalized_path.find(':') == std::string::npos &&
      !normalized_path.empty() && normalized_path[0] != '\\') {
    // Magic 2013 port (2026-11-08): a path without a device ("DATA_CORE\LUBE\...", the game's search for loose
    // files before its WAD) is tried in the game folder (game:\), so a loose file there replaces the WAD's. Not
    // found there either: it fails quietly (the game makes thousands of such probes; two log lines each slowed the
    // console's SD down).
    std::string in_game;
    ResolveSymbolicLink("game:\\" + normalized_path, in_game);
    auto game_it = std::find_if(devices_.cbegin(), devices_.cend(), [&](const auto& d) {
      return rex::string::utf8_starts_with_case(in_game, d->mount_path());
    });
    if (game_it == devices_.cend()) {
      return nullptr;
    }
    const std::string in_device = in_game.substr((*game_it)->mount_path().size());
    Entry* entry = ResolveUpdateVariant(game_it->get(), in_device, path);
    if (!entry) entry = (*game_it)->ResolvePath(in_device);
    if (entry) {
      REXFS_INFO("VFS: '{}' -> loose file in the game folder", path);
    }
    return entry;
  }
  if (it == devices_.cend()) {
    REXFS_WARN("VFS: '{}' -> [no device]", path);
    // Supress logging the error for ShaderDumpxe:\CompareBackEnds as this is
    // not an actual problem nor something we care about.
    if (path != "ShaderDumpxe:\\CompareBackEnds") {
      REXFS_ERROR("ResolvePath({}) failed - device not found", path);
    }
    return nullptr;
  }

  const auto& device = *it;
  auto relative_path = normalized_path.substr(device->mount_path().size());
  Entry* entry = ResolveUpdateVariant(device.get(), relative_path, path);
  if (!entry) entry = device->ResolvePath(relative_path);

  // Magic 2013 port (2026-11-08): what the game looks up inside a downloadable content package (DLC), found or not.
  if (device->mount_path().find("\\Device\\Content") != std::string::npos) {
    REXFS_INFO("VFS: DLC '{}' -> {}", path, entry ? "found" : "not found");
  }

  if (entry) {
    if (had_symlink) {
      REXFS_TRACE("VFS resolved '{}' via symlink '{}' on device '{}' -> '{}'", path,
                  normalized_path, device->mount_path(), entry->absolute_path());
    } else {
      REXFS_TRACE("VFS resolved '{}' on device '{}' -> '{}'", path, device->mount_path(),
                  entry->absolute_path());
    }
  } else {
    if (had_symlink) {
      REXFS_DEBUG("VFS: entry not found for '{}' (via symlink '{}') on device '{}'", path,
                  normalized_path, device->mount_path());
    } else {
      REXFS_DEBUG("VFS: entry not found for '{}' on device '{}'", path, device->mount_path());
    }
  }

  return entry;
}

Entry* VirtualFileSystem::CreatePath(const std::string_view path, uint32_t attributes) {
  // Create all required directories recursively.
  auto path_parts = rex::string::utf8_split_path(path);
  if (path_parts.empty()) {
    return nullptr;
  }
  auto partial_path = std::string(path_parts[0]);
  auto partial_entry = ResolvePath(partial_path);
  if (!partial_entry) {
    return nullptr;
  }
  auto parent_entry = partial_entry;
  for (size_t i = 1; i < path_parts.size() - 1; ++i) {
    partial_path = rex::string::utf8_join_guest_paths(partial_path, path_parts[i]);
    auto child_entry = ResolvePath(partial_path);
    if (!child_entry) {
      child_entry = parent_entry->CreateEntry(path_parts[i], kFileAttributeDirectory);
    }
    if (!child_entry) {
      return nullptr;
    }
    parent_entry = child_entry;
  }
  return parent_entry->CreateEntry(path_parts[path_parts.size() - 1], attributes);
}

bool VirtualFileSystem::DeletePath(const std::string_view path) {
  auto entry = ResolvePath(path);
  if (!entry) {
    return false;
  }
  auto parent = entry->parent();
  if (!parent) {
    // Can't delete root.
    return false;
  }
  return parent->Delete(entry);
}

X_STATUS VirtualFileSystem::OpenFile(Entry* root_entry, const std::string_view path,
                                     FileDisposition creation_disposition, uint32_t desired_access,
                                     bool is_directory, bool is_non_directory, File** out_file,
                                     FileAction* out_action) {
  // TODO(gibbed): should 'is_directory' remain as a bool or should it be
  // flipped to a generic FileAttributeFlags?

  // OpenFile takes no lock of its own (ResolvePath and the entries take the region), so this reports the time spent
  // inside it; the inner lookups report their own wait.
  LookupTiming timing{"OpenFile", path, 0, NowUs()};

  // Cleanup access.
  if (desired_access & FileAccess::kGenericRead) {
    desired_access |= FileAccess::kFileReadData;
  }
  if (desired_access & FileAccess::kGenericWrite) {
    desired_access |= FileAccess::kFileWriteData;
  }
  if (desired_access & FileAccess::kGenericAll) {
    desired_access |= FileAccess::kFileReadData | FileAccess::kFileWriteData;
  }

  // Lookup host device/parent path.
  // If no device or parent, fail.
  Entry* parent_entry = nullptr;
  Entry* entry = nullptr;

  auto base_path = rex::string::utf8_find_base_guest_path(path);
  if (!base_path.empty()) {
    parent_entry = !root_entry ? ResolvePath(base_path) : root_entry->ResolvePath(base_path);
    if (!parent_entry) {
      *out_action = FileAction::kDoesNotExist;
      return X_STATUS_NO_SUCH_FILE;
    }

    auto file_name = rex::string::utf8_find_name_from_guest_path(path);
    const std::string other = UpdateVariantName(file_name);
    if (!other.empty()) entry = parent_entry->GetChild(other);
    if (!entry) entry = parent_entry->GetChild(file_name);
  } else if (root_entry) {
    const std::string other = UpdateVariantName(path);
    if (!other.empty()) entry = root_entry->GetChild(other);
    if (!entry) entry = root_entry->GetChild(path);
  } else {
    entry = ResolvePath(path);
  }

  if (entry) {
    if (entry->attributes() & kFileAttributeDirectory && is_non_directory) {
      return X_STATUS_FILE_IS_A_DIRECTORY;
    }

    /*
     * If the cached entry does not exist on host anymore, invalidate it.
     *
     * Only on writable devices. This was a stat to the SD on every successful open, and on a
     * read-only device (the game data) it can never say no: the file was there at mount time and
     * nobody deletes it during play. On writable devices (saves and profiles) it is needed, because
     * the game itself deletes and recreates files and the in-memory entry goes stale; that case is
     * unchanged.
     */
    if (parent_entry && !parent_entry->is_read_only()) {
      const auto* host_path_entry = dynamic_cast<const HostPathEntry*>(parent_entry);
      if (host_path_entry) {
        const auto file_path = host_path_entry->host_path() / rex::to_path(entry->name());
        if (!std::filesystem::exists(file_path)) {
          entry->Delete();
          entry = nullptr;
        }
      }
    }
  }

  // Check if exists (if we need it to), or that it doesn't (if it shouldn't).
  switch (creation_disposition) {
    case FileDisposition::kOpen:
    case FileDisposition::kOverwrite:
      // Must exist.
      if (!entry) {
        *out_action = FileAction::kDoesNotExist;
        return X_STATUS_NO_SUCH_FILE;
      }
      break;
    case FileDisposition::kCreate:
      // Must not exist.
      if (entry) {
        *out_action = FileAction::kExists;
        return X_STATUS_OBJECT_NAME_COLLISION;
      }
      break;
    default:
      // Either way, ok.
      break;
  }

  // Verify permissions.
  bool wants_write =
      desired_access & FileAccess::kFileWriteData || desired_access & FileAccess::kFileAppendData;
  if (wants_write &&
      ((parent_entry && parent_entry->is_read_only()) || (entry && entry->is_read_only()))) {
    // Match Xenia behavior: downgrade to read access instead of failing.
    REXFS_WARN("Attempted to open read-only file/dir for write: {}", path);
    desired_access = FileAccess::kGenericRead | FileAccess::kFileReadData;
  }

  bool created = false;
  if (!entry) {
    // Remember that we are creating this new, instead of replacing.
    created = true;
    *out_action = FileAction::kCreated;
  } else {
    // May need to delete, if it exists.
    switch (creation_disposition) {
      case FileDisposition::kCreate:
        // Shouldn't be possible to hit this.
        assert_always();
        return X_STATUS_ACCESS_DENIED;
      case FileDisposition::kSuperscede:
        // Replace (by delete + recreate).
        if (!entry->Delete()) {
          return X_STATUS_ACCESS_DENIED;
        }
        entry = nullptr;
        *out_action = FileAction::kSuperseded;
        break;
      case FileDisposition::kOpen:
      case FileDisposition::kOpenIf:
        // Normal open.
        *out_action = FileAction::kOpened;
        break;
      case FileDisposition::kOverwrite:
      case FileDisposition::kOverwriteIf:
        // Overwrite by delete + recreate, or truncate if delete fails
        // (host file may be briefly locked by cloud sync, AV, etc.).
        if (entry->Delete()) {
          entry = nullptr;
        } else if (!entry->Truncate()) {
          return X_STATUS_ACCESS_DENIED;
        }
        *out_action = FileAction::kOverwritten;
        break;
    }
  }
  if (!entry) {
    // Create if needed (either new or as a replacement).
    entry = CreatePath(path, !is_directory ? kFileAttributeNormal : kFileAttributeDirectory);
    if (!entry) {
      return X_STATUS_ACCESS_DENIED;
    }
  }

  // Open.
  auto result = entry->Open(desired_access, out_file);
  if (XFAILED(result)) {
    *out_action = FileAction::kDoesNotExist;
  }
  return result;
}

}  // namespace rex::filesystem
