// Included by terminal.cpp, where the console encoding adapters are shared.
namespace terminal_command_driver {
namespace {
bool output(u32 encoding, const u8 *bytes, usize size) {
  if (encoding == 1) {
    terminal_write_m8(bytes, size);
    return true;
  }
  return Serial.write(bytes, size) == size;
}
void number(u32 value, u32 format) {
  if (format & 0x100U)
    Serial.print((i32)value, (int)(format & 255));
  else
    Serial.print(value, (int)format);
}
CoreInfo core_info() {
  return {core_61::program_steps(),
          terminal_script_backend::program_limit(),
          core_61::active_program_bank(),
          core_61::get_IP(),
          core_61::expanded_program_is_on(),
          core_61::ring_size(),
          ring_M::active_chip_count()};
}
const char *stack_text(u32 reg, char *out, const char *symbols) {
  return read_stack_register((stack)reg, out, symbols);
}
RingChip ring_chip(u32 index) {
  const auto &chip = ring_M::active_chips()[index];
  return {chip.NAME, chip.OFFSET};
}
CrashMetadata crash_metadata() {
  CrashMetadata m = {};
  m.build = resident_firmware::build_id();
  m.profile = firmware_build::PROFILE;
  if (!device_identity::format_public_id(device_identity::read(), m.public_id))
    strcpy(m.public_id, "unsupported");
  return m;
}
StorageInfo storage_info() {
  StorageInfo s = {};
  s.ready = program_store::ready();
  s.mount_status = (u32)program_store::mount_status();
  if (!s.ready)
    return s;
  s.capacity = program_store::geometry().capacity_bytes;
  s.used = program_store::used_nodes();
  s.maximum = program_store::max_nodes();
  const int count = program_store::total_count();
  for (int i = 0; i < count; ++i) {
    program_store::Entry e;
    if (program_store::entry_at(i, e) &&
        e.kind == program_store::NodeKind::DIRECTORY)
      ++s.directories;
  }
  s.files = count - s.directories;
  s.cluster_bytes = (u32)program_store::geometry().sectors_per_cluster * 512;
  s.settings_bytes = program_store::settings_size();
  s.required_crc = MK61_REQUIRE_RESIDENT_CRC;
  return s;
}
bool nor_snapshot(FlashSnapshot &out) {
  SpiNorFlash::Diagnostics d = {};
  if (!external_flash().diagnostics(d))
    return false;
  static_assert(sizeof(d) == sizeof(FlashSnapshot),
                "NOR diagnostic adapter layout changed");
#define CHECK_NOR_FIELD(name) \
  static_assert(offsetof(SpiNorFlash::Diagnostics, name) == \
                    offsetof(FlashSnapshot, name), "NOR diagnostic field changed: " #name)
  CHECK_NOR_FIELD(jedec_id);
  CHECK_NOR_FIELD(capacity_bytes);
  CHECK_NOR_FIELD(probe_upper_bytes);
  CHECK_NOR_FIELD(requested_clock_hz);
  CHECK_NOR_FIELD(peripheral_clock_hz);
  CHECK_NOR_FIELD(actual_clock_hz);
  CHECK_NOR_FIELD(page_size);
  CHECK_NOR_FIELD(prescaler);
  CHECK_NOR_FIELD(status);
  CHECK_NOR_FIELD(status_count);
  CHECK_NOR_FIELD(erase_opcode);
  CHECK_NOR_FIELD(sfdp_present);
  CHECK_NOR_FIELD(four_byte_address);
  CHECK_NOR_FIELD(four_byte_opcodes);
#undef CHECK_NOR_FIELD
  memcpy(&out, &d, sizeof(d));
  return true;
}
bool write_fraction(u8 reg, u32 value) {
  return mk61_ref::write_fraction7({mk61_ref::Kind::R, reg}, value);
}
void help_fallback() {
  terminal_println_m8(M8("Доступные команды:"));
  for (usize i = 0; i < terminal_catalog::count(); ++i) {
    Serial.print(terminal_catalog::at(i).name);
    Serial.write(' ');
  }
  Serial.println();
  Serial.println("Install matching /System");
}
const Services services = {sizeof(Services),
                           VERSION,
                           output,
                           number,
                           core_info,
                           core_61::get_code_page,
                           core_61::read_absolute_program,
                           core_61::write_absolute_program,
                           apply_program_memory_auto,
                           insert_cmd_in_program,
                           MK61Emu_ReadRegister,
                           stack_text,
                           MK61Emu_get_1302_R,
                           ringM,
                           ring_chip,
                           ErrorReaction,
                           crash_dump::copy,
                           crash_dump::clear,
                           crash_dump::boot_reset_flags,
                           crash_dump::memory_layout_valid,
                           crash_metadata,
                           crash_dump::mark_persisted,
                           storage_path::file_target,
                           storage_path::status_text,
                           mpu_guard::statistics,
                           mpu_guard::backend_name,
                           independent_watchdog::statistics,
                           independent_watchdog::running,
                           rtc_clock::startup_snapshot,
                           rtc_clock::set,
                           rtc_clock::read_alarm,
                           rtc_clock::schedule_alarm,
                           rtc_clock::schedule_after,
                           rtc_clock::cancel_alarm,
                           rtc_clock::backup_status,
                           storage_info,
                           nor_snapshot,
                           power_monitor::snapshot,
                           power_monitor::threshold_range,
                           resident_firmware::verify,
                           resident_firmware::last_failure,
                           resident_firmware::build_id,
                           virtual_fat::diagnostic,
                           virtual_fat::clear_diagnostic,
                           usb_mass_storage::startup_diagnostic,
                           usb_mass_storage::clear_startup_diagnostic,
                           mk61_ref::write_raw_register,
                           write_fraction,
                           entropy_pool::next_decimal7,
                           terminal_catalog::help_signature,
                           help_fallback,
                           led::pattern_start,
                           sound_pattern_start};

} // namespace
} // namespace terminal_command_driver

terminal_protocol::Result class_terminal::exec_external(u8 command) {
  using namespace terminal_command_driver;
#if defined(__arm__) || defined(__thumb__)
  asm volatile(".global mk61_terminal_command_abi\n.set mk61_terminal_command_abi, %c0" :: "i"(VERSION));
#endif
  // The bootstrap must work before /System is installed and on an
  // unformatted or damaged filesystem. Only the extended report is an APP.
  if (command == CMD_FS_STAT) {
    if (!terminal_core::at_end(command_args())) {
      Serial.println("Usage: df");
      return terminal_protocol::Result::error();
    }
    const StorageInfo info = storage_info();
    if (!info.ready) {
      if (info.mount_status ==
          (u32)program_store::MountStatus::FORMAT_REQUIRED) {
        Serial.println("C9: geometry changed; run format");
        Serial.println("Files were not modified");
      } else if (info.mount_status ==
                 (u32)program_store::MountStatus::REPAIR_REQUIRED) {
        Serial.println(
            "C9: catalog damaged; run format or use System > Format disk menu");
        Serial.println("Files were not modified");
      } else
        Serial.println("C9: unavailable");
      return terminal_protocol::Result::ok();
    }
    char text[320];
    const int length = snprintf(
        text, sizeof(text),
        "Filesystem: C9\r\nFlash: %lu bytes\r\nNodes: %lu used, %lu free, %lu "
        "total\r\nVisible: %lu files, %lu directories\r\nFAT12 cluster: %lu "
        "bytes (virtual)\r\nSettings: %lu bytes reserved\r\n",
        (unsigned long)info.capacity, (unsigned long)info.used,
        (unsigned long)(info.maximum - info.used), (unsigned long)info.maximum,
        (unsigned long)info.files, (unsigned long)info.directories,
        (unsigned long)info.cluster_bytes, (unsigned long)info.settings_bytes);
    if (length < 0 || (usize)length >= sizeof(text))
      return terminal_protocol::Result::error();
    Serial.print(text);
  }
  const char *driver = (command == CMD_DATE || command == CMD_ALARM)
                           ? "/System/CLOCK.APP"
                           : "/System/TERMINAL.APP";
  program_store::Entry app;
  if (storage_path::resolve_file(program_store::ROOT_ID, driver,
                                 program_store::ProgramType::APP,
                                 app) != storage_path::Status::OK) {
    if (command == CMD_FS_STAT)
      return terminal_protocol::Result::ok();
    if (command == CMD_HELP) {
      help_fallback();
      return terminal_protocol::Result::ok();
    }
    Serial.print("Install matching ");
    Serial.println(driver);
    return terminal_protocol::Result::error();
  }
  static const History history = {HISTORY_TEXT_SIZE, HISTORY_DEPTH, &hist_head,
                                  &hist_count,       hist_text,     hist_start,
                                  hist_length};
  Request request = {sizeof(Request),
                     VERSION,
                     &services,
                     command == CMD_SET_CODE  ? (const char *)&input_buffer[4]
                     : command == CMD_REG_SET ? (const char *)input_buffer
                                              : command_args(),
                     command,
                     current_directory,
                     (i32)AT,
                     &history};
  const u32 args[4] = {(u32)(uintptr_t)&request, sizeof(request), 0, 0};
  auto target = mk61_app_flow_to(MK61_APP_KIND_APPLICATION, app.id, EXECUTE);
  target.flags = MK61_APP_FLOW_DIRECT;
  u32 result = 0;
  const auto status =
      loadable_module::run_flow(target, (void *)args, sizeof(args), result);
  if (status != loadable_module::RuntimeStatus::OK) {
    terminal_output::line(
        Serial, "Terminal APP: ", loadable_module::status_text(status));
    return terminal_protocol::Result::error();
  }
  AT = request.assembly_address;
  return result == 1 ? terminal_protocol::Result::ok()
                     : terminal_protocol::Result::error();
}
