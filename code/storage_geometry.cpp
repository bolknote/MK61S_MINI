#include "storage_geometry.hpp"

#include <string.h>

namespace storage_geometry {
namespace {
static u32 ceil_div(u32 value, u32 divisor) {
  return value / divisor + (value % divisor != 0 ? 1U : 0U);
}
static u8 cluster_sectors_for(u32 logical_sectors) {
  const u32 ratio = logical_sectors / FAT12_MAX_DATA_CLUSTERS;
  u8 result = MIN_SECTORS_PER_CLUSTER;
  while(result < MAX_SECTORS_PER_CLUSTER && (u32) result * 2U <= ratio) {
    result = (u8) (result * 2U);
  }
  return result;
}
static u16 fat_sectors_for(u16 clusters) {
  return (u16) ceil_div(ceil_div(((u32) clusters + 2U) * 3U, 2U), LOGICAL_SECTOR_SIZE);
}
static u32 virtual_sectors_for(u16 clusters, u8 sectors_per_cluster,
                               u16& fat, u16& entries, u16& root) {
  fat = fat_sectors_for(clusters);
  entries = ROOT_ENTRY_CAPACITY;
  root = ROOT_ENTRY_CAPACITY / 16U;
  return 1U + 2U * fat + root + (u32) clusters * sectors_per_cluster;
}
static u16 virtual_cluster_limit(u32 capacity, u8 sectors_per_cluster) {
  u16 low = 1, high = FAT12_MAX_DATA_CLUSTERS, best = 0;
  while(low <= high) {
    const u16 middle = (u16) (low + (high - low) / 2U);
    u16 fat = 0, entries = 0, root = 0;
    if(virtual_sectors_for(middle, sectors_per_cluster, fat, entries, root) <= capacity) {
      best = middle;
      low = (u16) (middle + 1U);
    } else high = (u16) (middle - 1U);
  }
  return best;
}
static u16 stage_sectors_for(u32 sectors) {
  if(sectors >= STAGE_TARGET_MIN_PHYSICAL_SECTORS) return STAGE_TARGET_SECTORS;
  if(sectors >= 128U) return STAGE_SMALL_SECTORS;
  const u16 proportional = (u16) (sectors / 8U);
  return proportional < STAGE_MIN_SECTORS ? STAGE_MIN_SECTORS : proportional;
}
}

u16 fat_cluster_capacity(const Geometry& geometry) {
  const u32 overhead = 1U + 2U * geometry.fat_sectors + geometry.root_sectors;
  if(geometry.sectors_per_cluster == 0 || geometry.logical_sectors < overhead) return 0;
  const u32 clusters = (geometry.logical_sectors - overhead) / geometry.sectors_per_cluster;
  return clusters <= FAT12_MAX_DATA_CLUSTERS ? (u16) clusters : 0;
}
u32 import_scratch_first_sector(const Geometry& geometry) {
  return geometry.catalog_b_sector + geometry.catalog_bank_sectors;
}
u16 fat_reverse_sector_count(const Geometry& geometry) {
  const u32 windows = ceil_div(fat_cluster_capacity(geometry), 32U);
  return (u16) ceil_div(windows, 4096U / 200U);
}
u16 fat_name_index_sector_count(const Geometry& geometry) {
  return (u16) ceil_div(ceil_div((u32) geometry.max_nodes * 2U, 64U), 4096U / 136U);
}
u16 import_scratch_sector_count(const Geometry& geometry) {
  return (u16) (fat_reverse_sector_count(geometry) + fat_name_index_sector_count(geometry) + ceil_div((u32) fat_cluster_capacity(geometry) * 4U +
                         (u32) geometry.max_nodes * 14U, PHYSICAL_SECTOR_SIZE));
}

bool compute(u32 capacity_bytes, Geometry& out) {
  memset(&out, 0, sizeof(out));
  if(capacity_bytes < PHYSICAL_SECTOR_SIZE * 32U ||
     capacity_bytes > MAX_CAPACITY_BYTES ||
     capacity_bytes % PHYSICAL_SECTOR_SIZE != 0) return false;
  const u32 physical = capacity_bytes / PHYSICAL_SECTOR_SIZE;
  u32 logical_capacity = capacity_bytes / LOGICAL_SECTOR_SIZE;
  // A desktop FAT host retains AppleDouble chains until unmount. Give small
  // C9 volumes enough logical cluster addresses for those disposable files;
  // COW record allocation still enforces the physical NOR capacity.
  if(physical - 128U < 384U) logical_capacity = 4096U;
  const u8 cluster_sectors = cluster_sectors_for(logical_capacity);
  const u16 clusters = virtual_cluster_limit(logical_capacity, cluster_sectors);
  if(clusters < 8U) return false;

  // The inode quota budgets metadata, independently of payload or FAT clusters.
  const u32 target_nodes = physical * NODES_PER_PHYSICAL_SECTOR;
  const u16 nodes = (u16) (target_nodes < MAX_NODES ? target_nodes : MAX_NODES);
  const u16 pages = (u16) ceil_div((u32) nodes * INODE_BYTES, PHYSICAL_SECTOR_SIZE);
  const u16 bank = (u16) (CATALOG_HEADER_SECTORS + pages + CATALOG_WAL_SECTORS);
  const u16 stage = stage_sectors_for(physical);

  out.capacity_bytes = capacity_bytes;
  out.physical_sectors = physical;
  out.locator_a_sector = 0;
  out.locator_b_sector = 1;
  out.catalog_a_sector = LOCATOR_SECTORS;
  out.catalog_b_sector = LOCATOR_SECTORS + bank;
  out.catalog_table_sectors = pages;
  out.catalog_bank_sectors = bank;
  out.max_nodes = nodes;
  out.sectors_per_cluster = cluster_sectors;
  out.logical_sectors = virtual_sectors_for(clusters, cluster_sectors,
      out.fat_sectors, out.root_entries, out.root_sectors);
  out.data_first_sector = import_scratch_first_sector(out) + import_scratch_sector_count(out);
  out.settings_sector = physical - 1U;
  out.stage_sector_count = stage;
  out.stage_first_sector = out.settings_sector - stage;
  if(out.stage_first_sector <= out.data_first_sector + 4U) {
    memset(&out, 0, sizeof(out));
    return false;
  }
  out.data_sector_count = out.stage_first_sector - out.data_first_sector;
  return true;
}
}
