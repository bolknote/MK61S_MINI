#include "program_store.hpp"

#include "bounded_string.hpp"
#include "crc32.hpp"
#include "fat_name.hpp"
#include "Arduino.h"
#include "config.h"
#include "debug.h"
#include "exclusive_buffer.hpp"
#include "flash_capacity_probe.hpp"
#include "ledcontrol.h"
#include "shared_memory.hpp"
#include "shared_scratch.hpp"
#include "spi_nor_flash.hpp"
#include "tools.hpp"
#include "workspace_swap.hpp"
#include "zx0.hpp"

#include <stdint.h>
#include <string.h>

#ifdef SPI_FLASH
#if defined(PROGRAM_STORE_HOST_TEST)
extern SpiNorFlash flash;
static SpiNorFlash& flash_device(void) { return flash; }
#else
static SpiNorFlash& flash_device(void) { return external_flash(); }
#endif
#endif

namespace program_store {
namespace {

// Локатор, сектор данных, settings guard и staging сохраняют версию 5:
// их физический формат не меняется. Каталог версии 6 блокирует откат на старую
// прошивку: она увидит знакомый локатор, но не станет монтировать незнакомые
// inode больших файлов и перейдёт в безопасный REPAIR_REQUIRED.
static constexpr u8 PHYSICAL_FORMAT_VERSION = 5;
static constexpr u8 LEGACY_CATALOG_VERSION = 5;
static constexpr u8 CATALOG_VERSION = 6;
static constexpr u8 LOCATOR_STORE_VERSION_OFFSET = 7;
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
static constexpr u8 LEGACY_TYPE_COUNT = 6;
static constexpr u8 TYPE_COUNT = 7;
static constexpr u16 IMAGE1_HEADER_COUNT_OFFSET = 64;
static constexpr u16 LEGACY_WAL_RECORD_SIZE = 256;
static constexpr u8 LEGACY_WAL_MAX_UPDATES = 9;
static constexpr u16 LEGACY_IMAGE1_WAL_COUNT_OFFSET = 242;
static constexpr u16 LEGACY_WAL_CRC_OFFSET = 244;
// Каталог v6 публикует за одну COW-транзакцию основной inode, служебные
// FAT-extents максимального APP и изменения двух родительских списков.
static constexpr u16 WAL_RECORD_SIZE = 512;
static constexpr u8 WAL_MAX_UPDATES = 16;
static constexpr u16 IMAGE1_WAL_COUNT_OFFSET = 506;
static constexpr u16 WAL_CRC_OFFSET = 508;
static constexpr u8 OVERLAY_CAPACITY = 96;
static constexpr u16 STAGE_DATA_SIZE = VFAT_STAGE_BLOCK_SIZE;
static constexpr u16 STAGE_SECTOR_HEADER_SIZE = 16;
static constexpr u16 STAGE_RECORD_HEADER_SIZE = 16;
static constexpr u16 STAGE_RECORD_SIZE = STAGE_RECORD_HEADER_SIZE + STAGE_DATA_SIZE;
static constexpr u8 STAGE_RECORDS_PER_SECTOR =
    (storage_geometry::PHYSICAL_SECTOR_SIZE - STAGE_SECTOR_HEADER_SIZE) /
    STAGE_RECORD_SIZE;
static constexpr u16 STAGE_REF_CAPACITY = 384;
static constexpr u8 STAGE_REF_BITS = 9;
static constexpr u16 STAGE_REF_MASK = (1U << STAGE_REF_BITS) - 1U;
static constexpr u32 STAGE_KEY_MAX = VFAT_STAGE_KEY_MAX;
static constexpr u8 GC_SCAN_WINDOW = 32;
static constexpr u32 ERASE_TIMEOUT_MS = 5000;
static constexpr t_time_ms DISK_LED_ON_MS = 35;
static constexpr t_time_ms DISK_LED_OFF_MS = 35;
static constexpr u8 INODE_FLAG_LARGE_FILE = 0x01;
static constexpr u8 INODE_FLAG_ZX0 = 0x02;
static constexpr u8 INODE_FILE_FLAGS =
    INODE_FLAG_LARGE_FILE | INODE_FLAG_ZX0;
static constexpr u16 ZX0_MIN_SAVING = 64;
static constexpr u8 ZX0_MIN_SAVING_PERCENT = 10;
static constexpr usize ZX0_FALLBACK_WORKSPACE_SIZE = 1024;
static constexpr u16 LARGE_BLOCK_HEADER_SIZE = 32;
static constexpr u16 LARGE_BLOCK_DATA_SIZE =
    storage_geometry::PHYSICAL_SECTOR_SIZE - LARGE_BLOCK_HEADER_SIZE;
static constexpr u8 LARGE_BLOCK_COUNT =
    (MAX_APP_FILE_SIZE + LARGE_BLOCK_DATA_SIZE - 1U) / LARGE_BLOCK_DATA_SIZE;
static constexpr u16 LARGE_DESCRIPTOR_HEADER_SIZE = 20;
static constexpr u16 LARGE_DESCRIPTOR_SIZE =
    LARGE_DESCRIPTOR_HEADER_SIZE + (u16) LARGE_BLOCK_COUNT * sizeof(u32);
static constexpr u8 LEGACY_LARGE_DESCRIPTOR_VERSION = 1;
static constexpr u8 LARGE_DESCRIPTOR_VERSION = 2;

static_assert(STAGE_RECORDS_PER_SECTOR == 7, "C5 stage must pack seven sectors");
static_assert(STAGE_KEY_MAX == (0xFFFFFFFFUL >> STAGE_REF_BITS),
              "public C5 stage key range must match packed references");
static_assert(44 + WAL_MAX_UPDATES *
                  (2 + storage_geometry::INODE_BYTES) <=
                  IMAGE1_WAL_COUNT_OFFSET,
              "inode updates overlap the v6 WAL tail");
static_assert(IMAGE1_WAL_COUNT_OFFSET + sizeof(u16) <= WAL_CRC_OFFSET,
              "image counter overlaps the WAL CRC");
static_assert(LEGACY_IMAGE1_WAL_COUNT_OFFSET ==
                  44 + LEGACY_WAL_MAX_UPDATES *
                      (2 + storage_geometry::INODE_BYTES),
              "v5 WAL geometry changed");
static_assert(LEGACY_IMAGE1_WAL_COUNT_OFFSET + sizeof(u16) <=
                  LEGACY_WAL_CRC_OFFSET,
              "v5 image counter overlaps its WAL CRC");
static_assert(IMAGE1_HEADER_COUNT_OFFSET + sizeof(u16) <=
                  CATALOG_HEADER_CRC_OFFSET,
              "image counter overlaps the catalog-header CRC");
static_assert(LARGE_BLOCK_COUNT == 6,
              "maximum APP should occupy exactly six C5 large blocks");
static_assert(LARGE_DESCRIPTOR_SIZE < 128,
              "large-file descriptor must remain a small C5 record");
static_assert((usize) MAX_MK61_TEXT_SIZE + NAME_SIZE + RECORD_HEADER_SIZE <=
                  storage_geometry::PHYSICAL_SECTOR_SIZE / 2,
              "two maximum C5 records must fit one erase sector");
static_assert((usize) MAX_IMAGE1_SIZE + NAME_SIZE + RECORD_HEADER_SIZE <=
                  storage_geometry::PHYSICAL_SECTOR_SIZE / 2,
              "two maximum C5 image records must fit one erase sector");

static bool compute_geometry(u32 capacity,
                             storage_geometry::Geometry& geometry) {
  return storage_geometry::compute(capacity, geometry);
}

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

struct LargeDescriptor {
  u32 sectors[LARGE_BLOCK_COUNT];
  u32 generation;
  u32 data_crc;
  u16 data_len;
  u16 stored_len;
  u8 block_count;
  u8 version;
};

struct CatalogMeta {
  u16 root_head;
  u16 total_count;
  u16 type_count[TYPE_COUNT];
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
static MountStatus g_mount_status;
static u32 g_format_epoch;
static u8 g_locator_store_version;
static u8 g_locator_matching_copies;
static u8 g_catalog_write_version = CATALOG_VERSION;
static u8 g_active_bank;
static u32 g_catalog_generation;
static u32 g_wal_sequence;
static u8 g_wal_records;
static bool g_wal_sealed;
static CatalogMeta g_meta;
// Структура из массивов сохраняет естественное выравнивание Inode без двух
// байтов хвостового заполнения на каждый слот таблицы {u16, Inode}.
static u16 g_overlay_ids[OVERLAY_CAPACITY];
static Inode g_overlay_inodes[OVERLAY_CAPACITY];
static u8 g_overlay_count;
static u8 g_table_cache[512];
static u32 g_table_cache_address = EMPTY_ADDRESS;
static u8 g_disk_activity_depth;
static u8 g_disk_led_poll_divider;

// Упаковываем 18-битный виртуальный LBA и 9-битную ссылку на физическую запись
// в одно слово. Сам индекс арендует общую APP/USB overlay-арену и потому не
// увеличивает постоянный расход SRAM. На короткой финальной фазе terminal
// fsput он может быть сужен до диапазона одного файла в language workspace.
static u32* g_stage_index;
static u16 g_stage_index_capacity;
static u16 g_stage_ref_count;
static shared_memory::Lease g_stage_overlay_lease;
static bool g_stage_locked;
static bool g_stage_external;
static u8 g_stage_used[storage_geometry::STAGE_TARGET_SECTORS];
static u8 g_stage_sealed[storage_geometry::STAGE_TARGET_SECTORS];
static u16 g_stage_generation;
static u16 g_free_hint;
// Сектора незавершённой COW-записи ещё не достижимы из каталога, но сборщик
// мусора не должен успеть занять их при добавлении дескриптора.
static u32 g_large_write_sectors[LARGE_BLOCK_COUNT];
static u8 g_large_write_sector_count;
static u16 g_verified_large_id = NONE;
static u32 g_verified_large_generation;
static u8 g_verified_large_block = 0xFF;

static_assert((u16) storage_geometry::STAGE_TARGET_SECTORS *
                  STAGE_RECORDS_PER_SECTOR <= STAGE_REF_MASK,
              "C5 stage references must fit in the packed index");
static_assert((usize) STAGE_REF_CAPACITY * sizeof(u32) <=
                  shared_memory::STAGE_INDEX_SIZE,
              "full C5 staging index does not fit the shared overlay");

static int g_flat_cache_index = -1;
static u16 g_flat_cache_id;
static u16 g_child_cache_parent = NONE;
static int g_child_cache_index = -1;
static u16 g_child_cache_id = NONE;

#ifdef DEBUG_SPIFLASH
static void capacity_probe_debug(u32 candidate, bool complete,
                                 bool distinct) {
  Serial.print("C5 probe candidate: ");
  Serial.print(candidate);
  if(!complete) {
    Serial.println(" bytes, testing...");
  } else {
    Serial.println(distinct ? " bytes, distinct" : " bytes, aliased/failed");
  }
}
#endif

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
  if(flash_is_ok && flash_device().readByteArray(address, out, len)) {
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
    const bool ok = flash_device().writeByteArray(address, (u8*) data, len);
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
    const bool ok = flash_device().writeByte(address, value);
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
  while(!flash_device().eraseSector(sector_address(sector))) {
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

static u32 crc32_bytes(const u8* data, usize len, u32 crc = 0xFFFFFFFFUL) {
  return mk61_crc32::extend(crc, data, len);
}

static bool crc32_flash(mk61_crc32::Context& crc,
                        u32 address, u32 len) {
  u8 buffer[64];
  while(len != 0) {
    const u16 count = len > sizeof(buffer) ? sizeof(buffer) : (u16) len;
    if(!read_bytes(address, buffer, count) ||
       !crc.update(buffer, count)) return false;
    address += count;
    len -= count;
  }
  return true;
}

static bool crc32_flash(u32 address, u32 len, u32& output) {
  mk61_crc32::Context crc;
  if(!crc32_flash(crc, address, len)) return false;
  output = crc.finish();
  return true;
}

static bool crc32_flash_software(u32 address, u32 len, u32& output) {
  u32 state = mk61_crc32::INITIAL_STATE;
  u8 buffer[64];
  while(len != 0) {
    const u16 count = len > sizeof(buffer) ? sizeof(buffer) : (u16) len;
    if(!read_bytes(address, buffer, count)) return false;
    state = crc32_bytes(buffer, count, state);
    address += count;
    len -= count;
  }
  output = mk61_crc32::finish(state);
  return true;
}

static void encode_settings_guard(u8* guard, u32 capacity) {
  memset(guard, 0xFF, SETTINGS_GUARD_SIZE);
  memcpy(guard, "C5SG", 4);
  guard[4] = PHYSICAL_FORMAT_VERSION;
  put_le32(guard, 8, capacity);
  put_le32(guard, 12, mk61_crc32::calculate(guard, 12));
}

static bool settings_guard_valid(const storage_geometry::Geometry& geometry) {
  u8 guard[SETTINGS_GUARD_SIZE];
#ifdef SPI_FLASH
  const u32 address = sector_address(geometry.settings_sector) +
                      SETTINGS_JOURNAL_SIZE;
  if(!flash_device().rawPrepare(geometry.capacity_bytes) ||
     !flash_device().rawRead(address, guard, sizeof(guard))) return false;
#else
  (void) geometry;
  return false;
#endif
  return memcmp(guard, "C5SG", 4) == 0 &&
         guard[4] == PHYSICAL_FORMAT_VERSION &&
         get_le32(guard, 8) == geometry.capacity_bytes &&
         get_le32(guard, 12) == mk61_crc32::calculate(guard, 12);
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
    case ProgramType::IMAGE1: return 6;
    case ProgramType::APP: return -1; // счётчик APP вычисляется по inode
    case ProgramType::CHIP8: return -1; // счётчик CHIP-8 вычисляется по inode
    case ProgramType::MARKDOWN: return -1; // новый тип без миграции каталога
  }
  return -1;
}

static bool supported_type(ProgramType type) {
  return type == ProgramType::APP || type == ProgramType::CHIP8 ||
         type == ProgramType::MARKDOWN ||
         type_index(type) >= 0;
}

static u16 maximum_data_len(ProgramType type) {
  if(type == ProgramType::FONT) return MAX_FONT_SIZE;
  if(type == ProgramType::IMAGE1) return MAX_IMAGE1_SIZE;
  if(type == ProgramType::CHIP8) return MAX_CHIP8_SIZE;
  if(type == ProgramType::APP) return MAX_APP_FILE_SIZE;
  return MAX_MK61_TEXT_SIZE;
}

static const char* extension_for_type(ProgramType type) {
  switch(type) {
    case ProgramType::MK61: return "m61";
    case ProgramType::FOCAL: return "foc";
    case ProgramType::TINYBASIC: return "tbi";
    case ProgramType::TEXT: return "txt";
    case ProgramType::MK61_STATE: return "state.txt";
    case ProgramType::FONT: return "fmk";
    case ProgramType::IMAGE1: return "wbmp";
    case ProgramType::APP: return "app";
    case ProgramType::CHIP8: return "ch8";
    case ProgramType::MARKDOWN: return "md";
  }
  return "bin";
}

static const char* magic_for_type(ProgramType type) {
  switch(type) {
    case ProgramType::MK61: return "M1";
    case ProgramType::FOCAL: return "F1";
    case ProgramType::TINYBASIC: return "B2";
    case ProgramType::TEXT: return "T1";
    case ProgramType::MK61_STATE: return "M2";
    case ProgramType::FONT: return "f1";
    case ProgramType::IMAGE1: return "I1";
    case ProgramType::APP: return "A1";
    case ProgramType::CHIP8: return "C1";
    case ProgramType::MARKDOWN: return "T2";
  }
  return "??";
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

static bool large_file_inode(const Inode& inode) {
  return inode_kind(inode) == NodeKind::FILE &&
         (inode.flags & INODE_FLAG_LARGE_FILE) != 0;
}

static bool zx0_file_inode(const Inode& inode) {
  return inode_kind(inode) == NodeKind::FILE &&
         (inode.flags & INODE_FLAG_ZX0) != 0;
}

static bool inode_flags_valid(const Inode& inode) {
  const NodeKind kind = inode_kind(inode);
  if(kind != NodeKind::FILE) return inode.flags == 0;
  if((inode.flags & ~INODE_FILE_FLAGS) != 0) return false;
  if(inode_type(inode) == ProgramType::APP && zx0_file_inode(inode)) {
    return false;
  }
  return true;
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
  const u32 crc = mk61_crc32::finish(crc32_bytes(record, size));
  record[state_offset] = saved_state;
  memcpy(record + crc_offset, saved_crc, sizeof(saved_crc));
  return crc;
}

static u16 wal_record_size(u8 catalog_version) {
  return catalog_version == LEGACY_CATALOG_VERSION
      ? LEGACY_WAL_RECORD_SIZE : WAL_RECORD_SIZE;
}

static u8 wal_max_updates(u8 catalog_version) {
  return catalog_version == LEGACY_CATALOG_VERSION
      ? LEGACY_WAL_MAX_UPDATES : WAL_MAX_UPDATES;
}

static u16 wal_image_count_offset(u8 catalog_version) {
  return catalog_version == LEGACY_CATALOG_VERSION
      ? LEGACY_IMAGE1_WAL_COUNT_OFFSET : IMAGE1_WAL_COUNT_OFFSET;
}

static u16 wal_crc_offset(u8 catalog_version) {
  return catalog_version == LEGACY_CATALOG_VERSION
      ? LEGACY_WAL_CRC_OFFSET : WAL_CRC_OFFSET;
}

static void encode_meta(u8* record, const CatalogMeta& meta,
                        u16 image_count_offset) {
  put_le16(record, 10, meta.root_head);
  put_le16(record, 12, meta.total_count);
  put_le16(record, 14, meta.current_offset);
  put_le32(record, 16, meta.current_sector);
  put_le32(record, 20, meta.reserve_sector);
  put_le32(record, 24, meta.gc_cursor);
  put_le32(record, 28, meta.data_sequence);
  for(u8 i = 0; i < LEGACY_TYPE_COUNT; i++) {
    put_le16(record, (u16) (32 + i * 2), meta.type_count[i]);
  }
  put_le16(record, image_count_offset, meta.type_count[6]);
}

static u16 decode_optional_count(const u8* data, u16 offset) {
  const u16 count = get_le16(data, offset);
  return count == 0xFFFF ? 0 : count;
}

static CatalogMeta decode_meta(const u8* record, u16 image_count_offset) {
  CatalogMeta meta;
  meta.root_head = get_le16(record, 10);
  meta.total_count = get_le16(record, 12);
  meta.current_offset = get_le16(record, 14);
  meta.current_sector = get_le32(record, 16);
  meta.reserve_sector = get_le32(record, 20);
  meta.gc_cursor = get_le32(record, 24);
  meta.data_sequence = get_le32(record, 28);
  for(u8 i = 0; i < LEGACY_TYPE_COUNT; i++) {
    meta.type_count[i] = get_le16(record, (u16) (32 + i * 2));
  }
  meta.type_count[6] = decode_optional_count(record, image_count_offset);
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
  const u16 record_size = wal_record_size(g_catalog_write_version);
  const u8 maximum_updates = wal_max_updates(g_catalog_write_version);
  const u16 image_count_offset =
      wal_image_count_offset(g_catalog_write_version);
  const u16 crc_offset = wal_crc_offset(g_catalog_write_version);
  if(transaction.count > maximum_updates) return false;
  const u8 records_per_bank = (u8) ((u32) storage_geometry::CATALOG_WAL_SECTORS *
      storage_geometry::PHYSICAL_SECTOR_SIZE / record_size);
  if(g_wal_sealed || g_wal_records >= records_per_bank ||
     g_overlay_count + new_overlay_slots(transaction) > OVERLAY_CAPACITY) {
    if(!checkpoint()) {
      (void) load_catalog();
      return false;
    }
  }

  u8 record[WAL_RECORD_SIZE];
  memset(record, 0xFF, record_size);
  record[0] = 'W';
  record[1] = '5';
  record[2] = g_catalog_write_version;
  record[3] = STATE_WRITING;
  const u32 next_sequence = g_wal_sequence + 1;
  put_le32(record, 4, next_sequence);
  record[8] = transaction.count;
  encode_meta(record, transaction.meta, image_count_offset);
  u16 offset = 44;
  for(u8 i = 0; i < transaction.count; i++) {
    put_le16(record, offset, transaction.updates[i].id);
    serialize_inode(transaction.updates[i].inode, record + offset + 2);
    offset = (u16) (offset + 2 + storage_geometry::INODE_BYTES);
  }
  const u32 crc =
      normalized_record_crc(record, record_size, crc_offset, 3);
  put_le32(record, crc_offset, crc);

  const u32 address =
      wal_address(g_active_bank) + (u32) g_wal_records * record_size;
  if(!write_bytes(address, record, record_size) ||
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
  header[4] = g_catalog_write_version;
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
  for(u8 i = 0; i < LEGACY_TYPE_COUNT; i++) {
    put_le16(header, (u16) (52 + i * 2), g_meta.type_count[i]);
  }
  put_le16(header, IMAGE1_HEADER_COUNT_OFFSET, g_meta.type_count[6]);
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
  mk61_crc32::Context crc;
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
        if(!crc.update(buffer, sizeof(buffer))) return false;
        destination_address += sizeof(buffer);
        buffered = 0;
      }
    }
  }
  if(buffered != 0) {
    if(!write_bytes(destination_address, buffer, buffered)) return false;
    if(!crc.update(buffer, buffered)) return false;
  }
  const u32 table_crc = crc.finish();

  u8 header[CATALOG_HEADER_SIZE];
  encode_catalog_header(header, g_catalog_generation + 1, table_crc);
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

static bool decode_catalog_header(u8 bank, u8 catalog_version, u8* header,
                                  u32& generation, u32& wal_sequence,
                                  CatalogMeta& meta) {
  if(!read_bytes(sector_address(bank_sector(bank)), header, CATALOG_HEADER_SIZE)) return false;
  if(memcmp(header, "C5CT", 4) != 0 || header[4] != catalog_version ||
     header[5] != STATE_ACTIVE || header[6] != CATALOG_HEADER_SIZE ||
     get_le32(header, 12) != g_format_epoch ||
     get_le16(header, 16) != g_geometry.max_nodes) return false;
  if(normalized_record_crc(header, CATALOG_HEADER_SIZE,
                          CATALOG_HEADER_CRC_OFFSET, 5) !=
     get_le32(header, CATALOG_HEADER_CRC_OFFSET)) return false;
  u32 table_crc = 0;
  if(!crc32_flash(
       table_address(bank),
       (u32) g_geometry.max_nodes * storage_geometry::INODE_BYTES,
       table_crc)) return false;
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
  for(u8 i = 0; i < LEGACY_TYPE_COUNT; i++) {
    meta.type_count[i] = get_le16(header, (u16) (52 + i * 2));
  }
  meta.type_count[6] = decode_optional_count(header, IMAGE1_HEADER_COUNT_OFFSET);
  return generation != 0;
}

static bool generation_newer(u32 left, u32 right) {
  return (i32) (left - right) > 0;
}

static bool replay_wal(u8 catalog_version) {
  const u16 record_size = wal_record_size(catalog_version);
  const u8 maximum_updates = wal_max_updates(catalog_version);
  const u16 image_count_offset = wal_image_count_offset(catalog_version);
  const u16 crc_offset = wal_crc_offset(catalog_version);
  const u8 records_per_bank = (u8) ((u32) storage_geometry::CATALOG_WAL_SECTORS *
      storage_geometry::PHYSICAL_SECTOR_SIZE / record_size);
  g_wal_records = 0;
  g_wal_sealed = false;
  for(u8 record_index = 0; record_index < records_per_bank; record_index++) {
    u8 record[WAL_RECORD_SIZE];
    if(!read_bytes(wal_address(g_active_bank) +
                       (u32) record_index * record_size,
                   record, record_size)) return false;
    bool erased = true;
    for(u8 i = 0; i < 8; i++) if(record[i] != 0xFF) erased = false;
    if(erased) break;
    if(record[0] != 'W' || record[1] != '5' ||
       record[2] != catalog_version ||
       record[3] != STATE_ACTIVE || record[8] > maximum_updates ||
       normalized_record_crc(record, record_size, crc_offset, 3) !=
           get_le32(record, crc_offset)) {
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
    g_meta = decode_meta(record, image_count_offset);
    g_wal_sequence = sequence;
    g_wal_records++;
  }
  return true;
}

static bool load_catalog_version(u8 catalog_version) {
  u8 header_a[CATALOG_HEADER_SIZE];
  u8 header_b[CATALOG_HEADER_SIZE];
  u32 generation_a = 0;
  u32 generation_b = 0;
  u32 sequence_a = 0;
  u32 sequence_b = 0;
  CatalogMeta meta_a;
  CatalogMeta meta_b;
  const bool valid_a = decode_catalog_header(0, catalog_version, header_a,
                                             generation_a, sequence_a, meta_a);
  const bool valid_b = decode_catalog_header(1, catalog_version, header_b,
                                             generation_b, sequence_b, meta_b);
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
  return replay_wal(catalog_version);
}

static bool load_catalog(void) {
  return load_catalog_version(CATALOG_VERSION);
}

static void encode_locator(u8* locator,
                           u8 store_version = CATALOG_VERSION) {
  memset(locator, 0xFF, LOCATOR_SIZE);
  memcpy(locator, "C5FS", 4);
  locator[4] = PHYSICAL_FORMAT_VERSION;
  if(store_version != LEGACY_CATALOG_VERSION) {
    locator[LOCATOR_STORE_VERSION_OFFSET] = store_version;
  }
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
  put_le32(locator, 60, flash_device().capacityProbeUpper());
  put_le32(locator, 64, flash_device().getJEDECID());
#else
  put_le32(locator, 60, g_geometry.capacity_bytes);
  put_le32(locator, 64, 0);
#endif
  put_le32(locator, 68, normalized_record_crc(locator, LOCATOR_SIZE, 68, 5));
}

static bool locator_matches(const u8* locator,
                            storage_geometry::Geometry& geometry,
                            u32& epoch, u32& probe_upper, u32& jedec_id,
                            u8& store_version) {
  if(memcmp(locator, "C5FS", 4) != 0 ||
     locator[4] != PHYSICAL_FORMAT_VERSION ||
     locator[5] != STATE_ACTIVE || locator[6] != LOCATOR_SIZE ||
     normalized_record_crc((u8*) locator, LOCATOR_SIZE, 68, 5) != get_le32(locator, 68)) return false;
  store_version = locator[LOCATOR_STORE_VERSION_OFFSET] == 0xFF
      ? LEGACY_CATALOG_VERSION
      : locator[LOCATOR_STORE_VERSION_OFFSET];
  if(store_version != LEGACY_CATALOG_VERSION &&
     store_version != CATALOG_VERSION) return false;
  if(!compute_geometry(get_le32(locator, 8), geometry)) return false;
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

// Обновление прошивки может намеренно изменить вычисляемую геометрию C5/FAT,
// хотя физическая микросхема и сектор настроек не меняются. Старый каталог при
// этом смонтировать нельзя, но повторять разрушающую проверку ёмкости и стирать
// настройки было бы излишне и неожиданно. Этот ограниченный декодер доверяет
// только полностью зафиксированному локатору с CRC и независимо защищённой CRC
// метке на неизменившемся физическом конце.
static bool load_capacity_for_reformat(void) {
#ifndef SPI_FLASH
  return false;
#else
  u8 locator[LOCATOR_SIZE];
  const u32 probe_upper = flash_device().capacityProbeUpper();
  const u32 jedec_id = flash_device().getJEDECID();
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!read_bytes(sector_address(copy), locator, sizeof(locator)) ||
       memcmp(locator, "C5FS", 4) != 0 ||
       locator[4] != PHYSICAL_FORMAT_VERSION ||
       locator[5] != STATE_ACTIVE || locator[6] != LOCATOR_SIZE ||
       normalized_record_crc(locator, LOCATOR_SIZE, 68, 5) !=
           get_le32(locator, 68) ||
       get_le32(locator, 60) != probe_upper ||
       get_le32(locator, 64) != jedec_id) continue;

    storage_geometry::Geometry geometry;
    const u32 capacity = get_le32(locator, 8);
    if(!compute_geometry(capacity, geometry) ||
       get_le32(locator, 20) != geometry.physical_sectors ||
       get_le32(locator, 52) != geometry.settings_sector ||
       !flash_device().setCapacity(capacity) || !settings_guard_valid(geometry)) {
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
  u8 stored_version = 0;
#ifdef SPI_FLASH
  const u32 probe_upper = flash_device().capacityProbeUpper();
  const u32 jedec_id = flash_device().getJEDECID();
#else
  const u32 probe_upper = 0;
  const u32 jedec_id = 0;
#endif
  bool found = false;
  storage_geometry::Geometry selected_geometry = {};
  u32 selected_epoch = 0;
  u8 selected_version = 0;
  u8 selected_copies = 0;
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!read_bytes(sector_address(copy), locator, sizeof(locator))) continue;
    if(!locator_matches(locator, geometry, epoch, stored_probe_upper,
                        stored_jedec_id, stored_version)) continue;
    if(stored_jedec_id != jedec_id || stored_probe_upper != probe_upper ||
       !flash_device().setCapacity(geometry.capacity_bytes) ||
       !settings_guard_valid(geometry)) continue;
    if(!found || stored_version > selected_version) {
      selected_geometry = geometry;
      selected_epoch = epoch;
      selected_version = stored_version;
      selected_copies = 1;
      found = true;
    } else if(stored_version == selected_version &&
              epoch == selected_epoch &&
              geometry.capacity_bytes == selected_geometry.capacity_bytes) {
      selected_copies++;
    }
  }
  if(!found) return false;
  g_geometry = selected_geometry;
  g_format_epoch = selected_epoch;
  g_locator_store_version = selected_version;
  g_locator_matching_copies = selected_copies;
  return true;
}

static bool write_locators_version(u8 store_version) {
  u8 locator[LOCATOR_SIZE];
  encode_locator(locator, store_version);
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!erase_sector(copy)) return false;
    const u32 address = sector_address(copy);
    if(!write_bytes(address, locator, sizeof(locator)) ||
       !write_byte(address + 5, STATE_ACTIVE)) return false;
  }
  g_locator_store_version = store_version;
  g_locator_matching_copies = storage_geometry::LOCATOR_SECTORS;
  return true;
}

static bool write_locators(void) {
  return write_locators_version(CATALOG_VERSION);
}

static bool load_or_migrate_catalog(void) {
  if(load_catalog_version(CATALOG_VERSION)) {
    if(g_locator_store_version == CATALOG_VERSION) {
      return g_locator_matching_copies == storage_geometry::LOCATOR_SECTORS ||
             write_locators();
    }
    // Один новый банк мог пережить прерванную миграцию. Переписываем второй,
    // затем публикуем версию в обоих локаторах.
    return checkpoint() && write_locators();
  }
  if(g_locator_store_version != LEGACY_CATALOG_VERSION ||
     !load_catalog_version(LEGACY_CATALOG_VERSION)) return false;

  // Таблица inode не изменилась. Два COW-checkpoint переводят по одному банку
  // каталога, не трогая ни записи файлов, ни staging, ни settings.
  return checkpoint() && checkpoint() && write_locators();
}

static bool data_sector_header_valid(u32 sector) {
  u8 header[DATA_SECTOR_HEADER_SIZE];
  if(!read_bytes(sector_address(sector), header, sizeof(header))) return false;
  return memcmp(header, "C5D0", 4) == 0 &&
         header[4] == PHYSICAL_FORMAT_VERSION &&
         header[5] == STATE_ACTIVE && get_le32(header, 8) == g_format_epoch;
}

static bool initialize_data_sector(u32 sector) {
  if(!erase_sector(sector)) return false;
  u8 header[DATA_SECTOR_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C5D0", 4);
  header[4] = PHYSICAL_FORMAT_VERSION;
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

static bool read_large_descriptor(u16 id, const Inode& inode,
                                  LargeDescriptor& descriptor);

static bool transient_large_sector(u32 sector) {
  for(u8 index = 0; index < g_large_write_sector_count; index++) {
    if(g_large_write_sectors[index] == sector) return true;
  }
  return false;
}

static bool descriptor_contains_sector(const LargeDescriptor& descriptor,
                                       u32 sector) {
  for(u8 index = 0; index < descriptor.block_count; index++) {
    if(descriptor.sectors[index] == sector) return true;
  }
  return false;
}

static bool sector_has_live_inode(u32 sector) {
  if(transient_large_sector(sector)) return true;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode)) continue;
    if(inode.address < EXTENT_ADDRESS &&
       inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE == sector) return true;
    if(large_file_inode(inode)) {
      LargeDescriptor descriptor = {};
      if(read_large_descriptor(id, inode, descriptor) &&
         descriptor_contains_sector(descriptor, sector)) return true;
    }
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

  // За один проход таблицы inode отмечаем активность 32 кандидатов. Прежний
  // цикл с секторами снаружи мог при почти заполненном накопителе просматривать
  // всю таблицу узлов для каждого сектора данных (квадратичный худший случай).
  for(u32 base = 0; base < count; base += GC_SCAN_WINDOW) {
    const u8 window = (u8) ((count - base < GC_SCAN_WINDOW)
        ? count - base : GC_SCAN_WINDOW);
    u32 live_mask = 0;
    for(u8 index = 0; index < g_large_write_sector_count; index++) {
      const u32 sector = g_large_write_sectors[index];
      if(!data_sector_in_range(sector)) continue;
      const u32 relative = (sector - first + count - (start - first)) % count;
      if(relative >= base && relative < base + window) {
        live_mask |= 1UL << (relative - base);
      }
    }
    for(u16 id = 0; id < g_geometry.max_nodes; id++) {
      Inode inode;
      if(!get_inode(id, inode) || !visible_inode(inode)) continue;
      if(inode.address < EXTENT_ADDRESS) {
        const u32 sector = inode.address /
            storage_geometry::PHYSICAL_SECTOR_SIZE;
        if(data_sector_in_range(sector)) {
          const u32 relative =
              (sector - first + count - (start - first)) % count;
          if(relative >= base && relative < base + window) {
            live_mask |= 1UL << (relative - base);
          }
        }
      }
      if(large_file_inode(inode)) {
        LargeDescriptor descriptor = {};
        if(!read_large_descriptor(id, inode, descriptor)) continue;
        for(u8 block = 0; block < descriptor.block_count; block++) {
          const u32 sector = descriptor.sectors[block];
          if(!data_sector_in_range(sector)) continue;
          const u32 relative =
              (sector - first + count - (start - first)) % count;
          if(relative >= base && relative < base + window) {
            live_mask |= 1UL << (relative - base);
          }
        }
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

  for(u8 index = 0; index < g_large_write_sector_count; index++) {
    const u32 sector = g_large_write_sectors[index];
    if(!data_sector_in_range(sector)) continue;
    const u32 relative = (sector - first + count - (start - first)) % count;
    if(relative < window) live_bytes[relative] = 0xFFFF;
  }
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode)) continue;
    if(inode.address < EXTENT_ADDRESS) {
      const u32 sector = inode.address /
          storage_geometry::PHYSICAL_SECTOR_SIZE;
      if(data_sector_in_range(sector)) {
        const u32 relative =
            (sector - first + count - (start - first)) % count;
        if(relative < window) {
          const u32 sum = (u32) live_bytes[relative] + inode.record_len;
          live_bytes[relative] = sum > 0xFFFFU ? 0xFFFFU : (u16) sum;
        }
      }
    }
    if(large_file_inode(inode)) {
      LargeDescriptor descriptor = {};
      if(!read_large_descriptor(id, inode, descriptor)) continue;
      for(u8 block = 0; block < descriptor.block_count; block++) {
        const u32 sector = descriptor.sectors[block];
        if(!data_sector_in_range(sector)) continue;
        const u32 relative =
            (sector - first + count - (start - first)) % count;
        if(relative < window) live_bytes[relative] = 0xFFFF;
      }
    }
  }

  u16 best_bytes = 0xFFFF;
  u32 best = EMPTY_ADDRESS;
  for(u8 slot = 0; slot < window; slot++) {
    const u32 sector = first + (start - first + slot) % count;
    if(sector == g_meta.current_sector || sector == g_meta.reserve_sector) {
      continue;
    }
    if(live_bytes[slot] != 0xFFFF && live_bytes[slot] < best_bytes) {
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

  const u32 destination = g_meta.reserve_sector;
  if(!initialize_data_sector(destination)) return false;
  u16 destination_offset = DATA_SECTOR_HEADER_SIZE;
  u8 copy_buffer[64];
  u16 next_id = 0;
  while(next_id < g_geometry.max_nodes) {
    Transaction transaction;
    txn_begin(transaction);
    while(next_id < g_geometry.max_nodes &&
          transaction.count < WAL_MAX_UPDATES) {
      const u16 id = next_id++;
      Inode inode;
      if(!get_inode(id, inode) || !visible_inode(inode) ||
         inode.address >= EXTENT_ADDRESS ||
         inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE != victim) {
        continue;
      }
      if(inode.record_len == 0 ||
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
      if(!txn_set(transaction, id, inode)) return false;
      destination_offset = (u16) (destination_offset + inode.record_len);
    }
    if(transaction.count != 0 && !append_transaction(transaction)) {
      return false;
    }
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

struct MemorySource {
  const u8* data;
  u16 size;
};

static bool read_memory_source(void* context, u32 offset,
                               u8* output, usize size) {
  const MemorySource& source = *(MemorySource*) context;
  if(output == NULL || offset > source.size ||
     size > source.size - offset) return false;
  if(size != 0) memcpy(output, source.data + offset, size);
  return true;
}

static bool source_valid(const FileSource& source, u16 data_len) {
  return data_len == 0 || source.read != NULL;
}

class CompressionBuffer {
  public:
    CompressionBuffer(u8* supplied, usize supplied_size)
      : memory_(NULL), size_(0), acquired_(false) {
      if(supplied != NULL && supplied_size != 0) {
        memory_ = supplied;
        size_ = supplied_size;
        return;
      }
      if(exclusive_buffer::acquire(
            exclusive_buffer::Owner::PROGRAM_STORE_COMPRESSION,
            exclusive_buffer::SIZE)) {
        memory_ = exclusive_buffer::data(
            exclusive_buffer::Owner::PROGRAM_STORE_COMPRESSION);
        size_ = exclusive_buffer::SIZE;
        acquired_ = memory_ != NULL;
      }
    }

    ~CompressionBuffer(void) {
      if(acquired_) {
        exclusive_buffer::release(
            exclusive_buffer::Owner::PROGRAM_STORE_COMPRESSION);
      }
    }

    u8* data(void) const { return memory_; }
    usize size(void) const { return size_; }

  private:
    u8* memory_;
    usize size_;
    bool acquired_;
};

struct MemoryOutput {
  u8* data;
  u16 capacity;
  u16 size;
};

static bool write_memory_output(void* context, u8 value) {
  MemoryOutput& output = *(MemoryOutput*) context;
  if(output.size >= output.capacity) return false;
  output.data[output.size++] = value;
  return true;
}

enum class CompressionChoice : u8 {
  RAW,
  ZX0,
  ERROR
};

struct CompressionPlan {
  const u8* input;
  u8* workspace;
  usize workspace_size;
  const u8* stored_data;
  u16 stored_len;
  zx0::Prepared prepared;
};

static CompressionChoice prepare_compressed_payload(
    ProgramType type, const FileSource& source, u16 data_len,
    CompressionBuffer& large_buffer, shared_scratch::Lease& scratch,
    const u8* contiguous_data,
    u8* preferred_workspace, usize preferred_workspace_size,
    u8* fallback_workspace, usize fallback_workspace_size,
    CompressionPlan& plan) {
  memset(&plan, 0, sizeof(plan));
  plan.stored_len = data_len;
  if(!transparent_compression_enabled(type) || data_len == 0 ||
     data_len < ZX0_MIN_SAVING) return CompressionChoice::RAW;

  const bool memory_source = source.read == read_memory_source;
  u8* output = NULL;

  if(contiguous_data != NULL) {
    plan.input = contiguous_data;
    if(large_buffer.data() != NULL &&
       scratch.acquire(shared_scratch::Owner::PROGRAM_STORE_COMPRESSION,
                       MAX_IMAGE1_SIZE)) {
      output = scratch.data();
      plan.workspace = large_buffer.data();
      plan.workspace_size = large_buffer.size();
    } else {
      plan.workspace = fallback_workspace;
      plan.workspace_size = fallback_workspace_size;
    }
  } else if(memory_source) {
    const MemorySource& memory = *(const MemorySource*) source.context;
    if(memory.size != data_len || memory.data == NULL) {
      return CompressionChoice::RAW;
    }
    plan.input = memory.data;
    if(large_buffer.data() != NULL &&
       scratch.acquire(shared_scratch::Owner::PROGRAM_STORE_COMPRESSION,
                       MAX_IMAGE1_SIZE)) {
      output = scratch.data();
      plan.workspace = large_buffer.data();
      plan.workspace_size = large_buffer.size();
    } else {
      plan.workspace = fallback_workspace;
      plan.workspace_size = fallback_workspace_size;
    }
  } else if(data_len <= MAX_IMAGE1_SIZE) {
    if(large_buffer.size() <= MAX_IMAGE1_SIZE + sizeof(u32) ||
       !scratch.acquire(shared_scratch::Owner::PROGRAM_STORE_COMPRESSION,
                        data_len) ||
       !source.read(source.context, 0, scratch.data(), data_len)) {
      return CompressionChoice::RAW;
    }
    plan.input = scratch.data();
    output = large_buffer.data();
    plan.workspace = large_buffer.data() + MAX_IMAGE1_SIZE;
    plan.workspace_size = large_buffer.size() - MAX_IMAGE1_SIZE;
  } else {
    if(large_buffer.size() <= (usize) data_len + sizeof(u32) ||
       !scratch.acquire(shared_scratch::Owner::PROGRAM_STORE_COMPRESSION,
                        MAX_IMAGE1_SIZE) ||
       !source.read(source.context, 0, large_buffer.data(), data_len)) {
      return CompressionChoice::RAW;
    }
    plan.input = large_buffer.data();
    output = scratch.data();
    plan.workspace = large_buffer.data() + data_len;
    plan.workspace_size = large_buffer.size() - data_len;
  }

  // Свободная runtime-арена даёт ZX0 полный 8-КиБ план без постоянной SRAM.
  // Она применяется только как отдельная область: encoder намеренно запрещает
  // пересечение input/workspace.
  if(plan.input != NULL && preferred_workspace != NULL &&
     preferred_workspace_size >= sizeof(u32)) {
    const uintptr_t input_begin = (uintptr_t) plan.input;
    const uintptr_t input_end = input_begin + data_len;
    const uintptr_t work_begin = (uintptr_t) preferred_workspace;
    const uintptr_t work_end = work_begin + preferred_workspace_size;
    if(input_end >= input_begin && work_end >= work_begin &&
       !(input_begin < work_end && work_begin < input_end)) {
      plan.workspace = preferred_workspace;
      plan.workspace_size = preferred_workspace_size;
    }
  }

  if(plan.input == NULL || plan.workspace == NULL ||
     plan.workspace_size < sizeof(u32)) return CompressionChoice::RAW;
  if(!zx0::prepare(plan.input, data_len,
                   plan.workspace, plan.workspace_size,
                   plan.prepared) ||
     plan.prepared.output_size > 0xFFFFU) return CompressionChoice::RAW;

  if(plan.prepared.output_size >= data_len) return CompressionChoice::RAW;
  const u16 saving = (u16) (data_len - plan.prepared.output_size);
  if(saving < ZX0_MIN_SAVING ||
     (u32) saving * 100U <
         (u32) data_len * ZX0_MIN_SAVING_PERCENT) {
    return CompressionChoice::RAW;
  }
  plan.stored_len = (u16) plan.prepared.output_size;
  if(plan.stored_len <= MAX_IMAGE1_SIZE && output != NULL) {
    MemoryOutput packed = {output, MAX_IMAGE1_SIZE, 0};
    const zx0::Output sink = {&packed, write_memory_output};
    if(!zx0::emit(plan.prepared, sink) ||
       packed.size != plan.stored_len) return CompressionChoice::ERROR;
    if(packed.data == scratch.data()) {
      memcpy(large_buffer.data(), packed.data, packed.size);
      plan.stored_data = large_buffer.data();
    } else {
      plan.stored_data = packed.data;
    }
    scratch.reset();
  } else if(plan.stored_len > MAX_IMAGE1_SIZE && scratch.ok() &&
            plan.input != scratch.data()) {
    scratch.reset();
  }
  return CompressionChoice::ZX0;
}

static void encode_record_crc_stable(
    u8 stable[11], NodeKind kind, ProgramType type, u16 id,
    u16 parent_id, const char* name, u16 stored_len) {
  stable[0] = (u8) kind;
  stable[1] = (u8) type;
  put_le16(stable, 2, id);
  put_le16(stable, 4, parent_id);
  put_le16(stable, 6, stored_len);
  stable[8] = (u8) strlen(name);
  stable[9] = PHYSICAL_FORMAT_VERSION;
  stable[10] = 0x5A;
}

static bool update_record_crc_prefix(mk61_crc32::Context& crc,
                                     NodeKind kind, ProgramType type, u16 id,
                                     u16 parent_id, const char* name,
                                     u16 stored_len) {
  u8 stable[11];
  encode_record_crc_stable(
      stable, kind, type, id, parent_id, name, stored_len);
  return crc.update(stable, sizeof(stable)) &&
         crc.update((const u8*) name, strlen(name));
}

static u32 record_crc_prefix_state(
    NodeKind kind, ProgramType type, u16 id, u16 parent_id,
    const char* name, u16 stored_len) {
  u8 stable[11];
  encode_record_crc_stable(
      stable, kind, type, id, parent_id, name, stored_len);
  const u32 state = crc32_bytes(stable, sizeof(stable));
  return crc32_bytes((const u8*) name, strlen(name), state);
}

static bool record_crc_source(NodeKind kind, ProgramType type, u16 id,
                              u16 parent_id, const char* name,
                              const FileSource& source, u16 data_len,
                              u32& output) {
  u32 state =
      record_crc_prefix_state(kind, type, id, parent_id, name, data_len);
  u8 buffer[64];
  u16 offset = 0;
  while(offset < data_len) {
    const u16 remaining = (u16) (data_len - offset);
    const u16 count = remaining < (u16) sizeof(buffer)
        ? remaining : (u16) sizeof(buffer);
    if(!source.read(source.context, offset, buffer, count)) return false;
    state = crc32_bytes(buffer, count, state);
    offset = (u16) (offset + count);
  }
  output = mk61_crc32::finish(state);
  return true;
}

static bool append_record_source(NodeKind kind, ProgramType type, u16 id,
                                 u16 parent_id, const char* name,
                                 const FileSource& source, u16 data_len,
                                 u32& address, u16& record_len) {
  if(!source_valid(source, data_len)) return false;
  const u8 name_len = (u8) strlen(name);
  record_len = (u16) (RECORD_HEADER_SIZE + name_len + data_len);
  if(!ensure_record_space(record_len, address)) return false;
  u32 crc = 0;
  if(!record_crc_source(kind, type, id, parent_id, name, source,
                        data_len, crc)) return false;

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
  put_le32(header, 12, crc);
  if(!write_bytes(address, header, sizeof(header)) ||
     !write_bytes(address + RECORD_HEADER_SIZE, (const u8*) name, name_len)) {
    return false;
  }
  u8 buffer[64];
  u16 offset = 0;
  while(offset < data_len) {
    const u16 remaining = (u16) (data_len - offset);
    const u16 count = remaining < (u16) sizeof(buffer)
        ? remaining : (u16) sizeof(buffer);
    if(!source.read(source.context, offset, buffer, count) ||
       !write_bytes(address + RECORD_HEADER_SIZE + name_len + offset,
                    buffer, count)) return false;
    offset = (u16) (offset + count);
  }
  if(!write_byte(address + 2, STATE_ACTIVE)) return false;
  g_meta.current_offset = (u16) (g_meta.current_offset + record_len);
  return true;
}

static bool append_record(NodeKind kind, ProgramType type, u16 id,
                          u16 parent_id, const char* name, const u8* data,
                          u16 data_len, u32& address, u16& record_len) {
  MemorySource memory = { data, data_len };
  const FileSource source = { &memory, read_memory_source };
  return append_record_source(kind, type, id, parent_id, name, source,
                              data_len, address, record_len);
}

struct Zx0CrcOutput {
  mk61_crc32::Context* crc;
  u16 size;
  u16 expected_size;
};

static bool write_zx0_crc_byte(void* context, u8 value) {
  Zx0CrcOutput& output = *(Zx0CrcOutput*) context;
  if(output.size >= output.expected_size ||
     !output.crc->update_byte(value)) return false;
  output.size++;
  return true;
}

struct FlashEncodeOutput {
  u32 address;
  u16 size;
  u16 expected_size;
  u8 buffer[64];
  u8 buffered;
};

static bool flush_flash_encode_output(FlashEncodeOutput& output) {
  if(output.buffered == 0) return true;
  if(!write_bytes(output.address + output.size - output.buffered,
                  output.buffer, output.buffered)) return false;
  output.buffered = 0;
  return true;
}

static bool write_flash_encode_byte(void* context, u8 value) {
  FlashEncodeOutput& output = *(FlashEncodeOutput*) context;
  if(output.size >= output.expected_size) return false;
  output.buffer[output.buffered++] = value;
  output.size++;
  return output.buffered != sizeof(output.buffer) ||
         flush_flash_encode_output(output);
}

static bool append_zx0_record(ProgramType type, u16 id, u16 parent_id,
                              const char* name,
                              const zx0::Prepared& prepared,
                              u16 stored_len,
                              u32& address, u16& record_len) {
  if(stored_len == 0 || prepared.output_size != stored_len) return false;
  const u8 name_len = (u8) strlen(name);
  record_len = (u16) (RECORD_HEADER_SIZE + name_len + stored_len);

  mk61_crc32::Context record_crc;
  if(!update_record_crc_prefix(
       record_crc, NodeKind::FILE, type, id, parent_id,
       name, stored_len)) return false;
  Zx0CrcOutput checked = {&record_crc, 0, stored_len};
  const zx0::Output crc_sink = {&checked, write_zx0_crc_byte};
  if(!zx0::emit(prepared, crc_sink) ||
     checked.size != stored_len) return false;
  const u32 checksum = record_crc.finish();
  if(!ensure_record_space(record_len, address)) return false;

  u8 header[RECORD_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  header[0] = 'R';
  header[1] = '5';
  header[2] = STATE_WRITING;
  header[3] = (u8) NodeKind::FILE;
  put_le16(header, 4, id);
  put_le16(header, 6, parent_id);
  put_le16(header, 8, stored_len);
  header[10] = name_len;
  header[11] = (u8) type;
  put_le32(header, 12, checksum);
  if(!write_bytes(address, header, sizeof(header)) ||
     !write_bytes(address + RECORD_HEADER_SIZE,
                  (const u8*) name, name_len)) return false;

  FlashEncodeOutput encoded = {
    address + RECORD_HEADER_SIZE + name_len,
    0, stored_len, {}, 0
  };
  const zx0::Output flash_sink = {&encoded, write_flash_encode_byte};
  if(!zx0::emit(prepared, flash_sink) || encoded.size != stored_len ||
     !flush_flash_encode_output(encoded) ||
     !write_byte(address + 2, STATE_ACTIVE)) return false;
  g_meta.current_offset = (u16) (g_meta.current_offset + record_len);
  return true;
}

static bool read_record_header(const Inode& inode, u16 expected_id, u8* header) {
  if(!visible_inode(inode) || inode.address >= EXTENT_ADDRESS || inode.record_len < RECORD_HEADER_SIZE ||
     !inode_flags_valid(inode) ||
     !read_bytes(inode.address, header, RECORD_HEADER_SIZE)) return false;
  const u16 stored_len = get_le16(header, 8);
  const bool length_valid = large_file_inode(inode)
      ? stored_len <= LARGE_DESCRIPTOR_SIZE
      : inode_kind(inode) != NodeKind::FILE
          ? stored_len == 0
          : zx0_file_inode(inode)
              ? stored_len != 0 && stored_len < inode.data_len
              : stored_len == inode.data_len;
  return header[0] == 'R' && header[1] == '5' && header[2] == STATE_ACTIVE &&
         header[3] == (u8) inode_kind(inode) && get_le16(header, 4) == expected_id &&
         get_le16(header, 6) == inode.parent_id && length_valid &&
         header[10] != 0 && header[10] < NAME_SIZE &&
         (u16) (RECORD_HEADER_SIZE + header[10] + stored_len) ==
             inode.record_len;
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
  mk61_crc32::Context crc;
  return update_record_crc_prefix(
             crc, (NodeKind) header[3], (ProgramType) header[11],
             id, inode.parent_id, name, get_le16(header, 8)) &&
         crc32_flash(
             crc, inode.address + RECORD_HEADER_SIZE + header[10],
             get_le16(header, 8)) &&
         crc.finish() == get_le32(header, 12);
}

struct RecordPayloadInput {
  u32 address;
  u16 size;
  u16 position;
  u8 buffer[64];
  u8 buffered;
  u8 cursor;
  mk61_crc32::Context* crc;
};

static bool next_record_payload_byte(void* context, u8& value) {
  RecordPayloadInput& input = *(RecordPayloadInput*) context;
  if(input.position >= input.size) return false;
  if(input.cursor >= input.buffered) {
    const u16 remaining = (u16) (input.size - input.position);
    input.buffered = (u8) (remaining < sizeof(input.buffer)
        ? remaining : sizeof(input.buffer));
    input.cursor = 0;
    if(!read_bytes(input.address + input.position,
                   input.buffer, input.buffered) ||
       !input.crc->update(input.buffer, input.buffered)) return false;
  }
  value = input.buffer[input.cursor++];
  input.position++;
  return true;
}

static bool read_zx0_record_range(u16 id, const Inode& inode,
                                  const char* name, const u8* header,
                                  u16 offset, u8* output, u16 size) {
  const u16 stored_len = get_le16(header, 8);
  mk61_crc32::Context record_crc;
  if(!update_record_crc_prefix(
       record_crc, (NodeKind) header[3], (ProgramType) header[11],
       id, inode.parent_id, name, stored_len)) return false;
  RecordPayloadInput compressed = {
    inode.address + RECORD_HEADER_SIZE + header[10],
    stored_len, 0, {}, 0, 0, &record_crc
  };
  const zx0::Input input = {&compressed, next_record_payload_byte};
  u8 window[256] = {};
  return zx0::decode_range(input, stored_len, inode.data_len,
                           offset, output, size, window, sizeof(window)) &&
         compressed.position == stored_len &&
         record_crc.finish() == get_le32(header, 12);
}

static u16 large_block_length(const LargeDescriptor& descriptor,
                              u8 block_index) {
  const u32 offset = (u32) block_index * LARGE_BLOCK_DATA_SIZE;
  if(offset >= descriptor.stored_len) return 0;
  const u32 remaining = (u32) descriptor.stored_len - offset;
  return remaining < LARGE_BLOCK_DATA_SIZE
      ? (u16) remaining : LARGE_BLOCK_DATA_SIZE;
}

static void encode_large_descriptor(const LargeDescriptor& descriptor,
                                    u8* output, u16& size) {
  size = (u16) (LARGE_DESCRIPTOR_HEADER_SIZE +
                (u16) descriptor.block_count * sizeof(u32));
  memset(output, 0xFF, LARGE_DESCRIPTOR_SIZE);
  memcpy(output, "C5L0", 4);
  output[4] = descriptor.version;
  output[5] = descriptor.block_count;
  put_le16(output, 6, LARGE_DESCRIPTOR_HEADER_SIZE);
  put_le16(output, 8, descriptor.data_len);
  put_le16(output, 10, descriptor.stored_len);
  put_le32(output, 12, descriptor.generation);
  put_le32(output, 16, descriptor.data_crc);
  for(u8 index = 0; index < descriptor.block_count; index++) {
    put_le32(output, (u16) (LARGE_DESCRIPTOR_HEADER_SIZE +
                            index * sizeof(u32)),
             descriptor.sectors[index]);
  }
}

static bool decode_large_descriptor(const u8* input, u16 size,
                                    LargeDescriptor& descriptor) {
  memset(&descriptor, 0, sizeof(descriptor));
  if(input == NULL || size < LARGE_DESCRIPTOR_HEADER_SIZE ||
     memcmp(input, "C5L0", 4) != 0 ||
     (input[4] != LEGACY_LARGE_DESCRIPTOR_VERSION &&
      input[4] != LARGE_DESCRIPTOR_VERSION) ||
     get_le16(input, 6) != LARGE_DESCRIPTOR_HEADER_SIZE) return false;
  descriptor.version = input[4];
  descriptor.block_count = input[5];
  descriptor.data_len = get_le16(input, 8);
  descriptor.stored_len =
      descriptor.version == LEGACY_LARGE_DESCRIPTOR_VERSION
          ? descriptor.data_len : get_le16(input, 10);
  descriptor.generation = get_le32(input, 12);
  descriptor.data_crc = get_le32(input, 16);
  if(descriptor.data_len == 0 || descriptor.data_len > MAX_APP_FILE_SIZE ||
     descriptor.stored_len == 0 ||
     descriptor.stored_len > descriptor.data_len ||
     descriptor.block_count == 0 ||
     descriptor.block_count > LARGE_BLOCK_COUNT ||
     descriptor.block_count !=
         (descriptor.stored_len + LARGE_BLOCK_DATA_SIZE - 1U) /
             LARGE_BLOCK_DATA_SIZE ||
     size != LARGE_DESCRIPTOR_HEADER_SIZE +
                 (u16) descriptor.block_count * sizeof(u32) ||
     descriptor.generation == 0 ||
     descriptor.generation == 0xFFFFFFFFUL) return false;
  for(u8 index = 0; index < descriptor.block_count; index++) {
    const u32 sector = get_le32(
        input, (u16) (LARGE_DESCRIPTOR_HEADER_SIZE + index * sizeof(u32)));
    if(!data_sector_in_range(sector)) return false;
    for(u8 previous = 0; previous < index; previous++) {
      if(descriptor.sectors[previous] == sector) return false;
    }
    descriptor.sectors[index] = sector;
  }
  return true;
}

static bool read_large_descriptor(u16 id, const Inode& inode,
                                  LargeDescriptor& descriptor) {
  if(!large_file_inode(inode)) return false;
  char name[NAME_SIZE];
  u8 header[RECORD_HEADER_SIZE];
  if(!read_inode_name(id, inode, name) ||
     !verify_record_crc(id, inode, name) ||
     !read_record_header(inode, id, header)) return false;
  const u16 size = get_le16(header, 8);
  if(size > LARGE_DESCRIPTOR_SIZE) return false;
  u8 encoded[LARGE_DESCRIPTOR_SIZE];
  if(!read_bytes(inode.address + RECORD_HEADER_SIZE + header[10],
                 encoded, size) ||
     !decode_large_descriptor(encoded, size, descriptor) ||
     descriptor.data_len != inode.data_len ||
     (zx0_file_inode(inode)
          ? descriptor.stored_len >= descriptor.data_len
          : descriptor.stored_len != descriptor.data_len)) return false;
  return true;
}

static bool large_block_header(u32 sector, u16 id,
                               const LargeDescriptor& descriptor,
                               u8 block_index, u8* header) {
  if(header == NULL || block_index >= descriptor.block_count ||
     descriptor.sectors[block_index] != sector ||
     !read_bytes(sector_address(sector), header,
                 LARGE_BLOCK_HEADER_SIZE)) return false;
  const u16 data_len = large_block_length(descriptor, block_index);
  return memcmp(header, "C5B0", 4) == 0 &&
         header[4] == descriptor.version &&
         header[5] == STATE_ACTIVE &&
         get_le16(header, 6) == LARGE_BLOCK_HEADER_SIZE &&
         get_le32(header, 8) == g_format_epoch &&
         get_le16(header, 12) == id &&
         get_le16(header, 14) == block_index &&
         get_le32(header, 16) == descriptor.generation &&
         get_le16(header, 20) == data_len &&
         normalized_record_crc(header, LARGE_BLOCK_HEADER_SIZE, 28, 5) ==
             get_le32(header, 28);
}

static bool verify_large_block(u16 id, const LargeDescriptor& descriptor,
                               u8 block_index) {
  if(g_verified_large_id == id &&
     g_verified_large_generation == descriptor.generation &&
     g_verified_large_block == block_index) return true;
  u8 header[LARGE_BLOCK_HEADER_SIZE];
  const u32 sector = descriptor.sectors[block_index];
  if(!large_block_header(sector, id, descriptor, block_index, header)) {
    return false;
  }
  const u16 data_len = get_le16(header, 20);
  u32 crc = 0;
  if(!crc32_flash(
       sector_address(sector) + LARGE_BLOCK_HEADER_SIZE,
       data_len, crc)) return false;
  if(crc != get_le32(header, 24)) return false;
  g_verified_large_id = id;
  g_verified_large_generation = descriptor.generation;
  g_verified_large_block = block_index;
  return true;
}

static bool read_large_data(u16 id, const LargeDescriptor& descriptor,
                            u16 offset, u8* output, u16 size) {
  while(size != 0) {
    const u8 block = (u8) (offset / LARGE_BLOCK_DATA_SIZE);
    const u16 in_block = (u16) (offset % LARGE_BLOCK_DATA_SIZE);
    if(block >= descriptor.block_count ||
       !verify_large_block(id, descriptor, block)) return false;
    const u16 available =
        (u16) (large_block_length(descriptor, block) - in_block);
    const u16 count = size < available ? size : available;
    if(count == 0 ||
       !read_bytes(sector_address(descriptor.sectors[block]) +
                       LARGE_BLOCK_HEADER_SIZE + in_block,
                   output, count)) return false;
    output += count;
    offset = (u16) (offset + count);
    size = (u16) (size - count);
  }
  return true;
}

struct LargePayloadInput {
  u16 id;
  const LargeDescriptor* descriptor;
  u16 position;
  u8 buffer[64];
  u8 buffered;
  u8 cursor;
  u32 crc;
};

static bool next_large_payload_byte(void* context, u8& value) {
  LargePayloadInput& input = *(LargePayloadInput*) context;
  if(input.position >= input.descriptor->stored_len) return false;
  if(input.cursor >= input.buffered) {
    const u8 block = (u8) (input.position / LARGE_BLOCK_DATA_SIZE);
    const u16 in_block =
        (u16) (input.position % LARGE_BLOCK_DATA_SIZE);
    if(block >= input.descriptor->block_count ||
       !verify_large_block(input.id, *input.descriptor, block)) return false;
    const u16 block_remaining =
        (u16) (large_block_length(*input.descriptor, block) - in_block);
    const u16 total_remaining =
        (u16) (input.descriptor->stored_len - input.position);
    u16 count = block_remaining < total_remaining
        ? block_remaining : total_remaining;
    if(count > sizeof(input.buffer)) count = sizeof(input.buffer);
    if(count == 0 ||
       !read_bytes(sector_address(input.descriptor->sectors[block]) +
                       LARGE_BLOCK_HEADER_SIZE + in_block,
                   input.buffer, count)) return false;
    input.crc = crc32_bytes(input.buffer, count, input.crc);
    input.buffered = (u8) count;
    input.cursor = 0;
  }
  value = input.buffer[input.cursor++];
  input.position++;
  return true;
}

static bool read_large_zx0_range(u16 id,
                                 const LargeDescriptor& descriptor,
                                 u16 offset, u8* output, u16 size) {
  LargePayloadInput compressed = {
    id, &descriptor, 0, {}, 0, 0, mk61_crc32::INITIAL_STATE
  };
  const zx0::Input input = {&compressed, next_large_payload_byte};
  u8 window[256] = {};
  return zx0::decode_range(input, descriptor.stored_len,
                           descriptor.data_len, offset, output, size,
                           window, sizeof(window)) &&
         compressed.position == descriptor.stored_len &&
         mk61_crc32::finish(compressed.crc) == descriptor.data_crc;
}

static bool payload_equals_source(u16 id, const Inode& inode,
                                  const char* name,
                                  const FileSource& source, u16 data_len) {
  if(inode_kind(inode) != NodeKind::FILE || inode.data_len != data_len ||
     !source_valid(source, data_len)) return false;
  u8 actual[64];
  u8 expected[64];
  LargeDescriptor descriptor = {};
  u8 header[RECORD_HEADER_SIZE] = {};
  u32 address = 0;
  if(large_file_inode(inode)) {
    if(!read_large_descriptor(id, inode, descriptor)) return false;
  } else {
    if(!read_record_header(inode, id, header) ||
       (!zx0_file_inode(inode) &&
        !verify_record_crc(id, inode, name))) return false;
    address = inode.address + RECORD_HEADER_SIZE + header[10];
  }
  u16 offset = 0;
  while(offset < data_len) {
    const u16 remaining = (u16) (data_len - offset);
    const u16 count = remaining < (u16) sizeof(actual)
      ? remaining : (u16) sizeof(actual);
    const bool read_ok = zx0_file_inode(inode)
        ? (large_file_inode(inode)
              ? read_large_zx0_range(
                    id, descriptor, offset, actual, count)
              : read_zx0_record_range(
                    id, inode, name, header, offset, actual, count))
        : (large_file_inode(inode)
              ? read_large_data(id, descriptor, offset, actual, count)
              : read_bytes(address + offset, actual, count));
    if(!read_ok ||
       !source.read(source.context, offset, expected, count) ||
       memcmp(actual, expected, count) != 0) return false;
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

template<usize N>
static bool fat_visible_name(NodeKind kind, ProgramType type,
                             const char* name, char (&out)[N]) {
  if(name == NULL) return false;
  const usize length = bounded_string::copy(out, name);
  if(name[length] != 0) return false;
  if(kind != NodeKind::FILE) return true;
  if(length + 1 >= N) return false;
  out[length] = '.';
  const char* extension = extension_for_type(type);
  const usize extension_length = bounded_string::copy(
      out + length + 1, N - length - 1, extension);
  return extension[extension_length] == 0;
}

static bool fat_name_available(u16 parent_id, NodeKind kind,
                               ProgramType type, const char* name,
                               u16 ignore_id) {
  char wanted[NAME_SIZE + 16];
  if(!fat_visible_name(kind, type, name, wanted)) return false;
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
      if(!fat_visible_name(inode_kind(inode), inode_type(inode), stored,
                           visible)) return false;
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
  const u32 capacity = flash_device().getCapacity();
#else
  const u32 capacity = 0;
#endif
  if(!compute_geometry(capacity, g_geometry)) return false;
  g_format_epoch = 0xC5F50001UL ^ capacity ^ millis();
  if(g_format_epoch == 0 || g_format_epoch == 0xFFFFFFFFUL) g_format_epoch ^= 0x13579BDFUL;
  g_ready = false;
  g_mount_status = MountStatus::UNAVAILABLE;
  g_active_bank = 1;
  g_catalog_generation = 0;
  g_wal_sequence = 0;
  g_wal_records = 0;
  g_wal_sealed = false;
  g_overlay_count = 0;
  g_free_hint = 0;
  g_locator_store_version = 0;
  g_locator_matching_copies = 0;
  g_catalog_write_version = CATALOG_VERSION;
  g_large_write_sector_count = 0;
  g_verified_large_id = NONE;
  g_verified_large_generation = 0;
  g_verified_large_block = 0xFF;
  g_table_cache_address = EMPTY_ADDRESS;
  memset(&g_meta, 0, sizeof(g_meta));
  g_meta.root_head = NONE;
  g_meta.current_sector = EMPTY_ADDRESS;
  g_meta.current_offset = 0;
  g_meta.reserve_sector = g_geometry.data_first_sector + g_geometry.data_sector_count - 1;
  g_meta.gc_cursor = g_geometry.data_first_sector;
  g_meta.data_sequence = 0;

  // checkpoint() сама стирает и публикует новый активный банк. Другой банк
  // привязан к эпохе и будет стёрт, когда снова станет приёмником COW, поэтому
  // предварительное стирание обоих банков здесь лишь утраивало работу с
  // каталогом при первом запуске на W25Q128 ёмкостью 16 МиБ.
  if(!checkpoint()) return false;
  // Заголовки staging также содержат эпоху форматирования. Старые или чужие
  // секторы после форматирования игнорируются и стираются лениво перед первой записью.
  if(erase_settings) {
    if(!erase_sector(g_geometry.settings_sector) || !write_settings_guard()) return false;
  } else if(!settings_guard_valid(g_geometry)) {
    return false;
  }
  if(!write_locators()) return false;
  g_ready = true;
  g_mount_status = MountStatus::READY;
  return true;
}

} // пространство имён

static bool sweep_orphan_file_extents(void);

void init(void) {
  DiskActivity activity;
  g_ready = false;
  g_mount_status = MountStatus::UNAVAILABLE;
  g_free_hint = 0;
  memset(&g_geometry, 0, sizeof(g_geometry));
  if(!flash_is_ok) return;
  dbgln(SPIROM, "C5 locator: scan");
  if(!load_locator()) {
    dbgln(SPIROM, "C5 locator: absent or incompatible");
    const bool preserve_settings = load_capacity_for_reformat();
    u32 capacity = 0;
#ifdef SPI_FLASH
    if(!preserve_settings) {
      dbgln(SPIROM, "C5 capacity probe: start");
#ifdef DEBUG_SPIFLASH
      const flash_capacity_probe::ProbeProgress progress =
          capacity_probe_debug;
#else
      const flash_capacity_probe::ProbeProgress progress = nullptr;
#endif
      if(!flash_capacity_probe::detect(
             flash_device(), flash_device().capacityProbeUpper(), capacity, progress) ||
         !flash_device().setCapacity(capacity)) {
        dbgln(SPIROM, "C5 capacity probe: failed");
        return;
      }
    }
#endif
    if(!preserve_settings) {
      dbgln(SPIROM, "C5 capacity probe: ", (isize) capacity, " bytes");
    } else {
      dbgln(SPIROM, "C5 geometry migration: preserve settings");
    }
    dbgln(SPIROM, "C5 format: start");
    if(!format_internal(!preserve_settings)) {
      dbgln(SPIROM, "C5 format: failed");
      return;
    }
    dbgln(SPIROM, "C5 format: complete");
  } else if(!load_or_migrate_catalog()) {
    dbgln(SPIROM, "C5 catalog: both banks invalid");
    // Действительный локатор доказывает, что это существующий том C5. Потеря
    // обоих банков каталога не должна выглядеть как первое использование:
    // сохраняем каждый байт до явного запроса пользователя на форматирование.
    g_mount_status = MountStatus::REPAIR_REQUIRED;
  } else {
    dbgln(SPIROM, "C5 catalog: ready");
    g_ready = true;
    g_mount_status = MountStatus::READY;
  }
  if(g_ready) {
    (void) sweep_orphan_file_extents();
    vfat_stage_clear();
  }
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

MountStatus mount_status(void) { return g_mount_status; }

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
  return (g_ready || g_mount_status == MountStatus::REPAIR_REQUIRED)
      ? sector_address(g_geometry.settings_sector) : 0;
}

u16 settings_size(void) {
  return (g_ready || g_mount_status == MountStatus::REPAIR_REQUIRED)
      ? SETTINGS_JOURNAL_SIZE : 0;
}

bool erase_settings(void) {
  DiskActivity activity;
  return (g_ready || g_mount_status == MountStatus::REPAIR_REQUIRED) &&
         erase_sector(g_geometry.settings_sector) &&
         write_settings_guard();
}

const char* file_extension(ProgramType type) {
  return extension_for_type(type);
}

TypeMagic type_magic(ProgramType type) {
  const char* text = magic_for_type(type);
  return make_type_magic(text[0], text[1]);
}

const char* type_magic_text(ProgramType type) {
  return magic_for_type(type);
}

bool type_from_magic(TypeMagic magic, ProgramType& type) {
  static const ProgramType TYPES[] = {
    ProgramType::MK61,
    ProgramType::FOCAL,
    ProgramType::TINYBASIC,
    ProgramType::TEXT,
    ProgramType::MK61_STATE,
    ProgramType::FONT,
    ProgramType::IMAGE1,
    ProgramType::APP,
    ProgramType::CHIP8,
    ProgramType::MARKDOWN
  };
  for(const ProgramType candidate : TYPES) {
    if(type_magic(candidate) != magic) continue;
    type = candidate;
    return true;
  }
  return false;
}

int total_count(void) { return g_ready ? g_meta.total_count : 0; }

int count(ProgramType type) {
  const int index = type_index(type);
  if(!g_ready) return 0;
  if(index >= 0) return g_meta.type_count[index];
  if(!supported_type(type)) return 0;
  int result = 0;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(get_inode(id, inode) && inode_used(inode) &&
       inode_kind(inode) == NodeKind::FILE &&
       inode_type(inode) == type) result++;
  }
  return result;
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

class LargeWriteGuard {
  public:
    LargeWriteGuard(void) {
      g_large_write_sector_count = 0;
      g_verified_large_id = NONE;
      g_verified_large_block = 0xFF;
    }
    ~LargeWriteGuard(void) { g_large_write_sector_count = 0; }
};

static bool select_large_sector(u32& output) {
  const u32 first = g_geometry.data_first_sector;
  const u32 count = g_geometry.data_sector_count;
  const u32 start = data_sector_in_range(g_meta.gc_cursor)
      ? g_meta.gc_cursor : first;
  for(u32 offset = 0; offset < count; offset++) {
    const u32 sector = first + (start - first + offset) % count;
    if(sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
       sector_has_live_inode(sector)) continue;
    if(!erase_sector(sector)) continue;
    output = sector;
    g_meta.gc_cursor = first + (sector - first + 1) % count;
    return true;
  }
  return false;
}

static bool program_large_source(u16 id, const FileSource& source,
                                 u16 data_len,
                                 LargeDescriptor& descriptor) {
  memset(&descriptor, 0, sizeof(descriptor));
  descriptor.data_len = data_len;
  descriptor.stored_len = data_len;
  descriptor.version = LARGE_DESCRIPTOR_VERSION;
  descriptor.block_count = (u8) (
      (descriptor.stored_len + LARGE_BLOCK_DATA_SIZE - 1U) /
          LARGE_BLOCK_DATA_SIZE);
  if(descriptor.block_count == 0 ||
     descriptor.block_count > LARGE_BLOCK_COUNT) return false;
  descriptor.generation = ++g_meta.data_sequence;
  if(descriptor.generation == 0 ||
     descriptor.generation == 0xFFFFFFFFUL) {
    descriptor.generation = ++g_meta.data_sequence;
  }

  u32 file_crc = mk61_crc32::INITIAL_STATE;
  u8 buffer[64];
  u16 file_offset = 0;
  for(u8 block = 0; block < descriptor.block_count; block++) {
    u32 sector = EMPTY_ADDRESS;
    if(!select_large_sector(sector)) return false;
    descriptor.sectors[block] = sector;
    g_large_write_sectors[g_large_write_sector_count++] = sector;

    const u16 block_len = large_block_length(descriptor, block);
    u32 block_crc = 0xFFFFFFFFUL;
    u16 block_offset = 0;
    while(block_offset < block_len) {
      const u16 remaining = (u16) (block_len - block_offset);
      const u16 count = remaining < (u16) sizeof(buffer)
          ? remaining : (u16) sizeof(buffer);
      if(!source.read(source.context, file_offset, buffer, count) ||
         !write_bytes(sector_address(sector) + LARGE_BLOCK_HEADER_SIZE +
                          block_offset,
                      buffer, count)) return false;
      block_crc = crc32_bytes(buffer, count, block_crc);
      file_crc = crc32_bytes(buffer, count, file_crc);
      file_offset = (u16) (file_offset + count);
      block_offset = (u16) (block_offset + count);
    }

    u8 header[LARGE_BLOCK_HEADER_SIZE];
    memset(header, 0xFF, sizeof(header));
    memcpy(header, "C5B0", 4);
    header[4] = descriptor.version;
    header[5] = STATE_WRITING;
    put_le16(header, 6, LARGE_BLOCK_HEADER_SIZE);
    put_le32(header, 8, g_format_epoch);
    put_le16(header, 12, id);
    put_le16(header, 14, block);
    put_le32(header, 16, descriptor.generation);
    put_le16(header, 20, block_len);
    put_le32(header, 24, ~block_crc);
    put_le32(header, 28,
             normalized_record_crc(header, sizeof(header), 28, 5));
    const u32 address = sector_address(sector);
    u32 verified_crc = 0;
    if(!write_bytes(address, header, sizeof(header)) ||
       !write_byte(address + 5, STATE_ACTIVE) ||
       !crc32_flash(address + LARGE_BLOCK_HEADER_SIZE,
                    block_len, verified_crc) ||
       verified_crc != get_le32(header, 24)) return false;
  }
  descriptor.data_crc = mk61_crc32::finish(file_crc);
  return file_offset == descriptor.stored_len;
}

namespace {

struct LargeZx0Output {
  u16 id;
  LargeDescriptor* descriptor;
  u16 position;
  u8 buffer[64];
  u8 buffered;
  u32 block_crc[LARGE_BLOCK_COUNT];
  mk61_crc32::Context* file_crc;
};

static bool flush_large_zx0_output(LargeZx0Output& output) {
  if(output.buffered == 0) return true;
  const u16 start = (u16) (output.position - output.buffered);
  const u8 block = (u8) (start / LARGE_BLOCK_DATA_SIZE);
  const u16 in_block = (u16) (start % LARGE_BLOCK_DATA_SIZE);
  if(block >= output.descriptor->block_count ||
     (u32) in_block + output.buffered >
         large_block_length(*output.descriptor, block) ||
     !write_bytes(sector_address(output.descriptor->sectors[block]) +
                      LARGE_BLOCK_HEADER_SIZE + in_block,
                  output.buffer, output.buffered)) return false;
  output.block_crc[block] =
      crc32_bytes(output.buffer, output.buffered, output.block_crc[block]);
  if(!output.file_crc->update(output.buffer, output.buffered)) return false;
  output.buffered = 0;
  return true;
}

static bool write_large_zx0_byte(void* context, u8 value) {
  LargeZx0Output& output = *(LargeZx0Output*) context;
  if(output.position >= output.descriptor->stored_len) return false;
  output.buffer[output.buffered++] = value;
  output.position++;
  if(output.buffered == sizeof(output.buffer) ||
     output.position == output.descriptor->stored_len ||
     output.position % LARGE_BLOCK_DATA_SIZE == 0) {
    return flush_large_zx0_output(output);
  }
  return true;
}

static bool finish_large_zx0_output(LargeZx0Output& output) {
  if(!flush_large_zx0_output(output) ||
     output.position != output.descriptor->stored_len) return false;
  for(u8 block = 0; block < output.descriptor->block_count; block++) {
    const u16 block_len = large_block_length(*output.descriptor, block);
    u8 header[LARGE_BLOCK_HEADER_SIZE];
    memset(header, 0xFF, sizeof(header));
    memcpy(header, "C5B0", 4);
    header[4] = output.descriptor->version;
    header[5] = STATE_WRITING;
    put_le16(header, 6, LARGE_BLOCK_HEADER_SIZE);
    put_le32(header, 8, g_format_epoch);
    put_le16(header, 12, output.id);
    put_le16(header, 14, block);
    put_le32(header, 16, output.descriptor->generation);
    put_le16(header, 20, block_len);
    put_le32(header, 24, ~output.block_crc[block]);
    put_le32(header, 28,
             normalized_record_crc(header, sizeof(header), 28, 5));
    const u32 address =
        sector_address(output.descriptor->sectors[block]);
    u32 verified_crc = 0;
    if(!write_bytes(address, header, sizeof(header)) ||
       !write_byte(address + 5, STATE_ACTIVE) ||
       !crc32_flash_software(address + LARGE_BLOCK_HEADER_SIZE,
                             block_len, verified_crc) ||
       verified_crc != get_le32(header, 24)) return false;
  }
  output.descriptor->data_crc = output.file_crc->finish();
  return true;
}

} // namespace

static bool program_large_zx0(u16 id,
                              const zx0::Prepared& prepared, u16 data_len,
                              u16 stored_len,
                              LargeDescriptor& descriptor) {
  if(prepared.input_size != data_len ||
     prepared.output_size != stored_len) return false;
  memset(&descriptor, 0, sizeof(descriptor));
  descriptor.data_len = data_len;
  descriptor.stored_len = stored_len;
  descriptor.version = LARGE_DESCRIPTOR_VERSION;
  descriptor.block_count = (u8) (
      (stored_len + LARGE_BLOCK_DATA_SIZE - 1U) / LARGE_BLOCK_DATA_SIZE);
  if(descriptor.block_count == 0 ||
     descriptor.block_count > LARGE_BLOCK_COUNT) return false;
  descriptor.generation = ++g_meta.data_sequence;
  if(descriptor.generation == 0 ||
     descriptor.generation == 0xFFFFFFFFUL) {
    descriptor.generation = ++g_meta.data_sequence;
  }
  for(u8 block = 0; block < descriptor.block_count; block++) {
    u32 sector = EMPTY_ADDRESS;
    if(!select_large_sector(sector)) return false;
    descriptor.sectors[block] = sector;
    g_large_write_sectors[g_large_write_sector_count++] = sector;
  }

  mk61_crc32::Context file_crc;
  LargeZx0Output encoded = {};
  encoded.id = id;
  encoded.descriptor = &descriptor;
  encoded.file_crc = &file_crc;
  for(u8 block = 0; block < LARGE_BLOCK_COUNT; block++) {
    encoded.block_crc[block] = 0xFFFFFFFFUL;
  }
  const zx0::Output sink = {&encoded, write_large_zx0_byte};
  return zx0::emit(prepared, sink) &&
         finish_large_zx0_output(encoded);
}

static bool collect_file_extents(u16 file_id, const Inode& file,
                                 u16* output, u8& count) {
  count = 0;
  u16 current = file.first_child;
  u16 previous = NONE;
  while(current != NONE) {
    if(count >= MAX_FAT_EXTENTS_PER_FILE || current == file_id) return false;
    for(u8 index = 0; index < count; index++) {
      if(output[index] == current) return false;
    }
    Inode extent;
    if(!get_inode(current, extent) ||
       inode_kind(extent) != NodeKind::FILE_EXTENT ||
       extent.parent_id != file_id || extent.prev_sibling != previous ||
       extent.data_len != (u16) (count + 1U)) return false;
    output[count++] = current;
    previous = current;
    current = extent.next_sibling;
  }
  return true;
}

static bool id_selected(const u16* ids, u8 count, u16 id) {
  for(u8 index = 0; index < count; index++) {
    if(ids[index] == id) return true;
  }
  return false;
}

static bool choose_file_extents(u16 file_id, const Inode& old_inode,
                                bool replacing, u8 wanted,
                                const u16* requested, u8 requested_count,
                                u16* output) {
  if(wanted > MAX_FAT_EXTENTS_PER_FILE ||
     (requested != NULL && requested_count != wanted) ||
     (requested == NULL && requested_count != 0)) return false;

  u8 chosen = 0;
  if(requested != NULL) {
    for(u8 index = 0; index < wanted; index++) {
      const u16 id = requested[index];
      if(id >= g_geometry.max_nodes || id == file_id ||
         id_selected(output, chosen, id)) return false;
      Inode inode;
      if(!get_inode(id, inode) ||
         (inode_used(inode) &&
          (inode_kind(inode) != NodeKind::FILE_EXTENT ||
           inode.parent_id != file_id))) return false;
      output[chosen++] = id;
    }
    return true;
  }

  if(replacing && inode_kind(old_inode) == NodeKind::FILE) {
    u16 old[MAX_FAT_EXTENTS_PER_FILE];
    u8 old_count = 0;
    if(!collect_file_extents(file_id, old_inode, old, old_count)) return false;
    while(chosen < wanted && chosen < old_count) {
      output[chosen] = old[chosen];
      chosen++;
    }
  }
  const u16 start = g_free_hint < g_geometry.max_nodes ? g_free_hint : 0;
  for(u16 step = 0; chosen < wanted && step < g_geometry.max_nodes; step++) {
    const u16 id = (u16) ((start + step) % g_geometry.max_nodes);
    if(id == file_id || id_selected(output, chosen, id)) continue;
    Inode inode;
    if(get_inode(id, inode) && !inode_used(inode)) output[chosen++] = id;
  }
  if(chosen != wanted) return false;
  if(wanted != 0) {
    g_free_hint = (u16) ((output[wanted - 1] + 1U) % g_geometry.max_nodes);
  }
  return true;
}

static Inode file_extent_inode(u16 file_id, u8 index,
                               u16 previous, u16 next,
                               ProgramType type) {
  Inode inode = empty_inode();
  inode.address = EXTENT_ADDRESS;
  inode.data_len = (u16) (index + 1U);
  inode.record_len = 0;
  inode.parent_id = file_id;
  inode.first_child = NONE;
  inode.next_sibling = next;
  inode.prev_sibling = previous;
  inode.name_hash = 0;
  inode.kind_type = make_kind_type(NodeKind::FILE_EXTENT, type);
  inode.flags = 0;
  return inode;
}

static bool file_extent_referenced(u16 extent_id, const Inode& extent) {
  if(inode_kind(extent) != NodeKind::FILE_EXTENT ||
     extent.parent_id >= g_geometry.max_nodes) return false;
  Inode file;
  if(!get_inode(extent.parent_id, file) ||
     inode_kind(file) != NodeKind::FILE) {
    return false;
  }
  u16 ids[MAX_FAT_EXTENTS_PER_FILE];
  u8 count = 0;
  if(!collect_file_extents(extent.parent_id, file, ids, count)) return false;
  return id_selected(ids, count, extent_id);
}

static bool sweep_orphan_file_extents(void) {
  u16 id = 0;
  while(id < g_geometry.max_nodes) {
    Transaction transaction;
    txn_begin(transaction);
    while(id < g_geometry.max_nodes && transaction.count < WAL_MAX_UPDATES) {
      Inode inode;
      if(!get_inode(id, inode)) return false;
      if(inode_used(inode) && inode_kind(inode) == NodeKind::FILE_EXTENT &&
         !file_extent_referenced(id, inode) &&
         !txn_set(transaction, id, empty_inode())) return false;
      id++;
    }
    if(transaction.count != 0 && !append_transaction(transaction)) {
      return false;
    }
  }
  g_free_hint = 0;
  return true;
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
  inode.data_len = NONE; // первый экстент каталога
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

bool write_file_from_source(u16 parent_id, u16 preferred_id, ProgramType type,
                            const char* name, u16 data_len,
                            const FileSource& source,
                            const u16* fat_extents, u8 fat_extent_count,
                            u16* out_id,
                            u8* compression_buffer,
                            usize compression_buffer_size,
                            const u8* contiguous_data) {
  DiskActivity activity;
  LargeWriteGuard large_guard;
  alignas(4) u8 fallback_workspace[ZX0_FALLBACK_WORKSPACE_SIZE];
  const u16 max_data_len = maximum_data_len(type);
  if(!g_ready || !supported_type(type) || !valid_name(name) || !parent_valid(parent_id) ||
     (type == ProgramType::CHIP8 && data_len == 0) ||
     data_len > max_data_len ||
     !source_valid(source, data_len)) return false;
  const u32 cluster_bytes =
      (u32) g_geometry.sectors_per_cluster * VFAT_STAGE_BLOCK_SIZE;
  const u8 required_clusters = data_len == 0 ? 1 : (u8) (
      ((u32) data_len + cluster_bytes - 1U) / cluster_bytes);
  const u8 required_extents = (u8) (required_clusters - 1U);
  if(required_extents > MAX_FAT_EXTENTS_PER_FILE ||
     (fat_extents == NULL && fat_extent_count != 0) ||
     (fat_extents != NULL && fat_extent_count != required_extents)) {
    return false;
  }

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
    bool same_extents = fat_extents == NULL;
    if(fat_extents != NULL && inode_kind(old_inode) == NodeKind::FILE) {
      u16 current[MAX_FAT_EXTENTS_PER_FILE];
      u8 current_count = 0;
      same_extents = collect_file_extents(id, old_inode, current,
                                          current_count) &&
                     current_count == fat_extent_count &&
                     memcmp(current, fat_extents,
                            (usize) current_count * sizeof(current[0])) == 0;
    }
    if(old_inode.parent_id == parent_id && inode_type(old_inode) == type &&
       strcmp(old_name, name) == 0 && same_extents &&
       payload_equals_source(id, old_inode, name, source, data_len)) {
      if(out_id != NULL) *out_id = id;
      return true;
    }
  }

  u16 extent_ids[MAX_FAT_EXTENTS_PER_FILE] = {};
  if(!choose_file_extents(id, old_inode, replacing,
                          required_extents, fat_extents,
                          fat_extent_count, extent_ids)) return false;

  CompressionBuffer compression(compression_buffer,
                                compression_buffer_size);
  shared_memory::Lease compression_workspace;
  if(transparent_compression_enabled(type) && data_len >= ZX0_MIN_SAVING) {
    (void) workspace_swap::acquire(
        shared_memory::Owner::PROGRAM_STORE_COMPRESSION,
        shared_memory::WORKSPACE_SIZE,
        workspace_swap::AcquireMode::OPPORTUNISTIC,
        compression_workspace);
  }
  shared_scratch::Lease compression_scratch;
  CompressionPlan compression_plan = {};
  const CompressionChoice compression_choice =
      prepare_compressed_payload(type, source, data_len, compression,
                                 compression_scratch, contiguous_data,
                                 compression_workspace.data(),
                                 compression_workspace.size(),
                                 fallback_workspace,
                                 sizeof(fallback_workspace),
                                 compression_plan);
  if(compression_choice == CompressionChoice::ERROR) return false;
  const bool zx0 = compression_choice == CompressionChoice::ZX0;
  const u16 stored_len = zx0 ? compression_plan.stored_len : data_len;
  const bool large =
      (type == ProgramType::APP || type == ProgramType::CHIP8) &&
      stored_len > MAX_IMAGE1_SIZE;

  u32 address = 0;
  u16 record_len = 0;
  LargeDescriptor descriptor = {};
  if(large) {
    if(!(zx0
          ? program_large_zx0(id, compression_plan.prepared, data_len,
                              stored_len, descriptor)
          : program_large_source(id, source, data_len, descriptor))) {
      return false;
    }
    u8 encoded[LARGE_DESCRIPTOR_SIZE];
    u16 encoded_size = 0;
    encode_large_descriptor(descriptor, encoded, encoded_size);
    if(!append_record(NodeKind::FILE, type, id, parent_id, name,
                      encoded, encoded_size, address, record_len)) return false;
  } else if(zx0) {
    if(compression_plan.stored_data != NULL) {
      if(!append_record(NodeKind::FILE, type, id, parent_id, name,
                        compression_plan.stored_data, stored_len,
                        address, record_len)) return false;
    } else if(!append_zx0_record(
                  type, id, parent_id, name,
                  compression_plan.prepared,
                  stored_len, address, record_len)) {
      return false;
    }
  } else if(!append_record_source(NodeKind::FILE, type, id, parent_id, name,
                                  source, stored_len, address, record_len)) {
    return false;
  }

  Inode inode = replacing ? old_inode : empty_inode();
  inode.address = address;
  inode.data_len = data_len;
  inode.record_len = record_len;
  inode.parent_id = parent_id;
  inode.name_hash = hash_name(name);
  inode.kind_type = make_kind_type(NodeKind::FILE, type);
  inode.flags = (large ? INODE_FLAG_LARGE_FILE : 0) |
                (zx0 ? INODE_FLAG_ZX0 : 0);
  inode.first_child = required_extents != 0
      ? extent_ids[0] : NONE;
  if(!replacing) {
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
      if(new_type_index >= 0) transaction.meta.type_count[new_type_index]++;
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
    if(index >= 0) transaction.meta.type_count[index]++;
    if(!link_at_head(transaction, id, inode, parent_id)) return false;
  }
  if(required_extents != 0) {
    for(u8 index = 0; index < required_extents; index++) {
      const u16 previous = index == 0 ? NONE : extent_ids[index - 1];
      const u16 next = index + 1U < required_extents
          ? extent_ids[index + 1] : NONE;
      if(!txn_set(transaction, extent_ids[index],
                  file_extent_inode(id, index, previous, next, type))) {
        return false;
      }
    }
  }
  if(!append_transaction(transaction)) return false;
  g_verified_large_id = NONE;
  g_verified_large_block = 0xFF;
  (void) sweep_orphan_file_extents();
  if(out_id != NULL) *out_id = id;
  return true;
}

bool write_file(u16 parent_id, u16 preferred_id, ProgramType type,
                const char* name, const u8* data, u16 data_len, u16* out_id) {
  MemorySource memory = { data, data_len };
  const FileSource source = { &memory, read_memory_source };
  return write_file_from_source(parent_id, preferred_id, type, name,
                                data_len, source, NULL, 0, out_id);
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
     offset > inode.data_len || !read_inode_name(id, inode, name)) return false;
  const u16 available = (u16) (inode.data_len - offset);
  const u16 copied = available < len ? available : len;
  if(large_file_inode(inode)) {
    LargeDescriptor descriptor = {};
    if(!read_large_descriptor(id, inode, descriptor)) return false;
    if(zx0_file_inode(inode)) {
      if(!read_large_zx0_range(
            id, descriptor, offset, data, copied)) return false;
    } else if(copied != 0 &&
              !read_large_data(id, descriptor, offset, data, copied)) {
      return false;
    }
  } else {
    u8 header[RECORD_HEADER_SIZE];
    if(!read_record_header(inode, id, header)) return false;
    if(zx0_file_inode(inode)) {
      if(!read_zx0_record_range(id, inode, name, header,
                                offset, data, copied)) return false;
    } else if(!verify_record_crc(id, inode, name) ||
              (copied != 0 &&
               !read_bytes(inode.address + RECORD_HEADER_SIZE +
                               header[10] + offset,
                           data, copied))) {
      return false;
    }
  }
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

  // Экстенты каталога освобождаются с конца до освобождения самого inode.
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
  if(inode_kind(inode) == NodeKind::FILE) {
    g_verified_large_id = NONE;
    g_verified_large_block = 0xFF;
    (void) sweep_orphan_file_extents();
  }
  if(g_free_hint >= g_geometry.max_nodes || id < g_free_hint) g_free_hint = id;
  return true;
}

bool remove_tree(u16 id, u16* removed) {
  DiskActivity activity;
  if(removed != NULL) *removed = 0;
  if(!g_ready || id >= g_geometry.max_nodes) return false;
  Inode root;
  if(!get_inode(id, root) || !visible_inode(root)) return false;

  // Обходное удаление в обратном порядке без стека. MAX_DIRECTORY_DEPTH
  // ограничивает проверку повреждений, а переход к first_child после каждого
  // зафиксированного удаления гарантирует, что сбой питания оставит лишь
  // уменьшенное, но согласованное поддерево.
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

  shared_scratch::Lease scratch;
  u8 descriptor[LARGE_DESCRIPTOR_SIZE];
  const u8* payload = NULL;
  u16 payload_len = 0;
  u8 header[RECORD_HEADER_SIZE];
  char old_name[NAME_SIZE];
  if(!read_inode_name(id, inode, old_name) ||
     !verify_record_crc(id, inode, old_name) ||
     !read_record_header(inode, id, header)) return false;
  payload_len = get_le16(header, 8);
  if(payload_len != 0) {
    u8* target = descriptor;
    usize capacity = sizeof(descriptor);
    if(!large_file_inode(inode)) {
      if(!scratch.acquire(shared_scratch::Owner::PROGRAM_STORE_RENAME,
                          payload_len)) return false;
      target = scratch.data();
      capacity = scratch.size();
    }
    if(payload_len > capacity ||
       !read_bytes(inode.address + RECORD_HEADER_SIZE + header[10],
                   target, payload_len)) return false;
    payload = target;
  }
  u32 address = 0;
  u16 record_len = 0;
  if(!append_record(inode_kind(inode), inode_type(inode), id,
                    new_parent_id, new_name, payload, payload_len,
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

bool release_file_extent(u16 extent_id) {
  DiskActivity activity;
  Inode extent;
  if(!g_ready || !get_inode(extent_id, extent) ||
     inode_kind(extent) != NodeKind::FILE_EXTENT) return false;
  const u16 file_id = extent.parent_id;
  Inode file;
  if(!get_inode(file_id, file) ||
     inode_kind(file) != NodeKind::FILE) return false;

  u16 current[MAX_FAT_EXTENTS_PER_FILE] = {};
  u8 current_count = 0;
  if(!collect_file_extents(file_id, file, current, current_count) ||
     current_count == 0) return false;
  u8 removed_index = current_count;
  for(u8 index = 0; index < current_count; index++) {
    if(current[index] == extent_id) {
      removed_index = index;
      break;
    }
  }
  if(removed_index == current_count) return false;

  u16 remaining[MAX_FAT_EXTENTS_PER_FILE] = {};
  u8 remaining_count = 0;
  for(u8 index = 0; index < current_count; index++) {
    if(index != removed_index) remaining[remaining_count++] = current[index];
  }

  Transaction transaction;
  txn_begin(transaction);
  file.first_child = remaining_count == 0 ? NONE : remaining[0];
  if(!txn_set(transaction, file_id, file)) return false;
  for(u8 index = 0; index < remaining_count; index++) {
    const u16 previous = index == 0 ? NONE : remaining[index - 1];
    const u16 next = index + 1U < remaining_count
        ? remaining[index + 1] : NONE;
    if(!txn_set(transaction, remaining[index],
                file_extent_inode(file_id, index, previous, next,
                                  inode_type(file)))) return false;
  }
  if(!txn_set(transaction, extent_id, empty_inode()) ||
     !append_transaction(transaction)) return false;
  if(g_free_hint >= g_geometry.max_nodes || extent_id < g_free_hint) {
    g_free_hint = extent_id;
  }
  return true;
}

bool first_file_extent(u16 file_id, u16& out_id) {
  Inode file;
  if(!g_ready || !get_inode(file_id, file) ||
     inode_kind(file) != NodeKind::FILE ||
     file.first_child == NONE) return false;
  out_id = file.first_child;
  return true;
}

bool next_file_extent(u16 id, u16& out_id) {
  Inode inode;
  if(!g_ready || !get_inode(id, inode)) return false;
  if(inode_kind(inode) == NodeKind::FILE) {
    if(inode.first_child == NONE) return false;
    out_id = inode.first_child;
    return true;
  }
  if(inode_kind(inode) != NodeKind::FILE_EXTENT ||
     inode.next_sibling == NONE) return false;
  out_id = inode.next_sibling;
  return true;
}

bool file_extent_info(u16 extent_id, u16& file_id, u8& cluster_index,
                      u16& next_id) {
  Inode inode;
  if(!g_ready || !get_inode(extent_id, inode) ||
     inode_kind(inode) != NodeKind::FILE_EXTENT ||
     inode.data_len == 0 ||
     inode.data_len > MAX_FAT_EXTENTS_PER_FILE) return false;
  file_id = inode.parent_id;
  cluster_index = (u8) inode.data_len;
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

// Ниже реализован постоянный журнал staging для USB.

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

static void forget_stage_index_binding(void) {
  g_stage_index = nullptr;
  g_stage_index_capacity = 0;
  g_stage_ref_count = 0;
  g_stage_external = false;
}

static shared_memory::EvictionDecision prepare_stage_index_eviction(void) {
  if(g_stage_locked) return shared_memory::EvictionDecision::KEEP;
  forget_stage_index_binding();
  return shared_memory::EvictionDecision::RELEASE;
}

static bool bind_full_stage_index(void) {
  if(g_stage_overlay_lease.ok()) {
    return !g_stage_external && g_stage_index != nullptr &&
           g_stage_index_capacity == STAGE_REF_CAPACITY;
  }
  if(g_stage_external ||
     !g_stage_overlay_lease.acquire_cache(
         shared_memory::Arena::OVERLAY,
         shared_memory::Owner::VFAT_STAGE,
         (usize) STAGE_REF_CAPACITY * sizeof(u32))) return false;
  if(!g_stage_overlay_lease.set_evictable(prepare_stage_index_eviction)) {
    g_stage_overlay_lease.reset();
    return false;
  }
  g_stage_index = reinterpret_cast<u32*>(g_stage_overlay_lease.data());
  g_stage_index_capacity = STAGE_REF_CAPACITY;
  g_stage_ref_count = 0;
  return true;
}

static bool ensure_stage_index(void) {
  if(g_stage_index != nullptr) return true;
  vfat_stage_clear();
  return g_stage_index != nullptr;
}

static u32 stage_index_key(u16 index) {
  return g_stage_index[index] >> STAGE_REF_BITS;
}

static u16 stage_index_ref(u16 index) {
  return (u16) (g_stage_index[index] & STAGE_REF_MASK);
}

static int stage_ref_index(u32 key) {
  if(g_stage_index == nullptr) return -1;
  for(u16 i = 0; i < g_stage_ref_count; i++) {
    if(stage_index_key(i) == key) return i;
  }
  return -1;
}

static bool stage_sector_header_valid(u16 sector) {
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  if(!read_bytes(stage_sector_address(sector), header, sizeof(header))) return false;
  return memcmp(header, "C5S0", 4) == 0 &&
         header[4] == PHYSICAL_FORMAT_VERSION &&
         header[5] == STATE_ACTIVE && get_le32(header, 8) == g_format_epoch;
}

static bool initialize_stage_sector(u16 sector) {
  if(!erase_sector(g_geometry.stage_first_sector + sector)) return false;
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C5S0", 4);
  header[4] = PHYSICAL_FORMAT_VERSION;
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
  u32 state = crc32_bytes(prefix, sizeof(prefix));
  state = crc32_bytes(data, STAGE_DATA_SIZE, state);
  return mk61_crc32::finish(state);
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
  // Полная запись программируется одним проверяемым потоком. Восстановление
  // принимает только записи ACTIVE с совпадающей CRC данных, поэтому отключение
  // питания во время программирования любой страницы NOR не заменит старую версию.
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
    if(g_stage_ref_count >= g_stage_index_capacity) return false;
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

// Завершает любое прерванное уплотнение. До стирания старого сектора копии всегда
// получают более новое поколение, поэтому при любом сбое питания остаётся хотя
// бы одна действительная версия каждого промежуточного блока.
static bool recover_stage_reserve(void) {
  const u16 normal_count = normal_stage_sector_count();
  if(normal_count == 0) return false;
  const u16 reserve = normal_count;
  u8 reserve_live = stage_sector_live_count(reserve);
  if(reserve_live == 0) return true;

  // Обычный приёмник уже может содержать первые записи, скопированные обратно
  // до сброса. Завершаем это направление, если свободного хвоста достаточно.
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

  // Иначе сброс произошёл при копировании разреженного сектора в резерв.
  // Завершаем копирование, стираем исходный сектор и копируем данные обратно.
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

} // пространство имён

void vfat_stage_clear(void) {
  if(g_stage_external || !bind_full_stage_index()) {
    g_stage_ref_count = 0;
    return;
  }
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
        // Никогда не дописываем после оборванной записи: сохранение предыдущего
        // действительного поколения важнее неиспользованного хвоста сектора.
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
                g_stage_ref_count < g_stage_index_capacity) {
        g_stage_index[g_stage_ref_count] = pack_stage_index(key, ref);
        g_stage_ref_count++;
      }
    }
  }
}

#if defined(PROGRAM_STORE_HOST_TEST)
bool test_rewrite_catalog_as_v5(void) {
  if(!g_ready) return false;
  g_catalog_write_version = LEGACY_CATALOG_VERSION;
  bool ok = checkpoint() && checkpoint();
  if(ok) {
    // Оставляем активную 256-байтовую WAL-запись v5, чтобы тест миграции
    // проверял не только checkpoint, но и старый журнал.
    Transaction transaction;
    txn_begin(transaction);
    transaction.meta.data_sequence++;
    ok = append_transaction(transaction);
  }
  if(ok) ok = write_locators_version(LEGACY_CATALOG_VERSION);
  g_catalog_write_version = CATALOG_VERSION;
  return ok;
}

bool test_file_storage_info(u16 id, u16& stored_len,
                            bool& large, bool& zx0) {
  Inode inode;
  u8 header[RECORD_HEADER_SIZE];
  if(!g_ready || !get_inode(id, inode) ||
     inode_kind(inode) != NodeKind::FILE ||
     !read_record_header(inode, id, header)) return false;
  large = large_file_inode(inode);
  zx0 = zx0_file_inode(inode);
  if(large) {
    LargeDescriptor descriptor = {};
    if(!read_large_descriptor(id, inode, descriptor)) return false;
    stored_len = descriptor.stored_len;
  } else {
    stored_len = get_le16(header, 8);
  }
  return true;
}

bool test_file_record_location(u16 id, u32& sector, u16& record_len) {
  Inode inode;
  if(!g_ready || !get_inode(id, inode) ||
     inode_kind(inode) != NodeKind::FILE ||
     inode.address >= EXTENT_ADDRESS) return false;
  sector = inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE;
  record_len = inode.record_len;
  return true;
}
#endif

bool vfat_stage_write(u32 block, const u8* data) {
  DiskActivity activity;
  if(!g_ready || data == NULL || block > STAGE_KEY_MAX ||
     !ensure_stage_index()) return false;
  if(stage_ref_index(block) < 0 &&
     g_stage_ref_count >= g_stage_index_capacity) return false;
  u16 sector = 0;
  u8 slot = 0;
  if(!find_stage_slot(sector, slot)) return false;
  (void) slot;
  return append_stage_value(sector, block, data);
}

bool vfat_stage_read(u32 block, u8* data) {
  if(!g_ready || data == NULL || !ensure_stage_index()) return false;
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
  return g_ready && g_stage_index != nullptr && stage_ref_index(block) >= 0;
}

u16 vfat_stage_count(void) {
  return g_ready && g_stage_index != nullptr ? g_stage_ref_count : 0;
}

void vfat_stage_forget(u32 start_block, u16 blocks) {
  if(!g_ready || !ensure_stage_index()) return;
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
  if(!g_ready || !ensure_stage_index()) return false;
  while(g_stage_ref_count != 0) {
    const u16 index = (u16) (g_stage_ref_count - 1);
    if(!write_byte(stage_record_address(stage_index_ref(index)) + 2,
                   STATE_DELETED)) return false;
    g_stage_ref_count--;
  }
  return true;
}

bool vfat_stage_lock(void) {
  if(g_stage_locked) return g_stage_index != nullptr;
  if(g_stage_external || !ensure_stage_index()) return false;
  g_stage_locked = true;
  return true;
}

bool vfat_stage_narrow(u32 start_block, u16 blocks,
                       u32* index_storage, u16 index_capacity) {
  if(!g_stage_locked || g_stage_external || !g_stage_overlay_lease.ok() ||
     g_stage_index == nullptr || index_storage == nullptr || blocks == 0 ||
     index_capacity < blocks ||
     ((uintptr_t) index_storage & (alignof(u32) - 1U)) != 0) return false;

  u16 count = 0;
  const u32 end_block = start_block + blocks;
  if(end_block < start_block) return false;
  for(u16 index = 0; index < g_stage_ref_count; index++) {
    const u32 key = stage_index_key(index);
    if(key < start_block || key >= end_block) continue;
    if(count >= index_capacity) return false;
    index_storage[count++] = g_stage_index[index];
  }

  g_stage_index = index_storage;
  g_stage_index_capacity = index_capacity;
  g_stage_ref_count = count;
  g_stage_external = true;
  g_stage_overlay_lease.reset();
  return true;
}

bool vfat_stage_narrow_matching(VfatStageKeyFilter include,
                                void* context,
                                u32* index_storage, u16 index_capacity) {
  if(!g_stage_locked || g_stage_external || !g_stage_overlay_lease.ok() ||
     g_stage_index == nullptr || include == nullptr ||
     index_storage == nullptr || index_capacity == 0 ||
     ((uintptr_t) index_storage & (alignof(u32) - 1U)) != 0) return false;

  u16 count = 0;
  for(u16 index = 0; index < g_stage_ref_count; index++) {
    const u32 key = stage_index_key(index);
    if(!include(context, key)) continue;
    if(count >= index_capacity) return false;
    index_storage[count++] = g_stage_index[index];
  }

  g_stage_index = index_storage;
  g_stage_index_capacity = index_capacity;
  g_stage_ref_count = count;
  g_stage_external = true;
  g_stage_overlay_lease.reset();
  return true;
}

bool vfat_stage_restore_full(void) {
  if(!g_stage_locked || !g_stage_external) return false;
  forget_stage_index_binding();
  vfat_stage_clear();
  return g_stage_overlay_lease.ok() && g_stage_index != nullptr &&
         g_stage_index_capacity == STAGE_REF_CAPACITY;
}

void vfat_stage_unlock(void) {
  g_stage_locked = false;
  if(g_stage_external) forget_stage_index_binding();
}

} // пространство имён program_store
