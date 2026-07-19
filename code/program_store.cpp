#include "program_store.hpp"

#include "fat_name.hpp"
#include "Arduino.h"
#include "config.h"
#include "flash_capacity_probe.hpp"
#include "ledcontrol.h"
#include "shared_scratch.hpp"
#include "spi_nor_flash.hpp"
#include "tools.hpp"

#include <string.h>

#ifdef SPI_FLASH
extern SpiNorFlash flash;
#endif

namespace program_store {
namespace {

static constexpr u8 FORMAT_VERSION = 5;
static constexpr u8 STATE_WRITING = 0xFF;
static constexpr u8 STATE_ACTIVE = 0x7F;
static constexpr u8 STATE_DELETED = 0x3F;
static constexpr u32 EMPTY_ADDRESS = 0xFFFFFFFFUL;
static constexpr u32 EXTENT_ADDRESS = 0xFFFFFFFEUL;
static constexpr u16 NONE = 0xFFFF;
static constexpr u16 DATA_SECTOR_HEADER_SIZE = 16;
static constexpr u16 RECORD_HEADER_SIZE = 16;
static constexpr u16 LOCATOR_SIZE = 72;
static constexpr u16 SETTINGS_GUARD_SIZE = 16;
static constexpr u16 SETTINGS_JOURNAL_SIZE =
    storage_geometry::PHYSICAL_SECTOR_SIZE - SETTINGS_GUARD_SIZE;
static constexpr u16 CATALOG_HEADER_SIZE = 80;
static constexpr u16 CATALOG_HEADER_CRC_OFFSET = 72;
static constexpr u16 WAL_RECORD_SIZE = 256;
static constexpr u8 WAL_MAX_UPDATES = 9;
static constexpr u8 OVERLAY_CAPACITY = 96;
static constexpr u16 STAGE_DATA_SIZE = 512;
static constexpr u16 STAGE_SECTOR_HEADER_SIZE = 16;
static constexpr u16 STAGE_RECORD_HEADER_SIZE = 16;
static constexpr u16 STAGE_RECORD_SIZE = STAGE_RECORD_HEADER_SIZE + STAGE_DATA_SIZE;
static constexpr u8 STAGE_RECORDS_PER_SECTOR =
    (storage_geometry::PHYSICAL_SECTOR_SIZE - STAGE_SECTOR_HEADER_SIZE) /
    STAGE_RECORD_SIZE;
static constexpr u16 STAGE_REF_CAPACITY = 384;
static constexpr u8 STAGE_REF_BITS = 9;
static constexpr u16 STAGE_REF_MASK = (1U << STAGE_REF_BITS) - 1U;
static constexpr u32 STAGE_KEY_MAX = 0xFFFFFFFFUL >> STAGE_REF_BITS;
static constexpr u8 GC_SCAN_WINDOW = 32;
static constexpr u32 ERASE_TIMEOUT_MS = 5000;
static constexpr t_time_ms DISK_LED_ON_MS = 35;
static constexpr t_time_ms DISK_LED_OFF_MS = 35;

static_assert(STAGE_RECORDS_PER_SECTOR == 7, "C5 stage must pack seven sectors");
static_assert((usize) MAX_MK61_TEXT_SIZE + NAME_SIZE + RECORD_HEADER_SIZE <=
                  storage_geometry::PHYSICAL_SECTOR_SIZE / 2,
              "two maximum C5 records must fit one erase sector");

struct Inode {
  u32 address;
  u16 data_len;
  u16 record_len;
  u16 parent_id;
  u16 first_child;
  u16 next_sibling;
  u16 prev_sibling;
  u16 name_hash;
  u8 kind_type;
  u8 flags;
};

static_assert(sizeof(Inode) == storage_geometry::INODE_BYTES,
              "C5 inode RAM and disk representation must stay compact");

struct CatalogMeta {
  u16 root_head;
  u16 total_count;
  u16 type_count[6];
  u32 current_sector;
  u16 current_offset;
  u32 reserve_sector;
  u32 gc_cursor;
  u32 data_sequence;
};

struct Update {
  u16 id;
  Inode inode;
};

struct Transaction {
  CatalogMeta meta;
  Update updates[WAL_MAX_UPDATES];
  u8 count;
};

static storage_geometry::Geometry g_geometry;
static bool g_ready;
static u32 g_format_epoch;
static u8 g_active_bank;
static u32 g_catalog_generation;
static u32 g_wal_sequence;
static u8 g_wal_records;
static bool g_wal_sealed;
static CatalogMeta g_meta;
// Structure-of-arrays keeps Inode naturally aligned without the two bytes of
// tail padding that an {u16, Inode} array would pay for every overlay slot.
static u16 g_overlay_ids[OVERLAY_CAPACITY];
static Inode g_overlay_inodes[OVERLAY_CAPACITY];
static u8 g_overlay_count;
static u8 g_table_cache[512];
static u32 g_table_cache_address = EMPTY_ADDRESS;
static u8 g_disk_activity_depth;
static u8 g_disk_led_poll_divider;

// Pack an 18-bit virtual LBA and a 9-bit physical record reference into one
// word.  This grows the live staging set fourfold while adding less than one
// KiB over the former parallel key/generation/reference arrays.
static u32 g_stage_index[STAGE_REF_CAPACITY];
static u16 g_stage_ref_count;
static u8 g_stage_used[storage_geometry::STAGE_TARGET_SECTORS];
static u8 g_stage_sealed[storage_geometry::STAGE_TARGET_SECTORS];
static u16 g_stage_generation;
static u16 g_free_hint;

static_assert((u16) storage_geometry::STAGE_TARGET_SECTORS *
                  STAGE_RECORDS_PER_SECTOR <= STAGE_REF_MASK,
              "C5 stage references must fit in the packed index");

static int g_flat_cache_index = -1;
static u16 g_flat_cache_id;
static u16 g_child_cache_parent = NONE;
static int g_child_cache_index = -1;
static u16 g_child_cache_id = NONE;

static void disk_led_poll(void) {
  if(g_disk_activity_depth == 0) return;
  g_disk_led_poll_divider++;
  if((g_disk_led_poll_divider & 0x0F) == 0) led::control();
}

class DiskActivity {
  public:
    DiskActivity(void) {
      if(g_disk_activity_depth++ == 0) {
        g_disk_led_poll_divider = 0;
        led::blink_continuous(DISK_LED_ON_MS, DISK_LED_OFF_MS);
      }
    }

    ~DiskActivity(void) {
      if(g_disk_activity_depth == 0) return;
      g_disk_activity_depth--;
      if(g_disk_activity_depth == 0) led::blink_stop();
    }
};

static u32 sector_address(u32 sector) {
  return sector * storage_geometry::PHYSICAL_SECTOR_SIZE;
}

static bool read_bytes(u32 address, u8* out, usize len) {
  if(len == 0) return true;
#ifdef SPI_FLASH
  if(flash_is_ok && flash.readByteArray(address, out, len)) {
    disk_led_poll();
    return true;
  }
#else
  (void) address;
#endif
  if(out != NULL) memset(out, 0xFF, len);
  return false;
}

static bool write_bytes(u32 address, const u8* data, usize len) {
  if(len == 0) return true;
#ifdef SPI_FLASH
  if(flash_is_ok && data != NULL) {
    const bool ok = flash.writeByteArray(address, (u8*) data, len);
    disk_led_poll();
    return ok;
  }
#else
  (void) address;
  (void) data;
#endif
  return false;
}

static bool write_byte(u32 address, u8 value) {
#ifdef SPI_FLASH
  if(flash_is_ok) {
    const bool ok = flash.writeByte(address, value);
    disk_led_poll();
    return ok;
  }
#else
  (void) address;
  (void) value;
#endif
  return false;
}

static bool erase_sector(u32 sector) {
#ifdef SPI_FLASH
  if(!flash_is_ok || sector >= g_geometry.physical_sectors) return false;
  const u32 stop_at = millis() + ERASE_TIMEOUT_MS;
  while(!flash.eraseSector(sector_address(sector))) {
    led::control();
    if((i32) (millis() - stop_at) >= 0) return false;
  }
  led::control();
  g_table_cache_address = EMPTY_ADDRESS;
  return true;
#else
  (void) sector;
  return false;
#endif
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

static u32 crc32_update(u32 crc, u8 value) {
  crc ^= value;
  for(u8 bit = 0; bit < 8; bit++) {
    crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320UL : crc >> 1;
  }
  return crc;
}

static u32 crc32_bytes(const u8* data, usize len, u32 crc = 0xFFFFFFFFUL) {
  for(usize i = 0; i < len; i++) crc = crc32_update(crc, data[i]);
  return crc;
}

static u32 crc32_flash(u32 address, u32 len, u32 crc = 0xFFFFFFFFUL) {
  u8 buffer[64];
  while(len != 0) {
    const u16 count = len > sizeof(buffer) ? sizeof(buffer) : (u16) len;
    if(!read_bytes(address, buffer, count)) return 0;
    crc = crc32_bytes(buffer, count, crc);
    address += count;
    len -= count;
  }
  return crc;
}

static void encode_settings_guard(u8* guard, u32 capacity) {
  memset(guard, 0xFF, SETTINGS_GUARD_SIZE);
  memcpy(guard, "C5SG", 4);
  guard[4] = FORMAT_VERSION;
  put_le32(guard, 8, capacity);
  put_le32(guard, 12, ~crc32_bytes(guard, 12));
}

static bool settings_guard_valid(const storage_geometry::Geometry& geometry) {
  u8 guard[SETTINGS_GUARD_SIZE];
#ifdef SPI_FLASH
  const u32 address = sector_address(geometry.settings_sector) +
                      SETTINGS_JOURNAL_SIZE;
  if(!flash.rawPrepare(geometry.capacity_bytes) ||
     !flash.rawRead(address, guard, sizeof(guard))) return false;
#else
  (void) geometry;
  return false;
#endif
  return memcmp(guard, "C5SG", 4) == 0 &&
         guard[4] == FORMAT_VERSION &&
         get_le32(guard, 8) == geometry.capacity_bytes &&
         get_le32(guard, 12) == ~crc32_bytes(guard, 12);
}

static bool write_settings_guard(void) {
  u8 guard[SETTINGS_GUARD_SIZE];
  encode_settings_guard(guard, g_geometry.capacity_bytes);
  return write_bytes(sector_address(g_geometry.settings_sector) +
                     SETTINGS_JOURNAL_SIZE, guard, sizeof(guard));
}

static u16 hash_name(const char* name) {
  u16 hash = 0x811C;
  if(name == NULL) return hash;
  while(*name != 0) {
    hash ^= (u8) *name++;
    hash = (u16) (hash * 257U + 17U);
  }
  return hash;
}

static char ascii_upper(char value) {
  return value >= 'a' && value <= 'z' ? (char) (value - 'a' + 'A') : value;
}

static bool valid_utf8(const char* text, usize len) {
  usize offset = 0;
  while(offset < len) {
    const u8 first = (u8) text[offset];
    u8 continuation = 0;
    u32 codepoint = 0;
    if(first < 0x80) {
      offset++;
      continue;
    } else if((first & 0xE0) == 0xC0) {
      continuation = 1;
      codepoint = first & 0x1F;
    } else if((first & 0xF0) == 0xE0) {
      continuation = 2;
      codepoint = first & 0x0F;
    } else if((first & 0xF8) == 0xF0) {
      continuation = 3;
      codepoint = first & 0x07;
    } else {
      return false;
    }
    if(offset + continuation >= len) return false;
    for(u8 i = 1; i <= continuation; i++) {
      const u8 next = (u8) text[offset + i];
      if((next & 0xC0) != 0x80) return false;
      codepoint = (codepoint << 6) | (next & 0x3F);
    }
    if((continuation == 1 && codepoint < 0x80) ||
       (continuation == 2 && codepoint < 0x800) ||
       (continuation == 3 && codepoint < 0x10000) ||
       codepoint > 0x10FFFF ||
       (codepoint >= 0xD800 && codepoint <= 0xDFFF)) return false;
    offset += (usize) continuation + 1;
  }
  return true;
}

static bool reserved_dos_name(const char* name, usize len) {
  usize base_len = 0;
  while(base_len < len && name[base_len] != '.') base_len++;
  char base[5] = {};
  if(base_len == 0 || base_len >= sizeof(base)) return false;
  for(usize i = 0; i < base_len; i++) base[i] = ascii_upper(name[i]);
  if(strcmp(base, "CON") == 0 || strcmp(base, "PRN") == 0 ||
     strcmp(base, "AUX") == 0 || strcmp(base, "NUL") == 0) return true;
  return base_len == 4 && (memcmp(base, "COM", 3) == 0 ||
                           memcmp(base, "LPT", 3) == 0) &&
         base[3] >= '1' && base[3] <= '9';
}

static bool valid_name(const char* name) {
  if(name == NULL || name[0] == 0 || strcmp(name, ".") == 0 ||
     strcmp(name, "..") == 0) return false;
  usize len = 0;
  while(name[len] != 0) {
    const u8 value = (u8) name[len];
    if(value < 0x20 || strchr("<>:\"/\\|?*", value) != NULL) return false;
    if(++len >= NAME_SIZE) return false;
  }
  return name[len - 1] != ' ' && name[len - 1] != '.' &&
         valid_utf8(name, len) && !reserved_dos_name(name, len);
}

static int type_index(ProgramType type) {
  switch(type) {
    case ProgramType::MK61: return 0;
    case ProgramType::FOCAL: return 1;
    case ProgramType::TINYBASIC: return 2;
    case ProgramType::TEXT: return 3;
    case ProgramType::MK61_STATE: return 4;
    case ProgramType::FONT: return 5;
  }
  return -1;
}

static bool supported_type(ProgramType type) {
  return type_index(type) >= 0;
}

static const char* extension_for_type(ProgramType type) {
  switch(type) {
    case ProgramType::MK61: return "m61";
    case ProgramType::FOCAL: return "foc";
    case ProgramType::TINYBASIC: return "tbi";
    case ProgramType::TEXT: return "txt";
    case ProgramType::MK61_STATE: return "state.txt";
    case ProgramType::FONT: return "fmk";
  }
  return "bin";
}

static Inode empty_inode(void) {
  Inode inode;
  memset(&inode, 0xFF, sizeof(inode));
  return inode;
}

static bool inode_used(const Inode& inode) {
  return inode.address != EMPTY_ADDRESS;
}

static NodeKind inode_kind(const Inode& inode) {
  return (NodeKind) ((inode.kind_type >> 6) & 0x03);
}

static ProgramType inode_type(const Inode& inode) {
  return (ProgramType) (inode.kind_type & 0x3F);
}

static u8 make_kind_type(NodeKind kind, ProgramType type) {
  return (u8) (((u8) kind << 6) | ((u8) type & 0x3F));
}

static bool visible_inode(const Inode& inode) {
  if(!inode_used(inode)) return false;
  const NodeKind kind = inode_kind(inode);
  return kind == NodeKind::FILE || kind == NodeKind::DIRECTORY;
}

static void serialize_inode(const Inode& inode, u8* out) {
  if(!inode_used(inode)) {
    memset(out, 0xFF, storage_geometry::INODE_BYTES);
    return;
  }
  put_le32(out, 0, inode.address);
  put_le16(out, 4, inode.data_len);
  put_le16(out, 6, inode.record_len);
  put_le16(out, 8, inode.parent_id);
  put_le16(out, 10, inode.first_child);
  put_le16(out, 12, inode.next_sibling);
  put_le16(out, 14, inode.prev_sibling);
  put_le16(out, 16, inode.name_hash);
  out[18] = inode.kind_type;
  out[19] = inode.flags;
}

static Inode deserialize_inode(const u8* data) {
  if(get_le32(data, 0) == EMPTY_ADDRESS) return empty_inode();
  Inode inode;
  inode.address = get_le32(data, 0);
  inode.data_len = get_le16(data, 4);
  inode.record_len = get_le16(data, 6);
  inode.parent_id = get_le16(data, 8);
  inode.first_child = get_le16(data, 10);
  inode.next_sibling = get_le16(data, 12);
  inode.prev_sibling = get_le16(data, 14);
  inode.name_hash = get_le16(data, 16);
  inode.kind_type = data[18];
  inode.flags = data[19];
  return inode;
}

static u32 bank_sector(u8 bank) {
  return bank == 0 ? g_geometry.catalog_a_sector : g_geometry.catalog_b_sector;
}

static u32 table_address(u8 bank) {
  return sector_address(bank_sector(bank) + storage_geometry::CATALOG_HEADER_SECTORS);
}

static u32 wal_address(u8 bank) {
  return sector_address(bank_sector(bank) + storage_geometry::CATALOG_HEADER_SECTORS +
                        g_geometry.catalog_table_sectors);
}

static int overlay_search(u16 id, bool& found) {
  int low = 0;
  int high = g_overlay_count;
  while(low < high) {
    const int middle = low + (high - low) / 2;
    if(g_overlay_ids[middle] < id) low = middle + 1;
    else high = middle;
  }
  found = low < g_overlay_count && g_overlay_ids[low] == id;
  return low;
}

static bool overlay_set(u16 id, const Inode& inode) {
  bool found = false;
  const int position = overlay_search(id, found);
  if(found) {
    g_overlay_inodes[position] = inode;
    return true;
  }
  if(g_overlay_count >= OVERLAY_CAPACITY) return false;
  for(int i = g_overlay_count; i > position; i--) {
    g_overlay_ids[i] = g_overlay_ids[i - 1];
    g_overlay_inodes[i] = g_overlay_inodes[i - 1];
  }
  g_overlay_ids[position] = id;
  g_overlay_inodes[position] = inode;
  g_overlay_count++;
  return true;
}

static bool read_table_bytes(u32 offset, u8* out, u16 len) {
  const u32 base = table_address(g_active_bank);
  while(len != 0) {
    const u32 address = base + offset;
    const u32 cache_address = address & ~511UL;
    if(g_table_cache_address != cache_address) {
      if(!read_bytes(cache_address, g_table_cache, sizeof(g_table_cache))) return false;
      g_table_cache_address = cache_address;
    }
    const u16 in_cache = (u16) (address - cache_address);
    const u16 count = len < sizeof(g_table_cache) - in_cache
        ? len : (u16) (sizeof(g_table_cache) - in_cache);
    memcpy(out, g_table_cache + in_cache, count);
    out += count;
    offset += count;
    len = (u16) (len - count);
  }
  return true;
}

static bool get_inode(u16 id, Inode& out) {
  if(id >= g_geometry.max_nodes) return false;
  bool found = false;
  const int position = overlay_search(id, found);
  if(found) {
    out = g_overlay_inodes[position];
    return true;
  }
  u8 disk[storage_geometry::INODE_BYTES];
  if(!read_table_bytes((u32) id * storage_geometry::INODE_BYTES,
                       disk, sizeof(disk))) return false;
  out = deserialize_inode(disk);
  return true;
}

static CatalogMeta current_meta(void) {
  return g_meta;
}

static void invalidate_iteration_caches(void) {
  g_flat_cache_index = -1;
  g_child_cache_parent = NONE;
  g_child_cache_index = -1;
  g_child_cache_id = NONE;
}

static void txn_begin(Transaction& transaction) {
  transaction.meta = current_meta();
  transaction.count = 0;
}

static bool txn_get(const Transaction& transaction, u16 id, Inode& inode) {
  for(u8 i = 0; i < transaction.count; i++) {
    if(transaction.updates[i].id == id) {
      inode = transaction.updates[i].inode;
      return true;
    }
  }
  return get_inode(id, inode);
}

static bool txn_set(Transaction& transaction, u16 id, const Inode& inode) {
  if(id >= g_geometry.max_nodes) return false;
  for(u8 i = 0; i < transaction.count; i++) {
    if(transaction.updates[i].id == id) {
      transaction.updates[i].inode = inode;
      return true;
    }
  }
  if(transaction.count >= WAL_MAX_UPDATES) return false;
  transaction.updates[transaction.count].id = id;
  transaction.updates[transaction.count].inode = inode;
  transaction.count++;
  return true;
}

static u32 normalized_record_crc(u8* record, u16 size, u16 crc_offset, u8 state_offset) {
  const u8 saved_state = record[state_offset];
  u8 saved_crc[4];
  memcpy(saved_crc, record + crc_offset, sizeof(saved_crc));
  record[state_offset] = STATE_WRITING;
  memset(record + crc_offset, 0, sizeof(saved_crc));
  const u32 crc = ~crc32_bytes(record, size);
  record[state_offset] = saved_state;
  memcpy(record + crc_offset, saved_crc, sizeof(saved_crc));
  return crc;
}

static void encode_meta(u8* record, const CatalogMeta& meta) {
  put_le16(record, 10, meta.root_head);
  put_le16(record, 12, meta.total_count);
  put_le16(record, 14, meta.current_offset);
  put_le32(record, 16, meta.current_sector);
  put_le32(record, 20, meta.reserve_sector);
  put_le32(record, 24, meta.gc_cursor);
  put_le32(record, 28, meta.data_sequence);
  for(u8 i = 0; i < 6; i++) put_le16(record, (u16) (32 + i * 2), meta.type_count[i]);
}

static CatalogMeta decode_meta(const u8* record) {
  CatalogMeta meta;
  meta.root_head = get_le16(record, 10);
  meta.total_count = get_le16(record, 12);
  meta.current_offset = get_le16(record, 14);
  meta.current_sector = get_le32(record, 16);
  meta.reserve_sector = get_le32(record, 20);
  meta.gc_cursor = get_le32(record, 24);
  meta.data_sequence = get_le32(record, 28);
  for(u8 i = 0; i < 6; i++) meta.type_count[i] = get_le16(record, (u16) (32 + i * 2));
  return meta;
}

static bool checkpoint(void);
static bool load_catalog(void);

static u8 new_overlay_slots(const Transaction& transaction) {
  u8 added = 0;
  for(u8 i = 0; i < transaction.count; i++) {
    bool found = false;
    (void) overlay_search(transaction.updates[i].id, found);
    if(!found) added++;
  }
  return added;
}

static bool append_transaction(const Transaction& transaction) {
  const u8 records_per_bank = (u8) ((u32) storage_geometry::CATALOG_WAL_SECTORS *
      storage_geometry::PHYSICAL_SECTOR_SIZE / WAL_RECORD_SIZE);
  if(g_wal_sealed || g_wal_records >= records_per_bank ||
     g_overlay_count + new_overlay_slots(transaction) > OVERLAY_CAPACITY) {
    if(!checkpoint()) {
      (void) load_catalog();
      return false;
    }
  }

  u8 record[WAL_RECORD_SIZE];
  memset(record, 0xFF, sizeof(record));
  record[0] = 'W';
  record[1] = '5';
  record[2] = FORMAT_VERSION;
  record[3] = STATE_WRITING;
  const u32 next_sequence = g_wal_sequence + 1;
  put_le32(record, 4, next_sequence);
  record[8] = transaction.count;
  encode_meta(record, transaction.meta);
  u16 offset = 44;
  for(u8 i = 0; i < transaction.count; i++) {
    put_le16(record, offset, transaction.updates[i].id);
    serialize_inode(transaction.updates[i].inode, record + offset + 2);
    offset = (u16) (offset + 2 + storage_geometry::INODE_BYTES);
  }
  const u32 crc = normalized_record_crc(record, sizeof(record), 244, 3);
  put_le32(record, 244, crc);

  const u32 address = wal_address(g_active_bank) + (u32) g_wal_records * WAL_RECORD_SIZE;
  if(!write_bytes(address, record, sizeof(record)) ||
     !write_byte(address + 3, STATE_ACTIVE)) {
    g_wal_sealed = true;
    (void) load_catalog();
    return false;
  }

  for(u8 i = 0; i < transaction.count; i++) {
    if(!overlay_set(transaction.updates[i].id, transaction.updates[i].inode)) return false;
  }
  g_wal_sequence = next_sequence;
  g_meta = transaction.meta;
  g_wal_records++;
  invalidate_iteration_caches();
  return true;
}

static void encode_catalog_header(u8* header, u32 generation, u32 table_crc) {
  memset(header, 0xFF, CATALOG_HEADER_SIZE);
  header[0] = 'C';
  header[1] = '5';
  header[2] = 'C';
  header[3] = 'T';
  header[4] = FORMAT_VERSION;
  header[5] = STATE_WRITING;
  header[6] = CATALOG_HEADER_SIZE;
  put_le32(header, 8, generation);
  put_le32(header, 12, g_format_epoch);
  put_le16(header, 16, g_geometry.max_nodes);
  put_le32(header, 20, table_crc);
  put_le32(header, 24, g_wal_sequence);
  put_le16(header, 28, g_meta.root_head);
  put_le16(header, 30, g_meta.total_count);
  put_le16(header, 32, g_meta.current_offset);
  put_le32(header, 36, g_meta.current_sector);
  put_le32(header, 40, g_meta.reserve_sector);
  put_le32(header, 44, g_meta.gc_cursor);
  put_le32(header, 48, g_meta.data_sequence);
  for(u8 i = 0; i < 6; i++) put_le16(header, (u16) (52 + i * 2), g_meta.type_count[i]);
  put_le32(header, CATALOG_HEADER_CRC_OFFSET,
           normalized_record_crc(header, CATALOG_HEADER_SIZE,
                                 CATALOG_HEADER_CRC_OFFSET, 5));
}

static bool checkpoint(void) {
  const u8 destination = (u8) (g_active_bank ^ 1U);
  for(u16 sector = 0; sector < g_geometry.catalog_bank_sectors; sector++) {
    if(!erase_sector(bank_sector(destination) + sector)) return false;
  }

  u8 buffer[512];
  u8 disk_inode[storage_geometry::INODE_BYTES];
  u16 buffered = 0;
  u32 destination_address = table_address(destination);
  u32 crc = 0xFFFFFFFFUL;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode)) return false;
    serialize_inode(inode, disk_inode);
    u8 copied = 0;
    while(copied < sizeof(disk_inode)) {
      const u16 room = (u16) (sizeof(buffer) - buffered);
      const u16 count = (u16) ((sizeof(disk_inode) - copied < room)
          ? sizeof(disk_inode) - copied : room);
      memcpy(buffer + buffered, disk_inode + copied, count);
      buffered = (u16) (buffered + count);
      copied = (u8) (copied + count);
      if(buffered == sizeof(buffer)) {
        if(!write_bytes(destination_address, buffer, sizeof(buffer))) return false;
        crc = crc32_bytes(buffer, sizeof(buffer), crc);
        destination_address += sizeof(buffer);
        buffered = 0;
      }
    }
  }
  if(buffered != 0) {
    if(!write_bytes(destination_address, buffer, buffered)) return false;
    crc = crc32_bytes(buffer, buffered, crc);
  }
  crc = ~crc;

  u8 header[CATALOG_HEADER_SIZE];
  encode_catalog_header(header, g_catalog_generation + 1, crc);
  const u32 header_address = sector_address(bank_sector(destination));
  if(!write_bytes(header_address, header, sizeof(header)) ||
     !write_byte(header_address + 5, STATE_ACTIVE)) return false;

  g_active_bank = destination;
  g_catalog_generation++;
  g_overlay_count = 0;
  g_wal_records = 0;
  g_wal_sealed = false;
  g_table_cache_address = EMPTY_ADDRESS;
  invalidate_iteration_caches();
  return true;
}

static bool decode_catalog_header(u8 bank, u8* header, u32& generation,
                                  u32& wal_sequence, CatalogMeta& meta) {
  if(!read_bytes(sector_address(bank_sector(bank)), header, CATALOG_HEADER_SIZE)) return false;
  if(memcmp(header, "C5CT", 4) != 0 || header[4] != FORMAT_VERSION ||
     header[5] != STATE_ACTIVE || header[6] != CATALOG_HEADER_SIZE ||
     get_le32(header, 12) != g_format_epoch ||
     get_le16(header, 16) != g_geometry.max_nodes) return false;
  if(normalized_record_crc(header, CATALOG_HEADER_SIZE,
                          CATALOG_HEADER_CRC_OFFSET, 5) !=
     get_le32(header, CATALOG_HEADER_CRC_OFFSET)) return false;
  const u32 table_crc = ~crc32_flash(table_address(bank),
      (u32) g_geometry.max_nodes * storage_geometry::INODE_BYTES);
  if(table_crc != get_le32(header, 20)) return false;

  generation = get_le32(header, 8);
  wal_sequence = get_le32(header, 24);
  meta.root_head = get_le16(header, 28);
  meta.total_count = get_le16(header, 30);
  meta.current_offset = get_le16(header, 32);
  meta.current_sector = get_le32(header, 36);
  meta.reserve_sector = get_le32(header, 40);
  meta.gc_cursor = get_le32(header, 44);
  meta.data_sequence = get_le32(header, 48);
  for(u8 i = 0; i < 6; i++) meta.type_count[i] = get_le16(header, (u16) (52 + i * 2));
  return generation != 0;
}

static bool generation_newer(u32 left, u32 right) {
  return (i32) (left - right) > 0;
}

static bool replay_wal(void) {
  const u8 records_per_bank = (u8) ((u32) storage_geometry::CATALOG_WAL_SECTORS *
      storage_geometry::PHYSICAL_SECTOR_SIZE / WAL_RECORD_SIZE);
  g_wal_records = 0;
  g_wal_sealed = false;
  for(u8 record_index = 0; record_index < records_per_bank; record_index++) {
    u8 record[WAL_RECORD_SIZE];
    if(!read_bytes(wal_address(g_active_bank) + (u32) record_index * WAL_RECORD_SIZE,
                   record, sizeof(record))) return false;
    bool erased = true;
    for(u8 i = 0; i < 8; i++) if(record[i] != 0xFF) erased = false;
    if(erased) break;
    if(record[0] != 'W' || record[1] != '5' || record[2] != FORMAT_VERSION ||
       record[3] != STATE_ACTIVE || record[8] > WAL_MAX_UPDATES ||
       normalized_record_crc(record, sizeof(record), 244, 3) != get_le32(record, 244)) {
      g_wal_sealed = true;
      break;
    }
    const u32 sequence = get_le32(record, 4);
    if(!generation_newer(sequence, g_wal_sequence)) {
      g_wal_sealed = true;
      break;
    }

    u16 offset = 44;
    for(u8 i = 0; i < record[8]; i++) {
      const u16 id = get_le16(record, offset);
      if(id >= g_geometry.max_nodes) return false;
      if(!overlay_set(id, deserialize_inode(record + offset + 2))) return false;
      offset = (u16) (offset + 2 + storage_geometry::INODE_BYTES);
    }
    g_meta = decode_meta(record);
    g_wal_sequence = sequence;
    g_wal_records++;
  }
  return true;
}

static bool load_catalog(void) {
  u8 header_a[CATALOG_HEADER_SIZE];
  u8 header_b[CATALOG_HEADER_SIZE];
  u32 generation_a = 0;
  u32 generation_b = 0;
  u32 sequence_a = 0;
  u32 sequence_b = 0;
  CatalogMeta meta_a;
  CatalogMeta meta_b;
  const bool valid_a = decode_catalog_header(0, header_a, generation_a, sequence_a, meta_a);
  const bool valid_b = decode_catalog_header(1, header_b, generation_b, sequence_b, meta_b);
  if(!valid_a && !valid_b) return false;

  if(valid_b && (!valid_a || generation_newer(generation_b, generation_a))) {
    g_active_bank = 1;
    g_catalog_generation = generation_b;
    g_wal_sequence = sequence_b;
    g_meta = meta_b;
  } else {
    g_active_bank = 0;
    g_catalog_generation = generation_a;
    g_wal_sequence = sequence_a;
    g_meta = meta_a;
  }
  g_overlay_count = 0;
  g_table_cache_address = EMPTY_ADDRESS;
  return replay_wal();
}

static void encode_locator(u8* locator) {
  memset(locator, 0xFF, LOCATOR_SIZE);
  memcpy(locator, "C5FS", 4);
  locator[4] = FORMAT_VERSION;
  locator[5] = STATE_WRITING;
  locator[6] = LOCATOR_SIZE;
  put_le32(locator, 8, g_geometry.capacity_bytes);
  put_le32(locator, 12, g_format_epoch);
  put_le16(locator, 16, g_geometry.max_nodes);
  locator[18] = g_geometry.sectors_per_cluster;
  put_le32(locator, 20, g_geometry.physical_sectors);
  put_le32(locator, 24, g_geometry.catalog_a_sector);
  put_le32(locator, 28, g_geometry.catalog_b_sector);
  put_le16(locator, 32, g_geometry.catalog_table_sectors);
  put_le16(locator, 34, g_geometry.catalog_bank_sectors);
  put_le32(locator, 36, g_geometry.data_first_sector);
  put_le32(locator, 40, g_geometry.data_sector_count);
  put_le32(locator, 44, g_geometry.stage_first_sector);
  put_le16(locator, 48, g_geometry.stage_sector_count);
  put_le32(locator, 52, g_geometry.settings_sector);
  put_le32(locator, 56, g_geometry.logical_sectors);
#ifdef SPI_FLASH
  put_le32(locator, 60, flash.capacityProbeUpper());
  put_le32(locator, 64, flash.getJEDECID());
#else
  put_le32(locator, 60, g_geometry.capacity_bytes);
  put_le32(locator, 64, 0);
#endif
  put_le32(locator, 68, normalized_record_crc(locator, LOCATOR_SIZE, 68, 5));
}

static bool locator_matches(const u8* locator, storage_geometry::Geometry& geometry,
                            u32& epoch, u32& probe_upper, u32& jedec_id) {
  if(memcmp(locator, "C5FS", 4) != 0 || locator[4] != FORMAT_VERSION ||
     locator[5] != STATE_ACTIVE || locator[6] != LOCATOR_SIZE ||
     normalized_record_crc((u8*) locator, LOCATOR_SIZE, 68, 5) != get_le32(locator, 68)) return false;
  if(!storage_geometry::compute(get_le32(locator, 8), geometry)) return false;
  if(geometry.max_nodes != get_le16(locator, 16) ||
     geometry.sectors_per_cluster != locator[18] ||
     geometry.physical_sectors != get_le32(locator, 20) ||
     geometry.catalog_a_sector != get_le32(locator, 24) ||
     geometry.catalog_b_sector != get_le32(locator, 28) ||
     geometry.catalog_table_sectors != get_le16(locator, 32) ||
     geometry.catalog_bank_sectors != get_le16(locator, 34) ||
     geometry.data_first_sector != get_le32(locator, 36) ||
     geometry.data_sector_count != get_le32(locator, 40) ||
     geometry.stage_first_sector != get_le32(locator, 44) ||
     geometry.stage_sector_count != get_le16(locator, 48) ||
     geometry.settings_sector != get_le32(locator, 52) ||
     geometry.logical_sectors != get_le32(locator, 56)) return false;
  epoch = get_le32(locator, 12);
  probe_upper = get_le32(locator, 60);
  jedec_id = get_le32(locator, 64);
  return epoch != 0;
}

// A firmware update may deliberately change the derived C5/FAT geometry while
// the physical chip and its settings sector remain unchanged.  In that case
// the old catalog cannot be mounted, but rerunning the destructive capacity
// probe and erasing settings would be both unnecessary and surprising.  This
// narrower decoder trusts only a fully committed, CRC-protected locator plus
// the independently CRC-protected guard at the unchanged physical end.
static bool load_capacity_for_reformat(void) {
#ifndef SPI_FLASH
  return false;
#else
  u8 locator[LOCATOR_SIZE];
  const u32 probe_upper = flash.capacityProbeUpper();
  const u32 jedec_id = flash.getJEDECID();
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!read_bytes(sector_address(copy), locator, sizeof(locator)) ||
       memcmp(locator, "C5FS", 4) != 0 || locator[4] != FORMAT_VERSION ||
       locator[5] != STATE_ACTIVE || locator[6] != LOCATOR_SIZE ||
       normalized_record_crc(locator, LOCATOR_SIZE, 68, 5) !=
           get_le32(locator, 68) ||
       get_le32(locator, 60) != probe_upper ||
       get_le32(locator, 64) != jedec_id) continue;

    storage_geometry::Geometry geometry;
    const u32 capacity = get_le32(locator, 8);
    if(!storage_geometry::compute(capacity, geometry) ||
       get_le32(locator, 20) != geometry.physical_sectors ||
       get_le32(locator, 52) != geometry.settings_sector ||
       !flash.setCapacity(capacity) || !settings_guard_valid(geometry)) {
      continue;
    }
    return true;
  }
  return false;
#endif
}

static bool load_locator(void) {
  u8 locator[LOCATOR_SIZE];
  storage_geometry::Geometry geometry;
  u32 epoch = 0;
  u32 stored_probe_upper = 0;
  u32 stored_jedec_id = 0;
#ifdef SPI_FLASH
  const u32 probe_upper = flash.capacityProbeUpper();
  const u32 jedec_id = flash.getJEDECID();
#else
  const u32 probe_upper = 0;
  const u32 jedec_id = 0;
#endif
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!read_bytes(sector_address(copy), locator, sizeof(locator))) continue;
    if(!locator_matches(locator, geometry, epoch, stored_probe_upper,
                        stored_jedec_id)) continue;
    if(stored_jedec_id != jedec_id || stored_probe_upper != probe_upper ||
       !flash.setCapacity(geometry.capacity_bytes) ||
       !settings_guard_valid(geometry)) continue;
    g_geometry = geometry;
    g_format_epoch = epoch;
    return true;
  }
  return false;
}

static bool write_locators(void) {
  u8 locator[LOCATOR_SIZE];
  encode_locator(locator);
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!erase_sector(copy)) return false;
    const u32 address = sector_address(copy);
    if(!write_bytes(address, locator, sizeof(locator)) ||
       !write_byte(address + 5, STATE_ACTIVE)) return false;
  }
  return true;
}

static bool data_sector_header_valid(u32 sector) {
  u8 header[DATA_SECTOR_HEADER_SIZE];
  if(!read_bytes(sector_address(sector), header, sizeof(header))) return false;
  return memcmp(header, "C5D0", 4) == 0 && header[4] == FORMAT_VERSION &&
         header[5] == STATE_ACTIVE && get_le32(header, 8) == g_format_epoch;
}

static bool initialize_data_sector(u32 sector) {
  if(!erase_sector(sector)) return false;
  u8 header[DATA_SECTOR_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C5D0", 4);
  header[4] = FORMAT_VERSION;
  header[5] = STATE_WRITING;
  put_le32(header, 8, g_format_epoch);
  put_le32(header, 12, ++g_meta.data_sequence);
  const u32 address = sector_address(sector);
  return write_bytes(address, header, sizeof(header)) &&
         write_byte(address + 5, STATE_ACTIVE);
}

static bool data_sector_in_range(u32 sector) {
  return sector >= g_geometry.data_first_sector &&
         sector < g_geometry.data_first_sector + g_geometry.data_sector_count;
}

static bool sector_has_live_inode(u32 sector) {
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode)) continue;
    if(inode.address < EXTENT_ADDRESS &&
       inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE == sector) return true;
  }
  return false;
}

static bool range_erased(u32 address, u16 len) {
  u8 buffer[32];
  while(len != 0) {
    const u16 count = len < sizeof(buffer) ? len : sizeof(buffer);
    if(!read_bytes(address, buffer, count)) return false;
    for(u8 i = 0; i < count; i++) if(buffer[i] != 0xFF) return false;
    address += count;
    len = (u16) (len - count);
  }
  return true;
}

static bool select_reclaimable_sector(u32& out) {
  const u32 first = g_geometry.data_first_sector;
  const u32 count = g_geometry.data_sector_count;
  const u32 start = data_sector_in_range(g_meta.gc_cursor)
      ? g_meta.gc_cursor : first;

  // Mark liveness for 32 candidates per inode-table pass. The former
  // sector-first loop could scan the complete node table once for every data
  // sector near full capacity (quadratic worst case).
  for(u32 base = 0; base < count; base += GC_SCAN_WINDOW) {
    const u8 window = (u8) ((count - base < GC_SCAN_WINDOW)
        ? count - base : GC_SCAN_WINDOW);
    u32 live_mask = 0;
    for(u16 id = 0; id < g_geometry.max_nodes; id++) {
      Inode inode;
      if(!get_inode(id, inode) || !visible_inode(inode) ||
         inode.address >= EXTENT_ADDRESS) continue;
      const u32 sector = inode.address /
          storage_geometry::PHYSICAL_SECTOR_SIZE;
      if(!data_sector_in_range(sector)) continue;
      const u32 relative = (sector - first + count - (start - first)) % count;
      if(relative >= base && relative < base + window) {
        live_mask |= 1UL << (relative - base);
      }
    }
    for(u8 slot = 0; slot < window; slot++) {
      const u32 sector = first +
          (start - first + base + slot) % count;
      if(sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
         (live_mask & (1UL << slot)) != 0) continue;
      if(!initialize_data_sector(sector)) continue;
      out = sector;
      g_meta.gc_cursor = first + (sector - first + 1) % count;
      return true;
    }
  }
  return false;
}

static bool select_gc_victim(u32& out) {
  const u32 first = g_geometry.data_first_sector;
  const u32 count = g_geometry.data_sector_count;
  const u32 start = data_sector_in_range(g_meta.gc_cursor)
      ? g_meta.gc_cursor : first;
  const u8 window = (u8) (count < GC_SCAN_WINDOW ? count : GC_SCAN_WINDOW);
  u16 live_bytes[GC_SCAN_WINDOW] = {};

  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) ||
       inode.address >= EXTENT_ADDRESS) continue;
    const u32 sector = inode.address /
        storage_geometry::PHYSICAL_SECTOR_SIZE;
    if(!data_sector_in_range(sector)) continue;
    const u32 relative = (sector - first + count - (start - first)) % count;
    if(relative >= window) continue;
    const u32 sum = (u32) live_bytes[relative] + inode.record_len;
    live_bytes[relative] = sum > 0xFFFFU ? 0xFFFFU : (u16) sum;
  }

  u16 best_bytes = 0xFFFF;
  u32 best = EMPTY_ADDRESS;
  for(u8 slot = 0; slot < window; slot++) {
    const u32 sector = first + (start - first + slot) % count;
    if(sector == g_meta.current_sector || sector == g_meta.reserve_sector) {
      continue;
    }
    if(live_bytes[slot] < best_bytes) {
      best_bytes = live_bytes[slot];
      best = sector;
    }
  }
  if(best == EMPTY_ADDRESS) return false;
  out = best;
  return true;
}

static bool commit_meta_only(const CatalogMeta& meta) {
  Transaction transaction;
  txn_begin(transaction);
  transaction.meta = meta;
  return append_transaction(transaction);
}

static bool garbage_collect(void) {
  if(!data_sector_in_range(g_meta.reserve_sector) ||
     sector_has_live_inode(g_meta.reserve_sector)) {
    u32 replacement = EMPTY_ADDRESS;
    if(!select_reclaimable_sector(replacement)) return false;
    CatalogMeta meta = g_meta;
    meta.reserve_sector = replacement;
    if(!commit_meta_only(meta)) return false;
  }

  u32 victim = EMPTY_ADDRESS;
  if(!select_gc_victim(victim)) return false;

  shared_scratch::Lease scratch(shared_scratch::Owner::PROGRAM_STORE_GC,
                                shared_scratch::SIZE);
  if(!scratch.ok()) return false;
  u16* ids = (u16*) scratch.data();
  const u16 id_capacity = (u16) (scratch.size() / sizeof(u16));
  u16 id_count = 0;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) || inode.address >= EXTENT_ADDRESS) continue;
    if(inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE != victim) continue;
    if(id_count >= id_capacity) return false;
    ids[id_count++] = id;
  }

  const u32 destination = g_meta.reserve_sector;
  if(!initialize_data_sector(destination)) return false;
  u16 destination_offset = DATA_SECTOR_HEADER_SIZE;
  u8 copy_buffer[64];
  for(u16 index = 0; index < id_count;) {
    Transaction transaction;
    txn_begin(transaction);
    for(u8 batch = 0; batch < WAL_MAX_UPDATES && index < id_count;
        batch++, index++) {
      Inode inode;
      if(!get_inode(ids[index], inode) || inode.record_len == 0 ||
         (u32) destination_offset + inode.record_len >
             storage_geometry::PHYSICAL_SECTOR_SIZE) return false;
      const u32 new_address = sector_address(destination) + destination_offset;
      u32 source = inode.address;
      u16 remaining = inode.record_len;
      u32 target = new_address;
      while(remaining != 0) {
        const u16 copied = remaining < sizeof(copy_buffer)
            ? remaining : sizeof(copy_buffer);
        if(!read_bytes(source, copy_buffer, copied) ||
           !write_bytes(target, copy_buffer, copied)) return false;
        source += copied;
        target += copied;
        remaining = (u16) (remaining - copied);
      }
      inode.address = new_address;
      if(!txn_set(transaction, ids[index], inode)) return false;
      destination_offset = (u16) (destination_offset + inode.record_len);
    }
    if(!append_transaction(transaction)) return false;
  }

  CatalogMeta promoted = g_meta;
  promoted.current_sector = destination;
  promoted.current_offset = destination_offset;
  promoted.reserve_sector = EMPTY_ADDRESS;
  const u32 first = g_geometry.data_first_sector;
  promoted.gc_cursor = first +
      (victim - first + 1) % g_geometry.data_sector_count;
  if(!commit_meta_only(promoted)) return false;
  if(!erase_sector(victim)) return false;
  CatalogMeta reserved = g_meta;
  reserved.reserve_sector = victim;
  return commit_meta_only(reserved);
}

static bool ensure_record_space(u16 record_len, u32& address) {
  if(record_len > storage_geometry::PHYSICAL_SECTOR_SIZE - DATA_SECTOR_HEADER_SIZE) return false;
  for(u8 attempt = 0; attempt < 3; attempt++) {
    if(data_sector_in_range(g_meta.current_sector) &&
       data_sector_header_valid(g_meta.current_sector) &&
       (u32) g_meta.current_offset + record_len <= storage_geometry::PHYSICAL_SECTOR_SIZE) {
      address = sector_address(g_meta.current_sector) + g_meta.current_offset;
      if(range_erased(address, record_len)) return true;
      g_meta.current_sector = EMPTY_ADDRESS;
      g_meta.current_offset = 0;
    }

    u32 sector = EMPTY_ADDRESS;
    if(select_reclaimable_sector(sector)) {
      g_meta.current_sector = sector;
      g_meta.current_offset = DATA_SECTOR_HEADER_SIZE;
      continue;
    }
    if(!garbage_collect()) return false;
  }
  return false;
}

static u32 record_crc(NodeKind kind, ProgramType type, u16 id, u16 parent_id,
                      const char* name, const u8* data, u16 data_len) {
  u8 stable[11];
  stable[0] = (u8) kind;
  stable[1] = (u8) type;
  put_le16(stable, 2, id);
  put_le16(stable, 4, parent_id);
  put_le16(stable, 6, data_len);
  stable[8] = (u8) strlen(name);
  stable[9] = FORMAT_VERSION;
  stable[10] = 0x5A;
  u32 crc = crc32_bytes(stable, sizeof(stable));
  crc = crc32_bytes((const u8*) name, strlen(name), crc);
  if(data_len != 0) crc = crc32_bytes(data, data_len, crc);
  return ~crc;
}

static bool append_record(NodeKind kind, ProgramType type, u16 id, u16 parent_id,
                          const char* name, const u8* data, u16 data_len,
                          u32& address, u16& record_len) {
  const u8 name_len = (u8) strlen(name);
  record_len = (u16) (RECORD_HEADER_SIZE + name_len + data_len);
  if(!ensure_record_space(record_len, address)) return false;

  u8 header[RECORD_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  header[0] = 'R';
  header[1] = '5';
  header[2] = STATE_WRITING;
  header[3] = (u8) kind;
  put_le16(header, 4, id);
  put_le16(header, 6, parent_id);
  put_le16(header, 8, data_len);
  header[10] = name_len;
  header[11] = (u8) type;
  put_le32(header, 12, record_crc(kind, type, id, parent_id, name, data, data_len));
  if(!write_bytes(address, header, sizeof(header)) ||
     !write_bytes(address + RECORD_HEADER_SIZE, (const u8*) name, name_len) ||
     !write_bytes(address + RECORD_HEADER_SIZE + name_len, data, data_len) ||
     !write_byte(address + 2, STATE_ACTIVE)) return false;
  g_meta.current_offset = (u16) (g_meta.current_offset + record_len);
  return true;
}

static bool read_record_header(const Inode& inode, u16 expected_id, u8* header) {
  if(!visible_inode(inode) || inode.address >= EXTENT_ADDRESS || inode.record_len < RECORD_HEADER_SIZE ||
     !read_bytes(inode.address, header, RECORD_HEADER_SIZE)) return false;
  return header[0] == 'R' && header[1] == '5' && header[2] == STATE_ACTIVE &&
         header[3] == (u8) inode_kind(inode) && get_le16(header, 4) == expected_id &&
         get_le16(header, 6) == inode.parent_id && get_le16(header, 8) ==
             (inode_kind(inode) == NodeKind::FILE ? inode.data_len : 0) &&
         header[10] != 0 && header[10] < NAME_SIZE &&
         (u16) (RECORD_HEADER_SIZE + header[10] + get_le16(header, 8)) == inode.record_len;
}

static bool read_inode_name(u16 id, const Inode& inode, char* out) {
  u8 header[RECORD_HEADER_SIZE];
  if(out == NULL || !read_record_header(inode, id, header)) return false;
  if(!read_bytes(inode.address + RECORD_HEADER_SIZE, (u8*) out, header[10])) return false;
  out[header[10]] = 0;
  return hash_name(out) == inode.name_hash;
}

static bool verify_record_crc(u16 id, const Inode& inode, const char* name) {
  u8 header[RECORD_HEADER_SIZE];
  if(!read_record_header(inode, id, header)) return false;
  u8 stable[11];
  stable[0] = header[3];
  stable[1] = header[11];
  put_le16(stable, 2, id);
  put_le16(stable, 4, inode.parent_id);
  put_le16(stable, 6, get_le16(header, 8));
  stable[8] = header[10];
  stable[9] = FORMAT_VERSION;
  stable[10] = 0x5A;
  u32 crc = crc32_bytes(stable, sizeof(stable));
  crc = crc32_bytes((const u8*) name, strlen(name), crc);
  crc = crc32_flash(inode.address + RECORD_HEADER_SIZE + header[10],
                    get_le16(header, 8), crc);
  return ~crc == get_le32(header, 12);
}

static bool payload_equals(u16 id, const Inode& inode, const char* name,
                           const u8* data, u16 data_len) {
  if(inode_kind(inode) != NodeKind::FILE || inode.data_len != data_len ||
     !verify_record_crc(id, inode, name)) return false;
  u8 actual[64];
  u8 header[RECORD_HEADER_SIZE];
  if(!read_record_header(inode, id, header)) return false;
  const u32 address = inode.address + RECORD_HEADER_SIZE + header[10];
  u16 offset = 0;
  while(offset < data_len) {
    const u16 count = (u16) ((data_len - offset < sizeof(actual))
        ? data_len - offset : sizeof(actual));
    if(!read_bytes(address + offset, actual, count) ||
       memcmp(actual, data + offset, count) != 0) return false;
    offset = (u16) (offset + count);
  }
  return true;
}

static bool fill_entry(u16 id, const Inode& inode, Entry& out) {
  if(!visible_inode(inode) || !read_inode_name(id, inode, out.name)) return false;
  out.id = id;
  out.parent_id = inode.parent_id;
  out.kind = inode_kind(inode);
  out.type = inode_type(inode);
  out.data_len = out.kind == NodeKind::FILE ? inode.data_len : 0;
  return true;
}

static bool parent_valid(u16 parent_id) {
  if(parent_id == ROOT_ID) return true;
  Inode parent;
  return get_inode(parent_id, parent) && inode_used(parent) &&
         inode_kind(parent) == NodeKind::DIRECTORY;
}

static bool directory_child_depth(u16 parent_id, u8& child_depth) {
  child_depth = 1;
  u16 ancestor = parent_id;
  while(ancestor != ROOT_ID) {
    if(child_depth >= MAX_DIRECTORY_DEPTH) return false;
    Inode inode;
    if(!get_inode(ancestor, inode) || !visible_inode(inode) ||
       inode_kind(inode) != NodeKind::DIRECTORY) return false;
    ancestor = inode.parent_id;
    child_depth++;
  }
  return true;
}

static bool directory_subtree_height(u16 directory_id, u8& height) {
  height = 0;
  for(u16 candidate = 0; candidate < g_geometry.max_nodes; candidate++) {
    Inode inode;
    if(!get_inode(candidate, inode) || !visible_inode(inode) ||
       inode_kind(inode) != NodeKind::DIRECTORY) continue;
    u16 ancestor = candidate;
    u8 distance = 0;
    bool terminated = false;
    for(u8 guard = 0; guard <= MAX_DIRECTORY_DEPTH; guard++) {
      if(ancestor == directory_id) {
        if(distance > height) height = distance;
        terminated = true;
        break;
      }
      if(ancestor == ROOT_ID) {
        terminated = true;
        break;
      }
      Inode parent;
      if(!get_inode(ancestor, parent) || !visible_inode(parent) ||
         inode_kind(parent) != NodeKind::DIRECTORY) return false;
      ancestor = parent.parent_id;
      distance++;
    }
    if(!terminated) return false;
  }
  return true;
}

static bool child_head(const Transaction& transaction, u16 parent_id, u16& head) {
  if(parent_id == ROOT_ID) {
    head = transaction.meta.root_head;
    return true;
  }
  Inode parent;
  if(!txn_get(transaction, parent_id, parent) || inode_kind(parent) != NodeKind::DIRECTORY) return false;
  head = parent.first_child;
  return true;
}

static bool set_child_head(Transaction& transaction, u16 parent_id, u16 head) {
  if(parent_id == ROOT_ID) {
    transaction.meta.root_head = head;
    return true;
  }
  Inode parent;
  if(!txn_get(transaction, parent_id, parent) || inode_kind(parent) != NodeKind::DIRECTORY) return false;
  parent.first_child = head;
  return txn_set(transaction, parent_id, parent);
}

static bool link_at_head(Transaction& transaction, u16 id, Inode& inode, u16 parent_id) {
  u16 head = NONE;
  if(!child_head(transaction, parent_id, head)) return false;
  inode.parent_id = parent_id;
  inode.prev_sibling = NONE;
  inode.next_sibling = head;
  if(head != NONE) {
    Inode previous_head;
    if(!txn_get(transaction, head, previous_head) || !visible_inode(previous_head)) return false;
    previous_head.prev_sibling = id;
    if(!txn_set(transaction, head, previous_head)) return false;
  }
  return set_child_head(transaction, parent_id, id) && txn_set(transaction, id, inode);
}

static bool unlink_node(Transaction& transaction, u16 id, Inode& inode) {
  if(inode.prev_sibling != NONE) {
    Inode previous;
    if(!txn_get(transaction, inode.prev_sibling, previous)) return false;
    previous.next_sibling = inode.next_sibling;
    if(!txn_set(transaction, inode.prev_sibling, previous)) return false;
  } else if(!set_child_head(transaction, inode.parent_id, inode.next_sibling)) {
    return false;
  }
  if(inode.next_sibling != NONE) {
    Inode next;
    if(!txn_get(transaction, inode.next_sibling, next)) return false;
    next.prev_sibling = inode.prev_sibling;
    if(!txn_set(transaction, inode.next_sibling, next)) return false;
  }
  inode.prev_sibling = NONE;
  inode.next_sibling = NONE;
  return txn_set(transaction, id, inode);
}

static bool find_free_id(u16 preferred, u16& out) {
  if(preferred < g_geometry.max_nodes) {
    Inode inode;
    if(get_inode(preferred, inode) && !inode_used(inode)) {
      out = preferred;
      g_free_hint = (u16) ((preferred + 1U) % g_geometry.max_nodes);
      return true;
    }
    return false;
  }
  const u16 start = g_free_hint < g_geometry.max_nodes ? g_free_hint : 0;
  for(u16 step = 0; step < g_geometry.max_nodes; step++) {
    const u16 id = (u16) ((start + step) % g_geometry.max_nodes);
    Inode inode;
    if(get_inode(id, inode) && !inode_used(inode)) {
      out = id;
      g_free_hint = (u16) ((id + 1U) % g_geometry.max_nodes);
      return true;
    }
  }
  return false;
}

static bool same_child_key(u16 id, const Inode& inode, NodeKind kind,
                           ProgramType type, const char* name) {
  if(!visible_inode(inode) || inode_kind(inode) != kind || inode.name_hash != hash_name(name)) return false;
  if(kind == NodeKind::FILE && inode_type(inode) != type) return false;
  char stored[NAME_SIZE];
  return read_inode_name(id, inode, stored) && strncmp(stored, name, NAME_SIZE) == 0;
}

static bool find_child_id(u16 parent_id, NodeKind kind, ProgramType type,
                          const char* name, u16& out) {
  if(!parent_valid(parent_id)) return false;
  u16 id = parent_id == ROOT_ID ? g_meta.root_head : NONE;
  if(parent_id != ROOT_ID) {
    Inode parent;
    if(!get_inode(parent_id, parent)) return false;
    id = parent.first_child;
  }
  for(u16 guard = 0; id != NONE && guard < g_geometry.max_nodes; guard++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) || inode.parent_id != parent_id) return false;
    if(same_child_key(id, inode, kind, type, name)) {
      out = id;
      return true;
    }
    id = inode.next_sibling;
  }
  return false;
}

static void fat_visible_name(NodeKind kind, ProgramType type,
                             const char* name, char* out) {
  strcpy(out, name);
  if(kind != NodeKind::FILE) return;
  const usize length = strlen(out);
  out[length] = '.';
  strcpy(out + length + 1, extension_for_type(type));
}

static bool fat_name_available(u16 parent_id, NodeKind kind,
                               ProgramType type, const char* name,
                               u16 ignore_id) {
  char wanted[NAME_SIZE + 16];
  fat_visible_name(kind, type, name, wanted);
  u16 root_slots = storage_geometry::ROOT_SYSTEM_DIRENTS;
  u16 id = parent_id == ROOT_ID ? g_meta.root_head : NONE;
  if(parent_id != ROOT_ID) {
    Inode parent;
    if(!get_inode(parent_id, parent) || inode_kind(parent) != NodeKind::DIRECTORY) {
      return false;
    }
    id = parent.first_child;
  }
  for(u16 guard = 0; id != NONE && guard < g_geometry.max_nodes; guard++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) ||
       inode.parent_id != parent_id) return false;
    if(id != ignore_id) {
      char stored[NAME_SIZE];
      char visible[NAME_SIZE + 16];
      if(!read_inode_name(id, inode, stored)) return false;
      fat_visible_name(inode_kind(inode), inode_type(inode), stored, visible);
      if(parent_id == ROOT_ID) {
        const u16 slots = fat_name::dirent_count(visible);
        if(slots == 0 || slots > g_geometry.root_entries ||
           root_slots > g_geometry.root_entries - slots) {
          return false;
        }
        root_slots = (u16) (root_slots + slots);
      }
      if(fat_name::equal(wanted, visible)) return false;
    }
    id = inode.next_sibling;
  }
  if(id != NONE) return false;
  if(parent_id != ROOT_ID) return true;
  const u16 wanted_slots = fat_name::dirent_count(wanted);
  return wanted_slots != 0 && wanted_slots <= g_geometry.root_entries &&
         root_slots <= g_geometry.root_entries - wanted_slots;
}

static bool find_global_file(ProgramType type, const char* name, u16& out) {
  const u16 wanted_hash = hash_name(name);
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || inode_kind(inode) != NodeKind::FILE ||
       inode_type(inode) != type || inode.name_hash != wanted_hash) continue;
    char stored[NAME_SIZE];
    if(read_inode_name(id, inode, stored) && strncmp(stored, name, NAME_SIZE) == 0) {
      out = id;
      return true;
    }
  }
  return false;
}

static bool format_internal(bool erase_settings) {
#ifdef SPI_FLASH
  const u32 capacity = flash.getCapacity();
#else
  const u32 capacity = 0;
#endif
  if(!storage_geometry::compute(capacity, g_geometry)) return false;
  g_format_epoch = 0xC5F50001UL ^ capacity ^ millis();
  if(g_format_epoch == 0 || g_format_epoch == 0xFFFFFFFFUL) g_format_epoch ^= 0x13579BDFUL;
  g_ready = false;
  g_active_bank = 1;
  g_catalog_generation = 0;
  g_wal_sequence = 0;
  g_wal_records = 0;
  g_wal_sealed = false;
  g_overlay_count = 0;
  g_free_hint = 0;
  g_table_cache_address = EMPTY_ADDRESS;
  memset(&g_meta, 0, sizeof(g_meta));
  g_meta.root_head = NONE;
  g_meta.current_sector = EMPTY_ADDRESS;
  g_meta.current_offset = 0;
  g_meta.reserve_sector = g_geometry.data_first_sector + g_geometry.data_sector_count - 1;
  g_meta.gc_cursor = g_geometry.data_first_sector;
  g_meta.data_sequence = 0;

  for(u8 bank = 0; bank < storage_geometry::CATALOG_BANKS; bank++) {
    for(u16 sector = 0; sector < g_geometry.catalog_bank_sectors; sector++) {
      if(!erase_sector(bank_sector(bank) + sector)) return false;
    }
  }
  if(!checkpoint()) return false;
  for(u16 sector = 0; sector < g_geometry.stage_sector_count; sector++) {
    if(!erase_sector(g_geometry.stage_first_sector + sector)) return false;
  }
  if(erase_settings) {
    if(!erase_sector(g_geometry.settings_sector) || !write_settings_guard()) return false;
  } else if(!settings_guard_valid(g_geometry)) {
    return false;
  }
  if(!write_locators()) return false;
  g_ready = true;
  return true;
}

} // namespace

void init(void) {
  DiskActivity activity;
  g_ready = false;
  g_free_hint = 0;
  memset(&g_geometry, 0, sizeof(g_geometry));
  if(!flash_is_ok) return;
  if(!load_locator()) {
    const bool preserve_settings = load_capacity_for_reformat();
    u32 capacity = 0;
#ifdef SPI_FLASH
    if(!preserve_settings &&
       (!flash_capacity_probe::detect(flash, flash.capacityProbeUpper(), capacity) ||
        !flash.setCapacity(capacity))) return;
#endif
    (void) format_internal(!preserve_settings);
  } else if(!load_catalog()) {
    (void) format_internal(false);
  } else {
    g_ready = true;
  }
  if(g_ready) vfat_stage_clear();
}

bool format(void) {
  DiskActivity activity;
  return flash_is_ok && format_internal(false) && (vfat_stage_clear(), true);
}

bool refresh(void) {
  init();
  return g_ready;
}

bool ready(void) { return g_ready; }

const storage_geometry::Geometry& geometry(void) { return g_geometry; }

u16 max_nodes(void) { return g_ready ? g_geometry.max_nodes : 0; }

u16 used_nodes(void) {
  if(!g_ready) return 0;
  u16 used = 0;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(get_inode(id, inode) && inode_used(inode)) used++;
  }
  return used;
}

bool basename_valid(const char* name) { return valid_name(name); }

u32 settings_address(void) {
  return g_ready ? sector_address(g_geometry.settings_sector) : 0;
}

u16 settings_size(void) {
  return g_ready ? SETTINGS_JOURNAL_SIZE : 0;
}

bool erase_settings(void) {
  DiskActivity activity;
  return g_ready && erase_sector(g_geometry.settings_sector) &&
         write_settings_guard();
}

const char* file_extension(ProgramType type) {
  return extension_for_type(type);
}

int total_count(void) { return g_ready ? g_meta.total_count : 0; }

int count(ProgramType type) {
  const int index = type_index(type);
  return g_ready && index >= 0 ? g_meta.type_count[index] : 0;
}

bool entry_by_id(u16 id, Entry& out) {
  if(!g_ready) return false;
  Inode inode;
  return get_inode(id, inode) && fill_entry(id, inode, out);
}

bool entry_at(int index, Entry& out) {
  if(!g_ready || index < 0 || index >= g_meta.total_count) return false;
  int seen = -1;
  u16 start = 0;
  if(g_flat_cache_index >= 0 && index >= g_flat_cache_index) {
    seen = g_flat_cache_index - 1;
    start = g_flat_cache_id;
  }
  for(u16 id = start; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode)) continue;
    if(++seen != index) continue;
    if(!fill_entry(id, inode, out)) return false;
    g_flat_cache_index = index + 1;
    g_flat_cache_id = (u16) (id + 1);
    return true;
  }
  return false;
}

bool entry(ProgramType type, int index, Entry& out) {
  if(!g_ready || index < 0) return false;
  int seen = 0;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || inode_kind(inode) != NodeKind::FILE ||
       inode_type(inode) != type) continue;
    if(seen++ == index) return fill_entry(id, inode, out);
  }
  return false;
}

int child_count(u16 parent_id) {
  if(!g_ready || !parent_valid(parent_id)) return 0;
  int result = 0;
  u16 id = parent_id == ROOT_ID ? g_meta.root_head : NONE;
  if(parent_id != ROOT_ID) {
    Inode parent;
    if(!get_inode(parent_id, parent)) return 0;
    id = parent.first_child;
  }
  for(u16 guard = 0; id != NONE && guard < g_geometry.max_nodes; guard++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) || inode.parent_id != parent_id) break;
    result++;
    id = inode.next_sibling;
  }
  return result;
}

bool child(u16 parent_id, int index, Entry& out) {
  if(!g_ready || index < 0 || !parent_valid(parent_id)) return false;
  u16 id = parent_id == ROOT_ID ? g_meta.root_head : NONE;
  int seen = 0;
  if(parent_id != ROOT_ID) {
    Inode parent;
    if(!get_inode(parent_id, parent)) return false;
    id = parent.first_child;
  }
  if(g_child_cache_parent == parent_id && g_child_cache_index >= 0 &&
     index >= g_child_cache_index) {
    id = g_child_cache_id;
    seen = g_child_cache_index;
  }
  for(u16 guard = 0; id != NONE && guard < g_geometry.max_nodes; guard++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) || inode.parent_id != parent_id) return false;
    if(seen++ == index) {
      if(!fill_entry(id, inode, out)) return false;
      g_child_cache_parent = parent_id;
      g_child_cache_index = seen;
      g_child_cache_id = inode.next_sibling;
      return true;
    }
    id = inode.next_sibling;
  }
  return false;
}

bool exists(ProgramType type, const char* name) {
  u16 id = NONE;
  return g_ready && valid_name(name) && find_global_file(type, name, id);
}

bool create_directory(u16 parent_id, const char* name, u16 preferred_id,
                      u16* out_id) {
  DiskActivity activity;
  if(!g_ready || !valid_name(name) || !parent_valid(parent_id)) return false;
  u8 depth = 0;
  if(!directory_child_depth(parent_id, depth)) return false;
  u16 named_id = NONE;
  const bool named = find_child_id(parent_id, NodeKind::DIRECTORY,
                                   ProgramType::MK61, name, named_id);
  if(preferred_id < g_geometry.max_nodes) {
    Inode preferred;
    if(!get_inode(preferred_id, preferred)) return false;
    if(inode_used(preferred)) {
      if(inode_kind(preferred) != NodeKind::DIRECTORY ||
         (named && named_id != preferred_id)) return false;
      char old_name[NAME_SIZE];
      if(!read_inode_name(preferred_id, preferred, old_name)) return false;
      if((preferred.parent_id != parent_id || strcmp(old_name, name) != 0) &&
         !move_rename(preferred_id, parent_id, name)) return false;
      if(out_id != NULL) *out_id = preferred_id;
      return true;
    }
    if(named) return false;
  } else if(named) {
    if(out_id != NULL) *out_id = named_id;
    return true;
  }
  if(!fat_name_available(parent_id, NodeKind::DIRECTORY,
                         ProgramType::MK61, name, preferred_id)) return false;
  u16 id = NONE;
  if(!find_free_id(preferred_id, id)) return false;
  u32 address = 0;
  u16 record_len = 0;
  if(!append_record(NodeKind::DIRECTORY, ProgramType::MK61, id, parent_id,
                    name, NULL, 0, address, record_len)) return false;
  Inode inode = empty_inode();
  inode.address = address;
  inode.data_len = NONE; // first directory extent
  inode.record_len = record_len;
  inode.parent_id = parent_id;
  inode.first_child = NONE;
  inode.next_sibling = NONE;
  inode.prev_sibling = NONE;
  inode.name_hash = hash_name(name);
  inode.kind_type = make_kind_type(NodeKind::DIRECTORY, ProgramType::MK61);
  inode.flags = 0;

  Transaction transaction;
  txn_begin(transaction);
  transaction.meta.total_count++;
  if(!link_at_head(transaction, id, inode, parent_id) ||
     !append_transaction(transaction)) return false;
  if(out_id != NULL) *out_id = id;
  return true;
}

bool write_file(u16 parent_id, u16 preferred_id, ProgramType type,
                const char* name, const u8* data, u16 data_len, u16* out_id) {
  DiskActivity activity;
  if(!g_ready || !supported_type(type) || !valid_name(name) || !parent_valid(parent_id) ||
     data_len > (type == ProgramType::FONT ? MAX_FONT_SIZE : MAX_MK61_TEXT_SIZE) ||
     (data_len != 0 && data == NULL)) return false;
  u16 named_id = NONE;
  const bool named = find_child_id(parent_id, NodeKind::FILE, type, name,
                                   named_id);
  u16 id = NONE;
  Inode old_inode = empty_inode();
  bool replacing = false;
  if(preferred_id < g_geometry.max_nodes) {
    if(!get_inode(preferred_id, old_inode)) return false;
    if(inode_used(old_inode)) {
      if(inode_kind(old_inode) != NodeKind::FILE ||
         (named && named_id != preferred_id)) return false;
      id = preferred_id;
      replacing = true;
    } else {
      if(named) return false;
      id = preferred_id;
    }
  } else if(named) {
    id = named_id;
    if(!get_inode(id, old_inode)) return false;
    replacing = true;
  } else if(!find_free_id(INVALID_ID, id)) {
    return false;
  }
  if(!fat_name_available(parent_id, NodeKind::FILE, type, name, id)) {
    return false;
  }

  char old_name[NAME_SIZE] = {};
  if(replacing) {
    if(!read_inode_name(id, old_inode, old_name)) return false;
    if(old_inode.parent_id == parent_id && inode_type(old_inode) == type &&
       strcmp(old_name, name) == 0 &&
       payload_equals(id, old_inode, name, data, data_len)) {
      if(out_id != NULL) *out_id = id;
      return true;
    }
  }

  u32 address = 0;
  u16 record_len = 0;
  if(!append_record(NodeKind::FILE, type, id, parent_id, name, data, data_len,
                    address, record_len)) return false;
  Inode inode = replacing ? old_inode : empty_inode();
  inode.address = address;
  inode.data_len = data_len;
  inode.record_len = record_len;
  inode.parent_id = parent_id;
  inode.name_hash = hash_name(name);
  inode.kind_type = make_kind_type(NodeKind::FILE, type);
  inode.flags = 0;
  if(!replacing) {
    inode.first_child = NONE;
    inode.next_sibling = NONE;
    inode.prev_sibling = NONE;
  }

  Transaction transaction;
  txn_begin(transaction);
  if(replacing) {
    const int old_type_index = type_index(inode_type(old_inode));
    const int new_type_index = type_index(type);
    if(old_type_index != new_type_index) {
      if(old_type_index >= 0 && transaction.meta.type_count[old_type_index] != 0) {
        transaction.meta.type_count[old_type_index]--;
      }
      transaction.meta.type_count[new_type_index]++;
    }
    if(old_inode.parent_id != parent_id) {
      Inode unlinked = old_inode;
      if(!unlink_node(transaction, id, unlinked)) return false;
      inode.prev_sibling = NONE;
      inode.next_sibling = NONE;
      if(!link_at_head(transaction, id, inode, parent_id)) return false;
    } else if(!txn_set(transaction, id, inode)) {
      return false;
    }
  } else {
    transaction.meta.total_count++;
    const int index = type_index(type);
    transaction.meta.type_count[index]++;
    if(!link_at_head(transaction, id, inode, parent_id)) return false;
  }
  if(!append_transaction(transaction)) return false;
  if(out_id != NULL) *out_id = id;
  return true;
}

bool write(ProgramType type, const char* name, const u8* data, u16 data_len) {
  return write_file(ROOT_ID, INVALID_ID, type, name, data, data_len, NULL);
}

bool write_from_usb(ProgramType type, const char* name, const u8* data, u16 data_len) {
  return write(type, name, data, data_len);
}

bool read_range_id(u16 id, u16 offset, u8* data, u16 len, u16* out_len) {
  DiskActivity activity;
  if(!g_ready || data == NULL) return false;
  Inode inode;
  char name[NAME_SIZE];
  if(!get_inode(id, inode) || inode_kind(inode) != NodeKind::FILE ||
     offset > inode.data_len || !read_inode_name(id, inode, name) ||
     !verify_record_crc(id, inode, name)) return false;
  const u16 available = (u16) (inode.data_len - offset);
  const u16 copied = available < len ? available : len;
  u8 header[RECORD_HEADER_SIZE];
  if(!read_record_header(inode, id, header)) return false;
  if(copied != 0 && !read_bytes(inode.address + RECORD_HEADER_SIZE + header[10] + offset,
                                data, copied)) return false;
  if(out_len != NULL) *out_len = copied;
  return true;
}

bool read_id(u16 id, u8* data, u16 capacity, u16* out_len) {
  Inode inode;
  if(!g_ready || !get_inode(id, inode) || inode_kind(inode) != NodeKind::FILE ||
     capacity < inode.data_len) return false;
  u16 copied = 0;
  if(!read_range_id(id, 0, data, inode.data_len, &copied) || copied != inode.data_len) return false;
  if(out_len != NULL) *out_len = copied;
  return true;
}

bool read_range(ProgramType type, const char* name, u16 offset, u8* data,
                u16 len, u16* out_len) {
  u16 id = NONE;
  return find_global_file(type, name, id) && read_range_id(id, offset, data, len, out_len);
}

bool read(ProgramType type, const char* name, u8* data, u16 capacity, u16* out_len) {
  u16 id = NONE;
  return find_global_file(type, name, id) && read_id(id, data, capacity, out_len);
}

bool remove_id(u16 id) {
  DiskActivity activity;
  if(!g_ready) return false;
  Inode inode;
  if(!get_inode(id, inode) || !visible_inode(inode)) return false;
  if(inode_kind(inode) == NodeKind::DIRECTORY && inode.first_child != NONE) return false;

  // Directory extents are released from the tail before the inode itself.
  if(inode_kind(inode) == NodeKind::DIRECTORY) {
    while(inode.data_len != NONE) {
      u16 extent = inode.data_len;
      Inode extent_inode;
      while(get_inode(extent, extent_inode) && extent_inode.next_sibling != NONE) {
        extent = extent_inode.next_sibling;
      }
      if(!release_directory_extent(extent) || !get_inode(id, inode)) return false;
    }
  }

  Transaction transaction;
  txn_begin(transaction);
  if(!unlink_node(transaction, id, inode)) return false;
  transaction.meta.total_count--;
  if(inode_kind(inode) == NodeKind::FILE) {
    const int index = type_index(inode_type(inode));
    if(index >= 0 && transaction.meta.type_count[index] != 0) transaction.meta.type_count[index]--;
  }
  if(!txn_set(transaction, id, empty_inode())) return false;
  if(!append_transaction(transaction)) return false;
  if(g_free_hint >= g_geometry.max_nodes || id < g_free_hint) g_free_hint = id;
  return true;
}

bool remove_tree(u16 id, u16* removed) {
  DiskActivity activity;
  if(removed != NULL) *removed = 0;
  if(!g_ready || id >= g_geometry.max_nodes) return false;
  Inode root;
  if(!get_inode(id, root) || !visible_inode(root)) return false;

  // Stack-free post-order deletion. MAX_DIRECTORY_DEPTH bounds corruption
  // checks, while following first_child after each committed removal means a
  // power cut can leave only a smaller, still-consistent subtree.
  u16 current = id;
  u16 count = 0;
  while(true) {
    Inode inode;
    if(!get_inode(current, inode) || !visible_inode(inode)) return false;
    if(inode_kind(inode) == NodeKind::DIRECTORY && inode.first_child != NONE) {
      current = inode.first_child;
      continue;
    }

    const u16 parent = inode.parent_id;
    const bool done = current == id;
    if(!remove_id(current)) return false;
    count++;
    if(done) {
      if(removed != NULL) *removed = count;
      return true;
    }
    current = parent;
  }
}

bool remove(ProgramType type, const char* name) {
  u16 id = NONE;
  return find_global_file(type, name, id) && remove_id(id);
}

bool move_rename(u16 id, u16 new_parent_id, const char* new_name) {
  DiskActivity activity;
  if(!g_ready || !valid_name(new_name) || !parent_valid(new_parent_id)) return false;
  Inode inode;
  if(!get_inode(id, inode) || !visible_inode(inode)) return false;
  if(inode_kind(inode) == NodeKind::DIRECTORY) {
    u8 new_depth = 0;
    u8 subtree_height = 0;
    if(!directory_child_depth(new_parent_id, new_depth) ||
       !directory_subtree_height(id, subtree_height) ||
       (u16) new_depth + subtree_height > MAX_DIRECTORY_DEPTH) return false;
    u16 ancestor = new_parent_id;
    for(u8 depth = 0; ancestor != ROOT_ID && depth < MAX_DIRECTORY_DEPTH; depth++) {
      if(ancestor == id) return false;
      Inode parent;
      if(!get_inode(ancestor, parent) || inode_kind(parent) != NodeKind::DIRECTORY) return false;
      ancestor = parent.parent_id;
    }
    if(ancestor != ROOT_ID) return false;
  }
  if(!fat_name_available(new_parent_id, inode_kind(inode), inode_type(inode),
                         new_name, id)) return false;

  shared_scratch::Lease scratch(shared_scratch::Owner::PROGRAM_STORE_RENAME,
                                inode_kind(inode) == NodeKind::FILE ? inode.data_len : 0);
  const u8* payload = NULL;
  if(inode_kind(inode) == NodeKind::FILE && inode.data_len != 0) {
    if(!scratch.ok()) return false;
    u16 len = 0;
    if(!read_id(id, scratch.data(), scratch.size(), &len) || len != inode.data_len) return false;
    payload = scratch.data();
  }
  u32 address = 0;
  u16 record_len = 0;
  if(!append_record(inode_kind(inode), inode_type(inode), id, new_parent_id,
                    new_name, payload,
                    inode_kind(inode) == NodeKind::FILE ? inode.data_len : 0,
                    address, record_len)) return false;

  Transaction transaction;
  txn_begin(transaction);
  if(inode.parent_id != new_parent_id) {
    if(!unlink_node(transaction, id, inode)) return false;
    inode.address = address;
    inode.record_len = record_len;
    inode.name_hash = hash_name(new_name);
    if(!link_at_head(transaction, id, inode, new_parent_id)) return false;
  } else {
    inode.address = address;
    inode.record_len = record_len;
    inode.name_hash = hash_name(new_name);
    if(!txn_set(transaction, id, inode)) return false;
  }
  return append_transaction(transaction);
}

bool rename(ProgramType type, const char* old_name, const char* new_name) {
  u16 id = NONE;
  Inode inode;
  return find_global_file(type, old_name, id) && get_inode(id, inode) &&
         move_rename(id, inode.parent_id, new_name);
}

bool allocate_directory_extent(u16 directory_id, u16 preferred_id) {
  DiskActivity activity;
  Inode directory;
  if(!g_ready || !get_inode(directory_id, directory) ||
     inode_kind(directory) != NodeKind::DIRECTORY) return false;
  u16 id = NONE;
  if(!find_free_id(preferred_id, id)) return false;
  u16 tail = NONE;
  if(directory.data_len != NONE) {
    tail = directory.data_len;
    Inode extent;
    for(u16 guard = 0; guard < g_geometry.max_nodes; guard++) {
      if(!get_inode(tail, extent) || inode_kind(extent) != NodeKind::DIRECTORY_EXTENT ||
         extent.parent_id != directory_id) return false;
      if(extent.next_sibling == NONE) break;
      tail = extent.next_sibling;
    }
  }
  Inode extent = empty_inode();
  extent.address = EXTENT_ADDRESS;
  extent.data_len = 0;
  extent.record_len = 0;
  extent.parent_id = directory_id;
  extent.first_child = NONE;
  extent.next_sibling = NONE;
  extent.prev_sibling = tail;
  extent.name_hash = 0;
  extent.kind_type = make_kind_type(NodeKind::DIRECTORY_EXTENT, ProgramType::MK61);
  extent.flags = 0;

  Transaction transaction;
  txn_begin(transaction);
  if(tail == NONE) {
    directory.data_len = id;
    if(!txn_set(transaction, directory_id, directory)) return false;
  } else {
    Inode previous;
    if(!txn_get(transaction, tail, previous)) return false;
    previous.next_sibling = id;
    if(!txn_set(transaction, tail, previous)) return false;
  }
  return txn_set(transaction, id, extent) && append_transaction(transaction);
}

bool release_directory_extent(u16 extent_id) {
  DiskActivity activity;
  Inode extent;
  if(!g_ready || !get_inode(extent_id, extent) ||
     inode_kind(extent) != NodeKind::DIRECTORY_EXTENT || extent.next_sibling != NONE) return false;
  Inode directory;
  if(!get_inode(extent.parent_id, directory) || inode_kind(directory) != NodeKind::DIRECTORY) return false;
  Transaction transaction;
  txn_begin(transaction);
  if(extent.prev_sibling == NONE) {
    directory.data_len = NONE;
    if(!txn_set(transaction, extent.parent_id, directory)) return false;
  } else {
    Inode previous;
    if(!txn_get(transaction, extent.prev_sibling, previous)) return false;
    previous.next_sibling = NONE;
    if(!txn_set(transaction, extent.prev_sibling, previous)) return false;
  }
  if(!txn_set(transaction, extent_id, empty_inode()) ||
     !append_transaction(transaction)) return false;
  if(g_free_hint >= g_geometry.max_nodes || extent_id < g_free_hint) {
    g_free_hint = extent_id;
  }
  return true;
}

bool first_extent(u16 directory_id, u16& out_id) {
  Inode directory;
  if(!g_ready || !get_inode(directory_id, directory) ||
     inode_kind(directory) != NodeKind::DIRECTORY || directory.data_len == NONE) return false;
  out_id = directory.data_len;
  return true;
}

bool next_extent(u16 id, u16& out_id) {
  Inode inode;
  if(!g_ready || !get_inode(id, inode)) return false;
  if(inode_kind(inode) == NodeKind::DIRECTORY) {
    if(inode.data_len == NONE) return false;
    out_id = inode.data_len;
    return true;
  }
  if(inode_kind(inode) != NodeKind::DIRECTORY_EXTENT || inode.next_sibling == NONE) return false;
  out_id = inode.next_sibling;
  return true;
}

bool extent_info(u16 extent_id, u16& directory_id, u16& next_id) {
  Inode inode;
  if(!g_ready || !get_inode(extent_id, inode) ||
     inode_kind(inode) != NodeKind::DIRECTORY_EXTENT) return false;
  directory_id = inode.parent_id;
  next_id = inode.next_sibling;
  return true;
}

u16 purge_empty(void) {
  u16 purged = 0;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(get_inode(id, inode) && inode_kind(inode) == NodeKind::FILE && inode.data_len == 0 &&
       remove_id(id)) purged++;
  }
  return purged;
}

bool write_mk61(const char* name, const u8* code, u16 code_len) {
  return write(ProgramType::MK61, name, code, code_len);
}

bool read_mk61(const char* name, u8* code, u16 capacity, u16* out_len) {
  return read(ProgramType::MK61, name, code, capacity, out_len);
}

// Persistent USB staging journal is implemented below.

namespace {

static u32 stage_sector_address(u16 sector) {
  return sector_address(g_geometry.stage_first_sector + sector);
}

static u32 stage_record_address(u16 ref) {
  if(ref == 0) return 0;
  ref--;
  const u16 sector = (u16) (ref / STAGE_RECORDS_PER_SECTOR);
  const u16 slot = (u16) (ref % STAGE_RECORDS_PER_SECTOR);
  return stage_sector_address(sector) + STAGE_SECTOR_HEADER_SIZE +
         (u32) slot * STAGE_RECORD_SIZE;
}

static u32 pack_stage_index(u32 key, u16 ref) {
  return (key << STAGE_REF_BITS) | ref;
}

static u32 stage_index_key(u16 index) {
  return g_stage_index[index] >> STAGE_REF_BITS;
}

static u16 stage_index_ref(u16 index) {
  return (u16) (g_stage_index[index] & STAGE_REF_MASK);
}

static int stage_ref_index(u32 key) {
  for(u16 i = 0; i < g_stage_ref_count; i++) {
    if(stage_index_key(i) == key) return i;
  }
  return -1;
}

static bool stage_sector_header_valid(u16 sector) {
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  if(!read_bytes(stage_sector_address(sector), header, sizeof(header))) return false;
  return memcmp(header, "C5S0", 4) == 0 && header[4] == FORMAT_VERSION &&
         header[5] == STATE_ACTIVE && get_le32(header, 8) == g_format_epoch;
}

static bool initialize_stage_sector(u16 sector) {
  if(!erase_sector(g_geometry.stage_first_sector + sector)) return false;
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C5S0", 4);
  header[4] = FORMAT_VERSION;
  header[5] = STATE_WRITING;
  put_le32(header, 8, g_format_epoch);
  put_le32(header, 12, ++g_meta.data_sequence);
  return write_bytes(stage_sector_address(sector), header, sizeof(header)) &&
         write_byte(stage_sector_address(sector) + 5, STATE_ACTIVE);
}

static u32 stage_crc(u32 key, u16 generation, const u8* data) {
  u8 prefix[6];
  put_le32(prefix, 0, key);
  put_le16(prefix, 4, generation);
  u32 crc = crc32_bytes(prefix, sizeof(prefix));
  return ~crc32_bytes(data, STAGE_DATA_SIZE, crc);
}

static bool read_stage_record(u16 ref, u32& key, u16& generation,
                              u32& crc, u8& state) {
  u8 header[STAGE_RECORD_HEADER_SIZE];
  if(!read_bytes(stage_record_address(ref), header, sizeof(header))) return false;
  if(header[0] != 'S' || header[1] != '5') return false;
  state = header[2];
  key = get_le32(header, 4);
  generation = get_le16(header, 8);
  crc = get_le32(header, 12);
  return true;
}

static bool stage_generation_newer(u16 left, u16 right) {
  return (i16) (left - right) > 0;
}

static bool stage_sector_has_live(u16 sector) {
  for(u16 i = 0; i < g_stage_ref_count; i++) {
    if((u16) ((stage_index_ref(i) - 1) / STAGE_RECORDS_PER_SECTOR) == sector) {
      return true;
    }
  }
  return false;
}

static u8 stage_sector_live_count(u16 sector) {
  u8 count = 0;
  for(u16 i = 0; i < g_stage_ref_count; i++) {
    if((u16) ((stage_index_ref(i) - 1) / STAGE_RECORDS_PER_SECTOR) == sector) {
      count++;
    }
  }
  return count;
}

static u16 normal_stage_sector_count(void) {
  return g_geometry.stage_sector_count > 1
      ? (u16) (g_geometry.stage_sector_count - 1) : 0;
}

static bool stage_slot_erased(u16 sector, u8 slot) {
  const u16 ref = (u16) (sector * STAGE_RECORDS_PER_SECTOR + slot + 1);
  u8 header[STAGE_RECORD_HEADER_SIZE];
  if(!read_bytes(stage_record_address(ref), header, sizeof(header))) return false;
  for(u8 i = 0; i < sizeof(header); i++) if(header[i] != 0xFF) return false;
  return true;
}

static bool append_stage_value(u16 sector, u32 key, const u8* data) {
  if(sector >= g_geometry.stage_sector_count || data == NULL ||
     g_stage_sealed[sector] || g_stage_used[sector] >= STAGE_RECORDS_PER_SECTOR) return false;
  if(!stage_sector_header_valid(sector)) {
    if(stage_sector_has_live(sector) || !initialize_stage_sector(sector)) return false;
    g_stage_used[sector] = 0;
    g_stage_sealed[sector] = 0;
  }
  const u8 slot = g_stage_used[sector];
  if(!stage_slot_erased(sector, slot)) {
    g_stage_sealed[sector] = 1;
    return false;
  }

  g_stage_generation++;
  if(g_stage_generation == 0) g_stage_generation = 1;
  const u16 ref = (u16) (sector * STAGE_RECORDS_PER_SECTOR + slot + 1);
  const u32 address = stage_record_address(ref);
  u8 record[STAGE_RECORD_SIZE];
  memset(record, 0xFF, STAGE_RECORD_HEADER_SIZE);
  record[0] = 'S';
  record[1] = '5';
  // The complete record is programmed as one verified stream. Recovery only
  // accepts ACTIVE records whose payload CRC matches, so a power cut during
  // any constituent NOR page program cannot supersede the previous version.
  record[2] = STATE_ACTIVE;
  put_le32(record, 4, key);
  put_le16(record, 8, g_stage_generation);
  put_le32(record, 12, stage_crc(key, g_stage_generation, data));
  memcpy(record + STAGE_RECORD_HEADER_SIZE, data, STAGE_DATA_SIZE);
  if(!write_bytes(address, record, sizeof(record))) {
    g_stage_sealed[sector] = 1;
    return false;
  }

  g_stage_used[sector] = (u8) (slot + 1);
  int index = stage_ref_index(key);
  const u16 old_ref = index < 0 ? 0 : stage_index_ref((u16) index);
  if(index < 0) {
    if(g_stage_ref_count >= STAGE_REF_CAPACITY) return false;
    index = g_stage_ref_count++;
  }
  g_stage_index[index] = pack_stage_index(key, ref);
  if(old_ref != 0) (void) write_byte(stage_record_address(old_ref) + 2,
                                      STATE_DELETED);
  return true;
}

static bool read_stage_ref_payload(u16 ref, u8* data) {
  u32 key = 0;
  u16 generation = 0;
  u32 crc = 0;
  u8 state = 0;
  return read_stage_record(ref, key, generation, crc, state) &&
         state == STATE_ACTIVE &&
         read_bytes(stage_record_address(ref) + STAGE_RECORD_HEADER_SIZE,
                    data, STAGE_DATA_SIZE) &&
         stage_crc(key, generation, data) == crc;
}

static bool copy_live_stage_records(u16 source, u16 destination) {
  u8 data[STAGE_DATA_SIZE];
  for(;;) {
    int index = -1;
    for(u16 i = 0; i < g_stage_ref_count; i++) {
      const u16 sector = (u16) ((stage_index_ref(i) - 1) /
                                STAGE_RECORDS_PER_SECTOR);
      if(sector == source) {
        index = (int) i;
        break;
      }
    }
    if(index < 0) return true;
    const u32 key = stage_index_key((u16) index);
    const u16 ref = stage_index_ref((u16) index);
    if(!read_stage_ref_payload(ref, data) ||
       !append_stage_value(destination, key, data)) return false;
  }
}

static bool erase_stage_sector(u16 sector) {
  if(!erase_sector(g_geometry.stage_first_sector + sector)) return false;
  g_stage_used[sector] = 0;
  g_stage_sealed[sector] = 0;
  return true;
}

// Completes any interrupted compaction. Copies always receive a newer
// generation before the old sector is erased, so every power cut leaves at
// least one valid version of every staged block.
static bool recover_stage_reserve(void) {
  const u16 normal_count = normal_stage_sector_count();
  if(normal_count == 0) return false;
  const u16 reserve = normal_count;
  u8 reserve_live = stage_sector_live_count(reserve);
  if(reserve_live == 0) return true;

  // The normal destination may already contain the first records copied back
  // before a reset. Finish that direction whenever its erased tail fits.
  for(u16 sector = 0; sector < normal_count; sector++) {
    if(stage_sector_has_live(sector) && !stage_sector_header_valid(sector)) continue;
    if(!stage_sector_header_valid(sector)) {
      if(!initialize_stage_sector(sector)) continue;
      g_stage_used[sector] = 0;
      g_stage_sealed[sector] = 0;
    }
    if(g_stage_sealed[sector] ||
       (u16) g_stage_used[sector] + reserve_live > STAGE_RECORDS_PER_SECTOR) continue;
    if(!copy_live_stage_records(reserve, sector)) return false;
    return erase_stage_sector(reserve);
  }

  // Otherwise the reset happened while the sparse victim was being copied
  // into the reserve. Finish that copy, erase the victim, then copy back.
  if(!stage_sector_header_valid(reserve) || g_stage_sealed[reserve]) return false;
  for(u16 victim = 0; victim < normal_count; victim++) {
    const u8 victim_live = stage_sector_live_count(victim);
    if((u16) g_stage_used[reserve] + victim_live > STAGE_RECORDS_PER_SECTOR) continue;
    if(!copy_live_stage_records(victim, reserve) ||
       !initialize_stage_sector(victim)) return false;
    g_stage_used[victim] = 0;
    g_stage_sealed[victim] = 0;
    if(!copy_live_stage_records(reserve, victim)) return false;
    return erase_stage_sector(reserve);
  }
  return false;
}

static bool compact_stage(u16& out_sector, u8& out_slot) {
  const u16 normal_count = normal_stage_sector_count();
  if(normal_count == 0 || !recover_stage_reserve()) return false;
  const u16 reserve = normal_count;
  if(!initialize_stage_sector(reserve)) return false;
  g_stage_used[reserve] = 0;
  g_stage_sealed[reserve] = 0;

  u16 victim = 0;
  u8 victim_live = 0xFF;
  for(u16 sector = 0; sector < normal_count; sector++) {
    const u8 live = stage_sector_live_count(sector);
    if(live < victim_live) {
      victim = sector;
      victim_live = live;
    }
  }
  if(victim_live >= STAGE_RECORDS_PER_SECTOR ||
     !copy_live_stage_records(victim, reserve) ||
     !initialize_stage_sector(victim)) return false;
  g_stage_used[victim] = 0;
  g_stage_sealed[victim] = 0;
  if(!copy_live_stage_records(reserve, victim) ||
     !erase_stage_sector(reserve) ||
     g_stage_used[victim] >= STAGE_RECORDS_PER_SECTOR) return false;
  out_sector = victim;
  out_slot = g_stage_used[victim];
  return true;
}

static bool find_stage_slot(u16& out_sector, u8& out_slot) {
  if(!recover_stage_reserve()) return false;
  const u16 normal_count = normal_stage_sector_count();
  for(u16 sector = 0; sector < normal_count; sector++) {
    if(g_stage_sealed[sector] || g_stage_used[sector] >= STAGE_RECORDS_PER_SECTOR) continue;
    if(!stage_sector_header_valid(sector)) {
      if(stage_sector_has_live(sector) || !initialize_stage_sector(sector)) continue;
      g_stage_used[sector] = 0;
      g_stage_sealed[sector] = 0;
    }
    if(!stage_slot_erased(sector, g_stage_used[sector])) {
      g_stage_sealed[sector] = 1;
      continue;
    }
    out_sector = sector;
    out_slot = g_stage_used[sector];
    return true;
  }

  for(u16 sector = 0; sector < normal_count; sector++) {
    if(stage_sector_has_live(sector)) continue;
    if(!initialize_stage_sector(sector)) continue;
    g_stage_used[sector] = 0;
    g_stage_sealed[sector] = 0;
    out_sector = sector;
    out_slot = 0;
    return true;
  }
  return compact_stage(out_sector, out_slot);
}

} // namespace

void vfat_stage_clear(void) {
  g_stage_ref_count = 0;
  g_stage_generation = 0;
  memset(g_stage_used, 0, sizeof(g_stage_used));
  memset(g_stage_sealed, 0, sizeof(g_stage_sealed));
  if(!g_ready) return;

  u8 payload[STAGE_DATA_SIZE];
  for(u16 sector = 0; sector < g_geometry.stage_sector_count; sector++) {
    if(!stage_sector_header_valid(sector)) continue;
    for(u8 slot = 0; slot < STAGE_RECORDS_PER_SECTOR; slot++) {
      const u16 ref = (u16) (sector * STAGE_RECORDS_PER_SECTOR + slot + 1);
      u8 raw[STAGE_RECORD_HEADER_SIZE];
      if(!read_bytes(stage_record_address(ref), raw, sizeof(raw))) break;
      bool erased = true;
      for(u8 i = 0; i < sizeof(raw); i++) if(raw[i] != 0xFF) erased = false;
      if(erased) break;
      g_stage_used[sector] = (u8) (slot + 1);
      if(raw[0] != 'S' || raw[1] != '5') {
        g_stage_sealed[sector] = 1;
        continue;
      }
      const u8 state = raw[2];
      const u32 key = get_le32(raw, 4);
      const u16 generation = get_le16(raw, 8);
      if(stage_generation_newer(generation, g_stage_generation)) g_stage_generation = generation;
      if(state != STATE_ACTIVE) continue;
      const u32 crc = get_le32(raw, 12);
      if(!read_bytes(stage_record_address(ref) + STAGE_RECORD_HEADER_SIZE,
                     payload, sizeof(payload)) ||
         stage_crc(key, generation, payload) != crc) {
        // Never append after a torn record: retaining the previous valid
        // generation is more important than the unused tail of this sector.
        g_stage_sealed[sector] = 1;
        continue;
      }
      const int old = stage_ref_index(key);
      if(old >= 0) {
        u32 old_key = 0;
        u16 old_generation = 0;
        u32 old_crc = 0;
        u8 old_state = 0;
        if((!read_stage_record(stage_index_ref((u16) old), old_key,
                               old_generation, old_crc, old_state) ||
            stage_generation_newer(generation, old_generation)) &&
           key <= STAGE_KEY_MAX) {
          g_stage_index[old] = pack_stage_index(key, ref);
        }
      } else if(key <= STAGE_KEY_MAX &&
                g_stage_ref_count < STAGE_REF_CAPACITY) {
        g_stage_index[g_stage_ref_count] = pack_stage_index(key, ref);
        g_stage_ref_count++;
      }
    }
  }
}

bool vfat_stage_write(u32 block, const u8* data) {
  DiskActivity activity;
  if(!g_ready || data == NULL || block > STAGE_KEY_MAX) return false;
  if(stage_ref_index(block) < 0 && g_stage_ref_count >= STAGE_REF_CAPACITY) return false;
  u16 sector = 0;
  u8 slot = 0;
  if(!find_stage_slot(sector, slot)) return false;
  (void) slot;
  return append_stage_value(sector, block, data);
}

bool vfat_stage_read(u32 block, u8* data) {
  if(!g_ready || data == NULL) return false;
  const int index = stage_ref_index(block);
  if(index < 0) return false;
  u32 key = 0;
  u16 generation = 0;
  u32 crc = 0;
  u8 state = 0;
  const u16 ref = stage_index_ref((u16) index);
  if(!read_stage_record(ref, key, generation, crc, state) ||
     state != STATE_ACTIVE || key != block ||
     !read_bytes(stage_record_address(ref) + STAGE_RECORD_HEADER_SIZE,
                 data, STAGE_DATA_SIZE) || stage_crc(key, generation, data) != crc) return false;
  return true;
}

bool vfat_stage_exists(u32 block) {
  return g_ready && stage_ref_index(block) >= 0;
}

u16 vfat_stage_count(void) {
  return g_ready ? g_stage_ref_count : 0;
}

void vfat_stage_forget(u32 start_block, u16 blocks) {
  for(u16 offset = 0; offset < blocks; offset++) {
    const int index = stage_ref_index(start_block + offset);
    if(index < 0) continue;
    if(!write_byte(stage_record_address(stage_index_ref((u16) index)) + 2,
                   STATE_DELETED)) continue;
    const u16 last = (u16) (g_stage_ref_count - 1);
    g_stage_index[index] = g_stage_index[last];
    g_stage_ref_count--;
  }
}

bool vfat_stage_discard_all(void) {
  while(g_stage_ref_count != 0) {
    const u16 index = (u16) (g_stage_ref_count - 1);
    if(!write_byte(stage_record_address(stage_index_ref(index)) + 2,
                   STATE_DELETED)) return false;
    g_stage_ref_count--;
  }
  return true;
}

} // namespace program_store
