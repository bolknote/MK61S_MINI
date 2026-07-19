#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "SPIFlash.h"
#include "ledcontrol.h"
#include "program_store.hpp"
#include "virtual_fat.hpp"

SPIFlash flash;
bool flash_is_ok = true;

namespace led {
void init(void) {}
void on(void) {}
void off(void) {}
void blink(usize, t_time_ms, t_time_ms) {}
void blink_continuous(t_time_ms, t_time_ms) {}
void blink_stop(void) {}
bool pattern_start(const PatternStep*, usize) { return true; }
void control(void) {}
void control(t_time_ms) {}
} // namespace led

namespace {

static u16 read_le16(const u8* data, u16 offset) {
  return (u16) (data[offset] | ((u16) data[offset + 1] << 8));
}

static u32 read_le32(const u8* data, u16 offset) {
  return (u32) data[offset] |
         ((u32) data[offset + 1] << 8) |
         ((u32) data[offset + 2] << 16) |
         ((u32) data[offset + 3] << 24);
}

static void write_le16(u8* data, u16 offset, u16 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
}

static void write_le32(u8* data, u16 offset, u32 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
  data[offset + 2] = (u8) (value >> 16);
  data[offset + 3] = (u8) (value >> 24);
}

struct Layout {
  u8 sectors_per_cluster;
  u16 fat_sectors;
  u16 root_entries;
  u32 root_start;
  u32 root_sectors;
  u32 data_start;
  u32 total_sectors;
};

static Layout layout(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  Layout result = {};
  assert(read_le16(boot, 11) == virtual_fat::SECTOR_SIZE);
  result.sectors_per_cluster = boot[13];
  const u16 reserved = read_le16(boot, 14);
  assert(reserved == 1 && boot[16] == 2);
  result.fat_sectors = read_le16(boot, 22);
  result.root_entries = read_le16(boot, 17);
  result.root_start = reserved + (u32) boot[16] * result.fat_sectors;
  result.root_sectors = ((u32) result.root_entries * 32 + 511) / 512;
  result.data_start = result.root_start + result.root_sectors;
  result.total_sectors = read_le16(boot, 19);
  if(result.total_sectors == 0) result.total_sectors = read_le32(boot, 32);
  return result;
}

static u32 cluster_lba(const Layout& fs, u16 cluster, u8 sector = 0) {
  return fs.data_start + (u32) (cluster - 2) * fs.sectors_per_cluster + sector;
}

static void fresh(u32 capacity = SPIFlash::DEFAULT_CAPACITY) {
  virtual_fat::end_session();
  SPIFlash::reset(capacity);
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
}

static u16 fat12_value(u16 cluster) {
  const Layout fs = layout();
  const u32 byte_offset = (u32) cluster + cluster / 2;
  u8 first[512];
  u8 second[512];
  assert(virtual_fat::read_sector(1 + byte_offset / 512, first));
  const u16 offset = (u16) (byte_offset % 512);
  u8 hi = 0;
  if(offset == 511) {
    assert(virtual_fat::read_sector(2 + byte_offset / 512, second));
    hi = second[0];
  } else {
    hi = first[offset + 1];
  }
  const u16 packed = (u16) (first[offset] | ((u16) hi << 8));
  (void) fs;
  return (cluster & 1) == 0 ? (u16) (packed & 0x0FFF)
                             : (u16) (packed >> 4);
}

static void set_fat12_value(u8* fat, u16 cluster, u16 value) {
  const u16 offset = (u16) (cluster + cluster / 2);
  assert(offset + 1 < 512);
  value &= 0x0FFF;
  if((cluster & 1) == 0) {
    fat[offset] = (u8) value;
    fat[offset + 1] = (u8) ((fat[offset + 1] & 0xF0) | (value >> 8));
  } else {
    fat[offset] = (u8) ((fat[offset] & 0x0F) | (value << 4));
    fat[offset + 1] = (u8) (value >> 4);
  }
}

static u8 short_checksum(const u8* name) {
  u8 sum = 0;
  for(u8 i = 0; i < 11; i++) {
    sum = (u8) (((sum & 1) ? 0x80 : 0) + (sum >> 1) + name[i]);
  }
  return sum;
}

static void write_lfn_char(u8* item, u8 index, u16 value) {
  static const u8 offsets[13] = {
    1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30
  };
  write_le16(item, offsets[index], value);
}

static u16 read_lfn_char(const u8* item, u8 index) {
  static const u8 offsets[13] = {
    1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30
  };
  return read_le16(item, offsets[index]);
}

static u8 append_ascii_entry(u8* directory, u8 slot, const char* name,
                             const char short_name[11], bool is_directory,
                             u16 cluster, u32 size) {
  assert(strlen(name) <= 13 && slot + 2 < 16);
  u8* lfn = directory + (u16) slot * 32;
  memset(lfn, 0xFF, 32);
  lfn[0] = 0x41;
  lfn[11] = 0x0F;
  lfn[12] = 0;
  lfn[13] = short_checksum((const u8*) short_name);
  write_le16(lfn, 26, 0);
  const u8 len = (u8) strlen(name);
  for(u8 i = 0; i < 13; i++) {
    write_lfn_char(lfn, i, i < len ? (u8) name[i] : i == len ? 0 : 0xFFFF);
  }
  u8* item = lfn + 32;
  memset(item, 0, 32);
  memcpy(item, short_name, 11);
  item[11] = is_directory ? 0x10 : 0x20;
  write_le16(item, 26, cluster);
  write_le32(item, 28, size);
  return (u8) (slot + 2);
}

static void dot_entries(u8* directory, u16 self_cluster,
                        u16 parent_cluster) {
  memset(directory, 0, 512);
  memcpy(directory, ".          ", 11);
  directory[11] = 0x10;
  write_le16(directory, 26, self_cluster);
  memcpy(directory + 32, "..         ", 11);
  directory[32 + 11] = 0x10;
  write_le16(directory + 32, 26, parent_cluster);
}

static int first_free_slot(const u8* directory) {
  for(int slot = 0; slot < 16; slot++) {
    if(directory[slot * 32] == 0) return slot;
  }
  return -1;
}

static void expect_file(u16 id, const u8* expected, u16 expected_len) {
  u8 actual[program_store::MAX_MK61_TEXT_SIZE] = {};
  u16 actual_len = 0;
  assert(program_store::read_id(id, actual, sizeof(actual), &actual_len));
  assert(actual_len == expected_len);
  assert(memcmp(actual, expected, expected_len) == 0);
}

static void expect_flush(void) {
  const bool ok = virtual_fat::flush_pending();
  if(!ok) fprintf(stderr, "VFAT flush failed in %s\n",
                  virtual_fat::trace_line_at(0));
  assert(ok);
}

static void test_dynamic_fat12_bpb(void) {
  const u32 capacities[] = {
    128U * 1024U, 512U * 1024U,
    2U * 1024U * 1024U, 16U * 1024U * 1024U
  };
  for(u32 capacity : capacities) {
    fresh(capacity);
    const Layout fs = layout();
    const storage_geometry::Geometry& geometry = program_store::geometry();
    assert(fs.total_sectors == geometry.logical_sectors);
    assert(fs.sectors_per_cluster == geometry.sectors_per_cluster);
    assert(fs.fat_sectors == geometry.fat_sectors);
    assert(fs.root_entries == geometry.root_entries);
    assert(virtual_fat::sector_count() == geometry.logical_sectors);
    const u32 data_sectors = fs.total_sectors - fs.data_start;
    assert(data_sectors / fs.sectors_per_cluster == geometry.max_nodes);
    assert(geometry.max_nodes < 4085);
    assert(fat12_value(0) == 0xFF8);
    assert(fat12_value(1) == 0xFFF);
  }
}

static void test_macos_no_index_marker(void) {
  fresh();
  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  assert((root[11] & 0x08) != 0);
  assert(root[32] == 0x42 && root[32 + 11] == 0x0F);
  assert(root[64] == 0x01 && root[64 + 11] == 0x0F);
  assert(memcmp(root + 96, "METADATANIX", 11) == 0);
  assert((root[96 + 11] & 0x07) == 0x07);
  assert(read_le16(root + 96, 26) == 0);
  assert(read_le32(root + 96, 28) == 0);

  char name[27] = {};
  for(u8 slot = 1; slot <= 2; slot++) {
    const u8* item = root + (u16) slot * 32;
    const u8 sequence = (u8) (item[0] & 0x1F);
    assert(sequence >= 1 && sequence <= 2);
    for(u8 index = 0; index < 13; index++) {
      const u16 value = read_lfn_char(item, index);
      if(value == 0 || value == 0xFFFF) continue;
      assert(value < 0x80);
      name[(u16) (sequence - 1) * 13 + index] = (char) value;
    }
  }
  assert(strcmp(name, ".metadata_never_index") == 0);
  assert(first_free_slot(root) == storage_geometry::ROOT_SYSTEM_DIRENTS);
}

static void test_stable_clusters_and_nested_reads(void) {
  fresh();
  u16 first_dir = 0;
  u16 second_dir = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, "Projects",
                                         10, &first_dir));
  assert(program_store::create_directory(first_dir, "Games", 11,
                                         &second_dir));
  const u8 payload[] = {'1', '0', ' ', 'P', 'R', 'I', 'N', 'T'};
  u16 file = 0;
  assert(program_store::write_file(second_dir, 12,
                                   program_store::ProgramType::TINYBASIC,
                                   "demo", payload, sizeof(payload), &file));
  assert(virtual_fat::reset_session());
  assert(first_dir == 10 && second_dir == 11 && file == 12);
  assert(fat12_value(12) >= 0xFF8);
  assert(fat12_value(13) >= 0xFF8);
  assert(fat12_value(14) >= 0xFF8);

  const Layout fs = layout();
  u8 sector[512] = {};
  assert(virtual_fat::read_sector(cluster_lba(fs, 14), sector));
  assert(memcmp(sector, payload, sizeof(payload)) == 0);
  for(usize i = sizeof(payload); i < sizeof(sector); i++) assert(sector[i] == 0);

  assert(virtual_fat::read_sector(cluster_lba(fs, 12), sector));
  assert(sector[0] == '.' && sector[32] == '.');
  assert(virtual_fat::read_sector(cluster_lba(fs, 13), sector));
  assert(sector[0] == '.' && sector[32] == '.');
}

static void test_directory_extents_grow_without_flat_catalog_scan(void) {
  fresh();
  u16 directory = 0;
  assert(program_store::create_directory(program_store::ROOT_ID,
                                         "Large collection", 20, &directory));
  const u8 data = 0x42;
  for(u16 i = 0; i < 30; i++) {
    char name[32];
    snprintf(name, sizeof(name), "long-program-name-%02u", (unsigned) i);
    assert(program_store::write_file(directory, (u16) (100 + i),
                                     program_store::ProgramType::MK61,
                                     name, &data, 1, NULL));
  }
  assert(virtual_fat::reset_session());
  const u16 first_cluster = (u16) (directory + 2);
  const u16 extent_cluster = fat12_value(first_cluster);
  assert(extent_cluster >= 2 && extent_cluster < 0xFF8);
  assert(fat12_value(extent_cluster) >= 0xFF8);
  u16 owner = 0;
  u16 next = 0;
  assert(program_store::extent_info((u16) (extent_cluster - 2), owner, next));
  assert(owner == directory && next == program_store::INVALID_ID);
}

static void stage_host_tree(void) {
  const Layout fs = layout();
  const u16 outer_cluster = 102;
  const u16 inner_cluster = 103;
  const u16 file_cluster = 104;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, outer_cluster, 0xFFF);
  set_fat12_value(fat, inner_cluster, 0xFFF);
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  int slot = first_free_slot(root);
  assert(slot == storage_geometry::ROOT_SYSTEM_DIRENTS);
  static const char outer_short[11] = {'M','Y','S','T','U','F','~','1',' ',' ',' '};
  slot = append_ascii_entry(root, (u8) slot, "My Stuff", outer_short, true,
                            outer_cluster, 0);
  root[slot * 32] = 0;

  u8 outer[512];
  dot_entries(outer, outer_cluster, 0);
  static const char inner_short[11] = {'G','A','M','E','S','~','1',' ',' ',' ',' '};
  slot = append_ascii_entry(outer, 2, "Games", inner_short, true,
                            inner_cluster, 0);
  outer[slot * 32] = 0;

  u8 inner[512];
  dot_entries(inner, inner_cluster, outer_cluster);
  static const char file_short[11] = {'N','O','T','E','S','~','1',' ','T','X','T'};
  static const u8 payload[] = "hello from a nested directory\n";
  slot = append_ascii_entry(inner, 2, "notes.txt", file_short, false,
                            file_cluster, sizeof(payload) - 1);
  inner[slot * 32] = 0;

  u8 file_data[512] = {};
  memcpy(file_data, payload, sizeof(payload) - 1);
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, file_cluster),
                                           file_data, 1));
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, inner_cluster),
                                           inner, 1));
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, outer_cluster),
                                           outer, 1));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::dirty_cache_sectors() == 5);
  assert(fat12_value(outer_cluster) == 0xFFF);
  assert(fat12_value(inner_cluster) == 0xFFF);
  assert(fat12_value(file_cluster) == 0xFFF);
}

static void test_host_creates_arbitrary_nested_tree(void) {
  fresh();
  stage_host_tree();
  expect_flush();
  assert(virtual_fat::write_cache_capacity() == 16);
  assert(program_store::vfat_stage_count() == 0);

  program_store::Entry outer;
  program_store::Entry inner;
  program_store::Entry file;
  assert(program_store::entry_by_id(100, outer));
  assert(program_store::entry_by_id(101, inner));
  assert(program_store::entry_by_id(102, file));
  assert(outer.kind == program_store::NodeKind::DIRECTORY);
  assert(inner.kind == program_store::NodeKind::DIRECTORY);
  assert(strcmp(outer.name, "My Stuff") == 0);
  assert(strcmp(inner.name, "Games") == 0);
  assert(outer.parent_id == program_store::ROOT_ID);
  assert(inner.parent_id == outer.id);
  assert(file.parent_id == inner.id);
  assert(file.type == program_store::ProgramType::TEXT);
  assert(strcmp(file.name, "notes") == 0);
  static const u8 payload[] = "hello from a nested directory\n";
  expect_file(file.id, payload, sizeof(payload) - 1);

  program_store::init();
  assert(virtual_fat::reset_session());
  expect_file(file.id, payload, sizeof(payload) - 1);
}

static void test_staged_update_survives_session_reset(void) {
  fresh();
  const u8 old_data[] = "old";
  u16 id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 50,
                                   program_store::ProgramType::TEXT,
                                   "journal", old_data, sizeof(old_data) - 1,
                                   &id));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 updated[512] = {};
  memcpy(updated, "new", 3);
  assert(virtual_fat::write_sector(cluster_lba(fs, (u16) (id + 2)), updated));
  virtual_fat::end_session();
  program_store::init();
  assert(virtual_fat::reset_session());
  assert(program_store::vfat_stage_count() == 1);
  expect_flush();
  expect_file(id, (const u8*) "new", 3);
}

static void test_identical_data_writes_do_not_restage(void) {
  fresh();
  const Layout fs = layout();
  const u32 lba = cluster_lba(fs, 200);
  u8 data[512] = {};

  // An unallocated data cluster renders as zero and needs no physical log
  // record when the host redundantly zero-fills it.
  assert(virtual_fat::write_sector(lba, data));
  assert(program_store::vfat_stage_count() == 0);

  data[17] = 0x5A;
  assert(virtual_fat::write_sector(lba, data));
  assert(program_store::vfat_stage_count() == 1);
  const u64 programmed = SPIFlash::programmedBytes();
  assert(virtual_fat::write_sector(lba, data));
  assert(program_store::vfat_stage_count() == 1);
  assert(SPIFlash::programmedBytes() == programmed);
}

static void test_write_cache_coalesces_and_evicts_lru(void) {
  fresh();
  const Layout fs = layout();
  assert(virtual_fat::write_cache_capacity() == 16);
  const u32 first_lba = cluster_lba(fs, 300);
  u8 data[512] = {};
  u8 readback[512] = {};

  data[9] = 1;
  assert(virtual_fat::write_cached_sectors(first_lba, data, 1));
  data[9] = 2;
  assert(virtual_fat::write_cached_sectors(first_lba, data, 1));
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::dirty_cache_sectors() == 1);
  assert(virtual_fat::read_sector(first_lba, readback));
  assert(memcmp(readback, data, sizeof(data)) == 0);

  // Returning to the persistent zero block cancels the dirty write entirely.
  memset(data, 0, sizeof(data));
  assert(virtual_fat::write_cached_sectors(first_lba, data, 1));
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == 0);

  // Fill every slot with a distinct dirty sector. The next miss persists only
  // the LRU sector; the other writes stay coalescible in RAM until sync.
  const u8 capacity = virtual_fat::write_cache_capacity();
  for(u8 i = 0; i < capacity; i++) {
    memset(data, 0, sizeof(data));
    data[0] = (u8) (i + 1);
    assert(virtual_fat::write_cached_sectors(first_lba + i, data, 1));
  }
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 0);

  memset(data, 0, sizeof(data));
  data[0] = 0xA5;
  assert(virtual_fat::write_cached_sectors(first_lba + capacity, data, 1));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 1);
  assert(virtual_fat::flush_write_cache());
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == (u16) capacity + 1);
}

static void test_fast_usb_cache_is_atomic_and_defers_spi(void) {
  fresh();
  const Layout fs = layout();
  const u32 first_lba = cluster_lba(fs, 600);
  u8 zero[512] = {};
  u8 readback[512] = {};

  // The interrupt-safe path does not read even a zero-filled base sector.
  // Sync performs the postponed comparison and avoids a staging write.
  assert(virtual_fat::try_write_cached_sectors(first_lba, zero, 1));
  assert(virtual_fat::dirty_cache_sectors() == 1);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::read_sector(first_lba, readback));
  assert(memcmp(readback, zero, sizeof(zero)) == 0);
  assert(virtual_fat::flush_write_cache());
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == 0);

  fresh();
  const Layout fresh_fs = layout();
  const u32 packet_lba = cluster_lba(fresh_fs, 600);
  const u8 capacity = virtual_fat::write_cache_capacity();
  assert(capacity == 16);
  u8 packet[16 * 512] = {};
  for(u8 index = 0; index < capacity; index++) {
    packet[(u32) index * 512] = (u8) (index + 1);
  }
  assert(virtual_fat::try_write_cached_sectors(packet_lba, packet, capacity));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 0);

  // A full cache cannot accept another key synchronously. Failure leaves the
  // entire packet untouched, after which the normal path may persist one LRU
  // victim and continue without losing the BOT packet.
  u8 extra[512] = {0xA5};
  assert(!virtual_fat::try_write_cached_sectors(packet_lba + capacity,
                                                extra, 1));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::read_sector(packet_lba + capacity - 1, readback));
  assert(readback[0] == capacity);

  // Rewriting a resident key never needs SPI and remains on the fast path.
  u8 replacement[512] = {0x5A};
  assert(virtual_fat::try_write_cached_sectors(packet_lba + capacity - 1,
                                               replacement, 1));
  assert(virtual_fat::read_sector(packet_lba + capacity - 1, readback));
  assert(memcmp(readback, replacement, sizeof(replacement)) == 0);
  assert(program_store::vfat_stage_count() == 0);

  assert(virtual_fat::write_cached_sectors(packet_lba + capacity, extra, 1));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 1);
  assert(virtual_fat::flush_write_cache());
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == (u16) capacity + 1);

  // Preflight also reserves a clean key addressed later in the same packet;
  // it must not mutate that sector before deciding to defer the whole packet.
  fresh();
  const Layout reserved_fs = layout();
  const u32 reserved_lba = cluster_lba(reserved_fs, 700);
  assert(virtual_fat::write_cached_sectors(reserved_lba + 15, zero, 1));
  assert(virtual_fat::dirty_cache_sectors() == 0);
  for(u8 index = 0; index < 15; index++) {
    extra[0] = (u8) (index + 1);
    assert(virtual_fat::try_write_cached_sectors(reserved_lba + index,
                                                 extra, 1));
  }
  u8 two_sectors[2 * 512] = {};
  two_sectors[0] = 0xC1;
  two_sectors[512] = 0xC2;
  assert(!virtual_fat::try_write_cached_sectors(reserved_lba + 15,
                                                two_sectors, 2));
  assert(virtual_fat::dirty_cache_sectors() == 15);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::read_sector(reserved_lba + 15, readback));
  assert(readback[0] == 0);
  assert(virtual_fat::read_sector(reserved_lba + 16, readback));
  assert(readback[0] == 0);
}

static void test_optional_display_cache_span(void) {
  fresh();
  virtual_fat::end_session();
  alignas(4) static u8 display_cache[8192];
  assert(virtual_fat::set_external_cache(display_cache,
                                         sizeof(display_cache)));
  assert(virtual_fat::reset_session());
  assert(virtual_fat::write_cache_capacity() == 32);

  const Layout fs = layout();
  const u32 first_lba = cluster_lba(fs, 500);
  u8 data[512] = {};
  for(u8 i = 0; i < virtual_fat::write_cache_capacity(); i++) {
    data[0] = (u8) (i + 1);
    assert(virtual_fat::write_cached_sectors(first_lba + i, data, 1));
  }
  assert(virtual_fat::dirty_cache_sectors() == 32);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::flush_pending());
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(virtual_fat::write_cache_capacity() == 32);
}

static void test_host_deletes_file_via_directory(void) {
  fresh();
  const u8 data[] = {'x'};
  u16 id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 60,
                                   program_store::ProgramType::MK61,
                                   "delete-me", data, 1, &id));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 user_offset = storage_geometry::ROOT_SYSTEM_DIRENTS * 32U;
  memset(root + user_offset, 0, 512 - user_offset);
  assert(virtual_fat::write_sector(fs.root_start, root));
  expect_flush();
  program_store::Entry removed;
  assert(!program_store::entry_by_id(id, removed));
  assert(program_store::total_count() == 0);
}

static void test_finder_appledouble_does_not_abort_batch(void) {
  fresh();
  const Layout fs = layout();
  const u16 sidecar_cluster = 202;
  const u16 file_cluster = 203;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, sidecar_cluster, 0xFFF);
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  u8 slot = (u8) first_free_slot(root);
  static const char sidecar_short[11] =
      {'_','G','A','M','E','~','1',' ','M','6','1'};
  slot = append_ascii_entry(root, slot, "._game.m61", sidecar_short,
                            false, sidecar_cluster, 4096);
  static const char file_short[11] =
      {'G','A','M','E',' ',' ',' ',' ','M','6','1'};
  static const u8 payload[] = {0x11, 0x22, 0x33};
  slot = append_ascii_entry(root, slot, "game.m61", file_short,
                            false, file_cluster, sizeof(payload));
  root[slot * 32] = 0;

  u8 data[512] = {};
  memcpy(data, payload, sizeof(payload));
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();

  program_store::Entry file;
  assert(program_store::entry_by_id((u16) (file_cluster - 2), file));
  assert(strcmp(file.name, "game") == 0);
  expect_file(file.id, payload, sizeof(payload));
  program_store::Entry ignored;
  assert(!program_store::entry_by_id((u16) (sidecar_cluster - 2), ignored));
}

static void test_malformed_fat_chain_is_rejected_atomically(void) {
  fresh();
  const Layout fs = layout();
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, 202, 202);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] = {'B','R','O','K','E','N','~','1','T','X','T'};
  const int free_slot = first_free_slot(root);
  assert(free_slot == storage_geometry::ROOT_SYSTEM_DIRENTS);
  const u8 slot = append_ascii_entry(root, (u8) free_slot,
                                     "broken.txt", short_name,
                                     false, 202, 1);
  root[slot * 32] = 0;
  u8 data[512] = {0xAA};
  assert(virtual_fat::write_sector(cluster_lba(fs, 202), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::flush_pending());
  assert(program_store::total_count() == 0);
  assert(program_store::vfat_stage_count() != 0);
  assert(program_store::vfat_stage_discard_all());
}

} // namespace

int main(void) {
  test_dynamic_fat12_bpb();
  test_macos_no_index_marker();
  test_stable_clusters_and_nested_reads();
  test_directory_extents_grow_without_flat_catalog_scan();
  test_host_creates_arbitrary_nested_tree();
  test_staged_update_survives_session_reset();
  test_identical_data_writes_do_not_restage();
  test_write_cache_coalesces_and_evicts_lru();
  test_fast_usb_cache_is_atomic_and_defers_spi();
  test_optional_display_cache_span();
  test_host_deletes_file_via_directory();
  test_finder_appledouble_does_not_abort_batch();
  test_malformed_fat_chain_is_rejected_atomically();
  virtual_fat::end_session();
  printf("virtual_fat_self_test: ok\n");
  return 0;
}
