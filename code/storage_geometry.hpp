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
// Sixteen normal log segments hold 112 physical records for at most 96 live
// dirty blocks. The seventeenth segment is an atomic compaction reserve.
static constexpr u8 STAGE_TARGET_SECTORS = 17;
static constexpr u8 STAGE_MIN_SECTORS = 4;

// A C5 inode is 20 bytes on flash. A 31-byte basename plus the longest
// generated extension needs at most four LFN entries and one short entry.
static constexpr u8 INODE_BYTES = 20;
static constexpr u8 MAX_DIRENTS_PER_NODE = 5;

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
