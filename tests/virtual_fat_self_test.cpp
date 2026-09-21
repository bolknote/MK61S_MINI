#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "SPIFlash.h"
#include "exclusive_buffer.hpp"
#include "ledcontrol.h"
#include "loadable_module_runtime.hpp"
#include "program_store.hpp"
#include "shared_memory.hpp"
#include "virtual_fat.hpp"

SPIFlash flash;
bool flash_is_ok = true;

namespace led {
void init(void) {}
void on(void) {}
void off(void) {}
void blink(usize, t_time_ms, t_time_ms) {}
void blink_continuous(t_time_ms, t_time_ms) {}
void blink_stop(void) {}
bool pattern_start(const PatternStep*, usize) { return true; }
void control(void) {}
void control(t_time_ms) {}
} // пространство имён led

#if MK61_ANY_LOADABLE_MODULE
namespace loadable_module {
StoreStatus validate_app(const ModuleSource& source, Header& header) {
  memset(&header, 0, sizeof(header));
  if(source.read == nullptr || source.size < HEADER_SIZE ||
     source.size > MAX_CONTAINER_SIZE) return StoreStatus::WRONG_FILE_SIZE;
  shared_memory::Lease app_validation_buffer;
  if(!app_validation_buffer.acquire_cache(
       shared_memory::Arena::OVERLAY,
       shared_memory::Owner::LOADABLE_MODULE, APP_MAX_MEMORY_SIZE)) {
    return StoreStatus::UNAVAILABLE;
  }
  u8 marker = 0;
  if(!source.read(source.context, 0, &marker, 1)) {
    return StoreStatus::IO_ERROR;
  }
  if(marker == 0xEE) return StoreStatus::INVALID_HEADER;
  header.kind = Kind::APPLICATION;
  return StoreStatus::OK;
}
} // namespace loadable_module
#endif

namespace {

static u16 read_le16(const u8* data, u16 offset) {
  return (u16) (data[offset] | ((u16) data[offset + 1] << 8));
}

static u32 read_le32(const u8* data, u16 offset) {
  return (u32) data[offset] |
         ((u32) data[offset + 1] << 8) |
         ((u32) data[offset + 2] << 16) |
         ((u32) data[offset + 3] << 24);
}

static void write_le16(u8* data, u16 offset, u16 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
}

static void write_le32(u8* data, u16 offset, u32 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
  data[offset + 2] = (u8) (value >> 16);
  data[offset + 3] = (u8) (value >> 24);
}

struct Layout {
  u8 sectors_per_cluster;
  u16 fat_sectors;
  u16 root_entries;
  u32 root_start;
  u32 root_sectors;
  u32 data_start;
  u32 total_sectors;
};

static Layout layout(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  Layout result = {};
  assert(read_le16(boot, 11) == virtual_fat::SECTOR_SIZE);
  result.sectors_per_cluster = boot[13];
  const u16 reserved = read_le16(boot, 14);
  assert(reserved == 1 && boot[16] == 2);
  result.fat_sectors = read_le16(boot, 22);
  result.root_entries = read_le16(boot, 17);
  result.root_start = reserved + (u32) boot[16] * result.fat_sectors;
  result.root_sectors = ((u32) result.root_entries * 32 + 511) / 512;
  result.data_start = result.root_start + result.root_sectors;
  result.total_sectors = read_le16(boot, 19);
  if(result.total_sectors == 0) result.total_sectors = read_le32(boot, 32);
  return result;
}

static u32 cluster_lba(const Layout& fs, u16 cluster, u8 sector = 0) {
  return fs.data_start + (u32) (cluster - 2) * fs.sectors_per_cluster + sector;
}

static void fresh(u32 capacity = SPIFlash::DEFAULT_CAPACITY) {
  virtual_fat::end_session();
  virtual_fat::clear_diagnostic();
  SPIFlash::reset(capacity);
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
}

static void test_boot_sector_volume_serial_fallback(void) {
  fresh();
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  assert(read_le32(boot, 39) ==
         ((0xC6000000UL ^ SPIFlash::DEFAULT_CAPACITY) ^
          program_store::media_revision()));
}

static void test_volume_serial_tracks_persistent_media_revision(void) {
  fresh();
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  const u32 initial = read_le32(boot, 39);

  // A catalog mutation must not change the identity of an already mounted
  // FAT volume, but the following session must see a new identity.
  static const u8 payload[] = {'o', 'k'};
  u16 id = program_store::INVALID_ID;
  assert(program_store::write_file(
      program_store::ROOT_ID, 60, program_store::ProgramType::TEXT,
      "revision", payload, sizeof(payload), &id));
  assert(virtual_fat::read_sector(0, boot));
  assert(read_le32(boot, 39) == initial);
  assert(virtual_fat::reset_session());
  assert(virtual_fat::read_sector(0, boot));
  const u32 after_catalog = read_le32(boot, 39);
  assert(after_catalog != initial);

  // Even a host sector later rejected or discarded advances the persistent
  // staging generation. This is what invalidates stale macOS directory cache
  // after an interrupted transaction.
  u8 staged[virtual_fat::SECTOR_SIZE] = {};
  assert(program_store::vfat_stage_write(123, staged));
  assert(virtual_fat::read_sector(0, boot));
  assert(read_le32(boot, 39) == after_catalog);
  assert(virtual_fat::reset_session());
  assert(virtual_fat::read_sector(0, boot));
  assert(read_le32(boot, 39) != after_catalog);
}

static void test_session_start_reuses_the_locked_stage_index(void) {
  fresh();
  virtual_fat::end_session();

  // Leave a sizeable deleted journal tail.  Its in-memory index is already
  // authoritative; starting another session must lock and reuse that index,
  // not reread every old record from SPI Flash.
  u8 sector[virtual_fat::SECTOR_SIZE] = {};
  for(u16 index = 0; index < 24; ++index) {
    const u32 key = 100U + index;
    sector[0] = (u8) index;
    assert(program_store::vfat_stage_write(key, sector));
    program_store::vfat_stage_forget(key, 1);
  }
  assert(program_store::vfat_stage_count() == 0);

  SPIFlash::resetOperationCounts();
  assert(virtual_fat::reset_session());
  assert(SPIFlash::readOperations() <= 4U);
}

static u16 fat12_value(u16 cluster) {
  const Layout fs = layout();
  const u32 byte_offset = (u32) cluster + cluster / 2;
  u8 first[512];
  u8 second[512];
  assert(virtual_fat::read_sector(1 + byte_offset / 512, first));
  const u16 offset = (u16) (byte_offset % 512);
  u8 hi = 0;
  if(offset == 511) {
    assert(virtual_fat::read_sector(2 + byte_offset / 512, second));
    hi = second[0];
  } else {
    hi = first[offset + 1];
  }
  const u16 packed = (u16) (first[offset] | ((u16) hi << 8));
  (void) fs;
  return (cluster & 1) == 0 ? (u16) (packed & 0x0FFF)
                             : (u16) (packed >> 4);
}

static void set_fat12_value(u8* fat, u16 cluster, u16 value) {
  const u16 offset = (u16) (cluster + cluster / 2);
  assert(offset + 1 < 512);
  value &= 0x0FFF;
  if((cluster & 1) == 0) {
    fat[offset] = (u8) value;
    fat[offset + 1] = (u8) ((fat[offset + 1] & 0xF0) | (value >> 8));
  } else {
    fat[offset] = (u8) ((fat[offset] & 0x0F) | (value << 4));
    fat[offset + 1] = (u8) (value >> 4);
  }
}

static u8 short_checksum(const u8* name) {
  u8 sum = 0;
  for(u8 i = 0; i < 11; i++) {
    sum = (u8) (((sum & 1) ? 0x80 : 0) + (sum >> 1) + name[i]);
  }
  return sum;
}

static void write_lfn_char(u8* item, u8 index, u16 value) {
  static const u8 offsets[13] = {
    1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30
  };
  write_le16(item, offsets[index], value);
}

static u16 read_lfn_char(const u8* item, u8 index) {
  static const u8 offsets[13] = {
    1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30
  };
  return read_le16(item, offsets[index]);
}

static u8 append_utf16_entry(u8* directory, u8 slot, const u16* name,
                             u8 name_len, const char short_name[11],
                             bool is_directory, u16 cluster, u32 size) {
  const u8 lfn_count = (u8) ((name_len + 12U) / 13U);
  assert(name != nullptr && name_len != 0 && lfn_count <= 8 &&
         slot + lfn_count + 1U < 16U);
  const u8 checksum = short_checksum((const u8*) short_name);
  for(u8 offset = 0; offset < lfn_count; ++offset) {
    const u8 sequence = (u8) (lfn_count - offset);
    u8* lfn = directory + (u16) (slot + offset) * 32U;
    memset(lfn, 0xFF, 32);
    lfn[0] = sequence;
    if(sequence == lfn_count) lfn[0] |= 0x40;
    lfn[11] = 0x0F;
    lfn[12] = 0;
    lfn[13] = checksum;
    write_le16(lfn, 26, 0);
    const u16 base = (u16) (sequence - 1U) * 13U;
    for(u8 index = 0; index < 13; ++index) {
      const u16 source = (u16) (base + index);
      write_lfn_char(lfn, index,
                     source < name_len ? name[source] :
                     source == name_len ? 0 : 0xFFFF);
    }
  }
  u8* item = directory + (u16) (slot + lfn_count) * 32U;
  memset(item, 0, 32);
  memcpy(item, short_name, 11);
  item[11] = is_directory ? 0x10 : 0x20;
  write_le16(item, 26, cluster);
  write_le32(item, 28, size);
  return (u8) (slot + lfn_count + 1U);
}

static u8 append_ascii_entry(u8* directory, u8 slot, const char* name,
                             const char short_name[11], bool is_directory,
                             u16 cluster, u32 size) {
  const usize length = strlen(name);
  assert(length <= 13);
  u16 utf16[13] = {};
  for(usize index = 0; index < length; index++) {
    utf16[index] = (u8) name[index];
  }
  return append_utf16_entry(directory, slot, utf16, (u8) length,
                            short_name, is_directory, cluster, size);
}

#if MK61_ANY_LOADABLE_MODULE
static void append_short_entry(u8* directory, u16 slot,
                               const char short_name[11],
                               bool is_directory, u16 cluster, u32 size) {
  u8* item = directory + (u32) slot * 32U;
  memset(item, 0, 32);
  memcpy(item, short_name, 11);
  item[11] = is_directory ? 0x10 : 0x20;
  write_le16(item, 26, cluster);
  write_le32(item, 28, size);
}
#endif

static void dot_entries(u8* directory, u16 self_cluster,
                        u16 parent_cluster) {
  memset(directory, 0, 512);
  memcpy(directory, ".          ", 11);
  directory[11] = 0x10;
  write_le16(directory, 26, self_cluster);
  memcpy(directory + 32, "..         ", 11);
  directory[32 + 11] = 0x10;
  write_le16(directory + 32, 26, parent_cluster);
}

static int first_free_slot(const u8* directory) {
  for(int slot = 0; slot < 16; slot++) {
    if(directory[slot * 32] == 0) return slot;
  }
  return -1;
}

static void expect_file(u16 id, const u8* expected, u16 expected_len) {
  u8 actual[program_store::MAX_IMAGE1_SIZE] = {};
  u16 actual_len = 0;
  assert(program_store::read_id(id, actual, sizeof(actual), &actual_len));
  assert(actual_len == expected_len);
  assert(memcmp(actual, expected, expected_len) == 0);
}

static void expect_flush(void) {
  const bool ok = virtual_fat::flush_pending();
  if(!ok) {
    char report[virtual_fat::DIAGNOSTIC_LINE_SIZE];
    assert(virtual_fat::format_diagnostic(virtual_fat::diagnostic(), report,
                                          sizeof(report)));
    fprintf(stderr, "VFAT flush failed: %s\n", report);
  }
  assert(ok);
}

static void expect_rejected_pending_recovered(void) {
  const virtual_fat::Diagnostic cause = virtual_fat::diagnostic();
  assert(cause.code != virtual_fat::ErrorCode::NONE);
  assert(program_store::vfat_stage_count() == 0);
  virtual_fat::end_session();
  assert(memcmp(&cause, &virtual_fat::diagnostic(), sizeof(cause)) == 0);
  assert(virtual_fat::reset_session());
  assert(virtual_fat::finalize_pending());
  assert(memcmp(&cause, &virtual_fat::diagnostic(), sizeof(cause)) == 0);
}

static void test_diagnostic_contract(void) {
  using namespace virtual_fat;
  DiagnosticState state = {};
  assert(state.value.code == ErrorCode::NONE);
  assert(!state.fail(ErrorCode::FILE_TOO_LARGE, Phase::ENTRY,
                     7492, 1536, "README"));
  assert(!state.fail(ErrorCode::DIRECTORY_ENTRY, Phase::ENTRY));
  char line[DIAGNOSTIC_LINE_SIZE];
  assert(format_diagnostic(state.value, line, sizeof(line)));
  assert(strcmp(line, "VFAT v=1 code=1221 phase=3 flags=0 actual=7492 limit=1536 subject=524541444D45") == 0);
  char screen[10];
  format_error_code(state.value.code, screen);
  assert(strcmp(screen, "USB E1221") == 0);

  state.begin_attempt();
  assert(state.value.code == ErrorCode::FILE_TOO_LARGE);
  state.fail(ErrorCode::ROOT_READ, Phase::VALIDATE, 0xFEDCBA98, 15, nullptr, true);
  assert(state.value.code == ErrorCode::ROOT_READ);
  assert(state.value.flags == RETRYABLE);
  assert(state.value.subject[0] == 0);
  assert(format_diagnostic(state.value, line, sizeof(line)));
  assert(strcmp(line, "VFAT v=1 code=1233 phase=5 flags=1 actual=4275878552 limit=15 subject=") == 0);
  state.clear();
  assert(state.value.code == ErrorCode::NONE && state.value.flags == 0);
  static const char too_long_m8[] = "123456789012345\306";
  state.fail(ErrorCode::NAME_TOO_LONG, Phase::ENTRY, 20, 15, too_long_m8);
  assert(strcmp(state.value.subject, "123456789012345") == 0);
  assert(state.value.flags == SUBJECT_TRUNCATED);
  state.clear();
  static const char unsafe_m8[] = {'A', '\n', '/', '\\', 0x7F,
                                   (char) 0x98, 0};
  state.fail(ErrorCode::NAME, Phase::ENTRY, 0, 0, unsafe_m8);
  assert(strcmp(state.value.subject, "A?????") == 0);
  state.clear();
  char repeated_m8[17];
  memset(repeated_m8, 0xDF, 16); // Я
  repeated_m8[16] = 0;
  state.fail(ErrorCode::NAME, Phase::ENTRY, UINT32_MAX, UINT32_MAX,
             repeated_m8);
  assert(memcmp(state.value.subject, repeated_m8, 15) == 0 &&
         state.value.subject[15] == 0);
  assert(state.value.flags == SUBJECT_TRUNCATED);
  assert(format_diagnostic(state.value, line, sizeof(line)));
  const usize length = strlen(line);
  // Every insufficient output capacity stays terminated and inside its bound.
  for(usize size = 1; size <= length; ++size) {
    char bounded[DIAGNOSTIC_LINE_SIZE];
    memset(bounded, '#', sizeof(bounded));
    assert(!format_diagnostic(state.value, bounded, size));
    assert(memchr(bounded, 0, size) != nullptr);
    assert(bounded[size] == '#');
  }
  assert(!format_diagnostic(state.value, nullptr, 0));

  const Diagnostic retained = state.value;
  clear_diagnostic();
  assert(diagnostic().code == ErrorCode::NONE);
  restore_diagnostic(retained);
  assert(memcmp(&diagnostic(), &retained, sizeof(retained)) == 0);
}

static void test_dynamic_fat12_bpb(void) {
  const u32 capacities[] = {
    128U * 1024U, 512U * 1024U,
    2U * 1024U * 1024U, 16U * 1024U * 1024U
  };
  for(u32 capacity : capacities) {
    fresh(capacity);
    const Layout fs = layout();
    const storage_geometry::Geometry& geometry = program_store::geometry();
    assert(fs.total_sectors == geometry.logical_sectors);
    assert(fs.sectors_per_cluster == geometry.sectors_per_cluster);
    assert(fs.fat_sectors == geometry.fat_sectors);
    assert(fs.root_entries == geometry.root_entries);
    assert(virtual_fat::sector_count() == geometry.logical_sectors);
    const u32 data_sectors = fs.total_sectors - fs.data_start;
    assert(data_sectors / fs.sectors_per_cluster == geometry.max_nodes);
    assert(geometry.max_nodes < 4085);
    assert(fat12_value(0) == 0xFF8);
    assert(fat12_value(1) == 0xFFF);
  }
}

static void test_macos_no_index_marker(void) {
  fresh();
  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  assert((root[11] & 0x08) != 0);
  assert(root[32] == 0x42 && root[32 + 11] == 0x0F);
  assert(root[64] == 0x01 && root[64 + 11] == 0x0F);
  assert(memcmp(root + 96, "METADATANIX", 11) == 0);
  assert((root[96 + 11] & 0x07) == 0x07);
  assert(read_le16(root + 96, 26) == 0);
  assert(read_le32(root + 96, 28) == 0);

  char name[27] = {};
  for(u8 slot = 1; slot <= 2; slot++) {
    const u8* item = root + (u16) slot * 32;
    const u8 sequence = (u8) (item[0] & 0x1F);
    assert(sequence >= 1 && sequence <= 2);
    for(u8 index = 0; index < 13; index++) {
      const u16 value = read_lfn_char(item, index);
      if(value == 0 || value == 0xFFFF) continue;
      assert(value < 0x80);
      name[(u16) (sequence - 1) * 13 + index] = (char) value;
    }
  }
  assert(strcmp(name, ".metadata_never_index") == 0);
  assert(first_free_slot(root) == storage_geometry::ROOT_SYSTEM_DIRENTS);
}

static void test_stable_clusters_and_nested_reads(void) {
  fresh();
  u16 first_dir = 0;
  u16 second_dir = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, "Projects",
                                         10, &first_dir));
  assert(program_store::create_directory(first_dir, "Games", 11,
                                         &second_dir));
  const u8 payload[] = {'1', '0', ' ', 'P', 'R', 'I', 'N', 'T'};
  u16 file = 0;
  assert(program_store::write_file(second_dir, 12,
                                   program_store::ProgramType::TINYBASIC,
                                   "demo", payload, sizeof(payload), &file));
  assert(virtual_fat::reset_session());
  assert(first_dir == 10 && second_dir == 11 && file == 12);
  assert(fat12_value(12) >= 0xFF8);
  assert(fat12_value(13) >= 0xFF8);
  assert(fat12_value(14) >= 0xFF8);

  const Layout fs = layout();
  u8 sector[512] = {};
  assert(virtual_fat::read_sector(cluster_lba(fs, 14), sector));
  assert(memcmp(sector, payload, sizeof(payload)) == 0);
  for(usize i = sizeof(payload); i < sizeof(sector); i++) assert(sector[i] == 0);

  assert(virtual_fat::read_sector(cluster_lba(fs, 12), sector));
  assert(sector[0] == '.' && sector[32] == '.');
  assert(virtual_fat::read_sector(cluster_lba(fs, 13), sector));
  assert(sector[0] == '.' && sector[32] == '.');
}

static void test_empty_text_file_is_a_persistent_fat_object(void) {
  fresh();
  u16 id = program_store::INVALID_ID;
  assert(program_store::write_file(
      program_store::ROOT_ID, 18, program_store::ProgramType::TEXT,
      "empty", nullptr, 0, &id));
  assert(id == 18);

  // Starting a FAT session must expose, not silently purge, an intentional
  // zero-length file.  Empty text files are useful placeholders and are
  // valid both in C6 and FAT12.
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 root[512] = {};
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 expected_cluster = (u16) (id + 2U);
  const u8* short_entry = nullptr;
  for(u8 slot = 0; slot < 16; ++slot) {
    const u8* item = root + (u16) slot * 32U;
    if(item[11] != 0x0F && read_le16(item, 26) == expected_cluster) {
      short_entry = item;
      break;
    }
  }
  assert(short_entry != nullptr);
  assert(read_le32(short_entry, 28) == 0);

  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready());
  program_store::Entry entry = {};
  assert(program_store::entry_by_id(id, entry));
  assert(entry.type == program_store::ProgramType::TEXT);
  assert(entry.data_len == 0);
}

static void test_m8_text_exports_as_utf16_name_and_utf8_content(void) {
  fresh();
  static const char name_m8[] = {
    (char) 0xCF, (char) 0xF0, (char) 0xE8,
    (char) 0xE2, (char) 0xE5, (char) 0xF2, 0
  }; // Привет
  static const u8 content_m8[] = {
    0xD1, 0xF2, 0xF0, 0xEE, 0xEA, 0xE0, ' ', 0x0F, ' ',
    0xE4, 0xEE, 0xEC, '\n'
  }; // Строка -> дом, где 0x0F — частный символ M8 «->».
  u16 id = program_store::INVALID_ID;
  assert(program_store::write_file(
      program_store::ROOT_ID, 30, program_store::ProgramType::TEXT,
      name_m8, content_m8, sizeof(content_m8), &id));
  assert(id == 30 && virtual_fat::reset_session());

  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u8* short_entry = nullptr;
  u8 short_slot = 0;
  for(u8 slot = 0; slot < 16; slot++) {
    const u8* item = root + (u16) slot * 32U;
    if(item[11] != 0x0F && read_le16(item, 26) == id + 2U) {
      short_entry = item;
      short_slot = slot;
      break;
    }
  }
  assert(short_entry != nullptr && short_slot != 0);
  static const u16 expected_name[] = {
    0x041F, 0x0440, 0x0438, 0x0432, 0x0435, 0x0442,
    '.', 't', 'x', 't'
  };
  const u8* lfn = root + (u16) (short_slot - 1U) * 32U;
  assert(lfn[11] == 0x0F);
  for(u8 index = 0; index < sizeof(expected_name) / sizeof(expected_name[0]);
      index++) {
    assert(read_lfn_char(lfn, index) == expected_name[index]);
  }
  assert(read_lfn_char(lfn, sizeof(expected_name) / sizeof(expected_name[0])) ==
         0);

  static const char expected_utf8[] = u8"Строка → дом\n";
  assert(read_le32(short_entry, 28) == sizeof(expected_utf8) - 1U);
  u8 sector[512] = {};
  assert(virtual_fat::read_sector(cluster_lba(fs, (u16) (id + 2U)),
                                  sector));
  assert(memcmp(sector, expected_utf8, sizeof(expected_utf8) - 1U) == 0);
}

static void test_utf16_name_and_utf8_content_import_as_m8(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 120;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const u16 name_utf16[] = {
    0x0420, 0x0443, 0x0441, 0x0441, 0x043A, 0x0438, 0x0439,
    '.', 't', 'x', 't'
  }; // Русский.txt
  static const char short_name[11] =
      {'R','U','S','S','I','A','~','1','T','X','T'};
  static const char content_utf8[] = u8"Ёжик → дом\n";
  const u8 next = append_utf16_entry(
      root, (u8) first_free_slot(root), name_utf16,
      sizeof(name_utf16) / sizeof(name_utf16[0]), short_name, false,
      file_cluster, sizeof(content_utf8) - 1U);
  root[(u16) next * 32U] = 0;
  u8 data[512] = {};
  memcpy(data, content_utf8, sizeof(content_utf8) - 1U);
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();

  const u16 id = (u16) (file_cluster - 2U);
  program_store::Entry entry = {};
  assert(program_store::entry_by_id(id, entry));
  static const char expected_name_m8[] = {
    (char) 0xD0, (char) 0xF3, (char) 0xF1, (char) 0xF1,
    (char) 0xEA, (char) 0xE8, (char) 0xE9, 0
  };
  assert(strcmp(entry.name, expected_name_m8) == 0);
  static const u8 expected_content_m8[] = {
    0xA8, 0xE6, 0xE8, 0xEA, ' ', 0x0F, ' ', 0xE4, 0xEE, 0xEC, '\n'
  };
  expect_file(id, expected_content_m8, sizeof(expected_content_m8));
}

static void test_russian_lfn_sibling_survives_commit_reboot_and_cleanup(void) {
  fresh();
  static const char check_directory_m8[] = {
    (char) 0xCF, (char) 0xF0, (char) 0xEE, (char) 0xE2,
    (char) 0xE5, (char) 0xF0, (char) 0xEA, (char) 0xE0, 0
  }; // Проверка
  u16 check_directory_id = program_store::INVALID_ID;
  u16 system_directory_id = program_store::INVALID_ID;
  assert(program_store::create_directory(
      program_store::ROOT_ID, check_directory_m8, 60,
      &check_directory_id));
  assert(program_store::create_directory(
      program_store::ROOT_ID, "System", 61, &system_directory_id));
  assert(check_directory_id == 60 && system_directory_id == 61);

  // Exact field regression: C6 had a FILE inode at id 4 whose record name
  // was unreadable and whose sibling link no longer reached the root.  FAT
  // therefore exported cluster 6 as free; macOS reused it for the fixture,
  // while APPLY still interpreted inode 4 as a replacement and failed with
  // NAME_COLLISION/REPLACED_NAME.  A host allocation may reclaim this orphan,
  // but must not disturb either neighbouring root directory.
  static const u8 stale[] = {'o', 'l', 'd'};
  u16 stale_id = program_store::INVALID_ID;
  assert(program_store::write_file(
      program_store::ROOT_ID, 4, program_store::ProgramType::TEXT,
      "stale", stale, sizeof(stale), &stale_id));
  assert(stale_id == 4);
  assert(program_store::test_make_unreadable_orphan_file(stale_id));
  program_store::Entry stale_entry = {};
  assert(!program_store::entry_by_id(stale_id, stale_entry));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  static constexpr u16 FILE_CLUSTER = 6;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, FILE_CLUSTER, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const u16 name_utf16[] = {
    0x041F, 0x0440, 0x043E, 0x0432, 0x0435, 0x0440, 0x043A, 0x0430,
    '-', '7', '6', '2', '3', '.', 't', 'x', 't'
  }; // Проверка-7623.txt
  static const char short_name[11] =
      {'P','R','O','V','E','R','~','1','T','X','T'};
  static const char content_utf8[] =
      u8"Проверка USB AEB505B6E0067623: Ёжик, стрелка →, число 123.\n";
  const u8 next = append_utf16_entry(
      root, (u8) first_free_slot(root), name_utf16,
      sizeof(name_utf16) / sizeof(name_utf16[0]), short_name, false,
      FILE_CLUSTER, sizeof(content_utf8) - 1U);
  root[(u16) next * 32U] = 0;
  u8 data[512] = {};
  memcpy(data, content_utf8, sizeof(content_utf8) - 1U);
  assert(virtual_fat::write_cached_sectors(
      cluster_lba(fs, FILE_CLUSTER), data, 1));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  expect_flush();

  static constexpr u16 FILE_ID = FILE_CLUSTER - 2U;
  program_store::Entry file = {};
  assert(program_store::entry_by_id(FILE_ID, file));
  static const char expected_name_m8[] = {
    (char) 0xCF, (char) 0xF0, (char) 0xEE, (char) 0xE2,
    (char) 0xE5, (char) 0xF0, (char) 0xEA, (char) 0xE0,
    '-', '7', '6', '2', '3', 0
  };
  assert(file.parent_id == program_store::ROOT_ID);
  assert(file.type == program_store::ProgramType::TEXT);
  assert(strcmp(file.name, expected_name_m8) == 0);
  static const u8 expected_content_m8[] = {
    0xCF, 0xF0, 0xEE, 0xE2, 0xE5, 0xF0, 0xEA, 0xE0,
    ' ', 'U', 'S', 'B', ' ', 'A', 'E', 'B', '5', '0', '5', 'B', '6',
    'E', '0', '0', '6', '7', '6', '2', '3', ':', ' ', 0xA8, 0xE6,
    0xE8, 0xEA, ',', ' ', 0xF1, 0xF2, 0xF0, 0xE5, 0xEB, 0xEA, 0xE0,
    ' ', 0x0F, ',', ' ', 0xF7, 0xE8, 0xF1, 0xEB, 0xEE, ' ', '1', '2',
    '3', '.', '\n'
  };
  expect_file(FILE_ID, expected_content_m8, sizeof(expected_content_m8));

  // Reboot and re-export prove that C6 contains the committed M8 object,
  // rather than merely leaving a readable copy in the current FAT overlay.
  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
  assert(program_store::entry_by_id(FILE_ID, file));
  expect_file(FILE_ID, expected_content_m8, sizeof(expected_content_m8));
  assert(virtual_fat::read_sector(fs.root_start, root));
  int short_slot = -1;
  for(u8 slot = 0; slot < 16; ++slot) {
    const u8* item = root + (u16) slot * 32U;
    if(item[11] != 0x0F && read_le16(item, 26) == FILE_CLUSTER) {
      short_slot = slot;
      break;
    }
  }
  assert(short_slot >= 2);
  const u8* lfn_last = root + (u16) (short_slot - 2) * 32U;
  const u8* lfn_first = root + (u16) (short_slot - 1) * 32U;
  assert(lfn_last[0] == 0x42 && lfn_first[0] == 0x01);
  assert(read_lfn_char(lfn_last, 0) == '.' &&
         read_lfn_char(lfn_last, 1) == 't' &&
         read_lfn_char(lfn_last, 2) == 'x' &&
         read_lfn_char(lfn_last, 3) == 't');
  assert(read_lfn_char(lfn_first, 0) == 0x041F);

  // The HIL removes only its reserved fixture.  The similarly named user
  // directory and the System directory must remain untouched.
  virtual_fat::end_session();
  assert(program_store::remove_id(FILE_ID));
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
  assert(!program_store::entry_by_id(FILE_ID, file));
  program_store::Entry directory = {};
  assert(program_store::entry_by_id(check_directory_id, directory));
  assert(directory.kind == program_store::NodeKind::DIRECTORY);
  assert(strcmp(directory.name, check_directory_m8) == 0);
  assert(program_store::entry_by_id(system_directory_id, directory));
  assert(directory.kind == program_store::NodeKind::DIRECTORY);
  assert(strcmp(directory.name, "System") == 0);
}

static void test_m8_utf8_expansion_crosses_sector_boundary(void) {
  fresh();
  u8 source[300];
  memset(source, 0xDF, sizeof(source)); // Я: один байт M8, два байта UTF-8.
  u16 id = program_store::INVALID_ID;
  assert(program_store::write_file(
      program_store::ROOT_ID, 40, program_store::ProgramType::TEXT,
      "wide", source, sizeof(source), &id));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u8* short_entry = nullptr;
  for(u8 slot = 0; slot < 16; slot++) {
    const u8* item = root + (u16) slot * 32U;
    if(item[11] != 0x0F && read_le16(item, 26) == id + 2U) {
      short_entry = item;
      break;
    }
  }
  assert(short_entry != nullptr && read_le32(short_entry, 28) == 600U);
  u8 first[512];
  u8 second[512];
  assert(virtual_fat::read_sector(cluster_lba(fs, (u16) (id + 2U)), first));
  assert(virtual_fat::read_sector(cluster_lba(fs, (u16) (id + 2U), 1),
                                  second));
  for(u16 offset = 0; offset < 600U; offset += 2U) {
    const u8* sector = offset < 512U ? first : second;
    const u16 local = offset < 512U ? offset : (u16) (offset - 512U);
    assert(sector[local] == 0xD0 && sector[local + 1U] == 0xAF);
  }
}

static void test_unrepresentable_utf8_is_rejected_without_tree_damage(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 121;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'E','M','O','J','I',' ',' ',' ','T','X','T'};
  static const u8 invalid_m8_text[] = {
    'o', 'k', ' ', 0xF0, 0x9F, 0x98, 0x80 // U+1F600 is not in M8.
  };
  const u8 next = append_ascii_entry(
      root, (u8) first_free_slot(root), "emoji.txt", short_name, false,
      file_cluster, sizeof(invalid_m8_text));
  root[(u16) next * 32U] = 0;
  u8 data[512] = {};
  memcpy(data, invalid_m8_text, sizeof(invalid_m8_text));
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::finalize_pending());
  assert(virtual_fat::diagnostic().code ==
         virtual_fat::ErrorCode::TEXT_ENCODING);
  assert(program_store::total_count() == 0);
  expect_rejected_pending_recovered();
}

static void test_directory_extents_grow_without_flat_catalog_scan(void) {
  fresh();
  u16 directory = 0;
  assert(program_store::create_directory(program_store::ROOT_ID,
                                         "Large collection", 20, &directory));
  const u8 data = 0x42;
  for(u16 i = 0; i < 30; i++) {
    char name[32];
    snprintf(name, sizeof(name), "long-program-name-%02u", (unsigned) i);
    assert(program_store::write_file(directory, (u16) (100 + i),
                                     program_store::ProgramType::MK61,
                                     name, &data, 1, NULL));
  }
  assert(virtual_fat::reset_session());
  const u16 first_cluster = (u16) (directory + 2);
  const u16 extent_cluster = fat12_value(first_cluster);
  assert(extent_cluster >= 2 && extent_cluster < 0xFF8);
  assert(fat12_value(extent_cluster) >= 0xFF8);
  u16 owner = 0;
  u16 next = 0;
  assert(program_store::extent_info((u16) (extent_cluster - 2), owner, next));
  assert(owner == directory && next == program_store::INVALID_ID);
}

static void test_preallocated_directory_tail_is_canonicalized(void) {
  // macOS may reserve a large FAT chain for a directory even though the first
  // 0x00 entry terminates its live contents in the first cluster. Importing
  // that empty tail as C6 directory extents wastes nearly the entire node
  // table on a 512-KiB device and turns recovery into hundreds of catalog
  // transactions. The committed C6 tree must retain only live directory
  // storage.
  fresh(512U * 1024U);
  const Layout fs = layout();
  const u16 directory_cluster = 20;
  const u16 tail_last_cluster = 170;
  const u16 file_cluster = 180;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  for(u16 cluster = directory_cluster; cluster < tail_last_cluster; ++cluster) {
    set_fat12_value(fat, cluster, (u16) (cluster + 1U));
  }
  set_fat12_value(fat, tail_last_cluster, 0xFFF);
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  int slot = first_free_slot(root);
  assert(slot == storage_geometry::ROOT_SYSTEM_DIRENTS);
  static const char directory_short[11] = {
    'F','O','L','D','E','R','~','1',' ',' ',' '
  };
  slot = append_ascii_entry(root, (u8) slot, "Folder", directory_short,
                            true, directory_cluster, 0);
  root[(u16) slot * 32U] = 0;

  u8 directory[512];
  dot_entries(directory, directory_cluster, 0);
  static const char file_short[11] = {
    'N','O','T','E','~','1',' ',' ','T','X','T'
  };
  static const u8 payload[] = "preallocated directory tail\n";
  slot = append_ascii_entry(directory, 2, "note.txt", file_short, false,
                            file_cluster, sizeof(payload) - 1U);
  directory[(u16) slot * 32U] = 0;
  u8 file_data[512] = {};
  memcpy(file_data, payload, sizeof(payload) - 1U);

  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), file_data));
  assert(virtual_fat::write_sector(cluster_lba(fs, directory_cluster),
                                   directory));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  SPIFlash::resetOperationCounts();
  expect_flush();

  const u16 directory_id = (u16) (directory_cluster - 2U);
  const u16 file_id = (u16) (file_cluster - 2U);
  u16 extent = program_store::INVALID_ID;
  assert(!program_store::first_extent(directory_id, extent));
  expect_file(file_id, payload, sizeof(payload) - 1U);
  assert(program_store::vfat_stage_count() == 0);
  assert(SPIFlash::mutationOperations() < 96U);
  assert(virtual_fat::reset_session());
}

static void test_legacy_preallocated_directory_tail_is_trimmed_in_batches(void) {
  // Model the state left by older firmware after it had already materialized
  // the host's preallocated chain.  Recovery must heal it without performing
  // one WAL transaction for every obsolete extent.
  fresh(512U * 1024U);
  const Layout fs = layout();
  const u16 directory_cluster = 20;
  const u16 tail_last_cluster = 170;
  const u16 file_cluster = 180;
  const u16 directory_id = (u16) (directory_cluster - 2U);
  assert(program_store::create_directory(program_store::ROOT_ID, "Folder",
                                         directory_id, nullptr));
  for(u16 cluster = (u16) (directory_cluster + 1U);
      cluster <= tail_last_cluster; ++cluster) {
    assert(program_store::allocate_directory_extent(
        directory_id, (u16) (cluster - 2U)));
  }

  u16 extent = program_store::INVALID_ID;
  u16 extent_count = 0;
  if(program_store::first_extent(directory_id, extent)) {
    do {
      ++extent_count;
    } while(program_store::next_extent(extent, extent));
  }
  assert(extent_count == tail_last_cluster - directory_cluster);

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);
  u8 directory[512];
  assert(virtual_fat::read_sector(cluster_lba(fs, directory_cluster),
                                  directory));
  static const char file_short[11] = {
    'N','O','T','E','~','1',' ',' ','T','X','T'
  };
  static const u8 payload[] = "repair old directory extents\n";
  const u8 slot = append_ascii_entry(directory, 2, "note.txt", file_short,
                                     false, file_cluster,
                                     sizeof(payload) - 1U);
  directory[(u16) slot * 32U] = 0;
  u8 file_data[512] = {};
  memcpy(file_data, payload, sizeof(payload) - 1U);

  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), file_data));
  assert(virtual_fat::write_sector(cluster_lba(fs, directory_cluster),
                                   directory));
  assert(virtual_fat::write_sector(1, fat));
  SPIFlash::resetOperationCounts();
  expect_flush();

  assert(!program_store::first_extent(directory_id, extent));
  expect_file((u16) (file_cluster - 2U), payload, sizeof(payload) - 1U);
  assert(program_store::vfat_stage_count() == 0);
  assert(SPIFlash::mutationOperations() < 96U);
  assert(virtual_fat::reset_session());
}

static void test_live_file_reuses_legacy_directory_slack(void) {
  // Reproduce an interrupted host transaction in which the new root dirent
  // and file bytes reached the persistent stage, but the FAT update detaching
  // that cluster from an old preallocated directory tail did not.  The first
  // 0x00 in the directory makes the tail allocation slack, so recovery may
  // atomically repurpose its C6 node without losing any live directory data.
  fresh(512U * 1024U);
  const Layout fs = layout();
  const u16 directory_id = 20;
  const u16 slack_id = 42;
  const u16 directory_cluster = (u16) (directory_id + 2U);
  const u16 file_cluster = (u16) (slack_id + 2U);
  assert(program_store::create_directory(program_store::ROOT_ID, "Folder",
                                         directory_id, nullptr));
  assert(program_store::allocate_directory_extent(directory_id, slack_id));
  // Drop sectors cached before the direct C6 setup.  Do not call
  // reset_session(): its normal canonicalization would correctly trim the
  // deliberately constructed legacy slack before the recovery test begins.
  virtual_fat::end_session();
  assert(fat12_value(directory_cluster) == file_cluster);
  assert(fat12_value(file_cluster) >= 0xFF8);
  u8 staged_fat[512];
  assert(virtual_fat::read_sector(1, staged_fat));

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const int free_slot = first_free_slot(root);
  assert(free_slot >= (int) storage_geometry::ROOT_SYSTEM_DIRENTS);
  static const char file_short[11] = {
    'R','E','C','O','V','E','~','1','T','X','T'
  };
  static const u8 payload[] = "recovered directory slack\n";
  const u8 next_slot = append_ascii_entry(
      root, (u8) free_slot, "Recovered.txt", file_short, false,
      file_cluster, sizeof(payload) - 1U);
  root[(u16) next_slot * 32U] = 0;
  u8 file_data[512] = {};
  memcpy(file_data, payload, sizeof(payload) - 1U);

  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), file_data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  // The interrupted host did write its FAT sector, but it still contains the
  // old directory-tail link.  Store that unchanged sector explicitly: the
  // production journal may contain host writes whose final bytes equal the
  // currently exported sector after an earlier catalog mutation.
  assert(program_store::vfat_stage_write(1, staged_fat));
  assert(fat12_value(file_cluster) >= 0xFF8);
  assert(virtual_fat::flush_write_cache());
  virtual_fat::end_session();
  assert(fat12_value(file_cluster) >= 0xFF8);
  expect_flush();

  u16 extent = program_store::INVALID_ID;
  assert(!program_store::first_extent(directory_id, extent));
  expect_file(slack_id, payload, sizeof(payload) - 1U);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::reset_session());
}

static void stage_host_tree(void) {
  const Layout fs = layout();
  const u16 outer_cluster = 102;
  const u16 inner_cluster = 103;
  const u16 file_cluster = 104;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, outer_cluster, 0xFFF);
  set_fat12_value(fat, inner_cluster, 0xFFF);
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  int slot = first_free_slot(root);
  assert(slot == storage_geometry::ROOT_SYSTEM_DIRENTS);
  static const char outer_short[11] = {'M','Y','S','T','U','F','~','1',' ',' ',' '};
  slot = append_ascii_entry(root, (u8) slot, "My Stuff", outer_short, true,
                            outer_cluster, 0);
  root[slot * 32] = 0;

  u8 outer[512];
  dot_entries(outer, outer_cluster, 0);
  static const char inner_short[11] = {'G','A','M','E','S','~','1',' ',' ',' ',' '};
  slot = append_ascii_entry(outer, 2, "Games", inner_short, true,
                            inner_cluster, 0);
  outer[slot * 32] = 0;

  u8 inner[512];
  dot_entries(inner, inner_cluster, outer_cluster);
  static const char file_short[11] = {'N','O','T','E','S','~','1',' ','T','X','T'};
  static const u8 payload[] = "hello from a nested directory\n";
  slot = append_ascii_entry(inner, 2, "notes.txt", file_short, false,
                            file_cluster, sizeof(payload) - 1);
  inner[slot * 32] = 0;

  u8 file_data[512] = {};
  memcpy(file_data, payload, sizeof(payload) - 1);
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, file_cluster),
                                           file_data, 1));
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, inner_cluster),
                                           inner, 1));
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, outer_cluster),
                                           outer, 1));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::dirty_cache_sectors() == 5);
  assert(fat12_value(outer_cluster) == 0xFFF);
  assert(fat12_value(inner_cluster) == 0xFFF);
  assert(fat12_value(file_cluster) == 0xFFF);
}

static void test_host_creates_arbitrary_nested_tree(void) {
  fresh();
  stage_host_tree();
  expect_flush();
  assert(virtual_fat::write_cache_capacity() == 16);
  assert(program_store::vfat_stage_count() == 0);

  program_store::Entry outer;
  program_store::Entry inner;
  program_store::Entry file;
  assert(program_store::entry_by_id(100, outer));
  assert(program_store::entry_by_id(101, inner));
  assert(program_store::entry_by_id(102, file));
  assert(outer.kind == program_store::NodeKind::DIRECTORY);
  assert(inner.kind == program_store::NodeKind::DIRECTORY);
  assert(strcmp(outer.name, "My Stuff") == 0);
  assert(strcmp(inner.name, "Games") == 0);
  assert(outer.parent_id == program_store::ROOT_ID);
  assert(inner.parent_id == outer.id);
  assert(file.parent_id == inner.id);
  assert(file.type == program_store::ProgramType::TEXT);
  assert(strcmp(file.name, "notes") == 0);
  static const u8 payload[] = "hello from a nested directory\n";
  expect_file(file.id, payload, sizeof(payload) - 1);

  program_store::init();
  assert(virtual_fat::reset_session());
  expect_file(file.id, payload, sizeof(payload) - 1);
}

static void test_staged_update_is_recovered_before_next_session(void) {
  fresh();
  const u8 old_data[] = "old";
  u16 id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 50,
                                   program_store::ProgramType::TEXT,
                                   "journal", old_data, sizeof(old_data) - 1,
                                   &id));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 updated[512] = {};
  memcpy(updated, "new", 3);
  assert(virtual_fat::write_sector(cluster_lba(fs, (u16) (id + 2)), updated));
  virtual_fat::end_session();
  program_store::init();
  assert(virtual_fat::reset_session());
  assert(program_store::vfat_stage_count() == 0);
  expect_file(id, (const u8*) "new", 3);
}

static void test_recovery_io_failure_refuses_mount_and_retries(void) {
  fresh();
  const u8 old_data[] = "old";
  u16 id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 50,
                                   program_store::ProgramType::TEXT,
                                   "journal", old_data, sizeof(old_data) - 1,
                                   &id));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 updated[512] = {};
  memcpy(updated, "new", 3);
  assert(virtual_fat::write_sector(cluster_lba(fs, (u16) (id + 2)), updated));
  virtual_fat::end_session();
  program_store::init();

  // A real media failure must never expose the staged overlay as a mounted
  // volume or throw it away. The normal USB caller closes this failed session;
  // a later attempt retries the same durable journal.
  SPIFlash::failAfterOperations(0);
  assert(!virtual_fat::reset_session());
  assert((virtual_fat::diagnostic().flags & virtual_fat::RETRYABLE) != 0);
  assert(program_store::vfat_stage_count() != 0);
  SPIFlash::clearFailure();
  virtual_fat::end_session();
  program_store::init();
  assert(virtual_fat::reset_session());
  assert(program_store::vfat_stage_count() == 0);
  expect_file(id, (const u8*) "new", 3);
}

static void test_full_staging_rejects_next_sector_without_tree_damage(void) {
  fresh(16U * 1024U * 1024U);
  static const u8 old_data[] = {'s', 'a', 'f', 'e'};
  u16 old_id = 0;
  assert(program_store::write_file(
      program_store::ROOT_ID, 60, program_store::ProgramType::TEXT,
      "keep-me", old_data, sizeof(old_data), &old_id));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  const u32 first = cluster_lba(fs, 500);
  static constexpr u16 CAPACITY = 384;
  assert(first + CAPACITY < fs.total_sectors);
  u8 data[512] = {};
  for(u16 index = 0; index < CAPACITY; index++) {
    memset(data, 0, sizeof(data));
    data[0] = (u8) (index + 1U);
    data[1] = (u8) (index >> 8);
    data[2] = 0x5A;
    assert(virtual_fat::write_sector(first + index, data));
  }
  assert(program_store::vfat_stage_count() == CAPACITY);
  memset(data, 0xA5, sizeof(data));
  assert(!virtual_fat::write_sector(first + CAPACITY, data));
  assert(program_store::vfat_stage_count() == CAPACITY);

  // Не подтверждённый 385-й сектор остаётся только в исчезающем RAM-кэше.
  // После reboot журнал первых 384 секторов цел, но новый сеанс сначала
  // согласует его с основным деревом. Неиспользуемые данные отбрасываются до
  // того, как новый host увидит FAT, поэтому они не становятся фантомами.
  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
  assert(program_store::vfat_stage_count() == 0);
  expect_file(old_id, old_data, sizeof(old_data));
}

static void test_identical_data_writes_do_not_restage(void) {
  fresh();
  const Layout fs = layout();
  const u32 lba = cluster_lba(fs, 200);
  u8 data[512] = {};

  // Нераспределённый кластер данных читается как ноль и не требует физической
  // записи в журнале, когда хост избыточно заполняет его нулями.
  assert(virtual_fat::write_sector(lba, data));
  assert(program_store::vfat_stage_count() == 0);

  data[17] = 0x5A;
  assert(virtual_fat::write_sector(lba, data));
  assert(program_store::vfat_stage_count() == 1);
  const u64 programmed = SPIFlash::programmedBytes();
  assert(virtual_fat::write_sector(lba, data));
  assert(program_store::vfat_stage_count() == 1);
  assert(SPIFlash::programmedBytes() == programmed);
}

static void test_write_cache_coalesces_and_evicts_lru(void) {
  fresh();
  const Layout fs = layout();
  assert(virtual_fat::write_cache_capacity() == 16);
  const u32 first_lba = cluster_lba(fs, 300);
  u8 data[512] = {};
  u8 readback[512] = {};

  data[9] = 1;
  assert(virtual_fat::write_cached_sectors(first_lba, data, 1));
  data[9] = 2;
  assert(virtual_fat::write_cached_sectors(first_lba, data, 1));
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::dirty_cache_sectors() == 1);
  assert(virtual_fat::read_sector(first_lba, readback));
  assert(memcmp(readback, data, sizeof(data)) == 0);

  // Возврат к постоянному нулевому блоку полностью отменяет грязную запись.
  memset(data, 0, sizeof(data));
  assert(virtual_fat::write_cached_sectors(first_lba, data, 1));
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == 0);

  // Заполняем каждую ячейку отдельным грязным сектором. Следующий промах сохраняет
  // только сектор LRU; остальные записи до синхронизации можно объединять в ОЗУ.
  const u8 capacity = virtual_fat::write_cache_capacity();
  for(u8 i = 0; i < capacity; i++) {
    memset(data, 0, sizeof(data));
    data[0] = (u8) (i + 1);
    assert(virtual_fat::write_cached_sectors(first_lba + i, data, 1));
  }
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 0);

  memset(data, 0, sizeof(data));
  data[0] = 0xA5;
  assert(virtual_fat::write_cached_sectors(first_lba + capacity, data, 1));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 1);
  assert(virtual_fat::flush_write_cache());
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == (u16) capacity + 1);
}

static void test_fast_usb_cache_is_atomic_and_defers_spi(void) {
  fresh();
  const Layout fs = layout();
  const u32 first_lba = cluster_lba(fs, 600);
  u8 zero[512] = {};
  u8 readback[512] = {};

  // Безопасный для прерываний путь не читает даже заполненный нулями базовый сектор.
  // Синхронизация выполняет отложенное сравнение и избегает промежуточной записи.
  assert(virtual_fat::try_write_cached_sectors(first_lba, zero, 1));
  assert(virtual_fat::dirty_cache_sectors() == 1);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::read_sector(first_lba, readback));
  assert(memcmp(readback, zero, sizeof(zero)) == 0);
  assert(virtual_fat::flush_write_cache());
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == 0);

  fresh();
  const Layout fresh_fs = layout();
  const u32 packet_lba = cluster_lba(fresh_fs, 600);
  const u8 capacity = virtual_fat::write_cache_capacity();
  assert(capacity == 16);
  u8 packet[16 * 512] = {};
  for(u8 index = 0; index < capacity; index++) {
    packet[(u32) index * 512] = (u8) (index + 1);
  }
  assert(virtual_fat::try_write_cached_sectors(packet_lba, packet, capacity));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 0);

  // Полный кэш не может синхронно принять ещё один ключ. При отказе весь пакет
  // остаётся нетронутым, после чего обычный путь может сохранить одну жертву LRU
  // и продолжить без потери пакета BOT.
  u8 extra[512] = {0xA5};
  assert(!virtual_fat::try_write_cached_sectors(packet_lba + capacity,
                                                extra, 1));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::read_sector(packet_lba + capacity - 1, readback));
  assert(readback[0] == capacity);

  // Перезапись находящегося в кэше ключа не требует SPI и остаётся на быстром пути.
  u8 replacement[512] = {0x5A};
  assert(virtual_fat::try_write_cached_sectors(packet_lba + capacity - 1,
                                               replacement, 1));
  assert(virtual_fat::read_sector(packet_lba + capacity - 1, readback));
  assert(memcmp(readback, replacement, sizeof(replacement)) == 0);
  assert(program_store::vfat_stage_count() == 0);

  assert(virtual_fat::write_cached_sectors(packet_lba + capacity, extra, 1));
  assert(virtual_fat::dirty_cache_sectors() == capacity);
  assert(program_store::vfat_stage_count() == 1);
  assert(virtual_fat::flush_write_cache());
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(program_store::vfat_stage_count() == (u16) capacity + 1);

  // Предварительная проверка также резервирует чистый ключ, адресованный позднее
  // в том же пакете; она не должна менять этот сектор до решения отложить весь пакет.
  fresh();
  const Layout reserved_fs = layout();
  const u32 reserved_lba = cluster_lba(reserved_fs, 700);
  assert(virtual_fat::write_cached_sectors(reserved_lba + 15, zero, 1));
  assert(virtual_fat::dirty_cache_sectors() == 0);
  for(u8 index = 0; index < 15; index++) {
    extra[0] = (u8) (index + 1);
    assert(virtual_fat::try_write_cached_sectors(reserved_lba + index,
                                                 extra, 1));
  }
  u8 two_sectors[2 * 512] = {};
  two_sectors[0] = 0xC1;
  two_sectors[512] = 0xC2;
  assert(!virtual_fat::try_write_cached_sectors(reserved_lba + 15,
                                                two_sectors, 2));
  assert(virtual_fat::dirty_cache_sectors() == 15);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::read_sector(reserved_lba + 15, readback));
  assert(readback[0] == 0);
  assert(virtual_fat::read_sector(reserved_lba + 16, readback));
  assert(readback[0] == 0);
}

static void test_optional_display_cache_span(void) {
  fresh();
  virtual_fat::end_session();
  alignas(4) static u8 display_cache[8192];
  assert(virtual_fat::set_external_cache(display_cache,
                                         sizeof(display_cache)));
  assert(virtual_fat::reset_session());
  assert(virtual_fat::write_cache_capacity() == 32);

  const Layout fs = layout();
  const u32 first_lba = cluster_lba(fs, 500);
  u8 data[512] = {};
  for(u8 i = 0; i < virtual_fat::write_cache_capacity(); i++) {
    data[0] = (u8) (i + 1);
    assert(virtual_fat::write_cached_sectors(first_lba + i, data, 1));
  }
  assert(virtual_fat::dirty_cache_sectors() == 32);
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::flush_pending());
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::dirty_cache_sectors() == 0);
  assert(virtual_fat::write_cache_capacity() == 32);
}

static void test_metadata_only_recovery_does_not_redecode_unchanged_text(void) {
  fresh();
  static u8 source[program_store::MAX_TINYBASIC_TEXT_SIZE];
  for(u16 index = 0; index < sizeof(source); index++) {
    source[index] = (u8) (index % 41U == 40U ? '\n' : 'A' + index % 7U);
  }
  u16 id = program_store::INVALID_ID;
  assert(program_store::write_file(
      program_store::ROOT_ID, 80, program_store::ProgramType::TINYBASIC,
      "large-source", source, sizeof(source), &id));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(fs.root_start, root));
  virtual_fat::end_session();

  // Model the harmless root-directory sector which macOS commonly leaves in
  // the durable journal.  Recovery must verify the FAT mapping, but it must
  // not stream-decode every byte of an unchanged compressed source again.
  assert(program_store::vfat_stage_write(fs.root_start, root));
  assert(program_store::vfat_stage_count() == 1);
  alignas(4) static u8 display_cache[8192];
  assert(virtual_fat::set_external_cache(display_cache,
                                         sizeof(display_cache)));
  SPIFlash::resetOperationCounts();
  assert(virtual_fat::reset_session());
  assert(SPIFlash::readOperations() <= 256U);
  assert(program_store::vfat_stage_count() == 0);
  static u8 restored[program_store::MAX_TINYBASIC_TEXT_SIZE];
  u16 restored_size = 0;
  assert(program_store::read_id(id, restored, sizeof(restored),
                                &restored_size));
  assert(restored_size == sizeof(source));
  assert(memcmp(restored, source, sizeof(source)) == 0);
}

static void run_usb_commit_zx0_workspace_test(usize external_size,
                                               bool managed_bulk = false) {
  fresh();
  alignas(4) static u8 display_cache[8192];
  u8* external_data = display_cache;
  if(external_size != 0) {
    assert(external_size <= sizeof(display_cache));
    virtual_fat::end_session();
    if(managed_bulk) {
      assert(external_size == exclusive_buffer::SIZE);
      assert(exclusive_buffer::acquire(
          exclusive_buffer::Owner::USB_CACHE, external_size));
      external_data = exclusive_buffer::data(
          exclusive_buffer::Owner::USB_CACHE);
      assert(external_data != nullptr);
    }
    assert(virtual_fat::set_external_cache(external_data,
                                           external_size));
    assert(virtual_fat::reset_session());
  }
  const Layout fs = layout();
  const u16 file_cluster = 222;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);

  static u8 payload[1400];
  for(u16 index = 0; index < sizeof(payload); index++) {
    payload[index] = (u8) ("USB ZX0 commit workspace\n"[index % 25U]);
  }
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'P','A','C','K','E','D',' ',' ','T','X','T'};
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "packed.txt", short_name,
      false, file_cluster, sizeof(payload));
  root[(u16) slot * 32U] = 0;

  u8 sectors[3 * 512] = {};
  memcpy(sectors, payload, sizeof(payload));
  assert(virtual_fat::write_cached_sectors(
      cluster_lba(fs, file_cluster), sectors, 3));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  expect_flush();
  const usize external_slots = external_size / virtual_fat::SECTOR_SIZE;
  assert(virtual_fat::write_cache_capacity() ==
         16U + (external_slots > 16U ? 16U : external_slots));

  program_store::Entry entry = {};
  assert(program_store::entry_by_id((u16) (file_cluster - 2U), entry));
  assert(entry.type == program_store::ProgramType::TEXT);
  u16 stored_len = 0;
  bool large = true;
  bool zx0 = false;
  assert(program_store::test_file_storage_info(
      entry.id, stored_len, large, zx0));
  assert(zx0 && !large && stored_len + 64U <= sizeof(payload));
  expect_file(entry.id, payload, sizeof(payload));

  u8 readback[3 * 512] = {};
  assert(virtual_fat::read_sectors(
      cluster_lba(fs, file_cluster), readback, 3));
  assert(memcmp(readback, sectors, sizeof(readback)) == 0);
  if(managed_bulk) {
    virtual_fat::end_session();
    exclusive_buffer::release(exclusive_buffer::Owner::USB_CACHE);
  }
}

static void test_usb_commit_uses_available_cache_for_zx0(void) {
  // LCD1602: только primary cache. UC1609: внешний display buffer
  // временно отдаётся компрессору. F401 предоставляет ровно три сектора,
  // F411 — шестнадцать; оба размера должны проходить один путь фиксации.
  run_usb_commit_zx0_workspace_test(0);
  run_usb_commit_zx0_workspace_test(1536);
  run_usb_commit_zx0_workspace_test(8192);
#if MK61_EXCLUSIVE_BUFFER_ENABLED
  run_usb_commit_zx0_workspace_test(exclusive_buffer::SIZE, true);
#endif
}

static void test_host_deletes_file_via_directory(void) {
  fresh();
  const u8 data[] = {'x'};
  u16 id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 60,
                                   program_store::ProgramType::MK61,
                                   "delete-me", data, 1, &id));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 user_offset = storage_geometry::ROOT_SYSTEM_DIRENTS * 32U;
  memset(root + user_offset, 0, 512 - user_offset);
  assert(virtual_fat::write_sector(fs.root_start, root));
  expect_flush();
  program_store::Entry removed;
  assert(!program_store::entry_by_id(id, removed));
  assert(program_store::total_count() == 0);
}

static void test_incomplete_file_preflight_preserves_existing_tree(void) {
  fresh();
  static const u8 old_data[] = {0x41, 0x42, 0x43};
  u16 old_id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 60,
                                   program_store::ProgramType::TEXT,
                                   "keep-me", old_data, sizeof(old_data),
                                   &old_id));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  const u16 new_cluster = 220;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, new_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 user_offset = storage_geometry::ROOT_SYSTEM_DIRENTS * 32U;
  memset(root + user_offset, 0, sizeof(root) - user_offset);
  static const char short_name[11] =
      {'N','E','W',' ',' ',' ',' ',' ','T','X','T'};
  const u8 slot = append_ascii_entry(
      root, storage_geometry::ROOT_SYSTEM_DIRENTS, "new.txt",
      short_name, false, new_cluster, 1);
  root[(u16) slot * 32U] = 0;

  // Хост успел записать FAT и каталог, но data sector ещё не пришёл.
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(virtual_fat::flush_pending_result() ==
         virtual_fat::CommitResult::REJECTED);
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::FILE_DATA);
  assert(virtual_fat::diagnostic().phase == virtual_fat::Phase::VALIDATE);
  assert(virtual_fat::diagnostic().actual == cluster_lba(fs, new_cluster));
  assert(virtual_fat::diagnostic().limit == 0);
  assert(strcmp(virtual_fat::diagnostic().subject, "new") == 0);
  assert(program_store::vfat_stage_count() != 0);

  program_store::Entry kept = {};
  assert(program_store::entry_by_id(old_id, kept));
  assert(strcmp(kept.name, "keep-me") == 0);
  expect_file(old_id, old_data, sizeof(old_data));
  program_store::Entry rejected = {};
  assert(!program_store::entry_by_id((u16) (new_cluster - 2U), rejected));
  assert(virtual_fat::finalize_pending_result() ==
         virtual_fat::CommitResult::REJECTED);
  expect_rejected_pending_recovered();
}

static void test_flush_result_distinguishes_media_failure(void) {
  fresh();
  const Layout fs = layout();
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  root[511] ^= 0x5A;
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  SPIFlash::failAfterOperations(0);
  assert(virtual_fat::flush_pending_result() ==
         virtual_fat::CommitResult::IO_FAILED);
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::CACHE_WRITE);
  assert(virtual_fat::diagnostic().phase == virtual_fat::Phase::CACHE);
  assert((virtual_fat::diagnostic().flags & virtual_fat::RETRYABLE) != 0);
  SPIFlash::clearFailure();
}

static void test_finder_appledouble_does_not_abort_batch(void) {
  fresh();
  const Layout fs = layout();
  const u16 sidecar_cluster = 202;
  const u16 file_cluster = 203;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, sidecar_cluster, 0xFFF);
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  u8 slot = (u8) first_free_slot(root);
  static const char sidecar_short[11] =
      {'_','G','A','M','E','~','1',' ','M','6','1'};
  slot = append_ascii_entry(root, slot, "._game.m61", sidecar_short,
                            false, sidecar_cluster, 4096);
  static const char file_short[11] =
      {'G','A','M','E',' ',' ',' ',' ','M','6','1'};
  static const u8 payload[] = {'1', '2', '3'};
  slot = append_ascii_entry(root, slot, "game.m61", file_short,
                            false, file_cluster, sizeof(payload));
  root[slot * 32] = 0;

  u8 data[512] = {};
  memcpy(data, payload, sizeof(payload));
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();

  program_store::Entry file;
  assert(program_store::entry_by_id((u16) (file_cluster - 2), file));
  assert(strcmp(file.name, "game") == 0);
  expect_file(file.id, payload, sizeof(payload));
  program_store::Entry ignored;
  assert(!program_store::entry_by_id((u16) (sidecar_cluster - 2), ignored));
}

static void test_wbmp_import_uses_its_full_quota(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 220;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const int free_slot = first_free_slot(root);
  assert(free_slot == storage_geometry::ROOT_SYSTEM_DIRENTS);
  static const char short_name[11] =
      {'S','C','R','E','E','N',' ',' ','W','B','M'};
  const u8 slot = append_ascii_entry(root, (u8) free_slot,
                                     "screen.wbmp", short_name, false,
                                     file_cluster,
                                     program_store::MAX_IMAGE1_SIZE);
  root[slot * 32] = 0;

  u8 clusters[4 * 512] = {};
  for(u16 i = 0; i < program_store::MAX_IMAGE1_SIZE; i++) {
    clusters[i] = (u8) (i * 37U + 11U);
  }
  assert(virtual_fat::write_cached_sectors(cluster_lba(fs, file_cluster),
                                           clusters, 4));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  expect_flush();

  program_store::Entry image;
  assert(program_store::entry_by_id((u16) (file_cluster - 2), image));
  assert(image.type == program_store::ProgramType::IMAGE1);
  assert(strcmp(image.name, "screen") == 0);
  assert(image.data_len == program_store::MAX_IMAGE1_SIZE);
  expect_file(image.id, clusters, program_store::MAX_IMAGE1_SIZE);
}

static void test_markdown_import_keeps_t2_type(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 220;

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'R','E','A','D','M','E',' ',' ','M','D',' '};
  static const u8 payload[] = "# Read me\n\n**Markdown**\n";
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "readme.md", short_name,
      false, file_cluster, sizeof(payload) - 1U);
  root[(u16) slot * 32U] = 0;

  u8 data[512] = {};
  memcpy(data, payload, sizeof(payload) - 1U);
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();

  program_store::Entry entry = {};
  assert(program_store::entry_by_id((u16) (file_cluster - 2U), entry));
  assert(entry.type == program_store::ProgramType::MARKDOWN);
  assert(strcmp(entry.name, "readme") == 0);
  expect_file(entry.id, payload, sizeof(payload) - 1U);

  assert(virtual_fat::reset_session());
  assert(program_store::count(program_store::ProgramType::MARKDOWN) == 1);
}

static void test_wbmp_over_quota_is_rejected(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 220;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'T','O','O','L','A','R','G','E','W','B','M'};
  const u8 slot = append_ascii_entry(
    root, (u8) first_free_slot(root), "large.wbmp", short_name, false,
    file_cluster, (u32) program_store::MAX_IMAGE1_SIZE + 1U);
  root[slot * 32] = 0;
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::finalize_pending());
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::FILE_TOO_LARGE);
  assert(virtual_fat::diagnostic().actual == 1601);
  assert(virtual_fat::diagnostic().limit == 1600);
  assert(strcmp(virtual_fat::diagnostic().subject, "large") == 0);
  assert(program_store::total_count() == 0);
  expect_rejected_pending_recovered();
}

static void test_markdown_over_quota_does_not_poison_next_session(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 220;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'R','E','A','D','M','E',' ',' ','M','D',' '};
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "README.md", short_name, false,
      file_cluster, 7492U);
  root[slot * 32] = 0;
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::flush_pending());
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::FILE_TOO_LARGE);
  assert(virtual_fat::diagnostic().actual == 7492);
  assert(virtual_fat::diagnostic().limit ==
         (u32) program_store::MAX_MK61_TEXT_SIZE * 3U);
  assert(strcmp(virtual_fat::diagnostic().subject, "README") == 0);
  assert(program_store::total_count() == 0);
  assert(program_store::vfat_stage_count() != 0);

  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
  assert(program_store::vfat_stage_count() == 0);
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::FILE_TOO_LARGE);

  // A real successful import, unlike a no-op sync, retires the old error.
  write_le32(root + (u16) (slot - 1) * 32, 28, 1);
  u8 data[512] = {'#'};
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::NONE);
}

static void test_wbmp_short_name_alias(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 220;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  u8* const item = root + first_free_slot(root) * 32;
  memset(item, 0, 32);
  memcpy(item, "SCREEN  WBM", 11);
  item[11] = 0x20;
  write_le16(item, 26, file_cluster);
  write_le32(item, 28, 4);
  item[32] = 0;
  const u8 payload[512] = {0x00, 0x00, 0x08, 0x00};
  assert(virtual_fat::write_sector(cluster_lba(fs, file_cluster), payload));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();
  program_store::Entry image;
  assert(program_store::entry_by_id((u16) (file_cluster - 2), image));
  assert(image.type == program_store::ProgramType::IMAGE1);
  assert(strcmp(image.name, "SCREEN") == 0);
}

static void expect_large_file(u16 id, const std::vector<u8>& expected);

static void test_chip8_import_uses_full_quota_and_large_zx0(void) {
  fresh();
  virtual_fat::end_session();
  alignas(4) static u8 display_cache[8192];
  assert(virtual_fat::set_external_cache(display_cache,
                                         sizeof(display_cache)));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  const u16 file_cluster = 221;
  const u8 cluster_count = (u8) (
      (program_store::MAX_CHIP8_SIZE +
       (u32) fs.sectors_per_cluster * virtual_fat::SECTOR_SIZE - 1U) /
      ((u32) fs.sectors_per_cluster * virtual_fat::SECTOR_SIZE));
  assert(cluster_count >= 1);

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  for(u8 index = 0; index < cluster_count; index++) {
    set_fat12_value(
        fat, (u16) (file_cluster + index),
        index + 1U < cluster_count
            ? (u16) (file_cluster + index + 1U) : 0xFFF);
  }

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'F','U','S','E',' ',' ',' ',' ','C','H','8'};
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "fuse.ch8", short_name, false,
      file_cluster, program_store::MAX_CHIP8_SIZE);
  root[slot * 32] = 0;

  std::vector<u8> rom(program_store::MAX_CHIP8_SIZE);
  u32 state = 0x27182818UL;
  for(usize block = 0; block < rom.size() / 256U; block++) {
    const usize base = block * 256U;
    for(usize index = 0; index < 160; index++) {
      state ^= state << 13;
      state ^= state >> 17;
      state ^= state << 5;
      rom[base + index] = (u8) state;
    }
    memcpy(rom.data() + base + 160, rom.data() + base, 96);
  }
  assert(virtual_fat::write_cached_sectors(
      cluster_lba(fs, file_cluster), rom.data(),
      (u16) (rom.size() / virtual_fat::SECTOR_SIZE)));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  expect_flush();

  program_store::Entry entry = {};
  assert(program_store::entry_by_id((u16) (file_cluster - 2), entry));
  assert(entry.type == program_store::ProgramType::CHIP8);
  assert(strcmp(entry.name, "fuse") == 0);
  assert(entry.data_len == program_store::MAX_CHIP8_SIZE);
  u16 stored_len = 0;
  bool large = false;
  bool zx0 = false;
  assert(program_store::test_file_storage_info(
      entry.id, stored_len, large, zx0));
  assert(zx0 && large);
  assert(stored_len > program_store::MAX_IMAGE1_SIZE);
  assert(stored_len + 64U <= rom.size());
  expect_large_file(entry.id, rom);
}

static void test_chip8_over_quota_is_rejected(void) {
  fresh();
  const Layout fs = layout();
  const u16 file_cluster = 221;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, file_cluster, 0xFFF);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'L','A','R','G','E',' ',' ',' ','C','H','8'};
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "large.ch8", short_name, false,
      file_cluster, (u32) program_store::MAX_CHIP8_SIZE + 1U);
  root[slot * 32] = 0;
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::finalize_pending());
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::FILE_TOO_LARGE);
  assert(virtual_fat::diagnostic().actual == 3585);
  assert(virtual_fat::diagnostic().limit == 3584);
  assert(program_store::total_count() == 0);
  expect_rejected_pending_recovered();
}

static void test_f411_large_font_import_is_streamed(void) {
  if(program_store::MAX_FONT_SIZE <= program_store::MAX_IMAGE1_SIZE) return;
  fresh();
  virtual_fat::end_session();
  alignas(4) static u8 display_cache[8192];
  assert(virtual_fat::set_external_cache(display_cache,
                                         sizeof(display_cache)));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  const u16 first_cluster = 225;
  const u32 size = program_store::MAX_FONT_SIZE;
  const u32 cluster_size =
      (u32) fs.sectors_per_cluster * virtual_fat::SECTOR_SIZE;
  const u8 cluster_count = (u8) ((size + cluster_size - 1U) / cluster_size);

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  for(u8 index = 0; index < cluster_count; ++index) {
    set_fat12_value(
        fat, (u16) (first_cluster + index),
        index + 1U < cluster_count
            ? (u16) (first_cluster + index + 1U) : 0xFFF);
  }

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'U','I','1','6',' ',' ',' ',' ','F','M','K'};
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "UI16.FMK", short_name, false,
      first_cluster, size);
  root[slot * 32] = 0;

  std::vector<u8> expected(size);
  u32 state = 0x1602F411UL;
  for(u32 offset = 0; offset < size; ++offset) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    expected[offset] = (u8) state;
  }
  assert(virtual_fat::write_cached_sectors(
      cluster_lba(fs, first_cluster), expected.data(),
      (u16) (expected.size() / virtual_fat::SECTOR_SIZE)));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  expect_flush();

  const u16 id = (u16) (first_cluster - 2U);
  program_store::Entry font = {};
  assert(program_store::entry_by_id(id, font));
  assert(font.type == program_store::ProgramType::FONT);
  assert(strcmp(font.name, "UI16") == 0);
  assert(font.data_len == size);
  expect_large_file(id, expected);
}

static void expect_large_file(u16 id, const std::vector<u8>& expected) {
  std::vector<u8> actual(expected.size());
  u16 length = 0;
  assert(program_store::read_id(id, actual.data(), (u16) actual.size(),
                                &length));
  assert(length == expected.size());
  assert(actual == expected);
}

static void run_app_import_across_fat_chain(u32 capacity,
                                            u8 expected_cluster_sectors,
                                            u8 expected_cluster_count) {
  fresh(capacity);
  const Layout fs = layout();
  assert(fs.sectors_per_cluster == expected_cluster_sectors);
  const u16 first_cluster = 20;
  const u32 size = program_store::MAX_APP_FILE_SIZE;
  const u8 cluster_count = (u8) (
      (size + (u32) fs.sectors_per_cluster * 512U - 1U) /
      ((u32) fs.sectors_per_cluster * 512U));
  assert(cluster_count == expected_cluster_count);
  assert(cluster_count <=
         program_store::MAX_FAT_EXTENTS_PER_FILE + 1U);

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  for(u8 index = 0; index < cluster_count; index++) {
    set_fat12_value(fat, (u16) (first_cluster + index),
                    index + 1U < cluster_count
                        ? (u16) (first_cluster + index + 1U) : 0xFFF);
  }

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'F','O','C','A','L',' ',' ',' ','A','P','P'};
  const u8 next_slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "FOCAL.APP", short_name, false,
      first_cluster, size);
  root[next_slot * 32] = 0;

  std::vector<u8> expected(size);
  for(u32 offset = 0; offset < size; offset++) {
    expected[offset] = (u8) (offset * 29U + (offset >> 7) + 3U);
  }
  const u16 sectors = (u16) ((size + 511U) / 512U);
  // Данные намеренно приходят в обратном порядке, а FAT и каталог — последними.
  for(u16 logical = sectors; logical != 0;) {
    logical--;
    const u8 cluster_index =
        (u8) (logical / fs.sectors_per_cluster);
    const u8 sector = (u8) (logical % fs.sectors_per_cluster);
    u8 block[512] = {};
    const u32 offset = (u32) logical * sizeof(block);
    const u16 count = (u16) ((size - offset < sizeof(block))
        ? size - offset : sizeof(block));
    memcpy(block, expected.data() + offset, count);
    assert(virtual_fat::write_sector(
        cluster_lba(fs, (u16) (first_cluster + cluster_index), sector),
        block));
  }
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();

  const u16 id = (u16) (first_cluster - 2U);
  program_store::Entry app = {};
  assert(program_store::entry_by_id(id, app));
  assert(app.type == program_store::ProgramType::APP);
  assert(strcmp(app.name, "FOCAL") == 0);
  expect_large_file(id, expected);
  for(u8 index = 0; index < cluster_count; index++) {
    assert(fat12_value((u16) (first_cluster + index)) ==
           (index + 1U < cluster_count
                ? (u16) (first_cluster + index + 1U) : 0xFFF));
  }

  // Хост переписал только один сектор существующей цепочки. Остальные сектора
  // должны браться из C5, а не считаться потерянными из-за отсутствия в staging.
  static constexpr u16 changed_sector = 17;
  u8 replacement[512];
  memcpy(replacement, expected.data() + (u32) changed_sector * 512U,
         sizeof(replacement));
  for(u16 index = 0; index < sizeof(replacement); index++) {
    replacement[index] ^= 0x5A;
  }
  const u8 changed_cluster =
      (u8) (changed_sector / fs.sectors_per_cluster);
  const u8 in_cluster =
      (u8) (changed_sector % fs.sectors_per_cluster);
  assert(virtual_fat::write_sector(
      cluster_lba(fs, (u16) (first_cluster + changed_cluster), in_cluster),
      replacement));
  memcpy(expected.data() + (u32) changed_sector * 512U,
         replacement, sizeof(replacement));
  expect_flush();
  expect_large_file(id, expected);
}

static void test_app_import_is_streamed_across_fat_chain(void) {
  run_app_import_across_fat_chain(512U * 1024U, 4, 11);
  run_app_import_across_fat_chain(16U * 1024U * 1024U, 8, 6);
}

#if MK61_ANY_LOADABLE_MODULE
static void test_invalid_app_preflight_preserves_existing_tree(void) {
  fresh();
  static const u8 old_data[] = {0x11, 0x22, 0x33};
  u16 old_id = 0;
  assert(program_store::write_file(program_store::ROOT_ID, 60,
                                   program_store::ProgramType::MK61,
                                   "keep-me", old_data, sizeof(old_data),
                                   &old_id));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  const u16 app_cluster = 220;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, app_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 user_offset = storage_geometry::ROOT_SYSTEM_DIRENTS * 32U;
  memset(root + user_offset, 0, sizeof(root) - user_offset);
  static const char short_name[11] =
      {'B','R','O','K','E','N',' ',' ','A','P','P'};
  const u8 slot = append_ascii_entry(
      root, storage_geometry::ROOT_SYSTEM_DIRENTS, "BROKEN.APP",
      short_name, false, app_cluster, loadable_module::HEADER_SIZE);
  root[(u16) slot * 32U] = 0;

  u8 invalid[512] = {0xEE};
  assert(virtual_fat::write_sector(cluster_lba(fs, app_cluster), invalid));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::finalize_pending());
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::APP_INVALID);
  assert(virtual_fat::diagnostic().actual ==
         (u32) loadable_module::StoreStatus::INVALID_HEADER);

  program_store::Entry kept = {};
  assert(program_store::entry_by_id(old_id, kept));
  assert(strcmp(kept.name, "keep-me") == 0);
  expect_file(old_id, old_data, sizeof(old_data));
  program_store::Entry rejected = {};
  assert(!program_store::entry_by_id((u16) (app_cluster - 2U), rejected));
  expect_rejected_pending_recovered();
}

static void test_unchanged_invalid_app_does_not_block_other_files(void) {
  fresh();
  u8 old_app[loadable_module::HEADER_SIZE] = {0xEE};
  u16 old_id = 0;
  assert(program_store::write_file(
      program_store::ROOT_ID, 60, program_store::ProgramType::APP,
      "old-firmware", old_app, sizeof(old_app), &old_id));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  const u16 text_cluster = 220;
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, text_cluster, 0xFFF);

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] =
      {'N','O','T','E',' ',' ',' ',' ','T','X','T'};
  const u8 slot = append_ascii_entry(
      root, (u8) first_free_slot(root), "note.txt", short_name,
      false, text_cluster, 3);
  root[(u16) slot * 32U] = 0;
  u8 data[512] = {'n', 'e', 'w'};
  assert(virtual_fat::write_sector(cluster_lba(fs, text_cluster), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  expect_flush();

  // Старый APP остаётся видимым и может быть удалён/заменён отдельно, но его
  // несовместимость не превращает весь C5 в недоступный для записи том.
  expect_file(old_id, old_app, sizeof(old_app));
  expect_file((u16) (text_cluster - 2U), data, 3);
}

static constexpr u16 BATCH_DIRECTORY_CLUSTER = 20;
static constexpr u16 BATCH_FIRST_APP_CLUSTER = 40;
static constexpr u16 BATCH_APP_SIZE = loadable_module::HEADER_SIZE;

static void batch_app_name(u16 index, char name[7],
                           char short_name[11]) {
  snprintf(name, 7, "APP%03u", (unsigned) index);
  memset(short_name, ' ', 11);
  memcpy(short_name, name, 6);
  memcpy(short_name + 8, "APP", 3);
}

static void batch_app_payload(u16 index, u8 data[512]) {
  memset(data, 0, 512);
  for(u16 offset = 0; offset < BATCH_APP_SIZE; offset++) {
    data[offset] = (u8) (index * 31U + offset * 7U + 1U);
  }
  assert(data[0] != 0xEE);
}

static void stage_app_batch(u16 count) {
  assert(count != 0 && count <= 25);
  const Layout fs = layout();
  assert(fs.sectors_per_cluster == 8);

  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, BATCH_DIRECTORY_CLUSTER, 0xFFF);
  for(u16 index = 0; index < count; index++) {
    set_fat12_value(fat, (u16) (BATCH_FIRST_APP_CLUSTER + index), 0xFFF);
  }

  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u8 root_slot = (u8) first_free_slot(root);
  static const char system_short[11] =
      {'S','Y','S','T','E','M',' ',' ',' ',' ',' '};
  const u8 root_end = append_ascii_entry(
      root, root_slot, "System", system_short, true,
      BATCH_DIRECTORY_CLUSTER, 0);
  root[(u16) root_end * 32U] = 0;

  u8 directory[8U * 512U] = {};
  dot_entries(directory, BATCH_DIRECTORY_CLUSTER, 0);
  for(u16 index = 0; index < count; index++) {
    char name[7];
    char short_name[11];
    batch_app_name(index, name, short_name);
    append_short_entry(directory, (u16) (2U + index), short_name, false,
                       (u16) (BATCH_FIRST_APP_CLUSTER + index),
                       BATCH_APP_SIZE);

    u8 data[512];
    batch_app_payload(index, data);
    assert(virtual_fat::write_cached_sectors(
        cluster_lba(fs, (u16) (BATCH_FIRST_APP_CLUSTER + index)), data, 1));
  }
  directory[(u32) (2U + count) * 32U] = 0;
  assert(virtual_fat::write_cached_sectors(
      cluster_lba(fs, BATCH_DIRECTORY_CLUSTER), directory,
      fs.sectors_per_cluster));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
}

static void expect_app_batch(u16 count) {
  assert(program_store::count(program_store::ProgramType::APP) == count);
  program_store::Entry system = {};
  assert(program_store::entry_by_id(
      (u16) (BATCH_DIRECTORY_CLUSTER - 2U), system));
  assert(system.kind == program_store::NodeKind::DIRECTORY);
  assert(strcmp(system.name, "System") == 0);
  for(u16 index = 0; index < count; index++) {
    const u16 id =
        (u16) (BATCH_FIRST_APP_CLUSTER + index - 2U);
    char name[7];
    char short_name[11];
    batch_app_name(index, name, short_name);
    program_store::Entry app = {};
    assert(program_store::entry_by_id(id, app));
    assert(app.parent_id == system.id);
    assert(app.type == program_store::ProgramType::APP);
    assert(strcmp(app.name, name) == 0);
    u8 expected[512];
    batch_app_payload(index, expected);
    expect_file(id, expected, BATCH_APP_SIZE);
  }
}

static constexpr u16 REPURPOSED_APP_ID = 42;
static constexpr u16 REPURPOSED_OLD_SIZE = 4097;

static u16 stage_repurposed_app_extent(void) {
  fresh(16U * 1024U * 1024U);
  static u8 original[REPURPOSED_OLD_SIZE];
  for(u16 offset = 0; offset < sizeof(original); offset++) {
    original[offset] = (u8) (offset * 17U + 3U);
  }
  assert(original[0] != 0xEE);
  assert(program_store::write_file(
      program_store::ROOT_ID, REPURPOSED_APP_ID,
      program_store::ProgramType::APP, "OLDAPP",
      original, sizeof(original)));
  u16 released_id = 0;
  assert(program_store::first_file_extent(
      REPURPOSED_APP_ID, released_id));
  u16 extra = 0;
  assert(!program_store::next_file_extent(released_id, extra));
  assert(virtual_fat::reset_session());

  const Layout fs = layout();
  const u16 old_cluster = (u16) (REPURPOSED_APP_ID + 2U);
  const u16 new_cluster = (u16) (released_id + 2U);
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, old_cluster, 0xFFF);
  set_fat12_value(fat, new_cluster, 0xFFF);

  // Новый APP намеренно расположен раньше уменьшаемого старого APP. APPLY не
  // может полагаться на порядок записей каталога для освобождения extent.
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 user_offset = storage_geometry::ROOT_SYSTEM_DIRENTS * 32U;
  memset(root + user_offset, 0, sizeof(root) - user_offset);
  static const char new_short[11] =
      {'N','E','W','A','P','P',' ',' ','A','P','P'};
  u8 slot = append_ascii_entry(
      root, storage_geometry::ROOT_SYSTEM_DIRENTS, "NEWAPP.APP",
      new_short, false, new_cluster, BATCH_APP_SIZE);
  static const char old_short[11] =
      {'O','L','D','A','P','P',' ',' ','A','P','P'};
  slot = append_ascii_entry(
      root, slot, "OLDAPP.APP", old_short, false,
      old_cluster, BATCH_APP_SIZE);
  root[(u16) slot * 32U] = 0;

  u8 new_data[512];
  batch_app_payload(77, new_data);
  assert(virtual_fat::write_cached_sectors(
      cluster_lba(fs, new_cluster), new_data, 1));
  assert(virtual_fat::write_cached_sectors(fs.root_start, root, 1));
  assert(virtual_fat::write_cached_sectors(1, fat, 1));
  return released_id;
}

static void expect_repurposed_app_extent(u16 released_id) {
  assert(program_store::count(program_store::ProgramType::APP) == 2);
  program_store::Entry old_app = {};
  assert(program_store::entry_by_id(REPURPOSED_APP_ID, old_app));
  assert(strcmp(old_app.name, "OLDAPP") == 0);
  assert(old_app.data_len == BATCH_APP_SIZE);
  u16 extent = 0;
  assert(!program_store::first_file_extent(REPURPOSED_APP_ID, extent));

  program_store::Entry new_app = {};
  assert(program_store::entry_by_id(released_id, new_app));
  assert(strcmp(new_app.name, "NEWAPP") == 0);
  assert(new_app.type == program_store::ProgramType::APP);
  u8 expected[512];
  batch_app_payload(77, expected);
  expect_file(released_id, expected, BATCH_APP_SIZE);
}

static void test_repurposed_app_extent_power_cuts_are_recoverable(void) {
  const u16 released_id = stage_repurposed_app_extent();
  assert(virtual_fat::flush_write_cache());
  SPIFlash::resetOperationCounts();
  expect_flush();
  const u32 operation_count = SPIFlash::mutationOperations();
  assert(operation_count > 12U);
  expect_repurposed_app_extent(released_id);

  for(u32 cut = 0; cut <= operation_count; cut++) {
    const u16 current_released = stage_repurposed_app_extent();
    assert(current_released == released_id);
    assert(virtual_fat::flush_write_cache());
    SPIFlash::resetOperationCounts();
    SPIFlash::failAfterOperations((i32) cut);
    (void) virtual_fat::finalize_pending();
    SPIFlash::clearFailure();

    virtual_fat::end_session();
    program_store::init();
    assert(program_store::ready());
    assert(virtual_fat::reset_session());
    if(program_store::vfat_stage_count() != 0) expect_flush();
    expect_repurposed_app_extent(released_id);
    assert(program_store::vfat_stage_count() == 0);
  }
}

static void test_many_apps_are_imported_in_one_batch(void) {
  fresh(16U * 1024U * 1024U);
  stage_app_batch(25);
  expect_flush();
  expect_app_batch(25);

  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready());
  assert(virtual_fat::reset_session());
  expect_app_batch(25);
}

static u32 app_batch_commit_operation_count(u16 count) {
  fresh(16U * 1024U * 1024U);
  stage_app_batch(count);
  assert(virtual_fat::flush_write_cache());
  SPIFlash::resetOperationCounts();
  expect_flush();
  return SPIFlash::mutationOperations();
}

static void test_app_batch_power_cuts_are_recoverable(void) {
  static constexpr u16 COUNT = 3;
  const u32 operation_count = app_batch_commit_operation_count(COUNT);
  assert(operation_count > 12U);

  for(u32 cut = 0; cut <= operation_count; cut++) {
    fresh(16U * 1024U * 1024U);
    stage_app_batch(COUNT);
    assert(virtual_fat::flush_write_cache());
    SPIFlash::resetOperationCounts();
    SPIFlash::failAfterOperations((i32) cut);
    (void) virtual_fat::finalize_pending();
    SPIFlash::clearFailure();

    virtual_fat::end_session();
    program_store::init();
    assert(program_store::ready());
    assert(virtual_fat::reset_session());
    if(program_store::vfat_stage_count() != 0) expect_flush();
    expect_app_batch(COUNT);
    assert(program_store::vfat_stage_count() == 0);
  }
}
#endif

static void test_malformed_fat_chain_is_rejected_atomically(void) {
  fresh();
  const Layout fs = layout();
  u8 fat[512];
  assert(virtual_fat::read_sector(1, fat));
  set_fat12_value(fat, 202, 202);
  u8 root[512];
  assert(virtual_fat::read_sector(fs.root_start, root));
  static const char short_name[11] = {'B','R','O','K','E','N','~','1','T','X','T'};
  const int free_slot = first_free_slot(root);
  assert(free_slot == storage_geometry::ROOT_SYSTEM_DIRENTS);
  const u8 slot = append_ascii_entry(root, (u8) free_slot,
                                     "broken.txt", short_name,
                                     false, 202, 1);
  root[slot * 32] = 0;
  u8 data[512] = {0xAA};
  assert(virtual_fat::write_sector(cluster_lba(fs, 202), data));
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::write_sector(1, fat));
  assert(!virtual_fat::finalize_pending());
  assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::FILE_CHAIN);
  assert(virtual_fat::diagnostic().phase == virtual_fat::Phase::CHAIN);
  assert(virtual_fat::diagnostic().actual == 202);
  assert(virtual_fat::diagnostic().limit == 202);
  assert(program_store::total_count() == 0);
  expect_rejected_pending_recovered();
}

} // безымянное пространство имён

#include "vfat_mutation_cases.hpp"

int main(void) {
  test_diagnostic_contract();
  test_boot_sector_volume_serial_fallback();
  test_volume_serial_tracks_persistent_media_revision();
  test_session_start_reuses_the_locked_stage_index();
  test_dynamic_fat12_bpb();
  test_macos_no_index_marker();
  test_stable_clusters_and_nested_reads();
  test_empty_text_file_is_a_persistent_fat_object();
  test_m8_text_exports_as_utf16_name_and_utf8_content();
  test_utf16_name_and_utf8_content_import_as_m8();
  test_russian_lfn_sibling_survives_commit_reboot_and_cleanup();
  test_m8_utf8_expansion_crosses_sector_boundary();
  test_unrepresentable_utf8_is_rejected_without_tree_damage();
  test_directory_extents_grow_without_flat_catalog_scan();
  test_preallocated_directory_tail_is_canonicalized();
  test_legacy_preallocated_directory_tail_is_trimmed_in_batches();
  test_live_file_reuses_legacy_directory_slack();
  test_host_creates_arbitrary_nested_tree();
  test_staged_update_is_recovered_before_next_session();
  test_recovery_io_failure_refuses_mount_and_retries();
  test_full_staging_rejects_next_sector_without_tree_damage();
  test_identical_data_writes_do_not_restage();
  test_write_cache_coalesces_and_evicts_lru();
  test_fast_usb_cache_is_atomic_and_defers_spi();
  test_optional_display_cache_span();
  test_metadata_only_recovery_does_not_redecode_unchanged_text();
  test_usb_commit_uses_available_cache_for_zx0();
  test_host_deletes_file_via_directory();
  test_incomplete_file_preflight_preserves_existing_tree();
  test_flush_result_distinguishes_media_failure();
  test_finder_appledouble_does_not_abort_batch();
  test_markdown_import_keeps_t2_type();
  test_wbmp_import_uses_its_full_quota();
  test_wbmp_over_quota_is_rejected();
  test_markdown_over_quota_does_not_poison_next_session();
  test_wbmp_short_name_alias();
  test_chip8_import_uses_full_quota_and_large_zx0();
  test_chip8_over_quota_is_rejected();
  test_f411_large_font_import_is_streamed();
  test_app_import_is_streamed_across_fat_chain();
#if MK61_ANY_LOADABLE_MODULE
  test_invalid_app_preflight_preserves_existing_tree();
  test_unchanged_invalid_app_does_not_block_other_files();
  test_repurposed_app_extent_power_cuts_are_recoverable();
  test_many_apps_are_imported_in_one_batch();
  test_app_batch_power_cuts_are_recoverable();
#endif
  test_malformed_fat_chain_is_rejected_atomically();
  test_bounded_vfat_mutations();
  virtual_fat::end_session();
  printf("virtual_fat_self_test: ok\n");
  return 0;
}
