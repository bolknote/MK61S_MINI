#include "virtual_fat.hpp"
#include "config.h"

#if defined(ARDUINO_ARCH_STM32) && !defined(MK61_BUILD_USBDISK_MODULE) && \
    MK61_USBDISK_IS_LOADABLE

#include "virtual_fat_proxy.inc"

#else

#include "bounded_string.hpp"
#include "device_identity.hpp"
#include "fat_name.hpp"
#include "language_workspace.hpp"
#include "mk8_codec.hpp"
#if MK61_ANY_LOADABLE_MODULE
  #include "loadable_module_runtime.hpp"
#endif
#include "program_store.hpp"
#include "shared_scratch.hpp"
#include "storage_name.hpp"

#include <stdio.h>
#include <string.h>

#if defined(MK61_BUILD_USBDISK_MODULE)
extern "C" void mk61_usbdisk_startup_stage(u32 stage);
extern "C" bool mk61_usbdisk_startup_timed_out(void);
extern "C" u32 mk61_usbdisk_startup_timeout_elapsed(void);
extern "C" u32 mk61_usbdisk_startup_timeout_limit(void);
extern "C" void mk61_usbdisk_restart_startup_budget(void);
extern "C" u8* mk61_usbdisk_empty_stage_scratch(u32 size);
extern void idle_main_process();
#endif

namespace virtual_fat {
namespace {

#if defined(MK61_BUILD_USBDISK_MODULE)
static void startup_stage(u32 stage) {
  mk61_usbdisk_startup_stage(stage);
}
#else
static void startup_stage(u32) {}
#endif

static constexpr u8 FAT_COUNT = 2;
static constexpr u16 RESERVED_SECTORS = 1;
static constexpr u8 MEDIA_DESCRIPTOR = 0xF8;
static constexpr u16 FIRST_DATA_CLUSTER = 2;
static constexpr u16 FAT12_FREE = 0x000;
static constexpr u16 FAT12_BAD = 0xFF7;
static constexpr u16 FAT12_EOF = 0xFFF;
static constexpr u8 ATTR_READ_ONLY = 0x01;
static constexpr u8 ATTR_HIDDEN = 0x02;
static constexpr u8 ATTR_SYSTEM = 0x04;
static constexpr u8 ATTR_VOLUME = 0x08;
static constexpr u8 ATTR_DIRECTORY = 0x10;
static constexpr u8 ATTR_ARCHIVE = 0x20;
static constexpr u8 ATTR_LFN = 0x0F;
static constexpr u8 MAX_DEPTH = program_store::MAX_DIRECTORY_DEPTH;
static constexpr u8 MAX_LFN_ENTRIES = 8;
static constexpr u16 MAX_LFN_UNITS = MAX_LFN_ENTRIES * 13;
static constexpr u16 KIND_MAP_BYTES =
    (storage_geometry::FAT12_MAX_DATA_CLUSTERS * 2 + 7) / 8;
static constexpr u8 PRIMARY_CACHE_SLOTS = 13;
static constexpr u8 SCRATCH_CACHE_SLOTS = shared_scratch::SIZE / SECTOR_SIZE;
static constexpr u8 EXTERNAL_CACHE_SLOTS = 16;
static constexpr u8 MAX_CACHE_SLOTS = PRIMARY_CACHE_SLOTS +
                                      SCRATCH_CACHE_SLOTS +
                                      EXTERNAL_CACHE_SLOTS;

enum DesiredKind : u8 {
  DESIRED_NONE = 0,
  DESIRED_FILE = 1,
  DESIRED_DIRECTORY = 2,
  DESIRED_EXTENT = 3
};

struct LfnState {
  bool active;
  bool valid;
  u8 expected;
  u8 next_sequence;
  u8 checksum;
  u8 seen_mask;
  u16 name[MAX_LFN_UNITS];
};

struct ParsedNode {
  bool directory;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 id;
  u16 data_len;
  u8 attributes;
};

static constexpr u8 MAX_C6_FILE_CLUSTERS =
    program_store::MAX_FAT_EXTENTS_PER_FILE + 1U;

struct FileChain {
  u16 clusters[MAX_C6_FILE_CLUSTERS];
  u16 size;
  u8 cluster_count;
};

enum CacheState : u8 {
  CACHE_EMPTY = 0,
  CACHE_CLEAN = 1,
  // Новое значение ещё не сравнивалось с постоянными данными: пакет пришёл
  // напрямую из USB либо перезаписал грязный слот. Проверим при вытеснении
  // или синхронизации.
  CACHE_UNCHECKED = 2
};

struct CacheEntry {
  u32 lba;
  u32 age;
  CacheState state;
};

struct SessionState {
  u8 desired_kinds[KIND_MAP_BYTES];
  u32 cache_clock;
  CacheEntry cache[MAX_CACHE_SLOTS];
  u8 cache_data[PRIMARY_CACHE_SLOTS][SECTOR_SIZE];
};

static_assert(sizeof(SessionState) <= language_workspace::SIZE,
              "C6 FAT session and write-back cache must fit the shared 8 KiB workspace");
static_assert(sizeof(SessionState) >= PRIMARY_CACHE_SLOTS * SECTOR_SIZE,
              "C6 FAT cache geometry unexpectedly changed");
static_assert(SCRATCH_CACHE_SLOTS == 3,
              "shared scratch should lend exactly three USB sectors");
static_assert(shared_scratch::SIZE >= program_store::MAX_IMAGE1_SIZE,
              "USB import payload must fit the shared scratch buffer");

static language_workspace::Lease g_session_lease;
static shared_scratch::Lease g_cache_scratch;
static SessionState* g_session;
static u8* g_extra_cache;
static u8* g_commit_compression_buffer;
static usize g_commit_compression_buffer_size;
static u8 g_scratch_cache_slots;
static u8 g_extra_cache_slots;
static u8 g_cache_slots = PRIMARY_CACHE_SLOTS;
static constexpr u16 CLUSTER_MAP_BYTES =
    (storage_geometry::FAT12_MAX_DATA_CLUSTERS + 7) / 8;
struct SidecarScanMaps {
  u8 sidecars[CLUSTER_MAP_BYTES];
  u8 regular[CLUSTER_MAP_BYTES];
  u8 directories[CLUSTER_MAP_BYTES];
};
enum ClusterRole : u8 {
  CLUSTER_ROLE_NONE = 0,
  CLUSTER_ROLE_SIDECAR = 1,
  CLUSTER_ROLE_DIRECTORY = 2
};
static bool g_sidecar_scan_pending;
static bool g_sidecar_candidate_seen;
static constexpr u8 EXPORTED_SIZE_CACHE_ENTRIES = 16;
struct ExportedSizeCacheEntry {
  u16 id;
  u16 internal_size;
  u16 visible_size;
  u8 type;
  u8 valid;
};
static ExportedSizeCacheEntry
    g_exported_size_cache[EXPORTED_SIZE_CACHE_ENTRIES];
static u8 g_exported_size_cache_next;
static constexpr u8 DIRECTORY_CURSOR_COUNT = 8;
struct DirectoryRenderCursor {
  u16 parent_id;
  u8 root;
  u8 valid;
  u32 next_first_slot;
  u32 child_slot;
  u32 age;
  i32 child_index;
};
static DirectoryRenderCursor g_directory_cursors[DIRECTORY_CURSOR_COUNT];
static u32 g_directory_cursor_clock;

static void reset_directory_cursors() {
  memset(g_directory_cursors, 0, sizeof(g_directory_cursors));
  g_directory_cursor_clock = 0;
}

static bool resume_directory_cursor(u16 parent_id, bool root, u32 first_slot,
                                    u32& child_slot, int& child_index) {
  for(auto& cursor : g_directory_cursors) {
    if(!cursor.valid || cursor.parent_id != parent_id ||
       cursor.root != (u8) root || cursor.next_first_slot != first_slot) {
      continue;
    }
    cursor.age = ++g_directory_cursor_clock;
    child_slot = cursor.child_slot;
    child_index = cursor.child_index;
    return true;
  }
  return false;
}

static void save_directory_cursor(u16 parent_id, bool root,
                                  u32 next_first_slot, u32 child_slot,
                                  int child_index) {
  DirectoryRenderCursor* selected = nullptr;
  for(auto& cursor : g_directory_cursors) {
    if(cursor.valid && cursor.parent_id == parent_id &&
       cursor.root == (u8) root) {
      selected = &cursor;
      break;
    }
    if(!cursor.valid || selected == nullptr || cursor.age < selected->age) {
      selected = &cursor;
    }
  }
  if(selected == nullptr) return;
  selected->parent_id = parent_id;
  selected->root = root;
  selected->valid = 1;
  selected->next_first_slot = next_first_slot;
  selected->child_slot = child_slot;
  selected->child_index = child_index;
  selected->age = ++g_directory_cursor_clock;
}
#if defined(MK61_BUILD_USBDISK_MODULE)
static bool g_startup_recovery;
static u8 g_startup_recovery_reads;

class ScopedStartupRecovery {
 public:
  ScopedStartupRecovery() {
    g_startup_recovery = true;
    g_startup_recovery_reads = 0;
  }
  ~ScopedStartupRecovery() { g_startup_recovery = false; }
};

static void service_startup_recovery() {
  if(!g_startup_recovery || ++g_startup_recovery_reads < 8U) return;
  g_startup_recovery_reads = 0;
  // A persistent FAT transaction can require hundreds of SPI reads before
  // USB is started. Cooperate with the resident foreground loop so its sole
  // watchdog epoch continues to run; USB service is still inactive here and
  // therefore cannot re-enter this APP command.
  idle_main_process();
}
#else
class ScopedStartupRecovery {};
static void service_startup_recovery() {}
#endif
static DiagnosticState g_error;
static u32 g_session_volume_serial;
static bool g_session_volume_serial_valid;

static void record_startup_timeout() {
#if defined(MK61_BUILD_USBDISK_MODULE)
  if(mk61_usbdisk_startup_timed_out()) {
    g_error.fail(ErrorCode::RECOVERY_TIMEOUT, Phase::SESSION,
                 mk61_usbdisk_startup_timeout_elapsed(),
                 mk61_usbdisk_startup_timeout_limit(), nullptr, true);
  }
#endif
}

static bool ensure_session(void) {
  if(g_session_lease.ok() && g_session != NULL) return true;
  if(!g_session_lease.acquire(language_workspace::Owner::USB_DISK,
                              sizeof(SessionState))) return false;
  if(!program_store::vfat_stage_lock()) {
    g_session_lease.reset();
    return false;
  }
  g_session = (SessionState*) g_session_lease.data();
  memset(g_session, 0, sizeof(*g_session));
  return true;
}

static SessionState& session(void) {
  if(!ensure_session()) __builtin_trap();
  return *g_session;
}

static void update_cache_slot_count(void) {
  g_cache_slots = (u8) (PRIMARY_CACHE_SLOTS + g_scratch_cache_slots +
                        g_extra_cache_slots);
}

static const storage_geometry::Geometry& geometry(void) {
  return program_store::geometry();
}

static u32 fat_start(void) { return RESERVED_SECTORS; }

static u32 root_start(void) {
  return RESERVED_SECTORS + (u32) FAT_COUNT * geometry().fat_sectors;
}

static u32 data_start(void) {
  return root_start() + geometry().root_sectors;
}

static u16 cluster_limit(void) {
  return (u16) (FIRST_DATA_CLUSTER + geometry().max_nodes);
}

static bool valid_cluster(u16 cluster) {
  return cluster >= FIRST_DATA_CLUSTER && cluster < cluster_limit();
}

static bool sidecar_filter_enabled(void) {
  return g_session != NULL &&
         geometry().max_nodes <= storage_geometry::FAT12_MAX_DATA_CLUSTERS;
}

static bool cluster_marked(const u8* map, u16 cluster) {
  if(!valid_cluster(cluster) || !sidecar_filter_enabled()) return false;
  const u16 id = (u16) (cluster - FIRST_DATA_CLUSTER);
  return (map[id >> 3] & (u8) (1U << (id & 7U))) != 0;
}

static ClusterRole cluster_role(u16 cluster) {
  if(!valid_cluster(cluster) || !sidecar_filter_enabled()) {
    return CLUSTER_ROLE_NONE;
  }
  const u16 id = (u16) (cluster - FIRST_DATA_CLUSTER);
  const u16 bit = (u16) (id * 2U);
  return (ClusterRole) ((session().desired_kinds[bit / 8] >> (bit & 7)) & 3U);
}

static void set_cluster_role(u16 cluster, ClusterRole role) {
  const u16 id = (u16) (cluster - FIRST_DATA_CLUSTER);
  const u16 bit = (u16) (id * 2U);
  session().desired_kinds[bit / 8] = (u8) (
      session().desired_kinds[bit / 8] | ((u8) role << (bit & 7)));
}

static void mark_cluster(u8* map, u16 cluster) {
  const u16 id = (u16) (cluster - FIRST_DATA_CLUSTER);
  map[id >> 3] |= (u8) (1U << (id & 7U));
}

static bool sidecar_data_lba(u32 lba) {
  if(lba < data_start() || !sidecar_filter_enabled()) return false;
  const u32 id = (lba - data_start()) / geometry().sectors_per_cluster;
  return id < geometry().max_nodes &&
         cluster_role((u16) (id + FIRST_DATA_CLUSTER)) ==
             CLUSTER_ROLE_SIDECAR;
}

static bool directory_metadata_lba(u32 lba) {
  if(!sidecar_filter_enabled()) return false;
  if(lba >= fat_start() && lba < data_start()) return true;
  if(lba < data_start()) return false;
  const u32 id = (lba - data_start()) / geometry().sectors_per_cluster;
  return id < geometry().max_nodes &&
         cluster_role((u16) (id + FIRST_DATA_CLUSTER)) ==
             CLUSTER_ROLE_DIRECTORY;
}

static bool contains_sidecar_name(const u8* block) {
  for(u8 slot = 0; slot < SECTOR_SIZE / 32; slot++) {
    const u8* item = block + (u16) slot * 32U;
    if(item[0] == '.' && item[1] == '_') return true;
    if(item[11] == ATTR_LFN && (item[0] & 0x1FU) == 1U &&
       item[1] == '.' && item[2] == 0 &&
       item[3] == '_' && item[4] == 0) return true;
  }
  return false;
}

static u16 id_for_cluster(u16 cluster) {
  return (u16) (cluster - FIRST_DATA_CLUSTER);
}

static u16 cluster_for_id(u16 id) {
  return (u16) (id + FIRST_DATA_CLUSTER);
}

static u32 cluster_lba(u16 cluster, u8 sector_in_cluster = 0) {
  return data_start() + (u32) (cluster - FIRST_DATA_CLUSTER) *
         geometry().sectors_per_cluster + sector_in_cluster;
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

static void put_le16(u8* data, u16 offset, u16 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
}

static void put_le32(u8* data, u16 offset, u32 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
  data[offset + 2] = (u8) (value >> 16);
  data[offset + 3] = (u8) (value >> 24);
}

static char ascii_lower(char value) {
  return value >= 'A' && value <= 'Z' ? (char) (value - 'A' + 'a') : value;
}

static bool ends_with_ci(const char* text, const char* suffix) {
  const usize text_len = strlen(text);
  const usize suffix_len = strlen(suffix);
  if(suffix_len > text_len) return false;
  text += text_len - suffix_len;
  for(usize i = 0; i < suffix_len; i++) {
    if(ascii_lower(text[i]) != ascii_lower(suffix[i])) return false;
  }
  return true;
}

static const char* visible_extension(program_store::ProgramType type) {
  return program_store::file_extension(type);
}

static const char* short_extension(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61: return "M61";
    case program_store::ProgramType::FOCAL: return "FOC";
    case program_store::ProgramType::TINYBASIC: return "TBI";
    case program_store::ProgramType::TEXT: return "T1 ";
    case program_store::ProgramType::MK61_STATE: return "M2 ";
    case program_store::ProgramType::FONT: return "FMK";
    case program_store::ProgramType::IMAGE1: return "WBM";
    case program_store::ProgramType::APP: return "APP";
    case program_store::ProgramType::CHIP8: return "CH8";
    case program_store::ProgramType::MARKDOWN: return "MD ";
  }
  return "BIN";
}

static bool parse_file_name(char* full_name, program_store::ProgramType& type) {
  struct Suffix {
    const char* text;
    program_store::ProgramType type;
  };
  static const Suffix suffixes[] = {
    {".state.txt", program_store::ProgramType::MK61_STATE},
    {".m61", program_store::ProgramType::MK61},
    {".foc", program_store::ProgramType::FOCAL},
    {".tbi", program_store::ProgramType::TINYBASIC},
    {".txt", program_store::ProgramType::TEXT},
    {".md", program_store::ProgramType::MARKDOWN},
    {".t1", program_store::ProgramType::TEXT},
    {".m2", program_store::ProgramType::MK61_STATE},
    {".fmk", program_store::ProgramType::FONT},
    {".app", program_store::ProgramType::APP},
    {".ch8", program_store::ProgramType::CHIP8},
    {".wbmp", program_store::ProgramType::IMAGE1},
    // Псевдоним нужен при чтении записи без LFN: 8.3-проекция WBMP — WBM.
    {".wbm", program_store::ProgramType::IMAGE1}
  };
  for(const Suffix& suffix : suffixes) {
    if(!ends_with_ci(full_name, suffix.text)) continue;
    const usize base_len = strlen(full_name) - strlen(suffix.text);
    if(base_len == 0 || base_len >= program_store::NAME_SIZE) return false;
    full_name[base_len] = 0;
    type = suffix.type;
    return true;
  }
  return false;
}

static u32 maximum_file_size(program_store::ProgramType type) {
#if defined(MK61_BUILD_USBDISK_MODULE)
  const u32 internal = portable_system::call(
      MK61_SYS_USBDISK, MK61_USBDISK_MAX_FILE_SIZE, (u32) type);
  return program_store::text_content(type) ? internal * 3U : internal;
#else
  if(type == program_store::ProgramType::TINYBASIC) {
    return (u32) program_store::MAX_TINYBASIC_TEXT_SIZE * 3U;
  }
  if(type == program_store::ProgramType::FONT) {
    return program_store::MAX_FONT_SIZE;
  }
  if(type == program_store::ProgramType::IMAGE1) {
    return program_store::MAX_IMAGE1_SIZE;
  }
  if(type == program_store::ProgramType::CHIP8) {
    return program_store::MAX_CHIP8_SIZE;
  }
  if(type == program_store::ProgramType::APP) {
    return program_store::MAX_APP_FILE_SIZE;
  }
  const u32 internal = program_store::MAX_MK61_TEXT_SIZE;
  return program_store::text_content(type) ? internal * 3U : internal;
#endif
}

static void clear_exported_size_cache(void) {
  memset(g_exported_size_cache, 0, sizeof(g_exported_size_cache));
  g_exported_size_cache_next = 0;
}

static bool cached_exported_size(const program_store::Entry& entry,
                                 u32& output) {
  for(const auto& cached : g_exported_size_cache) {
    if(cached.valid && cached.id == entry.id &&
       cached.internal_size == entry.data_len &&
       cached.type == (u8) entry.type) {
      output = cached.visible_size;
      return true;
    }
  }
  return false;
}

static void cache_exported_size(const program_store::Entry& entry,
                                u32 size) {
  if(size > 0xFFFFU) return;
  ExportedSizeCacheEntry& cached =
      g_exported_size_cache[g_exported_size_cache_next];
  cached.id = entry.id;
  cached.internal_size = entry.data_len;
  cached.visible_size = (u16) size;
  cached.type = (u8) entry.type;
  cached.valid = 1;
  g_exported_size_cache_next = (u8) (
      (g_exported_size_cache_next + 1U) % EXPORTED_SIZE_CACHE_ENTRIES);
}

static u8* whole_text_scratch(u16 size) {
  // During a commit the UC1609 framebuffer is already detached from the
  // display and lent to the USB-disk module.  Prefer that full 8 KiB span:
  // the persistent staging journal is normally non-empty at this point, so
  // its smaller key-index scratch cannot be borrowed.  Materializing a text
  // file once avoids restarting ZX0 decompression for every 64-byte range.
  if(g_commit_compression_buffer != NULL &&
     size <= g_commit_compression_buffer_size) {
    return g_commit_compression_buffer;
  }
#if defined(MK61_BUILD_USBDISK_MODULE)
  // With an empty persistent journal its 1.5 KiB sorted-key array is idle.
  // Reuse it for one complete ordinary M8 text file instead of repeatedly
  // restarting ZX0 decompression for every 64-byte range. TinyBasic sources
  // larger than this buffer retain the bounded streaming fallback below.
  return mk61_usbdisk_empty_stage_scratch(size);
#else
  (void) size;
  return nullptr;
#endif
}

static bool exported_file_size(const program_store::Entry& entry,
                               u32& output) {
  output = entry.data_len;
  if(!program_store::text_content(entry.type)) return true;
  if(cached_exported_size(entry, output)) return true;
  output = 0;
  if(u8* const complete = whole_text_scratch(entry.data_len)) {
    u16 copied = 0;
    if(!program_store::read_range_id(entry.id, 0, complete, entry.data_len,
                                     &copied) || copied != entry.data_len) {
      return false;
    }
    for(u16 index = 0; index < copied; ++index) {
      if(!mk8::valid_byte(complete[index])) return false;
      output += mk8::utf8(complete[index]).size;
    }
    cache_exported_size(entry, output);
    return true;
  }
  u8 bytes[64];
  u16 offset = 0;
  while(offset < entry.data_len) {
    const u16 remaining = (u16) (entry.data_len - offset);
    const u16 wanted = remaining < (u16) sizeof(bytes)
        ? remaining : (u16) sizeof(bytes);
    u16 copied = 0;
    if(!program_store::read_range_id(entry.id, offset, bytes, wanted,
                                     &copied) || copied != wanted) return false;
    for(u16 index = 0; index < copied; ++index) {
      if(!mk8::valid_byte(bytes[index])) return false;
      output += mk8::utf8(bytes[index]).size;
    }
    offset = (u16) (offset + copied);
  }
  cache_exported_size(entry, output);
  return true;
}

static bool read_exported_range(const program_store::Entry& entry,
                                u32 external_offset, u8* output,
                                u16 capacity, u16& copied) {
  copied = 0;
  if(output == NULL && capacity != 0) return false;
  if(!program_store::text_content(entry.type)) {
    if(external_offset >= entry.data_len) return true;
    const u16 wanted = (u16) (((u32) entry.data_len - external_offset < capacity)
        ? (u32) entry.data_len - external_offset : capacity);
    return program_store::read_range_id(
        entry.id, (u16) external_offset, output, wanted, &copied);
  }

  u32 external_position = 0;
  const u32 external_end = external_offset + capacity;
  if(u8* const complete = whole_text_scratch(entry.data_len)) {
    u16 received = 0;
    if(!program_store::read_range_id(entry.id, 0, complete, entry.data_len,
                                     &received) || received != entry.data_len) {
      return false;
    }
    for(u16 index = 0; index < received; ++index) {
      if(!mk8::valid_byte(complete[index])) return false;
      const mk8::Utf8Bytes encoded = mk8::utf8(complete[index]);
      for(u8 part = 0; part < encoded.size; ++part, ++external_position) {
        if(external_position >= external_offset &&
           external_position < external_end) {
          output[copied++] = encoded.data[part];
        }
      }
      if(external_position >= external_end) break;
    }
    return true;
  }
  u8 bytes[64];
  u16 internal_offset = 0;
  while(internal_offset < entry.data_len && external_position < external_end) {
    const u16 remaining = (u16) (entry.data_len - internal_offset);
    const u16 wanted = remaining < (u16) sizeof(bytes)
        ? remaining : (u16) sizeof(bytes);
    u16 received = 0;
    if(!program_store::read_range_id(entry.id, internal_offset, bytes, wanted,
                                     &received) || received != wanted) return false;
    for(u16 index = 0; index < received; ++index) {
      if(!mk8::valid_byte(bytes[index])) return false;
      const mk8::Utf8Bytes encoded = mk8::utf8(bytes[index]);
      for(u8 part = 0; part < encoded.size; ++part, ++external_position) {
        if(external_position >= external_offset &&
           external_position < external_end) {
          output[copied++] = encoded.data[part];
        }
      }
      if(external_position >= external_end) break;
    }
    internal_offset = (u16) (internal_offset + received);
  }
  return true;
}

static bool m8_to_utf16(const char* input, u16* output, u16 capacity,
                        u16& output_len) {
  output_len = 0;
  if(input == NULL) return false;
  usize converted = 0;
  const usize input_len = strlen(input);
  if(!mk8::to_utf16((const u8*) input, input_len, output, capacity,
                    converted) || converted > 0xFFFFU) return false;
  output_len = (u16) converted;
  return true;
}

static bool utf16_to_m8(const u16* input, u16 input_len, char* output,
                        u16 capacity) {
  if(input == NULL || output == NULL || capacity == 0) return false;
  u16 units = 0;
  while(units < input_len && input[units] != 0 && input[units] != 0xFFFFU) {
    ++units;
  }
  usize converted = 0;
  if(!mk8::from_utf16(input, units, (u8*) output, capacity - 1U,
                      converted) || converted == 0 || converted >= capacity) {
    return false;
  }
  output[converted] = 0;
  return true;
}

static void full_name(const program_store::Entry& entry, char* output,
                      usize capacity) {
  if(entry.kind == program_store::NodeKind::DIRECTORY) {
    bounded_string::copy(output, capacity, entry.name);
    return;
  }
  snprintf(output, capacity, "%s.%s", entry.name,
           visible_extension(entry.type));
}

static u8 short_checksum(const u8* name) {
  u8 sum = 0;
  for(u8 i = 0; i < 11; i++) {
    sum = (u8) (((sum & 1) ? 0x80 : 0) + (sum >> 1) + name[i]);
  }
  return sum;
}

static char hex_digit(u8 value) {
  return value < 10 ? (char) ('0' + value) : (char) ('A' + value - 10);
}

static void short_alias(const program_store::Entry& entry, u8* output) {
  memset(output, ' ', 11);
  output[0] = entry.kind == program_store::NodeKind::DIRECTORY ? 'D' : 'F';
  output[1] = hex_digit((u8) (entry.id >> 12));
  output[2] = hex_digit((u8) ((entry.id >> 8) & 0x0F));
  output[3] = hex_digit((u8) ((entry.id >> 4) & 0x0F));
  output[4] = hex_digit((u8) (entry.id & 0x0F));
  if(entry.kind == program_store::NodeKind::FILE) {
    memcpy(output + 8, short_extension(entry.type), 3);
  }
}

static u8 node_dirent_count(const program_store::Entry& entry) {
  char name[program_store::NAME_SIZE + 16];
  full_name(entry, name, sizeof(name));
  const u16 count = fat_name::dirent_count(name);
  return count <= 0xFF ? (u8) count : 0;
}

static void put_lfn_unit(u8* item, u8 index, u16 value) {
  static const u8 offsets[13] = {
    1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30
  };
  put_le16(item, offsets[index], value);
}

static bool render_node_dirent(const program_store::Entry& entry, u8 offset,
                               u8* item) {
  char name[program_store::NAME_SIZE + 16];
  u16 units[MAX_LFN_UNITS];
  u16 unit_count = 0;
  full_name(entry, name, sizeof(name));
  if(!m8_to_utf16(name, units, MAX_LFN_UNITS, unit_count)) return false;
  const u8 lfn_count = (u8) ((unit_count + 12) / 13);
  u8 alias[11];
  short_alias(entry, alias);
  if(offset < lfn_count) {
    const u8 sequence = (u8) (lfn_count - offset);
    memset(item, 0xFF, 32);
    item[0] = sequence;
    if(sequence == lfn_count) item[0] |= 0x40;
    item[11] = ATTR_LFN;
    item[12] = 0;
    item[13] = short_checksum(alias);
    put_le16(item, 26, 0);
    const u16 base = (u16) (sequence - 1) * 13;
    for(u8 i = 0; i < 13; i++) {
      const u16 index = (u16) (base + i);
      const u16 value = index < unit_count ? units[index] :
                        index == unit_count ? 0 : 0xFFFF;
      put_lfn_unit(item, i, value);
    }
    return true;
  }
  if(offset != lfn_count) return false;
  memset(item, 0, 32);
  memcpy(item, alias, sizeof(alias));
  item[11] = entry.kind == program_store::NodeKind::DIRECTORY
      ? ATTR_DIRECTORY : ATTR_ARCHIVE;
  put_le16(item, 22, 0);
  put_le16(item, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 19));
  put_le16(item, 26, cluster_for_id(entry.id));
  u32 visible_size = 0;
  if(entry.kind == program_store::NodeKind::FILE &&
     !exported_file_size(entry, visible_size)) return false;
  put_le32(item, 28, visible_size);
  return true;
}

static bool render_no_index_dirent(u8 offset, u8* item) {
  static const char name[] = ".metadata_never_index";
  static const u8 alias[11] = {
    'M', 'E', 'T', 'A', 'D', 'A', 'T', 'A', 'N', 'I', 'X'
  };
  u16 units[MAX_LFN_UNITS];
  u16 unit_count = 0;
  if(!m8_to_utf16(name, units, MAX_LFN_UNITS, unit_count)) return false;
  const u8 lfn_count = (u8) ((unit_count + 12) / 13);
  if(offset < lfn_count) {
    const u8 sequence = (u8) (lfn_count - offset);
    memset(item, 0xFF, 32);
    item[0] = sequence;
    if(sequence == lfn_count) item[0] |= 0x40;
    item[11] = ATTR_LFN;
    item[12] = 0;
    item[13] = short_checksum(alias);
    put_le16(item, 26, 0);
    const u16 base = (u16) (sequence - 1) * 13;
    for(u8 i = 0; i < 13; i++) {
      const u16 index = (u16) (base + i);
      const u16 value = index < unit_count ? units[index] :
                        index == unit_count ? 0 : 0xFFFF;
      put_lfn_unit(item, i, value);
    }
    return true;
  }
  if(offset != lfn_count) return false;
  memset(item, 0, 32);
  memcpy(item, alias, sizeof(alias));
  item[11] = ATTR_READ_ONLY | ATTR_HIDDEN | ATTR_SYSTEM;
  return true;
}

static void boot_sector(u8* output) {
  memset(output, 0, SECTOR_SIZE);
  output[0] = 0xEB;
  output[1] = 0x3C;
  output[2] = 0x90;
  memcpy(output + 3, "MK61C6  ", 8);
  put_le16(output, 11, SECTOR_SIZE);
  output[13] = geometry().sectors_per_cluster;
  put_le16(output, 14, RESERVED_SECTORS);
  output[16] = FAT_COUNT;
  put_le16(output, 17, geometry().root_entries);
  if(geometry().logical_sectors <= 0xFFFFUL) {
    put_le16(output, 19, (u16) geometry().logical_sectors);
  } else {
    put_le32(output, 32, geometry().logical_sectors);
  }
  output[21] = MEDIA_DESCRIPTOR;
  put_le16(output, 22, geometry().fat_sectors);
  put_le16(output, 24, 32);
  put_le16(output, 26, 64);
  put_le32(output, 28, 0);
  output[36] = 0x80;
  output[38] = 0x29;
  put_le32(output, 39, volume_serial());
  memcpy(output + 43, "MK61S C6   ", 11);
  memcpy(output + 54, "FAT12   ", 8);
  output[510] = 0x55;
  output[511] = 0xAA;
}

static u16 base_fat_value(u16 cluster) {
  if(cluster == 0) return (u16) (0xF00 | MEDIA_DESCRIPTOR);
  if(cluster == 1) return FAT12_EOF;
  if(!valid_cluster(cluster)) return FAT12_FREE;
  const u16 id = id_for_cluster(cluster);
  program_store::Entry entry;
  if(program_store::entry_by_id(id, entry)) {
    if(entry.kind == program_store::NodeKind::FILE) {
      u16 extent = 0;
      return program_store::first_file_extent(id, extent)
          ? cluster_for_id(extent) : FAT12_EOF;
    }
    u16 extent = 0;
    return program_store::first_extent(id, extent)
        ? cluster_for_id(extent) : FAT12_EOF;
  }
  u16 owner = 0;
  u16 next = 0;
  u8 cluster_index = 0;
  if(program_store::file_extent_info(id, owner, cluster_index, next)) {
    (void) owner;
    (void) cluster_index;
    return next == program_store::INVALID_ID
        ? FAT12_EOF : cluster_for_id(next);
  }
  if(program_store::extent_info(id, owner, next)) {
    (void) owner;
    return next == program_store::INVALID_ID ? FAT12_EOF : cluster_for_id(next);
  }
  return FAT12_FREE;
}

static void set_fat_byte(u8* output, u32 sector, u32 byte_offset,
                         u8 value, u8 mask) {
  if(byte_offset / SECTOR_SIZE != sector) return;
  const u16 offset = (u16) (byte_offset % SECTOR_SIZE);
  output[offset] = (u8) ((output[offset] & ~mask) | (value & mask));
}

static void set_fat_entry(u8* output, u32 sector, u16 cluster, u16 value) {
  const u32 offset = (u32) cluster + cluster / 2;
  value &= 0x0FFF;
  if((cluster & 1) == 0) {
    set_fat_byte(output, sector, offset, (u8) value, 0xFF);
    set_fat_byte(output, sector, offset + 1, (u8) (value >> 8), 0x0F);
  } else {
    set_fat_byte(output, sector, offset, (u8) (value << 4), 0xF0);
    set_fat_byte(output, sector, offset + 1, (u8) (value >> 4), 0xFF);
  }
}

static void fat_sector(u32 sector, u8* output) {
  memset(output, 0, SECTOR_SIZE);
  const u32 byte_start = sector * SECTOR_SIZE;
  u32 first = byte_start * 2 / 3;
  if(first > 2) first -= 2;
  u32 last = (byte_start + SECTOR_SIZE + 2) * 2 / 3 + 2;
  if(last > cluster_limit()) last = cluster_limit();
  for(u32 cluster = first; cluster < last; cluster++) {
    set_fat_entry(output, sector, (u16) cluster,
                  base_fat_value((u16) cluster));
  }
}

static bool render_children(u16 parent_id, u32 first_slot, u8* output,
                            bool root) {
  memset(output, 0, SECTOR_SIZE);
  const u32 last_slot = first_slot + SECTOR_SIZE / 32;
  u32 cursor = root ? storage_geometry::ROOT_SYSTEM_DIRENTS : 2U;
  int first_child = 0;
  if(root) {
    if(first_slot == 0) {
      memcpy(output, "MK61S C6   ", 11);
      output[11] = ATTR_VOLUME;
      for(u8 offset = 0;
          offset + 1 < storage_geometry::ROOT_SYSTEM_DIRENTS;
          offset++) {
        if(!render_no_index_dirent(offset, output + (u16) (offset + 1) * 32)) {
          return false;
        }
      }
    }
  } else {
    if(first_slot == 0) {
      memcpy(output, ".          ", 11);
      output[11] = ATTR_DIRECTORY;
      put_le16(output, 26, cluster_for_id(parent_id));
      memcpy(output + 32, "..         ", 11);
      output[32 + 11] = ATTR_DIRECTORY;
      program_store::Entry directory;
      if(!program_store::entry_by_id(parent_id, directory)) return false;
      put_le16(output + 32, 26, directory.parent_id == program_store::ROOT_ID
                                   ? 0 : cluster_for_id(directory.parent_id));
    }
  }

  (void) resume_directory_cursor(parent_id, root, first_slot,
                                 cursor, first_child);

  const int children = program_store::child_count(parent_id);
  for(int index = first_child; index < children; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent_id, index, entry)) return false;
    const u8 count = node_dirent_count(entry);
    if(count == 0) return false;
    const u32 node_slot = cursor;
    for(u8 offset = 0; offset < count; offset++) {
      const u32 slot = cursor + offset;
      if(slot >= first_slot && slot < last_slot &&
         !render_node_dirent(entry, offset,
                             output + (slot - first_slot) * 32)) return false;
    }
    cursor += count;
    if(cursor >= last_slot && cursor > first_slot) {
      // If an LFN spans the sector boundary, the next sector must revisit the
      // same child to render the tail. Otherwise resume at the following one.
      save_directory_cursor(parent_id, root, last_slot,
                            cursor > last_slot ? node_slot : cursor,
                            cursor > last_slot ? index : index + 1);
      return true;
    }
  }
  save_directory_cursor(parent_id, root, last_slot, cursor, children);
  return true;
}

static bool directory_segment(u16 id, u16& directory_id, u16& segment) {
  program_store::Entry entry;
  if(program_store::entry_by_id(id, entry) &&
     entry.kind == program_store::NodeKind::DIRECTORY) {
    directory_id = id;
    segment = 0;
    return true;
  }
  u16 next = 0;
  if(!program_store::extent_info(id, directory_id, next)) return false;
  (void) next;
  u16 extent = 0;
  if(!program_store::first_extent(directory_id, extent)) return false;
  segment = 1;
  for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
    if(extent == id) return true;
    if(!program_store::next_extent(extent, extent)) break;
    segment++;
  }
  return false;
}

static bool data_sector_base(u32 offset, u8* output) {
  memset(output, 0, SECTOR_SIZE);
  const u8 sectors_per_cluster = geometry().sectors_per_cluster;
  const u16 cluster = (u16) (FIRST_DATA_CLUSTER + offset / sectors_per_cluster);
  const u8 sector = (u8) (offset % sectors_per_cluster);
  if(!valid_cluster(cluster)) return false;
  const u16 id = id_for_cluster(cluster);
  program_store::Entry entry;
  if(program_store::entry_by_id(id, entry)) {
    if(entry.kind == program_store::NodeKind::FILE) {
      const u32 file_offset = (u32) sector * SECTOR_SIZE;
      u32 visible_size = 0;
      if(!exported_file_size(entry, visible_size)) return false;
      if(file_offset >= visible_size) return true;
      u16 copied = 0;
      return read_exported_range(entry, file_offset, output, SECTOR_SIZE,
                                 copied);
    }
  }
  u16 file_id = 0;
  u16 file_next = 0;
  u8 file_cluster = 0;
  if(program_store::file_extent_info(id, file_id, file_cluster, file_next) &&
     program_store::entry_by_id(file_id, entry) &&
     entry.kind == program_store::NodeKind::FILE) {
    (void) file_next;
    const u32 file_offset =
        ((u32) file_cluster * sectors_per_cluster + sector) * SECTOR_SIZE;
    u32 visible_size = 0;
    if(!exported_file_size(entry, visible_size)) return false;
    if(file_offset >= visible_size) return true;
    u16 copied = 0;
    return read_exported_range(entry, file_offset, output, SECTOR_SIZE, copied);
  }
  u16 directory_id = 0;
  u16 segment = 0;
  if(!directory_segment(id, directory_id, segment)) return true;
  const u32 slots_per_cluster = (u32) sectors_per_cluster * (SECTOR_SIZE / 32);
  const u32 first_slot = (u32) segment * slots_per_cluster +
                         (u32) sector * (SECTOR_SIZE / 32);
  return render_children(directory_id, first_slot, output, false);
}

static bool read_base_sector(u32 lba, u8* output) {
  if(lba >= geometry().logical_sectors) return false;
  if(lba == 0) {
    boot_sector(output);
    return true;
  }
  if(lba < root_start()) {
    fat_sector((lba - fat_start()) % geometry().fat_sectors, output);
    return true;
  }
  if(lba < data_start()) {
    return render_children(program_store::ROOT_ID,
                           (lba - root_start()) * (SECTOR_SIZE / 32),
                           output, true);
  }
  return data_sector_base(lba - data_start(), output);
}

static u32 canonical_lba(u32 lba) {
  const u32 second_fat = fat_start() + geometry().fat_sectors;
  if(lba >= second_fat && lba < second_fat + geometry().fat_sectors) {
    return lba - geometry().fat_sectors;
  }
  return lba;
}

static u8* cache_bytes(u8 slot) {
  if(slot < PRIMARY_CACHE_SLOTS) return session().cache_data[slot];
  slot = (u8) (slot - PRIMARY_CACHE_SLOTS);
  if(slot < g_scratch_cache_slots) {
    return g_cache_scratch.data() + (u32) slot * SECTOR_SIZE;
  }
  slot = (u8) (slot - g_scratch_cache_slots);
  return g_extra_cache + (u32) slot * SECTOR_SIZE;
}

static int cache_index(u32 lba) {
  const u32 key = canonical_lba(lba);
  SessionState& state = session();
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    if(state.cache[slot].state != CACHE_EMPTY && state.cache[slot].lba == key) {
      return slot;
    }
  }
  return -1;
}

static void touch_cache(u8 slot) {
  SessionState& state = session();
  state.cache_clock++;
  if(state.cache_clock == 0) {
    // Потеря точного порядка LRU раз в четыре миллиарда обращений безвредна,
    // но переполнение возраста не должно навсегда делать активную запись самой старой.
    state.cache_clock = 1;
    for(u8 i = 0; i < g_cache_slots; i++) {
      if(state.cache[i].state != CACHE_EMPTY) state.cache[i].age = 1;
    }
  }
  state.cache[slot].age = state.cache_clock;
}

static bool read_persistent_sector(u32 lba, u8* output) {
  service_startup_recovery();
  const u32 key = canonical_lba(lba);
  if(key != 0 && program_store::vfat_stage_exists(key)) {
    return program_store::vfat_stage_read(key, output);
  }
  return read_base_sector(lba, output);
}

static bool persist_cache_slot(u8 slot) {
  SessionState& state = session();
  CacheEntry& entry = state.cache[slot];
  if(entry.state != CACHE_UNCHECKED) return true;
  u8 persistent[SECTOR_SIZE];
  if(!read_persistent_sector(entry.lba, persistent)) return false;
  if(memcmp(persistent, cache_bytes(slot), SECTOR_SIZE) == 0) {
    entry.state = CACHE_CLEAN;
    touch_cache(slot);
    return true;
  }
  if(!program_store::vfat_stage_write(entry.lba, cache_bytes(slot))) return false;
  entry.state = CACHE_CLEAN;
  touch_cache(slot);
  return true;
}

static int oldest_cache(CacheState wanted) {
  SessionState& state = session();
  int oldest = -1;
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    if(state.cache[slot].state != wanted) continue;
    if(oldest < 0 || state.cache[slot].age < state.cache[(u8) oldest].age) {
      oldest = slot;
    }
  }
  return oldest;
}

static int oldest_dirty_cache(void) {
  SessionState& state = session();
  int oldest = -1;
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    const CacheState cache_state = state.cache[slot].state;
    if(cache_state != CACHE_UNCHECKED) continue;
    if(oldest < 0 || state.cache[slot].age < state.cache[(u8) oldest].age) {
      oldest = slot;
    }
  }
  return oldest;
}

static bool prepare_cache_slot(u8& output) {
  SessionState& state = session();
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    if(state.cache[slot].state == CACHE_EMPTY) {
      output = slot;
      return true;
    }
  }

  // Предпочитаем удалить запись только для чтения. Лишь когда все слоты грязные,
  // добавляем в журнал NOR использовавшийся раньше всех.
  int victim = oldest_cache(CACHE_CLEAN);
  if(victim < 0) victim = oldest_dirty_cache();
  if(victim < 0 || !persist_cache_slot((u8) victim)) return false;
  state.cache[(u8) victim].state = CACHE_EMPTY;
  output = (u8) victim;
  return true;
}

static bool load_cached_sector(u32 lba, u8& slot) {
  const int found = cache_index(lba);
  if(found >= 0) {
    slot = (u8) found;
    touch_cache(slot);
    return true;
  }
  if(!prepare_cache_slot(slot)) return false;
  SessionState& state = session();
  CacheEntry& entry = state.cache[slot];
  if(!read_persistent_sector(lba, cache_bytes(slot))) {
    entry.state = CACHE_EMPTY;
    return false;
  }
  entry.lba = canonical_lba(lba);
  entry.state = CACHE_CLEAN;
  touch_cache(slot);
  return true;
}

static bool read_effective_sector(u32 lba, u8* output) {
  const int found = cache_index(lba);
  if(found >= 0) {
    const u8 slot = (u8) found;
    memcpy(output, cache_bytes(slot), SECTOR_SIZE);
    touch_cache(slot);
    return true;
  }
  return read_persistent_sector(lba, output);
}

static bool cached_effective_sector(u32 lba, const u8*& output) {
  u8 slot = 0;
  if(!load_cached_sector(lba, slot)) return false;
  output = cache_bytes(slot);
  return true;
}

static bool effective_fat_sector(u32 index, const u8*& output) {
  if(index >= geometry().fat_sectors) return false;
  const u32 lba = fat_start() + index;
  return cached_effective_sector(lba, output);
}

static bool effective_fat_value(u16 cluster, u16& value) {
  const u32 offset = (u32) cluster + cluster / 2;
  const u32 sector = offset / SECTOR_SIZE;
  const u16 in_sector = (u16) (offset % SECTOR_SIZE);
  const u8* first = NULL;
  if(!effective_fat_sector(sector, first)) return false;
  const u8 lo = first[in_sector];
  u8 hi = 0;
  if(in_sector + 1 < SECTOR_SIZE) {
    hi = first[in_sector + 1];
  } else {
    const u8* second = NULL;
    if(!effective_fat_sector(sector + 1, second)) return false;
    hi = second[0];
  }
  const u16 packed = (u16) (lo | ((u16) hi << 8));
  value = (cluster & 1) == 0 ? (u16) (packed & 0x0FFF)
                              : (u16) (packed >> 4);
  return true;
}

static bool fat_eof(u16 value) { return value >= 0xFF8 && value <= 0xFFF; }

static DesiredKind desired_kind(u16 id) {
  if(id >= storage_geometry::FAT12_MAX_DATA_CLUSTERS) return DESIRED_NONE;
  const u16 bit = (u16) id * 2;
  return (DesiredKind) ((session().desired_kinds[bit / 8] >> (bit & 7)) & 3);
}

static bool set_desired_kind(u16 id, DesiredKind kind) {
  if(id >= geometry().max_nodes || desired_kind(id) != DESIRED_NONE) return false;
  const u16 bit = (u16) id * 2;
  session().desired_kinds[bit / 8] = (u8) (
      session().desired_kinds[bit / 8] | ((u8) kind << (bit & 7)));
  return true;
}

static bool collect_file_chain(const ParsedNode& parsed, bool reserve_extents,
                               FileChain& chain) {
  memset(&chain, 0, sizeof(chain));
  chain.size = parsed.data_len;
  const u32 cluster_bytes =
      (u32) geometry().sectors_per_cluster * SECTOR_SIZE;
  const u32 required = parsed.data_len == 0 ? 1 :
      ((u32) parsed.data_len + cluster_bytes - 1U) / cluster_bytes;
  if(required == 0 || required > MAX_C6_FILE_CLUSTERS) {
    return g_error.fail(ErrorCode::CLUSTER_LIMIT, Phase::CHAIN,
                        required, MAX_C6_FILE_CLUSTERS, parsed.name);
  }
  chain.cluster_count = (u8) required;
  u16 cluster = cluster_for_id(parsed.id);
  for(u8 index = 0; index < chain.cluster_count; index++) {
    if(!valid_cluster(cluster)) {
      return g_error.fail(ErrorCode::FILE_CLUSTER, Phase::CHAIN,
                          cluster, cluster_limit(), parsed.name);
    }
    for(u8 previous = 0; previous < index; previous++) {
      if(chain.clusters[previous] == cluster) {
        return g_error.fail(ErrorCode::FILE_CHAIN, Phase::CHAIN,
                            cluster, index, parsed.name);
      }
    }
    chain.clusters[index] = cluster;
    if(index != 0 && reserve_extents &&
       !set_desired_kind(id_for_cluster(cluster), DESIRED_EXTENT)) {
      return g_error.fail(ErrorCode::DUPLICATE_CLUSTER, Phase::CHAIN,
                          cluster, index, parsed.name);
    }
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) {
      return g_error.fail(ErrorCode::FAT_READ, Phase::CHAIN,
                          cluster, 0, parsed.name, true);
    }
    if(index + 1U == chain.cluster_count) {
      if(!fat_eof(next)) {
        return g_error.fail(ErrorCode::FILE_CHAIN, Phase::CHAIN,
                            cluster, next, parsed.name);
      }
    } else {
      if(!valid_cluster(next)) {
        return g_error.fail(ErrorCode::FILE_CHAIN, Phase::CHAIN,
                            cluster, next, parsed.name);
      }
      cluster = next;
    }
  }
  return true;
}

static bool file_chain_matches(const FileChain& chain, u16 file_id) {
  u16 current = file_id;
  for(u8 index = 0; index < chain.cluster_count; index++) {
    if(current != id_for_cluster(chain.clusters[index])) return false;
    if(index + 1U == chain.cluster_count) {
      u16 extra = 0;
      return !program_store::next_file_extent(current, extra);
    }
    if(!program_store::next_file_extent(current, current)) return false;
  }
  return false;
}

static void reset_lfn(LfnState& lfn) {
  memset(&lfn, 0, sizeof(lfn));
  for(u16 i = 0; i < MAX_LFN_UNITS; i++) lfn.name[i] = 0xFFFF;
}

static void parse_lfn(const u8* item, LfnState& lfn) {
  static const u8 offsets[13] = {
    1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30
  };
  const u8 sequence = (u8) (item[0] & 0x1F);
  const bool last = (item[0] & 0x40) != 0;
  if(sequence == 0 || sequence > MAX_LFN_ENTRIES || item[12] != 0 ||
     get_le16(item, 26) != 0) {
    reset_lfn(lfn);
    return;
  }
  if(last) {
    reset_lfn(lfn);
    lfn.active = true;
    lfn.valid = true;
    lfn.expected = sequence;
    lfn.next_sequence = sequence;
    lfn.checksum = item[13];
  }
  if(!lfn.active || sequence != lfn.next_sequence ||
     item[13] != lfn.checksum) {
    lfn.valid = false;
  }
  for(u8 i = 0; i < 13; i++) {
    const u16 index = (u16) (sequence - 1) * 13 + i;
    if(index < MAX_LFN_UNITS) lfn.name[index] = get_le16(item, offsets[i]);
  }
  lfn.seen_mask = (u8) (lfn.seen_mask | (1U << (sequence - 1)));
  if(lfn.next_sequence != 0) lfn.next_sequence--;
}

static bool accepted_lfn(const LfnState& lfn, const u8* short_item,
                         char* output, u16 capacity) {
  if(!lfn.active || !lfn.valid || lfn.expected == 0 ||
     lfn.next_sequence != 0 || short_checksum(short_item) != lfn.checksum) return false;
  const u8 mask = (u8) ((1U << lfn.expected) - 1U);
  return (lfn.seen_mask & mask) == mask &&
         utf16_to_m8(lfn.name, (u16) lfn.expected * 13, output, capacity);
}

static bool short_name(const u8* item, char* output, u16 capacity) {
  u16 len = 0;
  for(u8 i = 0; i < 8 && item[i] != ' '; i++) {
    if(len + 1 >= capacity) return false;
    output[len++] = (char) item[i];
  }
  bool has_ext = false;
  for(u8 i = 8; i < 11; i++) if(item[i] != ' ') has_ext = true;
  if(has_ext) {
    if(len + 1 >= capacity) return false;
    output[len++] = '.';
    for(u8 i = 8; i < 11 && item[i] != ' '; i++) {
      if(len + 1 >= capacity) return false;
      output[len++] = (char) item[i];
    }
  }
  output[len] = 0;
  return len != 0;
}

enum class ParseStatus : u8 { SKIP, VALID, INVALID };

static bool system_directory(const char* name, u8 attributes) {
  if((attributes & (ATTR_HIDDEN | ATTR_SYSTEM)) == 0) return false;
  return strcmp(name, ".Spotlight-V100") == 0 ||
         strcmp(name, ".Trashes") == 0 ||
         strcmp(name, ".fseventsd") == 0 ||
         strcmp(name, "System Volume Information") == 0;
}

static bool host_sidecar_file(const char* name) {
  // Finder хранит расширенные атрибуты и ветви ресурсов в файлах AppleDouble.
  // Их суффикс намеренно повторяет настоящий файл (например, "._game.m61"),
  // поэтому импорт C6 по расширению должен отклонить их до того, как примет
  // многокилобайтный блок метаданных за исходник калькулятора.
  return name[0] == '.' && name[1] == '_';
}

static ParseStatus parse_short_item(const u8* item, const LfnState& lfn,
                                    ParsedNode& parsed) {
  if((item[11] & ATTR_VOLUME) != 0 || item[0] == 0xE5) return ParseStatus::SKIP;
  if(item[0] == '.') return ParseStatus::SKIP;
  char name[program_store::NAME_SIZE + 16];
  if(!accepted_lfn(lfn, item, name, sizeof(name)) &&
     !short_name(item, name, sizeof(name))) {
    g_error.fail(ErrorCode::NAME, Phase::ENTRY, get_le32(item, 0), item[11]);
    return ParseStatus::INVALID;
  }
  parsed.directory = (item[11] & ATTR_DIRECTORY) != 0;
  parsed.attributes = item[11];
  const u16 cluster = get_le16(item, 26);
  if(parsed.directory) {
    if(system_directory(name, parsed.attributes)) return ParseStatus::SKIP;
    if(!valid_cluster(cluster)) {
      g_error.fail(ErrorCode::DIRECTORY_CLUSTER, Phase::ENTRY,
                    cluster, cluster_limit(), name);
      return ParseStatus::INVALID;
    }
    if(strlen(name) >= program_store::NAME_SIZE) {
      g_error.fail(ErrorCode::NAME_TOO_LONG, Phase::ENTRY,
                    (u32) strlen(name), program_store::NAME_SIZE - 1, name);
      return ParseStatus::INVALID;
    }
    if(!storage_name::valid_basename(name, program_store::NAME_SIZE)) {
      g_error.fail(ErrorCode::NAME, Phase::ENTRY, 0, 0, name);
      return ParseStatus::INVALID;
    }
    bounded_string::copy(parsed.name, name);
    parsed.id = id_for_cluster(cluster);
    parsed.data_len = 0;
    parsed.type = program_store::ProgramType::MK61;
    return ParseStatus::VALID;
  }
  const u32 size = get_le32(item, 28);
  if(size == 0 && cluster == 0) return ParseStatus::SKIP;
  if(host_sidecar_file(name) || !parse_file_name(name, parsed.type)) {
    return ParseStatus::SKIP;
  }
  if(!storage_name::valid_basename(name, program_store::NAME_SIZE)) {
    g_error.fail(ErrorCode::NAME, Phase::ENTRY, 0, 0, name);
    return ParseStatus::INVALID;
  }
  // Неподдерживаемые файлы хоста намеренно игнорируются независимо от размера.
  // Квоту данных C6 применяем лишь после выбора известного расширения калькулятора.
  const u32 size_limit = maximum_file_size(parsed.type);
  if(parsed.type == program_store::ProgramType::CHIP8 && size == 0) {
    g_error.fail(ErrorCode::EMPTY_FILE, Phase::ENTRY, 0, 1, name);
    return ParseStatus::INVALID;
  }
  if(size > size_limit) {
    g_error.fail(ErrorCode::FILE_TOO_LARGE, Phase::ENTRY, size, size_limit, name);
    return ParseStatus::INVALID;
  }
  if(!valid_cluster(cluster)) {
    g_error.fail(ErrorCode::FILE_CLUSTER, Phase::ENTRY,
                  cluster, cluster_limit(), name);
    return ParseStatus::INVALID;
  }
  bounded_string::copy(parsed.name, name);
  parsed.id = id_for_cluster(cluster);
  parsed.data_len = (u16) size;
  return ParseStatus::VALID;
}

static bool scan_cluster_chain(u8* map, u16 first) {
  if(!valid_cluster(first)) return true;
  u16 cluster = first;
  for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
    if(!valid_cluster(cluster) || cluster_marked(map, cluster)) return true;
    mark_cluster(map, cluster);
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) return false;
    if(fat_eof(next) || next == FAT12_FREE || next == FAT12_BAD) return true;
    cluster = next;
  }
  return true; // A transient host FAT loop is not a reason to reject WRITE.
}

static bool scan_host_directory(u16 first_cluster, u8 depth,
                                SidecarScanMaps& maps);

static bool scan_host_directory_sector(u32 lba, u8 depth, LfnState& lfn,
                                       bool& end, SidecarScanMaps& maps) {
  for(u8 slot = 0; slot < SECTOR_SIZE / 32; slot++) {
    const u8* block = nullptr;
    if(!cached_effective_sector(lba, block)) return false;
    u8 item[32];
    memcpy(item, block + slot * 32, sizeof(item));
    if(item[0] == 0) {
      end = true;
      return true;
    }
    if(item[11] == ATTR_LFN) {
      if(item[0] == 0xE5) reset_lfn(lfn);
      else parse_lfn(item, lfn);
      continue;
    }
    if(item[0] == 0xE5 || (item[11] & ATTR_VOLUME) != 0) {
      reset_lfn(lfn);
      continue;
    }
    char name[program_store::NAME_SIZE + 16];
    const bool named = accepted_lfn(lfn, item, name, sizeof(name)) ||
                       short_name(item, name, sizeof(name));
    reset_lfn(lfn);
    if(!named) continue;
    if((item[11] & ATTR_DIRECTORY) != 0 &&
       (strcmp(name, ".") == 0 || strcmp(name, "..") == 0)) continue;
    const u16 cluster = get_le16(item, 26);
    if((item[11] & ATTR_DIRECTORY) != 0) {
      if(depth < MAX_DEPTH &&
         !system_directory(name, item[11]) &&
         !scan_host_directory(cluster, (u8) (depth + 1), maps)) return false;
    } else if(host_sidecar_file(name)) {
      if(!scan_cluster_chain(maps.sidecars, cluster)) return false;
    } else if(!scan_cluster_chain(maps.regular, cluster)) {
      return false;
    }
  }
  return true;
}

static bool scan_host_directory(u16 first_cluster, u8 depth,
                                SidecarScanMaps& maps) {
  LfnState lfn;
  reset_lfn(lfn);
  bool end = false;
  if(first_cluster == 0) {
    for(u16 sector = 0; sector < geometry().root_sectors && !end; sector++) {
      if(!scan_host_directory_sector(root_start() + sector, depth,
                                     lfn, end, maps)) return false;
    }
    return true;
  }
  u16 cluster = first_cluster;
  for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
    if(!valid_cluster(cluster) ||
       cluster_marked(maps.directories, cluster)) return true;
    mark_cluster(maps.directories, cluster);
    for(u8 sector = 0; sector < geometry().sectors_per_cluster && !end;
        sector++) {
      if(!scan_host_directory_sector(cluster_lba(cluster, sector), depth,
                                     lfn, end, maps)) return false;
    }
    if(end) return true;
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) return false;
    if(fat_eof(next) || next == FAT12_FREE || next == FAT12_BAD) return true;
    cluster = next;
  }
  return true;
}

static bool discard_known_sidecars(void) {
  if(!g_sidecar_scan_pending || !sidecar_filter_enabled()) return true;
  // These maps are needed only during this bounded scan. Keeping them on the
  // stack avoids adding 1.5 KiB of permanent BSS to the 20-KiB USBDISK.APP.
  SidecarScanMaps maps = {};
  if(!scan_host_directory(0, 0, maps)) return false;
  for(u16 byte = 0; byte < CLUSTER_MAP_BYTES; byte++) {
    // A transient host directory may mention a cluster twice. Never discard
    // data if any ordinary file or directory still refers to that cluster.
    maps.sidecars[byte] &=
        (u8) ~(maps.regular[byte] | maps.directories[byte]);
  }
  for(u16 id = 0; id < geometry().max_nodes; id++) {
    const u16 cluster = cluster_for_id(id);
    if(!cluster_marked(maps.sidecars, cluster)) continue;
    for(u8 sector = 0; sector < geometry().sectors_per_cluster; sector++) {
      const u32 lba = cluster_lba(cluster, sector);
      program_store::vfat_stage_forget(lba, 1);
      if(program_store::vfat_stage_exists(lba)) return false;
      const int cached = cache_index(lba);
      if(cached >= 0) session().cache[(u8) cached].state = CACHE_EMPTY;
    }
  }
  // The two-bit desired-kind workspace is idle between commits. Reuse it as
  // the persistent sidecar/directory role map; commit validation clears and
  // owns it under ScopedDesiredKinds below.
  memset(session().desired_kinds, 0, sizeof(session().desired_kinds));
  for(u16 id = 0; id < geometry().max_nodes; id++) {
    const u16 cluster = cluster_for_id(id);
    if(cluster_marked(maps.sidecars, cluster)) {
      set_cluster_role(cluster, CLUSTER_ROLE_SIDECAR);
    } else if(cluster_marked(maps.directories, cluster)) {
      set_cluster_role(cluster, CLUSTER_ROLE_DIRECTORY);
    }
  }
  g_sidecar_scan_pending = false;
  return true;
}

enum class WalkPass : u8 { VALIDATE, APPLY };

static bool walk_directory(u16 parent_id, bool root, u16 first_cluster,
                           u8 depth, WalkPass pass);

static bool read_file_chain_source(void* context, u32 offset,
                                   u8* output, usize size) {
  const FileChain& chain = *(FileChain*) context;
  if(output == NULL || offset > chain.size || size > chain.size - offset) {
    return false;
  }
  const u32 cluster_bytes =
      (u32) geometry().sectors_per_cluster * SECTOR_SIZE;
  while(size != 0) {
    const u8 cluster_index = (u8) (offset / cluster_bytes);
    const u32 in_cluster = offset % cluster_bytes;
    if(cluster_index >= chain.cluster_count) return false;
    const u8 sector = (u8) (in_cluster / SECTOR_SIZE);
    const u16 in_sector = (u16) (in_cluster % SECTOR_SIZE);
    u8 block[SECTOR_SIZE];
    if(!read_effective_sector(
           cluster_lba(chain.clusters[cluster_index], sector), block)) {
      return g_error.fail(ErrorCode::FILE_READ, Phase::VALIDATE,
                          cluster_lba(chain.clusters[cluster_index], sector),
                          chain.size, nullptr, true);
    }
    usize count = SECTOR_SIZE - in_sector;
    if(count > size) count = size;
    memcpy(output, block + in_sector, count);
    output += count;
    offset += (u32) count;
    size -= count;
  }
  return true;
}

static bool decode_chain_m8(const FileChain& chain, u32& utf8_offset,
                            u8& output) {
  if(utf8_offset >= chain.size) return false;
  u8 encoded[4] = {};
  const usize available = chain.size - utf8_offset < sizeof(encoded)
      ? (usize) (chain.size - utf8_offset) : sizeof(encoded);
  if(!read_file_chain_source((void*) &chain, utf8_offset,
                             encoded, available)) return false;
  const utf8_codec::Decoded decoded = utf8_codec::decode(encoded, available);
  if(!decoded.valid || decoded.size == 0 ||
     !mk8::from_codepoint(decoded.codepoint, output) ||
     !mk8::valid_byte(output)) return false;
  utf8_offset += decoded.size;
  return true;
}

static bool validate_text_chain(const FileChain& chain, u16 limit,
                                u16& m8_size) {
  m8_size = 0;
  u32 offset = 0;
  while(offset < chain.size) {
    u8 byte = 0;
    if(!decode_chain_m8(chain, offset, byte) || m8_size == limit) return false;
    ++m8_size;
  }
  return true;
}

struct ImportedTextSource {
  const FileChain* chain;
  u32 utf8_offset;
  u16 m8_offset;
  u16 size;
};

static bool seek_imported_text(ImportedTextSource& source, u16 wanted) {
  if(wanted > source.size) return false;
  if(wanted < source.m8_offset) {
    source.utf8_offset = 0;
    source.m8_offset = 0;
  }
  while(source.m8_offset < wanted) {
    u8 byte = 0;
    if(!decode_chain_m8(*source.chain, source.utf8_offset, byte)) return false;
    ++source.m8_offset;
  }
  return true;
}

static bool read_imported_text(void* context, u32 offset,
                               u8* output, usize size) {
  ImportedTextSource& source = *(ImportedTextSource*) context;
  if(output == NULL || offset > source.size || size > source.size - offset ||
     offset > 0xFFFFU || !seek_imported_text(source, (u16) offset)) return false;
  while(size-- != 0) {
    if(!decode_chain_m8(*source.chain, source.utf8_offset, *output++)) {
      return false;
    }
    ++source.m8_offset;
  }
  return true;
}

static bool base_file_cluster(u16 cluster, u16& file_id,
                              u8& cluster_index) {
  const u16 id = id_for_cluster(cluster);
  program_store::Entry entry;
  if(program_store::entry_by_id(id, entry) &&
     entry.kind == program_store::NodeKind::FILE) {
    file_id = id;
    cluster_index = 0;
    return true;
  }
  u16 next = 0;
  return program_store::file_extent_info(id, file_id, cluster_index, next);
}

static bool file_chain_complete(const FileChain& chain,
                                bool current_exists, u16 current_id,
                                u32 current_size, const char* subject,
                                bool& any_staged) {
  any_staged = false;
  const u32 cluster_bytes =
      (u32) geometry().sectors_per_cluster * SECTOR_SIZE;
  u32 remaining = chain.size;
  for(u8 index = 0; index < chain.cluster_count && remaining != 0; index++) {
    const u32 in_cluster = remaining < cluster_bytes
        ? remaining : cluster_bytes;
    const u8 sectors =
        (u8) ((in_cluster + SECTOR_SIZE - 1U) / SECTOR_SIZE);
    for(u8 sector = 0; sector < sectors; sector++) {
      const u32 lba = cluster_lba(chain.clusters[index], sector);
      if(program_store::vfat_stage_exists(lba)) {
        any_staged = true;
        continue;
      }
      u16 owner = 0;
      u8 old_cluster = 0;
      if(!current_exists ||
         !base_file_cluster(chain.clusters[index], owner, old_cluster) ||
         owner != current_id ||
         ((u32) old_cluster * geometry().sectors_per_cluster + sector) *
             SECTOR_SIZE >= current_size) {
        return g_error.fail(ErrorCode::FILE_DATA, Phase::VALIDATE,
                            lba, current_size, subject);
      }
    }
    remaining -= in_cluster;
  }
  return true;
}

#if MK61_ANY_LOADABLE_MODULE
static constexpr u16 MAX_APP_STAGE_BLOCKS =
    (program_store::MAX_APP_FILE_SIZE + SECTOR_SIZE - 1U) / SECTOR_SIZE;

static bool app_chain_contains_stage_key(void* context, u32 key) {
  if(context == NULL) return false;
  const FileChain& chain = *(FileChain*) context;
  const u32 cluster_bytes =
      (u32) geometry().sectors_per_cluster * SECTOR_SIZE;
  u32 remaining = chain.size;
  for(u8 index = 0; index < chain.cluster_count && remaining != 0; index++) {
    const u32 in_cluster =
        remaining < cluster_bytes ? remaining : cluster_bytes;
    const u16 sectors =
        (u16) ((in_cluster + SECTOR_SIZE - 1U) / SECTOR_SIZE);
    const u32 first = cluster_lba(chain.clusters[index], 0);
    if(key >= first && key - first < sectors) return true;
    remaining -= in_cluster;
  }
  return false;
}

static bool validate_app_chain(const ParsedNode& parsed,
                               FileChain& chain) {
  if(parsed.type != program_store::ProgramType::APP) return true;
  alignas(4) u32 app_stage_index[MAX_APP_STAGE_BLOCKS] = {};
  if(!program_store::vfat_stage_narrow_matching(
       app_chain_contains_stage_key, &chain,
       app_stage_index, MAX_APP_STAGE_BLOCKS)) {
    return g_error.fail(ErrorCode::APP_STAGE, Phase::VALIDATE,
                        parsed.data_len, MAX_APP_STAGE_BLOCKS, parsed.name, true);
  }
  const loadable_module::ModuleSource source = {
    &chain, parsed.data_len, read_file_chain_source
  };
  loadable_module::Header header = {};
  const loadable_module::StoreStatus status =
      loadable_module::validate_app(source, header);
  if(!program_store::vfat_stage_restore_full()) {
    return g_error.fail(ErrorCode::APP_STAGE_RESTORE, Phase::VALIDATE,
                        (u32) status, 0, parsed.name, true);
  }
  if(status == loadable_module::StoreStatus::OK) return true;
  return g_error.fail(ErrorCode::APP_INVALID, Phase::VALIDATE,
                      (u32) status, parsed.data_len, parsed.name,
                      status == loadable_module::StoreStatus::UNAVAILABLE ||
                      status == loadable_module::StoreStatus::IO_ERROR);
}
#endif

struct MaterializedFile {
  const u8* data;
  u16 size;
};

static bool read_materialized_file(void* context, u32 offset,
                                   u8* output, usize size) {
  const MaterializedFile& source = *(MaterializedFile*) context;
  if(output == NULL || offset > source.size ||
     size > source.size - offset) return false;
  memcpy(output, source.data + offset, size);
  return true;
}

static bool apply_file(u16 parent_id, const ParsedNode& parsed) {
  FileChain chain = {};
  if(!collect_file_chain(parsed, false, chain)) return false;
  program_store::Entry current;
  const bool exists = program_store::entry_by_id(parsed.id, current) &&
                      current.kind == program_store::NodeKind::FILE;
  u32 current_visible_size = 0;
  if(exists && !exported_file_size(current, current_visible_size)) return false;
  bool any_staged = false;
  if(!file_chain_complete(chain, exists, parsed.id,
                          exists ? current_visible_size : 0,
                          parsed.name, any_staged)) {
    return false;
  }
  const bool content_unchanged =
      exists && current.type == parsed.type &&
      current_visible_size == parsed.data_len && !any_staged &&
      file_chain_matches(chain, parsed.id);
  if(content_unchanged) {
    if(current.parent_id == parent_id && strcmp(current.name, parsed.name) == 0) {
      return true;
    }
    if(program_store::move_rename(parsed.id, parent_id, parsed.name)) {
      return true;
    }
    return g_error.fail(ErrorCode::APPLY, Phase::APPLY,
                        parsed.id, 1U, parsed.name, true);
  }

  u16 internal_size = parsed.data_len;
  ImportedTextSource text_source = {&chain, 0, 0, 0};
  program_store::FileSource source = {&chain, read_file_chain_source};
  if(program_store::text_content(parsed.type)) {
    const u16 limit = parsed.type == program_store::ProgramType::TINYBASIC
        ? program_store::MAX_TINYBASIC_TEXT_SIZE
        : program_store::MAX_MK61_TEXT_SIZE;
    if(!validate_text_chain(chain, limit, internal_size)) {
      return g_error.fail(ErrorCode::TEXT_ENCODING, Phase::APPLY,
                          parsed.data_len, limit, parsed.name);
    }
    text_source.size = internal_size;
    source = {&text_source, read_imported_text};
  }
  u16 extents[program_store::MAX_FAT_EXTENTS_PER_FILE] = {};
  for(u8 index = 1; index < chain.cluster_count; index++) {
    extents[index - 1] = id_for_cluster(chain.clusters[index]);
  }
  if(internal_size != 0 &&
     program_store::transparent_compression_enabled(parsed.type)) {
    const u8 source_slots = (u8) (
        ((u32) internal_size + SECTOR_SIZE - 1U) / SECTOR_SIZE);
    if(source_slots < PRIMARY_CACHE_SLOTS) {
      const u8 saved_cache_slots = g_cache_slots;
      const u8 workspace_slots =
          (u8) (PRIMARY_CACHE_SLOTS - source_slots);
      memset(session().cache, 0, sizeof(session().cache));
      g_cache_slots = workspace_slots;
      u8* const bytes = session().cache_data[workspace_slots];
      const bool loaded =
          source.read(source.context, 0, bytes, internal_size);
      memset(session().cache, 0, sizeof(session().cache));
      g_cache_slots = 0;
      if(!loaded) {
        g_cache_slots = saved_cache_slots;
        return g_error.fail(ErrorCode::APPLY, Phase::APPLY,
                            parsed.id, 2U, parsed.name, true);
      }
      MaterializedFile materialized = {bytes, internal_size};
      const program_store::FileSource memory_source = {
        &materialized, read_materialized_file
      };
      u8* const compression_buffer =
          g_commit_compression_buffer != NULL
              ? g_commit_compression_buffer
              : session().cache_data[0];
      const usize compression_buffer_size =
          g_commit_compression_buffer != NULL
              ? g_commit_compression_buffer_size
              : (usize) workspace_slots * SECTOR_SIZE;
      const bool written = program_store::write_file_from_source(
          parent_id, parsed.id, parsed.type, parsed.name, internal_size,
          memory_source, chain.cluster_count > 1 ? extents : NULL,
          (u8) (chain.cluster_count - 1U), NULL,
          compression_buffer, compression_buffer_size, bytes);
      memset(session().cache, 0, sizeof(session().cache));
      g_cache_slots = saved_cache_slots;
      if(written) return true;
      u32 detail = 3U;
      u16 owner = 0;
      u16 next = 0;
      u8 cluster_index = 0;
      if(program_store::file_extent_info(parsed.id, owner,
                                         cluster_index, next)) {
        detail |= 0x10000000UL | ((u32) owner << 8);
      } else if(program_store::extent_info(parsed.id, owner, next)) {
        detail |= 0x20000000UL | ((u32) owner << 8);
      } else if(program_store::entry_by_id(parsed.id, current)) {
        detail |= 0x30000000UL | ((u32) current.kind << 20) |
                  ((u32) current.type << 8);
      }
      detail |= (u32) program_store::last_write_failure_detail() << 16;
      detail |= (u32) program_store::last_write_failure() << 24;
      return g_error.fail(ErrorCode::APPLY, Phase::APPLY,
                          parsed.id, detail, parsed.name, true);
    }
  }
  if(program_store::write_file_from_source(
      parent_id, parsed.id, parsed.type, parsed.name, internal_size, source,
      chain.cluster_count > 1 ? extents : NULL,
      (u8) (chain.cluster_count - 1U), NULL,
      g_commit_compression_buffer, g_commit_compression_buffer_size)) {
    return true;
  }
  return g_error.fail(ErrorCode::APPLY, Phase::APPLY,
                      parsed.id, 4U, parsed.name, true);
}

static bool process_node(u16 parent_id, const ParsedNode& parsed,
                         u8 depth, WalkPass pass) {
  if(pass == WalkPass::VALIDATE) {
    const DesiredKind kind = parsed.directory ? DESIRED_DIRECTORY : DESIRED_FILE;
    if(!set_desired_kind(parsed.id, kind)) {
      return g_error.fail(ErrorCode::DUPLICATE_CLUSTER, Phase::VALIDATE,
                          cluster_for_id(parsed.id), (u32) kind, parsed.name);
    }
    program_store::Entry current;
    if(program_store::entry_by_id(parsed.id, current)) {
      if(parsed.directory != (current.kind == program_store::NodeKind::DIRECTORY)) {
        // Повторное использование между типами файла и каталога безопасно лишь
        // после полного удаления старого дерева; отказ сохраняет детерминизм восстановления.
        return g_error.fail(ErrorCode::KIND_CHANGE, Phase::VALIDATE,
                            cluster_for_id(parsed.id), (u32) current.kind,
                            parsed.name);
      }
    }
    if(!parsed.directory) {
      FileChain chain = {};
      if(!collect_file_chain(parsed, true, chain)) {
        return g_error.fail(ErrorCode::FILE_CHAIN, Phase::VALIDATE,
                            cluster_for_id(parsed.id), parsed.data_len, parsed.name);
      }
      program_store::Entry current = {};
      const bool exists =
          program_store::entry_by_id(parsed.id, current) &&
          current.kind == program_store::NodeKind::FILE;
      u32 current_visible_size = 0;
      if(exists && !exported_file_size(current, current_visible_size)) {
        return g_error.fail(ErrorCode::FILE_READ, Phase::VALIDATE,
                            parsed.id, current.data_len, parsed.name, true);
      }
      bool any_staged = false;
      if(!file_chain_complete(chain, exists, parsed.id,
                              exists ? current_visible_size : 0,
                              parsed.name, any_staged)) {
        return g_error.fail(ErrorCode::FILE_DATA, Phase::VALIDATE,
                            cluster_for_id(parsed.id), parsed.data_len, parsed.name);
      }
      // A chain without staged sectors whose visible bytes still map exactly
      // to the same C6 file cannot have changed.  Its stored M8 text and APP
      // payload were validated when they entered C6, so decoding them again
      // only makes metadata-only host traffic needlessly expensive.  Rename
      // and move handling remains in APPLY.
      const bool content_unchanged =
          exists && current.type == parsed.type &&
          current_visible_size == parsed.data_len && !any_staged &&
          file_chain_matches(chain, parsed.id);
      if(content_unchanged) return true;
      if(program_store::text_content(parsed.type)) {
        const u16 limit = parsed.type == program_store::ProgramType::TINYBASIC
            ? program_store::MAX_TINYBASIC_TEXT_SIZE
            : program_store::MAX_MK61_TEXT_SIZE;
        u16 internal_size = 0;
        if(!validate_text_chain(chain, limit, internal_size)) {
          return g_error.fail(ErrorCode::TEXT_ENCODING, Phase::VALIDATE,
                              parsed.data_len, limit, parsed.name);
        }
      }
#if MK61_ANY_LOADABLE_MODULE
      // Уже опубликованный APP может стать несовместимым после обновления
      // resident-прошивки. Пока его байты и FAT-цепочка не меняются, он не
      // должен блокировать удаление, переименование или копирование остальных
      // файлов. Новое и изменённое содержимое по-прежнему полностью
      // распаковывается и проверяется до первой мутации дерева C6.
      if(!validate_app_chain(parsed, chain)) return false;
#endif
      return true;
    }
    return walk_directory(parsed.id, false, cluster_for_id(parsed.id),
                          (u8) (depth + 1), pass);
  }

  if(parsed.directory) {
    // Directory clusters are only a transport representation.  A host may
    // preallocate a very long, empty tail (macOS commonly does this) after the
    // first 0x00 end marker.  Persisting that tail would consume one C6 node
    // per unused FAT cluster.  Import the live entries first; the final
    // ensure_all_directory_extents() pass materializes only the clusters that
    // those entries actually require.
    if(!program_store::create_directory(parent_id, parsed.name, parsed.id,
                                        NULL)) {
      return g_error.fail(ErrorCode::APPLY, Phase::APPLY,
                          parsed.id, 5U, parsed.name, true);
    }
    return walk_directory(parsed.id, false, cluster_for_id(parsed.id),
                          (u8) (depth + 1), pass);
  }
  return apply_file(parent_id, parsed);
}

static bool handle_directory_item(u16 parent_id, const u8* item,
                                  LfnState& lfn, u8 depth, WalkPass pass,
                                  bool& end) {
  if(item[0] == 0) {
    end = true;
    reset_lfn(lfn);
    return true;
  }
  if(item[11] == ATTR_LFN) {
    if(item[0] == 0xE5) reset_lfn(lfn);
    else parse_lfn(item, lfn);
    return true;
  }
  ParsedNode parsed = {};
  const ParseStatus status = parse_short_item(item, lfn, parsed);
  reset_lfn(lfn);
  if(status == ParseStatus::SKIP) return true;
  if(status == ParseStatus::INVALID) {
    return g_error.fail(ErrorCode::DIRECTORY_ENTRY, Phase::ENTRY, parent_id);
  }
  return process_node(parent_id, parsed, depth, pass);
}

static bool walk_directory(u16 parent_id, bool root, u16 first_cluster,
                           u8 depth, WalkPass pass) {
  if(depth > MAX_DEPTH) {
    return g_error.fail(ErrorCode::DEPTH, Phase::VALIDATE, depth, MAX_DEPTH);
  }
  LfnState lfn;
  reset_lfn(lfn);
  bool end = false;
  if(root) {
    for(u16 sector = 0; sector < geometry().root_sectors; sector++) {
      for(u8 slot = 0; slot < SECTOR_SIZE / 32; slot++) {
        const u8* block = NULL;
        if(!cached_effective_sector(root_start() + sector, block)) {
          return g_error.fail(ErrorCode::ROOT_READ, Phase::VALIDATE,
                              root_start() + sector, slot, nullptr, true);
        }
        u8 item[32];
        memcpy(item, block + slot * 32, sizeof(item));
        if(!handle_directory_item(program_store::ROOT_ID, item,
                                  lfn, depth, pass, end)) return false;
        if(end) return true;
      }
    }
    return true;
  }

  u16 cluster = first_cluster;
  for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
    if(!valid_cluster(cluster)) {
      return g_error.fail(ErrorCode::DIRECTORY_CLUSTER, Phase::CHAIN,
                          cluster, cluster_limit());
    }
    for(u8 sector = 0; sector < geometry().sectors_per_cluster; sector++) {
      if(end) break;
      for(u8 slot = 0; slot < SECTOR_SIZE / 32; slot++) {
        const u8* block = NULL;
        if(!cached_effective_sector(cluster_lba(cluster, sector), block)) {
          return g_error.fail(ErrorCode::DIRECTORY_READ, Phase::CHAIN,
                              cluster_lba(cluster, sector), slot, nullptr, true);
        }
        u8 item[32];
        memcpy(item, block + slot * 32, sizeof(item));
        if(!handle_directory_item(parent_id, item, lfn, depth,
                                  pass, end)) return false;
        if(end) break;
      }
    }
    // FAT specifies 0x00 as the end of all directory entries, not merely the
    // current sector.  Any clusters after it are allocation slack and must not
    // become persistent C6 directory extents.
    if(end) return true;
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) {
      return g_error.fail(ErrorCode::FAT_READ, Phase::CHAIN,
                          cluster, 0, nullptr, true);
    }
    if(fat_eof(next)) return true;
    if(next == FAT12_FREE || next == FAT12_BAD || !valid_cluster(next)) {
      return g_error.fail(ErrorCode::DIRECTORY_CHAIN, Phase::CHAIN, cluster, next);
    }
    if(pass == WalkPass::VALIDATE &&
       !set_desired_kind(id_for_cluster(next), DESIRED_EXTENT)) {
      return g_error.fail(ErrorCode::EXTENT_CHAIN, Phase::CHAIN, cluster, next);
    }
    cluster = next;
  }
  return g_error.fail(ErrorCode::DIRECTORY_CHAIN, Phase::CHAIN,
                      cluster, geometry().max_nodes);
}

static bool directory_chain_matches(u16 directory_id) {
  if(desired_kind(directory_id) != DESIRED_DIRECTORY) return false;
  u16 host_cluster = cluster_for_id(directory_id);
  u16 current_extent = program_store::INVALID_ID;
  (void) program_store::first_extent(directory_id, current_extent);
  for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
    u16 next = 0;
    if(!effective_fat_value(host_cluster, next)) return false;
    if(fat_eof(next)) return current_extent == program_store::INVALID_ID;
    if(!valid_cluster(next) || current_extent != id_for_cluster(next)) return false;
    host_cluster = next;
    if(!program_store::next_extent(current_extent, current_extent)) {
      current_extent = program_store::INVALID_ID;
    }
  }
  return false;
}

static bool release_all_extents(u16 directory_id) {
  return program_store::trim_directory_extents(directory_id, 0);
}

static bool release_mismatched_extent_chains(u16 parent_id, u8 depth = 0) {
  if(depth > MAX_DEPTH) return false;
  const int count = program_store::child_count(parent_id);
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent_id, index, entry)) return false;
    if(entry.kind != program_store::NodeKind::DIRECTORY) continue;
    if((!directory_chain_matches(entry.id) && !release_all_extents(entry.id)) ||
       !release_mismatched_extent_chains(entry.id, (u8) (depth + 1))) {
      return false;
    }
  }
  return true;
}

static bool release_repurposed_extents(void) {
  for(u16 id = 0; id < program_store::max_nodes(); id++) {
    const DesiredKind wanted = desired_kind(id);
    if(wanted != DESIRED_FILE && wanted != DESIRED_DIRECTORY) continue;
    u16 owner = 0;
    u16 next = 0;
    u8 cluster_index = 0;
    if(program_store::file_extent_info(
           id, owner, cluster_index, next)) {
      if(!program_store::release_file_extent(id)) return false;
      continue;
    }
    // A host is allowed to reuse allocation slack after the first 0x00
    // directory marker.  Older firmware persisted that entire preallocated
    // FAT tail as C6 directory extents.  If a later, interrupted host
    // transaction already points a live file or directory at one of those
    // clusters, free that exact extent before APPLY claims its stable id.
    // release_directory_extent() relinks both neighbours in one WAL record,
    // so this remains power-loss safe even when the reused node is in the
    // middle of a legacy tail.
    if(program_store::extent_info(id, owner, next) &&
       !program_store::release_directory_extent(id)) return false;
  }
  return true;
}

static bool prune_tree(u16 parent_id, bool strict) {
  int index = 0;
  while(index < program_store::child_count(parent_id)) {
    program_store::Entry entry;
    if(!program_store::child(parent_id, index, entry)) return false;
    if(entry.kind == program_store::NodeKind::DIRECTORY &&
       !prune_tree(entry.id, strict)) return false;
    const DesiredKind wanted = desired_kind(entry.id);
    const bool keep = (entry.kind == program_store::NodeKind::FILE &&
                       wanted == DESIRED_FILE) ||
                      (entry.kind == program_store::NodeKind::DIRECTORY &&
                       wanted == DESIRED_DIRECTORY);
    if(keep) {
      index++;
      continue;
    }
    if(entry.kind == program_store::NodeKind::DIRECTORY &&
       program_store::child_count(entry.id) != 0) {
      if(strict) return false;
      index++;
      continue;
    }
    if(!program_store::remove_id(entry.id)) return false;
  }
  return true;
}

static u32 directory_required_slots(u16 directory_id) {
  u32 slots = 2;
  const int count = program_store::child_count(directory_id);
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(directory_id, index, entry)) return 0;
    const u8 used = node_dirent_count(entry);
    if(used == 0) return 0;
    slots += used;
  }
  return slots;
}

static bool ensure_directory_extents(u16 directory_id) {
  startup_stage(20);
  const u32 slots = directory_required_slots(directory_id);
  if(slots == 0) return false;
  startup_stage(21);
  const u8 sectors_per_cluster = geometry().sectors_per_cluster;
  startup_stage(100U + sectors_per_cluster);
  const u32 per_cluster = (u32) sectors_per_cluster * (SECTOR_SIZE / 32);
  if(per_cluster == 0) return false;
  const u16 wanted = (u16) ((slots + per_cluster - 1) / per_cluster);
  startup_stage(22);
  u16 have = 1;
  u16 extent = 0;
  if(program_store::first_extent(directory_id, extent)) {
    do {
      have++;
    } while(program_store::next_extent(extent, extent));
  }
  startup_stage(23);
  while(have < wanted) {
    if(!program_store::allocate_directory_extent(directory_id,
                                                 program_store::INVALID_ID)) return false;
    have++;
  }
  startup_stage(24);
  if(have > wanted &&
     !program_store::trim_directory_extents(directory_id,
                                            (u16) (wanted - 1U))) return false;
  startup_stage(25);
  return true;
}

static bool ensure_all_directory_extents(u16 parent_id = program_store::ROOT_ID,
                                         u8 depth = 0) {
  if(depth > MAX_DEPTH) return false;
  const int count = program_store::child_count(parent_id);
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent_id, index, entry)) return false;
    if(entry.kind != program_store::NodeKind::DIRECTORY) continue;
    if(!ensure_directory_extents(entry.id) ||
       !ensure_all_directory_extents(entry.id, (u8) (depth + 1))) return false;
  }
  return true;
}

static void invalidate_clean_cache(void) {
  reset_directory_cursors();
  clear_exported_size_cache();
  if(g_session == NULL) return;
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    if(g_session->cache[slot].state == CACHE_CLEAN) {
      g_session->cache[slot].state = CACHE_EMPTY;
    }
  }
}

class ScopedCommitScratch {
  public:
    ScopedCommitScratch(void)
      : saved_extra_slots_(g_extra_cache_slots) {
      // К моменту создания этой защиты каждый грязный байт уже находится в
      // устойчивом к сбою питания журнале staging. Чистые записи кеша можно
      // удалить, чтобы VFAT_COMMIT занял shared_scratch, а
      // внешний кеш временно стал workspace упаковщика C6.
      memset(session().cache, 0, sizeof(session().cache));
      g_cache_scratch.reset();
      g_scratch_cache_slots = 0;
      g_commit_compression_buffer =
          saved_extra_slots_ != 0 ? g_extra_cache : NULL;
      g_commit_compression_buffer_size =
          (usize) saved_extra_slots_ * SECTOR_SIZE;
      g_extra_cache_slots = 0;
      update_cache_slot_count();
    }

    ~ScopedCommitScratch(void) {
      // Пока область scratch отсутствовала, фиксация могла заполнить чистые
      // записи кеша чтения. Очищаем их метаданные перед восстановлением слотов.
      memset(session().cache, 0, sizeof(session().cache));
      g_commit_compression_buffer = NULL;
      g_commit_compression_buffer_size = 0;
      g_extra_cache_slots = saved_extra_slots_;
      g_scratch_cache_slots = g_cache_scratch.acquire(
        shared_scratch::Owner::USB_CACHE, shared_scratch::SIZE
      ) ? SCRATCH_CACHE_SLOTS : 0;
      update_cache_slot_count();
    }

    ScopedCommitScratch(const ScopedCommitScratch&) = delete;
    ScopedCommitScratch& operator=(const ScopedCommitScratch&) = delete;

  private:
    u8 saved_extra_slots_;
};

class ScopedDesiredKinds {
 public:
  ScopedDesiredKinds() {
    memset(session().desired_kinds, 0, sizeof(session().desired_kinds));
  }
  ~ScopedDesiredKinds() {
    // The same two-bit array stores transient AppleDouble roles while the
    // volume is mounted. Never let partial validation kinds leak back into
    // the write path after either a successful or rejected commit. If the
    // MSC session continues after sync, rebuild those roles before accepting
    // the next packet: a retryable commit failure keeps the host FAT batch.
    memset(session().desired_kinds, 0, sizeof(session().desired_kinds));
    g_sidecar_scan_pending = g_sidecar_candidate_seen;
  }

  ScopedDesiredKinds(const ScopedDesiredKinds&) = delete;
  ScopedDesiredKinds& operator=(const ScopedDesiredKinds&) = delete;
};

static bool flush_write_cache_internal(void) {
  if(!discard_known_sidecars()) return false;
  while(true) {
    const int slot = oldest_dirty_cache();
    if(slot < 0) return true;
    if(!persist_cache_slot((u8) slot)) return false;
  }
}

static bool packet_contains_key(u32 lba, u16 count, u32 key) {
  if(key >= lba && key - lba < count) return true;
  const u32 fat = fat_start();
  const u32 fat_sectors = geometry().fat_sectors;
  if(key < fat || key - fat >= fat_sectors) return false;
  const u32 mirror = key + fat_sectors;
  return mirror >= lba && mirror - lba < count;
}

static int fast_reusable_cache_slot(u32 lba, u16 count) {
  SessionState& state = session();
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    if(state.cache[slot].state == CACHE_EMPTY) return slot;
  }
  int oldest = -1;
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    const CacheEntry& entry = state.cache[slot];
    // Удерживаем чистые секторы этого пакета зарезервированными до установки
    // всех его секторов: их байты могут стать грязными позднее в том же пакете.
    if(entry.state != CACHE_CLEAN ||
       packet_contains_key(lba, count, entry.lba)) continue;
    if(oldest < 0 || entry.age < state.cache[(u8) oldest].age) oldest = slot;
  }
  return oldest;
}

static bool fast_packet_fits(u32 lba, u16 count) {
  SessionState& state = session();
  u8 reusable = 0;
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    const CacheEntry& entry = state.cache[slot];
    if(entry.state == CACHE_EMPTY ||
       (entry.state == CACHE_CLEAN &&
        !packet_contains_key(lba, count, entry.lba))) reusable++;
  }

  u8 needed = 0;
  for(u16 index = 0; index < count; index++) {
    const u32 current_lba = lba + index;
    if(current_lba == 0 || sidecar_data_lba(current_lba) ||
       cache_index(current_lba) >= 0) continue;

    const u32 key = canonical_lba(current_lba);
    bool already_needed = false;
    for(u16 previous = 0; previous < index; previous++) {
      const u32 previous_lba = lba + previous;
      if(previous_lba != 0 && canonical_lba(previous_lba) == key) {
        already_needed = true;
        break;
      }
    }
    if(!already_needed && ++needed > reusable) return false;
  }
  return true;
}

static bool reserve_packet_cache_slots(u32 lba, u16 count) {
  // До первого изменения пакета освободим все нужные слоты. Если запись
  // вытесняемого старого сектора в журнал откажет, новый пакет останется
  // целиком непринятым, а уже подтверждённые старые данные — в RAM или NOR.
  u8 needed = 0;
  for(u16 index = 0; index < count; index++) {
    const u32 current_lba = lba + index;
    if(current_lba == 0 || sidecar_data_lba(current_lba) ||
       cache_index(current_lba) >= 0) continue;
    const u32 key = canonical_lba(current_lba);
    // Только вторая копия FAT может совпасть с более ранним LBA пакета.
    if(key < current_lba && key >= lba) continue;
    needed++;
  }

  SessionState& state = session();
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    if(state.cache[slot].state == CACHE_EMPTY && needed != 0) needed--;
  }
  while(needed != 0) {
    int victim = -1;
    for(u8 slot = 0; slot < g_cache_slots; slot++) {
      const CacheEntry& entry = state.cache[slot];
      if(entry.state == CACHE_EMPTY ||
         packet_contains_key(lba, count, entry.lba)) continue;
      if(entry.state == CACHE_CLEAN) {
        victim = slot;
        break; // Любой чистый слот дешевле вытеснения грязного.
      }
      if(victim < 0 || entry.age < state.cache[(u8) victim].age) victim = slot;
    }
    if(victim < 0 || !persist_cache_slot((u8) victim)) return false;
    state.cache[(u8) victim].state = CACHE_EMPTY;
    needed--;
  }
  return true;
}

static void write_reserved_packet_sector(u32 lba, const u8* data) {
  int found = cache_index(lba);
  if(found < 0) {
    for(u8 slot = 0; slot < g_cache_slots; slot++) {
      if(session().cache[slot].state == CACHE_EMPTY) {
        found = slot;
        break;
      }
    }
    if(found < 0) __builtin_trap(); // reserve_packet_cache_slots() гарантирует слот.
    CacheEntry& entry = session().cache[(u8) found];
    entry.lba = canonical_lba(lba);
    memcpy(cache_bytes((u8) found), data, SECTOR_SIZE);
    entry.state = CACHE_UNCHECKED;
  } else {
    u8* const bytes = cache_bytes((u8) found);
    if(memcmp(bytes, data, SECTOR_SIZE) != 0) {
      memcpy(bytes, data, SECTOR_SIZE);
      session().cache[(u8) found].state = CACHE_UNCHECKED;
    }
  }
  touch_cache((u8) found);
}

static void fast_cache_write_sector(u32 packet_lba, u16 packet_count,
                                    u32 lba, const u8* data) {
  const u32 key = canonical_lba(lba);
  int found = cache_index(key);
  u8 slot = 0;
  if(found >= 0) {
    slot = (u8) found;
    u8* const bytes = cache_bytes(slot);
    if(memcmp(bytes, data, SECTOR_SIZE) != 0) {
      memcpy(bytes, data, SECTOR_SIZE);
      session().cache[slot].state = CACHE_UNCHECKED;
    }
    touch_cache(slot);
    return;
  }

  found = fast_reusable_cache_slot(packet_lba, packet_count);
  // fast_packet_fits() резервирует все нужные слоты до любого изменения.
  if(found < 0) __builtin_trap();
  slot = (u8) found;
  CacheEntry& entry = session().cache[slot];
  // Не публикуем новый ключ, пока не получены все его байты. Этот путь не
  // обращается к SPI и потому безопасен внутри обратного вызова USB.
  entry.state = CACHE_EMPTY;
  entry.lba = key;
  memcpy(cache_bytes(slot), data, SECTOR_SIZE);
  touch_cache(slot);
  entry.state = CACHE_UNCHECKED;
}

} // пространство имён

u32 sector_count(void) {
  return program_store::ready() ? geometry().logical_sectors : 0;
}

u32 volume_serial(void) {
  if(g_session_volume_serial_valid) return g_session_volume_serial;
  u32 capacity = 0;
  if(program_store::ready()) {
    const storage_geometry::Geometry& current_geometry = geometry();
    startup_stage(30);
    capacity = current_geometry.capacity_bytes;
    startup_stage(31);
  }
  const u32 legacy_volume_serial = 0xC6000000UL ^ capacity;
  startup_stage(32);
  const u32 stable = device_identity::fat_volume_serial(
      device_identity::read(), legacy_volume_serial);
  startup_stage(33);
  return stable ^ program_store::media_revision();
}

bool read_sector(u32 lba, u8* output) {
  if(output == NULL || !program_store::ready() || lba >= sector_count()) return false;
  return read_effective_sector(lba, output);
}

bool read_sectors(u32 lba, u8* output, u16 count) {
  if(output == NULL && count != 0) return false;
  for(u16 i = 0; i < count; i++) {
    if(!read_sector(lba + i, output + (u32) i * SECTOR_SIZE)) return false;
  }
  return true;
}

bool set_external_cache(u8* data, usize size) {
  if(g_session != NULL) return false;
  if(data == NULL || size < SECTOR_SIZE) {
    g_extra_cache = NULL;
    g_extra_cache_slots = 0;
    update_cache_slot_count();
    return data == NULL;
  }
  usize slots = size / SECTOR_SIZE;
  if(slots > EXTERNAL_CACHE_SLOTS) slots = EXTERNAL_CACHE_SLOTS;
  g_extra_cache = data;
  g_extra_cache_slots = (u8) slots;
  update_cache_slot_count();
  return true;
}

u8 write_cache_capacity(void) {
  return g_cache_slots;
}

u8 dirty_cache_sectors(void) {
  if(g_session == NULL) return 0;
  u8 count = 0;
  for(u8 slot = 0; slot < g_cache_slots; slot++) {
    const CacheState state = g_session->cache[slot].state;
    if(state == CACHE_UNCHECKED) count++;
  }
  return count;
}

bool try_write_cached_sectors(u32 lba, const u8* data, u16 count) {
  // В отличие от write_cached_sectors(), эту функцию вызывает стек USB. Она не
  // должна занимать память, читать или программировать SPI NOR, вытеснять грязные
  // данные либо частично принимать пакет, которому затем нужен отложенный путь цикла.
  if((data == NULL && count != 0) || !program_store::ready() ||
     g_session == NULL || count > MAX_CACHE_SLOTS || lba > sector_count() ||
     (u32) count > sector_count() - lba || !fast_packet_fits(lba, count)) {
    return false;
  }
  for(u16 index = 0; index < count; index++) {
    const u32 current_lba = lba + index;
    const u8* const block = data + (u32) index * SECTOR_SIZE;
    const bool candidate = contains_sidecar_name(block);
    if(candidate && sidecar_filter_enabled()) g_sidecar_candidate_seen = true;
    if(current_lba != 0 && !sidecar_data_lba(current_lba)) {
      fast_cache_write_sector(lba, count, current_lba, block);
    }
    if((candidate && sidecar_filter_enabled()) || (g_sidecar_candidate_seen &&
                     current_lba != 0 && directory_metadata_lba(current_lba))) {
      g_sidecar_scan_pending = true;
    }
  }
  return true;
}

bool write_cached_sectors(u32 lba, const u8* data, u16 count) {
  if((data == NULL && count != 0) || !program_store::ready() ||
     !ensure_session() || lba > sector_count() ||
     (u32) count > sector_count() - lba || count > g_cache_slots) return false;

  // Закончим обработку старого пакета до изменения нового. Обычный BOT
  // пакет не больше cache capacity; его отложенный путь резервирует все
  // слоты до первого memcpy, как и быстрый путь в USB callback.
  if(!discard_known_sidecars()) return false;
  if(!reserve_packet_cache_slots(lba, count)) return false;
  for(u16 i = 0; i < count; i++) {
    const u32 current_lba = lba + i;
    const u8* const block = data + (u32) i * SECTOR_SIZE;
    const bool candidate = contains_sidecar_name(block);
    if(candidate && sidecar_filter_enabled()) g_sidecar_candidate_seen = true;
    if(current_lba == 0) continue;
    if(sidecar_data_lba(current_lba)) continue;
    write_reserved_packet_sector(current_lba, block);
    if((candidate && sidecar_filter_enabled()) || (g_sidecar_candidate_seen &&
                     directory_metadata_lba(current_lba))) {
      g_sidecar_scan_pending = true;
    }
  }
  // Это write-back cache (SCSI WCE=1): если последующая фильтрация sidecar
  // встретила временный сбой I/O, пакет уже принят. Оставляем scan_pending и
  // возвращаем ошибку при sync/eject, если повторная попытка тоже не удалась.
  (void) discard_known_sidecars();
  return true;
}

bool flush_write_cache(void) {
  return program_store::ready() && ensure_session() &&
         flush_write_cache_internal();
}

bool write_sector(u32 lba, const u8* data) {
  if(!write_cached_sectors(lba, data, 1)) return false;
  const int slot = lba == 0 ? -1 : cache_index(lba);
  return slot < 0 || persist_cache_slot((u8) slot);
}

bool write_sectors(u32 lba, const u8* data, u16 count) {
  return write_cached_sectors(lba, data, count) && flush_write_cache();
}

CommitResult flush_pending_result(void) {
  g_error.begin_attempt();
  if(!program_store::ready() || !ensure_session()) {
    record_startup_timeout();
    g_error.fail(ErrorCode::STORAGE_UNAVAILABLE, Phase::SESSION,
                  0, 0, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  if(!flush_write_cache_internal()) {
    g_error.fail(ErrorCode::CACHE_WRITE, Phase::CACHE,
                  dirty_cache_sectors(), g_cache_slots, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  const u16 staged_before = program_store::vfat_stage_count();
  if(staged_before == 0) {
    return CommitResult::OK;
  }
  startup_stage(50);
  ScopedCommitScratch commit_scratch;
  ScopedDesiredKinds desired_kinds;
  invalidate_clean_cache();
  startup_stage(51);
  if(!walk_directory(program_store::ROOT_ID, true, 0, 0,
                     WalkPass::VALIDATE)) {
    // Preserve the classification made by validation itself.  A slow but
    // deterministic incomplete host transaction is safe to roll back even
    // when the startup deadline expires at the same instant.  Previously
    // record_startup_timeout() added RETRYABLE to that already-recorded
    // FILE_DATA error, turning a disposable partial FAT journal into a
    // permanent mount blocker.
    const bool retryable = (g_error.value.flags & RETRYABLE) != 0;
    if(retryable) record_startup_timeout();
    g_error.fail(ErrorCode::VALIDATE, Phase::VALIDATE);
    return retryable ? CommitResult::IO_FAILED : CommitResult::REJECTED;
  }
  startup_stage(52);
  if(!release_repurposed_extents() ||
     !release_mismatched_extent_chains(program_store::ROOT_ID) ||
     !prune_tree(program_store::ROOT_ID, false)) {
    record_startup_timeout();
    g_error.fail(ErrorCode::PREPARE, Phase::PREPARE, 0, 0, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  startup_stage(53);
  invalidate_clean_cache();
  if(!walk_directory(program_store::ROOT_ID, true, 0, 0,
                     WalkPass::APPLY)) {
    record_startup_timeout();
    g_error.fail(ErrorCode::APPLY, Phase::APPLY, 0, 0, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  startup_stage(54);
  if(!prune_tree(program_store::ROOT_ID, true)) {
    record_startup_timeout();
    g_error.fail(ErrorCode::PRUNE, Phase::COMMIT, 0, 0, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  startup_stage(55);
  if(!program_store::vfat_stage_discard_all()) {
    record_startup_timeout();
    g_error.fail(ErrorCode::STAGE_DISCARD, Phase::COMMIT, 0, 0, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  startup_stage(56);
  invalidate_clean_cache();
  if(!ensure_all_directory_extents()) {
    record_startup_timeout();
    g_error.fail(ErrorCode::DIRECTORY_EXTENTS, Phase::COMMIT, 0, 0, nullptr, true);
    return CommitResult::IO_FAILED;
  }
  startup_stage(57);
  clear_diagnostic();
  startup_stage(58);
  return CommitResult::OK;
}

bool flush_pending(void) {
  return flush_pending_result() == CommitResult::OK;
}

CommitResult finalize_pending_result(void) {
  const CommitResult result = flush_pending_result();
  if(result != CommitResult::REJECTED) return result;
#if defined(MK61_BUILD_USBDISK_MODULE)
  // Validation may legitimately consume the whole startup budget before it
  // proves that the journal is deterministic garbage.  Give the bounded,
  // power-safe rollback its own budget; otherwise the ABI guard rejects the
  // very discard operation required to recover on the next mount.
  mk61_usbdisk_restart_startup_budget();
#endif
  if(program_store::ready() && ensure_session() &&
     program_store::vfat_stage_discard_all()) {
    memset(session().cache, 0, sizeof(session().cache));
    return CommitResult::REJECTED;
  }
  g_error.fail(ErrorCode::STAGE_DISCARD, Phase::COMMIT, 0, 0, nullptr, true);
  return CommitResult::IO_FAILED;
}

bool finalize_pending(void) {
  return finalize_pending_result() == CommitResult::OK;
}

bool reset_session(void) {
  ScopedStartupRecovery recovery;
  (void) recovery;
  reset_directory_cursors();
  clear_exported_size_cache();
  startup_stage(1);
  g_session_volume_serial_valid = false;
  if(!program_store::ready() || !ensure_session()) {
    record_startup_timeout();
    return false;
  }
  startup_stage(2);
  if(!g_cache_scratch.ok()) {
    g_scratch_cache_slots = g_cache_scratch.acquire(
      shared_scratch::Owner::USB_CACHE, shared_scratch::SIZE
    ) ? SCRATCH_CACHE_SLOTS : 0;
    update_cache_slot_count();
  }
  startup_stage(3);
  memset(g_session, 0, sizeof(*g_session));
  g_sidecar_scan_pending = false;
  g_sidecar_candidate_seen = false;
  startup_stage(4);
  // Persistent staging is a write-ahead journal, not a second filesystem.
  // A reset can follow an unplug or a power loss before the MSC close path had
  // a chance to finalize it. Reconcile that journal before exposing any FAT
  // sector to the next host session: a complete transaction is committed, a
  // deterministic invalid/partial one is rolled back, and a retryable media
  // failure keeps the journal for the next recovery attempt and refuses mount.
  if(program_store::vfat_stage_count() != 0 &&
     finalize_pending_result() == CommitResult::IO_FAILED) {
    return false;
  }
  startup_stage(45);
  const u16 remaining_stage = program_store::vfat_stage_count();
  startup_stage(46);
  startup_stage(5);
  if(remaining_stage != 0) {
    return g_error.fail(ErrorCode::STAGE_DISCARD, Phase::SESSION,
                        remaining_stage, 0, nullptr, true);
  }
  if(!ensure_all_directory_extents()) {
    record_startup_timeout();
    return g_error.fail(ErrorCode::DIRECTORY_EXTENTS, Phase::SESSION,
                        0, 0, nullptr, true);
  }
  startup_stage(6);
  // Freeze the identity for this mounted session. Host writes advance the
  // persistent staging generation, but a FAT volume must never change serial
  // while it is mounted. The next session observes the new revision and makes
  // macOS discard directory sectors cached from an interrupted transaction.
  g_session_volume_serial = volume_serial();
  g_session_volume_serial_valid = true;
  startup_stage(7);
  invalidate_clean_cache();
  return true;
}

void end_session(void) {
  startup_stage(40);
  g_cache_scratch.reset();
  startup_stage(41);
  g_session = NULL;
  g_session_lease.reset();
  startup_stage(42);
  program_store::vfat_stage_unlock();
  startup_stage(43);
  g_extra_cache = NULL;
  g_scratch_cache_slots = 0;
  g_extra_cache_slots = 0;
  update_cache_slot_count();
  g_session_volume_serial_valid = false;
  g_sidecar_scan_pending = false;
  g_sidecar_candidate_seen = false;
  clear_exported_size_cache();
  startup_stage(44);
}

const Diagnostic& diagnostic(void) { return g_error.value; }
void clear_diagnostic(void) { g_error.clear(); }
void report_startup_failure(u32 stage, const char* subject) {
  g_error.begin_attempt();
  g_error.fail(ErrorCode::STORAGE_UNAVAILABLE, Phase::SESSION,
               stage, 0, subject, true);
}
void restore_diagnostic(const Diagnostic& value) {
  g_error.value = value;
  g_error.recorded = false;
}

} // пространство имён virtual_fat

#endif
