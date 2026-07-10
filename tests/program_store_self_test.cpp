#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "SPIFlash.h"
#include "program_store.hpp"
#include "ledcontrol.h"

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
}

static constexpr uint32_t SECTOR_SIZE = 4096;
static constexpr uint32_t STORE_END = 100 * SECTOR_SIZE;
static constexpr uint32_t PRIMARY_CATALOG = 100 * SECTOR_SIZE;
static constexpr uint32_t MIRROR_CATALOG = 230 * SECTOR_SIZE;
static constexpr uint32_t VFAT_STAGE_BASE = 102 * SECTOR_SIZE;

static u16 crc16_update(u16 crc, u8 value) {
  crc ^= (u16) value << 8;
  for(u8 i = 0; i < 8; i++) crc = (crc & 0x8000) ? (u16) ((crc << 1) ^ 0x1021) : (u16) (crc << 1);
  return crc;
}

static void expect_data(const char* name, const char* expected) {
  uint8_t out[64] = {};
  u16 len = 0;
  assert(program_store::read(program_store::ProgramType::TEXT, name, out, sizeof(out), &len));
  assert(len == strlen(expected));
  assert(memcmp(out, expected, len) == 0);
}

static void test_catalog_generations_survive_reinit(void) {
  SPIFlash::reset();
  assert(program_store::format());

  assert(program_store::write(program_store::ProgramType::TEXT, "ALPHA", (const u8*) "one", 3));
  program_store::init();
  expect_data("ALPHA", "one");

  assert(program_store::write(program_store::ProgramType::TEXT, "BETA", (const u8*) "two", 3));
  program_store::init();
  expect_data("ALPHA", "one");
  expect_data("BETA", "two");

  assert(program_store::write(program_store::ProgramType::TEXT, "GAMMA", (const u8*) "three", 5));
  program_store::init();
  expect_data("GAMMA", "three");
}

static void test_failed_catalog_keeps_previous_snapshot(void) {
  SPIFlash::reset();
  assert(program_store::format());
  assert(program_store::write(program_store::ProgramType::TEXT, "ALPHA", (const u8*) "one", 3));

  // Fail whichever alternating catalog copy BETA targets. The last valid
  // ALPHA snapshot must remain bootable.
  SPIFlash::failRange(PRIMARY_CATALOG, MIRROR_CATALOG + SECTOR_SIZE);
  assert(!program_store::write(program_store::ProgramType::TEXT, "BETA", (const u8*) "two", 3));
  SPIFlash::clearFailure();

  program_store::init();
  expect_data("ALPHA", "one");
  assert(!program_store::exists(program_store::ProgramType::TEXT, "BETA"));
}

static void test_failed_payload_is_reported(void) {
  SPIFlash::reset();
  assert(program_store::format());

  SPIFlash::failRange(0, STORE_END);
  assert(!program_store::write(program_store::ProgramType::TEXT, "BROKEN", (const u8*) "data", 4));
  SPIFlash::clearFailure();

  program_store::init();
  assert(!program_store::exists(program_store::ProgramType::TEXT, "BROKEN"));
}

static void test_corrupt_newest_catalog_delta_rolls_back(void) {
  SPIFlash::reset();
  assert(program_store::format());
  assert(program_store::write(program_store::ProgramType::TEXT, "ALPHA", (const u8*) "one", 3));
  assert(program_store::write(program_store::ProgramType::TEXT, "BETA", (const u8*) "two", 3));

  // Corrupt only BETA's committed metadata delta. Replay must stop at the
  // previous valid boundary, preserving ALPHA as the durable state.
  static constexpr uint32_t FIRST_DELTA = PRIMARY_CATALOG + 960;
  SPIFlash::corrupt(FIRST_DELTA + 64 + 8, 0x00);
  program_store::init();
  expect_data("ALPHA", "one");
  assert(!program_store::exists(program_store::ProgramType::TEXT, "BETA"));

  // The rolled-back snapshot points before BETA's orphaned data record. Load
  // quarantines that physical tail, so the first retry uses a clean sector.
  assert(program_store::write(program_store::ProgramType::TEXT, "DELTA", (const u8*) "four", 4));
  program_store::init();
  expect_data("DELTA", "four");
}

static void test_legacy_catalog_is_migratable(void) {
  SPIFlash::reset();
  assert(program_store::format());
  assert(program_store::write(program_store::ProgramType::TEXT, "ALPHA", (const u8*) "one", 3));

  // Fill the delta area so the current state is compacted into the mirror as
  // a regular C3 checkpoint, which can then be converted to C1.
  for(u8 i = 0; i < 49; i++) {
    char name[16];
    snprintf(name, sizeof(name), "AUX%02u", (unsigned) i);
    assert(program_store::write(program_store::ProgramType::TEXT, name, (const u8*) "x", 1));
  }

  // Convert the newest C3 mirror checkpoint to the former C1/9-byte header.
  static u8 current[SECTOR_SIZE];
  static u8 legacy[SECTOR_SIZE];
  assert(flash.readByteArray(MIRROR_CATALOG, current, sizeof(current)));
  memset(legacy, 0xFF, sizeof(legacy));
  const u8 entry_count = current[4];
  const u16 current_len = (u16) (current[5] | ((u16) current[6] << 8));
  const u16 payload_len = (u16) (current_len - 13);
  const u16 legacy_len = (u16) (9 + payload_len);
  legacy[0] = 'C';
  legacy[1] = '1';
  legacy[2] = 0x7F;
  legacy[3] = 100;
  legacy[4] = entry_count;
  legacy[5] = (u8) (legacy_len & 0xFF);
  legacy[6] = (u8) (legacy_len >> 8);
  memcpy(legacy + 9, current + 13, payload_len);

  u16 crc = 0xFFFF;
  crc = crc16_update(crc, legacy[0]);
  crc = crc16_update(crc, legacy[1]);
  for(u8 i = 3; i <= 6; i++) crc = crc16_update(crc, legacy[i]);
  for(u16 i = 9; i < legacy_len; i++) crc = crc16_update(crc, legacy[i]);
  legacy[7] = (u8) (crc & 0xFF);
  legacy[8] = (u8) (crc >> 8);

  assert(flash.eraseSector(PRIMARY_CATALOG));
  assert(flash.eraseSector(MIRROR_CATALOG));
  assert(flash.writeByteArray(PRIMARY_CATALOG, legacy, legacy_len));

  program_store::init();
  expect_data("ALPHA", "one");
  assert(program_store::write(program_store::ProgramType::TEXT, "BETA", (const u8*) "two", 3));
  program_store::init();
  expect_data("BETA", "two");
}

static void test_font_type_survives_catalog_reload(void) {
  SPIFlash::reset();
  assert(program_store::format());
  const u8 font[] = {'F', 'M', 'K', '1', 0x42};
  assert(program_store::write(program_store::ProgramType::FONT, "PIXEL", font, sizeof(font)));

  program_store::init();
  assert(program_store::count(program_store::ProgramType::FONT) == 1);
  u8 stored[16];
  u16 len = 0;
  assert(program_store::read(program_store::ProgramType::FONT, "PIXEL", stored, sizeof(stored), &len));
  assert(len == sizeof(font));
  assert(memcmp(stored, font, len) == 0);
}

static void test_vfat_stage_recovers_latest_committed_sector(void) {
  SPIFlash::reset();
  assert(program_store::format());

  u8 first[512];
  memset(first, 0x31, sizeof(first));
  u8 latest[512];
  memset(latest, 0x72, sizeof(latest));
  assert(program_store::vfat_stage_write(2, first));
  assert(program_store::vfat_stage_write(2, latest));

  program_store::init();
  assert(program_store::vfat_stage_exists(2));
  u8 recovered[512];
  assert(program_store::vfat_stage_read(2, recovered));
  assert(memcmp(recovered, latest, sizeof(latest)) == 0);

  program_store::vfat_stage_forget(2, 1);
  program_store::init();
  assert(!program_store::vfat_stage_exists(2));
}

static void test_vfat_stage_reclaims_dead_segments(void) {
  SPIFlash::reset();
  assert(program_store::format());

  u8 pinned[512];
  memset(pinned, 0xA5, sizeof(pinned));
  assert(program_store::vfat_stage_write(2, pinned));

  u8 changing[512];
  for(u16 generation = 0; generation < 1200; generation++) {
    memset(changing, (u8) generation, sizeof(changing));
    assert(program_store::vfat_stage_write(3, changing));
  }

  program_store::init();
  u8 recovered[512];
  assert(program_store::vfat_stage_read(2, recovered));
  assert(memcmp(recovered, pinned, sizeof(pinned)) == 0);
  assert(program_store::vfat_stage_read(3, recovered));
  assert(recovered[0] == (u8) 1199);
}

static void test_catalog_wal_amortizes_flash_erases(void) {
  SPIFlash::reset();
  assert(program_store::format());
  const uint32_t erases_after_format = SPIFlash::eraseCount();
  const uint64_t bytes_after_format = SPIFlash::programmedBytes();

  for(u8 i = 0; i < 10; i++) {
    char name[16];
    snprintf(name, sizeof(name), "FAST%02u", (unsigned) i);
    const u8 payload = (u8) (0x80 + i);
    assert(program_store::write(program_store::ProgramType::TEXT, name, &payload, 1));
  }

  // Ten mutations fit in aligned 64-byte WAL records: no catalog sector is
  // erased and metadata traffic remains far below ten full snapshots.
  assert(SPIFlash::eraseCount() == erases_after_format);
  assert(SPIFlash::programmedBytes() - bytes_after_format < 2048);
  program_store::init();
  assert(program_store::exists(program_store::ProgramType::TEXT, "FAST00"));
  assert(program_store::exists(program_store::ProgramType::TEXT, "FAST09"));
}

static void test_identical_write_is_flash_noop(void) {
  SPIFlash::reset();
  assert(program_store::format());
  const u8 payload[] = {1, 2, 3, 4, 5};
  assert(program_store::write(program_store::ProgramType::TEXT, "SAME", payload, sizeof(payload)));
  const uint32_t erases = SPIFlash::eraseCount();
  const uint64_t programmed = SPIFlash::programmedBytes();
  assert(program_store::write(program_store::ProgramType::TEXT, "SAME", payload, sizeof(payload)));
  assert(SPIFlash::eraseCount() == erases);
  assert(SPIFlash::programmedBytes() == programmed);
}

static void test_format_invalidates_recoverable_stage_data(void) {
  SPIFlash::reset();
  assert(program_store::format());
  u8 staged[512];
  memset(staged, 0xCC, sizeof(staged));
  assert(program_store::vfat_stage_write(2, staged));
  assert(program_store::format());
  program_store::init();
  assert(!program_store::vfat_stage_exists(2));
}

static void test_partial_stage_tail_preserves_prior_records(void) {
  SPIFlash::reset();
  assert(program_store::format());
  u8 first[512];
  memset(first, 0x41, sizeof(first));
  u8 second[512];
  memset(second, 0x52, sizeof(second));
  assert(program_store::vfat_stage_write(2, first));

  // Record 1 payload is page-aligned at stage_base + 2 * 512.
  SPIFlash::failRange(VFAT_STAGE_BASE + 1024, VFAT_STAGE_BASE + 1536);
  assert(!program_store::vfat_stage_write(3, second));
  SPIFlash::clearFailure();

  u8 out[512];
  assert(program_store::vfat_stage_read(2, out));
  assert(memcmp(out, first, sizeof(first)) == 0);
  assert(program_store::vfat_stage_write(3, second));
  program_store::init();
  assert(program_store::vfat_stage_read(2, out));
  assert(memcmp(out, first, sizeof(first)) == 0);
  assert(program_store::vfat_stage_read(3, out));
  assert(memcmp(out, second, sizeof(second)) == 0);
}

static void test_power_cut_during_wal_update_is_atomic(void) {
  static const u8 old_data[] = {'o', 'l', 'd'};
  static const u8 new_data[] = {'n', 'e', 'w'};

  for(int cut = 0; cut < 12; cut++) {
    SPIFlash::reset();
    assert(program_store::format());
    assert(program_store::write(program_store::ProgramType::TEXT, "ATOMIC",
                                old_data, sizeof(old_data)));
    SPIFlash::failAfterOperations(cut);
    const bool committed = program_store::write(program_store::ProgramType::TEXT,
                                                "ATOMIC", new_data,
                                                sizeof(new_data));
    SPIFlash::clearFailure();
    program_store::init();

    u8 recovered[sizeof(old_data)] = {};
    u16 recovered_len = 0;
    assert(program_store::read(program_store::ProgramType::TEXT, "ATOMIC",
                               recovered, sizeof(recovered), &recovered_len));
    assert(recovered_len == sizeof(recovered));
    const bool is_old = memcmp(recovered, old_data, sizeof(recovered)) == 0;
    const bool is_new = memcmp(recovered, new_data, sizeof(recovered)) == 0;
    assert(is_old || is_new);
    if(committed) assert(is_new);
  }
}

static void test_vfat_stage_compacts_when_every_normal_segment_is_live(void) {
  SPIFlash::reset();
  assert(program_store::format());

  u8 data[512];
  memset(data, 0x11, sizeof(data));
  assert(program_store::vfat_stage_write(2, data));
  for(u8 i = 0; i < 6; i++) {
    memset(data, (u8) (0x20 + i), sizeof(data));
    assert(program_store::vfat_stage_write(129, data));
  }

  for(u16 segment = 1; segment < 127; segment++) {
    memset(data, (u8) segment, sizeof(data));
    assert(program_store::vfat_stage_write(129, data));
    memset(data, (u8) (0x40 + segment), sizeof(data));
    assert(program_store::vfat_stage_write((u16) (2 + segment), data));
    for(u8 i = 0; i < 5; i++) {
      memset(data, (u8) (segment + i), sizeof(data));
      assert(program_store::vfat_stage_write(129, data));
    }
  }

  // All 127 normal segments retain one anchor. This write can succeed only by
  // compacting the sparsest segment through the reserved erase sector.
  memset(data, 0xEE, sizeof(data));
  assert(program_store::vfat_stage_write(130, data));

  u8 recovered[512];
  for(u16 cluster = 2; cluster < 129; cluster++) {
    assert(program_store::vfat_stage_read(cluster, recovered));
  }
  assert(program_store::vfat_stage_read(130, recovered));
  assert(recovered[0] == 0xEE);
}

int main(void) {
  test_catalog_generations_survive_reinit();
  test_failed_catalog_keeps_previous_snapshot();
  test_failed_payload_is_reported();
  test_corrupt_newest_catalog_delta_rolls_back();
  test_legacy_catalog_is_migratable();
  test_font_type_survives_catalog_reload();
  test_vfat_stage_recovers_latest_committed_sector();
  test_vfat_stage_reclaims_dead_segments();
  test_catalog_wal_amortizes_flash_erases();
  test_identical_write_is_flash_noop();
  test_format_invalidates_recoverable_stage_data();
  test_partial_stage_tail_preserves_prior_records();
  test_power_cut_during_wal_update_is_atomic();
  test_vfat_stage_compacts_when_every_normal_segment_is_live();
  printf("program_store_self_test: ok\n");
  return 0;
}
