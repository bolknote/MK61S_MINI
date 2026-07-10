#include "virtual_fat.hpp"

#include "language_workspace.hpp"
#include "program_store.hpp"
#include "shared_scratch.hpp"

#include <stdio.h>
#if defined(MK61_VFAT_TRACE)
#include <stdarg.h>
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
static_assert(program_store::MAX_FONT_SIZE <= MAX_IMPORTED_LEN, "font files must fit the VFAT import buffer");
static constexpr u8 MAX_FILE_CLUSTERS = (MAX_IMPORTED_LEN + SECTOR_SIZE - 1) / SECTOR_SIZE;
static constexpr u16 MAX_LFN_CHARS = 64;
static constexpr u16 MAX_LFN_CODE_UNITS = 104;
static constexpr u8 MAX_PENDING_WRITES = program_store::MAX_ENTRIES;
static constexpr u8 MAX_PENDING_DELETES = program_store::MAX_ENTRIES;
static constexpr u8 IGNORED_WRITE_RANGES = program_store::MAX_ENTRIES;
// Enough raw FAT12 bytes for CLUSTER_LIMIT entries: (802 * 3 + 1) / 2 = 1203.
static constexpr u8 HOST_FAT_SECTORS = 3;
static constexpr u8 FAT_ATTR_VOLUME = 0x08;
static constexpr u8 FAT_ATTR_DIRECTORY = 0x10;
static constexpr u8 FAT_ATTR_ARCHIVE = 0x20;
static constexpr u8 FAT_ATTR_LFN = 0x0F;
static constexpr u16 ALIAS_SUFFIX_COUNT = 36U * 36U;
static constexpr u16 ALIAS_SUFFIX_AUTO = 0xFFFF;

static const program_store::ProgramType FILE_TYPES[] = {
  program_store::ProgramType::MK61,
  program_store::ProgramType::FOCAL
#if MK61_ENABLE_TINYBASIC
  ,
  program_store::ProgramType::TINYBASIC
#endif
  ,
  program_store::ProgramType::TEXT,
  program_store::ProgramType::MK61_STATE,
  program_store::ProgramType::FONT
};

struct PendingWrite {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 alias_suffix;
  u16 data_len;
  u16 chain[MAX_FILE_CLUSTERS];
  u8 chain_count;
  u8 dirty_mask;
  u8 flags;
};

static constexpr u8 PENDING_EXISTING_UPDATE = 0x01;

struct PendingDelete {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 start_cluster;
  u16 data_len;
};

struct IgnoredWriteRange {
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
  u16 alias_suffix;
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
  u8 next_sequence;
  u16 seen_mask;
  u8 checksum;
  u16 name[MAX_LFN_CODE_UNITS + 1];
};

struct SessionState {
  PendingWrite pending_writes[MAX_PENDING_WRITES];
  PendingDelete pending_deletes[MAX_PENDING_DELETES];
  IgnoredWriteRange ignored_ranges[IGNORED_WRITE_RANGES];
  ClusterMap cluster_maps[program_store::MAX_ENTRIES];
  LfnState root_lfn_state;
  u32 root_lfn_next_sector;
  u8 next_ignored_slot;
  u16 next_alias_suffix;

  // Raw copy of the FAT sectors the host has written this session. This is the
  // only way to learn the real (possibly fragmented) cluster chains the host
  // allocated for new files.
  u8 host_fat[HOST_FAT_SECTORS * SECTOR_SIZE];
  u8 host_fat_written;
  u16 host_fat_crc[FAT_COUNT][HOST_FAT_SECTORS];
  u8 host_fat_crc_valid[FAT_COUNT];
  u8 host_fat_conflict;

  // Cluster -> cluster_maps slot lookup (0xFF = unowned). FAT and data sector
  // handlers run inside the USB interrupt, so they must not rescan every file
  // for every cluster; that starved the main loop for seconds per FAT sector.
  u8 cluster_owner[DATA_CLUSTER_CAPACITY];
  u16 cached_data_clusters;
  u16 committed_count;
  bool cluster_index_valid;
};

static_assert(language_workspace::SIZE >= sizeof(SessionState), "language workspace must fit virtual FAT session");

static language_workspace::Lease session_lease;
static SessionState* session_state_ptr = NULL;

static bool ensure_session_state(void) {
  if(session_lease.ok() && session_state_ptr != NULL) return true;
  if(!session_lease.acquire(language_workspace::Owner::USB_DISK, sizeof(SessionState))) return false;
  session_state_ptr = (SessionState*) session_lease.data();
  return true;
}

static SessionState& session_state(void) {
  // All public virtual FAT entry points run inside the module-owned USB
  // session. Failure means another runtime violated the exclusive-session
  // contract; trap deterministically instead of dereferencing NULL.
  if(!ensure_session_state()) __builtin_trap();
  return *session_state_ptr;
}

static_assert(shared_scratch::SIZE >= MAX_IMPORTED_LEN, "shared scratch too small for virtual FAT commits");

static PendingDelete* find_pending_delete(program_store::ProgramType type, const char* name);
static void clear_pending_delete(PendingDelete* pending);
static bool entry_is_pending_delete(const program_store::Entry& entry);
static bool ignored_cluster(u16 cluster);
static void pin_committed_files(void);
static PendingWrite* find_pending(program_store::ProgramType type, const char* name);
static PendingWrite* allocate_pending(void);
static bool stage_write_with_recovery(u16 cluster, const u8* data);

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

static bool entry_visible(const program_store::Entry& entry) {
  return entry_name_visible(entry.name) && entry.data_len > 0;
}

static int file_count(void) {
  int count = 0;
  const int total = program_store::total_count();
  for(int i = 0; i < total; i++) {
    program_store::Entry entry;
    if(program_store::entry_at(i, entry) && entry_visible(entry)) count++;
  }
  const int max_files = ROOT_ENTRIES - 1;
  return (count > max_files) ? max_files : count;
}

static bool file_entry(int flat_index, program_store::Entry& out) {
  if(flat_index < 0) return false;

  int visible = 0;
  const int total = program_store::total_count();
  for(int i = 0; i < total; i++) {
    program_store::Entry entry;
    if(!program_store::entry_at(i, entry) || !entry_visible(entry)) continue;
    if(visible++ == flat_index) {
      out = entry;
      return true;
    }
  }

  return false;
}

/* ============================ host FAT shadow ============================ */

static u16 fat_sector_crc(const u8* data) {
  u16 crc = 0xFFFF;
  for(u16 i = 0; i < SECTOR_SIZE; i++) {
    crc ^= (u16) data[i] << 8;
    for(u8 bit = 0; bit < 8; bit++) {
      crc = (crc & 0x8000) ? (u16) ((crc << 1) ^ 0x1021) : (u16) (crc << 1);
    }
  }
  return crc;
}

static void record_host_fat_sector(u8 fat_copy, u32 fat_index, const u8* data) {
  if(fat_copy >= FAT_COUNT || fat_index >= HOST_FAT_SECTORS) return;
  memcpy(session_state().host_fat + fat_index * SECTOR_SIZE, data, SECTOR_SIZE);
  session_state().host_fat_written = (u8) (session_state().host_fat_written | (1U << fat_index));
  session_state().host_fat_crc[fat_copy][fat_index] = fat_sector_crc(data);
  session_state().host_fat_crc_valid[fat_copy] =
      (u8) (session_state().host_fat_crc_valid[fat_copy] | (1U << fat_index));
  const u8 bit = (u8) (1U << fat_index);
  const bool both = (session_state().host_fat_crc_valid[0] & bit) != 0 &&
                    (session_state().host_fat_crc_valid[1] & bit) != 0;
  if(both && session_state().host_fat_crc[0][fat_index] !=
                 session_state().host_fat_crc[1][fat_index]) {
    session_state().host_fat_conflict = (u8) (session_state().host_fat_conflict | bit);
  } else {
    session_state().host_fat_conflict = (u8) (session_state().host_fat_conflict & ~bit);
  }
}

static bool host_fat_byte(u32 offset, u8& out) {
  const u32 sector = offset / SECTOR_SIZE;
  if(sector >= HOST_FAT_SECTORS) return false;
  if((session_state().host_fat_written & (1U << sector)) == 0) return false;
  out = session_state().host_fat[offset];
  return true;
}

// FAT12 value the host wrote for a cluster, or 0xFFFF when unknown.
static u16 host_fat_next(u16 cluster) {
  const u32 offset = (u32) cluster + cluster / 2;
  const u32 first_sector = offset / SECTOR_SIZE;
  const u32 last_sector = (offset + 1) / SECTOR_SIZE;
  if(first_sector >= HOST_FAT_SECTORS || last_sector >= HOST_FAT_SECTORS) return 0xFFFF;
  if((session_state().host_fat_conflict & (1U << first_sector)) != 0 ||
     (session_state().host_fat_conflict & (1U << last_sector)) != 0) return 0xFFFE;
  u8 lo = 0;
  u8 hi = 0;
  if(!host_fat_byte(offset, lo) || !host_fat_byte(offset + 1, hi)) return 0xFFFF;
  const u16 raw = (u16) (lo | ((u16) hi << 8));
  return ((cluster & 1) == 0) ? (u16) (raw & 0x0FFF) : (u16) (raw >> 4);
}

// Freeze a cluster chain at directory-entry acceptance. Missing FAT sectors
// retain compatibility with hosts that omit unchanged FAT writes by using a
// contiguous chain, but an explicitly malformed link is never fabricated.
static bool build_chain(u16 start_cluster, u16 data_len, u16* out, u8& out_count) {
  out_count = 0;
  const u16 needed = clusters_for_len(data_len);
  if(needed == 0) return true;
  if(needed > MAX_FILE_CLUSTERS || start_cluster < FIRST_DATA_CLUSTER || start_cluster >= CLUSTER_LIMIT) return false;

  const u8 count = (u8) needed;
  u16 cluster = start_cluster;
  for(u8 i = 0; i < count; i++) {
    if(cluster < FIRST_DATA_CLUSTER || cluster >= CLUSTER_LIMIT) return false;
    for(u8 j = 0; j < i; j++) {
      if(out[j] == cluster) return false;
    }
    out[i] = cluster;
    out_count++;
    if(i + 1 == count) break;

    u16 next = host_fat_next(cluster);
    if(next == 0xFFFE) return false;
    if(next == 0xFFFF) next = (u16) (cluster + 1);
    else if(next < FIRST_DATA_CLUSTER || next >= CLUSTER_LIMIT) return false;
    cluster = next;
  }
  return true;
}

/* ============================ pending writes ============================= */

static void pending_clusters(const PendingWrite& pending, FileClusters& out) {
  out.count = pending.chain_count;
  for(u8 i = 0; i < pending.chain_count; i++) out.clusters[i] = pending.chain[i];
}

static u16 pending_start_cluster(const PendingWrite& pending) {
  return pending.chain_count == 0 ? 0 : pending.chain[0];
}

static PendingWrite* pending_for_cluster(u16 cluster, int* out_index = NULL) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = session_state().pending_writes[i];
    if(!pending.used || pending.chain_count == 0) continue;
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
    if(same_key(type, name, session_state().cluster_maps[i])) return &session_state().cluster_maps[i];
  }
  return NULL;
}

static ClusterMap* allocate_cluster_map(void) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    if(!session_state().cluster_maps[i].used) return &session_state().cluster_maps[i];
  }
  return NULL;
}

static bool alias_suffix_in_use(u16 suffix) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    const ClusterMap& map = session_state().cluster_maps[i];
    if(map.used && map.alias_suffix == suffix) return true;
  }
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    const PendingWrite& pending = session_state().pending_writes[i];
    if(pending.used && pending.alias_suffix == suffix) return true;
  }
  return false;
}

static u16 allocate_alias_suffix(void) {
  for(u16 attempt = 0; attempt < ALIAS_SUFFIX_COUNT; attempt++) {
    const u16 suffix = (u16) ((session_state().next_alias_suffix + attempt) %
                              ALIAS_SUFFIX_COUNT);
    if(alias_suffix_in_use(suffix)) continue;
    session_state().next_alias_suffix = (u16) ((suffix + 1) % ALIAS_SUFFIX_COUNT);
    return suffix;
  }
  return 0;
}

static void forget_cluster_map(program_store::ProgramType type, const char* name) {
  ClusterMap* map = find_cluster_map(type, name);
  if(map != NULL) memset(map, 0, sizeof(*map));
  session_state().cluster_index_valid = false;
}

static void purge_stale_cluster_maps(void) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    ClusterMap& map = session_state().cluster_maps[i];
    if(!map.used) continue;
    if(!program_store::exists(map.type, map.name)) memset(&map, 0, sizeof(map));
  }
  session_state().cluster_index_valid = false;
}

// Rebuilds the cluster -> owning map index. Clusters of files queued for
// deletion are left unowned so the host sees them as free space, but they
// still count towards the reported disk size to keep the geometry stable.
static void rebuild_cluster_index(void) {
  SessionState& state = session_state();
  memset(state.cluster_owner, 0xFF, sizeof(state.cluster_owner));
  u16 max_used = trace_cluster_count();

  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    const ClusterMap& map = state.cluster_maps[i];
    if(!map.used) continue;
    const bool deleted = find_pending_delete(map.type, map.name) != NULL;
    for(u8 j = 0; j < map.count; j++) {
      const u16 cluster = map.chain[j];
      if(cluster < FIRST_DATA_CLUSTER || cluster >= CLUSTER_LIMIT) continue;
      if(!deleted) state.cluster_owner[cluster - FIRST_DATA_CLUSTER] = i;
      const u16 used = (u16) (cluster + 1 - FIRST_DATA_CLUSTER);
      if(used > max_used) max_used = used;
    }
  }

  state.cached_data_clusters = max_used;
  state.cluster_index_valid = true;
}

// Files can also appear in the store without going through the host (e.g.
// self-tests or future device-side writes), so a cheap count check catches a
// store that changed behind the session's back.
static void ensure_cluster_index(void) {
  SessionState& state = session_state();
  const u16 committed = (u16) file_count();
  if(state.cluster_index_valid && state.committed_count == committed) return;
  pin_committed_files();
  rebuild_cluster_index();
  state.committed_count = committed;
}

// Map slot owning a cluster, or NULL. Position within the chain is returned
// through out_pos.
static const ClusterMap* cluster_owner_map(u16 cluster, u8& out_pos) {
  if(cluster < FIRST_DATA_CLUSTER || cluster >= CLUSTER_LIMIT) return NULL;
  ensure_cluster_index();
  const u8 slot = session_state().cluster_owner[cluster - FIRST_DATA_CLUSTER];
  if(slot == 0xFF) return NULL;
  const ClusterMap& map = session_state().cluster_maps[slot];
  for(u8 j = 0; j < map.count; j++) {
    if(map.chain[j] == cluster) {
      out_pos = j;
      return &map;
    }
  }
  return NULL;
}

static bool cluster_in_maps(u16 cluster) {
  for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
    const ClusterMap& map = session_state().cluster_maps[i];
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

static void store_cluster_map(program_store::ProgramType type, const char* name,
                              const u16* chain, u8 count,
                              u16 alias_suffix = ALIAS_SUFFIX_AUTO) {
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

  if(alias_suffix == ALIAS_SUFFIX_AUTO) {
    alias_suffix = map->used ? map->alias_suffix : allocate_alias_suffix();
  }

  memset(map, 0, sizeof(*map));
  map->used = true;
  map->type = type;
  strncpy(map->name, name, program_store::NAME_SIZE - 1);
  map->name[program_store::NAME_SIZE - 1] = 0;
  for(u8 i = 0; i < count && i < MAX_FILE_CLUSTERS; i++) map->chain[i] = chain[i];
  map->alias_suffix = alias_suffix;
  map->count = (count > MAX_FILE_CLUSTERS) ? MAX_FILE_CLUSTERS : count;
  session_state().cluster_index_valid = false;
}

static void rename_cluster_map(program_store::ProgramType type, const char* old_name, const char* new_name, u16 start_cluster, u16 data_len) {
  ClusterMap* map = find_cluster_map(type, old_name);
  if(map == NULL) {
    u16 chain[MAX_FILE_CLUSTERS];
    u8 count = 0;
    if(build_chain(start_cluster, data_len, chain, count)) store_cluster_map(type, new_name, chain, count);
    return;
  }

  strncpy(map->name, new_name, program_store::NAME_SIZE - 1);
  map->name[program_store::NAME_SIZE - 1] = 0;
  session_state().cluster_index_valid = false;
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
    session_state().cluster_index_valid = false;
  }

  if(map == NULL) {
    u16 start = allocate_contiguous_clusters(needed);
    if(start == 0) return;
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

// Committed program entry looked up by its store key.
static bool entry_by_key(program_store::ProgramType type, const char* name, program_store::Entry& out) {
  const int count = program_store::count(type);
  for(int i = 0; i < count; i++) {
    if(!program_store::entry(type, i, out)) continue;
    if(strncmp(out.name, name, program_store::NAME_SIZE) == 0) return true;
  }
  return false;
}

// Committed (and not pending-delete) file owning a cluster.
static bool find_cluster_owner(u16 cluster, program_store::Entry& out, FileClusters& out_chain, u8& out_pos) {
  u8 pos = 0;
  const ClusterMap* map = cluster_owner_map(cluster, pos);
  if(map == NULL) return false;
  if(!entry_by_key(map->type, map->name, out)) return false;

  out_chain.count = map->count;
  for(u8 i = 0; i < map->count; i++) out_chain.clusters[i] = map->chain[i];
  out_pos = pos;
  return true;
}

static u16 data_cluster_count(void) {
  ensure_cluster_index();
  return session_state().cached_data_clusters;
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
    case program_store::ProgramType::FOCAL: return "FOC";
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC: return "TBI";
#endif
    case program_store::ProgramType::TEXT: return "T1 ";
    case program_store::ProgramType::MK61_STATE: return "M2 ";
    case program_store::ProgramType::FONT: return "FMK";
  }
  return "M61";
}

static const char* visible_extension_for_type(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::TEXT: return "txt";
    case program_store::ProgramType::MK61_STATE: return "state.txt";
    case program_store::ProgramType::FONT: return "fmk";
    default: return extension_for_type(type);
  }
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

  u8 pos = 0;
  const ClusterMap* map = cluster_owner_map(cluster, pos);
  if(map != NULL) {
    return (pos + 1 < map->count) ? map->chain[pos + 1] : CLUSTER_EOF;
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

static bool name_uses_generated_alias_shape(const char* name) {
  if(name == NULL || strlen(name) != 8 || name[5] != '~') return false;
  const char a = safe_name_char(name[6]);
  const char b = safe_name_char(name[7]);
  const bool a36 = (a >= '0' && a <= '9') || (a >= 'A' && a <= 'Z');
  const bool b36 = (b >= '0' && b <= '9') || (b >= 'A' && b <= 'Z');
  return a36 && b36;
}

static bool needs_lfn(program_store::ProgramType type, const char* name) {
  if(type == program_store::ProgramType::TEXT || type == program_store::ProgramType::MK61_STATE) return true;
  return name != NULL && name[0] != 0 &&
         (!name_is_83_compatible(name) || name_uses_generated_alias_shape(name));
}

static void fill_short_name(const char* name, program_store::ProgramType type, int unique_index, u8* out) {
  memset(out, ' ', 11);
  const bool alias = needs_lfn(type, name);

  if(alias) {
    u8 pos = 0;
    for(u8 i = 0; i < program_store::NAME_SIZE - 1 && name[i] != 0 && pos < 5; i++) {
      const char c = safe_name_char(name[i]);
      if(c != 0) out[pos++] = (u8) c;
    }
    if(pos == 0) out[pos++] = 'P';
    while(pos < 5) out[pos++] = '_';

    // The session assigns and retains a unique two-digit base36 discriminator.
    // Names already shaped like generated aliases are forced through this path.
    const u16 suffix = (unique_index < 0) ? 0 : (u16) unique_index;
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
  const ClusterMap* map = find_cluster_map(entry.type, entry.name);
  const int suffix = map == NULL ? flat_index : map->alias_suffix;
  fill_short_name(entry.name, entry.type, suffix, out);
}

static void format_full_name(program_store::ProgramType type, const char* name, char* out) {
  u8 pos = 0;
  while(pos < program_store::NAME_SIZE - 1 && name[pos] != 0) {
    out[pos] = name[pos];
    pos++;
  }
  out[pos++] = '.';
  const char* ext = visible_extension_for_type(type);
  for(u8 i = 0; ext[i] != 0 && pos < MAX_LFN_CHARS; i++) out[pos++] = ext[i];
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
  (void) unique_index;
  fill_short_name(pending.name, pending.type, pending.alias_suffix, out);
}

static bool pending_visible(const PendingWrite& pending) {
  return pending.used && pending.name[0] != 0;
}

static void fill_pending_dir_entry(u8* out, const PendingWrite& pending, int unique_index) {
  fill_pending_name(pending, unique_index, out);
  out[11] = FAT_ATTR_ARCHIVE;
  put_le16(out, 22, 0);
  put_le16(out, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 6));
  put_le16(out, 26, pending.data_len == 0 ? 0 : pending_start_cluster(pending));
  put_le32(out, 28, pending.data_len);
}

static u8 dir_entries_for_name(const char* name, program_store::ProgramType type) {
  if(!needs_lfn(type, name)) return 1;
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
  const int entries_per_sector = SECTOR_SIZE / 32;
  const int first_entry = (int) (root_sector * entries_per_sector);
  const int last_entry = first_entry + entries_per_sector;

  if(first_entry == 0) {
    memcpy(out, "MK61S FS   ", 11);
    out[11] = FAT_ATTR_VOLUME;
  }

#if defined(MK61_VFAT_TRACE)
  if(first_entry <= 1 && 1 < last_entry) fill_trace_dir_entry(out + (1 - first_entry) * 32);
#endif

  // Single pass over the files with a running cursor: rescanning the whole
  // store for every flat index made a root-sector read cubic in file count.
  const int committed_files = file_count();
  int cursor = first_program_dir_index();
  int file_index = 0;
  const int total_entries = program_store::total_count();
  for(int raw_index = 0; raw_index < total_entries && cursor < last_entry; raw_index++) {
    program_store::Entry entry;
    if(!program_store::entry_at(raw_index, entry) || !entry_visible(entry)) continue;
    const u8 entries = dir_entries_for_name(entry.name, entry.type);
    for(u8 offset = 0; offset < entries; offset++) {
      const int dir_index = cursor + offset;
      if(dir_index < first_entry || dir_index >= last_entry) continue;
      u8* item = out + (dir_index - first_entry) * 32;
      render_committed_dir_entry(item, entry, file_index, offset);
      // Files queued for deletion keep their slots but are shown as
      // deleted; a zeroed slot would terminate directory enumeration.
      if(entry_is_pending_delete(entry)) item[0] = 0xE5;
    }
    cursor += entries;
    file_index++;
  }

  for(u8 pending_index = 0; pending_index < MAX_PENDING_WRITES && cursor < last_entry; pending_index++) {
    PendingWrite& pending = session_state().pending_writes[pending_index];
    if(!pending_visible(pending)) continue;
    const u8 entries = dir_entries_for_name(pending.name, pending.type);
    for(u8 offset = 0; offset < entries; offset++) {
      const int dir_index = cursor + offset;
      if(dir_index < first_entry || dir_index >= last_entry) continue;
      render_pending_dir_entry(out + (dir_index - first_entry) * 32, pending, committed_files + pending_index, offset);
    }
    cursor += entries;
  }
}

static bool read_staged_sector(u16 cluster, u8* out) {
  const bool ok = program_store::vfat_stage_read(cluster, out);
  if(ok) tracef("READ-STAGE c=%u b0=%02X", cluster, out[0]);
  else tracef("READ-STAGE miss c=%u", cluster);
  return ok;
}

static bool read_pending_data_sector(u16 cluster, u8* out) {
  int pos = 0;
  PendingWrite* pending = pending_for_cluster(cluster, &pos);
  if(pending == NULL) return false;
  if((pending->dirty_mask & (1U << pos)) == 0 &&
     (pending->flags & PENDING_EXISTING_UPDATE) != 0) return false;
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

static bool queue_committed_data_sector(const program_store::Entry& entry,
                                        const FileClusters& chain, u8 pos,
                                        const u8* data) {
  if(entry.data_len > MAX_IMPORTED_LEN) {
    tracef("UPDATE reject %s.%s len=%u", entry.name, extension_for_type(entry.type), entry.data_len);
    return false;
  }

  const u16 file_offset = (u16) (pos * SECTOR_SIZE);
  if(file_offset >= entry.data_len) return true;

  PendingWrite* pending = find_pending(entry.type, entry.name);
  if(pending == NULL) pending = allocate_pending();
  if(pending == NULL) return false;

  if(!pending->used) {
    memset(pending, 0, sizeof(*pending));
    pending->used = true;
    pending->type = entry.type;
    strncpy(pending->name, entry.name, program_store::NAME_SIZE - 1);
    pending->name[program_store::NAME_SIZE - 1] = 0;
    const ClusterMap* map = find_cluster_map(entry.type, entry.name);
    pending->alias_suffix = map == NULL ? allocate_alias_suffix() : map->alias_suffix;
    pending->data_len = entry.data_len;
    pending->chain_count = chain.count;
    for(u8 i = 0; i < chain.count; i++) pending->chain[i] = chain.clusters[i];
    pending->flags = PENDING_EXISTING_UPDATE;
  }

  if((pending->flags & PENDING_EXISTING_UPDATE) == 0 ||
     pending->data_len != entry.data_len || pending->chain_count != chain.count ||
     pos >= pending->chain_count || pending->chain[pos] != chain.clusters[pos]) return false;

  if(!stage_write_with_recovery(chain.clusters[pos], data) &&
     !program_store::vfat_stage_exists(chain.clusters[pos])) return false;
  pending->dirty_mask = (u8) (pending->dirty_mask | (1U << pos));
  tracef("UPDATE queue %s.%s off=%u b0=%02X %s", entry.name,
         extension_for_type(entry.type), file_offset, data[0],
         trace_sector_is_zero(data) ? "zero" : "data");
  return true;
}

static u16 max_len_for_type(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61:  return program_store::MAX_MK61_TEXT_SIZE;
    case program_store::ProgramType::FOCAL: return 639;
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC: return 1023;
#endif
    case program_store::ProgramType::TEXT: return program_store::MAX_MK61_TEXT_SIZE;
    case program_store::ProgramType::MK61_STATE: return program_store::MAX_MK61_TEXT_SIZE;
    case program_store::ProgramType::FONT: return program_store::MAX_FONT_SIZE;
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

static bool parse_extension(const u8* ext, program_store::ProgramType& type) {
  char normalized[3];
  for(u8 i = 0; i < 3; i++) normalized[i] = upper_short_char(ext[i]);

  if(memcmp(normalized, "M61", 3) == 0) {
    type = program_store::ProgramType::MK61;
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
  if(memcmp(normalized, "T1 ", 3) == 0) {
    type = program_store::ProgramType::TEXT;
    return true;
  }
  if(memcmp(normalized, "TXT", 3) == 0) {
    type = program_store::ProgramType::TEXT;
    return true;
  }
  if(memcmp(normalized, "M2 ", 3) == 0) {
    type = program_store::ProgramType::MK61_STATE;
    return true;
  }
  if(memcmp(normalized, "FMK", 3) == 0) {
    type = program_store::ProgramType::FONT;
    return true;
  }
  return false;
}

static bool lfn_ascii_equal_ci(const u16* name, u16 start, const char* suffix) {
  for(u16 i = 0; suffix[i] != 0; i++) {
    const u16 value = name[start + i];
    char expected = suffix[i];
    char actual = 0;
    if(value >= 'A' && value <= 'Z') actual = (char) (value - 'A' + 'a');
    else if(value >= 'a' && value <= 'z') actual = (char) value;
    else if(value >= '0' && value <= '9') actual = (char) value;
    else if(value == '.' || value == '_' || value == '-') actual = (char) value;
    else return false;
    if(expected >= 'A' && expected <= 'Z') expected = (char) (expected - 'A' + 'a');
    if(actual != expected) return false;
  }
  return true;
}

static u16 lfn_len(const u16* full_name) {
  u16 len = 0;
  while(len < MAX_LFN_CODE_UNITS && full_name[len] != 0) len++;
  return len;
}

static bool lfn_ends_with_ci(const u16* full_name, u16 len, const char* suffix) {
  u16 suffix_len = 0;
  while(suffix[suffix_len] != 0) suffix_len++;
  if(len <= suffix_len) return false;
  return lfn_ascii_equal_ci(full_name, (u16) (len - suffix_len), suffix);
}

static bool lfn_is_separator(u16 value) {
  switch(value) {
    case ' ': case '\t': case '_': case '-': case '.': case ',': case ';':
    case ':': case '(': case ')': case '[': case ']': case '{': case '}':
    case '+': case '=': case '&': case '!': case '?': case '#': case '\'':
      return true;
  }
  return false;
}

static bool append_char(char* out, u8 capacity, u8& len, char value) {
  if(len + 1 >= capacity) return false;
  out[len++] = value;
  out[len] = 0;
  return true;
}

static void append_text(char* out, u8 capacity, u8& len, const char* text) {
  for(u8 i = 0; text[i] != 0; i++) (void) append_char(out, capacity, len, text[i]);
}

static bool append_translit(u16 value, char* out, u8 capacity, u8& len) {
  if(value >= '0' && value <= '9') return append_char(out, capacity, len, (char) value);
  if(value >= 'A' && value <= 'Z') return append_char(out, capacity, len, (char) value);
  if(value >= 'a' && value <= 'z') return append_char(out, capacity, len, (char) value);

  switch(value) {
    case 0x0410: append_text(out, capacity, len, "A"); return true;
    case 0x0430: append_text(out, capacity, len, "a"); return true;
    case 0x0411: append_text(out, capacity, len, "B"); return true;
    case 0x0431: append_text(out, capacity, len, "b"); return true;
    case 0x0412: append_text(out, capacity, len, "V"); return true;
    case 0x0432: append_text(out, capacity, len, "v"); return true;
    case 0x0413: case 0x0490: append_text(out, capacity, len, "G"); return true;
    case 0x0433: case 0x0491: append_text(out, capacity, len, "g"); return true;
    case 0x0414: append_text(out, capacity, len, "D"); return true;
    case 0x0434: append_text(out, capacity, len, "d"); return true;
    case 0x0415: case 0x0401: case 0x0404: append_text(out, capacity, len, "E"); return true;
    case 0x0435: case 0x0451: case 0x0454: append_text(out, capacity, len, "e"); return true;
    case 0x0416: append_text(out, capacity, len, "Zh"); return true;
    case 0x0436: append_text(out, capacity, len, "zh"); return true;
    case 0x0417: append_text(out, capacity, len, "Z"); return true;
    case 0x0437: append_text(out, capacity, len, "z"); return true;
    case 0x0418: case 0x0406: append_text(out, capacity, len, "I"); return true;
    case 0x0438: case 0x0456: append_text(out, capacity, len, "i"); return true;
    case 0x0419: case 0x0407: append_text(out, capacity, len, "Y"); return true;
    case 0x0439: case 0x0457: append_text(out, capacity, len, "y"); return true;
    case 0x041A: append_text(out, capacity, len, "K"); return true;
    case 0x043A: append_text(out, capacity, len, "k"); return true;
    case 0x041B: append_text(out, capacity, len, "L"); return true;
    case 0x043B: append_text(out, capacity, len, "l"); return true;
    case 0x041C: append_text(out, capacity, len, "M"); return true;
    case 0x043C: append_text(out, capacity, len, "m"); return true;
    case 0x041D: append_text(out, capacity, len, "N"); return true;
    case 0x043D: append_text(out, capacity, len, "n"); return true;
    case 0x041E: append_text(out, capacity, len, "O"); return true;
    case 0x043E: append_text(out, capacity, len, "o"); return true;
    case 0x041F: append_text(out, capacity, len, "P"); return true;
    case 0x043F: append_text(out, capacity, len, "p"); return true;
    case 0x0420: append_text(out, capacity, len, "R"); return true;
    case 0x0440: append_text(out, capacity, len, "r"); return true;
    case 0x0421: append_text(out, capacity, len, "S"); return true;
    case 0x0441: append_text(out, capacity, len, "s"); return true;
    case 0x0422: append_text(out, capacity, len, "T"); return true;
    case 0x0442: append_text(out, capacity, len, "t"); return true;
    case 0x0423: case 0x040E: append_text(out, capacity, len, "U"); return true;
    case 0x0443: case 0x045E: append_text(out, capacity, len, "u"); return true;
    case 0x0424: append_text(out, capacity, len, "F"); return true;
    case 0x0444: append_text(out, capacity, len, "f"); return true;
    case 0x0425: append_text(out, capacity, len, "H"); return true;
    case 0x0445: append_text(out, capacity, len, "h"); return true;
    case 0x0426: append_text(out, capacity, len, "Ts"); return true;
    case 0x0446: append_text(out, capacity, len, "ts"); return true;
    case 0x0427: append_text(out, capacity, len, "Ch"); return true;
    case 0x0447: append_text(out, capacity, len, "ch"); return true;
    case 0x0428: append_text(out, capacity, len, "Sh"); return true;
    case 0x0448: append_text(out, capacity, len, "sh"); return true;
    case 0x0429: append_text(out, capacity, len, "Sch"); return true;
    case 0x0449: append_text(out, capacity, len, "sch"); return true;
    case 0x042B: append_text(out, capacity, len, "Y"); return true;
    case 0x044B: append_text(out, capacity, len, "y"); return true;
    case 0x042D: append_text(out, capacity, len, "E"); return true;
    case 0x044D: append_text(out, capacity, len, "e"); return true;
    case 0x042E: append_text(out, capacity, len, "Yu"); return true;
    case 0x044E: append_text(out, capacity, len, "yu"); return true;
    case 0x042F: append_text(out, capacity, len, "Ya"); return true;
    case 0x044F: append_text(out, capacity, len, "ya"); return true;
    case 0x042C: case 0x044C: case 0x042A: case 0x044A: return true;
  }
  return false;
}

static bool source_is_direct_internal_name(const u16* full_name, u16 base_len, const char* candidate) {
  u16 i = 0;
  while(i < base_len && i < program_store::NAME_SIZE - 1 && candidate[i] != 0) {
    if(full_name[i] != (u8) candidate[i]) return false;
    i++;
  }
  return i == base_len && candidate[i] == 0;
}

static bool name_exists_or_pending(program_store::ProgramType type, const char* name) {
  if(program_store::exists(type, name)) return true;
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    const PendingWrite& pending = session_state().pending_writes[i];
    if(!pending.used || pending.type != type) continue;
    if(strncmp(pending.name, name, program_store::NAME_SIZE) == 0) return true;
  }
  return false;
}

static bool build_normalized_name(const u16* full_name, u16 base_len, char* out) {
  static constexpr u8 MAX_WORDS = 12;
  static constexpr u8 WORD_SIZE = 16;
  char words[MAX_WORDS][WORD_SIZE];
  u8 word_len[MAX_WORDS];
  u8 word_count = 0;
  u8 current_len = 0;
  memset(words, 0, sizeof(words));
  memset(word_len, 0, sizeof(word_len));

  for(u16 i = 0; i < base_len; i++) {
    const u16 value = full_name[i];
    if(lfn_is_separator(value)) {
      if(current_len != 0) {
        word_len[word_count] = current_len;
        word_count++;
        current_len = 0;
        if(word_count >= MAX_WORDS) break;
      }
      continue;
    }
    if(word_count >= MAX_WORDS) break;
    if(!append_translit(value, words[word_count], WORD_SIZE, current_len)) continue;
  }

  if(word_count < MAX_WORDS && current_len != 0) {
    word_len[word_count] = current_len;
    word_count++;
  }

  if(word_count == 0) {
    strcpy(out, "FILE");
    return true;
  }

  // Words keep their full length while the joined name fits the store limit;
  // only oversized names get trimmed, longest word first. When even the
  // separators fit, they are kept as spaces so the stored name matches the
  // host filename exactly.
  u8 limit[MAX_WORDS];
  u16 total = 0;
  for(u8 i = 0; i < word_count; i++) {
    limit[i] = word_len[i];
    total = (u16) (total + limit[i]);
  }
  const bool with_spaces = (u16) (total + word_count - 1) <= program_store::NAME_SIZE - 1;

  while(total > program_store::NAME_SIZE - 1) {
    u8 best = MAX_WORDS;
    for(u8 i = 0; i < word_count; i++) {
      if(limit[i] <= 1) continue;
      if(best == MAX_WORDS || limit[i] > limit[best]) best = i;
    }
    if(best == MAX_WORDS) break;
    limit[best]--;
    total--;
  }

  u8 pos = 0;
  for(u8 i = 0; i < word_count && pos < program_store::NAME_SIZE - 1; i++) {
    if(with_spaces && i != 0) out[pos++] = ' ';
    for(u8 j = 0; j < limit[i] && words[i][j] != 0 && pos < program_store::NAME_SIZE - 1; j++) {
      out[pos++] = words[i][j];
    }
  }
  out[pos] = 0;
  return pos != 0;
}

static void make_import_name_unique(program_store::ProgramType type, const u16* full_name, u16 base_len, char* name) {
  if(source_is_direct_internal_name(full_name, base_len, name)) return;
  if(!name_exists_or_pending(type, name)) return;

  char base[program_store::NAME_SIZE];
  strncpy(base, name, sizeof(base) - 1);
  base[sizeof(base) - 1] = 0;

  for(u16 counter = 1; counter < 1000; counter++) {
    char suffix[4];
    snprintf(suffix, sizeof(suffix), "%u", (unsigned) counter);
    const u8 suffix_len = (u8) strlen(suffix);
    const u8 prefix_len = (u8) ((program_store::NAME_SIZE - 1 > suffix_len) ? (program_store::NAME_SIZE - 1 - suffix_len) : 0);
    u8 pos = 0;
    while(pos < prefix_len && base[pos] != 0) {
      name[pos] = base[pos];
      pos++;
    }
    for(u8 i = 0; suffix[i] != 0 && pos < program_store::NAME_SIZE - 1; i++) name[pos++] = suffix[i];
    name[pos] = 0;
    if(!name_exists_or_pending(type, name)) return;
  }
}

static bool parse_lfn_filename(const u16* full_name, ParsedDirEntry& parsed) {
  if(full_name == NULL || full_name[0] == '.') return false;

  const u16 len = lfn_len(full_name);
  if(len == 0) return false;

  u16 base_len = 0;
  if(lfn_ends_with_ci(full_name, len, ".state.txt")) {
    parsed.type = program_store::ProgramType::MK61_STATE;
    base_len = (u16) (len - 10);
  } else if(lfn_ends_with_ci(full_name, len, ".txt")) {
    parsed.type = program_store::ProgramType::TEXT;
    base_len = (u16) (len - 4);
  } else {
    int dot = -1;
    for(u16 i = 0; i < len; i++) {
      if(full_name[i] == '.') dot = (int) i;
    }
    if(dot <= 0 || len - (u16) dot - 1 != 3) return false;
    char ext[3];
    for(u8 i = 0; i < 3; i++) {
      const u16 value = full_name[(u16) dot + 1 + i];
      if(value > 0x7F) return false;
      ext[i] = (char) value;
    }
    if(!parse_extension((const u8*) ext, parsed.type)) return false;
    base_len = (u16) dot;
  }

  if(base_len == 0) return false;
  if(!build_normalized_name(full_name, base_len, parsed.name)) return false;
  make_import_name_unique(parsed.type, full_name, base_len, parsed.name);
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

static bool parse_dir_entry(const u8* item, const u16* lfn_name, ParsedDirEntry& parsed) {
  if(get_le16(item, 20) != 0) return false;
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
  int visible_index = 0;
  const int total = program_store::total_count();
  for(int i = 0; i < total; i++) {
    program_store::Entry current;
    if(!program_store::entry_at(i, current) || !entry_visible(current)) continue;
    const u8 entries = dir_entries_for_name(current.name, current.type);
    if(dir_index == cursor + entries - 1) {
      entry = current;
      flat_index = visible_index;
      return true;
    }
    cursor += entries;
    visible_index++;
  }
  return false;
}

static PendingDelete* find_pending_delete(program_store::ProgramType type, const char* name) {
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    PendingDelete& pending = session_state().pending_deletes[i];
    if(!pending.used || pending.type != type) continue;
    if(strncmp(pending.name, name, program_store::NAME_SIZE) == 0) return &pending;
  }
  return NULL;
}

static PendingDelete* find_pending_delete_for_cluster(program_store::ProgramType type, u16 start_cluster, u16 data_len) {
  // An empty entry (len 0, cluster 0) carries no identity: matching it against
  // a pending delete would "rename" an unrelated deleted file into every new
  // entry the host creates (seen as an endless Bumbl5/Bumbl6/... loop).
  if(data_len == 0) return NULL;
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    PendingDelete& pending = session_state().pending_deletes[i];
    if(!pending.used || pending.type != type) continue;
    if(pending.start_cluster == start_cluster && pending.data_len == data_len) return &pending;
  }
  return NULL;
}

static PendingDelete* allocate_pending_delete(void) {
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    if(!session_state().pending_deletes[i].used) return &session_state().pending_deletes[i];
  }
  tracef("DELETE queue full");
  return NULL;
}

static bool entry_is_pending_delete(const program_store::Entry& entry) {
  return find_pending_delete(entry.type, entry.name) != NULL;
}

static void clear_pending_delete(PendingDelete* pending) {
  if(pending == NULL) return;
  memset(pending, 0, sizeof(*pending));
  session_state().cluster_index_valid = false;
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
  session_state().cluster_index_valid = false;
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
  if(get_le16(item, 20) != 0) return false;
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
    PendingWrite& pending = session_state().pending_writes[i];
    if(!pending.used || pending.type != type) continue;
    if(strncmp(pending.name, name, program_store::NAME_SIZE) == 0) return &pending;
  }
  return NULL;
}

static PendingWrite* allocate_pending(void) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    if(!session_state().pending_writes[i].used) return &session_state().pending_writes[i];
  }

  (void) flush_pending();
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    if(!session_state().pending_writes[i].used) return &session_state().pending_writes[i];
  }

  tracef("WRITE queue full");
  return NULL;
}

static bool pending_has_all_data(const PendingWrite& pending) {
  if(pending.data_len == 0) return false;
  if((pending.flags & PENDING_EXISTING_UPDATE) != 0) return pending.dirty_mask != 0;
  if(pending.chain_count == 0) return false;
  FileClusters chain;
  pending_clusters(pending, chain);
  if(chain.count != clusters_for_len(pending.data_len)) return false;
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
  // The host creates the directory entry with length 0 first and fills in the
  // real length after the data sectors. Committing at this point would litter
  // the store with empty files (and burn flash erase cycles) on every copy.
  if(pending.data_len == 0) return false;
  if(!pending_has_all_data(pending)) return true;
  if(pending.data_len > MAX_IMPORTED_LEN) return false;

  shared_scratch::Lease scratch(shared_scratch::Owner::VFAT_COMMIT, MAX_IMPORTED_LEN);
  if(!scratch.ok()) return false;
  u8* commit_file_data = scratch.data();

  FileClusters chain;
  pending_clusters(pending, chain);
  tracef("COMMIT %s.%s c=%u len=%u n=%u", pending.name,
         extension_for_type(pending.type), pending_start_cluster(pending),
         pending.data_len, chain.count);

  if((pending.flags & PENDING_EXISTING_UPDATE) != 0) {
    u16 stored_len = 0;
    if(!program_store::read(pending.type, pending.name, commit_file_data,
                            scratch.size(), &stored_len)) return false;
    if(stored_len > pending.data_len) return false;
    if(stored_len < pending.data_len) {
      memset(commit_file_data + stored_len, 0, (u16) (pending.data_len - stored_len));
    }
  }

  for(u8 i = 0; i < chain.count; i++) {
    if((pending.flags & PENDING_EXISTING_UPDATE) != 0 &&
       (pending.dirty_mask & (1U << i)) == 0) continue;
    const u16 offset = (u16) (i * SECTOR_SIZE);
    if((usize) offset + SECTOR_SIZE > scratch.size()) return false;
    if(!read_staged_sector(chain.clusters[i], commit_file_data + offset)) return false;
  }

  tracef("COMMIT-DATA %s.%s len=%u b0=%02X", pending.name, extension_for_type(pending.type), pending.data_len, pending.data_len == 0 ? 0 : commit_file_data[0]);
  if(!program_store::write(pending.type, pending.name, commit_file_data, pending.data_len)) {
    tracef("COMMIT fail %s.%s", pending.name, extension_for_type(pending.type));
    // Keep the frozen transaction and its staged sectors. A failed SYNC must
    // never discard data that the host was previously allowed to write.
    return false;
  }
  tracef("COMMIT ok %s.%s", pending.name, extension_for_type(pending.type));
  clear_pending_delete(find_pending_delete(pending.type, pending.name));
  store_cluster_map(pending.type, pending.name, chain.clusters, chain.count,
                    pending.alias_suffix);
  for(u8 i = 0; i < chain.count; i++) program_store::vfat_stage_forget(chain.clusters[i], 1);
  memset(&pending, 0, sizeof(pending));
  return true;
}

static bool stage_has_all_data(u16 start_cluster, u16 data_len) {
  if(data_len == 0) return true;
  if(start_cluster < FIRST_DATA_CLUSTER) return false;
  u16 chain[MAX_FILE_CLUSTERS];
  u8 count = 0;
  if(!build_chain(start_cluster, data_len, chain, count)) return false;
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
    const IgnoredWriteRange& range = session_state().ignored_ranges[i];
    if(range.clusters == 0) continue;
    if(cluster >= range.start_cluster && cluster < (u16) (range.start_cluster + range.clusters)) return true;
  }
  return false;
}

static void clear_ignored_range(u16 start_cluster, u16 data_len) {
  if(data_len == 0 || start_cluster < FIRST_DATA_CLUSTER) return;
  const u16 clusters = clusters_for_len(data_len);
  for(u8 i = 0; i < IGNORED_WRITE_RANGES; i++) {
    IgnoredWriteRange& range = session_state().ignored_ranges[i];
    if(range.clusters == 0) continue;
    if(ranges_overlap(start_cluster, clusters, range.start_cluster, range.clusters)) range.clusters = 0;
  }
}

static void ignore_write_range(u16 start_cluster, u32 data_len) {
  if(data_len == 0 || start_cluster < FIRST_DATA_CLUSTER) return;
  if(data_len > (u32) DATA_CLUSTER_CAPACITY * SECTOR_SIZE) return;

  const u16 clusters = (u16) ((data_len + SECTOR_SIZE - 1) / SECTOR_SIZE);
  if(clusters == 0) return;

  IgnoredWriteRange* range = NULL;
  for(u8 i = 0; i < IGNORED_WRITE_RANGES; i++) {
    if(session_state().ignored_ranges[i].clusters == 0) {
      range = &session_state().ignored_ranges[i];
      break;
    }
  }
  if(range == NULL) {
    range = &session_state().ignored_ranges[session_state().next_ignored_slot];
    session_state().next_ignored_slot = (u8) ((session_state().next_ignored_slot + 1) % IGNORED_WRITE_RANGES);
  }

  range->start_cluster = start_cluster;
  range->clusters = clusters;
  tracef("IGNORE c=%u len=%lu n=%u", start_cluster, (unsigned long) data_len, clusters);
  program_store::vfat_stage_forget(start_cluster, clusters);
}

static void ignore_dir_entry_range(const u8* item) {
  ignore_write_range(get_le16(item, 26), get_le32(item, 28));
}

static void clear_ignored_ranges(void) {
  memset(session_state().ignored_ranges, 0, sizeof(session_state().ignored_ranges));
  session_state().next_ignored_slot = 0;
}

// Assign every committed file its cluster range up front so the layout the
// host reads at mount time never changes underneath it.
static void pin_committed_files(void) {
  int flat_index = 0;
  const int total = program_store::total_count();
  for(int i = 0; i < total; i++) {
    program_store::Entry entry;
    if(!program_store::entry_at(i, entry) || !entry_visible(entry)) continue;
    FileClusters chain;
    file_clusters(flat_index++, entry, chain);
  }
}

bool reset_session(void) {
  if(!ensure_session_state()) return false;
  memset(session_state().pending_writes, 0, sizeof(session_state().pending_writes));
  memset(session_state().pending_deletes, 0, sizeof(session_state().pending_deletes));
  memset(session_state().ignored_ranges, 0, sizeof(session_state().ignored_ranges));
  memset(session_state().cluster_maps, 0, sizeof(session_state().cluster_maps));
  memset(&session_state().root_lfn_state, 0, sizeof(session_state().root_lfn_state));
  memset(session_state().host_fat, 0, sizeof(session_state().host_fat));
  session_state().host_fat_written = 0;
  memset(session_state().host_fat_crc, 0, sizeof(session_state().host_fat_crc));
  memset(session_state().host_fat_crc_valid, 0, sizeof(session_state().host_fat_crc_valid));
  session_state().host_fat_conflict = 0;
  session_state().root_lfn_next_sector = 0;
  session_state().next_ignored_slot = 0;
  session_state().next_alias_suffix = 0;
  session_state().committed_count = 0;
  session_state().cluster_index_valid = false;
  program_store::vfat_stage_clear();
  ensure_cluster_index();
  return true;
}

void end_session(void) {
  session_state_ptr = NULL;
  session_lease.reset();
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
    PendingWrite& pending = session_state().pending_writes[i];
    if(!pending.used || pending.data_len == 0) continue;
    if(pending_has_any_data(pending)) continue;
    if(program_store::exists(pending.type, pending.name)) continue;

    ParsedDirEntry parsed;
    parsed.type = pending.type;
    strncpy(parsed.name, pending.name, program_store::NAME_SIZE - 1);
    parsed.name[program_store::NAME_SIZE - 1] = 0;
    parsed.start_cluster = pending_start_cluster(pending);
    parsed.data_len = pending.data_len;
    if(try_rename_pending_delete(parsed)) memset(&pending, 0, sizeof(pending));
  }
}

bool flush_pending(void) {
  tracef("SYNC");
  bool ok = true;
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = session_state().pending_writes[i];
    if(!pending.used) continue;
    if(pending.data_len == 0) {
      // Zero-length directory entries are transient host placeholders. The
      // program store intentionally has no empty-file objects, so retaining
      // these entries would only leak all pending slots.
      memset(&pending, 0, sizeof(pending));
      continue;
    }
    if(!pending_has_all_data(pending)) {
      tracef("SYNC incomplete %s.%s c=%u len=%u", pending.name,
             extension_for_type(pending.type), pending_start_cluster(pending),
             pending.data_len);
      ok = false;
      continue;
    }
    if(!try_commit_pending(pending)) ok = false;
  }
  reconcile_pending_renames();
  for(u8 i = 0; i < MAX_PENDING_DELETES; i++) {
    PendingDelete& pending = session_state().pending_deletes[i];
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
  program_store::Entry entry;
  if(!entry_by_key(parsed.type, parsed.name, entry) ||
     entry.data_len != parsed.data_len) return false;
  const ClusterMap* map = find_cluster_map(parsed.type, parsed.name);
  const u16 expected_cluster = entry.data_len == 0 || map == NULL || map->count == 0
    ? 0 : map->chain[0];
  return expected_cluster == parsed.start_cluster;
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

  u16 frozen_chain[MAX_FILE_CLUSTERS] = {0};
  u8 frozen_count = 0;
  if(!build_chain(parsed.start_cluster, parsed.data_len, frozen_chain, frozen_count)) {
    tracef("DIR reject-chain %s.%s c=%u len=%u", parsed.name,
           extension_for_type(parsed.type), parsed.start_cluster, parsed.data_len);
    return false;
  }

  PendingWrite* pending = find_pending(parsed.type, parsed.name);
  if(pending != NULL && pending_start_cluster(*pending) == parsed.start_cluster &&
     pending->data_len == parsed.data_len && pending->chain_count == frozen_count) {
    bool same_chain = true;
    for(u8 i = 0; i < frozen_count; i++) {
      if(pending->chain[i] != frozen_chain[i]) same_chain = false;
    }
    if(same_chain) {
      if((pending->flags & PENDING_EXISTING_UPDATE) != 0) return true;
      return parsed.data_len == 0 ? true : try_commit_pending(*pending);
    }
  }
  if(pending != NULL && pending->data_len != 0 && pending_has_any_data(*pending)) {
    tracef("DIR reject-mutate %s.%s", parsed.name, extension_for_type(parsed.type));
    return false;
  }

  for(u8 chain_pos = 0; chain_pos < frozen_count; chain_pos++) {
    const u16 cluster = frozen_chain[chain_pos];
    for(u8 i = 0; i < program_store::MAX_ENTRIES; i++) {
      const ClusterMap& map = session_state().cluster_maps[i];
      if(!map.used) continue;
      bool owns = false;
      for(u8 j = 0; j < map.count; j++) {
        if(map.chain[j] == cluster) owns = true;
      }
      if(!owns) continue;
      const bool same_file = map.type == parsed.type &&
          strncmp(map.name, parsed.name, program_store::NAME_SIZE) == 0;
      if(!same_file && find_pending_delete(map.type, map.name) == NULL) {
        tracef("DIR reject-overlap %s.%s c=%u", parsed.name,
               extension_for_type(parsed.type), cluster);
        return false;
      }
    }
    for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
      const PendingWrite& other = session_state().pending_writes[i];
      if(!other.used || &other == pending) continue;
      for(u8 j = 0; j < other.chain_count; j++) {
        if(other.chain[j] == cluster) {
          tracef("DIR reject-pending-overlap %s.%s c=%u", parsed.name,
                 extension_for_type(parsed.type), cluster);
          return false;
        }
      }
    }
  }
  if(pending == NULL) pending = allocate_pending();
  if(pending == NULL) return false;

  const u16 alias_suffix = pending->used
    ? pending->alias_suffix : allocate_alias_suffix();
  memset(pending, 0, sizeof(*pending));
  pending->used = true;
  pending->type = parsed.type;
  strncpy(pending->name, parsed.name, program_store::NAME_SIZE - 1);
  pending->name[program_store::NAME_SIZE - 1] = 0;
  pending->alias_suffix = alias_suffix;
  pending->data_len = parsed.data_len;
  pending->chain_count = frozen_count;
  for(u8 i = 0; i < frozen_count; i++) {
    pending->chain[i] = frozen_chain[i];
    if(program_store::vfat_stage_exists(frozen_chain[i])) {
      pending->dirty_mask = (u8) (pending->dirty_mask | (1U << i));
    }
  }
  return parsed.data_len == 0 ? true : try_commit_pending(*pending);
}

// Verifies that a 0xE5 tombstone written by the host really refers to this
// committed file (the host keeps size/cluster/name tail in deleted entries).
static bool deleted_entry_matches(const program_store::Entry& entry, int flat_index, const u8* item) {
  if(get_le32(item, 28) != entry.data_len) return false;
  const u16 item_cluster = get_le16(item, 26);
  const u16 expected_cluster = entry.data_len == 0 ? 0 : start_cluster_for_file(flat_index);
  return item_cluster == expected_cluster;
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
    PendingWrite& pending = session_state().pending_writes[i];
    if(!pending.used) continue;
    if(pending_start_cluster(pending) != item_cluster || pending.data_len != item_len) continue;
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
     deleted_entry_matches_strict(entry, file_index, item)) {
    return mark_pending_delete(entry, file_index);
  }

  // The host may address the entry through a stale directory index; find the
  // file by the tombstone's own identity instead.
  int flat_index = 0;
  const int total = program_store::total_count();
  for(int i = 0; i < total; i++) {
    program_store::Entry candidate;
    if(!program_store::entry_at(i, candidate) || !entry_visible(candidate)) continue;
    if(deleted_entry_matches_strict(candidate, flat_index, item)) {
      return mark_pending_delete(candidate, flat_index);
    }
    flat_index++;
  }

  return true;
}

static void reset_lfn_state(LfnState& lfn) {
  memset(&lfn, 0, sizeof(lfn));
}

static void parse_lfn_entry(const u8* item, LfnState& lfn) {
  static const u8 offsets[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
  const u8 sequence = (u8) (item[0] & 0x1F);
  const bool last = (item[0] & 0x40) != 0;
  if(sequence == 0 || sequence > 8 || item[11] != FAT_ATTR_LFN ||
     item[12] != 0 || get_le16(item, 26) != 0) {
    reset_lfn_state(lfn);
    return;
  }

  if(last) {
    reset_lfn_state(lfn);
    lfn.active = true;
    lfn.valid = true;
    lfn.expected = sequence;
    lfn.next_sequence = sequence;
    lfn.checksum = item[13];
  } else if(!lfn.active) {
    lfn.active = true;
    lfn.valid = false;
    lfn.expected = sequence;
    lfn.next_sequence = sequence;
    lfn.checksum = item[13];
  }

  if(sequence != lfn.next_sequence || item[13] != lfn.checksum ||
     (!last && sequence == lfn.expected)) lfn.valid = false;

  for(u8 i = 0; i < 13; i++) {
    const u8 offset = offsets[i];
    const u16 value = get_le16(item, offset);
    const u16 name_index = (u16) ((sequence - 1) * 13 + i);
    if(value == 0x0000) break;
    if(value == 0xFFFF) continue;
    if(value < 0x20 || name_index >= MAX_LFN_CODE_UNITS) {
      lfn.valid = false;
      continue;
    }
    lfn.name[name_index] = value;
  }

  lfn.seen_mask = (u16) (lfn.seen_mask | (1U << (sequence - 1)));
  if(lfn.next_sequence != 0) lfn.next_sequence--;
}

static const u16* accepted_lfn_name(const LfnState& lfn, const u8* short_entry) {
  if(!lfn.active || !lfn.valid || lfn.expected == 0 || lfn.expected > 8 ||
     lfn.next_sequence != 0) return NULL;
  const u16 expected_mask = (u16) ((1U << lfn.expected) - 1U);
  if((lfn.seen_mask & expected_mask) != expected_mask) return NULL;
  if(lfn.checksum != short_name_checksum(short_entry)) return NULL;
  return lfn.name;
}

static bool write_root_sector(u32 root_sector, const u8* data) {
  const int first_entry = (int) (root_sector * (SECTOR_SIZE / 32));
  LfnState& lfn = session_state().root_lfn_state;
  if(root_sector == 0 || !lfn.active || root_sector != session_state().root_lfn_next_sector) reset_lfn_state(lfn);
  session_state().root_lfn_next_sector = 0;

  for(int i = 0; i < (SECTOR_SIZE / 32); i++) {
    const int dir_index = first_entry + i;
    const u8* item = data + i * 32;
    const u8 first = item[0];
    const u8 attr = item[11];

    if(first == 0x00) {
      reset_lfn_state(lfn);
      break;
    }

    if(attr == FAT_ATTR_LFN) {
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
    const u16* lfn_name = accepted_lfn_name(lfn, item);

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
    if((attr & 0x06) != 0) {
      tracef("DIR ignore-hidden %d attr=%02X", dir_index, attr);
      ignore_dir_entry_range(item);
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
    session_state().root_lfn_next_sector = root_sector + 1;
  } else if(lfn.active) {
    reset_lfn_state(lfn);
  }
  return true;
}

// Segment cleaning is normally automatic. On a failed append, release ranges
// that metadata explicitly discarded, flush complete transactions, and retry.
static bool stage_write_with_recovery(u16 cluster, const u8* data) {
  if(program_store::vfat_stage_write(cluster, data)) return true;

  tracef("STAGE full c=%u", cluster);
  for(u8 i = 0; i < IGNORED_WRITE_RANGES; i++) {
    const IgnoredWriteRange& range = session_state().ignored_ranges[i];
    if(range.clusters != 0) program_store::vfat_stage_forget(range.start_cluster, range.clusters);
  }
  (void) flush_pending();
  return program_store::vfat_stage_write(cluster, data);
}

static bool write_data_sector(u32 data_sector, const u8* data) {
  const u16 cluster = (u16) (data_sector + FIRST_DATA_CLUSTER);
  if(trace_cluster(cluster)) return true;

  int pending_pos = 0;
  PendingWrite* pending = pending_for_cluster(cluster, &pending_pos);
  if(pending != NULL) {
    if(!stage_write_with_recovery(cluster, data) && !program_store::vfat_stage_exists(cluster)) {
      tracef("DATA pending fail c=%u", cluster);
      return false;
    }
    pending->dirty_mask = (u8) (pending->dirty_mask | (1U << pending_pos));
    tracef("DATA pending c=%u b0=%02X", cluster, data[0]);
    return true;
  }

  program_store::Entry entry;
  FileClusters chain;
  u8 pos = 0;
  if(find_cluster_owner(cluster, entry, chain, pos)) {
    tracef("DATA update c=%u b0=%02X", cluster, data[0]);
    return queue_committed_data_sector(entry, chain, pos, data);
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

  const bool ok = stage_write_with_recovery(cluster, data);
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
    const u32 fat_offset = lba - RESERVED_SECTORS;
    const u16 sectors_per_fat = fat_sector_count();
    const u8 fat_copy = (u8) (fat_offset / sectors_per_fat);
    const u32 fat_index = fat_offset % sectors_per_fat;
    record_host_fat_sector(fat_copy, fat_index, data);
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

const char* trace_line_at(u16 index) {
#if defined(MK61_VFAT_TRACE)
  if(index >= trace_line_count) return NULL;
  return trace_lines[trace_line_index(index)];
#else
  (void) index;
  return NULL;
#endif
}

} // namespace virtual_fat
