#include "program_store.hpp"
#include "fat_cluster_chain.hpp"

#include "bounded_string.hpp"
#include "crc32.hpp"
#include "fat_name.hpp"
#include "Arduino.h"
#include "config.h"
#include "debug.h"
#include "disk_activity.hpp"
#include "exclusive_buffer.hpp"
#include "flash_capacity_probe.hpp"
#include "ledcontrol.h"
#include "mk8_codec.hpp"
#include "shared_memory.hpp"
#include "shared_scratch.hpp"
#include "spi_nor_flash.hpp"
#include "storage_name.hpp"
#include "tools.hpp"
#include "workspace_swap.hpp"
#include "zx0.hpp"

#if !defined(PROGRAM_STORE_HOST_TEST)
  #include "independent_watchdog.hpp"
  #include "power_monitor.hpp"
#endif

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

// C9 is the only supported filesystem. Older layouts are formatted afresh.
static constexpr u8 PHYSICAL_FORMAT_VERSION = 9;
static constexpr u8 CATALOG_VERSION = 9;
static constexpr u8 LOCATOR_VERSION = 9;
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
static constexpr u16 CATALOG_HEADER_SIZE = 512;
static constexpr u16 CATALOG_HEADER_CRC_OFFSET = 508;
static constexpr u8 MAX_CATALOG_PAGES =
    (storage_geometry::MAX_NODES * storage_geometry::INODE_BYTES +
     storage_geometry::PHYSICAL_SECTOR_SIZE - 1) / storage_geometry::PHYSICAL_SECTOR_SIZE;
static constexpr u8 CATALOG_WAL_RECORDS = 15;
static constexpr u16 CATALOG_MAP_OFFSET = 80;
static constexpr u16 CATALOG_WAL_OFFSET = CATALOG_MAP_OFFSET + MAX_CATALOG_PAGES * 8;
static constexpr u16 CATALOG_CURSOR_OFFSET = CATALOG_WAL_OFFSET + 4;
static_assert(CATALOG_CURSOR_OFFSET + 4 <= CATALOG_HEADER_CRC_OFFSET, "catalog map exceeds root");
static constexpr u8 INLINE_TYPE_COUNT = 6;
static constexpr u8 TYPE_COUNT = 7;
static constexpr u16 IMAGE1_HEADER_COUNT_OFFSET = 64;
// Каталог публикует за одну WAL-транзакцию основной inode, служебные
// FAT-extents максимального APP и изменения двух родительских списков.
static constexpr u16 WAL_RECORD_SIZE = 512;
static constexpr u8 WAL_MAX_UPDATES = 16;
static constexpr u16 IMAGE1_WAL_COUNT_OFFSET = 506;
static constexpr u16 WAL_CRC_OFFSET = 508;
static constexpr u8 OVERLAY_CAPACITY = 32;
static constexpr u16 STAGE_DATA_SIZE = VFAT_STAGE_BLOCK_SIZE;
static constexpr u16 STAGE_SECTOR_HEADER_SIZE = 16;
static constexpr u16 STAGE_RECORD_HEADER_SIZE = 16;
static constexpr u16 STAGE_RECORD_SIZE = STAGE_RECORD_HEADER_SIZE + STAGE_DATA_SIZE;
static constexpr u8 STAGE_RECORDS_PER_SECTOR =
    (storage_geometry::PHYSICAL_SECTOR_SIZE - STAGE_SECTOR_HEADER_SIZE) /
    STAGE_RECORD_SIZE;
static constexpr u16 STAGE_REF_CAPACITY = 640;
static constexpr u8 STAGE_REF_BITS = 10;
static constexpr u16 STAGE_REF_MASK = (1U << STAGE_REF_BITS) - 1U;
static constexpr u32 STAGE_KEY_MAX = VFAT_STAGE_KEY_MAX;
// A 512-KiB C9 volume can lend unused data erase sectors to USB staging.
// The fixed stage remains the fallback and its last sector remains the COW
// compaction reserve. All borrowed sectors are identified by their C9S0
// headers after a reset, so the catalog allocator must never erase them.
static constexpr u8 STAGE_MAX_SLOTS = 128;
static constexpr u8 STAGE_MIN_FREE_DATA_SECTORS =
    storage_geometry::STAGE_MIN_FREE_DATA_SECTORS;
static constexpr u8 GC_SCAN_WINDOW = 32;
static constexpr u32 ERASE_TIMEOUT_MS = 5000;
static constexpr t_time_ms DISK_LED_ON_MS = 35;
static constexpr t_time_ms DISK_LED_OFF_MS = 35;
static constexpr u8 INODE_FLAG_LARGE_FILE = 0x01;
static constexpr u8 INODE_FLAG_ZX0 = 0x02;
static constexpr u8 INODE_FILE_FLAGS =
    INODE_FLAG_LARGE_FILE | INODE_FLAG_ZX0 | 0x04U;
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
static constexpr u8 LARGE_DESCRIPTOR_VERSION = 2;

static_assert(STAGE_RECORDS_PER_SECTOR == 7, "C9 stage must pack seven sectors");
static_assert(STAGE_KEY_MAX == 0x007FFFFFUL,
              "C9 stage keys must remain readable across firmware updates");
static_assert(44 + WAL_MAX_UPDATES *
                  (2 + storage_geometry::INODE_BYTES) <=
                  IMAGE1_WAL_COUNT_OFFSET,
              "inode updates overlap the v6 WAL tail");
static_assert(WAL_MAX_UPDATES >= 4, "file and parent links fit one WAL record");
static_assert(IMAGE1_WAL_COUNT_OFFSET + sizeof(u16) <= WAL_CRC_OFFSET,
              "image counter overlaps the WAL CRC");
static_assert(IMAGE1_HEADER_COUNT_OFFSET + sizeof(u16) <=
                  CATALOG_HEADER_CRC_OFFSET,
              "image counter overlaps the catalog-header CRC");
static_assert(LARGE_BLOCK_COUNT == 6,
              "maximum APP should occupy exactly six C9 large blocks");
static_assert(LARGE_DESCRIPTOR_SIZE < 128,
              "large-file descriptor must remain a small C9 record");
static_assert((usize) MAX_MK61_TEXT_SIZE + NAME_SIZE + RECORD_HEADER_SIZE <=
                  storage_geometry::PHYSICAL_SECTOR_SIZE / 2,
              "two maximum C9 records must fit one erase sector");
static_assert((usize) MAX_TINYBASIC_TEXT_SIZE + NAME_SIZE +
                  RECORD_HEADER_SIZE <=
                  storage_geometry::PHYSICAL_SECTOR_SIZE -
                      DATA_SECTOR_HEADER_SIZE,
              "maximum TinyBASIC source must fit one C9 data sector");
static_assert((usize) MAX_IMAGE1_SIZE + NAME_SIZE + RECORD_HEADER_SIZE <=
                  storage_geometry::PHYSICAL_SECTOR_SIZE / 2,
              "two maximum C9 image records must fit one erase sector");

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
  u16 exported_size;
  u32 fat_address;
};

static_assert(sizeof(Inode) == 28 && storage_geometry::INODE_BYTES == 26,
              "C9 inode has two RAM alignment bytes, not stored on disk");

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

union WriteWorkspace {
  alignas(4) u8 compression[ZX0_FALLBACK_WORKSPACE_SIZE];
  Transaction transaction;
};

#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
// C9 writes are serialized by the store and already use process-wide
// transaction state. F411 can therefore keep this temporary workspace in BSS
// and preserve the production stack-headroom gate; the compact F401 APP keeps
// the same workspace on the stack instead of permanently enlarging its arena.
static WriteWorkspace g_write_workspace;
// Catalog verification runs during every boot and may sit below several SPI
// and CRC frames.  The store is single-owner, so its synchronous read helpers
// can share one resident chunk instead of spending another 512 bytes of the
// protected stack.  F401 keeps the buffer local to avoid growing the APP
// arena, where RAM is much tighter than on F411.
static u8 g_crc_read_chunk[MK61_PROGRAM_STORE_READ_CHUNK];
// WAL replay and append never overlap: a failed append may reload the
// catalog only after the outgoing record is no longer needed.  Sharing this
// sector removes the other 512-byte boot-time frame without making the F401
// loadable implementation permanently larger.
static u8 g_wal_record[WAL_RECORD_SIZE];
#endif

static storage_geometry::Geometry g_geometry;
static bool g_ready;
static MountStatus g_mount_status;
static u32 g_format_epoch;
static u8 g_locator_valid_mask;
static constexpr u8 ALL_LOCATORS = (1U << storage_geometry::LOCATOR_SECTORS) - 1U;
struct CatalogPage { u32 sector; u32 crc; };
static CatalogPage g_catalog_pages[MAX_CATALOG_PAGES];
static CatalogPage g_catalog_pending[MAX_CATALOG_PAGES];
static u32 g_catalog_root = EMPTY_ADDRESS;
static u32 g_catalog_wal = EMPTY_ADDRESS;
static u32 g_catalog_pending_root = EMPTY_ADDRESS;
static u32 g_catalog_pending_wal = EMPTY_ADDRESS;
static u32 g_catalog_cursor;
static u32 g_gc_victim = EMPTY_ADDRESS;
static constexpr u8 C9_PIN_CAPACITY = 8;
struct C9PendingRecord { u32 address; u16 owner; bool mapping; };
static C9PendingRecord g_c9_pins[C9_PIN_CAPACITY];
static u8 g_c9_pin_count;
static u32 g_chain_verified_address = EMPTY_ADDRESS;
static u16 g_chain_verified_id = NONE;
static fat_cluster_chain::Plan g_chain_verified_plan;
static bool g_reverse_ready;
static bool g_import_applying;
static bool g_import_plan_ready;
#if !defined(ARDUINO_BLACKPILL_F401CC)
static u32 g_import_plan_erased;
#endif
static u16 g_reverse_window = NONE;
static u16 g_reverse_entries[32][3];
static bool c9_map_size(u16 id, const Inode& inode, u16& size);
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
#if !defined(ARDUINO_BLACKPILL_F401CC)
// Keep the parent inode block alongside the sequential child block on F411.
// A single line otherwise rereads 512 NOR bytes for almost every lookup.
static u8 g_table_other_cache[512];
static u32 g_table_other_address = EMPTY_ADDRESS;
#endif
static void invalidate_table_cache(void) {
  g_table_cache_address = EMPTY_ADDRESS;
#if !defined(ARDUINO_BLACKPILL_F401CC)
  g_table_other_address = EMPTY_ADDRESS;
#endif
}
static u8 g_disk_activity_depth;
static u8 g_disk_led_poll_divider;

// Упаковываем 18-битный виртуальный LBA и 9-битную ссылку на физическую запись
// в одно слово. Сам индекс арендует нижнюю часть общей динамической APP/USB
// SRAM и потому не
// увеличивает постоянный расход SRAM. На короткой финальной фазе terminal
// fsput он может быть сужен до диапазона одного файла в language workspace.
static u32* g_stage_index;
static u16 g_stage_index_capacity;
static u16 g_stage_ref_count;
#if defined(PROGRAM_STORE_HOST_TEST)
static StageIndexStats g_stage_index_stats;
#endif
static shared_memory::Lease g_stage_overlay_lease;
static bool g_stage_locked;
static bool g_stage_external;
#if !defined(PROGRAM_STORE_HOST_TEST)
static bool g_usb_file_import_progress;
#endif
static WriteFailure g_last_write_failure = WriteFailure::NONE;
static WriteFailureDetail g_last_write_failure_detail =
    WriteFailureDetail::NONE;
static u8 g_stage_used[STAGE_MAX_SLOTS];
static u8 g_stage_sealed[STAGE_MAX_SLOTS];
static u32 g_stage_physical[STAGE_MAX_SLOTS];
static u8 g_stage_slot_count;
static bool g_stage_recovery_ok;
static bool g_stage_known_empty;
// Preserve the original 23-bit key range despite the ten-bit record reference.
// A side bitmap is indexed by physical record reference, not by index position,
// so it also survives narrowing the index for APP validation.
static u8 g_stage_key_high[(STAGE_REF_MASK + 8U) / 8U];
static u16 g_stage_generation;
static u16 g_free_hint;
// Сектора незавершённой COW-записи ещё не достижимы из каталога, но сборщик
// мусора не должен успеть занять их при добавлении дескриптора.
static u32 g_large_write_sectors[LARGE_BLOCK_COUNT];
static u8 g_large_write_sector_count;
static u16 g_verified_large_id = NONE;
static u32 g_verified_large_generation;
static u8 g_verified_large_block = 0xFF;

static_assert((u16) STAGE_MAX_SLOTS *
                  STAGE_RECORDS_PER_SECTOR <= STAGE_REF_MASK,
              "C9 stage references must fit in the packed index");
static_assert((usize) STAGE_REF_CAPACITY * sizeof(u32) <=
                  shared_memory::STAGE_INDEX_SIZE,
              "full C9 staging index does not fit the shared overlay");

static int g_flat_cache_index = -1;
static u16 g_flat_cache_id;
static u16 g_child_cache_parent = NONE;
static int g_child_cache_index = -1;
static u16 g_child_cache_id = NONE;

#ifdef DEBUG_SPIFLASH
static void capacity_probe_debug(u32 candidate, bool complete,
                                 bool distinct) {
  Serial.print("C9 probe candidate: ");
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
        disk_activity::setFileOperation(true);
        g_disk_led_poll_divider = 0;
        led::blink_continuous(DISK_LED_ON_MS, DISK_LED_OFF_MS);
      }
    }

    ~DiskActivity(void) {
      if(g_disk_activity_depth == 0) return;
      g_disk_activity_depth--;
      if(g_disk_activity_depth == 0) {
        disk_activity::setFileOperation(false);
        led::blink_stop();
      }
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
#if !defined(PROGRAM_STORE_HOST_TEST)
    if(ok && g_usb_file_import_progress) {
      independent_watchdog::completed_storage_unit();
    }
#endif
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
#if !defined(PROGRAM_STORE_HOST_TEST)
    if(ok && g_usb_file_import_progress) {
      independent_watchdog::completed_storage_unit();
    }
#endif
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
#if !defined(PROGRAM_STORE_HOST_TEST)
    // A PVD rejection is not a transient NOR busy/error. Avoid spinning for
    // the normal five-second erase retry window while the rail is unsafe.
    if(!power_monitor::writes_allowed()) return false;
#endif
    led::control();
    if((i32) (millis() - stop_at) >= 0) return false;
  }
  led::control();
  invalidate_table_cache();
#if !defined(PROGRAM_STORE_HOST_TEST)
  if(g_usb_file_import_progress) {
    independent_watchdog::completed_storage_unit();
  }
#endif
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
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
  u8 (&buffer)[MK61_PROGRAM_STORE_READ_CHUNK] = g_crc_read_chunk;
#else
  u8 buffer[MK61_PROGRAM_STORE_READ_CHUNK];
#endif
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
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
  u8 (&buffer)[MK61_PROGRAM_STORE_READ_CHUNK] = g_crc_read_chunk;
#else
  u8 buffer[MK61_PROGRAM_STORE_READ_CHUNK];
#endif
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
  memcpy(guard, "C9SG", 4);
  guard[4] = PHYSICAL_FORMAT_VERSION;
  put_le32(guard, 8, capacity);
  put_le32(guard, 12, mk61_crc32::calculate(guard, 12));
}

static bool settings_guard_valid_for(const storage_geometry::Geometry& geometry,
                                     const char* magic, u8 version) {
  u8 guard[SETTINGS_GUARD_SIZE];
#ifdef SPI_FLASH
  const u32 address = sector_address(geometry.settings_sector) +
                      SETTINGS_JOURNAL_SIZE;
  if(!flash_device().rawPrepare(geometry.capacity_bytes) ||
     !flash_device().rawRead(address, guard, sizeof(guard))) return false;
#else
  (void) geometry;
  (void) magic;
  (void) version;
  return false;
#endif
  return memcmp(guard, magic, 4) == 0 &&
         guard[4] == version &&
         get_le32(guard, 8) == geometry.capacity_bytes &&
         get_le32(guard, 12) == mk61_crc32::calculate(guard, 12);
}

static bool settings_guard_valid(const storage_geometry::Geometry& geometry) {
  return settings_guard_valid_for(
      geometry, "C9SG", PHYSICAL_FORMAT_VERSION);
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
    hash ^= mk8::fold_case((u8) *name++);
    hash = (u16) (hash * 257U + 17U);
  }
  return hash;
}

static bool valid_name(const char* name) {
  return storage_name::valid_basename(name, NAME_SIZE);
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
    case ProgramType::MK61_BINARY: return -1;
    case ProgramType::SHEET: return -1;
  }
  return -1;
}

static bool supported_type(ProgramType type) {
  return type == ProgramType::APP || type == ProgramType::CHIP8 ||
         type == ProgramType::MARKDOWN || type == ProgramType::MK61_BINARY ||
         type == ProgramType::SHEET ||
         type_index(type) >= 0;
}

static u16 maximum_data_len(ProgramType type) {
  if(type == ProgramType::TINYBASIC) return MAX_TINYBASIC_TEXT_SIZE;
  if(type == ProgramType::FONT) return MAX_FONT_SIZE;
  if(type == ProgramType::IMAGE1) return MAX_IMAGE1_SIZE;
  if(type == ProgramType::CHIP8) return MAX_CHIP8_SIZE;
  if(type == ProgramType::MK61_BINARY) return MAX_MK61_BINARY_SIZE;
  if(type == ProgramType::SHEET) return MAX_SHEET_SIZE;
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
    case ProgramType::MK61_BINARY: return "bin";
    case ProgramType::SHEET: return "mks";
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
    case ProgramType::FONT: return "f2";
    case ProgramType::IMAGE1: return "I1";
    case ProgramType::APP: return "A1";
    case ProgramType::CHIP8: return "C1";
    case ProgramType::MARKDOWN: return "T2";
    case ProgramType::MK61_BINARY: return "M3";
    case ProgramType::SHEET: return "S1";
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
  if(kind != NodeKind::FILE) return inode.flags == 0 ||
      (kind == NodeKind::DIRECTORY && inode.flags == 0x04U);
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
  put_le16(out, 20, inode.exported_size);
  put_le32(out, 22, inode.fat_address);
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
  inode.exported_size = get_le16(data, 20);
  inode.fat_address = get_le32(data, 22);
  return inode;
}

static bool catalog_sector_in_range(u32 sector) {
  const u32 scratch = storage_geometry::import_scratch_first_sector(g_geometry);
  return sector >= storage_geometry::LOCATOR_SECTORS &&
         sector < g_geometry.stage_first_sector &&
         !(sector >= scratch &&
           sector - scratch < storage_geometry::import_scratch_sector_count(g_geometry));
}

__attribute__((noinline))
static bool catalog_sector_busy(u32 sector) {
  for(u8 index = 0; index < g_c9_pin_count; ++index) {
    if(g_c9_pins[index].address / 4096U == sector) return true;
  }
  if(sector == g_catalog_root || sector == g_catalog_wal ||
     sector == g_catalog_pending_root || sector == g_catalog_pending_wal ||
     sector == g_gc_victim) return true;
  for(u8 page = 0; page < g_geometry.catalog_table_sectors; ++page) {
    if(sector == g_catalog_pages[page].sector ||
       sector == g_catalog_pending[page].sector) return true;
  }
  return false;
}

static void clear_pending_catalog(void) {
  memset(g_catalog_pending, 0xFF, sizeof(g_catalog_pending));
  g_catalog_pending_root = g_catalog_pending_wal = EMPTY_ADDRESS;
}

static u32 wal_record_address(u8 index) {
  return index < 7
      ? sector_address(g_catalog_root) + CATALOG_HEADER_SIZE + (u32) index * WAL_RECORD_SIZE
      : sector_address(g_catalog_wal) + (u32) (index - 7) * WAL_RECORD_SIZE;
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

__attribute__((noinline))
static bool read_table_bytes(u32 offset, u8* out, u16 len) {
  while(len != 0) {
    const u32 page = offset / storage_geometry::PHYSICAL_SECTOR_SIZE;
    if(page >= g_geometry.catalog_table_sectors) return false;
    const u16 in_page = (u16) (offset % storage_geometry::PHYSICAL_SECTOR_SIZE);
    const u16 room = (u16) (storage_geometry::PHYSICAL_SECTOR_SIZE - in_page);
    if(g_catalog_pages[page].sector == EMPTY_ADDRESS) {
      const u16 count = len < room ? len : room;
      memset(out, 0xFF, count);
      out += count;
      offset += count;
      len = (u16) (len - count);
      continue;
    }
    const u32 address = sector_address(g_catalog_pages[page].sector) + in_page;
    const u32 cache_address = address & ~511UL;
#if !defined(ARDUINO_BLACKPILL_F401CC)
    const u8* cached = g_table_cache;
    if(g_table_cache_address != cache_address) {
      if(g_table_other_address == cache_address) {
        cached = g_table_other_cache;
      } else {
        memcpy(g_table_other_cache, g_table_cache, sizeof(g_table_cache));
        g_table_other_address = g_table_cache_address;
        g_table_cache_address = EMPTY_ADDRESS;
        if(!read_bytes(cache_address, g_table_cache, sizeof(g_table_cache))) return false;
        g_table_cache_address = cache_address;
      }
    }
#else
    if(g_table_cache_address != cache_address) {
      if(!read_bytes(cache_address, g_table_cache, sizeof(g_table_cache))) return false;
      g_table_cache_address = cache_address;
    }
    const u8* cached = g_table_cache;
#endif
    const u16 in_cache = (u16) (address - cache_address);
    const u16 count = len < sizeof(g_table_cache) - in_cache
        ? len : (u16) (sizeof(g_table_cache) - in_cache);
    memcpy(out, cached + in_cache, count);
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
  g_chain_verified_address = EMPTY_ADDRESS;
  g_reverse_window = NONE;
  if(!g_import_applying) g_reverse_ready = false;
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

static void encode_meta(u8* record, const CatalogMeta& meta,
                        u16 image_count_offset) {
  put_le16(record, 10, meta.root_head);
  put_le16(record, 12, meta.total_count);
  put_le16(record, 14, meta.current_offset);
  put_le32(record, 16, meta.current_sector);
  put_le32(record, 20, meta.reserve_sector);
  put_le32(record, 24, meta.gc_cursor);
  put_le32(record, 28, meta.data_sequence);
  for(u8 i = 0; i < INLINE_TYPE_COUNT; i++) {
    put_le16(record, (u16) (32 + i * 2), meta.type_count[i]);
  }
  put_le16(record, image_count_offset, meta.type_count[6]);
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
  for(u8 i = 0; i < INLINE_TYPE_COUNT; i++) {
    meta.type_count[i] = get_le16(record, (u16) (32 + i * 2));
  }
  meta.type_count[6] = get_le16(record, image_count_offset);
  return meta;
}

static bool checkpoint(bool empty_table = false, bool reserve_only = false);
static bool load_catalog(void);
static bool borrowed_stage_sector(u32 sector);
static bool sector_has_live_inode(u32 sector);
static bool live_sector_window(u32 first, u32 count, u32 start,
                               u32 base, u8 window, u32& mask);

static bool generation_newer(u32 left, u32 right) {
  return (i32) (left - right) > 0;
}

static u8 new_overlay_slots(const Transaction& transaction) {
  u8 added = 0;
  for(u8 i = 0; i < transaction.count; i++) {
    bool found = false;
    (void) overlay_search(transaction.updates[i].id, found);
    if(!found) added++;
  }
  return added;
}

// A separate cursor is committed with each root. GC transactions have their
// own cursor and must not undo catalog allocation when they publish metadata.
static bool allocate_catalog_sector(u32& output, bool reserve_only = false) {
  const u32 first = storage_geometry::LOCATOR_SECTORS;
  const u32 end = reserve_only ? g_geometry.data_first_sector
                              : g_geometry.stage_first_sector;
  const u32 count = end - first;
  const u32 start = g_catalog_cursor >= first && g_catalog_cursor < end
      ? g_catalog_cursor : first;
  for(u32 base = 0; base < count; base += GC_SCAN_WINDOW) {
    const u8 window = (u8) ((count - base < GC_SCAN_WINDOW)
        ? count - base : GC_SCAN_WINDOW);
    u32 live = 0;
    if(!live_sector_window(first, count, start, base, window, live)) return false;
    for(u8 slot = 0; slot < window; ++slot) {
      const u32 sector = first + (start - first + base + slot) % count;
      if(!catalog_sector_in_range(sector) ||
         (live & (1UL << slot)) != 0 || catalog_sector_busy(sector) ||
         sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
         borrowed_stage_sector(sector)) continue;
      if(!erase_sector(sector)) return false;
      output = sector;
      g_catalog_cursor = first + (sector - first + 1) % count;
      while(!catalog_sector_in_range(g_catalog_cursor)) {
        g_catalog_cursor = first + (g_catalog_cursor - first + 1) % count;
      }
      return true;
    }
  }
  return false;
}

static bool catalog_page_dirty(u8 page) {
  const u32 begin = (u32) page * storage_geometry::PHYSICAL_SECTOR_SIZE;
  const u32 end = begin + storage_geometry::PHYSICAL_SECTOR_SIZE;
  for(u8 i = 0; i < g_overlay_count; ++i) {
    const u32 offset = (u32) g_overlay_ids[i] * storage_geometry::INODE_BYTES;
    if(offset < end && offset + storage_geometry::INODE_BYTES > begin) return true;
  }
  return false;
}

// Stream a page through 512 bytes of scratch; never put a 4-KiB erase block
// on F401's stack. Inodes straddling a physical page are patched in both pages.
__attribute__((noinline))
static bool write_catalog_page(u8 page, CatalogPage& target,
                                bool reserve_only) {
  if(!allocate_catalog_sector(target.sector, reserve_only)) return false;
  mk61_crc32::Context crc;
  u8 buffer[512];
  u8 disk_inode[storage_geometry::INODE_BYTES];
  const u32 page_begin = (u32) page * storage_geometry::PHYSICAL_SECTOR_SIZE;
  for(u16 offset = 0; offset < storage_geometry::PHYSICAL_SECTOR_SIZE; offset += sizeof(buffer)) {
    const u32 begin = page_begin + offset;
    const u32 end = begin + sizeof(buffer);
    if(!read_table_bytes(begin, buffer, sizeof(buffer))) return false;
    for(u8 i = 0; i < g_overlay_count; ++i) {
      const u32 inode_begin = (u32) g_overlay_ids[i] * storage_geometry::INODE_BYTES;
      const u32 inode_end = inode_begin + storage_geometry::INODE_BYTES;
      if(inode_begin >= end || inode_end <= begin) continue;
      serialize_inode(g_overlay_inodes[i], disk_inode);
      const u32 low = inode_begin > begin ? inode_begin : begin;
      const u32 high = inode_end < end ? inode_end : end;
      memcpy(buffer + (low - begin), disk_inode + (low - inode_begin), high - low);
    }
    if(!write_bytes(sector_address(target.sector) + offset, buffer, sizeof(buffer)) ||
       !crc.update(buffer, sizeof(buffer))) return false;
  }
  target.crc = crc.finish();
  return true;
}

__attribute__((noinline))
static bool publish_catalog_root(u32 generation) {
  u8 header[CATALOG_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C9CT", 4);
  header[4] = CATALOG_VERSION;
  header[5] = STATE_WRITING;
  put_le16(header, 6, CATALOG_HEADER_SIZE);
  put_le32(header, 8, generation);
  put_le32(header, 12, g_format_epoch);
  put_le16(header, 16, g_geometry.max_nodes);
  put_le16(header, 18, g_geometry.catalog_table_sectors);
  put_le32(header, 24, g_wal_sequence);
  put_le16(header, 28, g_meta.root_head);
  put_le16(header, 30, g_meta.total_count);
  put_le16(header, 32, g_meta.current_offset);
  put_le32(header, 36, g_meta.current_sector);
  put_le32(header, 40, g_meta.reserve_sector);
  put_le32(header, 44, g_meta.gc_cursor);
  put_le32(header, 48, g_meta.data_sequence);
  for(u8 i = 0; i < INLINE_TYPE_COUNT; ++i) put_le16(header, 52 + i * 2, g_meta.type_count[i]);
  put_le16(header, IMAGE1_HEADER_COUNT_OFFSET, g_meta.type_count[6]);
  for(u8 page = 0; page < g_geometry.catalog_table_sectors; ++page) {
    put_le32(header, CATALOG_MAP_OFFSET + page * 8, g_catalog_pending[page].sector);
    put_le32(header, CATALOG_MAP_OFFSET + page * 8 + 4, g_catalog_pending[page].crc);
  }
  put_le32(header, CATALOG_WAL_OFFSET, g_catalog_pending_wal);
  put_le32(header, CATALOG_CURSOR_OFFSET, g_catalog_cursor);
  put_le32(header, CATALOG_HEADER_CRC_OFFSET,
           normalized_record_crc(header, sizeof(header), CATALOG_HEADER_CRC_OFFSET, 5));
  const u32 address = sector_address(g_catalog_pending_root);
  return write_bytes(address, header, sizeof(header)) &&
         write_byte(address + 5, STATE_ACTIVE);
}

static bool checkpoint(bool empty_table, bool reserve_only) {
  clear_pending_catalog();
  memcpy(g_catalog_pending, g_catalog_pages, sizeof(g_catalog_pending));
  if(empty_table) memset(g_catalog_pending, 0xFF, sizeof(g_catalog_pending));
  for(u8 page = 0; !empty_table && page < g_geometry.catalog_table_sectors; ++page) {
    const bool borrowed = reserve_only &&
        g_catalog_pages[page].sector != EMPTY_ADDRESS &&
        g_catalog_pages[page].sector >= g_geometry.data_first_sector;
    if((catalog_page_dirty(page) || borrowed) &&
       !write_catalog_page(page, g_catalog_pending[page], reserve_only)) return false;
  }
  if(!allocate_catalog_sector(g_catalog_pending_root, reserve_only) ||
     !allocate_catalog_sector(g_catalog_pending_wal, reserve_only)) return false;
  u32 generation = g_catalog_generation + 1;
  if(generation == 0) generation = 1;
  if(!publish_catalog_root(generation)) return false;
  memcpy(g_catalog_pages, g_catalog_pending, sizeof(g_catalog_pages));
  g_catalog_root = g_catalog_pending_root;
  g_catalog_wal = g_catalog_pending_wal;
  g_catalog_generation = generation;
  clear_pending_catalog();
  g_overlay_count = 0;
  g_wal_records = 0;
  g_wal_sealed = false;
  invalidate_table_cache();
  invalidate_iteration_caches();
  return true;
}

// No full-catalog checkpoint for every mutation. The bounded journal still
// commits up to 16 changed inodes atomically, including an entire APP's extents.
__attribute__((noinline))
static bool append_transaction_record(const Transaction& transaction) {
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
  u8 (&record)[WAL_RECORD_SIZE] = g_wal_record;
#else
  u8 record[WAL_RECORD_SIZE];
#endif
  memset(record, 0xFF, sizeof(record));
  record[0] = 'W';
  record[1] = '9';
  record[2] = CATALOG_VERSION;
  record[3] = STATE_WRITING;
  const u32 next_sequence = g_wal_sequence + 1;
  put_le32(record, 4, next_sequence);
  record[8] = transaction.count;
  encode_meta(record, transaction.meta, IMAGE1_WAL_COUNT_OFFSET);
  u16 offset = 44;
  for(u8 i = 0; i < transaction.count; ++i) {
    put_le16(record, offset, transaction.updates[i].id);
    serialize_inode(transaction.updates[i].inode, record + offset + 2);
    offset = (u16) (offset + 2 + storage_geometry::INODE_BYTES);
  }
  put_le32(record, WAL_CRC_OFFSET,
           normalized_record_crc(record, sizeof(record), WAL_CRC_OFFSET, 3));
  const u32 address = wal_record_address(g_wal_records);
  if(!write_bytes(address, record, sizeof(record)) ||
     !write_byte(address + 3, STATE_ACTIVE)) {
    g_wal_sealed = true;
    if(!load_catalog()) g_ready = false;
    return false;
  }
  for(u8 i = 0; i < transaction.count; ++i) {
    if(!overlay_set(transaction.updates[i].id, transaction.updates[i].inode)) return false;
  }
  g_wal_sequence = next_sequence;
  g_meta = transaction.meta;
  ++g_wal_records;
  invalidate_iteration_caches();
  return true;
}

static bool append_transaction(const Transaction& transaction) {
  if(transaction.count > WAL_MAX_UPDATES) return false;
  if(g_wal_sealed || g_wal_records >= CATALOG_WAL_RECORDS ||
     g_overlay_count + new_overlay_slots(transaction) > OVERLAY_CAPACITY) {
    if(!checkpoint()) {
      if(!load_catalog()) g_ready = false;
      return false;
    }
  }
  return append_transaction_record(transaction);
}

static bool replay_wal(void) {
  g_wal_records = 0;
  g_wal_sealed = false;
  for(u8 index = 0; index < CATALOG_WAL_RECORDS; ++index) {
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
    u8 (&record)[WAL_RECORD_SIZE] = g_wal_record;
#else
    u8 record[WAL_RECORD_SIZE];
#endif
    if(!read_bytes(wal_record_address(index), record, sizeof(record))) return false;
    bool erased = true;
    for(u16 i = 0; i < sizeof(record); ++i) if(record[i] != 0xFF) erased = false;
    if(erased) break;
    if(record[0] != 'W' || record[1] != '9' ||
       record[2] != CATALOG_VERSION || record[3] != STATE_ACTIVE ||
       record[8] > WAL_MAX_UPDATES || get_le32(record, 4) != g_wal_sequence + 1 ||
       normalized_record_crc(record, sizeof(record), WAL_CRC_OFFSET, 3) != get_le32(record, WAL_CRC_OFFSET)) {
      g_wal_sealed = true;
      break;
    }
    u16 offset = 44;
    for(u8 i = 0; i < record[8]; ++i) {
      const u16 id = get_le16(record, offset);
      if(id >= g_geometry.max_nodes ||
         !overlay_set(id, deserialize_inode(record + offset + 2))) return false;
      offset = (u16) (offset + 2 + storage_geometry::INODE_BYTES);
    }
    g_meta = decode_meta(record, IMAGE1_WAL_COUNT_OFFSET);
    g_wal_sequence = get_le32(record, 4);
    ++g_wal_records;
  }
  return true;
}

static bool catalog_header_valid(u8* header) {
  return memcmp(header, "C9CT", 4) == 0 &&
      header[4] == CATALOG_VERSION && header[5] == STATE_ACTIVE &&
      get_le16(header, 6) == CATALOG_HEADER_SIZE &&
      get_le32(header, 8) != 0 && get_le32(header, 12) == g_format_epoch &&
      get_le16(header, 16) == g_geometry.max_nodes &&
      get_le16(header, 18) == g_geometry.catalog_table_sectors &&
      normalized_record_crc(header, CATALOG_HEADER_SIZE, CATALOG_HEADER_CRC_OFFSET, 5) ==
          get_le32(header, CATALOG_HEADER_CRC_OFFSET);
}

__attribute__((noinline))
static bool load_catalog(void) {
  clear_pending_catalog();
  memset(g_catalog_pages, 0xFF, sizeof(g_catalog_pages));
  g_catalog_root = g_catalog_wal = EMPTY_ADDRESS;
  g_overlay_count = 0;
  invalidate_table_cache();
  if(g_geometry.catalog_table_sectors > MAX_CATALOG_PAGES) return false;
  u8 header[CATALOG_HEADER_SIZE];
  u32 newest = 0;
  // Only sector headers are scanned. Fixed locators contain format/geometry,
  // not a hot pointer rewritten each time the root moves.
  for(u32 sector = storage_geometry::LOCATOR_SECTORS;
      sector < g_geometry.stage_first_sector; ++sector) {
    if(!read_bytes(sector_address(sector), header, 16)) return false;
    if(memcmp(header, "C9CT", 4) != 0 || header[5] != STATE_ACTIVE ||
       get_le32(header, 12) != g_format_epoch) continue;
    if(!read_bytes(sector_address(sector), header, sizeof(header))) return false;
    if(catalog_header_valid(header) &&
       (g_catalog_root == EMPTY_ADDRESS || generation_newer(get_le32(header, 8), newest))) {
      g_catalog_root = sector;
      newest = get_le32(header, 8);
    }
  }
  if(g_catalog_root == EMPTY_ADDRESS ||
     !read_bytes(sector_address(g_catalog_root), header, sizeof(header))) return false;
  g_catalog_wal = get_le32(header, CATALOG_WAL_OFFSET);
  g_catalog_cursor = get_le32(header, CATALOG_CURSOR_OFFSET);
  if(!catalog_sector_in_range(g_catalog_wal) || g_catalog_wal == g_catalog_root ||
     !catalog_sector_in_range(g_catalog_cursor)) return false;
  for(u8 page = 0; page < g_geometry.catalog_table_sectors; ++page) {
    CatalogPage& entry = g_catalog_pages[page];
    entry.sector = get_le32(header, CATALOG_MAP_OFFSET + page * 8);
    entry.crc = get_le32(header, CATALOG_MAP_OFFSET + page * 8 + 4);
    if(entry.sector == EMPTY_ADDRESS) {
      if(entry.crc != EMPTY_ADDRESS) return false;
      continue;
    }
    if(!catalog_sector_in_range(entry.sector) || entry.sector == g_catalog_root ||
       entry.sector == g_catalog_wal) return false;
    for(u8 previous = 0; previous < page; ++previous) {
      if(g_catalog_pages[previous].sector == entry.sector) return false;
    }
    u32 crc = 0;
    if(!crc32_flash(sector_address(entry.sector), storage_geometry::PHYSICAL_SECTOR_SIZE, crc) ||
       crc != entry.crc) return false;
  }
  g_catalog_generation = newest;
  g_wal_sequence = get_le32(header, 24);
  g_meta.root_head = get_le16(header, 28);
  g_meta.total_count = get_le16(header, 30);
  g_meta.current_offset = get_le16(header, 32);
  g_meta.current_sector = get_le32(header, 36);
  g_meta.reserve_sector = get_le32(header, 40);
  g_meta.gc_cursor = get_le32(header, 44);
  g_meta.data_sequence = get_le32(header, 48);
  for(u8 i = 0; i < INLINE_TYPE_COUNT; ++i) g_meta.type_count[i] = get_le16(header, 52 + i * 2);
  g_meta.type_count[6] = get_le16(header, IMAGE1_HEADER_COUNT_OFFSET);
  return replay_wal();
}

static void encode_locator(u8* locator) {
  memset(locator, 0xFF, LOCATOR_SIZE);
  memcpy(locator, "C9FS", 4);
  locator[4] = LOCATOR_VERSION;
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

static bool locator_matches_format(const u8* locator, const char* magic,
                                   u8 format_version,
                                   storage_geometry::Geometry& geometry,
                                   u32& epoch, u32& probe_upper,
                                   u32& jedec_id) {
  if(memcmp(locator, magic, 4) != 0 ||
     locator[4] != format_version ||
     locator[5] != STATE_ACTIVE || locator[6] != LOCATOR_SIZE ||
     normalized_record_crc((u8*) locator, LOCATOR_SIZE, 68, 5) != get_le32(locator, 68)) return false;
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

// Обновление прошивки может намеренно изменить вычисляемую геометрию C9/FAT,
// хотя физическая микросхема и сектор настроек не меняются. Старый каталог при
// этом смонтировать нельзя, но повторять разрушающую проверку ёмкости и стирать
// настройки было бы излишне и неожиданно. Этот ограниченный декодер доверяет
// только полностью зафиксированному локатору с CRC и независимо защищённой CRC
// метке на неизменившемся физическом конце.
static
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
__attribute__((noinline))
#endif
bool load_capacity_for_reformat(void) {
#ifndef SPI_FLASH
  return false;
#else
  u8 locator[LOCATOR_SIZE];
  const u32 probe_upper = flash_device().capacityProbeUpper();
  const u32 jedec_id = flash_device().getJEDECID();
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!read_bytes(sector_address(copy), locator, sizeof(locator)) ||
       (memcmp(locator, "C9FS", 4) != 0 || locator[4] != LOCATOR_VERSION) ||
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
    g_format_epoch = get_le32(locator, 12);
    g_geometry = geometry;
    return true;
  }
  return false;
#endif
}

static
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
__attribute__((noinline))
#endif
bool load_locator(void) {
  u8 locator[LOCATOR_SIZE];
  storage_geometry::Geometry geometry;
  u32 epoch = 0;
  u32 stored_probe_upper = 0;
  u32 stored_jedec_id = 0;
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
  u8 selected_mask = 0;
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    if(!read_bytes(sector_address(copy), locator, sizeof(locator))) continue;
    if(!locator_matches_format(locator, "C9FS", LOCATOR_VERSION,
                               geometry, epoch, stored_probe_upper,
                               stored_jedec_id)) continue;
    if(stored_jedec_id != jedec_id || stored_probe_upper != probe_upper ||
       !flash_device().setCapacity(geometry.capacity_bytes) ||
       !settings_guard_valid(geometry)) continue;
    if(!found) {
      selected_geometry = geometry;
      selected_epoch = epoch;
      selected_mask = (u8) (1U << copy);
      found = true;
    } else if(epoch == selected_epoch &&
              geometry.capacity_bytes == selected_geometry.capacity_bytes) {
      selected_mask |= (u8) (1U << copy);
    }
  }
  if(!found) return false;
  g_geometry = selected_geometry;
  g_format_epoch = selected_epoch;
  g_locator_valid_mask = selected_mask;
  return true;
}

static bool write_locators(bool repair_only = false) {
  u8 locator[LOCATOR_SIZE];
  encode_locator(locator);
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    // Keep the last valid copy intact while repairing its peer. Rewriting
    // both could turn a power cut during repair into destructive reformat.
    if(repair_only && (g_locator_valid_mask & (1U << copy)) != 0) continue;
    g_locator_valid_mask &= (u8) ~(1U << copy);
    if(!erase_sector(copy)) return false;
    const u32 address = sector_address(copy);
    if(!write_bytes(address, locator, sizeof(locator)) ||
       !write_byte(address + 5, STATE_ACTIVE)) return false;
    g_locator_valid_mask |= (u8) (1U << copy);
  }
  return true;
}

static bool load_catalog_and_repair_locators(void) {
  return load_catalog() &&
         (g_locator_valid_mask == ALL_LOCATORS || write_locators(true));
}

static bool data_sector_header_valid(u32 sector) {
  u8 header[DATA_SECTOR_HEADER_SIZE];
  if(!read_bytes(sector_address(sector), header, sizeof(header))) return false;
  return memcmp(header, "C9D0", 4) == 0 &&
         header[4] == PHYSICAL_FORMAT_VERSION &&
         header[5] == STATE_ACTIVE && get_le32(header, 8) == g_format_epoch;
}

static bool initialize_data_sector(u32 sector) {
  if(!erase_sector(sector)) return false;
  u8 header[DATA_SECTOR_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C9D0", 4);
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

static bool borrowed_stage_sector(u32 sector) {
  if(!data_sector_in_range(sector) ||
     g_geometry.physical_sectors > 128) return false;
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  // A failed read must not turn an unknown sector into an erase candidate.
  if(!read_bytes(sector_address(sector), header, sizeof(header))) return true;
  return memcmp(header, "C9S0", 4) == 0 &&
         header[4] == PHYSICAL_FORMAT_VERSION &&
         header[5] == STATE_ACTIVE &&
         get_le32(header, 8) == g_format_epoch;
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
  if(catalog_sector_busy(sector) || transient_large_sector(sector)) return true;
  for(u16 id = 0; id < g_geometry.max_nodes; id++) {
    Inode inode;
    if(!get_inode(id, inode)) return true;
    if(!visible_inode(inode)) continue;
    if((inode.address < EXTENT_ADDRESS &&
        inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE == sector) ||
       (inode.fat_address < EXTENT_ADDRESS &&
        inode.fat_address / storage_geometry::PHYSICAL_SECTOR_SIZE == sector)) return true;
    if(large_file_inode(inode)) {
      LargeDescriptor descriptor = {};
      if(!read_large_descriptor(id, inode, descriptor) ||
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

static void mark_sector_window(u32 sector, u32 first, u32 count, u32 start,
                               u32 base, u8 window, u32& mask) {
  if(sector < first || sector - first >= count) return;
  const u32 relative = (sector - first + count - (start - first)) % count;
  if(relative >= base && relative < base + window) {
    mask |= 1UL << (relative - base);
  }
}

// One table scan covers 32 candidates for either allocator, including all
// large-file blocks. A read error must never make live data look reclaimable.
static bool live_sector_window(u32 first, u32 count, u32 start,
                               u32 base, u8 window, u32& mask) {
  mask = 0;
  for(u8 index = 0; index < g_large_write_sector_count; ++index) {
    mark_sector_window(g_large_write_sectors[index], first, count, start,
                       base, window, mask);
  }
  for(u16 id = 0; id < g_geometry.max_nodes; ++id) {
    Inode inode;
    if(!get_inode(id, inode)) return false;
    if(!visible_inode(inode)) continue;
    if(inode.address < EXTENT_ADDRESS) {
      mark_sector_window(inode.address / storage_geometry::PHYSICAL_SECTOR_SIZE,
                         first, count, start, base, window, mask);
    }
    if(inode.fat_address < EXTENT_ADDRESS) {
      mark_sector_window(inode.fat_address / storage_geometry::PHYSICAL_SECTOR_SIZE,
                         first, count, start, base, window, mask);
    }
    if(large_file_inode(inode)) {
      LargeDescriptor descriptor = {};
      if(!read_large_descriptor(id, inode, descriptor)) return false;
      for(u8 block = 0; block < descriptor.block_count; ++block) {
        mark_sector_window(descriptor.sectors[block], first, count, start,
                           base, window, mask);
      }
    }
  }
  return true;
}

static bool select_reclaimable_sector(u32& out) {
  const u32 first = g_geometry.data_first_sector;
  const u32 count = g_geometry.data_sector_count;
  const u32 start = data_sector_in_range(g_meta.gc_cursor)
      ? g_meta.gc_cursor : first;
  for(u32 base = 0; base < count; base += GC_SCAN_WINDOW) {
    const u8 window = (u8) ((count - base < GC_SCAN_WINDOW)
        ? count - base : GC_SCAN_WINDOW);
    u32 live_mask = 0;
    if(!live_sector_window(first, count, start, base, window, live_mask)) return false;
    for(u8 slot = 0; slot < window; slot++) {
      const u32 sector = first +
          (start - first + base + slot) % count;
      if(sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
         catalog_sector_busy(sector) || borrowed_stage_sector(sector) ||
         (live_mask & (1UL << slot)) != 0) continue;
      if(!initialize_data_sector(sector)) continue;
      out = sector;
      g_meta.gc_cursor = first + (sector - first + 1) % count;
      return true;
    }
  }
  return false;
}

static bool select_gc_victim(u32& out, u16 limit = 0xFFFE,
                             bool nonempty = false) {
  const u32 first = g_geometry.data_first_sector;
  const u32 count = g_geometry.data_sector_count;
  const u32 start = data_sector_in_range(g_meta.gc_cursor)
      ? g_meta.gc_cursor : first;
  for(u32 base = 0; base < count; base += GC_SCAN_WINDOW) {
    const u8 window = (u8) ((count - base < GC_SCAN_WINDOW)
        ? count - base : GC_SCAN_WINDOW);
    u16 live_bytes[GC_SCAN_WINDOW] = {};

    for(u8 index = 0; index < g_large_write_sector_count; index++) {
      const u32 sector = g_large_write_sectors[index];
      if(!data_sector_in_range(sector)) continue;
      const u32 relative = (sector - first + count - (start - first)) % count;
      if(relative >= base && relative < base + window) {
        live_bytes[relative - base] = 0xFFFF;
      }
    }
    for(u16 id = 0; id < g_geometry.max_nodes; id++) {
      Inode inode;
      if(!get_inode(id, inode)) return false;
      if(!visible_inode(inode)) continue;
      if(inode.address < EXTENT_ADDRESS) {
        const u32 sector = inode.address /
            storage_geometry::PHYSICAL_SECTOR_SIZE;
        if(data_sector_in_range(sector)) {
          const u32 relative =
              (sector - first + count - (start - first)) % count;
          if(relative >= base && relative < base + window) {
            const u8 slot = (u8) (relative - base);
            const u32 sum = (u32) live_bytes[slot] + inode.record_len;
            live_bytes[slot] = sum > 0xFFFFU ? 0xFFFFU : (u16) sum;
          }
        }
      }
      if(inode.fat_address < EXTENT_ADDRESS) {
        const u32 sector = inode.fat_address / storage_geometry::PHYSICAL_SECTOR_SIZE;
        if(data_sector_in_range(sector)) {
          const u32 relative = (sector - first + count - (start - first)) % count;
          if(relative >= base && relative < base + window) {
            u16 size = 0;
            if(!c9_map_size(id, inode, size)) return false;
            const u8 slot = (u8) (relative - base);
            const u32 sum = (u32) live_bytes[slot] + size;
            live_bytes[slot] = sum > 0xFFFFU ? 0xFFFFU : (u16) sum;
          }
        }
      }
      if(large_file_inode(inode)) {
        LargeDescriptor descriptor = {};
        if(!read_large_descriptor(id, inode, descriptor)) return false;
        for(u8 block = 0; block < descriptor.block_count; block++) {
          const u32 sector = descriptor.sectors[block];
          if(!data_sector_in_range(sector)) continue;
          const u32 relative =
              (sector - first + count - (start - first)) % count;
          if(relative >= base && relative < base + window) {
            live_bytes[relative - base] = 0xFFFF;
          }
        }
      }
    }

    u16 best_bytes = 0xFFFF;
    u32 best = EMPTY_ADDRESS;
    for(u8 slot = 0; slot < window; slot++) {
      const u32 sector = first + (start - first + base + slot) % count;
      if(sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
         catalog_sector_busy(sector) || borrowed_stage_sector(sector)) continue;
      if((!nonempty || live_bytes[slot] != 0) &&
         live_bytes[slot] <= limit && live_bytes[slot] < best_bytes) {
        best_bytes = live_bytes[slot];
        best = sector;
      }
    }
    if(best != EMPTY_ADDRESS) {
      out = best;
      return true;
    }
  }
  return false;
}

static bool commit_meta_only(const CatalogMeta& meta) {
  Transaction transaction;
  txn_begin(transaction);
  transaction.meta = meta;
  return append_transaction(transaction);
}

enum GcMode : u8 { GC_MERGE = 1, GC_LIVE_VICTIM = 2 };
static bool garbage_collect(u8 mode = 0) {
  const bool merge_current = (mode & GC_MERGE) != 0;
  // Includes newly allocated reserves not yet named by committed metadata.
  struct SectorPin {
    explicit SectorPin(u32 sector) { g_gc_victim = sector; }
    ~SectorPin() { g_gc_victim = EMPTY_ADDRESS; }
  };
  if(!merge_current && (!data_sector_in_range(g_meta.reserve_sector) ||
     borrowed_stage_sector(g_meta.reserve_sector) ||
     sector_has_live_inode(g_meta.reserve_sector))) {
    u32 replacement = EMPTY_ADDRESS;
    if(!select_reclaimable_sector(replacement)) return false;
    SectorPin reserve_pin(replacement);
    CatalogMeta meta = g_meta;
    meta.reserve_sector = replacement;
    if(!commit_meta_only(meta)) return false;
  }

  u32 victim = EMPTY_ADDRESS;
  u16 limit = 0xFFFE;
  if(merge_current) {
    if(!data_sector_in_range(g_meta.current_sector) ||
       !data_sector_header_valid(g_meta.current_sector) ||
       g_meta.current_offset > storage_geometry::PHYSICAL_SECTOR_SIZE) return false;
    limit = (u16) (storage_geometry::PHYSICAL_SECTOR_SIZE - g_meta.current_offset);
    if(!range_erased(sector_address(g_meta.current_sector) +
                      g_meta.current_offset, limit)) return false;
  }
  if(!select_gc_victim(victim, limit, (mode & GC_LIVE_VICTIM) != 0)) return false;
  // A checkpoint can run after the last inode has left the victim but before
  // GC erases it. Do not let the moving catalog claim it in that interval.
  SectorPin victim_pin(victim);

  const u32 destination = merge_current ? g_meta.current_sector
                                       : g_meta.reserve_sector;
  if(!merge_current && !initialize_data_sector(destination)) return false;
  u16 destination_offset = merge_current ? g_meta.current_offset
                                         : DATA_SECTOR_HEADER_SIZE;
  u8 copy_buffer[64];
  u16 next_id = 0;
  while(next_id < g_geometry.max_nodes) {
    Transaction transaction;
    txn_begin(transaction);
    while(next_id < g_geometry.max_nodes &&
          transaction.count < WAL_MAX_UPDATES) {
      const u16 id = next_id++;
      Inode inode;
      if(!get_inode(id, inode)) return false;
      if(!visible_inode(inode)) continue;
      bool moved = false;
      for(u8 reference = 0; reference < 2; ++reference) {
        const u32 old_address = reference == 0 ? inode.address : inode.fat_address;
        if(old_address >= EXTENT_ADDRESS || old_address / 4096U != victim) continue;
        u16 record_size = inode.record_len;
        if(reference != 0 && !c9_map_size(id, inode, record_size)) return false;
        if(record_size == 0 || (u32) destination_offset + record_size > 4096U) return false;
        const u32 new_address = sector_address(destination) + destination_offset;
        u32 source = old_address, target = new_address;
        u16 remaining = record_size;
        while(remaining != 0) {
          const u16 copied = remaining < sizeof(copy_buffer) ? remaining : sizeof(copy_buffer);
          if(!read_bytes(source, copy_buffer, copied) ||
             !write_bytes(target, copy_buffer, copied)) return false;
          source += copied; target += copied;
          remaining = (u16) (remaining - copied);
        }
        if(reference == 0) inode.address = new_address;
        else inode.fat_address = new_address;
        destination_offset = (u16) (destination_offset + record_size);
        moved = true;
      }
      if(moved && !txn_set(transaction, id, inode)) return false;
    }
    if(merge_current) transaction.meta.current_offset = destination_offset;
    if(transaction.count != 0 && !append_transaction(transaction)) {
      return false;
    }
  }

  CatalogMeta promoted = g_meta;
  promoted.current_sector = destination;
  promoted.current_offset = destination_offset;
  if(!merge_current) promoted.reserve_sector = EMPTY_ADDRESS;
  const u32 first = g_geometry.data_first_sector;
  promoted.gc_cursor = first +
      (victim - first + 1) % g_geometry.data_sector_count;
  if(!commit_meta_only(promoted)) return false;
  // The caller can now reclaim the old sector. Do not erase it twice: the
  // large-block allocator will erase it only after its last inode is durable.
  if(merge_current) return true;
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

static bool visible_file_size(ProgramType type, const FileSource& source,
                              u16 data_len, u32& output) {
  output = data_len;
  if(!text_content(type)) return true;
  output = 0;
  u8 bytes[64];
  u16 offset = 0;
  while(offset < data_len) {
    const u16 remaining = (u16) (data_len - offset);
    const u16 count = remaining < (u16) sizeof(bytes)
        ? remaining : (u16) sizeof(bytes);
    if(!source.read(source.context, offset, bytes, count)) return false;
    for(u16 index = 0; index < count; ++index) {
      if(!mk8::valid_byte(bytes[index])) return false;
      output += mk8::utf8(bytes[index]).size;
    }
    offset = (u16) (offset + count);
  }
  return true;
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
  header[1] = '9';
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
  header[1] = '9';
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

__attribute__((noinline))
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
  return header[0] == 'R' && header[1] == '9' && header[2] == STATE_ACTIVE &&
         header[3] == (u8) inode_kind(inode) && get_le16(header, 4) == expected_id &&
         get_le16(header, 6) == inode.parent_id && length_valid &&
         header[10] != 0 && header[10] < NAME_SIZE &&
         (u16) (RECORD_HEADER_SIZE + header[10] + stored_len) ==
             inode.record_len;
}

__attribute__((noinline))
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
  u8 buffer[MK61_PROGRAM_STORE_READ_CHUNK];
  u16 buffered;
  u16 cursor;
  mk61_crc32::Context* crc;
};

static bool next_record_payload_byte(void* context, u8& value) {
  RecordPayloadInput& input = *(RecordPayloadInput*) context;
  if(input.position >= input.size) return false;
  if(input.cursor >= input.buffered) {
    const u16 remaining = (u16) (input.size - input.position);
    input.buffered = (u16) (remaining < sizeof(input.buffer)
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
                                  u16 offset, u8* output, u16 size,
                                  const zx0::Output* sink = nullptr) {
  const u16 stored_len = get_le16(header, 8);
  mk61_crc32::Context record_crc;
  if(!update_record_crc_prefix(
       record_crc, (NodeKind) header[3], (ProgramType) header[11],
       id, inode.parent_id, name, stored_len)) return false;
  RecordPayloadInput compressed = {};
  compressed.address = inode.address + RECORD_HEADER_SIZE + header[10];
  compressed.size = stored_len;
  compressed.crc = &record_crc;
  const zx0::Input input = {&compressed, next_record_payload_byte};
  u8 window[256] = {};
  const bool decoded = zx0::decode_range(
      input, stored_len, inode.data_len,
      offset, output, size, window, sizeof(window), sink);
  return decoded &&
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
  memcpy(output, "C9L0", 4);
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
     memcmp(input, "C9L0", 4) != 0 ||
     input[4] != LARGE_DESCRIPTOR_VERSION ||
     get_le16(input, 6) != LARGE_DESCRIPTOR_HEADER_SIZE) return false;
  descriptor.version = input[4];
  descriptor.block_count = input[5];
  descriptor.data_len = get_le16(input, 8);
  descriptor.stored_len = get_le16(input, 10);
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
  return memcmp(header, "C9B0", 4) == 0 &&
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
  u8 buffer[MK61_PROGRAM_STORE_READ_CHUNK];
  u16 buffered;
  u16 cursor;
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
    input.buffered = count;
    input.cursor = 0;
  }
  value = input.buffer[input.cursor++];
  input.position++;
  return true;
}

static bool read_large_zx0_range(u16 id,
                                 const LargeDescriptor& descriptor,
                                 u16 offset, u8* output, u16 size,
                                 const zx0::Output* sink = nullptr) {
  LargePayloadInput compressed = {
    id, &descriptor, 0, {}, 0, 0, mk61_crc32::INITIAL_STATE
  };
  const zx0::Input input = {&compressed, next_large_payload_byte};
  u8 window[256] = {};
  return zx0::decode_range(input, descriptor.stored_len,
                           descriptor.data_len, offset, output, size,
                           window, sizeof(window), sink) &&
         compressed.position == descriptor.stored_len &&
         mk61_crc32::finish(compressed.crc) == descriptor.data_crc;
}

static bool payload_equals_source(u16 id, const Inode& inode,
                                  const char* name,
                                  const FileSource& source, u16 data_len) {
  if(inode_kind(inode) != NodeKind::FILE || inode.data_len != data_len ||
     !source_valid(source, data_len)) return false;
  // Equality checking is not on the read hot path.  Keep its two simultaneous
  // work buffers small so compressed-file verification preserves stack headroom
  // on the 64 KiB F401 build.
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

static WriteFailureDetail fat_name_available(u16 parent_id, NodeKind kind,
                                             ProgramType type,
                                             const char* name,
                                             u16 ignore_id) {
  char wanted[NAME_SIZE + 16];
  if(!fat_visible_name(kind, type, name, wanted)) {
    return WriteFailureDetail::TARGET_VISIBLE_NAME;
  }
  const u16 wanted_hash = hash_name(wanted);
  u16 root_slots = storage_geometry::ROOT_SYSTEM_DIRENTS;
  u16 id = parent_id == ROOT_ID ? g_meta.root_head : NONE;
  if(parent_id != ROOT_ID) {
    Inode parent;
    if(!get_inode(parent_id, parent) || inode_kind(parent) != NodeKind::DIRECTORY) {
      return WriteFailureDetail::PARENT;
    }
    id = parent.first_child;
  }
  for(u16 guard = 0; id != NONE && guard < g_geometry.max_nodes; guard++) {
    Inode inode;
    if(!get_inode(id, inode) || !visible_inode(inode) ||
       inode.parent_id != parent_id) {
      return WriteFailureDetail::CHILD_CATALOG;
    }
    if(id != ignore_id) {
      u16 visible_hash = inode.name_hash;
      if(inode_kind(inode) == NodeKind::FILE) {
        visible_hash = (u16) ((visible_hash ^ (u8) '.') * 257U + 17U);
        for(const char* ext = extension_for_type(inode_type(inode)); *ext; ++ext)
          visible_hash = (u16) ((visible_hash ^ mk8::fold_case((u8) *ext)) * 257U + 17U);
      }
      if(parent_id != ROOT_ID && visible_hash != wanted_hash) {
        id = inode.next_sibling;
        continue;
      }
      char stored[NAME_SIZE];
      char visible[NAME_SIZE + 16];
      if(!read_inode_name(id, inode, stored)) {
        return WriteFailureDetail::CHILD_NAME;
      }
      if(!fat_visible_name(inode_kind(inode), inode_type(inode), stored,
                           visible)) {
        return WriteFailureDetail::CHILD_VISIBLE_NAME;
      }
      if(parent_id == ROOT_ID) {
        const u16 slots = fat_name::dirent_count(visible);
        if(slots == 0 || slots > g_geometry.root_entries ||
           root_slots > g_geometry.root_entries - slots) {
          return WriteFailureDetail::ROOT_EXISTING_CAPACITY;
        }
        root_slots = (u16) (root_slots + slots);
      }
      if(fat_name::equal(wanted, visible)) {
        return WriteFailureDetail::COLLISION;
      }
    }
    id = inode.next_sibling;
  }
  if(id != NONE) return WriteFailureDetail::CHAIN;
  if(parent_id != ROOT_ID) return WriteFailureDetail::NONE;
  const u16 wanted_slots = fat_name::dirent_count(wanted);
  if(wanted_slots == 0 || wanted_slots > g_geometry.root_entries ||
     root_slots > g_geometry.root_entries - wanted_slots) {
    return WriteFailureDetail::ROOT_TARGET_CAPACITY;
  }
  return WriteFailureDetail::NONE;
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
  g_reverse_ready = g_import_applying = g_import_plan_ready = false;
  g_reverse_window = g_chain_verified_id = NONE;
  g_chain_verified_address = EMPTY_ADDRESS;
  g_c9_pin_count = 0;
#ifdef SPI_FLASH
  const u32 capacity = flash_device().getCapacity();
#else
  const u32 capacity = 0;
#endif
  if(!compute_geometry(capacity, g_geometry)) return false;
  g_format_epoch = g_format_epoch != 0
      ? g_format_epoch + 1 : (0xC9F90001UL ^ capacity ^ millis());
  if(g_format_epoch == 0 || g_format_epoch == 0xFFFFFFFFUL) g_format_epoch ^= 0x13579BDFUL;
  g_ready = false;
  g_mount_status = MountStatus::UNAVAILABLE;
  memset(g_catalog_pages, 0xFF, sizeof(g_catalog_pages));
  clear_pending_catalog();
  g_catalog_root = g_catalog_wal = EMPTY_ADDRESS;
  g_catalog_cursor = storage_geometry::LOCATOR_SECTORS;
  g_gc_victim = EMPTY_ADDRESS;
  g_catalog_generation = 0;
  g_wal_sequence = 0;
  g_wal_records = 0;
  g_wal_sealed = false;
  g_overlay_count = 0;
  g_free_hint = 0;
  g_locator_valid_mask = 0;
  g_large_write_sector_count = 0;
  g_verified_large_id = NONE;
  g_verified_large_generation = 0;
  g_verified_large_block = 0xFF;
  invalidate_table_cache();
  memset(&g_meta, 0, sizeof(g_meta));
  g_meta.root_head = NONE;
  g_meta.current_sector = EMPTY_ADDRESS;
  g_meta.current_offset = 0;
  g_meta.reserve_sector = g_geometry.data_first_sector + g_geometry.data_sector_count - 1;
  g_meta.gc_cursor = g_geometry.data_first_sector;
  g_meta.data_sequence = 0;

  // Publish an empty root and WAL, without reading or copying the old table.
  // Absent pages mean all-FF inodes. Old roots/data are excluded by the new
  // epoch and are erased lazily as the circular allocator reaches them.
  if(!checkpoint(true)) return false;
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


void init(void) {
  g_reverse_ready = g_import_applying = g_import_plan_ready = false;
  g_reverse_window = g_chain_verified_id = NONE;
  g_chain_verified_address = EMPTY_ADDRESS;
  g_c9_pin_count = 0;
  DiskActivity activity;
  g_ready = false;
  g_mount_status = MountStatus::UNAVAILABLE;
  g_free_hint = 0;
  g_format_epoch = 0;
  g_gc_victim = EMPTY_ADDRESS;
  memset(&g_geometry, 0, sizeof(g_geometry));
  if(!flash_is_ok) return;
  dbgln(SPIROM, "C9 locator: scan");
  if(load_locator()) {
    if(!load_catalog_and_repair_locators()) {
      dbgln(SPIROM, "C9 catalog: invalid");
      // A valid locator identifies an existing C9 volume. A broken root,
      // page or read is not a blank device: require an explicit format.
      g_mount_status = MountStatus::REPAIR_REQUIRED;
    } else {
      dbgln(SPIROM, "C9 catalog: ready");
      g_ready = true;
      g_mount_status = MountStatus::READY;
    }

  } else if(load_capacity_for_reformat()) {
    // A current C9 locator with changed geometry requires explicit format;
    // retain its measured capacity without probing the live volume.
    g_mount_status = MountStatus::FORMAT_REQUIRED;
  } else {
    dbgln(SPIROM, "C9 locator: absent or incompatible");
    u32 capacity = 0;
#ifdef SPI_FLASH
    {
      dbgln(SPIROM, "C9 capacity probe: start");
#ifdef DEBUG_SPIFLASH
      const flash_capacity_probe::ProbeProgress progress =
          capacity_probe_debug;
#else
      const flash_capacity_probe::ProbeProgress progress = nullptr;
#endif
      if(!flash_capacity_probe::detect(
             flash_device(), flash_device().capacityProbeUpper(), capacity, progress) ||
         !flash_device().setCapacity(capacity)) {
        dbgln(SPIROM, "C9 capacity probe: failed");
        return;
      }
    }
#endif
    dbgln(SPIROM, "C9 capacity probe: ", (isize) capacity, " bytes");
    dbgln(SPIROM, "C9 format: start");
    if(!format_internal(true)) {
      dbgln(SPIROM, "C9 format: failed");
      return;
    }
    dbgln(SPIROM, "C9 format: complete");
  }
  if(g_ready) {
    vfat_stage_clear();
  }
}

bool format(void) {
  DiskActivity activity;
  if(!flash_is_ok) return false;
  if(g_mount_status == MountStatus::FORMAT_REQUIRED) {
    if(!format_internal(!settings_guard_valid(g_geometry))) return false;
  } else if(!format_internal(false)) {
    return false;
  }
  vfat_stage_clear();
  return true;
}

bool refresh(void) {
  init();
  return g_ready;
}

bool ready(void) { return g_ready; }

u32 catalog_revision(void) {
  return g_ready ? g_format_epoch ^ g_wal_sequence ^ (g_catalog_generation * 251U) : 0;
}

u32 media_revision(void) {
  if(!g_ready) return 0;
  // Compact both persistent counters into a well-distributed change token.
  // FAT only compares identity; it does not impose ordering on this value.
  // Include the persisted volume identity: a reformat can reuse the same
  // catalog/WAL counters and inodes, but must invalidate live SRAM caches.
  u32 revision = g_format_epoch;
  revision ^= g_catalog_generation + 0x9E3779B9UL +
              (revision << 6) + (revision >> 2);
  revision ^= g_wal_sequence + 0x9E3779B9UL +
              (revision << 6) + (revision >> 2);
  revision ^= (u32) g_stage_generation + 0x9E3779B9UL +
              (revision << 6) + (revision >> 2);
  return revision;
}

MountStatus mount_status(void) { return g_mount_status; }

const storage_geometry::Geometry& geometry(void) { return g_geometry; }

u16 max_nodes(void) { return g_ready ? g_geometry.max_nodes : 0; }

u16 used_nodes(void) {
  return g_ready ? g_meta.total_count : 0;
}

bool basename_valid(const char* name) { return valid_name(name); }

u32 settings_address(void) {
  return (g_ready || g_mount_status == MountStatus::FORMAT_REQUIRED ||
          g_mount_status == MountStatus::REPAIR_REQUIRED)
      ? sector_address(g_geometry.settings_sector) : 0;
}

u16 settings_size(void) {
  return (g_ready || g_mount_status == MountStatus::FORMAT_REQUIRED ||
          g_mount_status == MountStatus::REPAIR_REQUIRED)
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
    ProgramType::MARKDOWN,
    ProgramType::MK61_BINARY,
    ProgramType::SHEET
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
  bool catalog_relocated = false;
  bool records_compacted = false;
  for(;;) {
    const u32 start = data_sector_in_range(g_meta.gc_cursor)
        ? g_meta.gc_cursor : first;
    for(u32 offset = 0; offset < count; offset++) {
      const u32 sector = first + (start - first + offset) % count;
      if(sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
         borrowed_stage_sector(sector) ||
         sector_has_live_inode(sector)) continue;
      if(!erase_sector(sector)) continue;
      output = sector;
      g_meta.gc_cursor = first + (sector - first + 1) % count;
      return true;
    }
    // Rotating catalog pages may borrow data sectors while there is space.
    // At physical exhaustion move them back to the metadata-only reserve;
    // otherwise the usable capacity depends on the last checkpoint location.
    if(!catalog_relocated) {
      catalog_relocated = true;
      bool borrowed = data_sector_in_range(g_catalog_root) ||
                      data_sector_in_range(g_catalog_wal);
      for(u8 page = 0; page < g_geometry.catalog_table_sectors; ++page) {
        borrowed |= data_sector_in_range(g_catalog_pages[page].sector);
      }
      if(borrowed) {
        if(!checkpoint(false, true)) {
          if(!load_catalog()) g_ready = false;
          return false;
        }
        continue;
      }
    }
    // Deleted large-file descriptors can leave several almost-empty record
    // sectors. A large block needs a whole sector, not just unused tail bytes.
    if(!records_compacted) {
      records_compacted = true;
      if(garbage_collect(true) ||
         (garbage_collect() && garbage_collect(true))) continue;
    }
    return false;
  }
}

// Keep large-file work buffers out of the caller's small-file/encoder paths.
// GCC otherwise inlines them and reserves their stack for every C9 write.
__attribute__((noinline))
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
    memcpy(header, "C9B0", 4);
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
    memcpy(header, "C9B0", 4);
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

__attribute__((noinline))
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

#include "program_store_fat_chain.inc"


static bool prepare_local_catalog_mutation(void) {
  // During MSC recovery the locked journal is the transaction being applied.
  // Outside that session, however, any surviving FAT stage describes an
  // older exported catalog.  A local/UI/terminal mutation establishes a new
  // authoritative C9 state, so discard that stale stage before changing the
  // catalog.  The stage records are invalidated one byte at a time and remain
  // power-loss safe; a later retry simply finishes the discard.
  return g_stage_locked || vfat_stage_discard_all();
}

bool create_directory(u16 parent_id, const char* name, u16 preferred_id,
                      u16* out_id) {
  C9Pins pins;
  DiskActivity activity;
  if(!g_ready || !prepare_local_catalog_mutation() ||
     !valid_name(name) || !parent_valid(parent_id)) return false;
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
  if(fat_name_available(parent_id, NodeKind::DIRECTORY,
                        ProgramType::MK61, name, preferred_id) !=
     WriteFailureDetail::NONE) return false;
  u16 id = NONE;
  if(!find_free_id(preferred_id, id)) return false;
  u16 cluster = 0;
  Inode empty = empty_inode();
  const u16* requested = g_directory_requested_cluster == NONE ? nullptr : &g_directory_requested_cluster;
  if(!c9_choose_file_chain(id, empty, 1, requested, requested == nullptr ? 0 : 1, &cluster)) return false;
  C9ArraySource mapping = {&cluster, 1};
  u32 fat_address = EMPTY_ADDRESS;
  if(!c9_append_chain(id, 1, {&mapping, c9_array_cluster}, fat_address)) return false;
  u32 address = 0;
  u16 record_len = 0;
  if(!append_record(NodeKind::DIRECTORY, ProgramType::MK61, id, parent_id,
                    name, NULL, 0, address, record_len)) return false;
  Inode inode = empty_inode();
  inode.address = address;
  inode.data_len = NONE;
  inode.fat_address = fat_address;
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
  if(!c9_pin(address, id, false) ||
     !link_at_head(transaction, id, inode, parent_id) ||
     !c9_grow_directory(transaction, parent_id) ||
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
#if !defined(PROGRAM_STORE_HOST_TEST)
  struct ImportProgressScope {
    bool previous;
    ImportProgressScope() : previous(g_usb_file_import_progress) {
      if(g_stage_locked) g_usb_file_import_progress = true;
    }
    ~ImportProgressScope() { g_usb_file_import_progress = previous; }
  } import_progress;
#endif
  C9Pins pins;
  g_last_write_failure = WriteFailure::ARGUMENTS;
  g_last_write_failure_detail = WriteFailureDetail::NONE;
  DiskActivity activity;
  if(!g_ready || !prepare_local_catalog_mutation()) return false;
  LargeWriteGuard large_guard;
  // The compression plan is consumed before the catalog transaction starts.
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE)
  WriteWorkspace& write_workspace = g_write_workspace;
#else
  WriteWorkspace write_workspace;
#endif
  write_workspace.compression[0] = 0; // Start the trivial array's lifetime.
  auto& fallback_workspace = write_workspace.compression;
  const u16 max_data_len = maximum_data_len(type);
  if(!supported_type(type) || !valid_name(name) || !parent_valid(parent_id) ||
     (type == ProgramType::CHIP8 && data_len == 0) ||
     data_len > max_data_len ||
     !source_valid(source, data_len)) return false;
  g_last_write_failure = WriteFailure::VISIBLE_SIZE;
  u32 fat_visible_size = 0;
  if(!visible_file_size(type, source, data_len, fat_visible_size) ||
     fat_visible_size > 0xFFFFU) return false;
  g_last_write_failure = WriteFailure::EXTENT_SHAPE;
  const u32 cluster_bytes =
      (u32) g_geometry.sectors_per_cluster * VFAT_STAGE_BLOCK_SIZE;
  const u8 required_clusters = fat_visible_size == 0 ? 0 : (u8) (
      (fat_visible_size + cluster_bytes - 1U) / cluster_bytes);
  if(required_clusters > MAX_FAT_EXTENTS_PER_FILE + 1U ||
     (fat_extents == NULL && fat_extent_count != 0) ||
     (fat_extents != NULL && fat_extent_count != required_clusters)) {
    return false;
  }

  g_last_write_failure = WriteFailure::PREFERRED_ID;
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
  g_last_write_failure = WriteFailure::NAME_COLLISION;
  g_last_write_failure_detail = fat_name_available(
      parent_id, NodeKind::FILE, type, name, id);
  if(g_last_write_failure_detail != WriteFailureDetail::NONE) {
    return false;
  }

  char old_name[NAME_SIZE] = {};
  if(replacing) {
    if(!read_inode_name(id, old_inode, old_name)) {
      g_last_write_failure_detail = WriteFailureDetail::REPLACED_NAME;
      return false;
    }
    const bool same_extents = fat_extents == nullptr ||
        c9_chain_equals(id, old_inode, fat_extents, fat_extent_count);
    if(old_inode.parent_id == parent_id && inode_type(old_inode) == type &&
       strcmp(old_name, name) == 0 && same_extents &&
       payload_equals_source(id, old_inode, name, source, data_len)) {
      if(!c9_reserve_mapping(id)) return false;
      g_last_write_failure = WriteFailure::NONE;
      if(out_id != NULL) *out_id = id;
      return true;
    }
  }

  g_last_write_failure = WriteFailure::EXTENT_SELECTION;
  u16 clusters[MAX_FAT_EXTENTS_PER_FILE + 1U] = {};
  if(!c9_pin(old_inode.fat_address, id, true) ||
     !c9_choose_file_chain(id, old_inode, required_clusters, fat_extents,
                          fat_extent_count, clusters)) return false;

  g_last_write_failure = WriteFailure::COMPRESSION;
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
      (type == ProgramType::APP || type == ProgramType::CHIP8 ||
       type == ProgramType::MK61_BINARY ||
       (MAX_FONT_SIZE > MAX_IMAGE1_SIZE && type == ProgramType::FONT)) &&
      stored_len > MAX_IMAGE1_SIZE;

  g_last_write_failure = WriteFailure::RECORD;
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

  if(!c9_pin(address, id, false)) return false;
  C9ArraySource mapping = {clusters, required_clusters};
  u32 fat_address = EMPTY_ADDRESS;
  if(!c9_append_chain(id, required_clusters, {&mapping, c9_array_cluster}, fat_address)) return false;
  Inode inode = replacing ? old_inode : empty_inode();
  inode.fat_address = fat_address;
  inode.address = address;
  inode.data_len = data_len;
  inode.exported_size = (u16) fat_visible_size;
  inode.record_len = record_len;
  inode.parent_id = parent_id;
  inode.name_hash = hash_name(name);
  inode.kind_type = make_kind_type(NodeKind::FILE, type);
  inode.flags = (large ? INODE_FLAG_LARGE_FILE : 0) |
                (zx0 ? INODE_FLAG_ZX0 : 0);
  inode.first_child = NONE;
  if(!replacing) {
    inode.next_sibling = NONE;
    inode.prev_sibling = NONE;
  }

  g_last_write_failure = WriteFailure::CATALOG;
  write_workspace.transaction.count = 0; // Start Transaction's lifetime.
  Transaction& transaction = write_workspace.transaction;
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
  if(!c9_grow_directory(transaction, parent_id)) return false;
  g_last_write_failure = WriteFailure::COMMIT;
  if(!append_transaction(transaction)) return false;
  g_last_write_failure = WriteFailure::NONE;
  g_verified_large_id = NONE;
  g_verified_large_block = 0xFF;
  if(out_id != NULL) *out_id = id;
  return true;
}

WriteFailure last_write_failure(void) { return g_last_write_failure; }
WriteFailureDetail last_write_failure_detail(void) {
  return g_last_write_failure_detail;
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

static bool read_file_range(u16 id, u16 offset, u8* data, u16 len,
                            u16* out_len, const zx0::Output* sink) {
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
            id, descriptor, offset, data, copied, sink)) return false;
    } else if(sink != nullptr) {
      LargePayloadInput input = {
        id, &descriptor, 0, {}, 0, 0, mk61_crc32::INITIAL_STATE
      };
      u8 value;
      while(input.position < descriptor.stored_len) {
        if(!next_large_payload_byte(&input, value) ||
           !sink->next(sink->context, value)) return false;
      }
      if(mk61_crc32::finish(input.crc) != descriptor.data_crc) return false;
    } else if(copied != 0 &&
              !read_large_data(id, descriptor, offset, data, copied)) {
      return false;
    }
  } else {
    u8 header[RECORD_HEADER_SIZE];
    if(!read_record_header(inode, id, header)) return false;
    if(zx0_file_inode(inode)) {
      if(!read_zx0_record_range(id, inode, name, header,
                                offset, data, copied, sink)) return false;
    } else if(sink != nullptr) {
      mk61_crc32::Context crc;
      if(!update_record_crc_prefix(
           crc, (NodeKind) header[3], (ProgramType) header[11],
           id, inode.parent_id, name, inode.data_len)) return false;
      RecordPayloadInput input = {};
      input.address = inode.address + RECORD_HEADER_SIZE + header[10];
      input.size = inode.data_len;
      input.crc = &crc;
      u8 value;
      while(input.position < input.size) {
        if(!next_record_payload_byte(&input, value) ||
           !sink->next(sink->context, value)) return false;
      }
      if(crc.finish() != get_le32(header, 12)) return false;
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

bool exported_size_id(u16 id, u32& size) {
  Inode inode;
  if(!g_ready || !get_inode(id, inode) || inode_kind(inode) != NodeKind::FILE) {
    return false;
  }
  size = inode.exported_size;
  return text_content(inode_type(inode))
      ? size >= inode.data_len && size <= 3U * inode.data_len
      : size == inode.data_len;
}

bool read_range_id(u16 id, u16 offset, u8* data, u16 len, u16* out_len) {
  return read_file_range(id, offset, data, len, out_len, nullptr);
}

bool stream_file_id(u16 id, const FileSink& sink) {
  if(sink.next == nullptr) return false;
  const zx0::Output output = {sink.context, sink.next};
  u8 unused;
  return read_file_range(id, 0, &unused, 0, nullptr, &output);
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
  if(!g_ready || !prepare_local_catalog_mutation()) return false;
  Inode inode;
  if(!get_inode(id, inode) || !visible_inode(inode)) return false;
  if(inode_kind(inode) == NodeKind::DIRECTORY && inode.first_child != NONE) return false;

  // Reuse the bounded, power-safe tail trim instead of one transaction and
  // a traversal from the head for every directory extent.
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
  }
  if(g_free_hint >= g_geometry.max_nodes || id < g_free_hint) g_free_hint = id;
  return true;
}

bool remove_tree(u16 id, u16* removed) {
  DiskActivity activity;
  if(removed != NULL) *removed = 0;
  if(!g_ready || !prepare_local_catalog_mutation() ||
     id >= g_geometry.max_nodes) return false;
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
  C9Pins pins;
  DiskActivity activity;
  if(!g_ready || !prepare_local_catalog_mutation() ||
     !valid_name(new_name) || !parent_valid(new_parent_id)) return false;
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
  if(fat_name_available(new_parent_id, inode_kind(inode), inode_type(inode),
                        new_name, id) != WriteFailureDetail::NONE) return false;

  u8 header[RECORD_HEADER_SIZE];
  char old_name[NAME_SIZE];
  if(!read_inode_name(id, inode, old_name) ||
     !verify_record_crc(id, inode, old_name) ||
     !read_record_header(inode, id, header) ||
     !c9_pin(inode.fat_address, id, true) ||
     !c9_pin(inode.address, id, false)) return false;
  const u16 payload_len = get_le16(header, 8);
  C9RawSource raw = {inode.address + RECORD_HEADER_SIZE + header[10], payload_len};
  const FileSource source = {&raw, c9_read_raw};
  u32 address = 0;
  u16 record_len = 0;
  if(!append_record_source(inode_kind(inode), inode_type(inode), id,
          new_parent_id, new_name, source, payload_len, address, record_len)) return false;

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
  return c9_pin(address, id, false) &&
      c9_grow_directory(transaction, new_parent_id) && append_transaction(transaction);
}

bool rename(ProgramType type, const char* old_name, const char* new_name) {
  u16 id = NONE;
  Inode inode;
  return find_global_file(type, old_name, id) && get_inode(id, inode) &&
         move_rename(id, inode.parent_id, new_name);
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
  return sector_address(g_stage_physical[sector]);
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
  const u8 mask = (u8) (1U << (ref & 7U));
  if((key & 0x00400000UL) != 0) {
    g_stage_key_high[ref >> 3] |= mask;
  } else {
    g_stage_key_high[ref >> 3] &= (u8) ~mask;
  }
  return ((key & 0x003FFFFFUL) << STAGE_REF_BITS) | ref;
}

static void forget_stage_index_binding(void) {
  if(g_stage_index != nullptr) {
    g_stage_known_empty = g_stage_recovery_ok && !g_stage_external &&
        g_stage_ref_count == 0 &&
        g_stage_slot_count == g_geometry.stage_sector_count;
  }
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

static u16 stage_ref_limit(void) {
  // 64 ordinary segments hold 448 records. Keep seven records spare in
  // addition to the dedicated compaction segment so a full index can update.
  return g_geometry.physical_sectors == 128 ? STAGE_REF_CAPACITY : 441;
}

static bool bind_full_stage_index(void) {
  const u16 capacity = stage_ref_limit();
  if(g_stage_overlay_lease.ok()) {
    if(!g_stage_external && g_stage_index != nullptr &&
       g_stage_index_capacity == capacity) return true;
    if(g_stage_locked) return false;
    g_stage_overlay_lease.reset();
    forget_stage_index_binding();
  }
  if(g_stage_external ||
     !g_stage_overlay_lease.acquire_cache(
         shared_memory::Arena::OVERLAY,
         shared_memory::Owner::VFAT_STAGE,
         (usize) capacity * sizeof(u32))) return false;
  if(!g_stage_overlay_lease.set_evictable(prepare_stage_index_eviction)) {
    g_stage_overlay_lease.reset();
    return false;
  }
  g_stage_index = reinterpret_cast<u32*>(g_stage_overlay_lease.data());
  g_stage_index_capacity = capacity;
  g_stage_ref_count = 0;
  return true;
}

static bool ensure_stage_index(void) {
  if(g_stage_index != nullptr) return g_stage_recovery_ok;
  vfat_stage_clear();
  return g_stage_index != nullptr && g_stage_recovery_ok;
}

static u32 stage_index_key(u16 index) {
  const u32 packed = g_stage_index[index];
  const u16 ref = (u16) (packed & STAGE_REF_MASK);
  return (packed >> STAGE_REF_BITS) |
         (((u32) ((g_stage_key_high[ref >> 3] >> (ref & 7U)) & 1U)) << 22);
}

static u16 stage_index_ref(u16 index) {
  return (u16) (g_stage_index[index] & STAGE_REF_MASK);
}

static u16 stage_lower_bound(u32 key) {
#if defined(PROGRAM_STORE_HOST_TEST)
  g_stage_index_stats.lookups++;
#endif
  u16 low = 0, high = g_stage_ref_count;
  while(low < high) {
#if defined(PROGRAM_STORE_HOST_TEST)
    g_stage_index_stats.probes++;
#endif
    const u16 middle = (u16) (low + (high - low) / 2U);
    if(stage_index_key(middle) < key) low = (u16) (middle + 1U);
    else high = middle;
  }
  return low;
}
static int stage_ref_index(u32 key) {
  if(g_stage_index == nullptr) return -1;
  const u16 position = stage_lower_bound(key);
  return position < g_stage_ref_count && stage_index_key(position) == key ? position : -1;
}
static void stage_insert_index(u32 key, u16 ref) {
  const u16 position = stage_lower_bound(key);
  memmove(g_stage_index + position + 1U, g_stage_index + position,
           (usize) (g_stage_ref_count - position) * sizeof(u32));
  g_stage_index[position] = pack_stage_index(key, ref);
  ++g_stage_ref_count;
}
static void stage_remove_index(u16 position) {
  --g_stage_ref_count;
  memmove(g_stage_index + position, g_stage_index + position + 1U,
           (usize) (g_stage_ref_count - position) * sizeof(u32));
}

static bool stage_sector_header_valid(u16 sector) {
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  if(!read_bytes(stage_sector_address(sector), header, sizeof(header))) return false;
  return memcmp(header, "C9S0", 4) == 0 &&
         header[4] == PHYSICAL_FORMAT_VERSION &&
         header[5] == STATE_ACTIVE && get_le32(header, 8) == g_format_epoch;
}

static bool initialize_stage_sector(u16 sector) {
  if(!erase_sector(g_stage_physical[sector])) return false;
  u8 header[STAGE_SECTOR_HEADER_SIZE];
  memset(header, 0xFF, sizeof(header));
  memcpy(header, "C9S0", 4);
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
  if(header[0] != 'S' || header[1] != '9') return false;
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

static u16 stage_reserve_slot(void) {
  return (u16) (g_geometry.stage_sector_count - 1);
}

static bool normal_stage_slot(u16 sector) {
  return sector < g_stage_slot_count && sector != stage_reserve_slot();
}

static bool stage_slot_erased(u16 sector, u8 slot) {
  const u16 ref = (u16) (sector * STAGE_RECORDS_PER_SECTOR + slot + 1);
  u8 header[STAGE_RECORD_HEADER_SIZE];
  if(!read_bytes(stage_record_address(ref), header, sizeof(header))) return false;
  for(u8 i = 0; i < sizeof(header); i++) if(header[i] != 0xFF) return false;
  return true;
}

static bool append_stage_value(u16 sector, u32 key, const u8* data) {
  if(sector >= g_stage_slot_count || data == NULL ||
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
  record[1] = '9';
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
    stage_insert_index(key, ref);
  } else g_stage_index[index] = pack_stage_index(key, ref);
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
  if(!erase_sector(g_stage_physical[sector])) return false;
  g_stage_used[sector] = 0;
  g_stage_sealed[sector] = 0;
  return true;
}

// Завершает любое прерванное уплотнение. До стирания старого сектора копии всегда
// получают более новое поколение, поэтому при любом сбое питания остаётся хотя
// бы одна действительная версия каждого промежуточного блока.
static bool recover_stage_reserve(void) {
  if(g_stage_slot_count < 2) return false;
  const u16 reserve = stage_reserve_slot();
  u8 reserve_live = stage_sector_live_count(reserve);
  if(reserve_live == 0) return true;

  // Обычный приёмник уже может содержать первые записи, скопированные обратно
  // до сброса. Завершаем это направление, если свободного хвоста достаточно.
  for(u16 sector = 0; sector < g_stage_slot_count; sector++) {
    if(!normal_stage_slot(sector)) continue;
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
  for(u16 victim = 0; victim < g_stage_slot_count; victim++) {
    if(!normal_stage_slot(victim)) continue;
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
  if(g_stage_slot_count < 2 || !recover_stage_reserve()) return false;
  const u16 reserve = stage_reserve_slot();
  if(!initialize_stage_sector(reserve)) return false;
  g_stage_used[reserve] = 0;
  g_stage_sealed[reserve] = 0;

  u16 victim = 0;
  u8 victim_live = 0xFF;
  for(u16 sector = 0; sector < g_stage_slot_count; sector++) {
    if(!normal_stage_slot(sector)) continue;
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

static void mark_stage_borrow_occupied(u32 (&bits)[4], u32 physical) {
  if(!data_sector_in_range(physical)) return;
  const u32 relative = physical - g_geometry.data_first_sector;
  bits[relative >> 5] |= 1UL << (relative & 31U);
}

#if defined(STM32F411xE)
static u32 g_stage_borrow_diagnostic;
#define C9_BORROW_TRACE(value) (g_stage_borrow_diagnostic = (value))
#else
#define C9_BORROW_TRACE(value) ((void) 0)
#endif

static bool borrow_stage_slot(u16& out_sector, u8& out_slot) {
  C9_BORROW_TRACE(1U);
  if(g_geometry.physical_sectors != 128 ||
     g_geometry.data_sector_count > 128 ||
     g_stage_slot_count >= STAGE_MAX_SLOTS) return false;
  for(;;) {
    u32 occupied[4] = {};
    mark_stage_borrow_occupied(occupied, g_meta.current_sector);
    mark_stage_borrow_occupied(occupied, g_meta.reserve_sector);
    for(u8 index = 0; index < g_large_write_sector_count; index++) {
      mark_stage_borrow_occupied(occupied, g_large_write_sectors[index]);
    }
    for(u8 index = 0; index < g_c9_pin_count; ++index) {
      mark_stage_borrow_occupied(occupied, g_c9_pins[index].address / 4096U);
    }
    for(u16 id = 0; id < g_geometry.max_nodes; id++) {
      Inode inode;
      if(!get_inode(id, inode)) { C9_BORROW_TRACE(0x20000U | id); return false; }
      if(!visible_inode(inode)) continue;
      mark_stage_borrow_occupied(occupied, inode.address / 4096U);
      mark_stage_borrow_occupied(occupied, inode.fat_address / 4096U);
      if(large_file_inode(inode)) {
        LargeDescriptor descriptor = {};
        if(!read_large_descriptor(id, inode, descriptor)) { C9_BORROW_TRACE(0x30000U | id); return false; }
        for(u8 block = 0; block < descriptor.block_count; block++) {
          mark_stage_borrow_occupied(occupied, descriptor.sectors[block]);
        }
      }
    }
    u32 chosen = EMPTY_ADDRESS;
    u16 reclaimable = 0;
    const u32 end = g_geometry.data_first_sector +
                    g_geometry.data_sector_count;
    for(u32 physical = g_geometry.data_first_sector; physical < end;
        physical++) {
      const u32 relative = physical - g_geometry.data_first_sector;
      if((occupied[relative >> 5] & (1UL << (relative & 31U))) != 0 ||
         catalog_sector_busy(physical) || borrowed_stage_sector(physical)) continue;
      chosen = physical;
      reclaimable++;
    }
    // The imported C9 files and its COW collector must still have room to
    // publish the batch after host sync. A borrowed sector is never taken from
    // live file data, the current writer, or the GC reserve.
    C9_BORROW_TRACE(0x40000U | reclaimable);
    if(reclaimable <= STAGE_MIN_FREE_DATA_SECTORS) {
      // Native directory growth/deletion leaves small live records spread over
      // many otherwise empty sectors. Merge a live victim before lending more
      // whole sectors; an empty GC victim would make no physical space here.
      if(!garbage_collect(GC_MERGE | GC_LIVE_VICTIM) &&
         (!garbage_collect(GC_LIVE_VICTIM) || !garbage_collect(GC_MERGE | GC_LIVE_VICTIM))) return false;
      continue;
    }
    const u16 slot = g_stage_slot_count++;
    g_stage_physical[slot] = chosen;
    g_stage_used[slot] = 0;
    g_stage_sealed[slot] = 0;
    C9_BORROW_TRACE(0x50000U | chosen);
    if(!initialize_stage_sector(slot)) {
      if(!stage_sector_header_valid(slot)) g_stage_slot_count--;
      return false;
    }
    C9_BORROW_TRACE(0x60000U | chosen);
    out_sector = slot;
    out_slot = 0;
    return true;
  }
}

static bool find_stage_slot(u16& out_sector, u8& out_slot) {
  if(!recover_stage_reserve()) return false;
  for(u16 sector = 0; sector < g_stage_slot_count; sector++) {
    if(!normal_stage_slot(sector)) continue;
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

  for(u16 sector = 0; sector < g_stage_slot_count; sector++) {
    if(!normal_stage_slot(sector)) continue;
    if(stage_sector_has_live(sector)) continue;
    if(!initialize_stage_sector(sector)) continue;
    g_stage_used[sector] = 0;
    g_stage_sealed[sector] = 0;
    out_sector = sector;
    out_slot = 0;
    return true;
  }
  // A sector with fewer than seven live records can always be compacted into
  // the fixed reserve. Do that before borrowing physical space from C9.
  for(u16 sector = 0; sector < g_stage_slot_count; sector++) {
    if(normal_stage_slot(sector) &&
       stage_sector_live_count(sector) < STAGE_RECORDS_PER_SECTOR) {
      return compact_stage(out_sector, out_slot);
    }
  }
  return borrow_stage_slot(out_sector, out_slot);
}

} // пространство имён

#if defined(STM32F411xE)
u32 vfat_stage_borrow_diagnostic(void) { return g_stage_borrow_diagnostic; }
#endif

void vfat_stage_clear(void) {
  const bool bound = !g_stage_external && bind_full_stage_index();
  // A fresh recovery must never reuse knowledge from another mount or index.
  g_stage_known_empty = false;
  if(!bound) {
    g_stage_ref_count = 0;
    return;
  }
  g_stage_recovery_ok = true;
  g_stage_ref_count = 0;
  g_stage_generation = 0;
  memset(g_stage_used, 0, sizeof(g_stage_used));
  memset(g_stage_sealed, 0, sizeof(g_stage_sealed));
  memset(g_stage_key_high, 0, sizeof(g_stage_key_high));
  if(!g_ready) return;

  g_stage_slot_count = (u8) g_geometry.stage_sector_count;
  for(u16 slot = 0; slot < g_stage_slot_count; slot++) {
    g_stage_physical[slot] = g_geometry.stage_first_sector + slot;
  }
  if(g_geometry.physical_sectors == 128) {
    const u32 end = g_geometry.data_first_sector +
                    g_geometry.data_sector_count;
    for(u32 physical = g_geometry.data_first_sector; physical < end;
        physical++) {
      if(!borrowed_stage_sector(physical)) continue;
      if(g_stage_slot_count >= STAGE_MAX_SLOTS) {
        g_stage_recovery_ok = false;
        return;
      }
      g_stage_physical[g_stage_slot_count++] = physical;
    }
  }

  u8 payload[STAGE_DATA_SIZE];
  for(u16 sector = 0; sector < g_stage_slot_count; sector++) {
    if(!stage_sector_header_valid(sector)) {
      if(sector >= g_geometry.stage_sector_count) g_stage_recovery_ok = false;
      continue;
    }
    for(u8 slot = 0; slot < STAGE_RECORDS_PER_SECTOR; slot++) {
      const u16 ref = (u16) (sector * STAGE_RECORDS_PER_SECTOR + slot + 1);
      u8 raw[STAGE_RECORD_HEADER_SIZE];
      if(!read_bytes(stage_record_address(ref), raw, sizeof(raw))) break;
      bool erased = true;
      for(u8 i = 0; i < sizeof(raw); i++) if(raw[i] != 0xFF) erased = false;
      if(erased) break;
      g_stage_used[sector] = (u8) (slot + 1);
      if(raw[0] != 'S' || raw[1] != '9') {
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
        stage_insert_index(key, ref);
      } else {
        g_stage_recovery_ok = false;
      }
    }
  }
  if(g_stage_ref_count == 0 && g_stage_recovery_ok) {
    bool released = true;
    for(u16 sector = g_geometry.stage_sector_count;
        sector < g_stage_slot_count; sector++) {
      if(!erase_sector(g_stage_physical[sector])) released = false;
    }
    if(released) g_stage_slot_count = (u8) g_geometry.stage_sector_count;
  }
}

#if defined(PROGRAM_STORE_HOST_TEST)
void test_reset_stage_index_stats(void) {
  g_stage_index_stats = {};
}

StageIndexStats test_stage_index_stats(void) {
  return g_stage_index_stats;
}

u32 test_catalog_root(void) { return g_catalog_root; }
u32 test_catalog_page(u8 page) {
  return page < g_geometry.catalog_table_sectors ? g_catalog_pages[page].sector : EMPTY_ADDRESS;
}
u32 test_catalog_wal_address(u8 record) {
  return record < CATALOG_WAL_RECORDS ? wal_record_address(record) : EMPTY_ADDRESS;
}
u8 test_catalog_wal_records(void) { return g_wal_records; }
u8 test_catalog_wal_capacity(void) { return CATALOG_WAL_RECORDS; }
bool test_catalog_checkpoint(void) { return g_ready && checkpoint(); }
bool test_catalog_protects(u32 sector) { return catalog_sector_busy(sector); }

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

u16 test_current_record_space(void) {
  return data_sector_in_range(g_meta.current_sector) && g_meta.current_offset <= 4096U
      ? (u16) (4096U - g_meta.current_offset) : 0;
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


bool test_relocate_fat_chain(u16 id, u32 sector) {
  Inode inode;
  u16 bytes = 0;
  if(!g_ready || !data_sector_in_range(sector) ||
     sector == g_meta.current_sector || sector == g_meta.reserve_sector ||
     catalog_sector_busy(sector) || borrowed_stage_sector(sector) ||
     !get_inode(id, inode) || inode.fat_address == EMPTY_ADDRESS ||
     !c9_map_size(id, inode, bytes) || !initialize_data_sector(sector)) return false;
  const u32 target = sector_address(sector) + DATA_SECTOR_HEADER_SIZE;
  u8 buffer[64];
  for(u16 offset = 0; offset < bytes;) {
    const u16 count = (u16) ((bytes - offset < sizeof(buffer)) ? bytes - offset : sizeof(buffer));
    if(!read_bytes(inode.fat_address + offset, buffer, count) ||
       !write_bytes(target + offset, buffer, count)) return false;
    offset = (u16) (offset + count);
  }
  inode.fat_address = target;
  Transaction transaction;
  txn_begin(transaction);
  return txn_set(transaction, id, inode) && append_transaction(transaction);
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

bool vfat_stage_snapshot(u32* keys, u16 capacity, u16& count) {
  count = 0;
  if(!g_ready || keys == nullptr || !ensure_stage_index() ||
     capacity < g_stage_ref_count) return false;
  for(u16 index = 0; index < g_stage_ref_count; ++index) {
    keys[index] = stage_index_key(index);
  }
  count = g_stage_ref_count;
  return true;
}

void vfat_stage_forget(u32 start_block, u16 blocks) {
  if(!g_ready || !ensure_stage_index()) return;
  for(u16 offset = 0; offset < blocks; offset++) {
    const int index = stage_ref_index(start_block + offset);
    if(index < 0) continue;
    if(!write_byte(stage_record_address(stage_index_ref((u16) index)) + 2,
                   STATE_DELETED)) continue;
    stage_remove_index((u16) index);
  }
}

bool vfat_stage_discard_unmatched(VfatStageKeyFilter include, void* context) {
  if(!g_ready || g_stage_external || include == nullptr || !ensure_stage_index()) return false;
  u16 index = 0;
  while(index < g_stage_ref_count) {
    if(include(context, stage_index_key(index))) { ++index; continue; }
    if(!write_byte(stage_record_address(stage_index_ref(index)) + 2, STATE_DELETED)) return false;
    stage_remove_index(index);
  }
  return true;
}

bool vfat_stage_discard_all(void) {
  // A narrowed index contains only the current file's blocks. Discarding it
  // would strand other acknowledged host writes while freeing their physical
  // stage sectors. The full index must be restored first.
  if(!g_ready || g_stage_external) return false;
  // Local APP writes need no stage index when its last complete recovery
  // proved the journal empty. USB Screen may now own the same overlay RAM.
  if(g_stage_index == nullptr && g_stage_known_empty) return true;
  if(!ensure_stage_index()) return false;
  while(g_stage_ref_count != 0) {
    const u16 index = (u16) (g_stage_ref_count - 1);
    if(!write_byte(stage_record_address(stage_index_ref(index)) + 2,
                   STATE_DELETED)) return false;
    g_stage_ref_count--;
  }
  for(u16 sector = g_geometry.stage_sector_count;
      sector < g_stage_slot_count; sector++) {
    if(!erase_sector(g_stage_physical[sector])) return false;
  }
  g_stage_slot_count = (u8) g_geometry.stage_sector_count;
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
         g_stage_index_capacity == stage_ref_limit() &&
         g_stage_recovery_ok;
}

void vfat_stage_unlock(void) {
  g_stage_locked = false;
  if(g_stage_external) forget_stage_index_binding();
}

bool vfat_stage_release_cache(void) {
  if(!g_stage_overlay_lease.ok() ||
     prepare_stage_index_eviction() != shared_memory::EvictionDecision::RELEASE) {
    return false;
  }
  g_stage_overlay_lease.reset();
  return true;
}

} // пространство имён program_store
