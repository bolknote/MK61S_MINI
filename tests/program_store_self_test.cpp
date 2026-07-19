#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "SPIFlash.h"
#include "ledcontrol.h"
#include "program_store.hpp"
#include "storage_path.hpp"

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
} // namespace led

namespace {

using program_store::Entry;
using program_store::NodeKind;
using program_store::ProgramType;

static void fresh(u32 capacity = SPIFlash::DEFAULT_CAPACITY) {
  SPIFlash::reset(capacity);
  program_store::init();
  assert(program_store::ready());
}

static void put_le32(u8* data, u16 offset, u32 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
  data[offset + 2] = (u8) (value >> 16);
  data[offset + 3] = (u8) (value >> 24);
}

static u32 crc32_bytes(const u8* data, usize len) {
  u32 crc = 0xFFFFFFFFUL;
  for(usize index = 0; index < len; index++) {
    crc ^= data[index];
    for(u8 bit = 0; bit < 8; bit++) {
      crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320UL : crc >> 1;
    }
  }
  return crc;
}

static u32 locator_crc(u8* locator) {
  const u8 state = locator[5];
  u8 stored_crc[4];
  memcpy(stored_crc, locator + 68, sizeof(stored_crc));
  locator[5] = 0xFF;
  memset(locator + 68, 0, sizeof(stored_crc));
  const u32 crc = ~crc32_bytes(locator, 72);
  locator[5] = state;
  memcpy(locator + 68, stored_crc, sizeof(stored_crc));
  return crc;
}

static void expect_text(u16 id, const u8* expected, u16 expected_len) {
  u8 actual[program_store::MAX_MK61_TEXT_SIZE] = {};
  u16 actual_len = 0;
  assert(program_store::read_id(id, actual, sizeof(actual), &actual_len));
  assert(actual_len == expected_len);
  assert(memcmp(actual, expected, expected_len) == 0);
}

static void expect_text(const char* name, const char* expected) {
  u8 actual[128] = {};
  u16 actual_len = 0;
  assert(program_store::read(ProgramType::TEXT, name, actual, sizeof(actual),
                             &actual_len));
  assert(actual_len == strlen(expected));
  assert(memcmp(actual, expected, actual_len) == 0);
}

static Entry by_id(u16 id) {
  Entry result = {};
  assert(program_store::entry_by_id(id, result));
  return result;
}

static void test_dynamic_geometry_and_lazy_format(void) {
  const u32 capacities[] = {
    128U * 1024U, 256U * 1024U, 512U * 1024U,
    1024U * 1024U,
    2U * 1024U * 1024U, 8U * 1024U * 1024U,
    16U * 1024U * 1024U
  };
  u16 previous_nodes = 0;
  for(u32 capacity : capacities) {
    fresh(capacity);
    const storage_geometry::Geometry& geometry = program_store::geometry();
    assert(geometry.capacity_bytes == capacity);
    assert(geometry.physical_sectors == capacity / SPIFlash::SECTOR_SIZE);
    assert(geometry.settings_sector + 1 == geometry.physical_sectors);
    assert(program_store::settings_address() ==
           geometry.settings_sector * SPIFlash::SECTOR_SIZE);
    assert(program_store::max_nodes() == geometry.max_nodes);
    assert(geometry.max_nodes >= previous_nodes);
    assert(geometry.max_nodes <= storage_geometry::FAT12_MAX_DATA_CLUSTERS);
    assert(SPIFlash::sectorEraseCount(geometry.data_first_sector) == 0);
    previous_nodes = geometry.max_nodes;
  }
  assert(previous_nodes > 3000);
}

static void test_roundtrip_ranges_and_noop(void) {
  fresh();
  u8 source[program_store::MAX_MK61_TEXT_SIZE];
  for(u16 i = 0; i < sizeof(source); i++) source[i] = (u8) (i * 37U + 11U);

  u16 id = program_store::INVALID_ID;
  assert(program_store::write_file(program_store::ROOT_ID, 71,
                                   ProgramType::TEXT, "payload", source,
                                   sizeof(source), &id));
  assert(id == 71);
  expect_text(id, source, sizeof(source));

  u8 range[337] = {};
  u16 range_len = 0;
  assert(program_store::read_range_id(id, 419, range, sizeof(range),
                                      &range_len));
  assert(range_len == sizeof(range));
  assert(memcmp(range, source + 419, sizeof(range)) == 0);

  const u32 erases = SPIFlash::eraseCount();
  const u64 programmed = SPIFlash::programmedBytes();
  assert(program_store::write_file(program_store::ROOT_ID, id,
                                   ProgramType::TEXT, "payload", source,
                                   sizeof(source), &id));
  assert(SPIFlash::eraseCount() == erases);
  assert(SPIFlash::programmedBytes() == programmed);

  program_store::init();
  assert(program_store::ready());
  expect_text(id, source, sizeof(source));
}

static void test_arbitrary_nested_directories(void) {
  fresh();
  u16 projects = 0;
  u16 archive = 0;
  u16 nested = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, "Projects",
                                         40, &projects));
  assert(program_store::create_directory(program_store::ROOT_ID, "_Archive",
                                         41, &archive));
  assert(program_store::create_directory(projects, "2026.07", 42, &nested));
  assert(projects == 40 && archive == 41 && nested == 42);

  const u8 first[] = {1, 2, 3};
  const u8 second[] = {9, 8, 7, 6};
  u16 first_id = 0;
  u16 second_id = 0;
  assert(program_store::write_file(nested, 43, ProgramType::MK61, "demo",
                                   first, sizeof(first), &first_id));
  assert(program_store::write_file(archive, 44, ProgramType::MK61, "demo",
                                   second, sizeof(second), &second_id));
  assert(first_id == 43 && second_id == 44);
  expect_text(first_id, first, sizeof(first));
  expect_text(second_id, second, sizeof(second));

  Entry directory = by_id(nested);
  assert(directory.kind == NodeKind::DIRECTORY);
  assert(directory.parent_id == projects);
  assert(strcmp(directory.name, "2026.07") == 0);
  assert(program_store::child_count(program_store::ROOT_ID) == 2);
  assert(program_store::child_count(projects) == 1);
  assert(program_store::child_count(nested) == 1);

  assert(!program_store::move_rename(projects, nested, "cycle"));
  assert(program_store::move_rename(first_id, archive, "moved demo"));
  Entry moved = by_id(first_id);
  assert(moved.id == first_id && moved.parent_id == archive);
  assert(strcmp(moved.name, "moved demo") == 0);
  expect_text(first_id, first, sizeof(first));

  assert(!program_store::remove_id(archive));
  assert(program_store::remove_id(nested));
  assert(program_store::remove_id(projects));
  assert(program_store::remove_id(first_id));
  assert(program_store::remove_id(second_id));
  assert(program_store::remove_id(archive));
  assert(program_store::total_count() == 0);

  program_store::init();
  assert(program_store::total_count() == 0);
}

static void test_paths_and_recursive_tree_operations(void) {
  fresh();
  u16 projects = program_store::INVALID_ID;
  u16 year = program_store::INVALID_ID;
  u16 archive = program_store::INVALID_ID;
  assert(program_store::create_directory(program_store::ROOT_ID, "Projects",
                                         20, &projects));
  assert(program_store::create_directory(projects, "2026 Work", 21, &year));
  assert(program_store::create_directory(program_store::ROOT_ID, "Archive",
                                         22, &archive));
  const u8 data[] = {1, 2, 3};
  u16 m61 = program_store::INVALID_ID;
  u16 focal = program_store::INVALID_ID;
  assert(program_store::write_file(year, 23, ProgramType::MK61, "Demo",
                                   data, sizeof(data), &m61));
  assert(program_store::write_file(year, 24, ProgramType::FOCAL, "Demo",
                                   data, sizeof(data), &focal));

  u16 directory = program_store::INVALID_ID;
  assert(storage_path::resolve_directory(program_store::ROOT_ID,
      "'/projects/2026 Work'", directory) == storage_path::Status::OK);
  assert(directory == year);
  assert(storage_path::resolve_directory(year, ".././2026 Work/", directory) ==
         storage_path::Status::OK);
  assert(directory == year);

  Entry entry = {};
  assert(storage_path::resolve_file(program_store::ROOT_ID,
      "/PROJECTS/2026 Work/demo.m61", entry) == storage_path::Status::OK);
  assert(entry.id == m61);
  assert(storage_path::resolve_file(year, "Demo", entry) ==
         storage_path::Status::AMBIGUOUS);
  assert(storage_path::resolve_file(year, "demo",
      ProgramType::FOCAL, entry) == storage_path::Status::OK);
  assert(entry.id == focal);
  assert(storage_path::resolve_file(year, "demo.m61",
      ProgramType::FOCAL, entry) == storage_path::Status::WRONG_TYPE);

  storage_path::FileTarget target = {};
  assert(storage_path::file_target(year, "../new program.m61",
      ProgramType::MK61, target) == storage_path::Status::OK);
  assert(target.parent_id == projects);
  assert(target.type == ProgramType::MK61);
  assert(strcmp(target.name, "new program") == 0);
  assert(storage_path::file_target(year, "bad.foc", ProgramType::MK61,
      target) == storage_path::Status::WRONG_TYPE);

  char path[128];
  assert(storage_path::format_directory(year, path, sizeof(path)) ==
         storage_path::Status::OK);
  assert(strcmp(path, "/Projects/2026 Work") == 0);
  entry = by_id(m61);
  assert(storage_path::format_entry(entry, path, sizeof(path)) ==
         storage_path::Status::OK);
  assert(strcmp(path, "/Projects/2026 Work/Demo.m61") == 0);

  u16 parent = program_store::INVALID_ID;
  char name[program_store::NAME_SIZE];
  assert(storage_path::move_target(year, entry, "/Archive", parent, name,
                                   sizeof(name)) == storage_path::Status::OK);
  assert(parent == archive && strcmp(name, "Demo") == 0);
  assert(storage_path::move_target(year, entry, "../Renamed.m61", parent,
                                   name, sizeof(name)) ==
         storage_path::Status::OK);
  assert(parent == projects && strcmp(name, "Renamed") == 0);
  assert(storage_path::directory_within(year, projects));
  assert(!storage_path::directory_within(archive, projects));

  u16 created = program_store::INVALID_ID;
  assert(storage_path::create_directory(program_store::ROOT_ID,
      "/Generated/Deep/Leaf", true, created) == storage_path::Status::OK);
  assert(storage_path::resolve_directory(program_store::ROOT_ID,
      "/generated/deep/leaf", directory) == storage_path::Status::OK);
  assert(directory == created);
  assert(storage_path::create_directory(program_store::ROOT_ID,
      "/Generated/Missing/Nope", false, directory) ==
      storage_path::Status::NOT_FOUND);
  assert(storage_path::create_directory(program_store::ROOT_ID,
      "/", true, directory) == storage_path::Status::OK);
  assert(directory == program_store::ROOT_ID);

  assert(storage_path::move_target(year, entry,
      "/Projects/2026 Work/Demo.foc", parent, name, sizeof(name)) ==
      storage_path::Status::EXISTS);

  u16 generated = program_store::INVALID_ID;
  assert(storage_path::resolve_directory(program_store::ROOT_ID,
      "/Generated", generated) == storage_path::Status::OK);
  u16 removed = 0;
  assert(program_store::remove_tree(generated, &removed));
  assert(removed == 3);
  assert(program_store::remove_tree(projects, &removed));
  assert(removed == 4); // two directories and two files
  assert(!program_store::entry_by_id(projects, entry));
  assert(program_store::child_count(program_store::ROOT_ID) == 1);
  program_store::init();
  assert(program_store::child_count(program_store::ROOT_ID) == 1);
  assert(by_id(archive).kind == NodeKind::DIRECTORY);
}

static void test_directory_depth_limit_includes_moved_subtrees(void) {
  fresh();
  u16 subtree = program_store::INVALID_ID;
  u16 leaf = program_store::INVALID_ID;
  assert(program_store::create_directory(program_store::ROOT_ID, "subtree",
                                         program_store::INVALID_ID, &subtree));
  assert(program_store::create_directory(subtree, "leaf",
                                         program_store::INVALID_ID, &leaf));

  u16 parent = program_store::ROOT_ID;
  u16 chain[program_store::MAX_DIRECTORY_DEPTH - 1] = {};
  for(u8 depth = 0; depth < sizeof(chain) / sizeof(chain[0]); depth++) {
    char name[8];
    snprintf(name, sizeof(name), "d%02u", (unsigned) depth + 1);
    assert(program_store::create_directory(parent, name,
                                           program_store::INVALID_ID,
                                           &chain[depth]));
    parent = chain[depth];
  }

  // The subtree has height one.  Placing its root at depth 32 would put its
  // leaf at depth 33 and must therefore fail atomically.
  assert(!program_store::move_rename(subtree, chain[30], "too deep"));
  assert(by_id(subtree).parent_id == program_store::ROOT_ID);
  assert(by_id(leaf).parent_id == subtree);

  // Depths 31 and 32 are representable by the FAT walker.
  assert(program_store::move_rename(subtree, chain[29], "fits"));
  assert(by_id(subtree).parent_id == chain[29]);
  assert(by_id(leaf).parent_id == subtree);
  assert(program_store::move_rename(leaf, subtree, "renamed leaf"));

  u16 rejected = program_store::INVALID_ID;
  assert(!program_store::create_directory(leaf, "level 33",
                                          program_store::INVALID_ID,
                                          &rejected));
  assert(rejected == program_store::INVALID_ID);
}

static void test_names_and_exact_preferred_ids(void) {
  fresh();
  const char max_name[] = "1234567890123456789012345678901";
  static_assert(sizeof(max_name) == program_store::NAME_SIZE,
                "fixture must exercise the 31-byte C5 name limit");
  u16 id = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, max_name,
                                         123, &id));
  assert(id == 123);
  assert(strcmp(by_id(id).name, max_name) == 0);
  assert(!program_store::create_directory(program_store::ROOT_ID,
      "12345678901234567890123456789012", 124, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                          "bad:name", 124, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                          "trailing.", 124, NULL));
  const char invalid_utf8[] = {(char) 0xC0, (char) 0xAF, 0};
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                          invalid_utf8, 124, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                          "CON", 124, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                          "lpt9.log", 124, NULL));

  u16 case_id = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, "Case",
                                         125, &case_id));
  assert(!program_store::create_directory(program_store::ROOT_ID, "case",
                                          126, NULL));
  assert(program_store::move_rename(case_id, program_store::ROOT_ID, "case"));
  assert(strcmp(by_id(case_id).name, "case") == 0);
  assert(program_store::create_directory(program_store::ROOT_ID,
                                          "Каталог", 126, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                           "каталог", 130, NULL));
  Entry unicode = {};
  assert(storage_path::resolve_entry(program_store::ROOT_ID,
                                     "/каталог", unicode) ==
         storage_path::Status::OK);
  assert(unicode.id == 126);
  assert(program_store::create_directory(program_store::ROOT_ID,
                                          "Ёлка", 130, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                           "ёлка", 131, NULL));

  u16 suffix_directory = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, "demo.m61",
                                         127, &suffix_directory));

  const u8 value = 0x5A;
  assert(!program_store::write_file(program_store::ROOT_ID, 128,
                                    ProgramType::MK61, "demo", &value,
                                    1, NULL));
  assert(!program_store::write_file(program_store::ROOT_ID, 123,
                                    ProgramType::TEXT, "collision", &value,
                                    1, NULL));
  assert(program_store::write_file(program_store::ROOT_ID, 128,
                                   ProgramType::TEXT, "Report", &value,
                                   1, NULL));
  assert(!program_store::create_directory(program_store::ROOT_ID,
                                           "report.txt", 129, NULL));
  assert(program_store::write_file(program_store::ROOT_ID, 129,
                                   ProgramType::TEXT, ".hidden", &value,
                                   1, &id));
  assert(id == 129);
  assert(program_store::used_nodes() ==
         (u16) program_store::total_count());
}

static void test_directory_extents_are_persistent(void) {
  fresh();
  u16 directory = 0;
  assert(program_store::create_directory(program_store::ROOT_ID, "Many files",
                                         10, &directory));
  assert(program_store::allocate_directory_extent(directory, 11));
  assert(program_store::allocate_directory_extent(directory, 12));
  assert(!program_store::allocate_directory_extent(directory, 11));
  u16 extent = 0;
  assert(program_store::first_extent(directory, extent) && extent == 11);
  assert(program_store::next_extent(extent, extent) && extent == 12);
  assert(!program_store::next_extent(extent, extent));
  assert(program_store::total_count() == 1);
  assert(program_store::used_nodes() == 3);

  program_store::init();
  assert(program_store::first_extent(directory, extent) && extent == 11);
  assert(program_store::next_extent(extent, extent) && extent == 12);
  assert(!program_store::release_directory_extent(11));
  assert(program_store::release_directory_extent(12));
  assert(program_store::release_directory_extent(11));
  assert(program_store::used_nodes() == 1);
  assert(program_store::remove_id(directory));
}

static void test_quota_grows_beyond_legacy_128(void) {
  fresh();
  assert(program_store::max_nodes() > 160);
  for(u16 i = 0; i < 160; i++) {
    char name[16];
    snprintf(name, sizeof(name), "F%03u", (unsigned) i);
    const u8 data = (u8) i;
    assert(program_store::write(ProgramType::TEXT, name, &data, 1));
  }
  assert(program_store::total_count() == 160);
  program_store::init();
  assert(program_store::total_count() == 160);
  u8 value = 0;
  u16 len = 0;
  assert(program_store::read(ProgramType::TEXT, "F159", &value, 1, &len));
  assert(len == 1 && value == (u8) 159);
}

static void test_root_dirent_quota_is_exact_and_atomic(void) {
  fresh();
  u16 first = program_store::INVALID_ID;
  for(u16 i = 0; i < 254; i++) {
    char name[8];
    snprintf(name, sizeof(name), "D%03u", (unsigned) i);
    u16 id = program_store::INVALID_ID;
    assert(program_store::create_directory(program_store::ROOT_ID, name,
                                           program_store::INVALID_ID, &id));
    if(i == 0) first = id;
  }
  assert(program_store::child_count(program_store::ROOT_ID) == 254);
  assert(!program_store::create_directory(program_store::ROOT_ID, "overflow",
                                          program_store::INVALID_ID, NULL));

  u16 nested = program_store::INVALID_ID;
  assert(program_store::create_directory(first, "nested",
                                         program_store::INVALID_ID, &nested));
  assert(!program_store::move_rename(nested, program_store::ROOT_ID,
                                     "nested"));
  assert(by_id(nested).parent_id == first);

  const Entry original = by_id(first);
  assert(!program_store::move_rename(first, program_store::ROOT_ID,
      "1234567890123456789012345678901"));
  assert(strcmp(by_id(first).name, original.name) == 0);

  Entry removable = {};
  assert(program_store::child(program_store::ROOT_ID, 0, removable));
  if(removable.id == first) {
    assert(program_store::child(program_store::ROOT_ID, 1, removable));
  }
  assert(program_store::remove_id(removable.id));
  assert(program_store::move_rename(nested, program_store::ROOT_ID,
                                    "nested"));
  assert(by_id(nested).parent_id == program_store::ROOT_ID);
  assert(program_store::child_count(program_store::ROOT_ID) == 254);

  program_store::init();
  assert(program_store::child_count(program_store::ROOT_ID) == 254);
  assert(by_id(nested).parent_id == program_store::ROOT_ID);
}

static void test_corrupt_wal_tail_rolls_back_and_recovers(void) {
  fresh();
  assert(program_store::write(ProgramType::TEXT, "ALPHA",
                              (const u8*) "one", 3));
  assert(program_store::write(ProgramType::TEXT, "BETA",
                              (const u8*) "two", 3));
  const storage_geometry::Geometry geometry = program_store::geometry();
  const u32 wal = (geometry.catalog_a_sector +
                   storage_geometry::CATALOG_HEADER_SECTORS +
                   geometry.catalog_table_sectors) * SPIFlash::SECTOR_SIZE;
  SPIFlash::corrupt(wal + 256, 'X');

  program_store::init();
  expect_text("ALPHA", "one");
  assert(!program_store::exists(ProgramType::TEXT, "BETA"));
  assert(program_store::write(ProgramType::TEXT, "GAMMA",
                              (const u8*) "three", 5));
  program_store::init();
  expect_text("ALPHA", "one");
  expect_text("GAMMA", "three");
}

static void test_power_cuts_are_atomic_and_retryable(void) {
  static const u8 old_data[] = {'o', 'l', 'd'};
  static const u8 new_data[] = {'n', 'e', 'w'};
  for(i32 cut = 0; cut < 12; cut++) {
    fresh();
    assert(program_store::write(ProgramType::TEXT, "ATOMIC", old_data,
                                sizeof(old_data)));
    SPIFlash::failAfterOperations(cut);
    const bool committed = program_store::write(ProgramType::TEXT, "ATOMIC",
                                                new_data, sizeof(new_data));
    SPIFlash::clearFailure();

    // A failed transaction must not poison the current WAL slot.
    assert(program_store::write(ProgramType::TEXT, "AFTER",
                                (const u8*) "ok", 2));
    program_store::init();
    u8 recovered[sizeof(old_data)] = {};
    u16 len = 0;
    assert(program_store::read(ProgramType::TEXT, "ATOMIC", recovered,
                               sizeof(recovered), &len));
    assert(len == sizeof(recovered));
    const bool is_old = memcmp(recovered, old_data, sizeof(recovered)) == 0;
    const bool is_new = memcmp(recovered, new_data, sizeof(recovered)) == 0;
    assert(is_old || is_new);
    if(committed) assert(is_new);
    expect_text("AFTER", "ok");
  }
}

static void test_gc_preserves_live_records(void) {
  fresh(256U * 1024U);
  u8 keep[program_store::MAX_MK61_TEXT_SIZE];
  u8 churn[program_store::MAX_MK61_TEXT_SIZE];
  memset(keep, 0xA5, sizeof(keep));
  memset(churn, 0x3C, sizeof(churn));
  assert(program_store::write(ProgramType::FOCAL, "KEEP", keep,
                              sizeof(keep)));
  for(u16 generation = 0; generation < 180; generation++) {
    churn[0] = (u8) generation;
    churn[1] = (u8) (generation >> 8);
    assert(program_store::write_from_usb(ProgramType::TEXT, "CHURN", churn,
                                         sizeof(churn)));
  }
  program_store::init();
  u8 recovered[program_store::MAX_MK61_TEXT_SIZE] = {};
  u16 len = 0;
  assert(program_store::read(ProgramType::FOCAL, "KEEP", recovered,
                             sizeof(recovered), &len));
  assert(len == sizeof(keep) && memcmp(recovered, keep, sizeof(keep)) == 0);
  assert(program_store::read(ProgramType::TEXT, "CHURN", recovered,
                             sizeof(recovered), &len));
  assert(len == sizeof(churn) && memcmp(recovered, churn, sizeof(churn)) == 0);
}

static void test_stage_journal_survives_reboot_and_churn(void) {
  fresh();
  u8 pinned[512];
  u8 changing[512];
  memset(pinned, 0xA5, sizeof(pinned));
  assert(program_store::vfat_stage_write(0x12345, pinned));
  for(u16 generation = 0; generation < 1200; generation++) {
    memset(changing, (u8) generation, sizeof(changing));
    assert(program_store::vfat_stage_write(77, changing));
  }
  program_store::init();
  u8 recovered[512] = {};
  assert(program_store::vfat_stage_read(0x12345, recovered));
  assert(memcmp(recovered, pinned, sizeof(pinned)) == 0);
  assert(program_store::vfat_stage_read(77, recovered));
  assert(recovered[0] == (u8) 1199);
  program_store::vfat_stage_forget(77, 1);
  program_store::init();
  assert(!program_store::vfat_stage_exists(77));
}

static void test_stage_indexes_large_unique_write_burst(void) {
  fresh();
  static constexpr u16 BLOCKS = 384;
  u8 data[512];
  u8 recovered[512];

  // macOS may issue hundreds of distinct metadata/data writes before its first
  // SYNCHRONIZE CACHE.  Every live block, including erase-sector boundaries,
  // must survive reconstruction of the flash-resident staging journal.
  for(u16 block = 0; block < BLOCKS; block++) {
    for(u16 byte = 0; byte < sizeof(data); byte++) {
      data[byte] = (u8) (block * 37U + byte);
    }
    assert(program_store::vfat_stage_write(0x20000UL + block, data));
  }
  assert(program_store::vfat_stage_count() == BLOCKS);
  memset(data, 0xA5, sizeof(data));
  assert(!program_store::vfat_stage_write(0x30000UL, data));

  program_store::init();
  assert(program_store::vfat_stage_count() == BLOCKS);
  for(u16 block = 0; block < BLOCKS; block++) {
    memset(recovered, 0, sizeof(recovered));
    assert(program_store::vfat_stage_read(0x20000UL + block, recovered));
    for(u16 byte = 0; byte < sizeof(recovered); byte++) {
      assert(recovered[byte] == (u8) (block * 37U + byte));
    }
  }
}

static void test_stage_power_cut_keeps_previous_value(void) {
  u8 old_data[512];
  u8 new_data[512];
  memset(old_data, 0x11, sizeof(old_data));
  memset(new_data, 0xEE, sizeof(new_data));
  for(i32 cut = 0; cut < 7; cut++) {
    fresh();
    assert(program_store::vfat_stage_write(19, old_data));
    SPIFlash::failAfterOperations(cut);
    const bool committed = program_store::vfat_stage_write(19, new_data);
    SPIFlash::clearFailure();
    program_store::init();
    u8 recovered[512] = {};
    assert(program_store::vfat_stage_read(19, recovered));
    const bool old_value = memcmp(recovered, old_data, sizeof(recovered)) == 0;
    const bool new_value = memcmp(recovered, new_data, sizeof(recovered)) == 0;
    assert(old_value || new_value);
    if(committed) assert(new_value);
  }
}

static void test_stage_compacts_when_every_normal_sector_is_live(void) {
  fresh();
  assert(program_store::geometry().stage_sector_count ==
         storage_geometry::STAGE_TARGET_SECTORS);
  const u8 normal_sectors =
      (u8) (program_store::geometry().stage_sector_count - 1);
  u8 data[512];
  memset(data, 0, sizeof(data));
  data[0] = 0;
  assert(program_store::vfat_stage_write(1000, data));
  for(u8 fill = 0; fill < 6; fill++) {
    data[0] = fill;
    assert(program_store::vfat_stage_write(1, data));
  }
  for(u8 sector = 1; sector < normal_sectors; sector++) {
    data[0] = sector;
    assert(program_store::vfat_stage_write(1, data));
    assert(program_store::vfat_stage_write(1000U + sector, data));
    for(u8 fill = 0; fill < 5; fill++) {
      data[0] = (u8) (sector + fill);
      assert(program_store::vfat_stage_write(1, data));
    }
  }

  memset(data, 0xEE, sizeof(data));
  assert(program_store::vfat_stage_write(9999, data));
  program_store::init();
  u8 recovered[512];
  for(u8 sector = 0; sector < normal_sectors; sector++) {
    assert(program_store::vfat_stage_read(1000U + sector, recovered));
    assert(recovered[0] == sector);
  }
  assert(program_store::vfat_stage_read(9999, recovered));
  assert(recovered[0] == 0xEE);
}

static void test_settings_reservation_and_capacity_mismatch(void) {
  fresh();
  const u32 settings = program_store::settings_address();
  assert(program_store::settings_size() == 4080);
  assert(flash.writeByte(settings, 0x5A));
  assert(program_store::format());
  assert(flash.readByte(settings) == 0x5A);
  assert(program_store::erase_settings());
  assert(flash.readByte(settings) == 0xFF);
  u8 guard[4] = {};
  assert(flash.readByteArray(settings + program_store::settings_size(),
                             guard, sizeof(guard)));
  assert(memcmp(guard, "C5SG", 4) == 0);
  program_store::init();
  assert(program_store::ready());

  assert(program_store::write(ProgramType::TEXT, "OLD", (const u8*) "x", 1));
  SPIFlash::setReportedCapacity(1024U * 1024U);
  program_store::init();
  assert(program_store::ready());
  // A changed report invalidates the old locator, but it must not truncate
  // the same two-megabyte physical device.
  assert(program_store::geometry().capacity_bytes == 2U * 1024U * 1024U);
  assert(!program_store::exists(ProgramType::TEXT, "OLD"));
}

static void test_geometry_migration_preserves_settings(void) {
  fresh();
  const u32 settings = program_store::settings_address();
  assert(flash.writeByte(settings, 0x5A));
  assert(program_store::write(ProgramType::TEXT, "OLD", (const u8*) "x", 1));

  // Simulate a locator written by an older geometry algorithm while retaining
  // its committed state, physical capacity, chip identity and valid CRC.
  for(u8 copy = 0; copy < storage_geometry::LOCATOR_SECTORS; copy++) {
    u8 locator[72];
    const u32 address = (u32) copy * SPIFlash::SECTOR_SIZE;
    assert(flash.readByteArray(address, locator, sizeof(locator)));
    put_le32(locator, 56, 1); // deliberately differs from current geometry
    put_le32(locator, 68, locator_crc(locator));
    assert(flash.eraseSector(address));
    assert(flash.writeByteArray(address, locator, sizeof(locator)));
  }

  program_store::init();
  assert(program_store::ready());
  assert(flash.readByte(settings) == 0x5A);
  assert(!program_store::exists(ProgramType::TEXT, "OLD"));
  assert(program_store::geometry().logical_sectors != 1);
}

static void test_counterfeit_capacity_is_measured_not_trusted(void) {
  SPIFlash::reset(2U * 1024U * 1024U);
  SPIFlash::setReportedCapacity(16U * 1024U * 1024U);
  program_store::init();
  assert(program_store::ready());
  assert(program_store::geometry().capacity_bytes == 2U * 1024U * 1024U);
  assert(flash.getCapacity() == 2U * 1024U * 1024U);
  assert(program_store::write(ProgramType::TEXT, "KEEP",
                              (const u8*) "ok", 2));
  // The same forged JEDEC/SFDP upper bound must not force a reformat on every
  // boot after C5 has measured and recorded the real boundary once.
  program_store::init();
  assert(program_store::ready());
  assert(program_store::geometry().capacity_bytes == 2U * 1024U * 1024U);
  assert(program_store::exists(ProgramType::TEXT, "KEEP"));
}

static void test_underreported_capacity_uses_the_whole_device(void) {
  SPIFlash::reset(2U * 1024U * 1024U);
  SPIFlash::setReportedCapacity(512U * 1024U);
  program_store::init();
  assert(program_store::ready());
  assert(program_store::geometry().capacity_bytes == 2U * 1024U * 1024U);
  assert(program_store::write(ProgramType::TEXT, "KEEP",
                              (const u8*) "ok", 2));
  // The measured size can legitimately exceed the JEDEC/SFDP report and must
  // remain loadable without another destructive probe.
  program_store::init();
  assert(program_store::ready());
  assert(program_store::geometry().capacity_bytes == 2U * 1024U * 1024U);
  assert(program_store::exists(ProgramType::TEXT, "KEEP"));
}

static void test_declared_geometry_change_forces_a_fresh_probe(void) {
  fresh(2U * 1024U * 1024U);
  assert(program_store::write(ProgramType::TEXT, "OLD",
                              (const u8*) "x", 1));
  // A changed JEDEC/SFDP upper bound is treated as chip replacement even if
  // the newly measured physical boundary happens to be the same.
  SPIFlash::setReportedCapacity(4U * 1024U * 1024U);
  program_store::init();
  assert(program_store::ready());
  assert(program_store::geometry().capacity_bytes == 2U * 1024U * 1024U);
  assert(!program_store::exists(ProgramType::TEXT, "OLD"));
}

static void test_legacy_layout_is_not_migrated(void) {
  SPIFlash::reset();
  const u8 legacy[] = {'C', '4', 0x7F, 100, 1, 0, 0, 0, 0};
  assert(flash.writeByteArray(0, (u8*) legacy, sizeof(legacy)));
  program_store::init();
  assert(program_store::ready());
  assert(program_store::total_count() == 0);
  u8 locator[4] = {};
  assert(flash.readByteArray(0, locator, sizeof(locator)));
  assert(memcmp(locator, "C5FS", 4) == 0);
}

} // namespace

int main(void) {
  test_dynamic_geometry_and_lazy_format();
  test_roundtrip_ranges_and_noop();
  test_arbitrary_nested_directories();
  test_paths_and_recursive_tree_operations();
  test_directory_depth_limit_includes_moved_subtrees();
  test_names_and_exact_preferred_ids();
  test_directory_extents_are_persistent();
  test_quota_grows_beyond_legacy_128();
  test_root_dirent_quota_is_exact_and_atomic();
  test_corrupt_wal_tail_rolls_back_and_recovers();
  test_power_cuts_are_atomic_and_retryable();
  test_gc_preserves_live_records();
  test_stage_journal_survives_reboot_and_churn();
  test_stage_indexes_large_unique_write_burst();
  test_stage_power_cut_keeps_previous_value();
  test_stage_compacts_when_every_normal_sector_is_live();
  test_settings_reservation_and_capacity_mismatch();
  test_geometry_migration_preserves_settings();
  test_counterfeit_capacity_is_measured_not_trusted();
  test_underreported_capacity_uses_the_whole_device();
  test_declared_geometry_change_forces_a_fresh_probe();
  test_legacy_layout_is_not_migrated();
  printf("program_store_self_test: ok\n");
  return 0;
}
