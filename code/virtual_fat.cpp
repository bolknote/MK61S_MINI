#include "virtual_fat.hpp"

#include "program_store.hpp"
#include "shared_scratch.hpp"

#if defined(MK61_VFAT_TRACE)
#include <stdarg.h>
#include <stdio.h>
#endif
#include <string.h>

#ifndef MK61_ENABLE_TINYBASIC
  #define MK61_ENABLE_TINYBASIC 1
#endif

namespace virtual_fat {

static constexpr u8 FAT_COUNT = 2;
static constexpr u8 SECTORS_PER_CLUSTER = 1;
static constexpr u16 ROOT_ENTRIES = 1024;
static constexpr u16 ROOT_DIR_SECTORS = (ROOT_ENTRIES * 32 + SECTOR_SIZE - 1) / SECTOR_SIZE;
static constexpr u16 RESERVED_SECTORS = 1;
static constexpr u16 DATA_CLUSTER_CAPACITY = 800;
static constexpr u16 MEDIA_DESCRIPTOR = 0xF8;
static constexpr u16 CLUSTER_FREE = 0x000;
static constexpr u16 CLUSTER_EOF = 0xFFF;
static constexpr u16 FIRST_DATA_CLUSTER = 2;
static constexpr u16 CLUSTER_LIMIT = FIRST_DATA_CLUSTER + DATA_CLUSTER_CAPACITY;
static constexpr u16 MAX_IMPORTED_LEN = program_store::MAX_MK61_TEXT_SIZE;
static constexpr u8 MAX_FILE_CLUSTERS = (MAX_IMPORTED_LEN + SECTOR_SIZE - 1) / SECTOR_SIZE;
static constexpr u16 MAX_LFN_CHARS = program_store::NAME_SIZE + 3;
static constexpr u8 MAX_PENDING_WRITES = program_store::MAX_ENTRIES;
static constexpr u8 MAX_PENDING_DELETES = program_store::MAX_ENTRIES;
static constexpr u8 IGNORED_WRITE_RANGES = program_store::MAX_ENTRIES;
// Enough raw FAT12 bytes for CLUSTER_LIMIT entries: (802 * 3 + 1) / 2 = 1203.
static constexpr u8 HOST_FAT_SECTORS = 3;
static constexpr u8 FAT_ATTR_VOLUME = 0x08;
static constexpr u8 FAT_ATTR_DIRECTORY = 0x10;
static constexpr u8 FAT_ATTR_ARCHIVE = 0x20;
static constexpr u8 FAT_ATTR_LFN = 0x0F;

static const program_store::ProgramType FILE_TYPES[] = {
  program_store::ProgramType::MK61,
  program_store::ProgramType::BASIC,
  program_store::ProgramType::FOCAL
#if MK61_ENABLE_TINYBASIC
  ,
  program_store::ProgramType::TINYBASIC
#endif
};

struct PendingWrite {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 start_cluster;
  u16 data_len;
};

struct PendingDelete {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 start_cluster;
  u16 data_len;
};

struct IgnoredWriteRange {
  bool used;
  u16 start_cluster;
  u16 clusters;
};

// Session-stable cluster assignment of a committed program. Once a file is
// pinned here its clusters never move while the host stays mounted, even if
// other files are deleted. The chain may be non-contiguous when the host
// allocated a fragmented file.
struct ClusterMap {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 chain[MAX_FILE_CLUSTERS];
  u8 count;
};

struct FileClusters {
  u16 clusters[MAX_FILE_CLUSTERS];
  u8 count;
};

struct ParsedDirEntry {
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 start_cluster;
  u16 data_len;
};

struct LfnState {
  bool active;
  bool valid;
  u8 expected;
  u16 seen_mask;
  u8 checksum;
  char name[MAX_LFN_CHARS + 1];
};

static PendingWrite pending_writes[MAX_PENDING_WRITES];
static PendingDelete pending_deletes[MAX_PENDING_DELETES];
static IgnoredWriteRange ignored_ranges[IGNORED_WRITE_RANGES];
static ClusterMap cluster_maps[program_store::MAX_ENTRIES];
static LfnState root_lfn_state;
static u32 root_lfn_next_sector = 0;
static u8 next_ignored_slot = 0;

// Raw copy of the FAT sectors the host has written this session. This is the
// only way to learn the real (possibly fragmented) cluster chains the host
// allocated for new files.
static u8 host_fat[HOST_FAT_SECTORS * SECTOR_SIZE];
static u8 host_fat_written;

static_assert(shared_scratch::SIZE >= MAX_IMPORTED_LEN, "shared scratch too small for virtual FAT commits");

static PendingDelete* find_pending_delete(program_store::ProgramType type, const char* name);
static void clear_pending_delete(PendingDelete* pending);
static bool entry_is_pending_delete(const program_store::Entry& entry);
static bool ignored_cluster(u16 cluster);

static bool sector_is_zero(const u8* data) {
  for(u16 i = 0; i < SECTOR_SIZE; i++) {
    if(data[i] != 0) return false;
  }
  return true;
}

#if defined(MK61_VFAT_TRACE)
static constexpr u8 TRACE_LINES = 128;
static constexpr u8 TRACE_LINE_SIZE = 64;
static constexpr u16 TRACE_FILE_CLUSTERS = 17;
static constexpr u16 TRACE_FIRST_CLUSTER = FIRST_DATA_CLUSTER + DATA_CLUSTER_CAPACITY - TRACE_FILE_CLUSTERS;
static char trace_lines[TRACE_LINES][TRACE_LINE_SIZE];
static u16 trace_next_line;
static u16 trace_line_count;

static void tracef(const char* format, ...) {
  va_list args;
  va_start(args, format);
  vsnprintf(trace_lines[trace_next_line], TRACE_LINE_SIZE, format, args);
  va_end(args);

  trace_next_line = (u16) ((trace_next_line + 1) % TRACE_LINES);
  if(trace_line_count < TRACE_LINES) trace_line_count++;
}

static bool trace_sector_is_zero(const u8* data) {
  for(u16 i = 0; i < SECTOR_SIZE; i++) {
    if(data[i] != 0) return false;
  }
  return true;
}

static u16 trace_line_index(u16 visible_index) {
  const u16 first = (trace_line_count < TRACE_LINES) ? 0 : trace_next_line;
  return (u16) ((first + visible_index) % TRACE_LINES);
}

#else
static void tracef(const char*, ...) {}
static bool trace_sector_is_zero(const u8*) { return false; }
#endif

static u16 clusters_for_len(u16 len) {
  return (u16) ((len + SECTOR_SIZE - 1) / SECTOR_SIZE);
}

static u16 trace_cluster_count(void) {
  return 0;
}

static int first_program_dir_index(void) {
#if defined(MK61_VFAT_TRACE)
  return 2;
#else
  return 1;
#endif
}

static bool entry_name_visible(const char* name) {
  return name != NULL && name[0] != 0 && name[0] != '.' && name[0] != '_';
}

static int file_count(void) {
  int count = 0;
  for(program_store::ProgramType type : FILE_TYPES) {
    const int type_count = program_store::count(type);
    for(int i = 0; i < type_count; i++) {
      program_store::Entry entry;
      if(program_store::entry(type, i, entry) && entry_name_visible(entry.name)) count++;
    }
  }
  const int max_files = ROOT_ENTRIES - 1;
  return (count > max_files) ? max_files : count;
}

static bool file_entry(int flat_index, program_store::Entry& out) {
  if(flat_index < 0) return false;

  int visible = 0;
  for(program_store::ProgramType type : FILE_TYPES) {
    const int count = program_store::count(type);
    for(int i = 0; i < count; i++) {
      program_store::Entry entry;
      if(!program_store::entry(type, i, entry) || !entry_name_visible(entry.name)) continue;
      if(visible++ == flat_index) {
        out = entry;
        return true;
      }
    }
  }

  return false;
}

/* ============================ host FAT shadow ============================ */

static void record_host_fat_sector(u32 fat_index, const u8* data) {
  if(fat_index >= HOST_FAT_SECTORS) return;
  memcpy(host_fat + fat_index * SECTOR_SIZE, data, SECTOR_SIZE);
  host_fat_written = (u8) (host_fat_written | (1U << fat_index));
}

static bool host_fat_byte(u32 offset, u8& out) {
  const u32 sector = offset / SECTOR_SIZE;
  if(sector >= HOST_FAT_SECTORS) return false;
  if((host_fat_written & (1U << sector)) == 0) return false;
  out = host_fat[offset];
  return true;
}

// FAT12 value the host wrote for a cluster, or 0xFFFF when unknown.
static u16 host_fat_next(u16 cluster) {
  const u32 offset = (u32) cluster + cluster / 2;
  u8 lo = 0;
  u8 hi = 0;
  if(!host_fat_byte(offset, lo) || !host_fat_byte(offset + 1, hi)) return 0xFFFF;
  const u16 raw = (u16) (lo | ((u16) hi << 8));
  return ((cluster & 1) == 0) ? (u16) (raw & 0x0FFF) : (u16) (raw >> 4);
}

// Cluster chain of a file starting at start_cluster. Follows the host FAT
// when the host wrote it, otherwise assumes contiguous allocation.
static u8 build_chain(u16 start_cluster, u16 data_len, u16* out) {
  const u16 needed = clusters_for_len(data_len);
  const u8 count = (needed > MAX_FILE_CLUSTERS) ? MAX_FILE_CLUSTERS : (u8) needed;
  u16 cluster = start_cluster;
  for(u8 i = 0; i < count; i++) {
    out[i] = cluster;
    u16 next = host_fat_next(cluster);
    if(next < FIRST_DATA_CLUSTER || next >= CLUSTER_LIMIT) next = (u16) (cluster + 1);
    for(u8 j = 0; j <= i; j++) {
      if(out[j] == next) {
        next = (u16) (cluster + 1);
        break;
      }
    }
    cluster = next;
  }
  return count;
}

/* ============================ pending writes ============================= */

static void pending_clusters(const PendingWrite& pending, FileClusters& out) {
  out.count = 0;
  if(pending.data_len == 0 || pending.start_cluster < FIRST_DATA_CLUSTER) return;
  out.count = build_chain(pending.start_cluster, pending.data_len, out.clusters);
}

static PendingWrite* pending_for_cluster(u16 cluster, int* out_index = NULL) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used || pending.start_cluster < FIRST_DATA_CLUSTER) continue;
    FileClusters chain;
    pending_clusters(pending, chain);
    for(u8 j = 0; j < chain.count; j++) {
      if(chain.clusters[j] != cluster) continue;
      if(out_index != NULL) *out_index = j;
      return &pending;
    }
  }
  return NULL;
}

/* ============================ cluster mapping ============================ */

static bool same_key(program_store::ProgramType type, const char* name, const ClusterMap& map) {
  return name != NULL &&
         map.used &&
         map.type == type &&
         strncmp(map.name, name, program_store::NAME_SIZE) == 0;
}

static ClusterMap* find_cluster_map(program_store::ProgramType type, const char* name) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    if(same_key(type, name, cluster_maps[i])) return &cluster_maps[i];
  }
  return NULL;
}

static ClusterMap* allocate_cluster_map(void) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    if(!cluster_maps[i].used) return &cluster_maps[i];
  }
  return NULL;
}

static void forget_cluster_map(program_store::ProgramType type, const char* name) {
  ClusterMap* map = find_cluster_map(type, name);
  if(map != NULL) memset(map, 0, sizeof(*map));
}

static void purge_stale_cluster_maps(void) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    ClusterMap& map = cluster_maps[i];
    if(!map.used) continue;
    if(!program_store::exists(map.type, map.name)) memset(&map, 0, sizeof(map));
  }
}

static bool cluster_in_maps(u16 cluster) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    const ClusterMap& map = cluster_maps[i];
    if(!map.used) continue;
    for(u8 j = 0; j < map.count; j++) {
      if(map.chain[j] == cluster) return true;
    }
  }
  return false;
}

static bool cluster_in_pendings(u16 cluster) {
  return pending_for_cluster(cluster) != NULL;
}

static bool cluster_range_free(u16 start, u16 count) {
  for(u16 i = 0; i < count; i++) {
    const u16 cluster = (u16) (start + i);
    if(cluster_in_maps(cluster) || cluster_in_pendings(cluster) || ignored_cluster(cluster)) return false;
  }
  return true;
}

static u16 allocate_contiguous_clusters(u16 count) {
  if(count == 0) return 0;
  for(u16 start = FIRST_DATA_CLUSTER; (u32) start + count <= CLUSTER_LIMIT; start++) {
    if(cluster_range_free(start, count)) return start;
  }
  return 0;
}

static void store_cluster_map(program_store::ProgramType type, const char* name, const u16* chain, u8 count) {
  if(name == NULL || name[0] == 0 || count == 0) {
    forget_cluster_map(type, name);
    return;
  }

  ClusterMap* map = find_cluster_map(type, name);
  if(map == NULL) map = allocate_cluster_map();
  if(map == NULL) {
    purge_stale_cluster_maps();
    map = allocate_cluster_map();
  }
  if(map == NULL) return;

  memset(map, 0, sizeof(*map));
  map->used = true;
  map->type = type;
  strncpy(map->name, name, program_store::NAME_SIZE - 1);
  map->name[program_store::NAME_SIZE - 1] = 0;
  for(u8 i = 0; i < count && i < MAX_FILE_CLUSTERS; i++) map->chain[i] = chain[i];
  map->count = (count > MAX_FILE_CLUSTERS) ? MAX_FILE_CLUSTERS : count;
}

static void rename_cluster_map(program_store::ProgramType type, const char* old_name, const char* new_name, u16 start_cluster, u16 data_len) {
  ClusterMap* map = find_cluster_map(type, old_name);
  if(map == NULL) {
    u16 chain[MAX_FILE_CLUSTERS];
    const u8 count = build_chain(start_cluster, data_len, chain);
    store_cluster_map(type, new_name, chain, count);
    return;
  }

  strncpy(map->name, new_name, program_store::NAME_SIZE - 1);
  map->name[program_store::NAME_SIZE - 1] = 0;
}

// Session-stable cluster chain for a committed program; pins the file on
// first use so its clusters never move while the host is mounted.
static void file_clusters(int flat_index, const program_store::Entry& entry, FileClusters& out) {
  (void) flat_index;
  out.count = 0;
  const u16 needed16 = clusters_for_len(entry.data_len);
  if(needed16 == 0) return;
  const u8 needed = (needed16 > MAX_FILE_CLUSTERS) ? MAX_FILE_CLUSTERS : (u8) needed16;

  ClusterMap* map = find_cluster_map(entry.type, entry.name);
  if(map != NULL && map->count < needed) {
    // File grew on the device side: extend contiguously when possible,
    // otherwise relocate.
    bool can_extend = true;
    for(u8 i = map->count; i < needed && can_extend; i++) {
      const u16 cluster = (u16) (map->chain[map->count - 1] + 1 + (i - map->count));
      if(cluster >= CLUSTER_LIMIT || !cluster_range_free(cluster, 1)) can_extend = false;
    }
    if(can_extend) {
      for(u8 i = map->count; i < needed; i++) map->chain[i] = (u16) (map->chain[map->count - 1] + 1 + (i - map->count));
      map->count = needed;
    } else {
      memset(map, 0, sizeof(*map));
      map = NULL;
    }
  }

  if(map == NULL) {
    u16 start = allocate_contiguous_clusters(needed);
    if(start == 0) start = FIRST_DATA_CLUSTER;
    u16 chain[MAX_FILE_CLUSTERS];
    for(u8 i = 0; i < needed; i++) chain[i] = (u16) (start + i);
    store_cluster_map(entry.type, entry.name, chain, needed);
    for(u8 i = 0; i < needed; i++) out.clusters[i] = chain[i];
    out.count = needed;
    return;
  }

  for(u8 i = 0; i < needed; i++) out.clusters[i] = map->chain[i];
  out.count = needed;
}

static u16 start_cluster_for_file(int flat_index) {
  program_store::Entry entry;
  if(!file_entry(flat_index, entry) || entry.data_len == 0) return 0;
  FileClusters chain;
  file_clusters(flat_index, entry, chain);
  return (chain.count != 0) ? chain.clusters[0] : 0;
}

// Committed (and not pending-delete) file owning a cluster.
static bool find_cluster_owner(u16 cluster, program_store::Entry& out, FileClusters& out_chain, u8& out_pos) {
  if(cluster < FIRST_DATA_CLUSTER) return false;

  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!file_entry(i, entry)) continue;
    if(entry_is_pending_delete(entry)) continue;
    FileClusters chain;
    file_clusters(i, entry, chain);
    for(u8 j = 0; j < chain.count; j++) {
      if(chain.clusters[j] != cluster) continue;
      out = entry;
      out_chain = chain;
      out_pos = j;
      return true;
    }
  }

  return false;
}

static u16 data_cluster_count(void) {
  u16 clusters = trace_cluster_count();
  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!file_entry(i, entry)) continue;
    FileClusters chain;
    file_clusters(i, entry, chain);
    for(u8 j = 0; j < chain.count; j++) {
      const u16 end_cluster = (u16) (chain.clusters[j] + 1);
      const u16 needed = (end_cluster > FIRST_DATA_CLUSTER) ? (u16) (end_cluster - FIRST_DATA_CLUSTER) : 0;
      if(needed > clusters) clusters = needed;
    }
  }
  return clusters;
}

static u16 data_cluster_capacity(void) {
  const u16 used = data_cluster_count();
  return (used > DATA_CLUSTER_CAPACITY) ? used : DATA_CLUSTER_CAPACITY;
}

static u16 fat_sector_count(void) {
  const u32 entries = (u32) data_cluster_capacity() + FIRST_DATA_CLUSTER;
  const u32 bytes = (entries * 3 + 1) / 2;
  const u16 sectors = (u16) ((bytes + SECTOR_SIZE - 1) / SECTOR_SIZE);
  return (sectors == 0) ? 1 : sectors;
}

static u32 first_root_sector(void) {
  return RESERVED_SECTORS + FAT_COUNT * (u32) fat_sector_count();
}

static u32 first_data_sector(void) {
  return first_root_sector() + ROOT_DIR_SECTORS;
}

u32 sector_count(void) {
  return first_data_sector() + (u32) data_cluster_capacity() * SECTORS_PER_CLUSTER;
}

static void put_le16(u8* out, u16 offset, u16 value) {
  out[offset] = (u8) (value & 0xFF);
  out[offset + 1] = (u8) (value >> 8);
}

static void put_le32(u8* out, u16 offset, u32 value) {
  out[offset] = (u8) (value & 0xFF);
  out[offset + 1] = (u8) ((value >> 8) & 0xFF);
  out[offset + 2] = (u8) ((value >> 16) & 0xFF);
  out[offset + 3] = (u8) ((value >> 24) & 0xFF);
}

static const char* extension_for_type(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61:  return "M61";
    case program_store::ProgramType::BASIC: return "BAS";
    case program_store::ProgramType::FOCAL: return "FOC";
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC: return "TBI";
#endif
  }
  return "M61";
}

static u8 short_name_checksum(const u8* short_name) {
  u8 sum = 0;
  for(u8 i = 0; i < 11; i++) {
    sum = (u8) (((sum & 1) ? 0x80 : 0) + (sum >> 1) + short_name[i]);
  }
  return sum;
}

static u16 get_le16(const u8* data, u16 offset) {
  return (u16) (data[offset] | ((u16) data[offset + 1] << 8));
}

static u32 get_le32(const u8* data, u16 offset) {
  return (u32) data[offset] |
         ((u32) data[offset + 1] << 8) |
         ((u32) data[offset + 2] << 16) |
         ((u32) data[offset + 3] << 24);
}

static void read_boot_sector(u8* out) {
  memset(out, 0, SECTOR_SIZE);
  out[0] = 0xEB;
  out[1] = 0x3C;
  out[2] = 0x90;
  memcpy(out + 3, "MK61SFS ", 8);
  put_le16(out, 11, SECTOR_SIZE);
  out[13] = SECTORS_PER_CLUSTER;
  put_le16(out, 14, RESERVED_SECTORS);
  out[16] = FAT_COUNT;
  put_le16(out, 17, ROOT_ENTRIES);

  const u32 total = sector_count();
  if(total <= 0xFFFFUL) {
    put_le16(out, 19, (u16) total);
  } else {
    put_le16(out, 19, 0);
    put_le32(out, 32, total);
  }

  out[21] = MEDIA_DESCRIPTOR;
  put_le16(out, 22, fat_sector_count());
  put_le16(out, 24, 1);
  put_le16(out, 26, 1);
  put_le32(out, 28, 0);
  out[36] = 0x80;
  out[38] = 0x29;
  put_le32(out, 39, 0x6135F512UL);
  memcpy(out + 43, "MK61S FS   ", 11);
  memcpy(out + 54, "FAT12   ", 8);
  out[510] = 0x55;
  out[511] = 0xAA;
}

#if defined(MK61_VFAT_TRACE)
static bool trace_cluster(u16 cluster) {
  return cluster >= TRACE_FIRST_CLUSTER && cluster < (u16) (TRACE_FIRST_CLUSTER + TRACE_FILE_CLUSTERS);
}
#else
static bool trace_cluster(u16) { return false; }
#endif

static u16 fat_value(u16 cluster) {
  if(cluster == 0) return (u16) (0xFF0 | MEDIA_DESCRIPTOR);
  if(cluster == 1) return CLUSTER_EOF;

#if defined(MK61_VFAT_TRACE)
  if(trace_cluster(cluster)) {
    return (cluster + 1 >= (u16) (TRACE_FIRST_CLUSTER + TRACE_FILE_CLUSTERS)) ? CLUSTER_EOF : (u16) (cluster + 1);
  }
#endif

  program_store::Entry entry;
  FileClusters chain;
  u8 pos = 0;
  if(find_cluster_owner(cluster, entry, chain, pos)) {
    return (pos + 1 < chain.count) ? chain.clusters[pos + 1] : CLUSTER_EOF;
  }

  if(ignored_cluster(cluster)) return CLUSTER_FREE;
  return program_store::vfat_stage_exists(cluster) ? CLUSTER_EOF : CLUSTER_FREE;
}

static void set_fat_byte(u8* out, u32 fat_sector, u32 byte_offset, u8 value, u8 mask) {
  if(byte_offset / SECTOR_SIZE != fat_sector) return;
  const u16 pos = (u16) (byte_offset % SECTOR_SIZE);
  out[pos] = (u8) ((out[pos] & ~mask) | (value & mask));
}

static void set_fat12_entry(u8* out, u32 fat_sector, u16 cluster, u16 value) {
  const u32 offset = cluster + cluster / 2;
  value &= 0x0FFF;

  if((cluster & 1) == 0) {
    set_fat_byte(out, fat_sector, offset, (u8) value, 0xFF);
    set_fat_byte(out, fat_sector, offset + 1, (u8) (value >> 8), 0x0F);
  } else {
    set_fat_byte(out, fat_sector, offset, (u8) (value << 4), 0xF0);
    set_fat_byte(out, fat_sector, offset + 1, (u8) (value >> 4), 0xFF);
  }
}

static void read_fat_sector(u32 fat_sector, u8* out) {
  memset(out, 0, SECTOR_SIZE);
  const u16 last_cluster = (u16) (data_cluster_capacity() + FIRST_DATA_CLUSTER);
  for(u16 cluster = 0; cluster < last_cluster; cluster++) {
    int index = -1;
    PendingWrite* pending = pending_for_cluster(cluster, &index);
    if(pending != NULL) {
      FileClusters chain;
      pending_clusters(*pending, chain);
      const u16 value = (index + 1 < (int) chain.count) ? chain.clusters[index + 1] : CLUSTER_EOF;
      set_fat12_entry(out, fat_sector, cluster, value);
    } else {
      set_fat12_entry(out, fat_sector, cluster, fat_value(cluster));
    }
  }
}

static char safe_name_char(char c) {
  if(c >= 'a' && c <= 'z') return (char) (c - 'a' + 'A');
  if((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) return c;
  if(c == '_' || c == '-') return '_';
  return 0;
}

static char short_alias_digit(u16 value) {
  value = (u16) (value % 36);
  return (value < 10) ? (char) ('0' + value) : (char) ('A' + value - 10);
}

// Stable alias suffix: derived from the name itself so the short alias does
// not change when files are added/removed or a pending write commits.
static u16 short_alias_hash(const char* name) {
  u32 hash = 5381;
  for(u8 i = 0; i < program_store::NAME_SIZE && name[i] != 0; i++) {
    hash = hash * 33u + (u8) name[i];
  }
  return (u16) (hash % (36u * 36u));
}

static bool name_is_83_compatible(const char* name) {
  if(name == NULL || name[0] == 0) return false;

  u8 len = 0;
  while(len < program_store::NAME_SIZE && name[len] != 0) {
    if(len >= 8) return false;
    if(safe_name_char(name[len]) != name[len]) return false;
    len++;
  }

  return len != 0 && len < program_store::NAME_SIZE;
}

static bool needs_lfn(const char* name) {
  return name != NULL && name[0] != 0 && !name_is_83_compatible(name);
}

static void fill_short_name(const char* name, program_store::ProgramType type, int unique_index, u8* out) {
  memset(out, ' ', 11);
  const bool alias = needs_lfn(name);

  if(alias) {
    u8 pos = 0;
    for(u8 i = 0; i < program_store::NAME_SIZE - 1 && name[i] != 0 && pos < 5; i++) {
      const char c = safe_name_char(name[i]);
      if(c != 0) out[pos++] = (u8) c;
    }
    if(pos == 0) out[pos++] = 'P';
    while(pos < 5) out[pos++] = '_';

    const u16 suffix = short_alias_hash(name);
    out[5] = '~';
    out[6] = (u8) short_alias_digit((u16) (suffix / 36));
    out[7] = (u8) short_alias_digit((u16) (suffix % 36));
  } else {
    u8 pos = 0;
    for(u8 i = 0; i < program_store::NAME_SIZE - 1 && name[i] != 0 && pos < 8; i++) {
      const char c = safe_name_char(name[i]);
      if(c != 0) out[pos++] = (u8) c;
    }

    if(pos == 0) {
      out[0] = 'P';
      out[1] = (u8) ('0' + ((unique_index / 100) % 10));
      out[2] = (u8) ('0' + ((unique_index / 10) % 10));
      out[3] = (u8) ('0' + (unique_index % 10));
    }
  }

  memcpy(out + 8, extension_for_type(type), 3);
}

static void fill_83_name(const program_store::Entry& entry, int flat_index, u8* out) {
  fill_short_name(entry.name, entry.type, flat_index, out);
}

static void format_full_name(program_store::ProgramType type, const char* name, char* out) {
  u8 pos = 0;
  while(pos < program_store::NAME_SIZE - 1 && name[pos] != 0) {
    out[pos] = name[pos];
    pos++;
  }
  out[pos++] = '.';
  const char* ext = extension_for_type(type);
  out[pos++] = ext[0];
  out[pos++] = ext[1];
  out[pos++] = ext[2];
  out[pos] = 0;
}

static u8 lfn_count_for_name(const char* full_name) {
  u8 len = 0;
  while(len < MAX_LFN_CHARS && full_name[len] != 0) len++;
  return (u8) ((len + 12) / 13);
}

static void put_lfn_char(u8* out, u8 slot, u16 value) {
  static const u8 offsets[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
  const u8 offset = offsets[slot];
  out[offset] = (u8) (value & 0xFF);
  out[offset + 1] = (u8) (value >> 8);
}

static void fill_lfn_entry(u8* out, const char* full_name, u8 sequence, u8 total, u8 checksum) {
  memset(out, 0xFF, 32);
  out[0] = sequence;
  if(sequence == total) out[0] |= 0x40;
  out[11] = FAT_ATTR_LFN;
  out[12] = 0;
  out[13] = checksum;
  out[26] = 0;
  out[27] = 0;

  u8 len = 0;
  while(len < MAX_LFN_CHARS && full_name[len] != 0) len++;

  const u8 base = (u8) ((sequence - 1) * 13);
  for(u8 i = 0; i < 13; i++) {
    const u8 index = (u8) (base + i);
    u16 value = 0xFFFF;
    if(index < len) value = (u8) full_name[index];
    else if(index == len) value = 0x0000;
    put_lfn_char(out, i, value);
  }
}

static void fill_dir_entry(u8* out, const program_store::Entry& entry, int flat_index) {
  fill_83_name(entry, flat_index, out);
  out[11] = FAT_ATTR_ARCHIVE;
  put_le16(out, 22, 0);
  put_le16(out, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 6));
  put_le16(out, 26, entry.data_len == 0 ? 0 : start_cluster_for_file(flat_index));
  put_le32(out, 28, entry.data_len);
}

#if defined(MK61_VFAT_TRACE)
static void fill_trace_dir_entry(u8* out) {
  memcpy(out, "VFAT    LOG", 11);
  out[11] = FAT_ATTR_ARCHIVE;
  put_le16(out, 22, 0);
  put_le16(out, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 6));
  put_le16(out, 26, TRACE_FIRST_CLUSTER);
  put_le32(out, 28, (u32) TRACE_FILE_CLUSTERS * SECTOR_SIZE);
}

static bool read_trace_data_sector(u16 cluster, u8* out) {
  memset(out, ' ', SECTOR_SIZE);
  if(!trace_cluster(cluster)) return false;

  const u32 sector_start = (u32) (cluster - TRACE_FIRST_CLUSTER) * SECTOR_SIZE;
  u32 source_pos = 0;
  u16 written = 0;

  for(u16 i = 0; i < trace_line_count && written < SECTOR_SIZE; i++) {
    const char* line = trace_lines[trace_line_index(i)];
    const u16 line_len = (u16) strlen(line);
    for(u16 j = 0; j < line_len && written < SECTOR_SIZE; j++) {
      if(source_pos >= sector_start) out[written++] = (u8) line[j];
      source_pos++;
    }
    if(source_pos >= sector_start && written < SECTOR_SIZE) out[written++] = '\r';
    source_pos++;
    if(source_pos >= sector_start && written < SECTOR_SIZE) out[written++] = '\n';
    source_pos++;
  }

  return true;
}
#else
static bool read_trace_data_sector(u16, u8*) { return false; }
#endif

static void fill_pending_name(const PendingWrite& pending, int unique_index, u8* out) {
  fill_short_name(pending.name, pending.type, unique_index, out);
}

static bool pending_visible(const PendingWrite& pending) {
  return pending.used && pending.name[0] != 0;
}

static void fill_pending_dir_entry(u8* out, const PendingWrite& pending, int unique_index) {
  fill_pending_name(pending, unique_index, out);
  out[11] = FAT_ATTR_ARCHIVE;
  put_le16(out, 22, 0);
  put_le16(out, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 6));
  put_le16(out, 26, pending.data_len == 0 ? 0 : pending.start_cluster);
  put_le32(out, 28, pending.data_len);
}

static u8 dir_entries_for_name(const char* name, program_store::ProgramType type) {
  if(!needs_lfn(name)) return 1;
  char full_name[MAX_LFN_CHARS + 1];
  format_full_name(type, name, full_name);
  return (u8) (lfn_count_for_name(full_name) + 1);
}

static void render_committed_dir_entry(u8* out, const program_store::Entry& entry, int flat_index, u8 offset) {
  const u8 entries = dir_entries_for_name(entry.name, entry.type);
  if(entries == 1 || offset + 1 == entries) {
    fill_dir_entry(out, entry, flat_index);
    return;
  }

  char full_name[MAX_LFN_CHARS + 1];
  u8 short_name[11];
  format_full_name(entry.type, entry.name, full_name);
  fill_83_name(entry, flat_index, short_name);
  const u8 lfn_count = (u8) (entries - 1);
  const u8 sequence = (u8) (lfn_count - offset);
  fill_lfn_entry(out, full_name, sequence, lfn_count, short_name_checksum(short_name));
}

static void render_pending_dir_entry(u8* out, const PendingWrite& pending, int unique_index, u8 offset) {
  const u8 entries = dir_entries_for_name(pending.name, pending.type);
  if(entries == 1 || offset + 1 == entries) {
    fill_pending_dir_entry(out, pending, unique_index);
    return;
  }

  char full_name[MAX_LFN_CHARS + 1];
  u8 short_name[11];
  format_full_name(pending.type, pending.name, full_name);
  fill_pending_name(pending, unique_index, short_name);
  const u8 lfn_count = (u8) (entries - 1);
  const u8 sequence = (u8) (lfn_count - offset);
  fill_lfn_entry(out, full_name, sequence, lfn_count, short_name_checksum(short_name));
}

static void read_root_sector(u32 root_sector, u8* out) {
  memset(out, 0, SECTOR_SIZE);
  const int first_entry = (int) (root_sector * (SECTOR_SIZE / 32));
  const int committed_files = file_count();

  for(int i = 0; i < (SECTOR_SIZE / 32); i++) {
    const int dir_index = first_entry + i;
    u8* item = out + i * 32;

    if(dir_index == 0) {
      memcpy(item, "MK61S FS   ", 11);
      item[11] = FAT_ATTR_VOLUME;
      continue;
    }

#if defined(MK61_VFAT_TRACE)
    if(dir_index == 1) {
      fill_trace_dir_entry(item);
      continue;
    }
#endif

    int cursor = first_program_dir_index();
    bool rendered = false;
    for(int file_index = 0; file_index < committed_files; file_index++) {
      program_store::Entry entry;
      if(!file_entry(file_index, entry)) continue;
      const u8 entries = dir_entries_for_name(entry.name, entry.type);
      if(dir_index >= cursor && dir_index < cursor + entries) {
        render_committed_dir_entry(item, entry, file_index, (u8) (dir_index - cursor));
        // Files queued for deletion keep their slots but are shown as
        // deleted; a zeroed slot would terminate directory enumeration.
        if(entry_is_pending_delete(entry)) item[0] = 0xE5;
        rendered = true;
        break;
      }
      cursor += entries;
    }
    if(rendered) continue;

    for(u8 pending_index = 0; pending_index < MAX_PENDING_WRITES; pending_index++) {
      PendingWrite& pending = pending_writes[pending_index];
      if(!pending_visible(pending)) continue;
      const u8 entries = dir_entries_for_name(pending.name, pending.type);
      if(dir_index >= cursor && dir_index < cursor + entries) {
        render_pending_dir_entry(item, pending, committed_files + pending_index, (u8) (dir_index - cursor));
        break;
      }
      cursor += entries;
    }
  }
}

static bool read_staged_sector(u16 cluster, u8* out) {
  const bool ok = program_store::vfat_stage_read(cluster, out);
  if(ok) tracef("READ-STAGE c=%u b0=%02X", cluster, out[0]);
  else tracef("READ-STAGE miss c=%u", cluster);
  return ok;
}

static bool read_pending_data_sector(u16 cluster, u8* out) {
  if(pending_for_cluster(cluster) == NULL) return false;
  memset(out, 0, SECTOR_SIZE);
  (void) read_staged_sector(cluster, out);
  return true;
}

static bool read_data_sector(u32 data_sector, u8* out) {
  memset(out, 0, SECTOR_SIZE);
  const u16 cluster = (u16) (data_sector + FIRST_DATA_CLUSTER);

  if(read_trace_data_sector(cluster, out)) return true;

  if(read_pending_data_sector(cluster, out)) return true;

  program_store::Entry entry;
  FileClusters chain;
  u8 pos = 0;
  if(!find_cluster_owner(cluster, entry, chain, pos)) {
    (void) read_staged_sector(cluster, out);
    return true;
  }

  const u16 file_offset = (u16) (pos * SECTOR_SIZE);
  u16 copied = 0;
  if(!program_store::read_range(entry.type, entry.name, file_offset, out, SECTOR_SIZE, &copied)) return false;
  if(copied < SECTOR_SIZE) memset(out + copied, 0, SECTOR_SIZE - copied);
  tracef("READ %s.%s c=%u off=%u got=%u b0=%02X", entry.name, extension_for_type(entry.type), cluster, file_offset, copied, out[0]);
  return true;
}

static bool write_committed_data_sector(const program_store::Entry& entry, u8 pos, const u8* data) {
  if(entry.data_len > MAX_IMPORTED_LEN) {
    tracef("UPDATE reject %s.%s len=%u", entry.name, extension_for_type(entry.type), entry.data_len);
    return false;
  }

  const u16 file_offset = (u16) (pos * SECTOR_SIZE);
  if(file_offset >= entry.data_len) return true;

  shared_scratch::Lease scratch(shared_scratch::Owner::VFAT_COMMIT, MAX_IMPORTED_LEN);
  if(!scratch.ok()) return false;
  u8* commit_file_data = scratch.data();
  u16 stored_len = 0;
  if(!program_store::read(entry.type, entry.name, commit_file_data, scratch.size(), &stored_len)) return false;
  if(stored_len < entry.data_len) memset(commit_file_data + stored_len, 0, (u16) (entry.data_len - stored_len));

  const u16 remaining = (u16) (entry.data_len - file_offset);
  const u16 copy_len = (remaining > SECTOR_SIZE) ? SECTOR_SIZE : remaining;
  memcpy(commit_file_data + file_offset, data, copy_len);

  tracef("UPDATE %s.%s off=%u len=%u b0=%02X %s", entry.name, extension_for_type(entry.type), file_offset, copy_len, data[0], trace_sector_is_zero(data) ? "zero" : "data");
  const bool ok = program_store::write(entry.type, entry.name, commit_file_data, entry.data_len);
  tracef("UPDATE %s.%s %s", entry.name, extension_for_type(entry.type), ok ? "ok" : "fail");
  return ok;
}

static u16 max_len_for_type(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61:  return program_store::MAX_MK61_TEXT_SIZE;
    case program_store::ProgramType::BASIC: return 511;
    case program_store::ProgramType::FOCAL: return 639;
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC: return 1023;
#endif
  }
  return 0;
}

static char upper_short_char(u8 c) {
  if(c >= 'a' && c <= 'z') return (char) (c - 'a' + 'A');
  return (char) c;
}

static char normalize_short_char(u8 c) {
  const char upper = upper_short_char(c);
  if((upper >= 'A' && upper <= 'Z') || (upper >= '0' && upper <= '9') || upper == '_' || upper == '-') return upper;
  return 0;
}

static char normalize_lfn_name_char(char c) {
  if((c >= 'A' && c <= 'Z') ||
     (c >= 'a' && c <= 'z') ||
     (c >= '0' && c <= '9') ||
     c == '_' || c == '-' || c == ' ') return c;
  return 0;
}

static bool parse_extension(const u8* ext, program_store::ProgramType& type) {
  char normalized[3];
  for(u8 i = 0; i < 3; i++) normalized[i] = upper_short_char(ext[i]);

  if(memcmp(normalized, "M61", 3) == 0) {
    type = program_store::ProgramType::MK61;
    return true;
  }
  if(memcmp(normalized, "BAS", 3) == 0) {
    type = program_store::ProgramType::BASIC;
    return true;
  }
  if(memcmp(normalized, "FOC", 3) == 0) {
    type = program_store::ProgramType::FOCAL;
    return true;
  }
#if MK61_ENABLE_TINYBASIC
  if(memcmp(normalized, "TBI", 3) == 0) {
    type = program_store::ProgramType::TINYBASIC;
    return true;
  }
#endif
  return false;
}

static bool parse_lfn_filename(const char* full_name, ParsedDirEntry& parsed) {
  if(full_name == NULL || full_name[0] == '.') return false;

  int dot = -1;
  int len = 0;
  while(len <= (int) MAX_LFN_CHARS && full_name[len] != 0) {
    if(full_name[len] == '.') dot = len;
    len++;
  }
  if(dot <= 0 || len - dot - 1 != 3) return false;
  if(dot >= (int) program_store::NAME_SIZE) return false;

  char ext[3];
  ext[0] = full_name[dot + 1];
  ext[1] = full_name[dot + 2];
  ext[2] = full_name[dot + 3];
  if(!parse_extension((const u8*) ext, parsed.type)) return false;

  for(int i = 0; i < dot; i++) {
    const char c = normalize_lfn_name_char(full_name[i]);
    if(c == 0) return false;
    parsed.name[i] = c;
  }
  parsed.name[dot] = 0;
  return true;
}

static bool parse_short_filename(const u8* item, ParsedDirEntry& parsed) {
  if(!parse_extension(item + 8, parsed.type)) return false;
  if(item[0] == '.' || item[0] == '_') return false;
  u8 name_len = 0;
  bool padding = false;
  for(u8 i = 0; i < 8; i++) {
    const u8 raw = item[i];
    if(raw == ' ') {
      padding = true;
      continue;
    }
    if(padding) return false;
    const char c = normalize_short_char(raw);
    if(c == 0 || name_len >= program_store::NAME_SIZE - 1) return false;
    parsed.name[name_len++] = c;
  }
  if(name_len == 0) return false;
  parsed.name[name_len] = 0;
  return true;
}

static bool parse_dir_entry(const u8* item, const char* lfn_name, ParsedDirEntry& parsed) {
  if(lfn_name != NULL) {
    if(!parse_lfn_filename(lfn_name, parsed)) return false;
  } else if(!parse_short_filename(item, parsed)) {
    return false;
  }

  const u32 len = get_le32(item, 28);
  if(len > max_len_for_type(parsed.type)) return false;
  parsed.data_len = (u16) len;
  parsed.start_cluster = get_le16(item, 26);
  if(parsed.data_len == 0) parsed.start_cluster = 0;
  else if(parsed.start_cluster < FIRST_DATA_CLUSTER || parsed.start_cluster >= CLUSTER_LIMIT) return false;
  return true;
}

static bool committed_short_entry_at_dir_index(int dir_index, program_store::Entry& entry, int& flat_index) {
  int cursor = first_program_dir_index();
  const int committed_files = file_count();
  for(int i = 0; i < committed_files; i++) {
    program_store::Entry current;
    if(!file_entry(i, current)) continue;
    const u8 entries = dir_entries_for_name(current.name, current.type);
    if(dir_index == cursor + entries - 1) {
      entry = current;
      flat_index = i;
      return true;
    }
    cursor += entries;
  }
  return false;
}

static PendingDelete* find_pending_delete(program_store::ProgramType type, const char* name) {
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    PendingDelete& pending = pending_deletes[i];
    if(!pending.used || pending.type != type) continue;
    if(strncmp(pending.name, name, program_store::NAME_SIZE) == 0) return &pending;
  }
  return NULL;
}

static PendingDelete* find_pending_delete_for_cluster(program_store::ProgramType type, u16 start_cluster, u16 data_len) {
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    PendingDelete& pending = pending_deletes[i];
    if(!pending.used || pending.type != type) continue;
    if(pending.start_cluster == start_cluster && pending.data_len == data_len) return &pending;
  }
  return NULL;
}

static PendingDelete* allocate_pending_delete(void) {
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    if(!pending_deletes[i].used) return &pending_deletes[i];
  }
  tracef("DELETE queue full");
  return NULL;
}

static bool entry_is_pending_delete(const program_store::Entry& entry) {
  return find_pending_delete(entry.type, entry.name) != NULL;
}

static void clear_pending_delete(PendingDelete* pending) {
  if(pending != NULL) memset(pending, 0, sizeof(*pending));
}

static bool mark_pending_delete(const program_store::Entry& entry, int flat_index) {
  PendingDelete* pending = find_pending_delete(entry.type, entry.name);
  if(pending == NULL) pending = allocate_pending_delete();
  if(pending == NULL) return false;

  const u16 start_cluster = entry.data_len == 0 ? 0 : start_cluster_for_file(flat_index);
  memset(pending, 0, sizeof(*pending));
  pending->used = true;
  pending->type = entry.type;
  strncpy(pending->name, entry.name, program_store::NAME_SIZE - 1);
  pending->name[program_store::NAME_SIZE - 1] = 0;
  pending->start_cluster = start_cluster;
  pending->data_len = entry.data_len;
  tracef("DELETE? %s.%s c=%u len=%u", pending->name, extension_for_type(pending->type), pending->start_cluster, pending->data_len);
  return true;
}

static bool committed_entry_matches_dir(const program_store::Entry& entry, int flat_index, const ParsedDirEntry& parsed) {
  const u16 expected_cluster = entry.data_len == 0 ? 0 : start_cluster_for_file(flat_index);
  return entry.type == parsed.type &&
         entry.data_len == parsed.data_len &&
         expected_cluster == parsed.start_cluster;
}

static bool parse_generated_dir_entry(int dir_index, const u8* item, ParsedDirEntry& parsed) {
  program_store::Entry entry;
  int file_index = 0;
  if(!committed_short_entry_at_dir_index(dir_index, entry, file_index)) return false;

  u8 name[11];
  fill_83_name(entry, file_index, name);
  if(memcmp(name, item, 11) != 0) return false;

  const u32 len = get_le32(item, 28);
  if(len > max_len_for_type(entry.type)) return false;

  parsed.type = entry.type;
  strncpy(parsed.name, entry.name, program_store::NAME_SIZE - 1);
  parsed.name[program_store::NAME_SIZE - 1] = 0;
  parsed.data_len = (u16) len;
  parsed.start_cluster = get_le16(item, 26);
  if(parsed.data_len == 0) parsed.start_cluster = 0;
  else if(parsed.start_cluster < FIRST_DATA_CLUSTER || parsed.start_cluster >= CLUSTER_LIMIT) return false;
  return true;
}

static PendingWrite* find_pending(program_store::ProgramType type, const char* name) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used || pending.type != type) continue;
    if(strncmp(pending.name, name, program_store::NAME_SIZE) == 0) return &pending;
  }
  return NULL;
}

static PendingWrite* allocate_pending(void) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    if(!pending_writes[i].used) return &pending_writes[i];
  }

  (void) flush_pending();
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    if(!pending_writes[i].used) return &pending_writes[i];
  }

  tracef("WRITE queue full");
  return NULL;
}

static bool pending_has_all_data(const PendingWrite& pending) {
  if(pending.data_len == 0) return true;
  if(pending.start_cluster < FIRST_DATA_CLUSTER) return false;
  FileClusters chain;
  pending_clusters(pending, chain);
  if(chain.count == 0) return false;
  for(u8 i = 0; i < chain.count; i++) {
    if(!program_store::vfat_stage_exists(chain.clusters[i])) return false;
  }
  return true;
}

static bool pending_has_any_data(const PendingWrite& pending) {
  FileClusters chain;
  pending_clusters(pending, chain);
  for(u8 i = 0; i < chain.count; i++) {
    if(program_store::vfat_stage_exists(chain.clusters[i])) return true;
  }
  return false;
}

static bool try_commit_pending(PendingWrite& pending) {
  if(!pending.used) return true;
  if(!pending_has_all_data(pending)) return true;
  if(pending.data_len > MAX_IMPORTED_LEN) return false;

  shared_scratch::Lease scratch(shared_scratch::Owner::VFAT_COMMIT, MAX_IMPORTED_LEN);
  if(!scratch.ok()) return false;
  u8* commit_file_data = scratch.data();

  FileClusters chain;
  pending_clusters(pending, chain);
  tracef("COMMIT %s.%s c=%u len=%u n=%u", pending.name, extension_for_type(pending.type), pending.start_cluster, pending.data_len, chain.count);

  for(u8 i = 0; i < chain.count; i++) {
    const u16 offset = (u16) (i * SECTOR_SIZE);
    if((usize) offset + SECTOR_SIZE > scratch.size()) return false;
    if(!read_staged_sector(chain.clusters[i], commit_file_data + offset)) return false;
  }

  tracef("COMMIT-DATA %s.%s len=%u b0=%02X", pending.name, extension_for_type(pending.type), pending.data_len, pending.data_len == 0 ? 0 : commit_file_data[0]);
  if(!program_store::write(pending.type, pending.name, commit_file_data, pending.data_len)) {
    tracef("COMMIT fail %s.%s", pending.name, extension_for_type(pending.type));
    return false;
  }
  tracef("COMMIT ok %s.%s", pending.name, extension_for_type(pending.type));
  clear_pending_delete(find_pending_delete(pending.type, pending.name));
  store_cluster_map(pending.type, pending.name, chain.clusters, chain.count);
  for(u8 i = 0; i < chain.count; i++) program_store::vfat_stage_forget(chain.clusters[i], 1);
  memset(&pending, 0, sizeof(pending));
  return true;
}

static bool stage_has_all_data(u16 start_cluster, u16 data_len) {
  if(data_len == 0) return true;
  if(start_cluster < FIRST_DATA_CLUSTER) return false;
  u16 chain[MAX_FILE_CLUSTERS];
  const u8 count = build_chain(start_cluster, data_len, chain);
  for(u8 i = 0; i < count; i++) {
    if(!program_store::vfat_stage_exists(chain[i])) return false;
  }
  return true;
}

static bool ranges_overlap(u16 start_a, u16 clusters_a, u16 start_b, u16 clusters_b) {
  if(clusters_a == 0 || clusters_b == 0) return false;
  const u16 end_a = (u16) (start_a + clusters_a);
  const u16 end_b = (u16) (start_b + clusters_b);
  return start_a < end_b && start_b < end_a;
}

static bool ignored_cluster(u16 cluster) {
  for(u8 i = 0; i < IGNORED_WRITE_RANGES; i++) {
    const IgnoredWriteRange& range = ignored_ranges[i];
    if(!range.used) continue;
    if(cluster >= range.start_cluster && cluster < (u16) (range.start_cluster + range.clusters)) return true;
  }
  return false;
}

static void clear_ignored_range(u16 start_cluster, u16 data_len) {
  if(data_len == 0 || start_cluster < FIRST_DATA_CLUSTER) return;
  const u16 clusters = clusters_for_len(data_len);
  for(u8 i = 0; i < IGNORED_WRITE_RANGES; i++) {
    IgnoredWriteRange& range = ignored_ranges[i];
    if(!range.used) continue;
    if(ranges_overlap(start_cluster, clusters, range.start_cluster, range.clusters)) range.used = false;
  }
}

static void ignore_write_range(u16 start_cluster, u32 data_len) {
  if(data_len == 0 || start_cluster < FIRST_DATA_CLUSTER) return;
  if(data_len > (u32) DATA_CLUSTER_CAPACITY * SECTOR_SIZE) return;

  const u16 clusters = (u16) ((data_len + SECTOR_SIZE - 1) / SECTOR_SIZE);
  if(clusters == 0) return;

  IgnoredWriteRange* range = NULL;
  for(u8 i = 0; i < IGNORED_WRITE_RANGES; i++) {
    if(!ignored_ranges[i].used) {
      range = &ignored_ranges[i];
      break;
    }
  }
  if(range == NULL) {
    range = &ignored_ranges[next_ignored_slot];
    next_ignored_slot = (u8) ((next_ignored_slot + 1) % IGNORED_WRITE_RANGES);
  }

  range->used = true;
  range->start_cluster = start_cluster;
  range->clusters = clusters;
  tracef("IGNORE c=%u len=%lu n=%u", start_cluster, (unsigned long) data_len, clusters);
  program_store::vfat_stage_forget(start_cluster, clusters);
}

static void ignore_dir_entry_range(const u8* item) {
  ignore_write_range(get_le16(item, 26), get_le32(item, 28));
}

static void clear_ignored_ranges(void) {
  memset(ignored_ranges, 0, sizeof(ignored_ranges));
  next_ignored_slot = 0;
}

// Assign every committed file its cluster range up front so the layout the
// host reads at mount time never changes underneath it.
static void pin_committed_files(void) {
  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!file_entry(i, entry)) continue;
    FileClusters chain;
    file_clusters(i, entry, chain);
  }
}

void reset_session(void) {
  memset(pending_writes, 0, sizeof(pending_writes));
  memset(pending_deletes, 0, sizeof(pending_deletes));
  memset(ignored_ranges, 0, sizeof(ignored_ranges));
  memset(cluster_maps, 0, sizeof(cluster_maps));
  memset(&root_lfn_state, 0, sizeof(root_lfn_state));
  memset(host_fat, 0, sizeof(host_fat));
  host_fat_written = 0;
  root_lfn_next_sector = 0;
  next_ignored_slot = 0;
  program_store::vfat_stage_clear();
  pin_committed_files();
}

static bool rename_committed_entry(const ParsedDirEntry& parsed, const char* old_name) {
  if(strncmp(old_name, parsed.name, program_store::NAME_SIZE) == 0) return true;
  tracef("RENAME %s.%s -> %s.%s", old_name, extension_for_type(parsed.type), parsed.name, extension_for_type(parsed.type));
  if(!program_store::rename(parsed.type, old_name, parsed.name)) return false;
  rename_cluster_map(parsed.type, old_name, parsed.name, parsed.start_cluster, parsed.data_len);
  return true;
}

static bool try_rename_pending_delete(const ParsedDirEntry& parsed) {
  PendingDelete* pending_delete = find_pending_delete_for_cluster(parsed.type, parsed.start_cluster, parsed.data_len);
  if(pending_delete == NULL) return false;

  char old_name[program_store::NAME_SIZE];
  strncpy(old_name, pending_delete->name, sizeof(old_name) - 1);
  old_name[sizeof(old_name) - 1] = 0;

  if(!rename_committed_entry(parsed, old_name)) return false;
  clear_pending_delete(pending_delete);
  return true;
}

// A rename observed as "delete old + create new" may reach flush with the
// directory entry but no data sectors; resolve it as a rename instead of
// losing the file.
static void reconcile_pending_renames(void) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used || pending.data_len == 0) continue;
    if(pending_has_any_data(pending)) continue;
    if(program_store::exists(pending.type, pending.name)) continue;

    ParsedDirEntry parsed;
    parsed.type = pending.type;
    strncpy(parsed.name, pending.name, program_store::NAME_SIZE - 1);
    parsed.name[program_store::NAME_SIZE - 1] = 0;
    parsed.start_cluster = pending.start_cluster;
    parsed.data_len = pending.data_len;
    if(try_rename_pending_delete(parsed)) memset(&pending, 0, sizeof(pending));
  }
}

bool flush_pending(void) {
  tracef("SYNC");
  bool ok = true;
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used) continue;
    if(!pending_has_all_data(pending)) {
      tracef("SYNC incomplete %s.%s c=%u len=%u", pending.name, extension_for_type(pending.type), pending.start_cluster, pending.data_len);
      continue;
    }
    if(!try_commit_pending(pending)) ok = false;
  }
  reconcile_pending_renames();
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    PendingDelete& pending = pending_deletes[i];
    if(!pending.used) continue;
    if(program_store::exists(pending.type, pending.name) && !program_store::remove(pending.type, pending.name)) {
      ok = false;
      continue;
    }
    forget_cluster_map(pending.type, pending.name);
    memset(&pending, 0, sizeof(pending));
  }
  purge_stale_cluster_maps();
  clear_ignored_ranges();
  return ok;
}

static bool try_rename_existing_entry(int dir_index, const ParsedDirEntry& parsed) {
  program_store::Entry entry;
  int file_index = 0;
  if(!committed_short_entry_at_dir_index(dir_index, entry, file_index)) return false;
  if(!committed_entry_matches_dir(entry, file_index, parsed)) return false;

  PendingDelete* pending_delete = find_pending_delete(entry.type, entry.name);
  if(!rename_committed_entry(parsed, entry.name)) return false;
  clear_pending_delete(pending_delete);
  return true;
}

// The host often rewrites directory sectors that still contain entries we
// generated; recognize those echoes so they do not spawn ghost writes or
// cancel queued deletions.
static bool committed_entry_echo(const ParsedDirEntry& parsed) {
  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!file_entry(i, entry)) continue;
    if(entry.type != parsed.type) continue;
    if(strncmp(entry.name, parsed.name, program_store::NAME_SIZE) != 0) continue;
    if(entry.data_len != parsed.data_len) return false;
    const u16 expected_cluster = entry.data_len == 0 ? 0 : start_cluster_for_file(i);
    return expected_cluster == parsed.start_cluster;
  }
  return false;
}

static bool upsert_pending(const ParsedDirEntry& parsed, int dir_index) {
  if(parsed.data_len > MAX_IMPORTED_LEN) {
    tracef("DIR reject %s.%s len=%u", parsed.name, extension_for_type(parsed.type), parsed.data_len);
    return false;
  }

  const bool has_new_data = parsed.data_len != 0 && stage_has_all_data(parsed.start_cluster, parsed.data_len);
  if(!has_new_data) {
    if(committed_entry_echo(parsed)) return true;
    if(try_rename_existing_entry(dir_index, parsed)) return true;
    if(try_rename_pending_delete(parsed)) return true;
  }

  PendingWrite* pending = find_pending(parsed.type, parsed.name);
  if(pending == NULL) pending = allocate_pending();
  if(pending == NULL) return false;

  memset(pending, 0, sizeof(*pending));
  pending->used = true;
  pending->type = parsed.type;
  strncpy(pending->name, parsed.name, program_store::NAME_SIZE - 1);
  pending->name[program_store::NAME_SIZE - 1] = 0;
  pending->start_cluster = parsed.start_cluster;
  pending->data_len = parsed.data_len;
  return try_commit_pending(*pending);
}

// Verifies that a 0xE5 tombstone written by the host really refers to this
// committed file (the host keeps size/cluster/name tail in deleted entries).
static bool deleted_entry_matches(const program_store::Entry& entry, int flat_index, const u8* item) {
  if(get_le32(item, 28) != entry.data_len) return false;
  const u16 item_cluster = get_le16(item, 26);
  if(entry.data_len != 0 && item_cluster != 0 && item_cluster != start_cluster_for_file(flat_index)) return false;
  return true;
}

static bool deleted_entry_matches_strict(const program_store::Entry& entry, int flat_index, const u8* item) {
  if(!deleted_entry_matches(entry, flat_index, item)) return false;
  u8 short_name[11];
  fill_83_name(entry, flat_index, short_name);
  return memcmp(short_name + 1, item + 1, 10) == 0;
}

static bool remove_existing_dir_slot(int dir_index, const u8* item) {
  // Deleting a file whose write has not committed yet: drop the pending
  // write and its staged sectors.
  const u16 item_cluster = get_le16(item, 26);
  const u32 item_len = get_le32(item, 28);
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used) continue;
    if(pending.start_cluster != item_cluster || pending.data_len != item_len) continue;
    FileClusters chain;
    pending_clusters(pending, chain);
    for(u8 j = 0; j < chain.count; j++) program_store::vfat_stage_forget(chain.clusters[j], 1);
    tracef("DELETE pending %s.%s", pending.name, extension_for_type(pending.type));
    memset(&pending, 0, sizeof(pending));
    return true;
  }

  program_store::Entry entry;
  int file_index = 0;
  if(committed_short_entry_at_dir_index(dir_index, entry, file_index) &&
     deleted_entry_matches(entry, file_index, item)) {
    return mark_pending_delete(entry, file_index);
  }

  // The host may address the entry through a stale directory index; find the
  // file by the tombstone's own identity instead.
  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry candidate;
    if(!file_entry(i, candidate)) continue;
    if(!deleted_entry_matches_strict(candidate, i, item)) continue;
    return mark_pending_delete(candidate, i);
  }

  return true;
}

static void reset_lfn_state(LfnState& lfn) {
  memset(&lfn, 0, sizeof(lfn));
}

static void parse_lfn_entry(const u8* item, LfnState& lfn) {
  static const u8 offsets[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
  const u8 sequence = (u8) (item[0] & 0x1F);
  if(sequence == 0) {
    reset_lfn_state(lfn);
    return;
  }

  if((item[0] & 0x40) != 0) {
    reset_lfn_state(lfn);
    lfn.active = true;
    lfn.valid = true;
    lfn.expected = sequence;
    lfn.checksum = item[13];
  } else if(!lfn.active) {
    lfn.active = true;
    lfn.valid = false;
    lfn.expected = sequence;
    lfn.checksum = item[13];
  }

  if(sequence > lfn.expected || item[13] != lfn.checksum) lfn.valid = false;

  for(u8 i = 0; i < 13; i++) {
    const u8 offset = offsets[i];
    const u16 value = get_le16(item, offset);
    const u16 name_index = (u16) ((sequence - 1) * 13 + i);
    if(value == 0x0000) break;
    if(value == 0xFFFF) continue;
    if(value < 0x20 || value > 0x7E || name_index >= MAX_LFN_CHARS) {
      lfn.valid = false;
      continue;
    }
    lfn.name[name_index] = (char) value;
  }

  lfn.seen_mask = (u16) (lfn.seen_mask | (1U << (sequence - 1)));
}

static const char* accepted_lfn_name(const LfnState& lfn, const u8* short_entry) {
  if(!lfn.active || !lfn.valid || lfn.expected == 0 || lfn.expected > 8) return NULL;
  const u16 expected_mask = (u16) ((1U << lfn.expected) - 1U);
  if((lfn.seen_mask & expected_mask) != expected_mask) return NULL;
  if(lfn.checksum != short_name_checksum(short_entry)) return NULL;
  return lfn.name;
}

static bool write_root_sector(u32 root_sector, const u8* data) {
  const int first_entry = (int) (root_sector * (SECTOR_SIZE / 32));
  LfnState& lfn = root_lfn_state;
  if(root_sector == 0 || !lfn.active || root_sector != root_lfn_next_sector) reset_lfn_state(lfn);
  root_lfn_next_sector = 0;

  for(int i = 0; i < (SECTOR_SIZE / 32); i++) {
    const int dir_index = first_entry + i;
    const u8* item = data + i * 32;
    const u8 first = item[0];
    const u8 attr = item[11];

    if(first == 0x00) {
      reset_lfn_state(lfn);
      continue;
    }

    if((attr & 0x3F) == FAT_ATTR_LFN) {
      if(first == 0xE5) reset_lfn_state(lfn);
      else parse_lfn_entry(item, lfn);
      continue;
    }

    if(first == 0xE5) {
      if(!remove_existing_dir_slot(dir_index, item)) return false;
      reset_lfn_state(lfn);
      continue;
    }

    const bool has_lfn = lfn.active;
    const char* lfn_name = accepted_lfn_name(lfn, item);

    if(dir_index == 0 || (attr & FAT_ATTR_VOLUME) != 0) {
      reset_lfn_state(lfn);
      continue;
    }
    if((attr & FAT_ATTR_DIRECTORY) != 0) {
      tracef("DIR ignore-dir %d c=%u", dir_index, get_le16(item, 26));
      ignore_write_range(get_le16(item, 26), SECTOR_SIZE);
      reset_lfn_state(lfn);
      continue;
    }
    if(has_lfn && lfn_name == NULL) {
      tracef("DIR ignore-lfn %d first=%02X attr=%02X", dir_index, first, attr);
      ignore_dir_entry_range(item);
      reset_lfn_state(lfn);
      continue;
    }

    ParsedDirEntry parsed;
    bool parsed_ok = parse_dir_entry(item, lfn_name, parsed);
    if(!parsed_ok && lfn_name == NULL) parsed_ok = parse_generated_dir_entry(dir_index, item, parsed);
    reset_lfn_state(lfn);
    if(!parsed_ok) {
      tracef("DIR ignore %d first=%02X attr=%02X c=%u len=%lu", dir_index, first, attr, get_le16(item, 26), (unsigned long) get_le32(item, 28));
      ignore_dir_entry_range(item);
      continue;
    }
    clear_ignored_range(parsed.start_cluster, parsed.data_len);
    tracef("DIR %d %s.%s c=%u len=%u", dir_index, parsed.name, extension_for_type(parsed.type), parsed.start_cluster, parsed.data_len);
    if(!upsert_pending(parsed, dir_index)) return false;
  }

  if(lfn.active && lfn.valid) {
    root_lfn_next_sector = root_sector + 1;
  } else if(lfn.active) {
    reset_lfn_state(lfn);
  }
  return true;
}

static bool write_data_sector(u32 data_sector, const u8* data) {
  const u16 cluster = (u16) (data_sector + FIRST_DATA_CLUSTER);
  if(trace_cluster(cluster)) return true;

  PendingWrite* pending = pending_for_cluster(cluster);
  if(pending != NULL) {
    if(!program_store::vfat_stage_write(cluster, data) && !program_store::vfat_stage_exists(cluster)) {
      tracef("DATA pending fail c=%u", cluster);
      return false;
    }
    tracef("DATA pending c=%u b0=%02X", cluster, data[0]);
    return try_commit_pending(*pending);
  }

  program_store::Entry entry;
  FileClusters chain;
  u8 pos = 0;
  if(find_cluster_owner(cluster, entry, chain, pos)) {
    tracef("DATA update c=%u b0=%02X", cluster, data[0]);
    return write_committed_data_sector(entry, pos, data);
  }

  if(ignored_cluster(cluster)) {
    tracef("DATA ignored c=%u b0=%02X", cluster, data[0]);
    if(!sector_is_zero(data)) (void) program_store::vfat_stage_write(cluster, data);
    return true;
  }

  if(sector_is_zero(data)) {
    tracef("DATA zero c=%u", cluster);
    return true;
  }

  const bool ok = program_store::vfat_stage_write(cluster, data);
  tracef("DATA stage c=%u b0=%02X %s", cluster, data[0], ok ? "ok" : "fail");
  return ok;
}

bool read_sector(u32 lba, u8* out) {
  if(out == NULL) return false;
  if(lba >= sector_count()) return false;

  if(lba == 0) {
    read_boot_sector(out);
    return true;
  }

  const u16 fat_sectors = fat_sector_count();
  const u32 root_start = first_root_sector();
  const u32 data_start = first_data_sector();

  if(lba < root_start) {
    const u32 fat_sector = (lba - RESERVED_SECTORS) % fat_sectors;
    read_fat_sector(fat_sector, out);
    return true;
  }

  if(lba < data_start) {
    read_root_sector(lba - root_start, out);
    return true;
  }

  return read_data_sector(lba - data_start, out);
}

bool write_sector(u32 lba, const u8* data) {
  if(data == NULL) return false;
  if(lba >= sector_count()) return false;
  if(lba == 0) return true;

  const u32 root_start = first_root_sector();
  const u32 data_start = first_data_sector();

  if(lba < root_start) {
    // Remember the FAT the host writes: it describes the real cluster
    // chains (including fragmentation) of the files being copied.
    const u32 fat_index = (lba - RESERVED_SECTORS) % fat_sector_count();
    record_host_fat_sector(fat_index, data);
    return true;
  }
  if(lba < data_start) return write_root_sector(lba - root_start, data);
  return write_data_sector(lba - data_start, data);
}

bool read_sectors(u32 lba, u8* out, u16 count) {
  if(out == NULL && count != 0) return false;
  for(u16 i = 0; i < count; i++) {
    if(!read_sector(lba + i, out + (u32) i * SECTOR_SIZE)) return false;
  }
  return true;
}

bool write_sectors(u32 lba, const u8* data, u16 count) {
  if(data == NULL && count != 0) return false;
  for(u16 i = 0; i < count; i++) {
    if(!write_sector(lba + i, data + (u32) i * SECTOR_SIZE)) return false;
  }
  return true;
}

} // namespace virtual_fat

extern "C" u8 MK61_VirtualFatSync(void) {
  return virtual_fat::flush_pending() ? 0 : 1;
}
