#include "program_store.hpp"

#include "Arduino.h"
#include "config.h"
#include "tools.hpp"

#ifdef SPI_FLASH
#include <SPIFlash.h>
#endif

#include <string.h>

#ifdef SPI_FLASH
extern SPIFlash flash;
#endif

namespace program_store {

static constexpr u8 STATE_WRITING = 0xFF;
static constexpr u8 STATE_ACTIVE  = 0x7F;
static constexpr u8 STATE_DELETED = 0x3F;

static constexpr u8 SECTOR_TAG0 = 'S';
static constexpr u8 SECTOR_TAG1 = '1';
static constexpr usize SECTOR_HEADER_SIZE = 7;
static constexpr usize STORE_SECTOR_COUNT = (usize) MAX_SLOT_FOR_PROGRAM + 1;
static constexpr u32 ERASE_TIMEOUT_MS = 5000;

struct SectorInfo {
  bool empty;
  bool active;
  bool foreign;
  u32 generation;
  u16 used;
  u16 live;
  u16 dead;
};

struct IndexEntry {
  bool used;
  ProgramType type;
  char name[NAME_SIZE];
  u32 address;
  u16 data_len;
  u16 total_len;
  u8 name_len;
};

struct RecordMeta {
  ProgramType type;
  u8 state;
  u8 name_len;
  u16 data_len;
  u16 crc;
  u16 header_len;
  u16 total_len;
};

static SectorInfo sectors[STORE_SECTOR_COUNT];
static IndexEntry index_entries[MAX_ENTRIES];
static u8 index_count;
static bool index_valid;
static u32 next_generation = 1;

static u32 sector_base(usize sector) {
  return (u32) sector * (u32) FLASH_SECTOR_SIZE;
}

static u8 read_byte(u32 address) {
#ifdef SPI_FLASH
  if(flash_is_ok) return flash.readByte(address);
#endif
  (void) address;
  return 0xFF;
}

static void write_byte(u32 address, u8 value) {
#ifdef SPI_FLASH
  if(flash_is_ok) flash.writeByte(address, value);
#else
  (void) address;
  (void) value;
#endif
}

static bool erase_sector(usize sector) {
#ifdef SPI_FLASH
  if(!flash_is_ok) return false;
  const u32 address = sector_base(sector);
  const u32 stop_at = millis() + ERASE_TIMEOUT_MS;
  while(!flash.eraseSector(address)) {
    if((i32) (millis() - stop_at) >= 0) return false;
  }
  return true;
#else
  (void) sector;
  return false;
#endif
}

static bool is_empty_sector(usize sector) {
  const u32 base = sector_base(sector);
  for(usize i = 0; i < FLASH_SECTOR_SIZE; i++) {
    if(read_byte(base + (u32) i) != 0xFF) return false;
  }
  return true;
}

static u16 read_le16(u32 address) {
  const u16 lo = read_byte(address);
  const u16 hi = read_byte(address + 1);
  return (u16) (lo | (hi << 8));
}

static u32 read_le32(u32 address) {
  const u32 b0 = read_byte(address);
  const u32 b1 = read_byte(address + 1);
  const u32 b2 = read_byte(address + 2);
  const u32 b3 = read_byte(address + 3);
  return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
}

static void write_le16(u32 address, u16 value) {
  write_byte(address, (u8) (value & 0xFF));
  write_byte(address + 1, (u8) (value >> 8));
}

static void write_le32(u32 address, u32 value) {
  write_byte(address, (u8) (value & 0xFF));
  write_byte(address + 1, (u8) ((value >> 8) & 0xFF));
  write_byte(address + 2, (u8) ((value >> 16) & 0xFF));
  write_byte(address + 3, (u8) ((value >> 24) & 0xFF));
}

static u16 crc16_update(u16 crc, u8 value) {
  crc ^= (u16) value << 8;
  for(u8 i = 0; i < 8; i++) {
    crc = (crc & 0x8000) ? (u16) ((crc << 1) ^ 0x1021) : (u16) (crc << 1);
  }
  return crc;
}

static ProgramType type_from_tag(u8 tag0, u8 tag1, bool& ok) {
  ok = tag1 == '1';
  if(!ok) return ProgramType::MK61;
  if(tag0 == 'M') return ProgramType::MK61;
  if(tag0 == 'B') return ProgramType::BASIC;
  if(tag0 == 'F') return ProgramType::FOCAL;
  ok = false;
  return ProgramType::MK61;
}

static u8 tag0_for_type(ProgramType type) {
  switch(type) {
    case ProgramType::MK61:  return 'M';
    case ProgramType::BASIC: return 'B';
    case ProgramType::FOCAL: return 'F';
  }
  return 'M';
}

static bool parse_record(u32 address, u16 sector_offset, RecordMeta& out, bool& empty) {
  empty = false;
  const u8 tag0 = read_byte(address);
  if(tag0 == 0xFF) {
    empty = true;
    return false;
  }

  const u8 tag1 = read_byte(address + 1);
  bool tag_ok = false;
  out.type = type_from_tag(tag0, tag1, tag_ok);
  if(!tag_ok) return false;

  out.state = read_byte(address + 2);
  out.name_len = read_byte(address + 3);
  if(out.name_len == 0 || out.name_len >= NAME_SIZE) return false;

  if(out.type == ProgramType::MK61) {
    out.data_len = read_byte(address + 4);
    out.crc = read_le16(address + 5);
    out.header_len = 7;
    if(out.data_len > core_61::MAX_PROGRAM_STEP) return false;
  } else {
    out.data_len = read_le16(address + 4);
    out.crc = read_le16(address + 6);
    out.header_len = 8;
  }

  out.total_len = (u16) (out.header_len + out.name_len + out.data_len);
  if(out.total_len < out.header_len) return false;
  if((usize) sector_offset + out.total_len > FLASH_SECTOR_SIZE) return false;
  return true;
}

static u16 record_crc(u32 address, const RecordMeta& meta) {
  u16 crc = 0xFFFF;
  crc = crc16_update(crc, read_byte(address));
  crc = crc16_update(crc, read_byte(address + 1));
  crc = crc16_update(crc, meta.name_len);
  if(meta.type == ProgramType::MK61) {
    crc = crc16_update(crc, (u8) meta.data_len);
  } else {
    crc = crc16_update(crc, (u8) (meta.data_len & 0xFF));
    crc = crc16_update(crc, (u8) (meta.data_len >> 8));
  }

  const u32 payload = address + meta.header_len;
  for(u16 i = 0; i < (u16) (meta.name_len + meta.data_len); i++) {
    crc = crc16_update(crc, read_byte(payload + i));
  }
  return crc;
}

static u16 make_crc(ProgramType type, const char* name, u8 name_len, const u8* data, u16 data_len) {
  u16 crc = 0xFFFF;
  crc = crc16_update(crc, tag0_for_type(type));
  crc = crc16_update(crc, '1');
  crc = crc16_update(crc, name_len);
  if(type == ProgramType::MK61) {
    crc = crc16_update(crc, (u8) data_len);
  } else {
    crc = crc16_update(crc, (u8) (data_len & 0xFF));
    crc = crc16_update(crc, (u8) (data_len >> 8));
  }
  for(u8 i = 0; i < name_len; i++) crc = crc16_update(crc, (u8) name[i]);
  for(u16 i = 0; i < data_len; i++) crc = crc16_update(crc, data[i]);
  return crc;
}

static bool read_name(u32 address, const RecordMeta& meta, char* out) {
  if(meta.name_len == 0 || meta.name_len >= NAME_SIZE) return false;
  const u32 name_addr = address + meta.header_len;
  for(u8 i = 0; i < meta.name_len; i++) out[i] = (char) read_byte(name_addr + i);
  out[meta.name_len] = 0;
  return true;
}

static bool same_key(ProgramType type, const char* a, ProgramType other_type, const char* b) {
  if(type != other_type) return false;
  return strncmp(a, b, NAME_SIZE) == 0;
}

static int find_index(ProgramType type, const char* name) {
  for(u8 i = 0; i < index_count; i++) {
    if(index_entries[i].used && same_key(type, name, index_entries[i].type, index_entries[i].name)) return i;
  }
  return -1;
}

static void update_index(const RecordMeta& meta, const char* name, u32 address) {
  int idx = find_index(meta.type, name);
  if(idx < 0) {
    if(index_count >= MAX_ENTRIES) return;
    idx = index_count++;
  }

  IndexEntry& entry = index_entries[idx];
  entry.used = true;
  entry.type = meta.type;
  strncpy(entry.name, name, NAME_SIZE - 1);
  entry.name[NAME_SIZE - 1] = 0;
  entry.address = address;
  entry.data_len = meta.data_len;
  entry.total_len = meta.total_len;
  entry.name_len = meta.name_len;
}

static void scan_sector_header(usize sector) {
  SectorInfo& info = sectors[sector];
  memset(&info, 0, sizeof(info));

  const u32 base = sector_base(sector);
  if(read_byte(base) == SECTOR_TAG0 && read_byte(base + 1) == SECTOR_TAG1 && read_byte(base + 2) == STATE_ACTIVE) {
    info.active = true;
    info.generation = read_le32(base + 3);
    info.used = SECTOR_HEADER_SIZE;
    return;
  }

  if(is_empty_sector(sector)) {
    info.empty = true;
    info.used = 0;
    return;
  }

  info.foreign = true;
  info.used = FLASH_SECTOR_SIZE;
  info.dead = FLASH_SECTOR_SIZE;
}

static int next_sector_by_generation(bool processed[STORE_SECTOR_COUNT]) {
  int best = -1;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(processed[i] || !sectors[i].active) continue;
    if(best < 0 || sectors[i].generation < sectors[best].generation) best = (int) i;
  }
  return best;
}

static bool record_is_latest(u32 address, const RecordMeta& meta, const char* name) {
  const int idx = find_index(meta.type, name);
  return idx >= 0 && index_entries[idx].address == address;
}

static void scan_records_for_index(usize sector) {
  SectorInfo& info = sectors[sector];
  if(!info.active) return;

  u16 offset = SECTOR_HEADER_SIZE;
  while(offset < FLASH_SECTOR_SIZE) {
    RecordMeta meta;
    bool empty = false;
    const u32 address = sector_base(sector) + offset;
    if(!parse_record(address, offset, meta, empty)) {
      info.used = empty ? offset : FLASH_SECTOR_SIZE;
      return;
    }

    if(meta.state == STATE_ACTIVE && record_crc(address, meta) == meta.crc) {
      char name[NAME_SIZE];
      if(read_name(address, meta, name)) update_index(meta, name, address);
    }
    offset = (u16) (offset + meta.total_len);
  }
  info.used = FLASH_SECTOR_SIZE;
}

static void scan_records_for_stats(usize sector) {
  SectorInfo& info = sectors[sector];
  info.live = 0;
  info.dead = 0;
  if(!info.active) return;

  u16 offset = SECTOR_HEADER_SIZE;
  while(offset < info.used) {
    RecordMeta meta;
    bool empty = false;
    const u32 address = sector_base(sector) + offset;
    if(!parse_record(address, offset, meta, empty)) {
      info.dead = (u16) (info.dead + (info.used - offset));
      return;
    }

    bool live = false;
    if(meta.state == STATE_ACTIVE && record_crc(address, meta) == meta.crc) {
      char name[NAME_SIZE];
      live = read_name(address, meta, name) && record_is_latest(address, meta, name);
    }

    if(live) info.live = (u16) (info.live + meta.total_len);
    else info.dead = (u16) (info.dead + meta.total_len);
    offset = (u16) (offset + meta.total_len);
  }
}

bool refresh(void) {
  memset(sectors, 0, sizeof(sectors));
  memset(index_entries, 0, sizeof(index_entries));
  index_count = 0;
  next_generation = 1;

#ifdef SPI_FLASH
  if(!flash_is_ok) {
    index_valid = true;
    return false;
  }
#else
  index_valid = true;
  return false;
#endif

  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    scan_sector_header(i);
    if(sectors[i].active && sectors[i].generation >= next_generation) {
      next_generation = sectors[i].generation + 1;
      if(next_generation == 0) next_generation = 1;
    }
  }

  bool processed[STORE_SECTOR_COUNT];
  memset(processed, 0, sizeof(processed));
  while(true) {
    const int sector = next_sector_by_generation(processed);
    if(sector < 0) break;
    processed[sector] = true;
    scan_records_for_index((usize) sector);
  }

  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) scan_records_for_stats(i);
  index_valid = true;
  return true;
}

void init(void) {
  index_valid = false;
  refresh();
}

static bool ensure_index(void) {
  return index_valid ? true : refresh();
}

bool format(void) {
#ifdef SPI_FLASH
  if(!flash_is_ok) return false;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(!erase_sector(i)) return false;
  }
  index_valid = false;
  return refresh();
#else
  return false;
#endif
}

static int empty_sector(void) {
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(sectors[i].empty) return (int) i;
  }
  return -1;
}

static int foreign_sector(void) {
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(sectors[i].foreign) return (int) i;
  }
  return -1;
}

static int empty_sector_count(void) {
  int count = 0;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(sectors[i].empty) count++;
  }
  return count;
}

static int current_sector(void) {
  int best = -1;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(!sectors[i].active) continue;
    if(best < 0 || sectors[i].generation > sectors[best].generation) best = (int) i;
  }
  return best;
}

static bool open_sector(usize sector) {
  const u32 base = sector_base(sector);
  write_byte(base, SECTOR_TAG0);
  write_byte(base + 1, SECTOR_TAG1);
  write_byte(base + 2, STATE_WRITING);
  write_le32(base + 3, next_generation++);
  if(next_generation == 0) next_generation = 1;
  write_byte(base + 2, STATE_ACTIVE);
  index_valid = false;
  return refresh();
}

static bool prepare_empty_sector(void) {
  int sector = empty_sector();
  if(sector >= 0) return true;

  sector = foreign_sector();
  if(sector < 0) return false;
  if(!erase_sector((usize) sector)) return false;
  index_valid = false;
  return refresh();
}

static bool copy_live_records(usize victim, usize destination, u16& dest_used) {
  u16 offset = SECTOR_HEADER_SIZE;
  while(offset < sectors[victim].used) {
    RecordMeta meta;
    bool empty = false;
    const u32 src = sector_base(victim) + offset;
    if(!parse_record(src, offset, meta, empty)) return true;

    bool copy = false;
    if(meta.state == STATE_ACTIVE && record_crc(src, meta) == meta.crc) {
      char name[NAME_SIZE];
      copy = read_name(src, meta, name) && record_is_latest(src, meta, name);
    }

    if(copy) {
      if((usize) dest_used + meta.total_len > FLASH_SECTOR_SIZE) return false;
      const u32 dst = sector_base(destination) + dest_used;
      write_byte(dst, read_byte(src));
      write_byte(dst + 1, read_byte(src + 1));
      write_byte(dst + 2, STATE_WRITING);
      for(u16 i = 3; i < meta.total_len; i++) write_byte(dst + i, read_byte(src + i));
      write_byte(dst + 2, STATE_ACTIVE);
      dest_used = (u16) (dest_used + meta.total_len);
    }

    offset = (u16) (offset + meta.total_len);
  }
  return true;
}

static bool garbage_collect(u16 min_free) {
  if(!prepare_empty_sector()) return false;
  const int empty = empty_sector();
  if(empty < 0) return false;

  int victim = -1;
  u16 best_live = 0xFFFF;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(!sectors[i].active) continue;
    const u16 free_after = (u16) (FLASH_SECTOR_SIZE - SECTOR_HEADER_SIZE - sectors[i].live);
    if(free_after < min_free) continue;
    if(victim < 0 || sectors[i].live < best_live) {
      victim = (int) i;
      best_live = sectors[i].live;
    }
  }
  if(victim < 0) return false;

  if(!open_sector((usize) empty)) return false;
  u16 dest_used = SECTOR_HEADER_SIZE;
  if(!copy_live_records((usize) victim, (usize) empty, dest_used)) return false;
  if(!erase_sector((usize) victim)) return false;
  index_valid = false;
  return refresh();
}

static bool ensure_space(u16 record_len) {
  if(!ensure_index()) return false;
  if(record_len > FLASH_SECTOR_SIZE - SECTOR_HEADER_SIZE) return false;

  int current = current_sector();
  if(current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE) return true;

  if(empty_sector_count() >= 2) {
    const int empty = empty_sector();
    if(empty < 0 || !open_sector((usize) empty)) return false;
    current = current_sector();
    return current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE;
  }

  if(garbage_collect(record_len)) {
    current = current_sector();
    return current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE;
  }

  if(current < 0 && prepare_empty_sector()) {
    const int empty = empty_sector();
    if(empty >= 0 && open_sector((usize) empty)) return true;
  }

  return false;
}

static u8 name_len_of(const char* name) {
  if(name == NULL) return 0;
  u8 len = 0;
  while(len < NAME_SIZE - 1 && name[len] != 0) len++;
  return len;
}

static bool valid_write(ProgramType type, const char* name, u16 data_len) {
  const u8 nlen = name_len_of(name);
  if(nlen == 0 || nlen >= NAME_SIZE) return false;
  if(type == ProgramType::MK61 && data_len > core_61::MAX_PROGRAM_STEP) return false;
  return true;
}

static void mark_deleted_at(u32 address) {
  write_byte(address + 2, STATE_DELETED);
}

static void mark_all_deleted(ProgramType type, const char* name, u32 keep_address = 0xFFFFFFFFUL) {
  for(usize sector = 0; sector < STORE_SECTOR_COUNT; sector++) {
    if(!sectors[sector].active) continue;
    u16 offset = SECTOR_HEADER_SIZE;
    while(offset < sectors[sector].used) {
      RecordMeta meta;
      bool empty = false;
      const u32 address = sector_base(sector) + offset;
      if(!parse_record(address, offset, meta, empty)) break;
      if(address == keep_address) {
        offset = (u16) (offset + meta.total_len);
        continue;
      }
      if(meta.state == STATE_ACTIVE && meta.type == type && record_crc(address, meta) == meta.crc) {
        char record_name[NAME_SIZE];
        if(read_name(address, meta, record_name) && strncmp(record_name, name, NAME_SIZE) == 0) mark_deleted_at(address);
      }
      offset = (u16) (offset + meta.total_len);
    }
  }
  index_valid = false;
}

bool write(ProgramType type, const char* name, const u8* data, u16 data_len) {
  if(data == NULL && data_len != 0) return false;
  if(!valid_write(type, name, data_len)) return false;

  const u8 nlen = name_len_of(name);
  const u16 header_len = (type == ProgramType::MK61) ? 7 : 8;
  const u16 record_len = (u16) (header_len + nlen + data_len);
  if(!ensure_space(record_len)) return false;

  const int sector = current_sector();
  if(sector < 0) return false;
  const u32 address = sector_base((usize) sector) + sectors[sector].used;
  const u16 crc = make_crc(type, name, nlen, data, data_len);

  write_byte(address, tag0_for_type(type));
  write_byte(address + 1, '1');
  write_byte(address + 2, STATE_WRITING);
  write_byte(address + 3, nlen);
  if(type == ProgramType::MK61) {
    write_byte(address + 4, (u8) data_len);
    write_le16(address + 5, crc);
  } else {
    write_le16(address + 4, data_len);
    write_le16(address + 6, crc);
  }

  u32 pos = address + header_len;
  for(u8 i = 0; i < nlen; i++) write_byte(pos++, (u8) name[i]);
  for(u16 i = 0; i < data_len; i++) write_byte(pos++, data[i]);
  write_byte(address + 2, STATE_ACTIVE);

  if(ensure_index()) mark_all_deleted(type, name, address);
  index_valid = false;
  return refresh();
}

bool read(ProgramType type, const char* name, u8* data, u16 capacity, u16* out_len) {
  if(out_len != NULL) *out_len = 0;
  if(data == NULL && capacity != 0) return false;
  if(!ensure_index()) return false;
  const int idx = find_index(type, name);
  if(idx < 0) return false;
  const IndexEntry& entry = index_entries[idx];
  if(entry.data_len > capacity) return false;

  const u32 payload = entry.address + ((entry.type == ProgramType::MK61) ? 7 : 8) + entry.name_len;
  for(u16 i = 0; i < entry.data_len; i++) data[i] = read_byte(payload + i);
  if(out_len != NULL) *out_len = entry.data_len;
  return true;
}

bool remove(ProgramType type, const char* name) {
  if(!ensure_index()) return false;
  if(find_index(type, name) < 0) return false;
  mark_all_deleted(type, name);
  return refresh();
}

bool rename(ProgramType type, const char* old_name, const char* new_name) {
  if(old_name == NULL || new_name == NULL || old_name[0] == 0 || new_name[0] == 0) return false;
  u8 buffer[core_61::MAX_PROGRAM_STEP > 700 ? core_61::MAX_PROGRAM_STEP : 700];
  u16 len = 0;
  if(type == ProgramType::MK61) {
    if(!read(type, old_name, buffer, core_61::MAX_PROGRAM_STEP, &len)) return false;
  } else {
    if(!read(type, old_name, buffer, sizeof(buffer), &len)) return false;
  }
  if(!write(type, new_name, buffer, len)) return false;
  remove(type, old_name);
  return true;
}

int count(ProgramType type) {
  if(!ensure_index()) return 0;
  int result = 0;
  for(u8 i = 0; i < index_count; i++) {
    if(index_entries[i].used && index_entries[i].type == type) result++;
  }
  return result;
}

bool entry(ProgramType type, int index, Entry& out) {
  if(!ensure_index() || index < 0) return false;
  int seen = 0;
  for(u8 i = 0; i < index_count; i++) {
    if(!index_entries[i].used || index_entries[i].type != type) continue;
    if(seen++ != index) continue;
    out.type = index_entries[i].type;
    strncpy(out.name, index_entries[i].name, NAME_SIZE - 1);
    out.name[NAME_SIZE - 1] = 0;
    out.data_len = index_entries[i].data_len;
    return true;
  }
  return false;
}

bool exists(ProgramType type, const char* name) {
  if(!ensure_index()) return false;
  return find_index(type, name) >= 0;
}

bool write_mk61(const char* name, const u8* code, u8 code_len) {
  return write(ProgramType::MK61, name, code, code_len);
}

bool read_mk61(const char* name, u8* code, u8 capacity, u8* out_len) {
  u16 len = 0;
  if(!read(ProgramType::MK61, name, code, capacity, &len)) return false;
  if(out_len != NULL) *out_len = (u8) len;
  return true;
}

} // namespace program_store
