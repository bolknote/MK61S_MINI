// Shared command implementations for resident and portable System APP.

#if MK61_CRASH_DUMP_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
void MK61_TERMINAL_COMMAND_CLASS::print_crash_usage(void) {
      #if MK61_ENABLE_FAULT_INJECTION
      Serial.println(
          "Usage: crash [show|clear|save [path.txt]|test <usage|bus|hard>]");
      #else
      Serial.println("Usage: crash [show|clear|save [path.txt]]");
      #endif

    }
#endif

#if MK61_CRASH_DUMP_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::show_crash_dump(void) {
      crash_dump_format::Record record = {};
      if(!crash_dump::copy(record)) {
        terminal_output::field(
            Serial, "CRASH none reset=0x", crash_dump::boot_reset_flags(), HEX);
        terminal_output::line(
            Serial, " layout=", crash_dump::memory_layout_valid() ? "ok" : "invalid");
        return terminal_protocol::Result::ok();
      }

      shared_scratch::Lease scratch(
          shared_scratch::Owner::TERMINAL_TRANSFER,
          program_store::MAX_MK61_TEXT_SIZE);
      if(!scratch.ok()) {
        Serial.println("CRASH show busy");
        return terminal_protocol::Result::error();
      }
      const u16 length = crash_dump::format_report(
          record, scratch.data(), scratch.size());
      if(length == 0) {
        Serial.println("CRASH report failed");
        return terminal_protocol::Result::error();
      }
      Serial.write(scratch.data(), length);
      return terminal_protocol::Result::ok();
    }
#endif

#if MK61_CRASH_DUMP_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::save_crash_dump(const char* path) {
      crash_dump_format::Record record = {};
      if(!crash_dump::copy(record)) {
        Serial.println("CRASH no retained record");
        return terminal_protocol::Result::error();
      }

      storage_path::FileTarget target = {};
      const storage_path::Status path_status = storage_path::file_target(
          current_directory, path, program_store::ProgramType::TEXT, target);
      if(path_status != storage_path::Status::OK) {
        terminal_path_error("crash save", path_status);
        return terminal_protocol::Result::error();
      }

      shared_scratch::Lease scratch(
          shared_scratch::Owner::TERMINAL_TRANSFER,
          program_store::MAX_MK61_TEXT_SIZE);
      if(!scratch.ok()) {
        Serial.println("CRASH save busy");
        return terminal_protocol::Result::error();
      }
      const u16 length = crash_dump::format_report(
          record, scratch.data(), scratch.size());
      if(length == 0 ||
         !program_store::write_file(
             target.parent_id, program_store::INVALID_ID,
             program_store::ProgramType::TEXT, target.name,
             scratch.data(), length)) {
        Serial.println("CRASH save failed");
        return terminal_protocol::Result::error();
      }
      (void) crash_dump::mark_persisted();
      terminal_output::field(Serial, "CRASH saved ", path);
      terminal_output::line(Serial, " bytes=", length);
      return terminal_protocol::Result::ok();
    }
#endif

#if MK61_CRASH_DUMP_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::exec_crash(void) {
      const char* cursor = command_args();
      if(terminal_core::at_end(cursor)) return show_crash_dump();

      char action[12];
      if(!terminal_core::parse_token(cursor, action, sizeof(action))) {
        print_crash_usage();
        return terminal_protocol::Result::error();
      }
      if(strcmp(action, "show") == 0) {
        if(!terminal_core::at_end(cursor)) {
          print_crash_usage();
          return terminal_protocol::Result::error();
        }
        return show_crash_dump();
      }
      if(strcmp(action, "clear") == 0) {
        if(!terminal_core::at_end(cursor)) {
          print_crash_usage();
          return terminal_protocol::Result::error();
        }
        crash_dump::clear();
        Serial.println("CRASH cleared");
        return terminal_protocol::Result::ok();
      }
      if(strcmp(action, "save") == 0) {
        char path[MAX_INPUT_CHAR];
        if(terminal_core::at_end(cursor)) {
          bounded_string::copy(path, "CRASH.TXT");
        } else if(!terminal_copy_arg(path, sizeof(path), cursor)) {
          print_crash_usage();
          return terminal_protocol::Result::error();
        }
        return save_crash_dump(path);
      }

      #if MK61_ENABLE_FAULT_INJECTION
      if(strcmp(action, "test") == 0) {
        char fault[12];
        if(!terminal_core::parse_token(cursor, fault, sizeof(fault)) ||
           !terminal_core::at_end(cursor)) {
          print_crash_usage();
          return terminal_protocol::Result::error();
        }
        terminal_output::line(Serial, "CRASH injecting ", fault);
        Serial.flush();
        delay(20);
        if(strcmp(fault, "usage") == 0) crash_dump::inject_usage_fault();
        if(strcmp(fault, "bus") == 0) crash_dump::inject_bus_fault();
        if(strcmp(fault, "hard") == 0) crash_dump::inject_hard_fault();
      }
      #endif

      print_crash_usage();
      return terminal_protocol::Result::error();
    }
#endif

#if MK61_MPU_GUARD_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
void MK61_TERMINAL_COMMAND_CLASS::print_mpu_usage(void) {
      #if MK61_ENABLE_MPU_TEST
      Serial.println("Usage: mpu [status|test <guard|null|exec>]");
      #else
      Serial.println("Usage: mpu [status]");
      #endif
    }
#endif

#if MK61_MPU_GUARD_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::show_mpu_status(void) {
      const mpu_guard::Snapshot snapshot = mpu_guard::statistics();
      terminal_output::field(Serial, "MPU backend=", mpu_guard::backend_name());
      terminal_output::field(Serial, " enabled=", snapshot.enabled ? 1 : 0);
      terminal_output::field(Serial, " layout=", snapshot.layout_valid ? "ok" : "invalid");
      terminal_output::field(Serial, " regions=", snapshot.available_regions);
      Serial.print('/');
      Serial.print(snapshot.required_regions);
      terminal_output::field(Serial, " ram=0x", snapshot.ram_start, HEX);
      terminal_output::field(Serial, "..0x", snapshot.ram_end, HEX);
      terminal_output::field(Serial, " static_end=0x", snapshot.static_end, HEX);
      terminal_output::field(Serial, " guard=0x", snapshot.guard_base, HEX);
      Serial.print('+');
      Serial.print(snapshot.guard_size);
      terminal_output::field(Serial, " stack_budget=", snapshot.stack_budget);
      terminal_output::field(Serial, " msp=0x", snapshot.current_msp, HEX);
      terminal_output::field(Serial, " observed_low=0x", snapshot.lowest_observed_msp, HEX);
      terminal_output::field(
          Serial, " sampled_remaining=", snapshot.sampled_remaining_stack_bytes());
      terminal_output::field(Serial, " watermark=", snapshot.stack_watermark_enabled ? 1 : 0);
      terminal_output::field(
          Serial, " watermark_remaining=", snapshot.watermark_remaining_stack_bytes);
      terminal_output::field(
          Serial, " observed_remaining=", snapshot.remaining_stack_bytes());
      terminal_output::line(Serial, " sram_xn=", snapshot.sram_execute_never ? 1 : 0);
      return snapshot.enabled
          ? terminal_protocol::Result::ok()
          : terminal_protocol::Result::error();
    }
#endif

#if MK61_MPU_GUARD_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::exec_mpu(void) {
      const char* cursor = command_args();
      if(terminal_core::at_end(cursor)) return show_mpu_status();

      char action[12];
      if(!terminal_core::parse_token(cursor, action, sizeof(action))) {
        print_mpu_usage();
        return terminal_protocol::Result::error();
      }
      if(strcmp(action, "status") == 0 && terminal_core::at_end(cursor)) {
        return show_mpu_status();
      }

      #if MK61_ENABLE_MPU_TEST
      if(strcmp(action, "test") == 0) {
        char fault[12];
        if(!terminal_core::parse_token(cursor, fault, sizeof(fault)) ||
           !terminal_core::at_end(cursor)) {
          print_mpu_usage();
          return terminal_protocol::Result::error();
        }
        terminal_output::line(Serial, "MPU injecting ", fault);
        Serial.flush();
        delay(20);
        bool injected = false;
        if(strcmp(fault, "guard") == 0) {
          injected = mpu_guard::inject_guard_fault();
        } else if(strcmp(fault, "null") == 0) {
          injected = mpu_guard::inject_null_fault();
        } else if(strcmp(fault, "exec") == 0) {
          injected = mpu_guard::inject_execute_fault();
        } else {
          print_mpu_usage();
          return terminal_protocol::Result::error();
        }
        (void) injected;
        Serial.println("MPU fault was not raised");
        return terminal_protocol::Result::error();
      }
      #endif

      print_mpu_usage();
      return terminal_protocol::Result::error();
    }
#endif

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
const char* MK61_TERMINAL_COMMAND_CLASS::watchdog_state_name(u32 state) {
      switch(state) {
        case independent_watchdog::RETAINED_RUNNING: return "running";
        case independent_watchdog::RETAINED_INHIBITED: return "inhibited";
        case independent_watchdog::RETAINED_HANG_TEST: return "hang-test";
        default: return "unknown";
      }
    }
#endif

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
void MK61_TERMINAL_COMMAND_CLASS::print_watchdog_usage(void) {
      #if MK61_ENABLE_WATCHDOG_TEST
      Serial.println("Usage: wdog [status|test <starve|hang>]");
      #else
      Serial.println("Usage: wdog [status]");
      #endif
    }
#endif

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::show_watchdog_status(void) {
      const independent_watchdog::Snapshot snapshot =
          independent_watchdog::statistics();
      terminal_output::field(
          Serial, "WDOG backend=IWDG running=", independent_watchdog::running() ? 1 : 0);
      terminal_output::field(
          Serial, " nominal_ms=", independent_watchdog::NOMINAL_TIMEOUT_MS);
      terminal_output::field(Serial, " reset=", snapshot.boot_was_watchdog_reset ? 1 : 0);
      terminal_output::field(Serial, " generation=", snapshot.generation);
      terminal_output::field(Serial, " epochs=", snapshot.gate.epochs);
      terminal_output::field(Serial, " reloads=", snapshot.gate.reloads);
      terminal_output::field(Serial, " last_epoch_ms=", snapshot.gate.last_epoch_ms);
      terminal_output::field(Serial, " last_reload_ms=", snapshot.gate.last_reload_ms);
      terminal_output::line(Serial, " max_gap_ms=", snapshot.gate.maximum_reload_gap_ms);

      if(snapshot.previous_breadcrumb_valid) {
        terminal_output::field(
            Serial, "WDOG previous generation=", snapshot.previous.generation);
        terminal_output::field(
            Serial, " state=", watchdog_state_name(snapshot.previous.state));
        terminal_output::field(Serial, " epochs=", snapshot.previous.epochs);
        terminal_output::field(Serial, " reloads=", snapshot.previous.reloads);
        terminal_output::field(Serial, " last_epoch_ms=", snapshot.previous.last_epoch_ms);
        terminal_output::field(Serial, " last_reload_ms=", snapshot.previous.last_reload_ms);
        terminal_output::line(
            Serial, " max_gap_ms=", snapshot.previous.maximum_reload_gap_ms);
      }
      return terminal_protocol::Result::ok();
    }
#endif

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED || defined(MK61_BUILD_TERMINAL_MODULE)
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::exec_watchdog(void) {
      const char* cursor = command_args();
      if(terminal_core::at_end(cursor)) return show_watchdog_status();

      char action[12];
      if(!terminal_core::parse_token(cursor, action, sizeof(action))) {
        print_watchdog_usage();
        return terminal_protocol::Result::error();
      }
      if(strcmp(action, "status") == 0 && terminal_core::at_end(cursor)) {
        return show_watchdog_status();
      }

      #if MK61_ENABLE_WATCHDOG_TEST
      if(strcmp(action, "test") == 0) {
        char mode[12];
        if(!terminal_core::parse_token(cursor, mode, sizeof(mode)) ||
           !terminal_core::at_end(cursor)) {
          print_watchdog_usage();
          return terminal_protocol::Result::error();
        }
        if(strcmp(mode, "starve") == 0) {
          terminal_output::field(
              Serial, "WDOG feed inhibited; reset expected within ", independent_watchdog::NOMINAL_TIMEOUT_MS);
          Serial.println(" nominal ms");
          Serial.flush();
          independent_watchdog::inhibit_for_test();
          return terminal_protocol::Result::ok();
        }
        if(strcmp(mode, "hang") == 0) {
          terminal_output::field(
              Serial, "WDOG foreground hang; reset expected within ", independent_watchdog::NOMINAL_TIMEOUT_MS);
          Serial.println(" nominal ms");
          Serial.flush();
          independent_watchdog::hang_for_test();
        }
      }
      #endif

      print_watchdog_usage();
      return terminal_protocol::Result::error();
    }
#endif

void MK61_TERMINAL_COMMAND_CLASS::list_mk61_code_page(void) {
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      const usize program_steps = core_61::program_steps();

      for(int j = 0; j < 16; j++) {
        for(usize i = j; i < program_steps; i += 16) {
          print_address_as_MK61(i);
          Serial.print(". ");
          if(code_page[i] < 16) Serial.write('0');
          Serial.print(code_page[i], HEX);
          Serial.print("  ");
        }
        Serial.println();
      }
    }

void MK61_TERMINAL_COMMAND_CLASS::dump_mk61_code_page(void) {
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      const isize program_steps = (isize) core_61::program_steps();
      isize j = 0;
      do {
        for(isize i = 0; i < 16; i++) {
          Serial_write_hex(code_page[j]);
          Serial.print("  ");
          j++;
          if ( j >= program_steps ) break;
        }
        Serial.println();
      } while (j < program_steps);
    }

terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::exec_date(void) {
      const char* args = command_args();
      const char* option_cursor = args;
      char option[3] = {};
      const bool precise = terminal_core::parse_token(
          option_cursor, option, sizeof(option)) &&
          strcmp(option, "ms") == 0 &&
          terminal_core::at_end(option_cursor);
      const rtc_clock::TerminalRequest request = precise
          ? rtc_clock::TerminalRequest{
              rtc_clock::TerminalAction::SHOW, {0, 0, 0, 0, 0, 0}}
          : rtc_clock::parse_date_request(args);
      if(request.action == rtc_clock::TerminalAction::INVALID) {
        Serial.println("DATE ERROR: expected ms or YYYY-MM-DD HH:MM:SS");
        return terminal_protocol::Result::error();
      }

      if(request.action == rtc_clock::TerminalAction::SET) {
        if(!rtc_clock::set(request.date_time)) {
          Serial.println("DATE ERROR");
          return terminal_protocol::Result::error();
        }
        Serial.println("DATE OK");
        return terminal_protocol::Result::ok();
      }

      rtc_clock::StartupSnapshot snapshot = {};
      char text[rtc_clock::DATETIME_TEXT_SIZE];
      if(!rtc_clock::startup_snapshot(snapshot) ||
         !rtc_clock::format_datetime(snapshot.date_time, text)) {
        Serial.println("DATE ERROR");
        return terminal_protocol::Result::error();
      }
      Serial.print(text);
      if(precise) {
        const u16 milliseconds = rtc_clock::snapshot_milliseconds(snapshot);
        Serial.write('.');
        Serial.write((u8) ('0' + milliseconds / 100));
        Serial.write((u8) ('0' + (milliseconds / 10) % 10));
        Serial.write((u8) ('0' + milliseconds % 10));
      }
      Serial.println();
      if(!snapshot.time_set) Serial.println("Set the date.");
      return terminal_protocol::Result::ok();
    }

#if MK61_ENABLE_RTC_ALARM_TERMINAL
char MK61_TERMINAL_COMMAND_CLASS::alarm_id_letter(rtc_clock::AlarmId id) {
      return id == rtc_clock::AlarmId::A ? 'A' : 'B';
    }
#endif

#if MK61_ENABLE_RTC_ALARM_TERMINAL
void MK61_TERMINAL_COMMAND_CLASS::print_two_digits(u8 value) {
      Serial.write((u8) ('0' + value / 10));
      Serial.write((u8) ('0' + value % 10));
    }
#endif

#if MK61_ENABLE_RTC_ALARM_TERMINAL
void MK61_TERMINAL_COMMAND_CLASS::print_alarm_line(rtc_clock::AlarmId id) {
      rtc_clock::Alarm alarm = {};
      Serial.print("RTC ALARM ");
      Serial.write((u8) alarm_id_letter(id));
      if(!rtc_clock::read_alarm(id, alarm)) {
        Serial.println(" error");
        return;
      }
      if(!alarm.enabled) {
        Serial.println(" off");
        return;
      }
      Serial.write(' ');
      Serial.print(rtc_backup_layout::repeat_name(alarm.repeat));
      Serial.write(' ');
      if(alarm.repeat == rtc_clock::Repeat::ONE_SHOT) {
        char text[rtc_clock::DATETIME_TEXT_SIZE];
        if(rtc_clock::format_datetime(alarm.when, text)) {
          Serial.print(text);
          if(alarm.millisecond != rtc_backup_layout::MILLISECOND_IGNORED) {
            Serial.write('.');
            Serial.write((u8) ('0' + alarm.millisecond / 100));
            Serial.write((u8) ('0' + (alarm.millisecond / 10) % 10));
            Serial.write((u8) ('0' + alarm.millisecond % 10));
          }
          Serial.println();
        } else {
          Serial.println("invalid");
        }
        return;
      }
      print_two_digits(alarm.when.hour);
      Serial.write(':');
      print_two_digits(alarm.when.minute);
      Serial.write(':');
      print_two_digits(alarm.when.second);
      Serial.println();
    }
#endif

#if MK61_ENABLE_RTC_ALARM_TERMINAL
void MK61_TERMINAL_COMMAND_CLASS::print_alarm_status(void) {
      rtc_clock::BackupStatus status = {};
      (void) rtc_clock::backup_status(status);
      terminal_output::field(Serial, "RTC META valid=", status.valid ? 1 : 0);
      terminal_output::field(Serial, " boot-valid=", status.valid_at_boot ? 1 : 0);
      terminal_output::field(Serial, " boot=", status.boot_count);
      terminal_output::field(Serial, " reset=0x", status.reset_flags, HEX);
      terminal_output::field(
          Serial, " wake=", rtc_backup_layout::wake_reason_name(status.last_wake));
      terminal_output::field(Serial, " power-fail=", status.previous_power_unstable ? 1 : 0);
      terminal_output::line(Serial, " arm-fail=", status.alarm_arm_failures);
      print_alarm_line(rtc_clock::AlarmId::A);
      print_alarm_line(rtc_clock::AlarmId::B);
    }
#endif

#if MK61_ENABLE_RTC_ALARM_TERMINAL
terminal_protocol::Result MK61_TERMINAL_COMMAND_CLASS::exec_alarm(void) {
      const char* cursor = command_args();
      if(terminal_core::at_end(cursor)) {
        print_alarm_status();
        return terminal_protocol::Result::ok();
      }

      char slot[2] = {};
      char action[8] = {};
      if(!terminal_core::parse_token(cursor, slot, sizeof(slot)) ||
         !terminal_core::parse_token(cursor, action, sizeof(action)) ||
         slot[1] != 0 || (slot[0] != 'a' && slot[0] != 'A' &&
                         slot[0] != 'b' && slot[0] != 'B')) {
        Serial.println("Usage: alarm <a|b> <off|at|daily|in> ...");
        return terminal_protocol::Result::error();
      }
      const rtc_clock::AlarmId id = slot[0] == 'a' || slot[0] == 'A'
          ? rtc_clock::AlarmId::A : rtc_clock::AlarmId::B;

      bool ok = false;
      if(strcmp(action, "off") == 0 && terminal_core::at_end(cursor)) {
        ok = rtc_clock::cancel_alarm(id);
      } else if(strcmp(action, "at") == 0) {
        rtc_clock::DateTime when = {};
        ok = rtc_clock::parse_datetime(cursor, when) &&
            rtc_clock::schedule_alarm(
                id, {true, rtc_clock::Repeat::ONE_SHOT, when,
                     rtc_backup_layout::MILLISECOND_IGNORED});
      } else if(strcmp(action, "daily") == 0) {
        rtc_clock::DateTime when = {};
        ok = rtc_clock::parse_time_of_day(cursor, when) &&
            rtc_clock::schedule_alarm(
                id, {true, rtc_clock::Repeat::DAILY, when,
                     rtc_backup_layout::MILLISECOND_IGNORED});
      } else if(strcmp(action, "in") == 0) {
        usize seconds = 0;
        ok = terminal_core::parse_unsigned(
                 cursor, 10, 31536000UL, seconds) &&
             terminal_core::at_end(cursor) &&
             rtc_clock::schedule_after(id, (u32) seconds);
      } else {
        Serial.println("Usage: alarm <a|b> off | at YYYY-MM-DD HH:MM:SS | daily HH:MM:SS | in <seconds>");
        return terminal_protocol::Result::error();
      }

      Serial.println(ok ? "ALARM OK" : "ALARM ERROR");
      return ok ? terminal_protocol::Result::ok()
                : terminal_protocol::Result::error();
    }
#endif

void MK61_TERMINAL_COMMAND_CLASS::DumpRegisters(void) {
     // -0.12345678 -9A (14)
      char buffer[15];

      for(int i=0; i < 15; i++) {
        Serial.write('R');
        Serial.print(i, HEX);
        Serial.print(" = ");
        MK61Emu_ReadRegister(i, buffer, terminal_symbols);
        //Serial.write((char*) &buffer[0], 3); //Serial.write(buffer[1]); Serial.write('.');
        terminal_println_cp1251((char*) &buffer);
      }

      Serial.print("IP: "); Serial.println(core_61::get_IP());
    }

void MK61_TERMINAL_COMMAND_CLASS::Dump1302(void) {
      char buff[43];
      MK61Emu_get_1302_R(&buff[0]);
      Serial.println(buff);
    }

void  MK61_TERMINAL_COMMAND_CLASS::print_address_as_MK61(usize addr) {
      Serial.write(terminal_mnemonics::hex_digit((u8) (addr / 10)));
      Serial.write((u8) ('0' + addr % 10));
    }

void  MK61_TERMINAL_COMMAND_CLASS::echo_mk61_stack(void) {
      char cvalue[15];
      cvalue[14] = 0;

      Serial.print("X1 = "); terminal_println_cp1251(read_stack_register(stack::X1, cvalue, terminal_symbols));
      Serial.print("T  = "); terminal_println_cp1251(read_stack_register(stack::T, cvalue, terminal_symbols));
      Serial.print("Z  = "); terminal_println_cp1251(read_stack_register(stack::Z, cvalue, terminal_symbols));
      Serial.print("Y  = "); terminal_println_cp1251(read_stack_register(stack::Y, cvalue, terminal_symbols));
      Serial.print("X  = "); terminal_println_cp1251(read_stack_register(stack::X, cvalue, terminal_symbols));
      Serial.print("IP =  "); Serial.println(core_61::get_IP());
    }

void  MK61_TERMINAL_COMMAND_CLASS::echo_ISA_61(void) {
      char op[terminal_mnemonics::MAX_LENGTH + 1];
      for(usize opcode = 0; opcode < terminal_keys::COUNT; ++opcode) {
        terminal_mnemonics::english((u8) opcode, op);
        Serial_write_hex((u8) opcode);
        Serial.write(' ');
        Serial.print(op);
        if(opcode % 4 == 3) {
          Serial.println();
        } else {
          for(usize width = 3 + strlen(op); width < 16; ++width)
            Serial.write(' ');
        }
      }
    }

void MK61_TERMINAL_COMMAND_CLASS::pub_mk61_code_page(void) {
      TerminalMnemonicTable table;
      if(!table.ok()) {
        Serial.println("Mnemonic workspace busy");
        return;
      }
      char op[MAX_LEN_CLASSIC_MNEMO+1];
      u8 code_page[core_61::MAX_PROGRAM_STEP + 3] = {};
      core_61::get_code_page(&code_page[0]);
      const usize listing_end = seek_program_END(code_page);
      const usize program_steps = core_61::program_steps();
      const bool expanded = core_61::expanded_program_is_on();
      if(expanded) {
        const usize next_bank = ((usize) core_61::active_program_bank() + 1) *
            core_61::MAX_PROGRAM_STEP;
        for(usize offset = 0; offset < 3; ++offset)
          (void) core_61::read_absolute_program(
              (u16) (next_bank + offset), code_page[program_steps + offset]);
      }
      const terminal_listing::Layout layout(
          code_page, program_steps, listing_end, expanded);
      for(usize i = 0; i < terminal_listing::COLUMN_ROWS && i < layout.end; ++i) {
        for(usize ii = 0; ii < terminal_listing::COLUMN_COUNT; ++ii) {
          const usize address = ii * terminal_listing::COLUMN_ROWS + i;
          if(address >= layout.end) break;
          print_address_as_MK61(address); Serial.print(". ");

          const u8 code = code_page[address];
          if(layout.lengths[address] == 0) {
            Serial_write_hex(code);
            for(usize width = 2; width < MAX_LEN_CLASSIC_MNEMO + 2; ++width)
              Serial.write(' ');
          } else {
            terminal_write_m8(terminal_mnemonic_code(table.data(), code, op));
            for(usize width = strlen(op); width < MAX_LEN_CLASSIC_MNEMO; ++width)
              Serial.write(' ');
            Serial.print("  ");
          }
        }
        Serial.println();
      }
    }

void  MK61_TERMINAL_COMMAND_CLASS::lasm_mk61_code_page(void) {
      char op[terminal_mnemonics::MAX_LENGTH + 1];
      u8 code_page[core_61::MAX_PROGRAM_STEP + 3] = {};
      core_61::get_code_page(code_page);
      const usize listing_end = seek_program_END(code_page);
      const usize program_steps = core_61::program_steps();
      const bool expanded = core_61::expanded_program_is_on();
      if(expanded) {
        const usize next_bank = ((usize) core_61::active_program_bank() + 1) *
            core_61::MAX_PROGRAM_STEP;
        for(usize offset = 0; offset < 3; ++offset)
          (void) core_61::read_absolute_program(
              (u16) (next_bank + offset), code_page[program_steps + offset]);
      }
      const terminal_listing::Layout layout(
          code_page, program_steps, listing_end, expanded);
      for(usize row = 0; row < terminal_listing::COLUMN_ROWS && row < layout.end; ++row) {
        for(usize column = 0; column < terminal_listing::COLUMN_COUNT; ++column) {
          const usize address = column * terminal_listing::COLUMN_ROWS + row;
          if(address >= layout.end) break;
          Serial.print("00");
          print_address_as_MK61(address);
          const u8 code = code_page[address];
          Serial.write(' '); Serial_write_hex(code); Serial.write(' ');
          const usize length = layout.lengths[address];
          op[0] = 0;
          if(length != 0) {
            terminal_mnemonics::english(code, op);
            Serial.print(op);
          }
          for(usize width = strlen(op); width < terminal_mnemonics::MAX_LENGTH; ++width)
            Serial.write(' ');
          Serial.write(' ');
          usize argument_width = 0;
          for(usize operand = 1; operand < length; ++operand) {
            if(operand != 1) { Serial.write(' '); ++argument_width; }
            const usize source = !expanded || (code != 0x1F && code != 0x2F)
                ? (address + operand) % program_steps : address + operand;
            Serial_write_hex(code_page[source]);
            argument_width += 2;
          }
          const usize argument_field = terminal_listing::COLUMN_WIDTH - 8 -
              terminal_mnemonics::MAX_LENGTH - 1;
          for(; argument_width < argument_field; ++argument_width) Serial.write(' ');
        }
        Serial.println();
      }
    }

bool MK61_TERMINAL_COMMAND_CLASS::GetHexString(const char* args) {
      args = terminal_core::skip_spaces(args);
      if(args == NULL) return false;
      if(strlen(args) < 5U) {
        Serial.println("Usage: hin <four-digit-address> <hex-bytes>");
        return false;
      }

      usize address = 0;
      for(usize i = 0; i < 4; i++) {
        if(args[i] < '0' || args[i] > '9') {
          Serial.println("Address must contain exactly four decimal digits.");
          return false;
        }
        address = address * 10 + (usize) (args[i] - '0');
      }
      const usize limit = library_mk61::program_memory_mode() ==
          ProgramMemoryMode::CLASSIC_105 ? core_61::CLASSIC_PROGRAM_STEP :
          core_61::EXTENDED_ADDRESS_LIMIT;
      if(!terminal_core::is_space(args[4]) || address >= limit) {
        Serial.println("BAD address!");
        return false;
      }

      const char* hex = terminal_core::skip_spaces(args + 4);
      if(hex == NULL || terminal_core::is_end(*hex)) {
        Serial.println("Hex byte string is empty.");
        return false;
      }

      u8 bytes[core_61::MAX_PROGRAM_STEP] = {};
      usize count = 0;
      while(!terminal_core::is_end(*hex) && !terminal_core::is_space(*hex)) {
        const int high = terminal_core::digit_value(hex[0], 16);
        const int low = terminal_core::digit_value(hex[1], 16);
        if(high < 0 || low < 0) {
          Serial.println("Hex byte string must contain complete byte pairs.");
          return false;
        }
        if(address + count >= limit || count >= sizeof(bytes)) {
          Serial.println("Program memory overflow!");
          return false;
        }
        bytes[count++] = (u8) ((high << 4) | low);
        hex += 2;
      }
      if(count == 0 || !terminal_core::at_end(hex)) {
        Serial.println("Unexpected text after hex byte string.");
        return false;
      }

      u8 bank_zero[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      for(usize index = 0; index < core_61::MAX_PROGRAM_STEP; ++index)
        (void) core_61::read_absolute_program((u16) index, bank_zero[index]);
      for(usize index = 0; index < count; ++index)
        if(address + index < core_61::MAX_PROGRAM_STEP)
          bank_zero[address + index] = bytes[index];
      apply_program_memory_auto(bank_zero, core_61::MAX_PROGRAM_STEP, true,
          address + count > core_61::MAX_PROGRAM_STEP);
      for(usize index = 0; index < count; ++index) {
        if(!core_61::write_absolute_program((u16) (address + index), bytes[index])) {
          Serial.println("Program bank allocation failed!");
          return false;
        }
      }
      return true;
    }

void  MK61_TERMINAL_COMMAND_CLASS::PutHexString(const char* args) {
      if(!terminal_core::at_end(args)) {
        usize address = 0;
        usize count = 0;
        const char* cursor = args;
        if(!terminal_core::parse_unsigned(cursor, 10,
               core_61::EXTENDED_ADDRESS_LIMIT - 1U, address) ||
           !terminal_core::parse_unsigned(cursor, 10,
               core_61::MAX_PROGRAM_STEP, count) || count == 0 ||
           !terminal_core::at_end(cursor) ||
           address + count > core_61::EXTENDED_ADDRESS_LIMIT) {
          Serial.println("Usage: hout <absolute-address> <count>");
          return;
        }
        if(!core_61::expanded_program_is_on() &&
           address + count > core_61::CLASSIC_PROGRAM_STEP) {
          Serial.println("Address outside active program memory!");
          return;
        }
        for(usize offset = 0; offset < count; offset += 24) {
          const usize line_address = address + offset;
          Serial.print("hin ");
          for(usize place = 1000; place > 0; place /= 10)
            Serial.write((char) ('0' + (line_address / place) % 10U));
          Serial.write(' ');
          const usize line_count = count - offset < 24 ? count - offset : 24;
          for(usize index = 0; index < line_count; ++index) {
            u8 opcode = 0;
            if(!core_61::read_absolute_program(
                   (u16) (line_address + index), opcode)) {
              Serial.println("Address outside active program memory!");
              return;
            }
            Serial_write_hex(opcode);
          }
          Serial.println();
        }
        return;
      }
      u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      core_61::get_code_page(&code_page[0]);
      isize last_cmd_addr = seek_program_END(&code_page[0]);
      dbgln(MINI, "Last step in programm: ", last_cmd_addr);
      isize j = 0;
      while (j < last_cmd_addr) {
        Serial.print("00"); print_address_as_MK61(j); Serial.write(' ');
        isize jk = 0;
        while (jk < 24) {
          Serial_write_hex(code_page[j]);
          j++; jk++;
          if (j >= last_cmd_addr) break;
        }
        Serial.println();
      }
    }

bool MK61_TERMINAL_COMMAND_CLASS::Assembler(void) {
      TerminalMnemonicTable table;
      if(!table.ok()) {
        Serial.println("Mnemonic workspace busy");
        return false;
      }
      const terminal_core::Assembly assembly = terminal_core::parse_assembly(
        command_args(), AT, table.data(),
        library_mk61::program_memory_mode() == ProgramMemoryMode::CLASSIC_105
            ? core_61::CLASSIC_PROGRAM_STEP :
              core_61::EXTENDED_ADDRESS_LIMIT, terminal_mnemonics::find);
      if(assembly.error != terminal_core::AssemblyError::NONE) {
        ErrorReaction();
        switch(assembly.error) {
          case terminal_core::AssemblyError::EMPTY: Serial.println("Usage: asm [addr] <mnemonics>"); break;
          case terminal_core::AssemblyError::BAD_ADDRESS: Serial.println("BAD address!"); break;
          case terminal_core::AssemblyError::TOO_LONG: Serial.println("Program memory overflow!"); break;
          case terminal_core::AssemblyError::UNKNOWN_MNEMONIC:
            Serial.print("Unexpected token: ");
            Serial.println(assembly.error_at == NULL ? "" : assembly.error_at);
            break;
          case terminal_core::AssemblyError::NONE: break;
        }
        return false;
      }

      // Сначала полностью разбираем, затем применяем один раз: ошибочный токен
      // должен оставить программу без изменений.
      u8 bank_zero[core_61::CODE_PAGE_BUFFER_SIZE] = {};
      for(usize index = 0; index < core_61::MAX_PROGRAM_STEP; ++index)
        (void) core_61::read_absolute_program((u16) index, bank_zero[index]);
      for(usize index = 0; index < assembly.count; ++index)
        if(assembly.address + index < core_61::MAX_PROGRAM_STEP)
          bank_zero[assembly.address + index] = assembly.opcodes[index];
      apply_program_memory_auto(bank_zero, core_61::MAX_PROGRAM_STEP, true,
          assembly.address + assembly.count > core_61::MAX_PROGRAM_STEP);
      for(usize index = 0; index < assembly.count; ++index) {
        if(!core_61::write_absolute_program(
               (u16) (assembly.address + index), assembly.opcodes[index])) {
          Serial.println("Program bank allocation failed!");
          return false;
        }
      }
      AT = (isize) (assembly.address + assembly.count);

      Serial.print("Assembled ");
      Serial.print(assembly.count);
      Serial.print(" opcode(s) at ");
      Serial.println(assembly.address);
      return true;
    }

const char* MK61_TERMINAL_COMMAND_CLASS::power_state_name(
        const power_monitor::Snapshot& snapshot) {
      if(!snapshot.supported) return "unsupported";
      if(snapshot.below_threshold) return "low";
      if(snapshot.recovering) return "recovering";
      return snapshot.initialized ? "stable" : "uninitialized";
    }

void MK61_TERMINAL_COMMAND_CLASS::print_power_status(void) {
      const power_monitor::Snapshot power = power_monitor::snapshot();
      const power_monitor::ThresholdRange threshold =
          power_monitor::threshold_range();
      terminal_output::field(Serial, "POWER PVD", power.level);
      terminal_output::field(Serial, " fall=", threshold.falling_min_mv);
      Serial.write('-');
      Serial.print(threshold.falling_max_mv);
      terminal_output::field(Serial, " rise=", threshold.rising_min_mv);
      Serial.write('-');
      Serial.print(threshold.rising_max_mv);
      terminal_output::field(Serial, " state=", power_state_name(power));
      terminal_output::field(Serial, " gate=", power.writes_allowed ? 1 : 0);
      terminal_output::field(Serial, " wait=", power.stable_remaining_ms);
      terminal_output::field(Serial, " event=", power.low_events);
      Serial.write('/');
      Serial.print(power.recovery_events);
      Serial.print(" last=");
      Serial.print(!power.edge_seen ? "none"
          : (power.last_edge_low ? "fall" : "rise"));
      Serial.write('@');
      Serial.print(power.last_edge_ms);
      terminal_output::field(Serial, " prev=", power.previous_unstable ? 1 : 0);
      Serial.write('@');
      Serial.print(power.previous_edge_ms);
      terminal_output::field(Serial, " reject=", power.rejected_programs);
      Serial.write('/');
      Serial.print(power.rejected_erases);
      Serial.write('/');
      Serial.print(power.rejected_msc_writes);
      terminal_output::line(Serial, " reset_flags=0x", crash_dump::boot_reset_flags(), HEX);
    }

#if MK61_ENABLE_ANALOG_REPORT
void MK61_TERMINAL_COMMAND_CLASS::print_analog_status(void) {
      const hardware_info::AnalogSnapshot analog =
        hardware_info::read_analog_snapshot();
      char report[144];
      snprintf(report, sizeof(report),
        "ANALOG us/n=%u/%u raw(v/t/b)=%u/%u/%u "
        "val(mV/dC/mV)=%ld/%ld/%ld bat=%s",
        (unsigned) analog.elapsed_us,
        (unsigned) analog.conversion_count,
        (unsigned) analog.raw_vref,
        (unsigned) analog.raw_temperature,
        (unsigned) analog.raw_vbat,
        (long) (analog.vdda.valid ? analog.vdda.millivolts : -1L),
        (long) (analog.mcu_temperature.valid
          ? analog.mcu_temperature.decicelsius : -10000L),
        (long) (analog.battery.voltage.valid
          ? analog.battery.voltage.millivolts : -1L),
        hardware_info::battery_status_name(analog.battery));
      Serial.println(report);
    }
#endif


bool MK61_TERMINAL_COMMAND_CLASS::write_register_value(u8 reg, const char* args) {
      const mk61_ref::Ref ref = {mk61_ref::Kind::R, reg};
      mk61_register_init::Value value = {};
      if(!mk61_register_init::parse(args, value)) return false;
      // Сначала проверяем сам адрес. В частности, недоступный RF не должен
      // расходовать очередное значение независимого потока M61_INIT.
      if(!mk61_ref::register_available(reg)) return false;

      switch(value.kind) {
        case mk61_register_init::Kind::NUMBER:
          // The resident write service validates finiteness and exponent once.
          return mk61_ref::write(ref, value.number);
        case mk61_register_init::Kind::RANDOM: {
          // Этот путь намеренно не проверяет random_seed_enabled(): настройка
          // управляет только ROM-командой К СЧ, а инициализатор M61 имеет свой
          // независимый поток аппаратно собранной энтропии.
          const u32 seed7 = entropy_pool::next_decimal7(
              entropy_pool::Domain::M61_INIT);
          #if defined(MK61_BUILD_TERMINAL_MODULE)
          return invocation->services->write_fraction(reg, seed7);
#else
          return mk61_ref::write_fraction7(ref, seed7);
#endif
        }
        case mk61_register_init::Kind::RAW:
          #if defined(MK61_BUILD_TERMINAL_MODULE)
          return invocation->services->write_raw(reg, value.raw);
#else
          return mk61_ref::write_raw_register(reg, value.raw);
#endif
        case mk61_register_init::Kind::REGISTER: {
          double number = 0;
          return mk61_ref::read({mk61_ref::Kind::R, value.source_register}, number) &&
                 mk61_ref::write(ref, number);
        }
      }
      return false;
    }

bool MK61_TERMINAL_COMMAND_CLASS::write_stack_value(const char* args) {
      args = terminal_core::skip_spaces(args);
      if(args == NULL || args[0] == 0 || !terminal_core::is_space(args[1])) return false;

      char name[4] = {args[0], 0, 0, 0};
      mk61_ref::Ref ref;
      if(!mk61_ref::parse_name(name, ref) || ref.kind == mk61_ref::Kind::R) return false;

      double value = 0.0;
      if(!terminal_core::parse_single_decimal(args + 1, value)) return false;
      return mk61_ref::write(ref, value);
    }

isize MK61_TERMINAL_COMMAND_CLASS::parse_u32_list(const char* p, u32* out, usize max_count) {
      usize count = 0;
      while(true) {
        while(*p == ' ' || *p == ',') p++;
        if(*p == 0) break;
        if(*p < '0' || *p > '9') return -1;
        u32 value = 0;
        while(*p >= '0' && *p <= '9') {
          const u32 digit = (u32) (*p++ - '0');
          if(value > (0xFFFFFFFFUL - digit) / 10) return -1;
          value = value * 10 + digit;
        }
        if(count >= max_count) return -1;
        out[count++] = value;
      }
      return (isize) count;
    }

bool MK61_TERMINAL_COMMAND_CLASS::exec_led(void) {
      u32 values[2 * led::PATTERN_MAX - 1];
      const isize n = parse_u32_list(command_args(), values, 2 * led::PATTERN_MAX - 1);
      if(n <= 0 || (n % 2) == 0) return false; // нечётный список: state,ms,...,state

      led::PatternStep steps[led::PATTERN_MAX];
      usize count = 0;
      for(isize i = 0; i < n; i += 2) {
        if(values[i] > 1) return false;
        if(i + 1 < n && values[i + 1] > 65535) return false; // пауза хранится в u16
        steps[count].on = (u8) values[i];
        steps[count].hold_ms = (u16) ((i + 1 < n) ? values[i + 1] : 0);
        count++;
      }
      return led::pattern_start(steps, count);
    }

bool MK61_TERMINAL_COMMAND_CLASS::exec_beep(void) {
      u32 values[2 * SOUND_PATTERN_MAX];
      const isize n = parse_u32_list(command_args(), values, 2 * SOUND_PATTERN_MAX);
      if(n <= 0 || (n % 2) != 0) return false;

      SoundNote notes[SOUND_PATTERN_MAX];
      const usize count = (usize) n / 2;
      for(usize i = 0; i < count; i++) {
        if(values[2 * i] > 65535 || values[2 * i + 1] > 65535) return false; // u16 в SoundNote
        notes[i].frequency_Hz = (u16) values[2 * i];
        notes[i].duration_ms = (u16) values[2 * i + 1];
        notes[i].gap_ms = 0;
        notes[i].volume_percent = 100;
      }
      return sound_pattern_start(notes, count);
    }
