#include "virtual_fat.hpp"

#include "fat_name.hpp"
#include "language_workspace.hpp"
#include "program_store.hpp"
#include "shared_scratch.hpp"

#include <stdio.h>
#include <string.h>

namespace virtual_fat {
namespace {

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
static constexpr u32 INVALID_LBA = 0xFFFFFFFFUL;

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

struct SessionState {
  u8 desired_kinds[KIND_MAP_BYTES];
  u8 sector_cache[SECTOR_SIZE];
  u8 fat_cache[SECTOR_SIZE];
  u32 sector_cache_lba;
  u32 fat_cache_lba;
  bool sector_cache_valid;
  bool fat_cache_valid;
};

static_assert(sizeof(SessionState) < 2304,
              "C5 FAT session state must stay well below the shared 8 KiB workspace");
static_assert(shared_scratch::SIZE >= program_store::MAX_MK61_TEXT_SIZE,
              "USB import payload must fit the shared scratch buffer");

static language_workspace::Lease g_session_lease;
static SessionState* g_session;
static const char* g_last_error;
static char g_error_detail[48];

static bool ensure_session(void) {
  if(g_session_lease.ok() && g_session != NULL) return true;
  if(!g_session_lease.acquire(language_workspace::Owner::USB_DISK,
                              sizeof(SessionState))) return false;
  g_session = (SessionState*) g_session_lease.data();
  memset(g_session, 0, sizeof(*g_session));
  g_session->sector_cache_lba = INVALID_LBA;
  g_session->fat_cache_lba = INVALID_LBA;
  return true;
}

static SessionState& session(void) {
  if(!ensure_session()) __builtin_trap();
  return *g_session;
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
    {".t1", program_store::ProgramType::TEXT},
    {".m2", program_store::ProgramType::MK61_STATE},
    {".fmk", program_store::ProgramType::FONT}
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

static bool utf8_to_utf16(const char* input, u16* output, u16 capacity,
                          u16& output_len) {
  output_len = 0;
  if(input == NULL) return false;
  const u8* source = (const u8*) input;
  while(*source != 0) {
    u32 codepoint = 0;
    u8 count = 0;
    if(source[0] < 0x80) {
      codepoint = source[0];
      count = 1;
    } else if((source[0] & 0xE0) == 0xC0 &&
              (source[1] & 0xC0) == 0x80) {
      codepoint = ((u32) (source[0] & 0x1F) << 6) | (source[1] & 0x3F);
      count = 2;
      if(codepoint < 0x80) return false;
    } else if((source[0] & 0xF0) == 0xE0 &&
              (source[1] & 0xC0) == 0x80 &&
              (source[2] & 0xC0) == 0x80) {
      codepoint = ((u32) (source[0] & 0x0F) << 12) |
                  ((u32) (source[1] & 0x3F) << 6) | (source[2] & 0x3F);
      count = 3;
      if(codepoint < 0x800 || (codepoint >= 0xD800 && codepoint <= 0xDFFF)) return false;
    } else if((source[0] & 0xF8) == 0xF0 &&
              (source[1] & 0xC0) == 0x80 &&
              (source[2] & 0xC0) == 0x80 &&
              (source[3] & 0xC0) == 0x80) {
      codepoint = ((u32) (source[0] & 0x07) << 18) |
                  ((u32) (source[1] & 0x3F) << 12) |
                  ((u32) (source[2] & 0x3F) << 6) | (source[3] & 0x3F);
      count = 4;
      if(codepoint < 0x10000 || codepoint > 0x10FFFF) return false;
    } else {
      return false;
    }
    if(codepoint <= 0xFFFF) {
      if(output_len >= capacity) return false;
      output[output_len++] = (u16) codepoint;
    } else {
      if(output_len + 2 > capacity) return false;
      codepoint -= 0x10000;
      output[output_len++] = (u16) (0xD800 | (codepoint >> 10));
      output[output_len++] = (u16) (0xDC00 | (codepoint & 0x3FF));
    }
    source += count;
  }
  return true;
}

static bool append_utf8(u32 codepoint, char* output, u16 capacity, u16& len) {
  u8 bytes = codepoint < 0x80 ? 1 : codepoint < 0x800 ? 2 :
             codepoint < 0x10000 ? 3 : 4;
  if((u16) (len + bytes) >= capacity) return false;
  if(bytes == 1) {
    output[len++] = (char) codepoint;
  } else if(bytes == 2) {
    output[len++] = (char) (0xC0 | (codepoint >> 6));
    output[len++] = (char) (0x80 | (codepoint & 0x3F));
  } else if(bytes == 3) {
    output[len++] = (char) (0xE0 | (codepoint >> 12));
    output[len++] = (char) (0x80 | ((codepoint >> 6) & 0x3F));
    output[len++] = (char) (0x80 | (codepoint & 0x3F));
  } else {
    output[len++] = (char) (0xF0 | (codepoint >> 18));
    output[len++] = (char) (0x80 | ((codepoint >> 12) & 0x3F));
    output[len++] = (char) (0x80 | ((codepoint >> 6) & 0x3F));
    output[len++] = (char) (0x80 | (codepoint & 0x3F));
  }
  return true;
}

static bool utf16_to_utf8(const u16* input, u16 input_len, char* output,
                          u16 capacity) {
  u16 len = 0;
  for(u16 i = 0; i < input_len; i++) {
    u32 codepoint = input[i];
    if(codepoint == 0 || codepoint == 0xFFFF) break;
    if(codepoint >= 0xD800 && codepoint <= 0xDBFF) {
      if(i + 1 >= input_len || input[i + 1] < 0xDC00 ||
         input[i + 1] > 0xDFFF) return false;
      codepoint = 0x10000 + (((u32) codepoint - 0xD800) << 10) +
                  ((u32) input[++i] - 0xDC00);
    } else if(codepoint >= 0xDC00 && codepoint <= 0xDFFF) {
      return false;
    }
    if(!append_utf8(codepoint, output, capacity, len)) return false;
  }
  if(len >= capacity) return false;
  output[len] = 0;
  return len != 0;
}

static void full_name(const program_store::Entry& entry, char* output,
                      usize capacity) {
  if(entry.kind == program_store::NodeKind::DIRECTORY) {
    strncpy(output, entry.name, capacity - 1);
    output[capacity - 1] = 0;
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
  if(!utf8_to_utf16(name, units, MAX_LFN_UNITS, unit_count)) return false;
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
  put_le32(item, 28, entry.kind == program_store::NodeKind::FILE
                          ? entry.data_len : 0);
  return true;
}

static bool render_no_index_dirent(u8 offset, u8* item) {
  static const char name[] = ".metadata_never_index";
  static const u8 alias[11] = {
    'M', 'E', 'T', 'A', 'D', 'A', 'T', 'A', 'N', 'I', 'X'
  };
  u16 units[MAX_LFN_UNITS];
  u16 unit_count = 0;
  if(!utf8_to_utf16(name, units, MAX_LFN_UNITS, unit_count)) return false;
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
  memcpy(output + 3, "MK61C5  ", 8);
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
  put_le32(output, 39, 0xC5000000UL ^ geometry().capacity_bytes);
  memcpy(output + 43, "MK61S C5   ", 11);
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
    if(entry.kind == program_store::NodeKind::FILE) return FAT12_EOF;
    u16 extent = 0;
    return program_store::first_extent(id, extent)
        ? cluster_for_id(extent) : FAT12_EOF;
  }
  u16 owner = 0;
  u16 next = 0;
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
  u32 cursor = 0;
  if(root) {
    if(first_slot == 0) {
      memcpy(output, "MK61S C5   ", 11);
      output[11] = ATTR_VOLUME;
      for(u8 offset = 0;
          offset + 1 < storage_geometry::ROOT_SYSTEM_DIRENTS;
          offset++) {
        if(!render_no_index_dirent(offset, output + (u16) (offset + 1) * 32)) {
          return false;
        }
      }
    }
    cursor = storage_geometry::ROOT_SYSTEM_DIRENTS;
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
    cursor = 2;
  }

  const int children = program_store::child_count(parent_id);
  for(int index = 0; index < children; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent_id, index, entry)) return false;
    const u8 count = node_dirent_count(entry);
    if(count == 0) return false;
    for(u8 offset = 0; offset < count; offset++) {
      const u32 slot = cursor + offset;
      if(slot >= first_slot && slot < last_slot &&
         !render_node_dirent(entry, offset,
                             output + (slot - first_slot) * 32)) return false;
    }
    cursor += count;
    if(cursor >= last_slot && cursor > first_slot) {
      // Entries after this point cannot affect the requested sector.
      if(cursor >= last_slot) break;
    }
  }
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
      const u16 file_offset = (u16) sector * SECTOR_SIZE;
      if(file_offset >= entry.data_len) return true;
      u16 copied = 0;
      return program_store::read_range_id(id, file_offset, output, SECTOR_SIZE,
                                          &copied);
    }
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

static bool read_effective_sector(u32 lba, u8* output) {
  const u32 key = canonical_lba(lba);
  if(key != 0 && program_store::vfat_stage_exists(key)) {
    return program_store::vfat_stage_read(key, output);
  }
  return read_base_sector(lba, output);
}

static bool cached_effective_sector(u32 lba, const u8*& output) {
  SessionState& state = session();
  const u32 key = canonical_lba(lba);
  if(!state.sector_cache_valid || state.sector_cache_lba != key) {
    if(!read_effective_sector(lba, state.sector_cache)) return false;
    state.sector_cache_lba = key;
    state.sector_cache_valid = true;
  }
  output = state.sector_cache;
  return true;
}

static bool effective_fat_sector(u32 index, const u8*& output) {
  if(index >= geometry().fat_sectors) return false;
  SessionState& state = session();
  const u32 lba = fat_start() + index;
  if(!state.fat_cache_valid || state.fat_cache_lba != lba) {
    if(!read_effective_sector(lba, state.fat_cache)) return false;
    state.fat_cache_lba = lba;
    state.fat_cache_valid = true;
  }
  output = state.fat_cache;
  return true;
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
         utf16_to_utf8(lfn.name, (u16) lfn.expected * 13, output, capacity);
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
  // Finder stores extended attributes/resource forks in AppleDouble files.
  // Their suffix intentionally mirrors the real file (for example
  // "._game.m61"), so extension-based C5 import must reject them before it
  // mistakes a multi-kilobyte metadata blob for calculator source.
  return name[0] == '.' && name[1] == '_';
}

static ParseStatus parse_short_item(const u8* item, const LfnState& lfn,
                                    ParsedNode& parsed) {
  if((item[11] & ATTR_VOLUME) != 0 || item[0] == 0xE5) return ParseStatus::SKIP;
  if(item[0] == '.') return ParseStatus::SKIP;
  char name[program_store::NAME_SIZE + 16];
  if(!accepted_lfn(lfn, item, name, sizeof(name)) &&
     !short_name(item, name, sizeof(name))) return ParseStatus::INVALID;
  parsed.directory = (item[11] & ATTR_DIRECTORY) != 0;
  parsed.attributes = item[11];
  const u16 cluster = get_le16(item, 26);
  if(parsed.directory) {
    if(system_directory(name, parsed.attributes)) return ParseStatus::SKIP;
    if(!valid_cluster(cluster) || strlen(name) >= program_store::NAME_SIZE) {
      return ParseStatus::INVALID;
    }
    strcpy(parsed.name, name);
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
  // Unsupported host files are intentionally ignored regardless of size.
  // Apply the C5 payload quota only after a recognized calculator extension
  // has been selected.
  if(size > program_store::MAX_MK61_TEXT_SIZE) return ParseStatus::INVALID;
  if(!valid_cluster(cluster)) return ParseStatus::INVALID;
  strcpy(parsed.name, name);
  parsed.id = id_for_cluster(cluster);
  parsed.data_len = (u16) size;
  return ParseStatus::VALID;
}

enum class WalkPass : u8 { VALIDATE, APPLY };

static bool reconcile_directory_chain(u16 directory_id);
static bool walk_directory(u16 parent_id, bool root, u16 first_cluster,
                           u8 depth, WalkPass pass);

static bool file_sector_staged(u16 id, u8 sector) {
  return program_store::vfat_stage_exists(
      cluster_lba(cluster_for_id(id), sector));
}

static bool apply_file(u16 parent_id, const ParsedNode& parsed) {
  program_store::Entry current;
  const bool exists = program_store::entry_by_id(parsed.id, current) &&
                      current.kind == program_store::NodeKind::FILE;
  const u8 sectors = (u8) ((parsed.data_len + SECTOR_SIZE - 1) / SECTOR_SIZE);
  bool any_staged = false;
  for(u8 sector = 0; sector < sectors; sector++) {
    if(file_sector_staged(parsed.id, sector)) any_staged = true;
  }
  const bool baseline_compatible = exists && current.type == parsed.type &&
                                   current.data_len == parsed.data_len;
  if(baseline_compatible && !any_staged) {
    if(current.parent_id == parent_id && strcmp(current.name, parsed.name) == 0) {
      return true;
    }
    return program_store::move_rename(parsed.id, parent_id, parsed.name);
  }
  if(!baseline_compatible) {
    for(u8 sector = 0; sector < sectors; sector++) {
      if(!file_sector_staged(parsed.id, sector)) return false;
    }
  }

  shared_scratch::Lease scratch(shared_scratch::Owner::VFAT_COMMIT,
                                parsed.data_len);
  if(parsed.data_len != 0 && !scratch.ok()) return false;
  for(u8 sector = 0; sector < sectors; sector++) {
    u8 block[SECTOR_SIZE];
    if(!read_effective_sector(cluster_lba(cluster_for_id(parsed.id), sector),
                              block)) return false;
    const u16 offset = (u16) sector * SECTOR_SIZE;
    const u16 count = (u16) ((parsed.data_len - offset < SECTOR_SIZE)
        ? parsed.data_len - offset : SECTOR_SIZE);
    memcpy(scratch.data() + offset, block, count);
  }
  return program_store::write_file(parent_id, parsed.id, parsed.type,
                                   parsed.name,
                                   parsed.data_len == 0 ? NULL : scratch.data(),
                                   parsed.data_len, NULL);
}

static bool process_node(u16 parent_id, const ParsedNode& parsed,
                         u8 depth, WalkPass pass) {
  if(pass == WalkPass::VALIDATE) {
    const DesiredKind kind = parsed.directory ? DESIRED_DIRECTORY : DESIRED_FILE;
    if(!set_desired_kind(parsed.id, kind)) {
      snprintf(g_error_detail, sizeof(g_error_detail), "duplicate-cluster:%u:%s",
               (unsigned) parsed.id, parsed.name);
      g_last_error = g_error_detail;
      return false;
    }
    program_store::Entry current;
    if(program_store::entry_by_id(parsed.id, current)) {
      if(parsed.directory != (current.kind == program_store::NodeKind::DIRECTORY)) {
        // Reuse across file/directory kinds is safe only after the old tree is
        // fully removed; rejecting it keeps recovery deterministic.
        g_last_error = "kind-change";
        return false;
      }
    }
    u16 next = 0;
    if(!effective_fat_value(cluster_for_id(parsed.id), next)) {
      g_last_error = "fat-read";
      return false;
    }
    if(!parsed.directory) {
      if(!fat_eof(next)) g_last_error = "file-chain";
      return fat_eof(next);
    }
    return walk_directory(parsed.id, false, cluster_for_id(parsed.id),
                          (u8) (depth + 1), pass);
  }

  if(parsed.directory) {
    if(!program_store::create_directory(parent_id, parsed.name, parsed.id, NULL) ||
       !reconcile_directory_chain(parsed.id)) return false;
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
    g_last_error = "directory-entry";
    return false;
  }
  return process_node(parent_id, parsed, depth, pass);
}

static bool walk_directory(u16 parent_id, bool root, u16 first_cluster,
                           u8 depth, WalkPass pass) {
  if(depth > MAX_DEPTH) {
    g_last_error = "depth";
    return false;
  }
  LfnState lfn;
  reset_lfn(lfn);
  bool end = false;
  if(root) {
    for(u16 sector = 0; sector < geometry().root_sectors; sector++) {
      for(u8 slot = 0; slot < SECTOR_SIZE / 32; slot++) {
        const u8* block = NULL;
        if(!cached_effective_sector(root_start() + sector, block)) {
          g_last_error = "root-read";
          return false;
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
      g_last_error = "directory-cluster";
      return false;
    }
    for(u8 sector = 0; sector < geometry().sectors_per_cluster; sector++) {
      if(end) break;
      for(u8 slot = 0; slot < SECTOR_SIZE / 32; slot++) {
        const u8* block = NULL;
        if(!cached_effective_sector(cluster_lba(cluster, sector), block)) {
          g_last_error = "directory-read";
          return false;
        }
        u8 item[32];
        memcpy(item, block + slot * 32, sizeof(item));
        if(!handle_directory_item(parent_id, item, lfn, depth,
                                  pass, end)) return false;
        if(end) break;
      }
    }
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) {
      g_last_error = "directory-fat-read";
      return false;
    }
    if(fat_eof(next)) return true;
    if(next == FAT12_FREE || next == FAT12_BAD || !valid_cluster(next)) {
      g_last_error = "directory-chain";
      return false;
    }
    if(pass == WalkPass::VALIDATE &&
       !set_desired_kind(id_for_cluster(next), DESIRED_EXTENT)) {
      g_last_error = "extent-chain";
      return false;
    }
    cluster = next;
  }
  return false;
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
  for(;;) {
    u16 extent = 0;
    if(!program_store::first_extent(directory_id, extent)) return true;
    for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
      u16 next = 0;
      if(!program_store::next_extent(extent, next)) break;
      extent = next;
    }
    if(!program_store::release_directory_extent(extent)) return false;
  }
}

static bool reconcile_directory_chain(u16 directory_id) {
  if(directory_chain_matches(directory_id)) return true;
  if(!release_all_extents(directory_id)) return false;
  u16 cluster = cluster_for_id(directory_id);
  for(u16 guard = 0; guard < geometry().max_nodes; guard++) {
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) return false;
    if(fat_eof(next)) return true;
    if(!valid_cluster(next) ||
       !program_store::allocate_directory_extent(directory_id,
                                                  id_for_cluster(next))) return false;
    cluster = next;
  }
  return false;
}

static bool release_mismatched_extent_chains(void) {
  for(u16 id = 0; id < geometry().max_nodes; id++) {
    program_store::Entry entry;
    if(!program_store::entry_by_id(id, entry) ||
       entry.kind != program_store::NodeKind::DIRECTORY) continue;
    if(!directory_chain_matches(id) && !release_all_extents(id)) return false;
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
  const u32 slots = directory_required_slots(directory_id);
  if(slots == 0) return false;
  const u32 per_cluster = (u32) geometry().sectors_per_cluster *
                          (SECTOR_SIZE / 32);
  const u16 wanted = (u16) ((slots + per_cluster - 1) / per_cluster);
  u16 have = 1;
  u16 extent = 0;
  if(program_store::first_extent(directory_id, extent)) {
    do {
      have++;
    } while(program_store::next_extent(extent, extent));
  }
  while(have < wanted) {
    if(!program_store::allocate_directory_extent(directory_id,
                                                 program_store::INVALID_ID)) return false;
    have++;
  }
  while(have > wanted) {
    if(!program_store::first_extent(directory_id, extent)) return false;
    for(u16 guard = 1; guard + 1 < have; guard++) {
      if(!program_store::next_extent(extent, extent)) return false;
    }
    if(!program_store::release_directory_extent(extent)) return false;
    have--;
  }
  return true;
}

static bool ensure_all_directory_extents(void) {
  for(u16 id = 0; id < geometry().max_nodes; id++) {
    program_store::Entry entry;
    if(program_store::entry_by_id(id, entry) &&
       entry.kind == program_store::NodeKind::DIRECTORY &&
       !ensure_directory_extents(id)) return false;
  }
  return true;
}

static void invalidate_caches(void) {
  if(g_session == NULL) return;
  g_session->sector_cache_valid = false;
  g_session->fat_cache_valid = false;
  g_session->sector_cache_lba = INVALID_LBA;
  g_session->fat_cache_lba = INVALID_LBA;
}

} // namespace

u32 sector_count(void) {
  return program_store::ready() ? geometry().logical_sectors : 0;
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

bool write_sector(u32 lba, const u8* data) {
  if(data == NULL || !program_store::ready() || lba >= sector_count()) return false;
  if(lba == 0) return true;
  if(!ensure_session()) return false;
  const u32 key = canonical_lba(lba);
  if(lba < data_start()) {
    u8 current[SECTOR_SIZE];
    if(!read_effective_sector(lba, current)) return false;
    if(memcmp(current, data, sizeof(current)) == 0) return true;
  }
  if(!program_store::vfat_stage_write(key, data)) return false;
  invalidate_caches();
  return true;
}

bool write_sectors(u32 lba, const u8* data, u16 count) {
  if(data == NULL && count != 0) return false;
  for(u16 i = 0; i < count; i++) {
    if(!write_sector(lba + i, data + (u32) i * SECTOR_SIZE)) return false;
  }
  return true;
}

bool flush_pending(void) {
  if(!program_store::ready() || !ensure_session()) return false;
  if(program_store::vfat_stage_count() == 0) return true;
  g_last_error = NULL;
  memset(session().desired_kinds, 0, sizeof(session().desired_kinds));
  invalidate_caches();
  if(!walk_directory(program_store::ROOT_ID, true, 0, 0,
                     WalkPass::VALIDATE)) {
    if(g_last_error == NULL) g_last_error = "validate";
    return false;
  }
  if(!release_mismatched_extent_chains() || !prune_tree(program_store::ROOT_ID,
                                                        false)) {
    g_last_error = "prepare";
    return false;
  }
  invalidate_caches();
  if(!walk_directory(program_store::ROOT_ID, true, 0, 0,
                     WalkPass::APPLY)) {
    g_last_error = "apply";
    return false;
  }
  if(!prune_tree(program_store::ROOT_ID, true) ||
     !program_store::vfat_stage_discard_all()) {
    g_last_error = "commit";
    return false;
  }
  invalidate_caches();
  return ensure_all_directory_extents();
}

bool reset_session(void) {
  if(!program_store::ready() || !ensure_session()) return false;
  memset(g_session, 0, sizeof(*g_session));
  g_session->sector_cache_lba = INVALID_LBA;
  g_session->fat_cache_lba = INVALID_LBA;
  program_store::vfat_stage_clear();
  if(program_store::vfat_stage_count() == 0 && !ensure_all_directory_extents()) {
    return false;
  }
  invalidate_caches();
  return true;
}

void end_session(void) {
  g_session = NULL;
  g_session_lease.reset();
}

const char* trace_line_at(u16 index) {
  return index == 0 ? g_last_error : NULL;
}

} // namespace virtual_fat
