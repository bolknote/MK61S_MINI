#ifndef STORAGE_GEOMETRY_HPP
#define STORAGE_GEOMETRY_HPP

#include "rust_types.h"

namespace storage_geometry {

// Physical SPI NOR geometry used by C5. The virtual FAT sector remains 512
// bytes; physical erase sectors are never exposed to the USB host.
static constexpr u32 PHYSICAL_SECTOR_SIZE = 4096;
static constexpr u16 LOGICAL_SECTOR_SIZE = 512;
static constexpr u16 FAT12_MAX_DATA_CLUSTERS = 4084;
static constexpr u8 MIN_SECTORS_PER_CLUSTER = 4;   // 2 KiB, one 1536-byte file
static constexpr u8 MAX_SECTORS_PER_CLUSTER = 64;  // 32 KiB, broadly portable

static constexpr u8 LOCATOR_SECTORS = 2;
static constexpr u8 SETTINGS_SECTORS = 1;
static constexpr u8 CATALOG_HEADER_SECTORS = 1;
static constexpr u8 CATALOG_WAL_SECTORS = 2;
static constexpr u8 CATALOG_BANKS = 2;
// Sixty-four normal log segments hold 448 physical records for at most 384
// live dirty blocks. The final segment is an atomic compaction reserve.  The
// extra 192 KiB is negligible on the common 16 MiB part and prevents modern
// desktop filesystems from exhausting staging before issuing cache sync.
static constexpr u8 STAGE_TARGET_SECTORS = 65;
static constexpr u8 STAGE_SMALL_SECTORS = 17;
static constexpr u8 STAGE_MIN_SECTORS = 4;
static constexpr u16 STAGE_TARGET_MIN_PHYSICAL_SECTORS = 512; // 2 MiB

// A C5 inode is 20 bytes on flash. A 31-byte basename plus the longest
// generated extension needs at most four LFN entries and one short entry.
static constexpr u8 INODE_BYTES = 20;
static constexpr u8 MAX_DIRENTS_PER_NODE = 5;
// Volume label plus the three entries (two LFN and one short entry) required
// for macOS' zero-length .metadata_never_index marker.
static constexpr u8 ROOT_SYSTEM_DIRENTS = 4;
// FAT12/FAT16 roots are fixed-size arrays rather than ordinary cluster
// chains.  Sizing that array for every possible C5 node made a 16 MiB root
// 630 KiB large; desktop FAT drivers may rewrite much of it for every created
// entry.  512 entries is the conventional portable geometry and still leaves
// 508 entries for user objects.  Arbitrary subdirectories use cluster chains
// and provide the full volume-wide node quota.
static constexpr u16 ROOT_ENTRY_CAPACITY = 512;

struct Geometry {
  u32 capacity_bytes;
  u32 physical_sectors;

  u32 locator_a_sector;
  u32 locator_b_sector;
  u32 catalog_a_sector;
  u32 catalog_b_sector;
  u16 catalog_table_sectors;
  u16 catalog_bank_sectors;
  u32 data_first_sector;
  u32 data_sector_count;
  u32 stage_first_sector;
  u16 stage_sector_count;
  u32 settings_sector;

  u16 max_nodes;
  u8 sectors_per_cluster;
  u16 fat_sectors;
  u16 root_entries;
  u16 root_sectors;
  u32 logical_sectors;
};

// Computes a self-consistent layout. Returns false for chips too small for
// two atomic catalog banks, a staging journal, settings, and a GC reserve.
bool compute(u32 capacity_bytes, Geometry& out);

} // namespace storage_geometry

#endif
