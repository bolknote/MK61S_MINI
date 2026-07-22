// Host self test for the mk_math CORE backend.
//
// Compiles the real MK-61 engine (mk61emu_core.cpp) together with the CORE math
// backend (mk_math_core.cpp) and checks that every transcendental matches libm
// within the calculator's 8-digit precision, that pow() behaves, that the pure
// libm-free helpers agree with <math.h>, and that borrowing the core leaves the
// live user state untouched.

#include <cmath>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#include "mk_math.hpp"       // MK61_MATH_BACKEND == CORE (set via -D)
#include "mk61emu_core.h"

static int g_failures = 0;

static void check_near(const char* label, double got, double want, double tol) {
  const double diff = std::fabs(got - want);
  const double scale = std::fabs(want) > 1.0 ? std::fabs(want) : 1.0;
  if(diff > tol * scale) {
    std::printf("  FAIL %-14s got=%.10g want=%.10g diff=%.3g\n", label, got, want, diff);
    g_failures++;
  } else {
    std::printf("  ok   %-14s got=%.10g want=%.10g\n", label, got, want);
  }
}

static void check_true(const char* label, bool cond) {
  if(!cond) {
    std::printf("  FAIL %s\n", label);
    g_failures++;
  } else {
    std::printf("  ok   %s\n", label);
  }
}

static const char SYMBOLS[16] = {
    '0','1','2','3','4','5','6','7','8','9','-',' ',' ',' ',' ',' '
};

// Read any live stack register the same way the interpreters read X.
static double read_live_reg(stack reg) {
  char value[15];
  value[14] = 0;
  read_stack_register(reg, value, SYMBOLS);

  char buffer[24];
  char* out = buffer;
  if(value[0] == '-') *out++ = '-';
  for(int i = 1; i <= 9; i++) {
    if(value[i] == ' ') continue;
    *out++ = value[i];
  }
  *out++ = 'e';
  *out++ = (value[11] == '-') ? '-' : '+';
  *out++ = value[12];
  *out++ = value[13];
  *out = 0;
  return mk_math::atof(buffer);
}

static double read_live_x(void) { return read_live_reg(stack::X); }

struct MatrixKey { int x, y; };

struct RomHookProbe {
  int calls;
  u8 last_address;
  u8 last_replacement;
  u8 replacement;
  bool replace;
  bool arrays_present;
};

struct CommandHookProbe {
  int calls;
  core_61::Mk61CommandHookPhase last_phase;
  core_61::Mk61CommandSource last_source;
  u8 last_opcode;
  u8 last_replacement;
  u32 last_sequence;
  bool replace;
  u8 replacement;
  bool override_x;
  bool try_nested_registration;
  core_61::Mk61CommandHookHandle nested_registration;
  int order_tag;
  int* order_log;
  int* order_count;
};

struct ProgramBoundaryProbe {
  int calls;
  u8 target;
  u8 last_address;
  u8 last_opcode;
  bool yield;
};

static bool program_boundary_probe(
    const core_61::Mk61ProgramBoundaryContext& context, void* user_data) {
  ProgramBoundaryProbe* const probe = (ProgramBoundaryProbe*) user_data;
  probe->calls++;
  probe->last_address = context.address;
  probe->last_opcode = context.opcode;
  return probe->yield && context.address == probe->target;
}

static void rom_hook_probe(core_61::RomCommandHookContext& context, void* user_data) {
  RomHookProbe* const probe = (RomHookProbe*) user_data;
  probe->calls++;
  probe->last_address = context.address;
  probe->last_replacement = context.replacement_address;
  probe->arrays_present = context.r != nullptr && context.st != nullptr;
  if(probe->replace) context.replacement_address = probe->replacement;
}

static void command_hook_probe(
    core_61::Mk61CommandHookContext& context, void* user_data) {
  CommandHookProbe* const probe = (CommandHookProbe*) user_data;
  probe->calls++;
  probe->last_phase = context.phase;
  probe->last_source = context.source;
  probe->last_opcode = context.opcode;
  probe->last_replacement = context.replacement_opcode;
  probe->last_sequence = context.sequence;
  if(probe->order_log != nullptr && probe->order_count != nullptr) {
    probe->order_log[(*probe->order_count)++] = probe->order_tag;
  }
  if(probe->try_nested_registration) {
    probe->nested_registration = core_61::register_mk61_command_hook(
        0x00, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
        &command_hook_probe, probe);
  }
  if(context.phase == core_61::Mk61CommandHookPhase::BEFORE_EXECUTE && probe->replace) {
    context.replacement_opcode = probe->replacement;
  }
  if(context.phase == core_61::Mk61CommandHookPhase::AFTER_EXECUTE && probe->override_x) {
    // bcd_value follows the serial-ring digit order (least significant display
    // digit first), hence 4.2424242 is encoded as 0x24242424.
    const core_61::bcd_value replacement_x = {0x24242424U, 0};
    core_61::set_stack_register(stack::X, &replacement_x);
  }
}

static void press_matrix(MatrixKey key) {
  core_61::clear_displayed();
  for(int i = 0; i < 4; i++) {
    MK61Emu_SetKeyPress(key.x, key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0, 0);
  for(int i = 0; i < 512; i++) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }
}

// Mirrors library_pmk::hidden_press_key(), which relies on core_61::step()
// clearing the emulated matrix rather than calling SetKeyPress(0, 0).
static void press_matrix_without_explicit_release(MatrixKey key) {
  core_61::clear_displayed();
  for(int i = 0; i < 4; i++) {
    MK61Emu_SetKeyPress(key.x, key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }
  for(int i = 0; i < 64; i++) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }
  core_61::clear_displayed();
}

static MatrixKey digit_key(u8 digit) {
  return {(int) digit + 2, 1};
}

static void set_x_bcd(u32 mantissa, u16 signs_and_pow = 0) {
  const core_61::bcd_value value = {mantissa, signs_and_pow};
  core_61::set_stack_register(stack::X, &value);
}

static void store_direct(u8 reg, u32 mantissa) {
  set_x_bcd(mantissa);
  press_matrix({6, 9}); // X->P
  press_matrix(digit_key(reg));
}

static void prepare_indirect_registers(void) {
  core_61::enable();
  store_direct(5, 0x11111111U);
  store_direct(6, 0x22222222U);
  store_direct(7, 0x00000005U);
  store_direct(8, 0x00000006U);
}

static void press_kip7(void) {
  press_matrix({10, 9}); // K
  press_matrix({8, 9});  // P->X
  press_matrix(digit_key(7));
}

static void run_program(const u8* code, usize length) {
  u8 page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  for(usize i = 0; i < core_61::program_steps(); i++) page[i] = 0x50;
  for(usize i = 0; i < length && i < core_61::program_steps(); i++) page[i] = code[i];
  core_61::set_code_page(page);
  core_61::set_IP(0);
  press_matrix({2, 9}); // C/P
  for(int i = 0; i < 256 && core_61::is_RUN(); i++) core_61::step();
}

static void test_mk61_command_hooks(void) {
  std::printf("MK-61 user command hook registry:\n");
  core_61::configure_random_seed(false, 1);
  check_true("command registry empty",
      core_61::registered_mk61_command_hook_count() == 0);

  prepare_indirect_registers();
  int order[4] = {};
  int order_count = 0;
  CommandHookProbe replacer = {};
  replacer.replace = true;
  replacer.replacement = 0xD8;
  replacer.try_nested_registration = true;
  replacer.order_tag = 1;
  replacer.order_log = order;
  replacer.order_count = &order_count;
  CommandHookProbe observer = {};
  observer.order_tag = 2;
  observer.order_log = order;
  observer.order_count = &order_count;
  CommandHookProbe after = {};
  CommandHookProbe replacement_target = {};

  const core_61::Mk61CommandHookHandle replace_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &replacer);
  const core_61::Mk61CommandHookHandle observe_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &observer);
  const core_61::Mk61CommandHookHandle after_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &after);
  const core_61::Mk61CommandHookHandle replacement_target_handle =
      core_61::register_mk61_command_hook(
          0xD8, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &replacement_target);
  check_true("four command hooks registered",
      replace_handle != core_61::INVALID_MK61_COMMAND_HOOK &&
      observe_handle != core_61::INVALID_MK61_COMMAND_HOOK &&
      after_handle != core_61::INVALID_MK61_COMMAND_HOOK &&
      replacement_target_handle != core_61::INVALID_MK61_COMMAND_HOOK &&
      core_61::registered_mk61_command_hook_count() == 4);

  const u8 indirect_program[] = {0xD7, 0x50};
  run_program(indirect_program, sizeof(indirect_program));
  check_near("program D7->D8", read_live_x(), 2.2222222, 1e-8);
  check_true("program BEFORE source/opcode",
      replacer.calls == 1 &&
      replacer.last_phase == core_61::Mk61CommandHookPhase::BEFORE_EXECUTE &&
      replacer.last_source == core_61::Mk61CommandSource::PROGRAM &&
      replacer.last_opcode == 0xD7);
  check_true("same-opcode registration order",
      order_count == 2 && order[0] == 1 && order[1] == 2 &&
      observer.last_replacement == 0xD8);
  check_true("replacement not redispatched",
      replacement_target.calls == 0);
  check_true("program AFTER result point",
      after.calls == 1 &&
      after.last_phase == core_61::Mk61CommandHookPhase::AFTER_EXECUTE &&
      after.last_source == core_61::Mk61CommandSource::PROGRAM &&
      after.last_opcode == 0xD7 && after.last_replacement == 0xD8 &&
      after.last_sequence == replacer.last_sequence);
  check_true("nested registration rejected",
      replacer.nested_registration == core_61::INVALID_MK61_COMMAND_HOOK);

  check_true("remove program replacer",
      core_61::unregister_mk61_command_hook(replace_handle));
  check_true("reject stale command handle",
      !core_61::unregister_mk61_command_hook(replace_handle));
  check_true("remove program observer",
      core_61::unregister_mk61_command_hook(observe_handle));
  check_true("remove program after",
      core_61::unregister_mk61_command_hook(after_handle));
  check_true("remove replacement target",
      core_61::unregister_mk61_command_hook(replacement_target_handle));

  prepare_indirect_registers();
  CommandHookProbe keyboard_before = {};
  keyboard_before.replace = true;
  keyboard_before.replacement = 0xD8;
  CommandHookProbe keyboard_after = {};
  const core_61::Mk61CommandHookHandle keyboard_before_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &keyboard_before);
  const core_61::Mk61CommandHookHandle keyboard_after_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &keyboard_after);
  press_kip7();
  check_near("keyboard D7->D8", read_live_x(), 2.2222222, 1e-8);
  check_true("keyboard BEFORE source",
      keyboard_before.calls == 1 &&
      keyboard_before.last_source == core_61::Mk61CommandSource::KEYBOARD);
  check_true("keyboard AFTER source/result",
      keyboard_after.calls == 1 &&
      keyboard_after.last_source == core_61::Mk61CommandSource::KEYBOARD &&
      keyboard_after.last_replacement == 0xD8 &&
      keyboard_after.last_sequence == keyboard_before.last_sequence);
  check_true("remove keyboard BEFORE",
      core_61::unregister_mk61_command_hook(keyboard_before_handle));
  check_true("remove keyboard AFTER",
      core_61::unregister_mk61_command_hook(keyboard_after_handle));

  prepare_indirect_registers();
  CommandHookProbe override = {};
  override.override_x = true;
  const core_61::Mk61CommandHookHandle override_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &override);
  press_kip7();
  check_near("AFTER KIP7 overrides X", read_live_x(), 4.2424242, 1e-8);
  check_true("KIP7 AFTER called once", override.calls == 1);
  prepare_indirect_registers();
  run_program(indirect_program, sizeof(indirect_program));
  check_near("program AFTER KIP7 overrides X", read_live_x(), 4.2424242, 1e-8);
  check_true("program KIP7 AFTER called once", override.calls == 2);
  check_true("remove KIP7 override",
      core_61::unregister_mk61_command_hook(override_handle));
  press_matrix({8, 9});
  press_matrix(digit_key(5));
  check_near("KIP7 override keeps R5", read_live_x(), 1.1111111, 1e-8);
  press_matrix({8, 9});
  press_matrix(digit_key(7));
  check_near("KIP7 override keeps R7", read_live_x(), 5.0, 1e-8);

  prepare_indirect_registers();
  CommandHookProbe no_release = {};
  const core_61::Mk61CommandHookHandle no_release_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &no_release);
  press_matrix_without_explicit_release({10, 9});
  press_matrix_without_explicit_release({8, 9});
  press_matrix_without_explicit_release(digit_key(7));
  check_true("keyboard AFTER without explicit release", no_release.calls == 1);
  check_true("remove no-release hook",
      core_61::unregister_mk61_command_hook(no_release_handle));

  CommandHookProbe one = {};
  CommandHookProbe two = {};
  CommandHookProbe stop = {};
  const core_61::Mk61CommandHookHandle one_handle =
      core_61::register_mk61_command_hook(
          0x01, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &one);
  const core_61::Mk61CommandHookHandle two_handle =
      core_61::register_mk61_command_hook(
          0x02, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &two);
  const core_61::Mk61CommandHookHandle stop_handle =
      core_61::register_mk61_command_hook(
          0x50, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
          &command_hook_probe, &stop);
  const u8 consecutive_program[] = {0x01, 0x02, 0x50};
  run_program(consecutive_program, sizeof(consecutive_program));
  check_true("several opcodes intercepted",
      one.calls == 1 && two.calls == 1 && stop.calls == 1);
  check_true("consecutive command sequences",
      one.last_sequence < two.last_sequence && two.last_sequence < stop.last_sequence);
  check_true("remove opcode 01", core_61::unregister_mk61_command_hook(one_handle));
  check_true("remove opcode 02", core_61::unregister_mk61_command_hook(two_handle));
  check_true("remove opcode 50", core_61::unregister_mk61_command_hook(stop_handle));

  core_61::configure_random_seed(true, 1234567);
  CommandHookProbe capacity_probes[core_61::MK61_COMMAND_HOOK_CAPACITY] = {};
  core_61::Mk61CommandHookHandle capacity_hooks[core_61::MK61_COMMAND_HOOK_CAPACITY] = {};
  bool capacity_ok = true;
  for(usize i = 0; i < core_61::MK61_COMMAND_HOOK_CAPACITY; i++) {
    capacity_hooks[i] = core_61::register_mk61_command_hook(
        (u8) i, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
        &command_hook_probe, &capacity_probes[i]);
    capacity_ok &= capacity_hooks[i] != core_61::INVALID_MK61_COMMAND_HOOK;
  }
  check_true("public command-hook capacity", capacity_ok);
  const core_61::Mk61CommandHookHandle overflow =
      core_61::register_mk61_command_hook(
          0xFF, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &capacity_probes[0]);
  check_true("command-hook capacity enforced",
      overflow == core_61::INVALID_MK61_COMMAND_HOOK);
  check_true("RNG command hook has reserved slot",
      core_61::random_seed_enabled() &&
      core_61::registered_mk61_command_hook_count() ==
          core_61::MK61_COMMAND_HOOK_CAPACITY);
  core_61::configure_random_seed(false, 1);
  for(core_61::Mk61CommandHookHandle handle : capacity_hooks) {
    check_true("command capacity unregister",
        core_61::unregister_mk61_command_hook(handle));
  }
  check_true("command registry cleanup",
      core_61::registered_mk61_command_hook_count() == 0);
}

static void test_rom_command_hooks(void) {
  std::printf("ROM command hook registry:\n");
  core_61::configure_random_seed(false, 1);
  check_true("hook registry empty", core_61::registered_rom_command_hook_count() == 0);

  // Use an IK1306 command address with the same ROM word as address 00. This
  // lets the test exercise a real substitution without changing reset behavior.
  u8 ik1306_alias = 0;
  const u32 command_00 = core_61::rom_command_instruction(core_61::RomChip::IK1306, 0);
  for(u16 address = 1; address <= 0xFF; address++) {
    if(core_61::rom_command_instruction(core_61::RomChip::IK1306, (u8) address) == command_00) {
      ik1306_alias = (u8) address;
      break;
    }
  }
  check_true("ROM alias found", ik1306_alias != 0);

  RomHookProbe ik1302 = {};
  RomHookProbe ik1303 = {};
  RomHookProbe replacer = {};
  replacer.replace = true;
  replacer.replacement = ik1306_alias;
  RomHookProbe observer = {};

  const core_61::RomCommandHookHandle hook_1302 = core_61::register_rom_command_hook(
      core_61::RomChip::IK1302, 0, &rom_hook_probe, &ik1302);
  const core_61::RomCommandHookHandle hook_1303 = core_61::register_rom_command_hook(
      core_61::RomChip::IK1303, 0, &rom_hook_probe, &ik1303);
  const core_61::RomCommandHookHandle hook_replace = core_61::register_rom_command_hook(
      core_61::RomChip::IK1306, 0, &rom_hook_probe, &replacer);
  const core_61::RomCommandHookHandle hook_observe = core_61::register_rom_command_hook(
      core_61::RomChip::IK1306, 0, &rom_hook_probe, &observer);

  check_true("four hooks registered",
      hook_1302 != core_61::INVALID_ROM_COMMAND_HOOK &&
      hook_1303 != core_61::INVALID_ROM_COMMAND_HOOK &&
      hook_replace != core_61::INVALID_ROM_COMMAND_HOOK &&
      hook_observe != core_61::INVALID_ROM_COMMAND_HOOK &&
      core_61::registered_rom_command_hook_count() == 4);

  core_61::enable();
  check_true("different commands fire", ik1302.calls > 0 && ik1303.calls > 0);
  check_true("same command chains", replacer.calls > 0 && observer.calls > 0);
  check_true("registration order", observer.last_replacement == ik1306_alias);
  check_true("hook context arrays",
      ik1302.arrays_present && ik1303.arrays_present &&
      replacer.arrays_present && observer.arrays_present);
  check_true("original address stable",
      replacer.last_address == 0 && observer.last_address == 0);

  check_true("unregister one", core_61::unregister_rom_command_hook(hook_1302));
  check_true("reject stale handle", !core_61::unregister_rom_command_hook(hook_1302));
  ik1302.calls = 0;
  ik1303.calls = 0;
  core_61::enable();
  check_true("removed hook stays off", ik1302.calls == 0);
  check_true("other hook stays on", ik1303.calls > 0);

  check_true("remove IK1303", core_61::unregister_rom_command_hook(hook_1303));
  check_true("remove replacer", core_61::unregister_rom_command_hook(hook_replace));
  check_true("remove observer", core_61::unregister_rom_command_hook(hook_observe));
  check_true("registry empty again", core_61::registered_rom_command_hook_count() == 0);

  RomHookProbe capacity_probes[core_61::ROM_COMMAND_HOOK_CAPACITY] = {};
  core_61::RomCommandHookHandle capacity_hooks[core_61::ROM_COMMAND_HOOK_CAPACITY] = {};
  bool capacity_ok = true;
  for(usize i = 0; i < core_61::ROM_COMMAND_HOOK_CAPACITY; i++) {
    capacity_hooks[i] = core_61::register_rom_command_hook(
        core_61::RomChip::IK1302, (u8) i, &rom_hook_probe, &capacity_probes[i]);
    capacity_ok &= capacity_hooks[i] != core_61::INVALID_ROM_COMMAND_HOOK;
  }
  check_true("public hook capacity", capacity_ok);
  const core_61::RomCommandHookHandle overflow = core_61::register_rom_command_hook(
      core_61::RomChip::IK1303, 0, &rom_hook_probe, &ik1303);
  check_true("capacity enforced", overflow == core_61::INVALID_ROM_COMMAND_HOOK);
  core_61::configure_random_seed(true, 1234567);
  check_true("RNG reserved slot", core_61::random_seed_enabled() &&
      core_61::registered_rom_command_hook_count() == core_61::ROM_COMMAND_HOOK_CAPACITY);
  core_61::configure_random_seed(false, 1);
  for(core_61::RomCommandHookHandle handle : capacity_hooks) {
    check_true("capacity unregister", core_61::unregister_rom_command_hook(handle));
  }
  check_true("capacity cleanup", core_61::registered_rom_command_hook_count() == 0);
}

static void test_pure_helpers(void) {
  std::printf("pure helpers vs <math.h>:\n");
  const double xs[] = {3.14, -3.14, 2.5, -2.5, 0.0, 7.0, -7.0, 123.456, -0.001};
  for(double x : xs) {
    check_near("floor", mk_math::floor(x), std::floor(x), 1e-12);
    check_near("ceil", mk_math::ceil(x), std::ceil(x), 1e-12);
    check_near("trunc", mk_math::trunc(x), std::trunc(x), 1e-12);
    check_near("fabs", mk_math::fabs(x), std::fabs(x), 1e-12);
  }
  check_near("pow10_int+3", mk_math::pow10_int(3), 1000.0, 1e-12);
  check_near("pow10_int-2", mk_math::pow10_int(-2), 0.01, 1e-12);
  check_true("pow10_int max", mk_math::is_inf(mk_math::pow10_int(INT_MAX)));
  check_true("pow10_int min", mk_math::pow10_int(INT_MIN) == 0.0);
  check_true("log10_floor 100", mk_math::log10_floor(100.0) == 2);
  check_true("log10_floor 0.01", mk_math::log10_floor(0.01) == -2);
  check_true("log10_floor 5", mk_math::log10_floor(5.0) == 0);
  check_true("log10_floor 0.5", mk_math::log10_floor(0.5) == -1);

  const char* endp = nullptr;
  check_near("atof int", mk_math::atof("123"), 123.0, 1e-9);
  check_near("atof frac", mk_math::atof("3.14159"), 3.14159, 1e-9);
  check_near("atof sci", mk_math::atof("-1.5e3"), -1500.0, 1e-9);
  check_near("atof huge int", mk_math::atof("123456789012345678901"), 1.2345678901234568e20, 1e-15);
  check_near("atof leading 0", mk_math::atof("0.00000000000000000000125"), 1.25e-21, 1e-15);
  check_true("atof overflow", mk_math::is_inf(mk_math::atof("1e999999")));
  check_true("atof underflow", mk_math::atof("1e-999999") == 0.0);
  check_true("atof zero huge", mk_math::atof("0e999999") == 0.0);
  double v = mk_math::strtod("42.5abc", &endp);
  check_near("strtod value", v, 42.5, 1e-9);
  check_true("strtod endptr", endp != nullptr && *endp == 'a');
  check_true("trunc NaN", mk_math::is_nan(mk_math::trunc(__builtin_nan(""))));
  check_true("floor +Inf", mk_math::is_inf(mk_math::floor(__builtin_huge_val())));
  check_true("pow10 subnormal", mk_math::pow10_int(-309) > 0.0);
  check_true("log10 invalid", mk_math::log10_floor(0.0) == 0);

  const char* huge_end = nullptr;
  const double huge = mk_math::strtod("1e999999999999999999999", &huge_end);
  check_true("strtod huge", std::isinf(huge));
  check_true("strtod huge end", huge_end != nullptr && *huge_end == 0);
  check_true("strtod zero huge", mk_math::atof("0e999999999999999999999") == 0.0);
  check_true("strtod denormal", mk_math::atof("4.940656458e-324") == std::numeric_limits<double>::denorm_min());
  check_near("strtod 20 digits", mk_math::strtod("12345678901234567890", nullptr), 1.2345678901234567e19, 1e-15);
  check_near("strtod long fraction", mk_math::atof("0.1234567890123456789012345"),
             0.12345678901234568, 1e-15);
}

static void test_transcendental(void) {
  std::printf("CORE transcendental vs libm (tol 1e-6):\n");
  const double tol = 1e-6;

  check_near("sin(1)",   mk_math::sin(1.0),   std::sin(1.0),   tol);
  check_near("sin(-0.7)",mk_math::sin(-0.7),  std::sin(-0.7),  tol);
  check_near("cos(1)",   mk_math::cos(1.0),   std::cos(1.0),   tol);
  check_near("cos(2)",   mk_math::cos(2.0),   std::cos(2.0),   tol);
  check_near("tan(0.5)", mk_math::tan(0.5),   std::tan(0.5),   tol);
  check_near("asin(.5)", mk_math::asin(0.5),  std::asin(0.5),  tol);
  check_near("acos(.5)", mk_math::acos(0.5),  std::acos(0.5),  tol);
  check_near("atan(.5)", mk_math::atan(0.5),  std::atan(0.5),  tol);
  check_near("ln(2)",    mk_math::ln(2.0),    std::log(2.0),   tol);
  check_near("ln(10)",   mk_math::ln(10.0),   std::log(10.0),  tol);
  check_near("log10(100)",mk_math::log10(100.0), std::log10(100.0), tol);
  check_near("exp(1)",   mk_math::exp(1.0),   std::exp(1.0),   tol);
  check_near("exp(-2)",  mk_math::exp(-2.0),  std::exp(-2.0),  tol);
  check_near("sqrt(2)",  mk_math::sqrt(2.0),  std::sqrt(2.0),  tol);
  check_near("sqrt(1024)",mk_math::sqrt(1024.0), 32.0,         tol);

  check_near("pow(2,10)", mk_math::pow(2.0, 10.0), 1024.0,      tol);
  check_near("pow(1.5,3)",mk_math::pow(1.5, 3.0),  std::pow(1.5, 3.0), tol);
  check_near("pow(4,0.5)",mk_math::pow(4.0, 0.5),  2.0,         tol);
  check_near("pow(x,0)",  mk_math::pow(7.0, 0.0),  1.0,         tol);
  check_near("pow(-2,3)", mk_math::pow(-2.0, 3.0), -8.0,        tol);

  check_true("sqrt domain", mk_math::is_nan(mk_math::sqrt(-4.0)));
  check_true("ln domain", mk_math::is_nan(mk_math::ln(-1.0)));
  check_true("asin domain", mk_math::is_nan(mk_math::asin(2.0)));
  check_true("input overflow", mk_math::is_nan(mk_math::sin(1e100)));
  check_true("non-finite input", mk_math::is_nan(mk_math::cos(__builtin_huge_val())));
}

static void test_authentic_core_smoke(void) {
  std::printf("authentic ROM/core arithmetic smoke:\n");
  core_61::set_expanded_program_mode(false);
  core_61::enable();
  MK61Emu_SetAngleUnit(DEGREE);

  const MatrixKey key_2 = {4, 1};
  const MatrixKey key_3 = {5, 1};
  const MatrixKey key_enter = {11, 8};
  const MatrixKey key_add = {2, 8};
  press_matrix(key_2);
  press_matrix(key_enter);
  press_matrix(key_3);
  press_matrix(key_add);
  check_near("2 ENTER 3 +", read_live_x(), 5.0, 1e-8);
}

static double first_random(bool enhanced, u32 seed) {
  const MatrixKey key_k = {10, 9};
  const MatrixKey key_bx = {11, 8};
  core_61::configure_random_seed(enhanced, seed);
  core_61::enable();
  press_matrix(key_k);
  press_matrix(key_bx);
  return read_live_x();
}

static double next_random(void) {
  press_matrix({10, 9});
  press_matrix({11, 8});
  return read_live_x();
}

static void test_random_seed_hook(void) {
  std::printf("calculator random seed hook:\n");

  const double authentic_a = first_random(false, 1234567);
  const double authentic_b = first_random(false, 7654321);
  check_near("MK61 repeat", authentic_a, authentic_b, 0.0);

  const double enhanced_a = first_random(true, 1234567);
  const double enhanced_b = first_random(true, 7654321);
  check_true("seed changes RNG", std::fabs(enhanced_a - enhanced_b) > 1e-8);
  check_true("RNG in [0,1)", enhanced_a >= 0.0 && enhanced_a < 1.0 &&
                                  enhanced_b >= 0.0 && enhanced_b < 1.0);

  core_61::configure_random_seed(true, 2468135);
  core_61::enable();
  check_true("enhanced mode enabled", core_61::random_seed_enabled());
  press_matrix({4, 1}); // ordinary key 2 must not expose the hidden stream
  check_near("ordinary key unchanged", read_live_x(), 2.0, 1e-8);

  // A CORE math call borrows and resets the emulator internally. Its snapshot
  // must also preserve the external stream position.
  core_61::configure_random_seed(true, 11223344);
  core_61::enable();
  const double before_math = next_random();
  (void) mk_math::sin(1.0);
  const double after_math = next_random();

  core_61::configure_random_seed(true, 11223344);
  core_61::enable();
  const double reference_first = next_random();
  const double reference_second = next_random();
  check_near("math keeps RNG first", before_math, reference_first, 0.0);
  check_near("math keeps RNG stream", after_math, reference_second, 0.0);

  // The native ROM produced only 179 distinct values (26-value prefix plus a
  // 153-value cycle). Enhanced mode must not inherit that short repetition;
  // tolerate a few birthday collisions in the 7-digit space.
  core_61::configure_random_seed(true, 99887766);
  core_61::enable();
  static constexpr int SAMPLE_COUNT = 256;
  u32 values[SAMPLE_COUNT] = {};
  int unique = 0;
  for(int i = 0; i < SAMPLE_COUNT; i++) {
    const u32 value = (u32) std::llround(next_random() * 10000000.0);
    bool seen = false;
    for(int j = 0; j < unique; j++) seen |= values[j] == value;
    if(!seen) values[unique++] = value;
  }
  check_true("no native short cycle", unique > 240);

  // The built-in RNG recognizer runs after public BEFORE callbacks and follows
  // the final replacement opcode. Replacing 3B with NOP must neither inject nor
  // advance the stream.
  static constexpr u32 REPLACEMENT_SEED = 3141592;
  core_61::configure_random_seed(true, REPLACEMENT_SEED);
  core_61::enable();
  set_x_bcd(0x00000007U);
  CommandHookProbe suppress_rng = {};
  suppress_rng.replace = true;
  suppress_rng.replacement = (u8) MK61_NOP;
  const core_61::Mk61CommandHookHandle suppress_rng_handle =
      core_61::register_mk61_command_hook(
          0x3B, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &suppress_rng);
  (void) next_random();
  check_near("3B->NOP keeps X", read_live_x(), 7.0, 1e-8);
  check_true("remove RNG suppression",
      core_61::unregister_mk61_command_hook(suppress_rng_handle));
  const double after_suppressed = next_random();
  const double unsuppressed_reference = first_random(true, REPLACEMENT_SEED);
  check_near("3B->NOP keeps RNG stream", after_suppressed, unsuppressed_reference, 0.0);

  // Conversely, replacing another command with 3B must arm the same one-shot
  // A7 injection used by a native K RNG command.
  static constexpr u32 REDIRECTED_SEED = 2718281;
  core_61::configure_random_seed(true, REDIRECTED_SEED);
  core_61::enable();
  CommandHookProbe redirect_to_rng = {};
  redirect_to_rng.replace = true;
  redirect_to_rng.replacement = 0x3B;
  const core_61::Mk61CommandHookHandle redirect_handle =
      core_61::register_mk61_command_hook(
          0xD7, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
          &command_hook_probe, &redirect_to_rng);
  press_kip7();
  const double redirected_random = read_live_x();
  check_true("D7->3B produces RNG value",
      redirected_random >= 0.0 && redirected_random < 1.0);
  check_true("remove D7->3B redirect",
      core_61::unregister_mk61_command_hook(redirect_handle));
  const double redirected_reference = first_random(true, REDIRECTED_SEED);
  check_near("D7->3B uses enhanced seed", redirected_random, redirected_reference, 0.0);

  core_61::configure_random_seed(false, 1);
  check_true("enhanced mode disabled", !core_61::random_seed_enabled());
}

static void test_core_boundaries(void) {
  std::printf("core boundary regressions:\n");
  core_61::set_expanded_program_mode(false);
  core_61::enable();

  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
  const char* run_indicator = MK61Emu_GetIndicatorStr(SYMBOLS);
  check_true("RUN indicator bounded", std::strlen(run_indicator) < INDICATOR_STRING_LENGTH);
  check_true("GetComma exported", MK61Emu_GetComma() == core_61::COMMA_RUN_POSITION);

  char update_buffer[INDICATOR_STRING_LENGTH + 2];
  std::memset(update_buffer, 0, sizeof(update_buffer));
  update_buffer[INDICATOR_STRING_LENGTH] = 'A';
  update_buffer[INDICATOR_STRING_LENGTH + 1] = 'B';
  core_61::update_indicator(update_buffer, SYMBOLS);
  check_true("update indicator bounded",
    update_buffer[INDICATOR_STRING_LENGTH] == 'A' &&
    update_buffer[INDICATOR_STRING_LENGTH + 1] == 'B');

  m_IK1302.comma = 10;
  check_true("left comma bounded", std::strlen(MK61Emu_GetIndicatorStr(SYMBOLS)) < INDICATOR_STRING_LENGTH);

  char valid_mantissa[8] = {'1','2','3','4','5','6','7','8'};
  char invalid_mantissa[8] = {'1','2','3','x','5','6','7','8'};
  u8 ring_before[SIZE_RING_M];
  std::memcpy(ring_before, ringM, sizeof(ringM));
  check_true("reject exponent +100", !write_stack_register(stack::X, ' ', valid_mantissa, 100));
  check_true("reject exponent -100", !write_stack_register(stack::X, ' ', valid_mantissa, -100));
  check_true("reject bad BCD digit", !write_stack_register(stack::X, ' ', invalid_mantissa, 0));
  check_true("rejection is atomic", std::memcmp(ring_before, ringM, sizeof(ringM)) == 0);

  char terminated[15];
  std::memset(terminated, 'X', sizeof(terminated));
  read_stack_register(stack::X, terminated, SYMBOLS);
  check_true("stack text terminated", terminated[14] == 0);

  for(int expanded = 0; expanded <= 1; expanded++) {
    core_61::set_expanded_program_mode(expanded != 0);
    core_61::enable();
    u8 input[core_61::CODE_PAGE_BUFFER_SIZE] = {};
    u8 output[core_61::CODE_PAGE_BUFFER_SIZE] = {};
    for(usize i = 0; i < core_61::program_steps(); i++) input[i] = (u8) ((i * 37u + 11u) & 0xFFu);
    core_61::set_code_page(input);
    core_61::get_code_page(output);
    check_true(expanded ? "expanded code page" : "classic code page",
      std::memcmp(input, output, core_61::program_steps()) == 0);
  }

  core_61::set_expanded_program_mode(true);
  core_61::enable();
  ringM[15 * 42 + 21] = 7;
  check_true("R_F seeded", MK61Emu_Read_R_mantissa(15) != 0);
  core_61::clear_memory_registers();
  check_true("R_F cleared", MK61Emu_Read_R_mantissa(15) == 0);
}

static void test_program_boundary_yield(void) {
  std::printf("program command boundary yield:\n");
  core_61::clear_mk61_program_boundary_hook();
  core_61::set_expanded_program_mode(false);
  core_61::enable();

  u8 page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  for(usize i = 0; i < core_61::program_steps(); i++) page[i] = 0x50;
  page[0] = 0x01;
  page[1] = 0x02;
  page[2] = 0x50;
  core_61::set_code_page(page);
  core_61::set_IP(0);

  ProgramBoundaryProbe probe = {};
  probe.target = 0;
  probe.yield = true;
  check_true("boundary hook installed",
      core_61::set_mk61_program_boundary_hook(
          &program_boundary_probe, &probe));
  check_true("second boundary hook rejected",
      !core_61::set_mk61_program_boundary_hook(
          &program_boundary_probe, &probe));

  press_matrix({2, 9}); // C/P
  for(int i = 0; i < 32 && probe.calls == 0; i++) core_61::step();
  check_true("yielded before address 0",
      probe.calls > 0 && probe.last_address == 0 &&
      probe.last_opcode == 0x01 && core_61::program_boundary_yielded());

  const int repeated_before = probe.calls;
  core_61::step();
  check_true("same boundary repeats until resumed",
      probe.calls == repeated_before + 1 && probe.last_address == 0 &&
      probe.last_opcode == 0x01 && core_61::program_boundary_yielded());

  probe.target = 1;
  const int next_before = probe.calls;
  core_61::step();
  check_true("resume reaches following command",
      probe.calls > next_before && probe.last_address == 1 &&
      probe.last_opcode == 0x02 && core_61::program_boundary_yielded());

  core_61::ContextBuffer saved = {};
  check_true("caller context saved", core_61::save_context(saved));
  const i32 saved_ip = core_61::get_IP();
  set_x_bcd(0x12345678U);
  core_61::set_IP(17);
  check_true("caller context restored", core_61::restore_context(saved));
  check_true("boundary IP restored", core_61::get_IP() == saved_ip);

  core_61::clear_mk61_program_boundary_hook();
  check_true("boundary yield flag cleared",
      !core_61::program_boundary_yielded());
  for(int i = 0; i < 64 && core_61::is_RUN(); i++) core_61::step();
  check_true("program finishes after hook removal", core_61::is_CALC());

  // A trap address names the opcode byte. The operand of a two-byte jump is
  // consumed internally and must never surface as its own command boundary.
  core_61::enable();
  for(usize i = 0; i < core_61::program_steps(); i++) page[i] = 0x50;
  page[0] = 0x51; // БП / JMP
  page[1] = 0x02; // destination operand
  page[2] = 0x50;
  core_61::set_code_page(page);
  core_61::set_IP(0);
  probe = {};
  probe.target = 0;
  probe.yield = true;
  check_true("two-byte boundary hook installed",
      core_61::set_mk61_program_boundary_hook(
          &program_boundary_probe, &probe));
  press_matrix({2, 9});
  check_true("two-byte opcode boundary",
      probe.calls > 0 && probe.last_address == 0 &&
      probe.last_opcode == 0x51 && core_61::program_boundary_yielded());
  probe.target = 2;
  core_61::step();
  check_true("two-byte operand is not a boundary",
      probe.last_address == 2 && probe.last_opcode == 0x50 &&
      core_61::program_boundary_yielded());
  core_61::clear_mk61_program_boundary_hook();
}

static void test_save_restore(void) {
  std::printf("core context save/restore isolation:\n");
  core_61::enable();
  MK61Emu_SetAngleUnit(DEGREE);
  core_61::edit_program = true;

  // Load the whole stack with distinct values.
  char mX[8] = {'1','2','3','4','5','0','0','0'}; write_stack_register(stack::X, ' ', mX, 2); // 123.45
  char mY[8] = {'6','7','8','9','0','0','0','0'}; write_stack_register(stack::Y, '-', mY, 0); // -6.789
  char mZ[8] = {'1','1','1','1','1','1','1','1'}; write_stack_register(stack::Z, ' ', mZ, 1); // 11.111111
  char mT[8] = {'9','8','7','6','5','4','3','2'}; write_stack_register(stack::T, ' ', mT, -3); // 0.0098765...

  const double bX = read_live_reg(stack::X);
  const double bY = read_live_reg(stack::Y);
  const double bZ = read_live_reg(stack::Z);
  const double bT = read_live_reg(stack::T);
  // X2 == the screen/display latch, kept separately from stack X.
  char x2_before[24]; std::strncpy(x2_before, MK61Emu_GetIndicatorStr(SYMBOLS), sizeof(x2_before) - 1);
  x2_before[sizeof(x2_before) - 1] = 0;

  // Borrow the core for a normal op and for a domain error (√ of a negative,
  // which latches ЕГГОГ inside the borrow); neither may leak into live state.
  (void) mk_math::sin(1.0);
  (void) mk_math::sqrt(-4.0);

  char x2_after[24]; std::strncpy(x2_after, MK61Emu_GetIndicatorStr(SYMBOLS), sizeof(x2_after) - 1);
  x2_after[sizeof(x2_after) - 1] = 0;

  check_true("angle preserved (DEGREE)", MK61Emu_GetAngleUnit() == DEGREE);
  check_true("edit mode preserved", core_61::edit_program);
  check_near("X preserved", read_live_reg(stack::X), bX, 1e-6);
  check_near("Y preserved", read_live_reg(stack::Y), bY, 1e-6);
  check_near("Z preserved", read_live_reg(stack::Z), bZ, 1e-6);
  check_near("T preserved", read_live_reg(stack::T), bT, 1e-6);
  check_true("X2/display preserved", std::strcmp(x2_before, x2_after) == 0);
}

int main(void) {
  test_pure_helpers();
  test_transcendental();
  test_authentic_core_smoke();
  test_rom_command_hooks();
  test_mk61_command_hooks();
  test_random_seed_hook();
  test_program_boundary_yield();
  test_core_boundaries();
  test_save_restore();

  if(g_failures == 0) {
    std::printf("mk_math_self_test: ok\n");
    return 0;
  }
  std::printf("mk_math_self_test: %d failure(s)\n", g_failures);
  return 1;
}
