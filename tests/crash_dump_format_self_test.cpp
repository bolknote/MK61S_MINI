#include <cassert>
#include <cstring>
#include <iostream>
#include <string>

#include "crash_dump_format.hpp"

using crash_dump_format::Record;

static Record valid_record(void) {
  Record record = {};
  record.version = crash_dump_format::VERSION;
  record.size = sizeof(record);
  record.sequence = 7;
  record.exception_number = 6;
  record.exc_return = 0xFFFFFFF9UL;
  record.msp = 0x2000FFF0UL;
  record.stacked_pc = 0x08012345UL;
  record.stacked_lr = 0x08010001UL;
  record.cfsr = 1UL << 16;
  record.build_id = 0x12345678UL;
  record.capture_flags = crash_dump_format::FRAME_VALID |
                         crash_dump_format::CALLEE_SAVED_VALID;
  record.r4 = 0x44444444UL;
  record.r5 = 0x55555555UL;
  record.r11 = 0xBBBBBBBBUL;
  record.runtime_uptime_ms = 31415;
  record.runtime_state = 3;
  record.classic_ticks = 27;
  record.classic_steps = 26;
  record.classic_missed = 1;
  record.crc32 = crash_dump_format::calculate_crc(record);
  record.magic = crash_dump_format::MAGIC;
  return record;
}

static void test_layout_is_fixed(void) {
  assert(sizeof(Record) == 192);
  assert(offsetof(Record, crc32) == 188);
}

static void test_commit_and_crc(void) {
  Record record = valid_record();
  assert(crash_dump_format::valid(record));

  record.magic = 0;
  assert(!crash_dump_format::valid(record));
  record.magic = crash_dump_format::MAGIC;
  assert(crash_dump_format::valid(record));

  record.stacked_pc ^= 1U;
  assert(!crash_dump_format::valid(record));
}

static void test_header_rejects_other_versions_and_sizes(void) {
  Record record = valid_record();
  record.version++;
  record.crc32 = crash_dump_format::calculate_crc(record);
  assert(!crash_dump_format::valid(record));

  record = valid_record();
  record.size -= sizeof(u32);
  record.crc32 = crash_dump_format::calculate_crc(record);
  assert(!crash_dump_format::valid(record));
}

static void test_report_contains_actionable_fields(void) {
  const Record record = valid_record();
  u8 output[1024] = {};
  const u16 length = crash_dump_format::format_report(
      record, 0x87654321UL, output, sizeof(output));
  assert(length != 0);
  const std::string report((const char*) output, length);
  assert(report.find("exception=UsageFault(6)") != std::string::npos);
  assert(report.find("pc=0x08012345") != std::string::npos);
  assert(report.find("r4=0x44444444,r5=0x55555555") !=
         std::string::npos);
  assert(report.find("r11=0xBBBBBBBB") != std::string::npos);
  assert(report.find("cfsr=0x00010000") != std::string::npos);
  assert(report.find("current_build=0x87654321") != std::string::npos);
  assert(report.find("classic_ticks=27,steps=26,missed=1") !=
         std::string::npos);

  const crash_dump_format::ReportMetadata metadata = {
    "0123456789ABCDEF", "mini-v3-a00"
  };
  const u16 metadata_length = crash_dump_format::format_report(
      record, 0x87654321UL, output, sizeof(output), &metadata);
  assert(metadata_length != 0);
  const std::string metadata_report((const char*) output, metadata_length);
  assert(metadata_report.find(
      "device_public=0123456789ABCDEF,current_profile=mini-v3-a00") !=
      std::string::npos);

  u8 too_small[32] = {};
  assert(crash_dump_format::format_report(
             record, 0, too_small, sizeof(too_small)) == 0);
}

static void test_legacy_record_does_not_print_reserved_registers(void) {
  Record record = valid_record();
  record.capture_flags &= ~crash_dump_format::CALLEE_SAVED_VALID;
  record.crc32 = crash_dump_format::calculate_crc(record);

  u8 output[1024] = {};
  const u16 length = crash_dump_format::format_report(
      record, 0x87654321UL, output, sizeof(output));
  assert(length != 0);
  const std::string report((const char*) output, length);
  assert(report.find("r4=") == std::string::npos);
  assert(report.find("r11=") == std::string::npos);
}

static void test_exception_names(void) {
  assert(std::strcmp(crash_dump_format::exception_name(3), "HardFault") == 0);
  assert(std::strcmp(crash_dump_format::exception_name(4), "MemManage") == 0);
  assert(std::strcmp(crash_dump_format::exception_name(5), "BusFault") == 0);
  assert(std::strcmp(crash_dump_format::exception_name(6), "UsageFault") == 0);
  assert(std::strcmp(crash_dump_format::exception_name(99), "Unknown") == 0);
}

int main(void) {
  test_layout_is_fixed();
  test_commit_and_crc();
  test_header_rejects_other_versions_and_sizes();
  test_report_contains_actionable_fields();
  test_legacy_record_does_not_print_reserved_registers();
  test_exception_names();
  std::cout << "crash_dump_format_self_test: ok\n";
  return 0;
}
