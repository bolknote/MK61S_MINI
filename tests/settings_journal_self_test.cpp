#include "settings_journal.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

settings_journal::RecordData fixture(u8 counter) {
  settings_journal::RecordData data = {};
  data.grade = 2;
  data.counter = counter;
  data.flags = 0x45;
  data.sound = 0x0A;
  data.text_rows = 8;
  data.text_width = 3;
  data.text_height = 5;
  data.text_gap = 1;
  data.text_profile_stored = true;
  return data;
}

void commit(u8 record[settings_journal::RECORD_SIZE]) {
  record[settings_journal::COMMIT_INDEX] = settings_journal::COMMIT_MARKER;
}

void test_v3_commit_and_corruption(void) {
  u8 record[settings_journal::RECORD_SIZE];
  settings_journal::encode_uncommitted(fixture(7), record);

  settings_journal::RecordData decoded = {};
  assert(settings_journal::decode(record, decoded) == settings_journal::RecordStatus::INVALID);
  commit(record);
  assert(settings_journal::decode(record, decoded) == settings_journal::RecordStatus::VALID);
  assert(decoded.counter == 7);
  assert(decoded.text_profile_stored);
  assert(decoded.text_rows == 8 && decoded.text_width == 3);

  for(usize index = 0; index < settings_journal::COMMIT_INDEX; index++) {
    u8 corrupted[settings_journal::RECORD_SIZE];
    memcpy(corrupted, record, sizeof(corrupted));
    corrupted[index] ^= 0x01;
    assert(settings_journal::decode(corrupted, decoded) == settings_journal::RecordStatus::INVALID);
  }

  record[settings_journal::COMMIT_INDEX] = 0x00;
  assert(settings_journal::decode(record, decoded) == settings_journal::RecordStatus::INVALID);
}

void test_legacy_v2_compatibility(void) {
  u8 record[settings_journal::RECORD_SIZE];
  settings_journal::encode_uncommitted(fixture(9), record);
  record[settings_journal::IDX_VERSION] = settings_journal::VERSION_2;
  record[settings_journal::IDX_CRC] = settings_journal::checksum(record, settings_journal::IDX_CRC);
  record[settings_journal::COMMIT_INDEX] = 0xFF;

  settings_journal::RecordData decoded = {};
  u8 version = 0;
  assert(settings_journal::decode(record, decoded, &version) == settings_journal::RecordStatus::VALID);
  assert(version == settings_journal::VERSION_2);
  assert(decoded.counter == 9);
}

void test_legacy_v1_compatibility(void) {
  u8 record[settings_journal::RECORD_SIZE];
  memset(record, 0xFF, sizeof(record));
  record[settings_journal::IDX_MAGIC_0] = 'M';
  record[settings_journal::IDX_MAGIC_1] = '6';
  record[settings_journal::IDX_MAGIC_2] = '1';
  record[settings_journal::IDX_MAGIC_3] = 'S';
  record[settings_journal::IDX_VERSION] = settings_journal::VERSION_1;
  record[settings_journal::IDX_GRADE] = 1;
  record[settings_journal::IDX_COUNTER] = 4;
  record[settings_journal::IDX_FLAGS] = 0x12;
  record[settings_journal::IDX_SOUND] = 8;
  record[settings_journal::IDX_V1_CRC] = settings_journal::checksum(record, settings_journal::IDX_V1_CRC);

  settings_journal::RecordData decoded = {};
  u8 version = 0;
  assert(settings_journal::decode(record, decoded, &version) == settings_journal::RecordStatus::VALID);
  assert(version == settings_journal::VERSION_1);
  assert(decoded.counter == 4);
  assert(!decoded.text_profile_stored);
}

void test_scanner_uses_latest_complete_record(void) {
  u8 first[settings_journal::RECORD_SIZE];
  u8 second[settings_journal::RECORD_SIZE];
  u8 erased[settings_journal::RECORD_SIZE];
  memset(erased, 0xFF, sizeof(erased));
  settings_journal::encode_uncommitted(fixture(1), first);
  settings_journal::encode_uncommitted(fixture(2), second);
  commit(first);
  commit(second);

  settings_journal::Scanner scanner(settings_journal::RECORD_SIZE * 4);
  scanner.consume(first);
  scanner.consume(second);
  scanner.consume(erased);
  assert(!scanner.active());
  assert(scanner.has_value());
  assert(scanner.latest().counter == 2);
  assert(scanner.next_offset() == settings_journal::RECORD_SIZE * 2);
  assert(!scanner.needs_reclaim());

  settings_journal::Scanner interrupted(settings_journal::RECORD_SIZE * 4);
  interrupted.consume(first);
  second[settings_journal::COMMIT_INDEX] = 0xFF;
  interrupted.consume(second);
  assert(interrupted.has_value());
  assert(interrupted.latest().counter == 1);
  assert(interrupted.needs_reclaim());
}

void test_erased_detection_checks_entire_record(void) {
  u8 partial[settings_journal::RECORD_SIZE];
  memset(partial, 0xFF, sizeof(partial));
  partial[5] = 0;

  settings_journal::RecordData decoded = {};
  assert(settings_journal::decode(partial, decoded) == settings_journal::RecordStatus::INVALID);

  settings_journal::Scanner scanner(settings_journal::RECORD_SIZE * 2);
  scanner.consume(partial);
  assert(!scanner.ended_at_erased());
  assert(scanner.needs_reclaim());
}

} // namespace

int main(void) {
  test_v3_commit_and_corruption();
  test_legacy_v2_compatibility();
  test_legacy_v1_compatibility();
  test_scanner_uses_latest_complete_record();
  test_erased_detection_checks_entire_record();
  printf("settings_journal_self_test: ok\n");
  return 0;
}
