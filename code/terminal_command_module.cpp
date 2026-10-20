#if defined(MK61_BUILD_TERMINAL_MODULE)
#include "bounded_string.hpp"
#include "ledcontrol.h"
#include "sound_pattern.hpp"
#include "entropy_pool.hpp"
#include "mk61_ref.hpp"
#include "mk61_register_init.hpp"
#include "mk8_literal.hpp"
#include "storage_path.hpp"
#include "terminal_command_driver.hpp"
#include "terminal_command_ids.hpp"
#include "terminal_core.hpp"
#include "terminal_key_sequence.hpp"
#include "terminal_listing.hpp"
#include "terminal_mnemonics.hpp"
#include "terminal_output.hpp"
#include "terminal_protocol.hpp"
namespace core_61 {
static constexpr usize MAX_PROGRAM_STEP = 112, CODE_PAGE_BUFFER_SIZE = 113,
                       CLASSIC_PROGRAM_STEP = 105;
static constexpr u16 EXTENDED_ADDRESS_LIMIT = 10000;
usize program_steps();
bool expanded_program_is_on();
u8 active_program_bank();
u8 driver_get_IP();
void get_code_page(u8 *);
bool read_absolute_program(u16, u8 &);
bool write_absolute_program(u16, u8);
} // namespace core_61
namespace ring_M {
static constexpr usize EXPANDED_CHIP_COUNT = 7;
}
#include "crash_dump.hpp"
#include "independent_watchdog.hpp"
#include "loadable_app_services.h"
#include "mpu_guard.hpp"
#include "power_monitor.hpp"
#include "resident_firmware.hpp"
#include "rtc_clock.hpp"
#include "usb_mass_storage.hpp"
#include "virtual_fat_diagnostic.hpp"
#include <string.h>
#include <type_traits>

#ifndef MK61_ENABLE_RTC_ALARM_TERMINAL
#define MK61_ENABLE_RTC_ALARM_TERMINAL 1
#endif
#ifndef MK61_ENABLE_ANALOG_REPORT
#define MK61_ENABLE_ANALOG_REPORT 0
#endif
#define HEX 16
#define dbgln(...) ((void)0)
namespace {
using namespace terminal_command_driver;
Request *invocation = nullptr;
CoreInfo core_info = {};
static constexpr char terminal_symbols[16] = {
    '0', '1', '2', '3', '4', '5',        '6', '7',
    '8', '9', '-', 'L', 'C', (char)0xC3, 'E', ' '};
u32 call(Operation op, u32 a = 0, u32 b = 0, void *p = nullptr, u32 n = 0) {
  const auto &s = *invocation->services;
  switch (op) {
  case Operation::WRITE_BYTES:
    return s.output(a, (const u8 *)p, n);
  case Operation::NUMBER:
    s.number(a, b);
    return 1;
  case Operation::CORE_INFO:
    if (p && n == sizeof(CoreInfo)) {
      *(CoreInfo *)p = s.core_info();
      return 1;
    }
    return 0;
  case Operation::CORE_PAGE:
    if (p && n == 113) {
      s.core_page((u8 *)p);
      return 1;
    }
    return 0;
  case Operation::CORE_READ:
    return p && n == 1 && a < 10000 && s.core_read((u16)a, *(u8 *)p);
  case Operation::CORE_WRITE:
    return a < 10000 && b <= 255 && s.core_write((u16)a, (u8)b);
  case Operation::CORE_APPLY:
    if (p && n == 112) {
      s.core_apply((const u8 *)p, n, true, a != 0);
      return 1;
    }
    return 0;
  case Operation::CORE_INSERT:
    if (a < core_info.steps && b <= 255) {
      s.core_insert(a, b);
      return 1;
    }
    return 0;
  case Operation::REGISTER_TEXT:
    if (a < 15 && p && n == 15) {
      s.register_text((int)a, (char *)p, terminal_symbols);
      return 1;
    }
    return 0;
  case Operation::STACK_TEXT:
    if (a <= 4 && p && n == 15) {
      s.stack_text(a, (char *)p, terminal_symbols);
      return 1;
    }
    return 0;
  case Operation::CHIP_TEXT:
    if (p && n == 43) {
      s.chip_text((char *)p);
      return 1;
    }
    return 0;
  case Operation::RING_BYTE:
    return a < core_info.ring_size ? s.ring[a] : 0;
  case Operation::RING_CHIP:
    if (p && n == sizeof(RingChip) && a < core_info.ring_chips) {
      *(RingChip *)p = s.ring_chip(a);
      return 1;
    }
    return 0;
  case Operation::ERROR_REACTION:
    s.error_reaction();
    return 1;
  case Operation::CRASH_COPY:
    return s.crash_copy(*(crash_dump_format::Record *)p);
  case Operation::CRASH_CLEAR:
    s.crash_clear();
    return 1;
  case Operation::CRASH_FLAGS:
    return a ? s.crash_layout() : s.crash_flags();
  case Operation::CRASH_METADATA:
    *(CrashMetadata *)p = s.crash_metadata();
    return 1;
  case Operation::CRASH_PERSIST:
    return s.crash_persist();
  case Operation::PATH_TARGET: {
    auto &q = *(PathTarget *)p;
    return (u32)s.path_target((u16)a, q.path, (program_store::ProgramType)b,
                              *(storage_path::FileTarget *)q.output);
  }
  case Operation::PATH_STATUS:
    return (u32)(uintptr_t)s.path_status((storage_path::Status)a);
  case Operation::MPU_SNAPSHOT:
    *(mpu_guard::Snapshot *)p = s.mpu_snapshot();
    return 1;
  case Operation::MPU_BACKEND:
    return (u32)(uintptr_t)s.mpu_backend();
  case Operation::WATCHDOG_SNAPSHOT:
    *(independent_watchdog::Snapshot *)p = s.watchdog_snapshot();
    return 1;
  case Operation::WATCHDOG_RUNNING:
    return s.watchdog_running();
  case Operation::RTC_SNAPSHOT:
    return s.rtc_snapshot(*(rtc_clock::StartupSnapshot *)p);
  case Operation::RTC_SET:
    return s.rtc_set(*(rtc_clock::DateTime *)p);
  case Operation::RTC_ALARM_READ:
    return s.rtc_alarm_read((rtc_clock::AlarmId)a, *(rtc_clock::Alarm *)p);
  case Operation::RTC_ALARM_SET:
    return s.rtc_alarm_set((rtc_clock::AlarmId)a, *(rtc_clock::Alarm *)p);
  case Operation::RTC_ALARM_AFTER:
    return s.rtc_alarm_after((rtc_clock::AlarmId)a, b);
  case Operation::RTC_ALARM_CANCEL:
    return s.rtc_alarm_cancel((rtc_clock::AlarmId)a);
  case Operation::RTC_BACKUP:
    return s.rtc_backup(*(rtc_clock::BackupStatus *)p);
  case Operation::STORAGE_INFO:
    *(StorageInfo *)p = s.storage_info();
    return 1;
  case Operation::NOR_SNAPSHOT:
    return s.nor_snapshot(*(FlashSnapshot *)p);
  case Operation::POWER_SNAPSHOT:
    *(power_monitor::Snapshot *)p = s.power_snapshot();
    return 1;
  case Operation::POWER_THRESHOLD:
    *(power_monitor::ThresholdRange *)p = s.power_threshold();
    return 1;
  case Operation::FIRMWARE_VERIFY:
    *(resident_firmware::Result *)p = s.firmware_verify();
    return 1;
  case Operation::FIRMWARE_FAILURE:
    return s.firmware_failure(*(resident_firmware::Failure *)p);
  case Operation::FIRMWARE_BUILD:
    return s.firmware_build();
  case Operation::VFAT_DIAGNOSTIC:
    *(virtual_fat::Diagnostic *)p = s.vfat_diagnostic();
    return 1;
  case Operation::VFAT_CLEAR:
    s.vfat_clear();
    return 1;
  case Operation::MSC_DIAGNOSTIC:
    *(usb_mass_storage::StartupDiagnostic *)p = s.msc_diagnostic();
    return 1;
  case Operation::MSC_CLEAR:
    s.msc_clear();
    return 1;
  default:
    return 0;
  }
}
template <class T> bool read(Operation op, T &value, u32 a = 0) {
  return call(op, a, 0, &value, sizeof(value)) != 0;
}
struct Console {
  void write(const u8 *p, usize n) {
    (void)call(Operation::WRITE_BYTES, 0, 0, (void *)p, n);
  }
  void write(u8 c) { write(&c, 1); }
  void print(const char *s) {
    if (s)
      write((const u8 *)s, strlen(s));
  }
  void print(char c) { write((u8)c); }
  template <class T,
            typename std::enable_if<std::is_integral<T>::value, int>::type = 0>
  void print(T value, int base = 10) {
    (void)call(Operation::NUMBER, (u32)value,
               (u32)base | (std::is_signed<T>::value ? 0x100U : 0));
  }
  void println() { print("\r\n"); }
  template <class T> void println(T value) {
    print(value);
    println();
  }
  template <class T> void println(T value, int base) {
    print(value, base);
    println();
  }
} Serial;

void terminal_write_m8(const char *s) {
  (void)call(Operation::WRITE_BYTES, 1, 0, (void *)s, strlen(s));
}
void terminal_println_cp1251(const char *s) { Serial.println(s); }
void Serial_write_hex(u8 v) {
  static constexpr char digits[] = "0123456789ABCDEF";
  Serial.write((u8)digits[v >> 4]);
  Serial.write((u8)digits[v & 15]);
}
bool terminal_copy_arg(char *out, usize capacity, const char *args) {
  args = terminal_core::skip_spaces(args);
  if (!out || !capacity || !args)
    return false;
  usize n = 0;
  while (args[n] && args[n] != '\r' && args[n] != '\n')
    ++n;
  while (n && terminal_core::is_space(args[n - 1]))
    --n;
  if (!n || n >= capacity)
    return false;
  memcpy(out, args, n);
  out[n] = 0;
  return true;
}
void terminal_path_error(const char *operation, storage_path::Status status) {
  Serial.print(operation);
  Serial.print(": ");
  Serial.println(storage_path::status_text(status));
}
void ErrorReaction() { (void)call(Operation::ERROR_REACTION); }
constexpr char ISA_61[] =
#include "terminal_classic_isa.inc"
    ;
class TerminalMnemonicTable {
public:
  bool ok() const { return true; }
  const char *data() const { return ISA_61; }
};
char *terminal_mnemonic_code(const char *table, u8 opcode, char *text) {
  terminal_mnemonics::csv(table, opcode, text);
  if (!text[0] || (text[0] == '?' && !text[1]))
    terminal_mnemonics::hex(opcode, text);
  return text;
}
usize seek_program_END(u8 *page) {
  isize last = core_info.steps;
  while (last > 0 && page[last] == 0)
    --last;
  if (!last && !page[0])
    return 0;
  if (last < (isize)core_info.steps)
    ++last;
  if (last < (isize)core_info.steps)
    ++last;
  return last;
}
void apply_program_memory_auto(const u8 *page, usize n, bool, bool extra) {
  (void)call(Operation::CORE_APPLY, extra ? 1 : 0, 0, (void *)page, n);
  (void)read(Operation::CORE_INFO, core_info);
}
} // namespace

enum class ProgramMemoryMode : u8 { CLASSIC_105, AUTO };
namespace library_mk61 {
ProgramMemoryMode program_memory_mode() {
  return core_info.limit == 105 ? ProgramMemoryMode::CLASSIC_105
                                : ProgramMemoryMode::AUTO;
}
} // namespace library_mk61
namespace core_61 {
usize program_steps() { return core_info.steps; }
bool expanded_program_is_on() { return core_info.expanded != 0; }
u8 active_program_bank() { return (u8)core_info.bank; }
u8 driver_get_IP() { return (u8)core_info.instruction; }
void get_code_page(u8 *page) {
  (void)call(Operation::CORE_PAGE, 0, 0, page, CODE_PAGE_BUFFER_SIZE);
}
bool read_absolute_program(u16 a, u8 &out) {
  return call(Operation::CORE_READ, a, 0, &out, 1) != 0;
}
bool write_absolute_program(u16 a, u8 value) {
  return call(Operation::CORE_WRITE, a, value) != 0;
}
} // namespace core_61
void MK61Emu_ReadRegister(int n, char *out, const char *) {
  (void)call(Operation::REGISTER_TEXT, (u32)n, 0, out, 15);
}
const char *read_stack_register(stack reg, char out[15], const char *) {
  (void)call(Operation::STACK_TEXT, (u32)reg, 0, out, 15);
  return out;
}
void MK61Emu_get_1302_R(char *out) {
  (void)call(Operation::CHIP_TEXT, 0, 0, out, 43);
}
namespace rtc_clock {
bool startup_snapshot(StartupSnapshot &out) {
  return ::read(Operation::RTC_SNAPSHOT, out);
}
bool set(const DateTime &value) {
  return call(Operation::RTC_SET, 0, 0, (void *)&value, sizeof(value)) != 0;
}
bool read_alarm(AlarmId id, Alarm &out) {
  return ::read(Operation::RTC_ALARM_READ, out, (u32)id);
}
bool schedule_alarm(AlarmId id, const Alarm &value) {
  return call(Operation::RTC_ALARM_SET, (u32)id, 0, (void *)&value,
              sizeof(value)) != 0;
}
bool schedule_after(AlarmId id, u32 seconds) {
  return call(Operation::RTC_ALARM_AFTER, (u32)id, seconds) != 0;
}
bool cancel_alarm(AlarmId id) {
  return call(Operation::RTC_ALARM_CANCEL, (u32)id) != 0;
}
bool backup_status(BackupStatus &out) {
  return ::read(Operation::RTC_BACKUP, out);
}
} // namespace rtc_clock
namespace crash_dump {
bool copy(crash_dump_format::Record &out) {
  return ::read(Operation::CRASH_COPY, out);
}
void clear() { (void)call(Operation::CRASH_CLEAR); }
u32 boot_reset_flags() { return call(Operation::CRASH_FLAGS); }
bool memory_layout_valid() { return call(Operation::CRASH_FLAGS, 1) != 0; }
bool mark_persisted() { return call(Operation::CRASH_PERSIST) != 0; }
u16 format_report(const crash_dump_format::Record &record, u8 *out, usize n) {
  CrashMetadata m = {};
  if (!::read(Operation::CRASH_METADATA, m))
    return 0;
  const crash_dump_format::ReportMetadata meta = {m.public_id, m.profile};
  return crash_dump_format::format_report(record, m.build, out, n, &meta);
}
} // namespace crash_dump
namespace mpu_guard {
Snapshot statistics() {
  Snapshot s = {};
  (void)::read(Operation::MPU_SNAPSHOT, s);
  return s;
}
const char *backend_name() {
  return (const char *)(uintptr_t)call(Operation::MPU_BACKEND);
}
} // namespace mpu_guard
namespace independent_watchdog {
Snapshot statistics() {
  Snapshot s = {};
  (void)::read(Operation::WATCHDOG_SNAPSHOT, s);
  return s;
}
bool running() { return call(Operation::WATCHDOG_RUNNING) != 0; }
} // namespace independent_watchdog
namespace power_monitor {
Snapshot snapshot() {
  Snapshot s = {};
  (void)::read(terminal_command_driver::Operation::POWER_SNAPSHOT, s);
  return s;
}
ThresholdRange threshold_range() {
  ThresholdRange s = {};
  (void)::read(terminal_command_driver::Operation::POWER_THRESHOLD, s);
  return s;
}
} // namespace power_monitor
namespace entropy_pool {
u32 next_decimal7(Domain domain) {
  return invocation->services->random7(domain);
}
} // namespace entropy_pool
namespace led {
bool pattern_start(const PatternStep *steps, usize count) {
  return invocation->services->led_pattern(steps, count);
}
}
bool sound_pattern_start(const SoundNote *notes, usize count) {
  return invocation->services->sound_pattern(notes, count);
}
namespace storage_path {
Status file_target(u16 dir, const char *path, program_store::ProgramType type,
                   FileTarget &out) {
  PathTarget p = {path, &out};
  return (Status)call(Operation::PATH_TARGET, dir, (u32)type, &p, sizeof(p));
}
const char *status_text(Status status) {
  return (const char *)(uintptr_t)call(Operation::PATH_STATUS, (u32)status);
}
} // namespace storage_path

namespace {
class Commands {
  Request &request_;
  static constexpr usize MAX_INPUT_CHAR = terminal_core::INPUT_CAPACITY,
                         MAX_LEN_CLASSIC_MNEMO = 8;
  const char *command_args() const { return request_.arguments; }
  u16 current_directory;
  isize AT;

public:
  explicit Commands(Request &r)
      : request_(r), current_directory((u16)r.directory),
        AT(r.assembly_address) {}
  ~Commands() { request_.assembly_address = (i32)AT; }
  [[maybe_unused]] void print_crash_usage(void);
  [[maybe_unused]] terminal_protocol::Result show_crash_dump(void);
  [[maybe_unused]] terminal_protocol::Result save_crash_dump(const char *path);
  [[maybe_unused]] terminal_protocol::Result exec_crash(void);
  [[maybe_unused]] void print_mpu_usage(void);
  [[maybe_unused]] terminal_protocol::Result show_mpu_status(void);
  [[maybe_unused]] terminal_protocol::Result exec_mpu(void);
  [[maybe_unused]] const char *watchdog_state_name(u32 state);
  [[maybe_unused]] void print_watchdog_usage(void);
  [[maybe_unused]] terminal_protocol::Result show_watchdog_status(void);
  [[maybe_unused]] terminal_protocol::Result exec_watchdog(void);
  [[maybe_unused]] void list_mk61_code_page(void);
  [[maybe_unused]] void dump_mk61_code_page(void);
  [[maybe_unused]] terminal_protocol::Result exec_date(void);
  [[maybe_unused]] char alarm_id_letter(rtc_clock::AlarmId id);
  [[maybe_unused]] void print_two_digits(u8 value);
  [[maybe_unused]] void print_alarm_line(rtc_clock::AlarmId id);
  [[maybe_unused]] void print_alarm_status(void);
  [[maybe_unused]] terminal_protocol::Result exec_alarm(void);
  [[maybe_unused]] void DumpRegisters(void);
  [[maybe_unused]] void Dump1302(void);
  [[maybe_unused]] void print_address_as_MK61(usize addr);
  [[maybe_unused]] void echo_mk61_stack(void);
  [[maybe_unused]] void echo_ISA_61(void);
  [[maybe_unused]] void pub_mk61_code_page(void);
  [[maybe_unused]] void lasm_mk61_code_page(void);
  [[maybe_unused]] bool GetHexString(const char *args);
  [[maybe_unused]] void PutHexString(const char *args);
  [[maybe_unused]] bool Assembler(void);
  [[maybe_unused]] const char *
  power_state_name(const power_monitor::Snapshot &snapshot);
  [[maybe_unused]] void print_power_status(void);
  [[maybe_unused]] void print_analog_status(void);
  [[maybe_unused]] bool write_register_value(u8 reg, const char *args);
  [[maybe_unused]] bool write_stack_value(const char *args);
  [[maybe_unused]] terminal_protocol::Result execute(u8 command);
  [[maybe_unused]] terminal_protocol::Result filesystem_details();
  [[maybe_unused]] terminal_protocol::Result vfat_log();
  [[maybe_unused]] void ring_dump();
  [[maybe_unused]] void help();
  [[maybe_unused]] void history();
  [[maybe_unused]] isize parse_u32_list(const char *, u32 *, usize);
  [[maybe_unused]] bool exec_led();
  [[maybe_unused]] bool exec_beep();
};
#define MK61_TERMINAL_COMMAND_CLASS Commands
#define get_IP driver_get_IP
#include "terminal_command_functions.inc"
#undef get_IP
#undef MK61_TERMINAL_COMMAND_CLASS

void Commands::ring_dump() {
  usize i = 0, chip = 0, count = 0;
  RingChip current = {};
  if (core_info.ring_chips)
    (void)read(Operation::RING_CHIP, current, 0);
  Serial.print("MK61 ring M dump:");
  while (count < core_info.ring_size) {
    const u8 cell = (u8)call(Operation::RING_BYTE, count);
    if (!i) {
      i = 42;
      Serial.println();
      if (chip < core_info.ring_chips && current.offset == count) {
        Serial.println(current.name);
        ++chip;
        if (chip < core_info.ring_chips)
          (void)read(Operation::RING_CHIP, current, chip);
      }
      if (count < 100)
        Serial.write('0');
      if (count < 10)
        Serial.write('0');
      Serial.print(count);
      Serial.write(' ');
    }
    Serial.write((u8)(cell < 10 ? cell + '0' : cell - 10 + 'A'));
    ++count;
    --i;
  }
  Serial.println();
}
terminal_protocol::Result Commands::vfat_log() {
  const char *args = command_args();
  if (!terminal_core::at_end(args)) {
    char token[6];
    const char *cursor = args;
    if (!terminal_core::parse_token(cursor, token, sizeof(token)) ||
        !terminal_core::at_end(cursor) || strcmp(token, "clear")) {
      Serial.println("Usage: vlog [clear]");
      return terminal_protocol::Result::error();
    }
    (void)call(Operation::VFAT_CLEAR);
    (void)call(Operation::MSC_CLEAR);
  }
  virtual_fat::Diagnostic diagnostic = {};
  char line[virtual_fat::DIAGNOSTIC_LINE_SIZE];
  if (!read(Operation::VFAT_DIAGNOSTIC, diagnostic) ||
      !virtual_fat::format_diagnostic(diagnostic, line, sizeof(line)))
    return terminal_protocol::Result::error();
  Serial.println(line);
  usb_mass_storage::StartupDiagnostic startup = {};
  (void)read(Operation::MSC_DIAGNOSTIC, startup);
  terminal_output::field(Serial, "MSC startup valid=", startup.valid ? 1 : 0);
  terminal_output::line(Serial, " stage=", startup.valid ? startup.stage : 0);
  return terminal_protocol::Result::ok();
}
terminal_protocol::Result Commands::filesystem_details() {
  StorageInfo storage = {};
  if (!read(Operation::STORAGE_INFO, storage))
    return terminal_protocol::Result::error();
  FlashSnapshot flash = {};
  if (read(Operation::NOR_SNAPSHOT, flash)) {
    Serial.print("NOR JEDEC=0x");
    Serial_write_hex((u8)(flash.jedec_id >> 16));
    Serial_write_hex((u8)(flash.jedec_id >> 8));
    Serial_write_hex((u8)flash.jedec_id);
    terminal_output::field(Serial, " SFDP=", flash.sfdp_present ? 1 : 0);
    terminal_output::field(Serial, " probe=", flash.probe_upper_bytes);
    terminal_output::field(Serial, " page=", flash.page_size);
    Serial.print(" erase=0x");
    Serial_write_hex(flash.erase_opcode);
    terminal_output::field(Serial,
                           " address-bytes=", flash.four_byte_address ? 4 : 3);
    terminal_output::field(
        Serial, " opcodes=", flash.four_byte_opcodes ? "4-byte" : "legacy");
    Serial.print(" status=");
    for (u8 i = 0; i < flash.status_count; ++i) {
      if (i)
        Serial.write('/');
      Serial_write_hex(flash.status[i]);
    }
    Serial.println();
    terminal_output::field(Serial,
                           "SPI1 requested_hz=", flash.requested_clock_hz);
    terminal_output::field(Serial, " pclk_hz=", flash.peripheral_clock_hz);
    terminal_output::field(Serial, " prescaler=", flash.prescaler);
    terminal_output::line(Serial, " actual_hz=", flash.actual_clock_hz);
  } else
    Serial.println("NOR diagnostics=unavailable");
  print_power_status();
  resident_firmware::Result firmware = {};
  if (!read(Operation::FIRMWARE_VERIFY, firmware))
    return terminal_protocol::Result::error();
  const auto hex32 = [](u32 value) {
    Serial_write_hex((u8)(value >> 24));
    Serial_write_hex((u8)(value >> 16));
    Serial_write_hex((u8)(value >> 8));
    Serial_write_hex((u8)value);
  };
  Serial.print("FIRMWARE CRC state=");
  Serial.print(resident_firmware_format::status_name(firmware.status));
  terminal_output::field(Serial, " required=", storage.required_crc);
  terminal_output::field(Serial, " image=", firmware.image_size);
  terminal_output::field(Serial, " footer=", firmware.footer_offset);
  Serial.print(" expected=0x");
  hex32(firmware.expected_crc32);
  Serial.print(" build=0x");
  hex32(call(Operation::FIRMWARE_BUILD));
  Serial.print(" actual=0x");
  hex32(firmware.actual_crc32);
  Serial.print(" backend=");
  Serial.print(firmware.status == resident_firmware_format::Status::VALID
                   ? (firmware.hardware_crc ? "hardware" : "software")
                   : "not-run");
  terminal_output::line(Serial, " cycles=", firmware.cycles);
  resident_firmware::Failure failure = {};
  if (read(Operation::FIRMWARE_FAILURE, failure)) {
    Serial.print("FIRMWARE last-failure state=");
    Serial.print(resident_firmware_format::status_name(failure.status));
    Serial.print(" build=0x");
    hex32(failure.build_id);
    Serial.print(" expected=0x");
    hex32(failure.expected_crc32);
    Serial.print(" actual=0x");
    hex32(failure.actual_crc32);
    Serial.println();
  }
  return terminal_protocol::Result::ok();
}

void Commands::help() {
  program_store::Entry pages[2] = {};
  bool available = true;
  char path[] = "/System/HELP0.TXT";
  for (u8 page = 0; page < 2; ++page) {
    path[12] = (char)('0' + page);
    u8 tag[9];
    u16 count = 0;
    available =
        available &&
        storage_path::resolve_file(program_store::ROOT_ID, path,
                                   program_store::ProgramType::TEXT,
                                   pages[page]) == storage_path::Status::OK &&
        program_store::read_range_id(pages[page].id, 0, tag, sizeof(tag),
                                     &count) &&
        count == sizeof(tag) &&
        !memcmp(tag, invocation->services->help_signature(), sizeof(tag));
  }
  if (!available) {
    invocation->services->help_fallback();
    return;
  }
  terminal_write_m8(M8("Доступные команды:"));
  Serial.println();
  u8 bytes[64];
  for (const auto &page : pages)
    for (u16 offset = 9; offset < page.data_len;) {
      const u16 n = (u16)((usize)(page.data_len - offset) < sizeof(bytes)
                              ? page.data_len - offset
                              : sizeof(bytes));
      u16 count = 0;
      if (!program_store::read_range_id(page.id, offset, bytes, n, &count) ||
          count != n) {
        terminal_write_m8(M8("Ошибка чтения справки"));
        Serial.println();
        return;
      }
      (void)call(Operation::WRITE_BYTES, 1, 0, bytes, n);
      offset = (u16)(offset + n);
    }
}
void Commands::history() {
  const auto *h = request_.history;
  if (!h || !h->head || !h->count || !h->text || !h->start || !h->length ||
      h->depth != 8 || h->capacity != 256 ||
      *h->count > h->depth)
    return;
  if (!*h->count) {
    Serial.println("History is empty.");
    return;
  }
  u8 line[terminal_core::INPUT_CAPACITY];
  for (u8 i = 0; i < *h->count; ++i) {
    const u8 slot = (u8)((*h->head + i) % h->depth);
    const u8 n = h->length[slot];
    if (n >= sizeof(line))
      return;
    for (u8 j = 0; j < n; ++j)
      line[j] = (u8)h->text[(h->start[slot] + j) % h->capacity];
    Serial.print("  ");
    Serial.print(i + 1);
    Serial.print(": ");
    (void)call(Operation::WRITE_BYTES, 1, 0, line, n);
    Serial.println();
  }
}
terminal_protocol::Result Commands::execute(u8 command) {
  using R = terminal_protocol::Result;
#if MK61_TERMINAL_CLOCK_ONLY
  if (command == CMD_DATE)
    return exec_date();
  if (command == CMD_ALARM)
    return exec_alarm();
  return R::error();
#else
  switch (command) {
  case CMD_LED:
    if (exec_led()) return R::ok();
    Serial.println("Usage: led <0|1>[,<ms>,<0|1>,...]");
    return R::error();
  case CMD_BEEP:
    if (exec_beep()) return R::ok();
    Serial.println("Usage: beep <Hz>,<ms>[,<Hz>,<ms>,...]");
    return R::error();
  case CMD_HELP:
    help();
    return R::ok();
  case CMD_HISTORY:
    history();
    return R::ok();
  case CMD_REG_SET: {
    const char *line = request_.arguments;
    const int reg = terminal_core::digit_value(line[1], 16);
    const int limit = core_info.expanded ? 15 : 14;
    if (reg < 0 || reg > limit) {
      Serial.println("Use R0..RE; expanded RF.");
      return R::error();
    }
    while (!terminal_core::is_end(*line) && !terminal_core::is_space(*line))
      ++line;
    if (!write_register_value((u8)reg, terminal_core::skip_spaces(line))) {
      Serial.println("Usage: R<0..F>= <number|random|raw 12-hex-tetrads>");
      return R::error();
    }
    return R::ok();
  }
  case CMD_POKE:
    if (!write_stack_value(command_args())) {
      Serial.println(
          "Usage: poke <X|Y|Z|T> <finite number with exponent -99..99>");
      return R::error();
    }
    return R::ok();
  case CMD_FS_STAT:
    return filesystem_details();
  case CMD_VFAT_LOG:
    return vfat_log();
  case CMD_RING:
    ring_dump();
    return R::ok();
  case CMD_INS: {
    const char *args = command_args();
    usize at = 0, opcode = 0;
    if (!terminal_core::parse_unsigned(args, 10, core_info.steps - 1, at) ||
        !terminal_core::parse_unsigned(args, 16, 255, opcode) ||
        !terminal_core::at_end(args)) {
      Serial.println("Usage: ins <step> <00..FF>");
      return R::error();
    }
    (void)call(Operation::CORE_INSERT, at, opcode);
    return R::ok();
  }
  case CMD_CRASH:
    return exec_crash();
  case CMD_MPU:
    return exec_mpu();
  case CMD_WATCHDOG:
    return exec_watchdog();
  case CMD_ISA:
    echo_ISA_61();
    return R::ok();
  case CMD_LIST:
    list_mk61_code_page();
    return R::ok();
  case CMD_DUMP:
    dump_mk61_code_page();
    return R::ok();
  case CMD_PUB:
    pub_mk61_code_page();
    return R::ok();
  case CMD_LASM:
    lasm_mk61_code_page();
    return R::ok();
  case CMD_REG_DUMP:
    DumpRegisters();
    return R::ok();
  case CMD_1302:
    Dump1302();
    return R::ok();
  case CMD_STACK:
    echo_mk61_stack();
    return R::ok();
  case CMD_HIN:
  case CMD_SET_CODE:
    return GetHexString(command_args()) ? R::ok() : R::error();
  case CMD_HOUT:
    PutHexString(command_args());
    return R::ok();
  case CMD_ASM:
    return Assembler() ? R::ok() : R::error();
  default:
    return R::error();
  }
#endif
}
} // namespace
extern "C" u32 mk61_app_initialize(const mk61_app_api *api, u32 crc, u32 kind) {
  return portable_system::bind(api, crc, kind) ? 0 : 1;
}
extern "C" u32 mk61_app_command(u32 command, u32 a, u32 b, u32, u32) {
  using namespace terminal_command_driver;
  if (command != EXECUTE || b != sizeof(Request))
    return 0;
  auto *request = (Request *)(uintptr_t)a;
  if (!compatible(request) || request->command > 255)
    return 0;
  invocation = request;
  struct Clear {
    ~Clear() { invocation = nullptr; }
  } clear;
  if (!read(Operation::CORE_INFO, core_info) || !core_info.steps || core_info.steps > 112 ||
      core_info.ring_chips > ring_M::EXPANDED_CHIP_COUNT)
    return 0;
  Commands runner(*request);
  return runner.execute((u8)request->command).kind ==
                 terminal_protocol::ResultKind::OK
             ? 1
             : 0;
}
#endif
