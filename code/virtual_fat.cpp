#include "virtual_fat.hpp"

#include "program_store.hpp"

#include <string.h>

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
static constexpr u16 MAX_IMPORTED_LEN = 640;
static constexpr u16 MAX_LFN_CHARS = program_store::NAME_SIZE + 3;
static constexpr u8 MAX_PENDING_WRITES = 3;
static constexpr u8 WRITE_CACHE_SECTORS = 6;
static constexpr u8 FAT_ATTR_VOLUME = 0x08;
static constexpr u8 FAT_ATTR_DIRECTORY = 0x10;
static constexpr u8 FAT_ATTR_ARCHIVE = 0x20;
static constexpr u8 FAT_ATTR_LFN = 0x0F;

static const program_store::ProgramType FILE_TYPES[] = {
  program_store::ProgramType::MK61,
  program_store::ProgramType::BASIC,
  program_store::ProgramType::FOCAL
};

struct PendingWrite {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u16 start_cluster;
  u16 data_len;
  u8 sectors_seen;
  u8 data[MAX_IMPORTED_LEN];
};

struct CachedSector {
  bool used;
  u16 cluster;
  u8 data[SECTOR_SIZE];
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
static CachedSector write_cache[WRITE_CACHE_SECTORS];
static LfnState root_lfn_state;
static u8 next_cache_slot = 0;

static u16 clusters_for_len(u16 len) {
  const u16 clusters = (u16) ((len + SECTOR_SIZE - 1) / SECTOR_SIZE);
  return (clusters == 0) ? 1 : clusters;
}

static int file_count(void) {
  int count = 0;
  for(program_store::ProgramType type : FILE_TYPES) count += program_store::count(type);
  const int max_files = ROOT_ENTRIES - 1;
  return (count > max_files) ? max_files : count;
}

static bool file_entry(int flat_index, program_store::Entry& out) {
  if(flat_index < 0) return false;

  int base = 0;
  for(program_store::ProgramType type : FILE_TYPES) {
    const int count = program_store::count(type);
    if(flat_index < base + count) return program_store::entry(type, flat_index - base, out);
    base += count;
  }

  return false;
}

static u16 data_cluster_count(void) {
  u16 clusters = 0;
  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(file_entry(i, entry)) clusters = (u16) (clusters + clusters_for_len(entry.data_len));
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

static bool cluster_info(u16 cluster, program_store::Entry& out, u16& start_cluster) {
  if(cluster < FIRST_DATA_CLUSTER) return false;

  u16 current = FIRST_DATA_CLUSTER;
  const int count = file_count();
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!file_entry(i, entry)) continue;
    const u16 used = clusters_for_len(entry.data_len);
    if(cluster >= current && cluster < (u16) (current + used)) {
      out = entry;
      start_cluster = current;
      return true;
    }
    current = (u16) (current + used);
  }

  return false;
}

static PendingWrite* pending_for_cluster(u16 cluster) {
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used || pending.start_cluster < FIRST_DATA_CLUSTER) continue;
    const u16 clusters = clusters_for_len(pending.data_len);
    if(cluster >= pending.start_cluster && cluster < (u16) (pending.start_cluster + clusters)) return &pending;
  }
  return NULL;
}

static u16 fat_value(u16 cluster) {
  if(cluster == 0) return (u16) (0xFF0 | MEDIA_DESCRIPTOR);
  if(cluster == 1) return CLUSTER_EOF;

  program_store::Entry entry;
  u16 start_cluster = 0;
  if(!cluster_info(cluster, entry, start_cluster)) return CLUSTER_FREE;

  const u16 offset = (u16) (cluster - start_cluster);
  const u16 used = clusters_for_len(entry.data_len);
  return (offset + 1 >= used) ? CLUSTER_EOF : (u16) (cluster + 1);
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
    PendingWrite* pending = pending_for_cluster(cluster);
    if(pending != NULL) {
      const u16 offset = (u16) (cluster - pending->start_cluster);
      const u16 used = clusters_for_len(pending->data_len);
      const u16 value = (offset + 1 >= used) ? CLUSTER_EOF : (u16) (cluster + 1);
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

static void fill_83_name(const program_store::Entry& entry, int flat_index, u8* out) {
  memset(out, ' ', 11);
  u8 pos = 0;
  for(u8 i = 0; entry.name[i] != 0 && pos < 8; i++) {
    const char c = safe_name_char(entry.name[i]);
    if(c != 0) out[pos++] = (u8) c;
  }

  if(pos == 0) {
    out[0] = 'P';
    out[1] = (u8) ('0' + ((flat_index / 100) % 10));
    out[2] = (u8) ('0' + ((flat_index / 10) % 10));
    out[3] = (u8) ('0' + (flat_index % 10));
  }

  memcpy(out + 8, extension_for_type(entry.type), 3);
}

static void format_full_name(program_store::ProgramType type, const char* name, char* out) {
  u8 pos = 0;
  while(name[pos] != 0 && pos < program_store::NAME_SIZE - 1) {
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

static bool needs_lfn(const char* name) {
  u8 len = 0;
  while(name[len] != 0 && len < program_store::NAME_SIZE) len++;
  return len > 8;
}

static u8 lfn_count_for_name(const char* full_name) {
  u8 len = 0;
  while(full_name[len] != 0 && len < MAX_LFN_CHARS) len++;
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
  while(full_name[len] != 0 && len < MAX_LFN_CHARS) len++;

  const u8 base = (u8) ((sequence - 1) * 13);
  for(u8 i = 0; i < 13; i++) {
    const u8 index = (u8) (base + i);
    u16 value = 0xFFFF;
    if(index < len) value = (u8) full_name[index];
    else if(index == len) value = 0x0000;
    put_lfn_char(out, i, value);
  }
}

static u16 start_cluster_for_file(int flat_index) {
  u16 cluster = FIRST_DATA_CLUSTER;
  for(int i = 0; i < flat_index; i++) {
    program_store::Entry entry;
    if(file_entry(i, entry)) cluster = (u16) (cluster + clusters_for_len(entry.data_len));
  }
  return cluster;
}

static void fill_dir_entry(u8* out, const program_store::Entry& entry, int flat_index) {
  fill_83_name(entry, flat_index, out);
  out[11] = FAT_ATTR_ARCHIVE;
  put_le16(out, 22, 0);
  put_le16(out, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 6));
  put_le16(out, 26, start_cluster_for_file(flat_index));
  put_le32(out, 28, entry.data_len);
}

static void fill_pending_name(const PendingWrite& pending, u8* out) {
  memset(out, ' ', 11);
  u8 pos = 0;
  while(pending.name[pos] != 0 && pos < 8) {
    out[pos] = (u8) pending.name[pos];
    pos++;
  }

  memcpy(out + 8, extension_for_type(pending.type), 3);
}

static bool pending_visible(const PendingWrite& pending) {
  return pending.used && pending.name[0] != 0;
}

static PendingWrite* pending_entry(int index) {
  int seen = 0;
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    if(!pending_visible(pending_writes[i])) continue;
    if(seen++ == index) return &pending_writes[i];
  }
  return NULL;
}

static void fill_pending_dir_entry(u8* out, const PendingWrite& pending) {
  fill_pending_name(pending, out);
  out[11] = FAT_ATTR_ARCHIVE;
  put_le16(out, 22, 0);
  put_le16(out, 24, (u16) (((2026 - 1980) << 9) | (7 << 5) | 6));
  put_le16(out, 26, pending.start_cluster);
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

static void render_pending_dir_entry(u8* out, const PendingWrite& pending, u8 offset) {
  const u8 entries = dir_entries_for_name(pending.name, pending.type);
  if(entries == 1 || offset + 1 == entries) {
    fill_pending_dir_entry(out, pending);
    return;
  }

  char full_name[MAX_LFN_CHARS + 1];
  u8 short_name[11];
  format_full_name(pending.type, pending.name, full_name);
  fill_pending_name(pending, short_name);
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

    int cursor = 1;
    bool rendered = false;
    for(int file_index = 0; file_index < committed_files; file_index++) {
      program_store::Entry entry;
      if(!file_entry(file_index, entry)) continue;
      const u8 entries = dir_entries_for_name(entry.name, entry.type);
      if(dir_index >= cursor && dir_index < cursor + entries) {
        render_committed_dir_entry(item, entry, file_index, (u8) (dir_index - cursor));
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
        render_pending_dir_entry(item, pending, (u8) (dir_index - cursor));
        break;
      }
      cursor += entries;
    }
  }
}

static CachedSector* cached_sector(u16 cluster) {
  for(u8 i = 0; i < WRITE_CACHE_SECTORS; i++) {
    if(write_cache[i].used && write_cache[i].cluster == cluster) return &write_cache[i];
  }
  return NULL;
}

static bool read_data_sector(u32 data_sector, u8* out) {
  memset(out, 0, SECTOR_SIZE);
  const u16 cluster = (u16) (data_sector + FIRST_DATA_CLUSTER);

  CachedSector* cached = cached_sector(cluster);
  if(cached != NULL) {
    memcpy(out, cached->data, SECTOR_SIZE);
    return true;
  }

  program_store::Entry entry;
  u16 start_cluster = 0;
  if(!cluster_info(cluster, entry, start_cluster)) return true;

  const u16 file_offset = (u16) ((cluster - start_cluster) * SECTOR_SIZE);
  u16 copied = 0;
  if(!program_store::read_range(entry.type, entry.name, file_offset, out, SECTOR_SIZE, &copied)) return false;
  if(copied < SECTOR_SIZE) memset(out + copied, 0, SECTOR_SIZE - copied);
  return true;
}

static u16 max_len_for_type(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61:  return core_61::MAX_PROGRAM_STEP;
    case program_store::ProgramType::BASIC: return 511;
    case program_store::ProgramType::FOCAL: return 639;
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
  if(c >= 'a' && c <= 'z') c = (char) (c - 'a' + 'A');
  if((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-') return c;
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
  return false;
}

static bool parse_lfn_filename(const char* full_name, ParsedDirEntry& parsed) {
  int dot = -1;
  int len = 0;
  while(full_name[len] != 0 && len <= (int) MAX_LFN_CHARS) {
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
  if(parsed.data_len != 0 && parsed.start_cluster < FIRST_DATA_CLUSTER) return false;
  return true;
}

static bool committed_short_entry_at_dir_index(int dir_index, program_store::Entry& entry, int& flat_index) {
  int cursor = 1;
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

static bool generated_dir_entry_matches(int dir_index, const u8* item) {
  program_store::Entry entry;
  int file_index = 0;
  if(!committed_short_entry_at_dir_index(dir_index, entry, file_index)) return false;

  u8 name[11];
  fill_83_name(entry, file_index, name);
  if(memcmp(name, item, 11) != 0) return false;
  if(get_le16(item, 26) != start_cluster_for_file(file_index)) return false;
  return get_le32(item, 28) == entry.data_len;
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
  return &pending_writes[0];
}

static bool pending_has_all_data(const PendingWrite& pending) {
  if(pending.data_len == 0) return true;
  const u16 sectors = clusters_for_len(pending.data_len);
  for(u16 i = 0; i < sectors; i++) {
    if((pending.sectors_seen & (1U << i)) == 0) return false;
  }
  return true;
}

static bool try_commit_pending(PendingWrite& pending) {
  if(!pending.used || !pending_has_all_data(pending)) return true;
  if(!program_store::write(pending.type, pending.name, pending.data, pending.data_len)) return false;
  memset(&pending, 0, sizeof(pending));
  return true;
}

static void seed_pending_from_cache(PendingWrite& pending) {
  if(pending.data_len == 0 || pending.start_cluster < FIRST_DATA_CLUSTER) return;

  const u16 clusters = clusters_for_len(pending.data_len);
  for(u16 i = 0; i < clusters; i++) {
    CachedSector* cached = cached_sector((u16) (pending.start_cluster + i));
    if(cached == NULL) continue;
    const u16 offset = (u16) (i * SECTOR_SIZE);
    const u16 remaining = (pending.data_len > offset) ? (u16) (pending.data_len - offset) : 0;
    const u16 copy_len = (remaining > SECTOR_SIZE) ? SECTOR_SIZE : remaining;
    if(copy_len != 0) memcpy(pending.data + offset, cached->data, copy_len);
    pending.sectors_seen = (u8) (pending.sectors_seen | (1U << i));
  }
}

bool flush_pending(void) {
  bool ok = true;
  for(u8 i = 0; i < MAX_PENDING_WRITES; i++) {
    PendingWrite& pending = pending_writes[i];
    if(!pending.used) continue;
    seed_pending_from_cache(pending);
    if(!pending_has_all_data(pending)) continue;
    if(!try_commit_pending(pending)) ok = false;
  }
  return ok;
}

static bool upsert_pending(const ParsedDirEntry& parsed) {
  PendingWrite* pending = find_pending(parsed.type, parsed.name);
  if(pending == NULL) pending = allocate_pending();

  memset(pending, 0, sizeof(*pending));
  pending->used = true;
  pending->type = parsed.type;
  strncpy(pending->name, parsed.name, program_store::NAME_SIZE - 1);
  pending->name[program_store::NAME_SIZE - 1] = 0;
  pending->start_cluster = parsed.start_cluster;
  pending->data_len = parsed.data_len;
  seed_pending_from_cache(*pending);
  return try_commit_pending(*pending);
}

static void remove_existing_dir_slot(int dir_index) {
  program_store::Entry entry;
  int file_index = 0;
  if(committed_short_entry_at_dir_index(dir_index, entry, file_index)) (void) program_store::remove(entry.type, entry.name);
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
  if(root_sector == 0) reset_lfn_state(lfn);

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
      remove_existing_dir_slot(dir_index);
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
      reset_lfn_state(lfn);
      continue;
    }
    if(has_lfn && lfn_name == NULL) {
      reset_lfn_state(lfn);
      continue;
    }
    if(generated_dir_entry_matches(dir_index, item)) {
      reset_lfn_state(lfn);
      continue;
    }

    ParsedDirEntry parsed;
    const bool parsed_ok = parse_dir_entry(item, lfn_name, parsed);
    reset_lfn_state(lfn);
    if(!parsed_ok) continue;
    if(!upsert_pending(parsed)) return false;
  }

  return true;
}

static void cache_data_sector(u16 cluster, const u8* data) {
  CachedSector* cached = cached_sector(cluster);
  if(cached == NULL) {
    cached = &write_cache[next_cache_slot];
    next_cache_slot = (u8) ((next_cache_slot + 1) % WRITE_CACHE_SECTORS);
  }
  cached->used = true;
  cached->cluster = cluster;
  memcpy(cached->data, data, SECTOR_SIZE);
}

static bool write_data_sector(u32 data_sector, const u8* data) {
  const u16 cluster = (u16) (data_sector + FIRST_DATA_CLUSTER);
  cache_data_sector(cluster, data);

  PendingWrite* pending = pending_for_cluster(cluster);
  if(pending == NULL) return true;

  const u16 sector_index = (u16) (cluster - pending->start_cluster);
  if(sector_index >= 8) return true;
  const u16 offset = (u16) (sector_index * SECTOR_SIZE);
  const u16 remaining = (pending->data_len > offset) ? (u16) (pending->data_len - offset) : 0;
  const u16 copy_len = (remaining > SECTOR_SIZE) ? SECTOR_SIZE : remaining;
  if(copy_len != 0) memcpy(pending->data + offset, data, copy_len);
  pending->sectors_seen = (u8) (pending->sectors_seen | (1U << sector_index));
  return try_commit_pending(*pending);
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

  if(lba < root_start) return true;
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
