/**
 * @file        rex/filesystem/devices/pack_device.h
 * @brief       Read-only game data served from one pack file (the asset cache)
 *
 * Ported from Fruit Ninja NX's asset pack (fruitninja_nx/source/asset_pack.c, same on-disk format, version 2):
 * every file of a game data folder is stored back to back (16-byte aligned) in <folder>.nxpack, with a sorted path
 * index in <folder>.nxidx. On the Switch each file open on the SD card is an fs IPC plus a FAT directory walk; a
 * game that opens thousands of small files (SA2: ~1,800 in gd/) spends its loading screens on that. With the pack,
 * the whole folder is one file that stays open and every read is a positional read into it.
 *
 * Format (little endian):
 *   <folder>.nxpack: PackHeader, then the file data, each file at a 16-byte aligned offset.
 *   <folder>.nxidx:  IndexHeader, DiskEntry[count] sorted by path (strcmp), then the NUL-terminated paths
 *                    ('/'-separated, relative to the folder).
 *   Checksums are 64-bit FNV-1a: the index one covers the entries and the paths, the data one every file byte.
 * tools/build_asset_pack.py writes the same files on a PC; PackDevice::Build writes them on the console.
 */

#pragma once

#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <rex/filesystem/device.h>
#include <rex/filesystem/entry.h>
#include <rex/filesystem/file.h>

namespace rex::filesystem {

// Positional reads from the pack file, safe from several threads at once.
class PackStorage {
 public:
  virtual ~PackStorage() = default;
  // Exactly `size` bytes at `offset`, or false.
  virtual bool ReadAt(uint64_t offset, void* buffer, size_t size) = 0;
  static std::unique_ptr<PackStorage> Open(const std::filesystem::path& path);
};

class PackDevice;

class PackEntry : public Entry {
 public:
  PackEntry(Device* device, Entry* parent, const std::string_view path);
  ~PackEntry() override;

  X_STATUS Open(uint32_t desired_access, File** out_file) override;

  uint64_t data_offset() const { return data_offset_; }
  PackDevice* pack() const { return pack_; }

  // Small reads (<= half the window) are served from a 64 KB window of this file, as asset_pack.c does, but the
  // window belongs to the file and not to each open handle. Magic 2015 opens DATA_000.ZED again for nearly every
  // header read (66 opens in 14 s on the console, work/consola/mtg15_001.log), and with a window per handle every
  // one of those opens started cold: 95 reads of 256-8192 bytes at ~20 ms each, 24 of them the exact same range
  // read again (the log marks them REREAD). Copies `length` bytes at `offset` into `buffer`; false on a read error.
  bool ReadWindowed(uint8_t* buffer, size_t length, uint64_t offset);

 private:
  friend class PackDevice;
  PackDevice* pack_ = nullptr;
  uint64_t data_offset_ = 0;
  std::mutex window_mutex_;
  std::vector<uint8_t> window_;
  uint64_t window_offset_ = 0;
  size_t window_size_ = 0;
};

class PackFile : public File {
 public:
  PackFile(uint32_t file_access, PackEntry* entry);
  ~PackFile() override;

  void Destroy() override;
  X_STATUS ReadSync(std::span<uint8_t> buffer, size_t byte_offset, size_t* out_bytes_read) override;
  X_STATUS WriteSync(std::span<const uint8_t> /*buffer*/, size_t /*byte_offset*/,
                     size_t* /*out_bytes_written*/) override {
    return X_STATUS_ACCESS_DENIED;
  }
  X_STATUS SetLength(size_t /*length*/) override { return X_STATUS_ACCESS_DENIED; }

 private:
  PackEntry* pack_entry_;
};

class PackDevice : public Device {
 public:
  PackDevice(const std::string_view mount_path, const std::filesystem::path& folder);
  ~PackDevice() override;

  // The pack files of a data folder: <folder>.nxpack and <folder>.nxidx, next to it.
  static std::filesystem::path PackPath(const std::filesystem::path& folder);
  static std::filesystem::path IndexPath(const std::filesystem::path& folder);
  static bool Exists(const std::filesystem::path& folder);
  // Builds the pack of `folder` (first boot on the console). Written to temporary files, read back and checked,
  // then renamed into place; the folder itself is left as it is. `progress` gets 0..100.
  static bool Build(const std::filesystem::path& folder, std::string* error,
                    const std::function<void(const char* stage, uint32_t percent)>& progress = {});

  bool Initialize() override;
  void Dump(string::StringBuffer* string_buffer) override;
  Entry* ResolvePath(const std::string_view path) override;
  bool is_read_only() const override { return true; }

  const std::string& name() const override { return name_; }
  uint32_t attributes() const override { return 0; }
  uint32_t component_name_max_length() const override { return 255; }
  uint32_t total_allocation_units() const override { return 128 * 1024; }
  uint32_t available_allocation_units() const override { return 0; }
  uint32_t sectors_per_allocation_unit() const override { return 1; }
  uint32_t bytes_per_sector() const override { return 0x200; }

  PackStorage* storage() const { return storage_.get(); }
  size_t entry_count() const { return entry_count_; }

 private:
  std::string name_ = "PACK";
  std::filesystem::path folder_;
  std::unique_ptr<PackStorage> storage_;
  std::unique_ptr<PackEntry> root_entry_;
  size_t entry_count_ = 0;
};

}  // namespace rex::filesystem
