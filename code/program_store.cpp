#include "program_store.hpp"

#include "Arduino.h"
#include "config.h"
#include "ledcontrol.h"
#include "shared_scratch.hpp"
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
static constexpr usize CATALOG_SECTOR = STORE_SECTOR_COUNT;
static constexpr usize SETTINGS_SECTOR = STORE_SECTOR_COUNT + 1;
static constexpr usize VFAT_STAGE_FIRST_SECTOR = SETTINGS_SECTOR + 1;
static constexpr usize VFAT_STAGE_SECTOR_COUNT = 128;
static constexpr u16 VFAT_STAGE_FIRST_CLUSTER = 2;
static constexpr u16 VFAT_STAGE_CLUSTER_COUNT = 800;
static constexpr u16 VFAT_STAGE_DATA_SIZE = 512;
static constexpr u16 VFAT_STAGE_HEADER_SIZE = 8;
static constexpr u16 VFAT_STAGE_RECORD_SIZE = VFAT_STAGE_HEADER_SIZE + VFAT_STAGE_DATA_SIZE;
static constexpr u8 VFAT_STAGE_RECORDS_PER_SECTOR = FLASH_SECTOR_SIZE / VFAT_STAGE_RECORD_SIZE;
static constexpr u8 VFAT_STAGE_TAG0 = 'V';
static constexpr u8 VFAT_STAGE_TAG1 = 'S';
static constexpr u8 CATALOG_TAG0 = 'C';
static constexpr u8 CATALOG_TAG1 = '1';
static constexpr usize CATALOG_HEADER_SIZE = 9;
static constexpr usize CATALOG_SECTOR_INFO_SIZE = 9;
static constexpr usize CATALOG_ENTRY_SIZE = 25;
static constexpr u32 ERASE_TIMEOUT_MS = 5000;
static constexpr t_time_ms DISK_LED_ON_MS = 35;
static constexpr t_time_ms DISK_LED_OFF_MS = 35;

static constexpr u8 SECTOR_FLAG_EMPTY = 0x01;
static constexpr u8 SECTOR_FLAG_ACTIVE = 0x02;
static constexpr u8 SECTOR_FLAG_FOREIGN = 0x04;

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
static u16 vfat_stage_refs[VFAT_STAGE_CLUSTER_COUNT];
static bool vfat_stage_sector_prepared[VFAT_STAGE_SECTOR_COUNT];
static u8 index_count;
static bool index_valid;
static u32 next_generation = 1;
static u8 disk_activity_depth;
static u8 disk_led_poll_divider;
static u16 vfat_stage_active_count;
static u16 vfat_stage_offset;
static u8 vfat_stage_sector;

static void disk_led_poll(void) {
  if(disk_activity_depth == 0) return;
  disk_led_poll_divider++;
  if((disk_led_poll_divider & 0x0F) == 0) led::control();
}

class DiskActivity {
  public:
    DiskActivity(void) {
      if(disk_activity_depth++ == 0) {
        disk_led_poll_divider = 0;
        led::blink_continuous(DISK_LED_ON_MS, DISK_LED_OFF_MS);
      }
    }

    ~DiskActivity(void) {
      if(disk_activity_depth == 0) return;
      disk_activity_depth--;
      if(disk_activity_depth == 0) led::blink_stop();
    }
};

static u32 sector_base(usize sector) {
  return (u32) sector * (u32) FLASH_SECTOR_SIZE;
}

static u8 read_byte(u32 address) {
#ifdef SPI_FLASH
  if(flash_is_ok) {
    const u8 value = flash.readByte(address);
    disk_led_poll();
    return value;
  }
#endif
  (void) address;
  return 0xFF;
}

static void write_byte(u32 address, u8 value) {
#ifdef SPI_FLASH
  if(flash_is_ok) {
    flash.writeByte(address, value);
    disk_led_poll();
  }
#else
  (void) address;
  (void) value;
#endif
}

// Byte-at-a-time flash access costs a full SPI transaction (busy poll, command,
// 3 address bytes) per byte, which made every VFAT sector ~500 transactions and
// dominated USB disk mount time. Bulk transfers do the same work in one go.
static void read_bytes(u32 address, u8* out, usize len) {
  if(len == 0) return;
#ifdef SPI_FLASH
  if(flash_is_ok) {
    if(flash.readByteArray(address, out, len)) {
      disk_led_poll();
      return;
    }
  }
#endif
  (void) address;
  memset(out, 0xFF, len);
}

static void write_bytes(u32 address, const u8* data, usize len) {
  if(len == 0) return;
#ifdef SPI_FLASH
  if(flash_is_ok) {
    flash.writeByteArray(address, (uint8_t*) data, len);
    disk_led_poll();
  }
#else
  (void) address;
  (void) data;
#endif
}

static bool erase_sector(usize sector) {
#ifdef SPI_FLASH
  if(!flash_is_ok) return false;
  const u32 address = sector_base(sector);
  const u32 stop_at = millis() + ERASE_TIMEOUT_MS;
  while(!flash.eraseSector(address)) {
    led::control();
    if((i32) (millis() - stop_at) >= 0) return false;
  }
  led::control();
  return true;
#else
  (void) sector;
  return false;
#endif
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

static int sector_from_address(u32 address) {
  const usize sector = (usize) (address / FLASH_SECTOR_SIZE);
  return (sector < STORE_SECTOR_COUNT) ? (int) sector : -1;
}

static u16 offset_in_sector(u32 address) {
  return (u16) (address % FLASH_SECTOR_SIZE);
}

static u16 crc16_update(u16 crc, u8 value) {
  crc ^= (u16) value << 8;
  for(u8 i = 0; i < 8; i++) {
    crc = (crc & 0x8000) ? (u16) ((crc << 1) ^ 0x1021) : (u16) (crc << 1);
  }
  return crc;
}

static ProgramType type_from_tag(u8 tag0, u8 tag1, bool& ok) {
  ok = true;
  if(tag0 == 'M' && tag1 == '1') return ProgramType::MK61;
  if(tag0 == 'B' && tag1 == '1') return ProgramType::BASIC;
  if(tag0 == 'F' && tag1 == '1') return ProgramType::FOCAL;
  if(tag0 == 'B' && tag1 == '2') return ProgramType::TINYBASIC;
  if(tag0 == 'T' && tag1 == '1') return ProgramType::TEXT;
  if(tag0 == 'M' && tag1 == '2') return ProgramType::MK61_STATE;
  ok = false;
  return ProgramType::MK61;
}

static u8 tag0_for_type(ProgramType type) {
  switch(type) {
    case ProgramType::MK61:  return 'M';
    case ProgramType::BASIC: return 'B';
    case ProgramType::FOCAL: return 'F';
    case ProgramType::TINYBASIC: return 'B';
    case ProgramType::TEXT: return 'T';
    case ProgramType::MK61_STATE: return 'M';
  }
  return 'M';
}

static u8 tag1_for_type(ProgramType type) {
  switch(type) {
    case ProgramType::MK61:
    case ProgramType::BASIC:
    case ProgramType::FOCAL:
      return '1';
    case ProgramType::TINYBASIC:
      return '2';
    case ProgramType::TEXT:
      return '1';
    case ProgramType::MK61_STATE:
      return '2';
  }
  return '1';
}

static bool parse_record(u32 address, u16 sector_offset, RecordMeta& out, bool& empty) {
  empty = false;
  u8 header[8];
  read_bytes(address, header, sizeof(header));
  const u8 tag0 = header[0];
  if(tag0 == 0xFF) {
    empty = true;
    return false;
  }

  const u8 tag1 = header[1];
  bool tag_ok = false;
  out.type = type_from_tag(tag0, tag1, tag_ok);
  if(!tag_ok) return false;

  out.state = header[2];
  out.name_len = header[3];
  if(out.name_len == 0 || out.name_len >= NAME_SIZE) return false;

  out.data_len = (u16) (header[4] | (header[5] << 8));
  out.crc = (u16) (header[6] | (header[7] << 8));
  out.header_len = 8;
  if(out.data_len > MAX_MK61_TEXT_SIZE) return false;

  out.total_len = (u16) (out.header_len + out.name_len + out.data_len);
  if(out.total_len < out.header_len) return false;
  if((usize) sector_offset + out.total_len > FLASH_SECTOR_SIZE) return false;
  return true;
}

static u16 crc16_over_flash(u16 crc, u32 address, u16 len) {
  u8 chunk[64];
  while(len != 0) {
    const u16 step = (len > sizeof(chunk)) ? (u16) sizeof(chunk) : len;
    read_bytes(address, chunk, step);
    for(u16 i = 0; i < step; i++) crc = crc16_update(crc, chunk[i]);
    address += step;
    len = (u16) (len - step);
  }
  return crc;
}

static u16 record_crc(u32 address, const RecordMeta& meta) {
  u16 crc = 0xFFFF;
  u8 tags[2];
  read_bytes(address, tags, sizeof(tags));
  crc = crc16_update(crc, tags[0]);
  crc = crc16_update(crc, tags[1]);
  crc = crc16_update(crc, meta.name_len);
  crc = crc16_update(crc, (u8) (meta.data_len & 0xFF));
  crc = crc16_update(crc, (u8) (meta.data_len >> 8));
  return crc16_over_flash(crc, address + meta.header_len, (u16) (meta.name_len + meta.data_len));
}

static u16 make_crc(ProgramType type, const char* name, u8 name_len, const u8* data, u16 data_len) {
  u16 crc = 0xFFFF;
  crc = crc16_update(crc, tag0_for_type(type));
  crc = crc16_update(crc, tag1_for_type(type));
  crc = crc16_update(crc, name_len);
  crc = crc16_update(crc, (u8) (data_len & 0xFF));
  crc = crc16_update(crc, (u8) (data_len >> 8));
  for(u8 i = 0; i < name_len; i++) crc = crc16_update(crc, (u8) name[i]);
  for(u16 i = 0; i < data_len; i++) crc = crc16_update(crc, data[i]);
  return crc;
}

static bool vfat_stage_cluster_index(u16 cluster, u16& index) {
  if(cluster < VFAT_STAGE_FIRST_CLUSTER) return false;
  const u16 relative = (u16) (cluster - VFAT_STAGE_FIRST_CLUSTER);
  if(relative >= VFAT_STAGE_CLUSTER_COUNT) return false;
  index = relative;
  return true;
}

static u32 vfat_stage_base(void) {
  return sector_base(VFAT_STAGE_FIRST_SECTOR);
}

static u32 vfat_stage_ref_address(u16 ref) {
  if(ref == 0) return 0;
  ref--;
  const u16 sector = (u16) (ref / VFAT_STAGE_RECORDS_PER_SECTOR);
  const u16 record = (u16) (ref % VFAT_STAGE_RECORDS_PER_SECTOR);
  return vfat_stage_base() +
         (u32) sector * FLASH_SECTOR_SIZE +
         (u32) record * VFAT_STAGE_RECORD_SIZE;
}

static u16 vfat_stage_current_ref(void) {
  const u16 record = (u16) (vfat_stage_offset / VFAT_STAGE_RECORD_SIZE);
  return (u16) (vfat_stage_sector * VFAT_STAGE_RECORDS_PER_SECTOR + record + 1);
}

static u32 vfat_stage_capacity_bytes(void) {
#ifdef SPI_FLASH
  return flash.getCapacity();
#else
  return 0;
#endif
}

static u8 vfat_stage_sector_limit(void) {
#ifdef SPI_FLASH
  if(!flash_is_ok) return 0;
  const u32 sectors = vfat_stage_capacity_bytes() / FLASH_SECTOR_SIZE;
  if(sectors <= VFAT_STAGE_FIRST_SECTOR) return 0;
  const u32 available = sectors - VFAT_STAGE_FIRST_SECTOR;
  return (available > VFAT_STAGE_SECTOR_COUNT) ? VFAT_STAGE_SECTOR_COUNT : (u8) available;
#else
  return 0;
#endif
}

static bool vfat_stage_available(void) {
  return vfat_stage_sector_limit() != 0;
}

static u16 vfat_stage_crc(u16 cluster, const u8* data) {
  u16 crc = 0xFFFF;
  crc = crc16_update(crc, (u8) (cluster & 0xFF));
  crc = crc16_update(crc, (u8) (cluster >> 8));
  for(u16 i = 0; i < VFAT_STAGE_DATA_SIZE; i++) crc = crc16_update(crc, data[i]);
  return crc;
}

void vfat_stage_clear(void) {
  memset(vfat_stage_refs, 0, sizeof(vfat_stage_refs));
  memset(vfat_stage_sector_prepared, 0, sizeof(vfat_stage_sector_prepared));
  vfat_stage_active_count = 0;
  vfat_stage_sector = 0;
  vfat_stage_offset = 0;
}

static bool vfat_stage_prepare_sector(u8 sector) {
  if(sector >= vfat_stage_sector_limit()) return false;
  if(vfat_stage_sector_prepared[sector]) return true;
  if(!erase_sector(VFAT_STAGE_FIRST_SECTOR + sector)) return false;
  vfat_stage_sector_prepared[sector] = true;
  return true;
}

static bool vfat_stage_advance_record(void) {
  if(vfat_stage_offset + VFAT_STAGE_RECORD_SIZE <= FLASH_SECTOR_SIZE) return true;
  vfat_stage_sector++;
  vfat_stage_offset = 0;

  if(vfat_stage_sector < vfat_stage_sector_limit()) return true;
  if(vfat_stage_active_count != 0) return false;

  vfat_stage_clear();
  return vfat_stage_available();
}

bool vfat_stage_write(u16 cluster, const u8* data) {
  DiskActivity disk_activity;
  if(data == NULL || !vfat_stage_available()) return false;

  u16 index = 0;
  if(!vfat_stage_cluster_index(cluster, index)) return false;
  if(!vfat_stage_advance_record()) return false;
  if(!vfat_stage_prepare_sector(vfat_stage_sector)) return false;

  const u32 address = vfat_stage_base() +
                      (u32) vfat_stage_sector * FLASH_SECTOR_SIZE +
                      vfat_stage_offset;
  const u16 crc = vfat_stage_crc(cluster, data);

  const u8 header[VFAT_STAGE_HEADER_SIZE] = {
    VFAT_STAGE_TAG0, VFAT_STAGE_TAG1,
    (u8) (cluster & 0xFF), (u8) (cluster >> 8),
    (u8) (crc & 0xFF), (u8) (crc >> 8),
    0, 0
  };
  write_bytes(address, header, sizeof(header));
  write_bytes(address + VFAT_STAGE_HEADER_SIZE, data, VFAT_STAGE_DATA_SIZE);

  if(vfat_stage_refs[index] == 0) vfat_stage_active_count++;
  vfat_stage_refs[index] = vfat_stage_current_ref();
  vfat_stage_offset = (u16) (vfat_stage_offset + VFAT_STAGE_RECORD_SIZE);
  return true;
}

bool vfat_stage_read(u16 cluster, u8* data) {
  if(data == NULL) return false;

  u16 index = 0;
  if(!vfat_stage_cluster_index(cluster, index)) return false;
  const u32 address = vfat_stage_ref_address(vfat_stage_refs[index]);
  if(address == 0) return false;
  if(!vfat_stage_available()) return false;

  DiskActivity disk_activity;
  u8 header[VFAT_STAGE_HEADER_SIZE];
  read_bytes(address, header, sizeof(header));
  if(header[0] != VFAT_STAGE_TAG0 || header[1] != VFAT_STAGE_TAG1) return false;
  if((u16) (header[2] | (header[3] << 8)) != cluster) return false;
  const u16 expected_crc = (u16) (header[4] | (header[5] << 8));
  read_bytes(address + VFAT_STAGE_HEADER_SIZE, data, VFAT_STAGE_DATA_SIZE);
  return vfat_stage_crc(cluster, data) == expected_crc;
}

bool vfat_stage_exists(u16 cluster) {
  u16 index = 0;
  if(!vfat_stage_cluster_index(cluster, index)) return false;
  return vfat_stage_refs[index] != 0;
}

void vfat_stage_forget(u16 start_cluster, u16 clusters) {
  if(clusters == 0) return;
  for(u16 i = 0; i < clusters; i++) {
    u16 index = 0;
    if(!vfat_stage_cluster_index((u16) (start_cluster + i), index)) continue;
    if(vfat_stage_refs[index] == 0) continue;
    vfat_stage_refs[index] = 0;
    if(vfat_stage_active_count != 0) vfat_stage_active_count--;
  }
}

static bool read_name(u32 address, const RecordMeta& meta, char* out) {
  if(meta.name_len == 0 || meta.name_len >= NAME_SIZE) return false;
  read_bytes(address + meta.header_len, (u8*) out, meta.name_len);
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

static void remove_index_at(u8 idx) {
  if(idx >= index_count) return;
  for(u8 i = idx; i + 1 < index_count; i++) index_entries[i] = index_entries[i + 1];
  index_count--;
  memset(&index_entries[index_count], 0, sizeof(index_entries[index_count]));
}

static void add_live_to_sector(u32 address, u16 total_len) {
  const int sector = sector_from_address(address);
  if(sector < 0) return;
  SectorInfo& info = sectors[sector];
  if((usize) info.live + total_len <= 0xFFFF) info.live = (u16) (info.live + total_len);
}

static void move_live_to_dead(u32 address, u16 total_len) {
  const int sector = sector_from_address(address);
  if(sector < 0) return;
  SectorInfo& info = sectors[sector];
  info.live = (info.live >= total_len) ? (u16) (info.live - total_len) : 0;
  if((usize) info.dead + total_len <= 0xFFFF) info.dead = (u16) (info.dead + total_len);
}

static bool record_is_latest(u32 address, const RecordMeta& meta, const char* name) {
  const int idx = find_index(meta.type, name);
  return idx >= 0 && index_entries[idx].address == address;
}

static void reset_state(void) {
  memset(sectors, 0, sizeof(sectors));
  memset(index_entries, 0, sizeof(index_entries));
  index_count = 0;
  next_generation = 1;
}

static void reset_to_ignored_store(void) {
  reset_state();
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    sectors[i].foreign = true;
    sectors[i].used = FLASH_SECTOR_SIZE;
    sectors[i].dead = FLASH_SECTOR_SIZE;
  }
  index_valid = true;
}

static u8 flags_for_sector(const SectorInfo& info) {
  if(info.empty) return SECTOR_FLAG_EMPTY;
  if(info.active) return SECTOR_FLAG_ACTIVE;
  if(info.foreign) return SECTOR_FLAG_FOREIGN;
  return 0;
}

static u16 catalog_snapshot_len(u8 entry_count) {
  return (u16) (CATALOG_HEADER_SIZE +
                STORE_SECTOR_COUNT * CATALOG_SECTOR_INFO_SIZE +
                (usize) entry_count * CATALOG_ENTRY_SIZE);
}

static u16 catalog_crc_from_flash(u32 base, u16 total_len) {
  u16 crc = 0xFFFF;
  u8 header[CATALOG_HEADER_SIZE];
  read_bytes(base, header, sizeof(header));
  crc = crc16_update(crc, header[0]);
  crc = crc16_update(crc, header[1]);
  for(u8 i = 3; i < CATALOG_HEADER_SIZE; i++) {
    if(i == 7 || i == 8) continue;
    crc = crc16_update(crc, header[i]);
  }
  return crc16_over_flash(crc, base + CATALOG_HEADER_SIZE, (u16) (total_len - CATALOG_HEADER_SIZE));
}

static u16 catalog_crc_from_ram(u8 entry_count, u16 total_len) {
  u16 crc = 0xFFFF;
  crc = crc16_update(crc, CATALOG_TAG0);
  crc = crc16_update(crc, CATALOG_TAG1);
  crc = crc16_update(crc, (u8) STORE_SECTOR_COUNT);
  crc = crc16_update(crc, entry_count);
  crc = crc16_update(crc, (u8) (total_len & 0xFF));
  crc = crc16_update(crc, (u8) (total_len >> 8));

  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    const SectorInfo& info = sectors[i];
    crc = crc16_update(crc, flags_for_sector(info));
    crc = crc16_update(crc, (u8) (info.generation & 0xFF));
    crc = crc16_update(crc, (u8) ((info.generation >> 8) & 0xFF));
    crc = crc16_update(crc, (u8) ((info.generation >> 16) & 0xFF));
    crc = crc16_update(crc, (u8) ((info.generation >> 24) & 0xFF));
    crc = crc16_update(crc, (u8) (info.used & 0xFF));
    crc = crc16_update(crc, (u8) (info.used >> 8));
    crc = crc16_update(crc, (u8) (info.live & 0xFF));
    crc = crc16_update(crc, (u8) (info.live >> 8));
  }

  for(u8 i = 0; i < index_count; i++) {
    const IndexEntry& entry = index_entries[i];
    if(!entry.used) continue;
    const int sector = sector_from_address(entry.address);
    if(sector < 0) continue;
    const u16 offset = offset_in_sector(entry.address);
    crc = crc16_update(crc, (u8) entry.type);
    crc = crc16_update(crc, entry.name_len);
    crc = crc16_update(crc, (u8) sector);
    crc = crc16_update(crc, (u8) (offset & 0xFF));
    crc = crc16_update(crc, (u8) (offset >> 8));
    crc = crc16_update(crc, (u8) (entry.data_len & 0xFF));
    crc = crc16_update(crc, (u8) (entry.data_len >> 8));
    crc = crc16_update(crc, (u8) (entry.total_len & 0xFF));
    crc = crc16_update(crc, (u8) (entry.total_len >> 8));
    for(u8 n = 0; n < NAME_SIZE; n++) crc = crc16_update(crc, (u8) entry.name[n]);
  }

  return crc;
}

static bool save_catalog(void) {
#ifdef SPI_FLASH
  if(!flash_is_ok) return false;
#else
  return false;
#endif

  const u8 entry_count = index_count;
  const u16 total_len = catalog_snapshot_len(entry_count);
  if(total_len > FLASH_SECTOR_SIZE) return false;

  if(!erase_sector(CATALOG_SECTOR)) return false;

  const u32 base = sector_base(CATALOG_SECTOR);
  const u16 crc = catalog_crc_from_ram(entry_count, total_len);
  const u8 header[CATALOG_HEADER_SIZE] = {
    CATALOG_TAG0, CATALOG_TAG1, STATE_WRITING, (u8) STORE_SECTOR_COUNT, entry_count,
    (u8) (total_len & 0xFF), (u8) (total_len >> 8),
    (u8) (crc & 0xFF), (u8) (crc >> 8)
  };
  write_bytes(base, header, sizeof(header));

  u32 pos = base + CATALOG_HEADER_SIZE;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    const SectorInfo& info = sectors[i];
    const u8 record[CATALOG_SECTOR_INFO_SIZE] = {
      flags_for_sector(info),
      (u8) (info.generation & 0xFF), (u8) ((info.generation >> 8) & 0xFF),
      (u8) ((info.generation >> 16) & 0xFF), (u8) ((info.generation >> 24) & 0xFF),
      (u8) (info.used & 0xFF), (u8) (info.used >> 8),
      (u8) (info.live & 0xFF), (u8) (info.live >> 8)
    };
    write_bytes(pos, record, sizeof(record));
    pos += sizeof(record);
  }

  for(u8 i = 0; i < index_count; i++) {
    const IndexEntry& entry = index_entries[i];
    if(!entry.used) continue;
    const int sector = sector_from_address(entry.address);
    if(sector < 0) return false;
    const u16 offset = offset_in_sector(entry.address);
    u8 record[CATALOG_ENTRY_SIZE];
    record[0] = (u8) entry.type;
    record[1] = entry.name_len;
    record[2] = (u8) sector;
    record[3] = (u8) (offset & 0xFF);
    record[4] = (u8) (offset >> 8);
    record[5] = (u8) (entry.data_len & 0xFF);
    record[6] = (u8) (entry.data_len >> 8);
    record[7] = (u8) (entry.total_len & 0xFF);
    record[8] = (u8) (entry.total_len >> 8);
    for(u8 n = 0; n < NAME_SIZE; n++) record[9 + n] = (u8) entry.name[n];
    write_bytes(pos, record, sizeof(record));
    pos += sizeof(record);
  }

  write_byte(base + 2, STATE_ACTIVE);
  return true;
}

static bool load_catalog(void) {
#ifdef SPI_FLASH
  if(!flash_is_ok) return false;
#else
  return false;
#endif

  const u32 base = sector_base(CATALOG_SECTOR);
  if(read_byte(base) != CATALOG_TAG0 || read_byte(base + 1) != CATALOG_TAG1) return false;
  if(read_byte(base + 2) != STATE_ACTIVE) return false;
  if(read_byte(base + 3) != (u8) STORE_SECTOR_COUNT) return false;

  const u8 entry_count = read_byte(base + 4);
  if(entry_count > MAX_ENTRIES) return false;
  const u16 total_len = read_le16(base + 5);
  if(total_len != catalog_snapshot_len(entry_count) || total_len > FLASH_SECTOR_SIZE) return false;
  if(total_len < FLASH_SECTOR_SIZE && read_byte(base + total_len) != 0xFF) return false;

  const u16 stored_crc = read_le16(base + 7);
  if(catalog_crc_from_flash(base, total_len) != stored_crc) return false;

  reset_state();
  u32 pos = base + CATALOG_HEADER_SIZE;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    u8 record[CATALOG_SECTOR_INFO_SIZE];
    read_bytes(pos, record, sizeof(record));
    pos += sizeof(record);
    const u8 flags = record[0];
    const u32 generation = (u32) record[1] | ((u32) record[2] << 8) | ((u32) record[3] << 16) | ((u32) record[4] << 24);
    const u16 used = (u16) (record[5] | (record[6] << 8));
    const u16 live = (u16) (record[7] | (record[8] << 8));

    const u8 known_flags = (u8) (flags & (SECTOR_FLAG_EMPTY | SECTOR_FLAG_ACTIVE | SECTOR_FLAG_FOREIGN));
    if(known_flags == 0 || (known_flags & (known_flags - 1)) != 0) return false;

    SectorInfo& info = sectors[i];
    info.empty = (known_flags == SECTOR_FLAG_EMPTY);
    info.active = (known_flags == SECTOR_FLAG_ACTIVE);
    info.foreign = (known_flags == SECTOR_FLAG_FOREIGN);
    info.generation = generation;
    info.used = used;
    info.live = live;

    if(info.empty) {
      if(generation != 0 || used != 0 || live != 0) return false;
    } else if(info.active) {
      if(generation == 0 || used < SECTOR_HEADER_SIZE || used > FLASH_SECTOR_SIZE) return false;
      if(live > used - SECTOR_HEADER_SIZE) return false;
      info.dead = (u16) (used - SECTOR_HEADER_SIZE - live);
      if(generation >= next_generation) {
        next_generation = generation + 1;
        if(next_generation == 0) next_generation = 1;
      }
    } else {
      if(used != FLASH_SECTOR_SIZE || live != 0) return false;
      info.dead = FLASH_SECTOR_SIZE;
    }
  }

  for(u8 i = 0; i < entry_count; i++) {
    IndexEntry& entry = index_entries[index_count];
    const u8 type = read_byte(pos++);
    if(type > (u8) ProgramType::MK61_STATE) return false;
    entry.type = (ProgramType) type;
    entry.name_len = read_byte(pos++);
    const u8 sector = read_byte(pos++);
    const u16 offset = read_le16(pos); pos += 2;
    entry.data_len = read_le16(pos); pos += 2;
    entry.total_len = read_le16(pos); pos += 2;
    const u16 header_len = 8;
    if(entry.name_len == 0 || entry.name_len >= NAME_SIZE) return false;
    if(entry.total_len != header_len + entry.name_len + entry.data_len) return false;
    if(entry.data_len > MAX_MK61_TEXT_SIZE) return false;
    if(sector >= STORE_SECTOR_COUNT || !sectors[sector].active || offset < SECTOR_HEADER_SIZE) return false;
    if((usize) offset + entry.total_len > FLASH_SECTOR_SIZE) return false;
    for(u8 n = 0; n < NAME_SIZE; n++) entry.name[n] = (char) read_byte(pos++);
    entry.name[NAME_SIZE - 1] = 0;
    if(entry.name[entry.name_len] != 0) return false;
    entry.address = sector_base(sector) + offset;
    entry.used = true;
    index_count++;
  }

  index_valid = true;
  return true;
}

bool refresh(void) {
  DiskActivity disk_activity;
  index_valid = false;
  if(load_catalog()) return true;
  reset_to_ignored_store();
  return true;
}

void init(void) {
  vfat_stage_clear();
  index_valid = false;
  if(load_catalog()) return;
  reset_to_ignored_store();
}

static bool ensure_index(void) {
  return index_valid ? true : refresh();
}

bool format(void) {
  DiskActivity disk_activity;
#ifdef SPI_FLASH
  if(!flash_is_ok) return false;
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) {
    if(!erase_sector(i)) return false;
  }
  (void) erase_sector(CATALOG_SECTOR);
  vfat_stage_clear();
  reset_state();
  for(usize i = 0; i < STORE_SECTOR_COUNT; i++) sectors[i].empty = true;
  index_valid = true;
  (void) save_catalog();
  return true;
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

static bool reclaim_foreign_sector(void) {
  const int sector = foreign_sector();
  if(sector < 0) return false;
  if(!erase_sector((usize) sector)) return false;
  memset(&sectors[sector], 0, sizeof(sectors[sector]));
  sectors[sector].empty = true;
  return true;
}

static bool ensure_empty_sector_count(usize min_count) {
  while((usize) empty_sector_count() < min_count) {
    if(!reclaim_foreign_sector()) return false;
  }
  return true;
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
  const u32 generation = next_generation++;
  if(next_generation == 0) next_generation = 1;
  write_le32(base + 3, generation);
  write_byte(base + 2, STATE_ACTIVE);

  SectorInfo& info = sectors[sector];
  memset(&info, 0, sizeof(info));
  info.active = true;
  info.generation = generation;
  info.used = SECTOR_HEADER_SIZE;
  return true;
}

static bool prepare_empty_sector(void) {
  int sector = empty_sector();
  if(sector >= 0) return true;
  return reclaim_foreign_sector();
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
      char name[NAME_SIZE];
      if(read_name(src, meta, name)) {
        const int idx = find_index(meta.type, name);
        if(idx >= 0 && index_entries[idx].address == src) index_entries[idx].address = dst;
      }
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
  sectors[empty].used = dest_used;
  sectors[empty].live = sectors[victim].live;
  sectors[empty].dead = 0;
  if(!erase_sector((usize) victim)) return false;
  memset(&sectors[victim], 0, sizeof(sectors[victim]));
  sectors[victim].empty = true;
  (void) save_catalog();
  return true;
}

static bool ensure_space(u16 record_len) {
  if(!ensure_index()) return false;
  if(record_len > FLASH_SECTOR_SIZE - SECTOR_HEADER_SIZE) return false;

  int current = current_sector();
  if(current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE) return true;

  if(current < 0) {
    if(empty_sector() < 0 && !prepare_empty_sector()) return false;
    const int empty = empty_sector();
    if(empty < 0 || !open_sector((usize) empty)) return false;
    current = current_sector();
    return current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE;
  }

  if(empty_sector_count() >= 2 || ensure_empty_sector_count(2)) {
    const int empty = empty_sector();
    if(empty < 0 || !open_sector((usize) empty)) return false;
    current = current_sector();
    return current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE;
  }

  if(garbage_collect(record_len)) {
    current = current_sector();
    return current >= 0 && (usize) sectors[current].used + record_len <= FLASH_SECTOR_SIZE;
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
  (void) type;
  const u8 nlen = name_len_of(name);
  if(nlen == 0 || nlen >= NAME_SIZE) return false;
  if(data_len == 0 || data_len > MAX_MK61_TEXT_SIZE) return false;
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
  DiskActivity disk_activity;
  if(data == NULL && data_len != 0) return false;
  if(!valid_write(type, name, data_len)) return false;
  if(!ensure_index()) return false;

  const int old_idx = find_index(type, name);
  if(old_idx < 0 && index_count >= MAX_ENTRIES) return false;

  const u8 nlen = name_len_of(name);
  const u16 header_len = 8;
  const u16 record_len = (u16) (header_len + nlen + data_len);
  if(!ensure_space(record_len)) return false;

  const u32 old_address = (old_idx >= 0) ? index_entries[old_idx].address : 0xFFFFFFFFUL;
  const u16 old_total_len = (old_idx >= 0) ? index_entries[old_idx].total_len : 0;

  const int sector = current_sector();
  if(sector < 0) return false;
  const u32 address = sector_base((usize) sector) + sectors[sector].used;
  const u16 crc = make_crc(type, name, nlen, data, data_len);

  const u8 header[8] = {
    tag0_for_type(type), tag1_for_type(type), STATE_WRITING, nlen,
    (u8) (data_len & 0xFF), (u8) (data_len >> 8),
    (u8) (crc & 0xFF), (u8) (crc >> 8)
  };
  write_bytes(address, header, sizeof(header));
  write_bytes(address + header_len, (const u8*) name, nlen);
  write_bytes(address + header_len + nlen, data, data_len);
  write_byte(address + 2, STATE_ACTIVE);

  sectors[sector].used = (u16) (sectors[sector].used + record_len);
  add_live_to_sector(address, record_len);
  if(old_idx >= 0) {
    mark_deleted_at(old_address);
    move_live_to_dead(old_address, old_total_len);
  }

  RecordMeta meta;
  meta.type = type;
  meta.state = STATE_ACTIVE;
  meta.name_len = nlen;
  meta.data_len = data_len;
  meta.crc = crc;
  meta.header_len = header_len;
  meta.total_len = record_len;
  update_index(meta, name, address);
  (void) save_catalog();
  return true;
}

bool read(ProgramType type, const char* name, u8* data, u16 capacity, u16* out_len) {
  DiskActivity disk_activity;
  if(out_len != NULL) *out_len = 0;
  if(data == NULL && capacity != 0) return false;
  if(!ensure_index()) return false;
  const int idx = find_index(type, name);
  if(idx < 0) return false;
  const IndexEntry& entry = index_entries[idx];
  if(entry.data_len > capacity) return false;

  const u32 payload = entry.address + 8 + entry.name_len;
  read_bytes(payload, data, entry.data_len);
  if(out_len != NULL) *out_len = entry.data_len;
  return true;
}

bool read_range(ProgramType type, const char* name, u16 offset, u8* data, u16 len, u16* out_len) {
  DiskActivity disk_activity;
  if(out_len != NULL) *out_len = 0;
  if(data == NULL && len != 0) return false;
  if(!ensure_index()) return false;
  const int idx = find_index(type, name);
  if(idx < 0) return false;
  const IndexEntry& entry = index_entries[idx];
  if(offset >= entry.data_len) return true;

  u16 available = (u16) (entry.data_len - offset);
  if(available > len) available = len;

  const u32 payload = entry.address + 8 + entry.name_len + offset;
  read_bytes(payload, data, available);
  if(out_len != NULL) *out_len = available;
  return true;
}

bool remove(ProgramType type, const char* name) {
  DiskActivity disk_activity;
  if(!ensure_index()) return false;
  const int idx = find_index(type, name);
  if(idx < 0) return false;
  const u32 address = index_entries[idx].address;
  const u16 total_len = index_entries[idx].total_len;
  mark_deleted_at(address);
  move_live_to_dead(address, total_len);
  remove_index_at((u8) idx);
  (void) save_catalog();
  return true;
}

u16 purge_empty(void) {
  DiskActivity disk_activity;
  if(!ensure_index()) return 0;

  u16 purged = 0;
  for(u8 i = 0; i < index_count; ) {
    if(!index_entries[i].used || index_entries[i].data_len != 0) {
      i++;
      continue;
    }
    const u32 address = index_entries[i].address;
    const u16 total_len = index_entries[i].total_len;
    mark_deleted_at(address);
    move_live_to_dead(address, total_len);
    remove_index_at(i);
    purged++;
  }

  if(purged != 0) (void) save_catalog();
  return purged;
}

bool rename(ProgramType type, const char* old_name, const char* new_name) {
  DiskActivity disk_activity;
  if(old_name == NULL || new_name == NULL || old_name[0] == 0 || new_name[0] == 0) return false;
  shared_scratch::Lease scratch(shared_scratch::Owner::PROGRAM_STORE_RENAME, MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) return false;
  u8* buffer = scratch.data();
  u16 len = 0;
  if(type == ProgramType::MK61) {
    if(!read(type, old_name, buffer, MAX_MK61_TEXT_SIZE, &len)) return false;
  } else {
    if(!read(type, old_name, buffer, scratch.size(), &len)) return false;
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

bool write_mk61(const char* name, const u8* code, u16 code_len) {
  return write(ProgramType::MK61, name, code, code_len);
}

bool read_mk61(const char* name, u8* code, u16 capacity, u16* out_len) {
  u16 len = 0;
  if(!read(ProgramType::MK61, name, code, capacity, &len)) return false;
  if(out_len != NULL) *out_len = len;
  return true;
}

} // namespace program_store
