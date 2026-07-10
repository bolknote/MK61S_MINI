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

static void test_corrupt_newest_catalog_falls_back(void) {
  SPIFlash::reset();
  assert(program_store::format());
  assert(program_store::write(program_store::ProgramType::TEXT, "ALPHA", (const u8*) "one", 3));
  assert(program_store::write(program_store::ProgramType::TEXT, "BETA", (const u8*) "two", 3));

  // BETA is in the newer primary generation. Corrupting it must leave the
  // previous mirror generation readable rather than losing the whole store.
  SPIFlash::corrupt(PRIMARY_CATALOG + 2, 0x00);
  program_store::init();
  expect_data("ALPHA", "one");
  assert(!program_store::exists(program_store::ProgramType::TEXT, "BETA"));

  // The stale snapshot may point into a sector containing an orphaned newer
  // record. The first verified write quarantines that sector; the retry moves
  // to a clean one and must succeed without damaging ALPHA.
  assert(!program_store::write(program_store::ProgramType::TEXT, "DELTA", (const u8*) "four", 4));
  assert(program_store::write(program_store::ProgramType::TEXT, "DELTA", (const u8*) "four", 4));
  program_store::init();
  expect_data("DELTA", "four");
}

static void test_legacy_catalog_is_migratable(void) {
  SPIFlash::reset();
  assert(program_store::format());
  assert(program_store::write(program_store::ProgramType::TEXT, "ALPHA", (const u8*) "one", 3));

  // Convert the newest C2 mirror snapshot to the former C1/9-byte header.
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

int main(void) {
  test_catalog_generations_survive_reinit();
  test_failed_catalog_keeps_previous_snapshot();
  test_failed_payload_is_reported();
  test_corrupt_newest_catalog_falls_back();
  test_legacy_catalog_is_migratable();
  printf("program_store_self_test: ok\n");
  return 0;
}
