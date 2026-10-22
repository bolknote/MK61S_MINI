#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

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

static void test_exact_report_and_every_output_boundary(void) {
  // Preserve the exported text format, including spaces, case, newlines and
  // the absence of a trailing NUL. This is the complete pre-refactor report.
  const std::string expected = R"REPORT(MK61 CRASH DUMP 1
sequence=7,exception=UsageFault(6)
build=0x12345678,current_build=0x87654321
exc_return=0xFFFFFFF9,frame=valid,stack=MSP,fp=basic,persisted=0
r0=0x00000000,r1=0x00000000,r2=0x00000000,r3=0x00000000
r12=0x00000000,lr=0x08010001,pc=0x08012345,xpsr=0x00000000
r4=0x44444444,r5=0x55555555,r6=0x00000000,r7=0x00000000
r8=0x00000000,r9=0x00000000,r10=0x00000000,r11=0xBBBBBBBB
msp=0x2000FFF0,psp=0x00000000,control=0x00000000,primask=0x00000000,basepri=0x00000000,faultmask=0x00000000
cfsr=0x00010000,hfsr=0x00000000,dfsr=0x00000000,afsr=0x00000000
mmfar=0x00000000,mmfar_valid=0,bfar=0x00000000,bfar_valid=0,icsr=0x00000000,shcsr=0x00000000
rcc_at_fault=0x00000000,rcc_after_reboot=0x00000000
uptime_ms=31415,runtime_state=3,runtime_detail=0x00000000
classic_ticks=27,steps=26,missed=1,pending=0
)REPORT";
  const Record record = valid_record();
  for(usize capacity = 0; capacity <= expected.size() + 2; ++capacity) {
    std::vector<u8> output(expected.size() + 34, 0xA5);
    const u16 length = crash_dump_format::format_report(
        record, 0x87654321UL, output.data() + 16, capacity);
    assert(length == (capacity >= expected.size() ? expected.size() : 0));
    const usize written = std::min(capacity, (usize)expected.size());
    assert(std::memcmp(output.data() + 16, expected.data(), written) == 0);
    for(usize at = 0; at < 16; ++at) assert(output[at] == 0xA5);
    for(usize at = 16 + written; at < output.size(); ++at)
      assert(output[at] == 0xA5);
  }

  Record maximum;
  std::memset(&maximum, 0xFF, sizeof(maximum));
  maximum.magic = crash_dump_format::MAGIC;
  maximum.version = crash_dump_format::VERSION;
  maximum.size = sizeof(maximum);
  maximum.crc32 = crash_dump_format::calculate_crc(maximum);
  u8 output[2048];
  const u16 length = crash_dump_format::format_report(
      maximum, 0xFFFFFFFFUL, output, sizeof(output));
  assert(length != 0);
  const std::string report((const char*)output, length);
  assert(report.find("sequence=4294967295,exception=Unknown(4294967295)") != std::string::npos);
  assert(report.find("r11=0xFFFFFFFF") != std::string::npos);
  assert(report.find("classic_ticks=4294967295,steps=4294967295,missed=4294967295,pending=4294967295\n") != std::string::npos);
}

static void test_distinct_grouped_words_and_optional_registers(void) {
  Record record = valid_record();
  record.stacked_r0 = 0x00000101;
  record.stacked_r1 = 0x00000102;
  record.stacked_r2 = 0x00000103;
  record.stacked_r3 = 0x00000104;
  record.stacked_r12 = 0x00000105;
  record.stacked_lr = 0x00000106;
  record.stacked_pc = 0x00000107;
  record.stacked_xpsr = 0x00000108;
  record.r4 = 0x00000201;
  record.r5 = 0x00000202;
  record.r6 = 0x00000203;
  record.r7 = 0x00000204;
  record.r8 = 0x00000205;
  record.r9 = 0x00000206;
  record.r10 = 0x00000207;
  record.r11 = 0x00000208;
  record.msp = 0x00000301;
  record.psp = 0x00000302;
  record.control = 0x00000303;
  record.primask = 0x00000304;
  record.basepri = 0x00000305;
  record.faultmask = 0x00000306;
  record.cfsr = 0x00000401;
  record.hfsr = 0x00000402;
  record.dfsr = 0x00000403;
  record.afsr = 0x00000404;
  record.mmfar = 0x00000405;
  record.bfar = 0x00000406;
  record.icsr = 0x00000407;
  record.shcsr = 0x00000408;
  record.rcc_csr_at_fault = 0x00000501;
  record.rcc_csr_after_reboot = 0x00000502;
  for(bool callee_saved : {false, true}) {
    if(callee_saved) record.capture_flags |= crash_dump_format::CALLEE_SAVED_VALID;
    else record.capture_flags &= ~crash_dump_format::CALLEE_SAVED_VALID;
    record.crc32 = crash_dump_format::calculate_crc(record);
    u8 output[2048];
    const u16 length = crash_dump_format::format_report(
        record, 0x87654321UL, output, sizeof(output));
    assert(length != 0);
    const std::string report((const char*)output, length);
    assert(report.find("r0=0x00000101,r1=0x00000102,r2=0x00000103,r3=0x00000104\n"
                       "r12=0x00000105,lr=0x00000106,pc=0x00000107,xpsr=0x00000108\n")
           != std::string::npos);
    assert(report.find("msp=0x00000301,psp=0x00000302,control=0x00000303,"
                       "primask=0x00000304,basepri=0x00000305,faultmask=0x00000306\n")
           != std::string::npos);
    assert(report.find("cfsr=0x00000401,hfsr=0x00000402,dfsr=0x00000403,afsr=0x00000404\n"
                       "mmfar=0x00000405,mmfar_valid=0,bfar=0x00000406,bfar_valid=0,"
                       "icsr=0x00000407,shcsr=0x00000408\n"
                       "rcc_at_fault=0x00000501,rcc_after_reboot=0x00000502\n")
           != std::string::npos);
    const std::string registers =
        "r4=0x00000201,r5=0x00000202,r6=0x00000203,r7=0x00000204\n"
        "r8=0x00000205,r9=0x00000206,r10=0x00000207,r11=0x00000208\n";
    assert((report.find(registers) != std::string::npos) == callee_saved);
    assert((report.find("r4=") != std::string::npos) == callee_saved);
  }
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
  test_exact_report_and_every_output_boundary();
  test_distinct_grouped_words_and_optional_registers();
  test_legacy_record_does_not_print_reserved_registers();
  test_exception_names();
  std::cout << "crash_dump_format_self_test: ok\n";
  return 0;
}
