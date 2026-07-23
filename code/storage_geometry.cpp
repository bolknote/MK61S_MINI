#include "storage_geometry.hpp"

#include <string.h>

namespace storage_geometry {
namespace {

static u32 ceil_div(u32 value, u32 divisor) {
  return (value + divisor - 1) / divisor;
}

static u8 cluster_sectors_for(u32 logical_sectors) {
  const u32 ratio = logical_sectors / FAT12_MAX_DATA_CLUSTERS;
  u8 result = MIN_SECTORS_PER_CLUSTER;
  while(result < MAX_SECTORS_PER_CLUSTER && (u32) result * 2 <= ratio) {
    result = (u8) (result * 2);
  }
  return result;
}

static u16 fat_sectors_for(u16 nodes) {
  const u32 entries = (u32) nodes + 2;
  const u32 bytes = (entries * 3 + 1) / 2;
  return (u16) ceil_div(bytes, LOGICAL_SECTOR_SIZE);
}

static u16 root_entries_for(u16 nodes) {
  u32 entries = (u32) nodes * MAX_DIRENTS_PER_NODE + ROOT_SYSTEM_DIRENTS;
  if(entries > ROOT_ENTRY_CAPACITY) entries = ROOT_ENTRY_CAPACITY;
  entries = (entries + 15) & ~15UL;
  return (u16) entries;
}

static u32 virtual_sectors_for(u16 nodes, u8 sectors_per_cluster,
                               u16& fat_sectors, u16& root_entries,
                               u16& root_sectors) {
  fat_sectors = fat_sectors_for(nodes);
  root_entries = root_entries_for(nodes);
  root_sectors = (u16) ceil_div((u32) root_entries * 32, LOGICAL_SECTOR_SIZE);
  return 1 + (u32) CATALOG_BANKS * fat_sectors + root_sectors +
         (u32) nodes * sectors_per_cluster;
}

static u16 virtual_node_limit(u32 logical_capacity, u8 sectors_per_cluster) {
  u16 low = 1;
  u16 high = FAT12_MAX_DATA_CLUSTERS;
  u16 best = 0;
  while(low <= high) {
    const u16 middle = (u16) (low + (high - low) / 2);
    u16 fat = 0;
    u16 root_entries = 0;
    u16 root = 0;
    const u32 sectors = virtual_sectors_for(middle, sectors_per_cluster,
                                            fat, root_entries, root);
    if(sectors <= logical_capacity) {
      best = middle;
      low = (u16) (middle + 1);
    } else {
      high = (u16) (middle - 1);
    }
  }
  return best;
}

static u16 stage_sectors_for(u32 physical_sectors) {
  if(physical_sectors >= STAGE_TARGET_MIN_PHYSICAL_SECTORS) {
    return STAGE_TARGET_SECTORS;
  }
  if(physical_sectors >= 128) return STAGE_SMALL_SECTORS;
  const u16 proportional = (u16) (physical_sectors / 8);
  return proportional < STAGE_MIN_SECTORS ? STAGE_MIN_SECTORS : proportional;
}

} // пространство имён

bool compute(u32 capacity_bytes, Geometry& out) {
  memset(&out, 0, sizeof(out));
  if(capacity_bytes < PHYSICAL_SECTOR_SIZE * 32 ||
     capacity_bytes % PHYSICAL_SECTOR_SIZE != 0) return false;

  const u32 physical_sectors = capacity_bytes / PHYSICAL_SECTOR_SIZE;
  const u32 logical_capacity = capacity_bytes / LOGICAL_SECTOR_SIZE;
  const u8 sectors_per_cluster = cluster_sectors_for(logical_capacity);
  u16 nodes = virtual_node_limit(logical_capacity, sectors_per_cluster);
  if(nodes < 8) return false;

  const u16 stage_sectors = stage_sectors_for(physical_sectors);
  u16 table_sectors = 0;
  u16 bank_sectors = 0;
  u32 data_sectors = 0;

  // Число inode определяет размер каталога, а размер каталога — физический
  // предел числа inode в худшем случае. Для каждой поддерживаемой NOR со
  // степенной ёмкостью расчёт монотонно сходится за несколько итераций.
  for(u8 iteration = 0; iteration < 8; iteration++) {
    table_sectors = (u16) ceil_div((u32) nodes * INODE_BYTES,
                                   PHYSICAL_SECTOR_SIZE);
    bank_sectors = (u16) (CATALOG_HEADER_SECTORS + table_sectors +
                          CATALOG_WAL_SECTORS);
    const u32 overhead = LOCATOR_SECTORS + SETTINGS_SECTORS + stage_sectors +
                         (u32) CATALOG_BANKS * bank_sectors;
    if(overhead + 4 >= physical_sectors) return false;
    data_sectors = physical_sectors - overhead;

    // Исходная запись C5 максимального размера немного больше 1,5 КиБ, поэтому
    // в сектор стирания помещаются ровно две. Оставляем вне квоты два сектора,
    // чтобы запись и GC продвигались даже при худшем размере каждого файла.
    const u32 physical_limit = (data_sectors - 2) * 2;
    const u16 next = physical_limit < nodes ? (u16) physical_limit : nodes;
    if(next == nodes) break;
    nodes = next;
  }

  if(nodes < 8) return false;
  table_sectors = (u16) ceil_div((u32) nodes * INODE_BYTES,
                                 PHYSICAL_SECTOR_SIZE);
  bank_sectors = (u16) (CATALOG_HEADER_SECTORS + table_sectors +
                        CATALOG_WAL_SECTORS);

  out.capacity_bytes = capacity_bytes;
  out.physical_sectors = physical_sectors;
  out.locator_a_sector = 0;
  out.locator_b_sector = 1;
  out.catalog_a_sector = LOCATOR_SECTORS;
  out.catalog_b_sector = out.catalog_a_sector + bank_sectors;
  out.catalog_table_sectors = table_sectors;
  out.catalog_bank_sectors = bank_sectors;
  out.data_first_sector = out.catalog_b_sector + bank_sectors;
  out.settings_sector = physical_sectors - 1;
  out.stage_sector_count = stage_sectors;
  out.stage_first_sector = out.settings_sector - stage_sectors;
  if(out.stage_first_sector <= out.data_first_sector + 2) return false;
  out.data_sector_count = out.stage_first_sector - out.data_first_sector;

  out.max_nodes = nodes;
  out.sectors_per_cluster = sectors_per_cluster;
  out.logical_sectors = virtual_sectors_for(nodes, sectors_per_cluster,
                                             out.fat_sectors,
                                             out.root_entries,
                                             out.root_sectors);
  if(out.logical_sectors > logical_capacity || nodes > FAT12_MAX_DATA_CLUSTERS) {
    memset(&out, 0, sizeof(out));
    return false;
  }
  return true;
}

} // пространство имён storage_geometry
