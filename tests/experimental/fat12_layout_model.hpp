#ifndef MK61_FAT12_LAYOUT_MODEL_HPP
#define MK61_FAT12_LAYOUT_MODEL_HPP

#include "../../code/storage_geometry.hpp"

#include <string.h>

namespace fat12_layout_model {

// Independent C9 layout calculation, including all transient scratch reserves.
static constexpr u16 MAX_NODES = 8192;
static constexpr u8 INODE_BYTES = 26;
static constexpr u8 NODES_PER_PHYSICAL_SECTOR = 8;
static constexpr u8 CATALOG_PAGES =
    (MAX_NODES * INODE_BYTES + 4095U) / 4096U;
static_assert(80U + CATALOG_PAGES * 8U + 8U <= 508U,
              "Candidate mapping must fit the existing catalog root");

struct Layout {
  storage_geometry::Geometry geometry;
  u16 clusters;
  u16 directory_chain_clusters;
};

inline u32 ceil_div(u32 value, u32 divisor) {
  return value / divisor + (value % divisor != 0 ? 1U : 0U);
}

inline bool compute(u32 capacity, Layout& output) {
  output = {};
  using namespace storage_geometry;
  if(capacity < PHYSICAL_SECTOR_SIZE * 32U ||
     capacity > 128U * 1024U * 1024U ||
     capacity % PHYSICAL_SECTOR_SIZE != 0) return false;
  const u32 physical = capacity / PHYSICAL_SECTOR_SIZE;
  u32 sectors = capacity / LOGICAL_SECTOR_SIZE;
  if(physical >= 128U && sectors < 4096U) sectors = 4096U;
  u8 cluster_sectors = 1;
  while(cluster_sectors < MAX_SECTORS_PER_CLUSTER &&
        (u32) cluster_sectors * 2U <= sectors / FAT12_MAX_DATA_CLUSTERS) {
    cluster_sectors = (u8) (cluster_sectors * 2U);
  }
  u16 best = 0;
  u16 fat = 0;
  u16 root_entries = 0;
  u16 root_sectors = 0;
  u32 logical = 0;
  for(u16 clusters = 1; clusters <= FAT12_MAX_DATA_CLUSTERS; ++clusters) {
    const u16 next_fat = (u16) ceil_div(
        ceil_div(((u32) clusters + 2U) * 3U, 2U), LOGICAL_SECTOR_SIZE);
    const u32 entries = ROOT_ENTRY_CAPACITY;
    const u16 next_root = (u16) (entries * 32U / LOGICAL_SECTOR_SIZE);
    const u32 next_logical =
        1U + 2U * next_fat + next_root + (u32) clusters * cluster_sectors;
    if(next_logical > sectors) break;
    best = clusters;
    fat = next_fat;
    root_entries = (u16) entries;
    root_sectors = next_root;
    logical = next_logical;
  }
  const u32 target_nodes = physical * NODES_PER_PHYSICAL_SECTOR;
  const u16 nodes = (u16) (target_nodes < MAX_NODES ? target_nodes : MAX_NODES);
  const u16 pages = (u16) ceil_div((u32) nodes * INODE_BYTES, PHYSICAL_SECTOR_SIZE);
  const u16 bank = (u16) (pages + CATALOG_HEADER_SECTORS + CATALOG_WAL_SECTORS);
  const u16 stage = physical >= STAGE_TARGET_MIN_PHYSICAL_SECTORS
      ? STAGE_TARGET_SECTORS : physical >= 128U ? STAGE_SMALL_SECTORS
      : (u16) (physical / 8U < STAGE_MIN_SECTORS ? STAGE_MIN_SECTORS : physical / 8U);
  const u32 overhead = LOCATOR_SECTORS + SETTINGS_SECTORS + stage + 2U * bank;
  if(best == 0 || overhead + 4U >= physical) return false;
  Geometry& geometry = output.geometry;
  geometry.capacity_bytes = capacity;
  geometry.physical_sectors = physical;
  geometry.locator_a_sector = 0;
  geometry.locator_b_sector = 1;
  geometry.catalog_a_sector = LOCATOR_SECTORS;
  geometry.catalog_b_sector = LOCATOR_SECTORS + bank;
  geometry.catalog_table_sectors = pages;
  geometry.catalog_bank_sectors = bank;
  geometry.data_first_sector = LOCATOR_SECTORS + 2U * bank;
  geometry.settings_sector = physical - 1U;
  geometry.stage_sector_count = stage;
  geometry.stage_first_sector = geometry.settings_sector - stage;
  geometry.max_nodes = nodes;
  geometry.sectors_per_cluster = cluster_sectors;
  geometry.fat_sectors = fat;
  geometry.root_entries = root_entries;
  geometry.root_sectors = root_sectors;
  geometry.logical_sectors = logical;
  const u32 reverse = ceil_div(ceil_div(best, 32U), 4096U / 200U);
  const u32 name_index = ceil_div(ceil_div((u32) nodes * 2U, 64U), 4096U / 136U);
  const u32 plan = ceil_div((u32) best * 4U + (u32) nodes * 14U, 4096U);
  geometry.data_first_sector += reverse + name_index + plan;
  if(geometry.stage_first_sector <= geometry.data_first_sector + 4U) return false;
  geometry.data_sector_count = geometry.stage_first_sector - geometry.data_first_sector;
  output.clusters = best;
  output.directory_chain_clusters = (u16) ceil_div(
      (u32) nodes * MAX_DIRENTS_PER_NODE + 2U,
      (u32) cluster_sectors * (LOGICAL_SECTOR_SIZE / 32U));
  return true;
}
} // namespace fat12_layout_model
#endif
