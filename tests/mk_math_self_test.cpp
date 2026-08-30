// Хостовый самотест подсистемы CORE в mk_math.
//
// Собирает настоящее ядро МК-61 (mk61emu_core.cpp) вместе с математической
// подсистемой CORE (mk_math_core.cpp) и проверяет совпадение всех трансцендентных
// функций с libm в пределах 8-разрядной точности калькулятора, работу pow(),
// согласованность чистых вспомогательных функций без libm с <math.h> и
// неизменность рабочего пользовательского состояния при аренде ядра.

#include <cmath>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#include "mk_math.hpp"       // MK61_MATH_BACKEND == CORE (задаётся через -D)
#include "mk61emu_core.h"
#include "language_workspace.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"

static int g_failures = 0;

#if MK61_CORE_BODY_PROFILE
struct RankedBody {
  core_61::RomChip chip;
  u8 region;
  u8 microprogram;
  u64 calls;
};

static const char* body_chip_name(core_61::RomChip chip) {
  switch(chip) {
    case core_61::RomChip::IK1302: return "IK02";
    case core_61::RomChip::IK1303: return "IK03";
    case core_61::RomChip::IK1306: return "IK06";
  }
  return "IK??";
}

static void dump_body_profile(void) {
  static constexpr usize TOP_COUNT = 32;
  RankedBody top[TOP_COUNT] = {};
  usize distinct = 0;
  bool rom_bodies[3][core_61::BODY_PROFILE_REGION_COUNT]
                 [core_61::BODY_PROFILE_MICROPROGRAM_COUNT] = {};

  for(u8 chip = 0; chip < 3; chip++) {
    for(usize address = 0; address < 256; address++) {
      const u32 instruction = core_61::rom_command_instruction(
          (core_61::RomChip) chip, (u8) address);
      const u8 body[3] = {
        (u8) instruction,
        (u8) (instruction >> 8),
        (u8) ((u8) (instruction >> 16) > 0x1FU
            ? 0x5FU : (u8) (instruction >> 16))
      };
      for(u8 region = 0; region < 3; region++) {
        if(body[region] < core_61::BODY_PROFILE_MICROPROGRAM_COUNT)
          rom_bodies[chip][region][body[region]] = true;
      }
    }
  }

  usize rom_distinct = 0;
  for(u8 chip = 0; chip < 3; chip++) {
    for(u8 region = 0; region < 3; region++) {
      for(u8 body = 0;
          body < core_61::BODY_PROFILE_MICROPROGRAM_COUNT; body++) {
        if(rom_bodies[chip][region][body]) rom_distinct++;
      }
    }
  }

  for(u8 chip = 0; chip < 3; chip++) {
    for(u8 region = 0; region < core_61::BODY_PROFILE_REGION_COUNT;
        region++) {
      for(u8 microprogram = 0;
          microprogram < core_61::BODY_PROFILE_MICROPROGRAM_COUNT;
          microprogram++) {
        const u64 calls = core_61::body_profile_count(
            (core_61::RomChip) chip, region, microprogram);
        if(calls == 0) continue;
        distinct++;
        for(usize position = 0; position < TOP_COUNT; position++) {
          if(calls <= top[position].calls) continue;
          for(usize move = TOP_COUNT - 1; move > position; move--)
            top[move] = top[move - 1];
          top[position] = {
              (core_61::RomChip) chip, region, microprogram, calls};
          break;
        }
      }
    }
  }

  const u64 total = core_61::body_profile_total();
  std::printf(
      "core body profile: total=%llu observed=%lu rom_distinct=%lu\n",
      (unsigned long long) total, (unsigned long) distinct,
      (unsigned long) rom_distinct);
  u64 cumulative = 0;
  usize bodies_for_90_percent = 0;
  for(usize rank = 0; rank < TOP_COUNT && top[rank].calls != 0; rank++) {
    cumulative += top[rank].calls;
    const double coverage = total == 0
        ? 0.0 : 100.0 * (double) cumulative / (double) total;
    std::printf("  %2lu %-4s r%u mp=%02X calls=%llu cumulative=%6.2f%%\n",
        (unsigned long) (rank + 1), body_chip_name(top[rank].chip),
        (unsigned) (top[rank].region + 1),
        (unsigned) top[rank].microprogram,
        (unsigned long long) top[rank].calls, coverage);
    if(bodies_for_90_percent == 0 && coverage >= 90.0)
      bodies_for_90_percent = rank + 1;
  }
  std::printf("  bodies_for_90_percent=%lu\n",
      (unsigned long) bodies_for_90_percent);
}
#endif

static void check_near(const char* label, double got, double want, double tol) {
  const double diff = std::fabs(got - want);
  const double scale = std::fabs(want) > 1.0 ? std::fabs(want) : 1.0;
  if(!std::isfinite(got) || !std::isfinite(want) ||
     diff > tol * scale) {
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

// Читает любой рабочий регистр стека так же, как интерпретаторы читают X.
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
  u8 addresses[16];
  u8 opcodes[16];
};

static bool program_boundary_probe(
    const core_61::Mk61ProgramBoundaryContext& context, void* user_data) {
  ProgramBoundaryProbe* const probe = (ProgramBoundaryProbe*) user_data;
  if(probe->calls < (int) (sizeof(probe->addresses) / sizeof(probe->addresses[0]))) {
    probe->addresses[probe->calls] = context.address;
    probe->opcodes[probe->calls] = context.opcode;
  }
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
    // bcd_value следует порядку цифр в последовательном кольце (сначала младшая
    // цифра дисплея), поэтому 4.2424242 кодируется как 0x24242424.
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

// Повторяет library_pmk::hidden_press_key(), которая рассчитывает на очистку
// эмулируемой матрицы в core_61::step(), а не на вызов SetKeyPress(0, 0).
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

  // Используем адрес команды IK1306 с тем же словом ПЗУ, что и по адресу 00.
  // Так тест проверяет настоящую подстановку, не меняя поведение сброса.
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

  // The Flash-only test build does not run the SRAM-cache test which happens
  // to initialize the calculator.  Keep this test independent from build
  // options: eval_unary() deliberately refuses to snapshot an uninitialized
  // core whose internal table/ring pointers are still null.
  core_61::enable();

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
  press_matrix({4, 1}); // обычная клавиша 2 не должна раскрывать скрытый поток
  check_near("ordinary key unchanged", read_live_x(), 2.0, 1e-8);

  // Математический вызов CORE арендует и внутренне сбрасывает эмулятор. Его
  // снимок должен также сохранять позицию внешнего потока.
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

  // Штатное ПЗУ выдавало лишь 179 разных значений (префикс из 26 значений и
  // цикл из 153). Улучшенный режим не должен наследовать этот короткий повтор;
  // допускаем несколько коллизий дней рождения в 7-разрядном пространстве.
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

  // Встроенный распознаватель ГСЧ работает после внешних обратных вызовов BEFORE
  // и следует итоговому коду замены. Замена 3B на NOP не должна ни подставлять
  // значение, ни продвигать поток.
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

  // И наоборот, замена другой команды на 3B должна взвести ту же однократную
  // подстановку A7, которая используется штатной командой K RNG.
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

  // Адрес ловушки указывает на байт кода. Операнд двухбайтового перехода
  // используется внутри и не должен появляться как отдельная граница команды.
  core_61::enable();
  for(usize i = 0; i < core_61::program_steps(); i++) page[i] = 0x50;
  page[0] = 0x51; // БП / JMP
  page[1] = 0x02; // операнд назначения
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

  // CALL использует другой путь ПЗУ и действительно показывает последовательный
  // операнд по общему микроадресу предварительной выборки. Но результатом должны
  // быть только настоящие границы кодов: CALL 95, RET по 95, затем HLT по 2.
  core_61::enable();
  for(usize i = 0; i < core_61::program_steps(); i++) page[i] = 0x50;
  page[0] = 0x53; // ПП / CALL
  page[1] = 0x95; // операнд назначения в том виде, как он введён на калькуляторе
  page[2] = 0x50;
  page[95] = 0x52;
  core_61::set_code_page(page);
  core_61::set_IP(0);
  probe = {};
  check_true("CALL boundary hook installed",
      core_61::set_mk61_program_boundary_hook(
          &program_boundary_probe, &probe));
  press_matrix({2, 9});
  for(int i = 0; i < 256 && core_61::is_RUN(); i++) core_61::step();
  check_true("CALL operand is not a boundary",
      probe.calls == 3 &&
      probe.addresses[0] == 0 && probe.opcodes[0] == 0x53 &&
      probe.addresses[1] == 95 && probe.opcodes[1] == 0x52 &&
      probe.addresses[2] == 2 && probe.opcodes[2] == 0x50);
  check_true("CALL program finishes", core_61::is_CALC());
  core_61::clear_mk61_program_boundary_hook();

  // Вложенные вызовы тоже дважды показывают оба операнда; подавление должно
  // следовать стеку возвратов калькулятора, а не помнить лишь последний CALL.
  core_61::enable();
  for(usize i = 0; i < core_61::program_steps(); i++) page[i] = 0x50;
  page[0] = 0x53;
  page[1] = 0x90;
  page[2] = 0x50;
  page[90] = 0x53;
  page[91] = 0x95;
  page[92] = 0x52;
  page[95] = 0x52;
  core_61::set_code_page(page);
  core_61::set_IP(0);
  probe = {};
  check_true("nested CALL boundary hook installed",
      core_61::set_mk61_program_boundary_hook(
          &program_boundary_probe, &probe));
  press_matrix({2, 9});
  for(int i = 0; i < 512 && core_61::is_RUN(); i++) core_61::step();
  check_true("nested CALL operands are not boundaries",
      probe.calls == 5 &&
      probe.addresses[0] == 0 && probe.opcodes[0] == 0x53 &&
      probe.addresses[1] == 90 && probe.opcodes[1] == 0x53 &&
      probe.addresses[2] == 95 && probe.opcodes[2] == 0x52 &&
      probe.addresses[3] == 92 && probe.opcodes[3] == 0x52 &&
      probe.addresses[4] == 2 && probe.opcodes[4] == 0x50);
  check_true("nested CALL program finishes", core_61::is_CALC());
  core_61::clear_mk61_program_boundary_hook();
}

static void test_save_restore(void) {
  std::printf("core context save/restore isolation:\n");
  core_61::enable();
  MK61Emu_SetAngleUnit(DEGREE);
  core_61::edit_program = true;

  // Заполняем весь стек различающимися значениями.
  char mX[8] = {'1','2','3','4','5','0','0','0'}; write_stack_register(stack::X, ' ', mX, 2); // 123.45
  char mY[8] = {'6','7','8','9','0','0','0','0'}; write_stack_register(stack::Y, '-', mY, 0); // -6.789
  char mZ[8] = {'1','1','1','1','1','1','1','1'}; write_stack_register(stack::Z, ' ', mZ, 1); // 11.111111
  char mT[8] = {'9','8','7','6','5','4','3','2'}; write_stack_register(stack::T, ' ', mT, -3); // 0.0098765...

  const double bX = read_live_reg(stack::X);
  const double bY = read_live_reg(stack::Y);
  const double bZ = read_live_reg(stack::Z);
  const double bT = read_live_reg(stack::T);
  // X2 — защёлка экрана/дисплея, хранящаяся отдельно от стека X.
  char x2_before[24]; std::strncpy(x2_before, MK61Emu_GetIndicatorStr(SYMBOLS), sizeof(x2_before) - 1);
  x2_before[sizeof(x2_before) - 1] = 0;

  // Арендуем ядро для обычной операции и ошибки области определения (корня из
  // отрицательного числа, который фиксирует ЕГГОГ внутри аренды); ни одна из них
  // не должна проникнуть в рабочее состояние.
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

static void test_context_slot_arbitration(void) {
  std::printf("core context slot arbitration:\n");
  core_61::ContextBuffer* trap = core_61::acquire_context_buffer(
      core_61::ContextBufferOwner::M61_TRAP);
  check_true("trap acquires shared slot", trap != nullptr);
  check_true("owned slot is stable",
      core_61::owned_context_buffer(
          core_61::ContextBufferOwner::M61_TRAP) == trap);
  check_true("math cannot overwrite trap",
      core_61::acquire_context_buffer(
          core_61::ContextBufferOwner::MATH_CORE) == nullptr);
  check_true("benchmark cannot overwrite trap",
      core_61::acquire_context_buffer(
          core_61::ContextBufferOwner::BENCHMARK) == nullptr);
  check_true("busy math fails without stealing slot",
      std::isnan(mk_math::sin(1.0)) &&
      core_61::owned_context_buffer(
          core_61::ContextBufferOwner::M61_TRAP) == trap);
  check_true("wrong owner cannot release trap",
      !core_61::release_context_buffer(
          core_61::ContextBufferOwner::MATH_CORE));
  check_true("trap releases shared slot",
      core_61::release_context_buffer(
          core_61::ContextBufferOwner::M61_TRAP));
  check_true("released slot has no owner",
      core_61::owned_context_buffer(
          core_61::ContextBufferOwner::M61_TRAP) == nullptr);
  core_61::ContextBuffer* benchmark = core_61::acquire_context_buffer(
      core_61::ContextBufferOwner::BENCHMARK);
  check_true("benchmark reuses released slot", benchmark == trap);
  check_true("benchmark releases shared slot",
      core_61::release_context_buffer(
          core_61::ContextBufferOwner::BENCHMARK));
}

#if MK61_CORE_HOT_TABLES_IN_SRAM > 0
static void test_hot_table_cache_eviction(void) {
  std::printf("core hot-table cache eviction:\n");
  shared_memory::reset_statistics();
  core_61::reset_hot_table_cache_statistics();
  core_61::enable();

  core_61::HotTableCacheSnapshot cache =
      core_61::hot_table_cache_statistics();
  check_true("cache enabled and resident",
      cache.enabled && cache.level == MK61_CORE_HOT_TABLES_IN_SRAM &&
      cache.cached && cache.bytes <= shared_memory::WORKSPACE_SIZE);

  core_61::ContextBuffer start = {};
  core_61::ContextBuffer cached_result = {};
  core_61::ContextBuffer flash_result = {};
  check_true("cache test start saved", core_61::save_context(start));
  static constexpr int STEPS = 37;
  for(int step = 0; step < STEPS; step++) core_61::step();

  // Новый foreground-владелец должен синхронно переключить ядро на Flash,
  // а не получить BUSY и не оставить ни одного указателя в перезаписанной SRAM.
  shared_memory::Lease foreground(
      shared_memory::Arena::WORKSPACE,
      shared_memory::Owner::MARKDOWN_VIEWER,
      shared_memory::WORKSPACE_SIZE);
  check_true("foreground evicts core cache", foreground.ok());
  cache = core_61::hot_table_cache_statistics();
  check_true("cache reports eviction", !cache.cached && cache.evictions == 1);
  check_true("cached result saved after rebase",
      core_61::save_context(cached_result));

  check_true("start restored on Flash", core_61::restore_context(start));
  for(int step = 0; step < STEPS; step++) core_61::step();
  check_true("flash result saved", core_61::save_context(flash_result));
  check_true("SRAM and Flash execution are bit-identical",
      std::memcmp(cached_result.bytes, flash_result.bytes,
                  sizeof(cached_result.bytes)) == 0);
  cache = core_61::hot_table_cache_statistics();
  check_true("busy interval counted as Flash steps",
      cache.flash_steps == STEPS);

  foreground.reset();
  core_61::enable();
  cache = core_61::hot_table_cache_statistics();
  check_true("cache reloads after foreground release",
      cache.cached && cache.loads >= 2);
  const shared_memory::Snapshot workspace =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  check_true("arena records one successful reclaim",
      workspace.reclaim_attempts == 1 && workspace.reclaims == 1 &&
      workspace.reclaim_failures == 0);

  // Returning from a language to the calculator must not leave the core on
  // Flash forever. The complete inactive runtime is first stashed in BULK;
  // only then may the optional table cache replace its resident workspace.
  workspace_swap::discard();
  {
    language_workspace::Lease focal(
        language_workspace::Owner::FOCAL, 512);
    check_true("language evicts table cache", focal.ok() && focal.fresh());
    if(focal.ok()) {
      std::memset(focal.data(), 0, focal.size());
      ((u8*) focal.data())[0] = 0x61;
      ((u8*) focal.data())[511] = 0x5A;
    }
  }
  core_61::enable();
  cache = core_61::hot_table_cache_statistics();
  const workspace_swap::Statistics swap = workspace_swap::statistics();
  check_true("calculator stashes language and reloads cache",
      cache.cached && swap.valid &&
      swap.owner == shared_memory::Owner::FOCAL && swap.raw_size == 512);
  {
    language_workspace::Lease focal(
        language_workspace::Owner::FOCAL, 512);
    check_true("language restores after table-cache eviction",
        focal.ok() && !focal.fresh() &&
        ((const u8*) focal.data())[0] == 0x61 &&
        ((const u8*) focal.data())[511] == 0x5A);
  }
}
#endif

#if MK61_CORE_NATIVE_HOT_PATHS
static bool compare_native_steps(const char* label, bool expanded) {
  core_61::set_expanded_program_mode(expanded);
  core_61::set_native_hot_paths_enabled(false);
  core_61::enable();

  core_61::ContextBuffer start = {};
  core_61::ContextBuffer reference = {};
  core_61::ContextBuffer native = {};
  static const MatrixKey keys[] = {
    {4, 1},   // 2
    {11, 8},  // ENTER
    {5, 1},   // 3
    {2, 8},   // +
    {10, 9},  // K
    {11, 8}   // K-function continuation
  };

  for(usize iteration = 0; iteration < 160; iteration++) {
    const usize phase = iteration %
        (sizeof(keys) / sizeof(keys[0]) * 8U);
    if((phase & 7U) < 4U) {
      const MatrixKey key = keys[phase / 8U];
      MK61Emu_SetKeyPress(key.x, key.y);
    } else {
      MK61Emu_SetKeyPress(0, 0);
    }

    if(!core_61::save_context(start)) {
      std::printf("  FAIL %s: cannot save start at step %lu\n",
          label, (unsigned long) iteration);
      return false;
    }

    core_61::set_native_hot_paths_enabled(false);
    core_61::step();
    if(!core_61::save_context(reference)) {
      std::printf("  FAIL %s: cannot save reference at step %lu\n",
          label, (unsigned long) iteration);
      return false;
    }

    if(!core_61::restore_context(start)) {
      std::printf("  FAIL %s: cannot restore start at step %lu\n",
          label, (unsigned long) iteration);
      return false;
    }
    core_61::set_native_hot_paths_enabled(true);
    core_61::step();
    if(!core_61::save_context(native)) {
      std::printf("  FAIL %s: cannot save native state at step %lu\n",
          label, (unsigned long) iteration);
      return false;
    }

    if(std::memcmp(reference.bytes, native.bytes,
                   sizeof(reference.bytes)) != 0) {
      usize offset = 0;
      while(offset < sizeof(reference.bytes) &&
            reference.bytes[offset] == native.bytes[offset]) offset++;
      std::printf(
          "  FAIL %s: state differs at step %lu byte %lu (%02X != %02X)\n",
          label, (unsigned long) iteration, (unsigned long) offset,
          (unsigned) reference.bytes[offset], (unsigned) native.bytes[offset]);
      return false;
    }

    // Continue from the reference timeline so every comparison starts from a
    // state produced exclusively by the original bit-serial decoder.
    if(!core_61::restore_context(reference)) {
      std::printf("  FAIL %s: cannot continue reference at step %lu\n",
          label, (unsigned long) iteration);
      return false;
    }
  }
  return true;
}

static void test_native_hot_paths(void) {
  std::printf("native microprogram hot paths vs bit-serial reference:\n");
  core_61::reset_native_hot_path_counts();
  check_true("classic full-state differential",
      compare_native_steps("classic", false));
  check_true("expanded full-state differential",
      compare_native_steps("expanded", true));
  check_true("IK06 r1 body 00 exercised",
      core_61::native_hot_path_count(
          core_61::NativeHotPath::IK1306_ZERO_REGION1) > 0);
  check_true("IK06 r2 body 00 exercised",
      core_61::native_hot_path_count(
          core_61::NativeHotPath::IK1306_ZERO_REGION2) > 0);
  check_true("IK06 r3 body 06 exercised",
      core_61::native_hot_path_count(
          core_61::NativeHotPath::IK1306_ADD_S_REGION3) > 0);
  check_true("IK06 r3 body 07 exercised",
      core_61::native_hot_path_count(
          core_61::NativeHotPath::IK1306_ADVANCE_REGION3) > 0);
  check_true("IK06 r3 body 09 exercised",
      core_61::native_hot_path_count(
          core_61::NativeHotPath::IK1306_RESET_REGION3) > 0);
  core_61::set_native_hot_paths_enabled(true);
}
#endif

#if MK61_CORE_PACKED_AMK
static bool compare_packed_amk_steps(const char* label, bool expanded) {
  core_61::set_expanded_program_mode(expanded);
  core_61::set_packed_amk_enabled(false);
  core_61::enable();

  core_61::ContextBuffer start = {};
  core_61::ContextBuffer reference = {};
  core_61::ContextBuffer packed = {};
  static const MatrixKey keys[] = {
    {4, 1}, {11, 8}, {5, 1}, {2, 8}, {10, 9}, {11, 8}
  };

  for(usize iteration = 0; iteration < 160; iteration++) {
    const usize phase = iteration %
        (sizeof(keys) / sizeof(keys[0]) * 8U);
    if((phase & 7U) < 4U) {
      const MatrixKey key = keys[phase / 8U];
      MK61Emu_SetKeyPress(key.x, key.y);
    } else {
      MK61Emu_SetKeyPress(0, 0);
    }

    if(!core_61::save_context(start)) return false;
    core_61::set_packed_amk_enabled(false);
    core_61::step();
    if(!core_61::save_context(reference) ||
       !core_61::restore_context(start)) return false;

    core_61::set_packed_amk_enabled(true);
    core_61::step();
    if(!core_61::save_context(packed)) return false;
    if(std::memcmp(reference.bytes, packed.bytes,
                   sizeof(reference.bytes)) != 0) {
      usize offset = 0;
      while(offset < sizeof(reference.bytes) &&
            reference.bytes[offset] == packed.bytes[offset]) offset++;
      std::printf(
          "  FAIL %s: packed AMK differs at step %lu byte %lu "
          "(%02X != %02X)\n",
          label, (unsigned long) iteration, (unsigned long) offset,
          (unsigned) reference.bytes[offset], (unsigned) packed.bytes[offset]);
      return false;
    }
    if(!core_61::restore_context(reference)) return false;
  }
  return true;
}

static void test_packed_amk(void) {
  std::printf("packed AMK selector vs scalar full state:\n");
  check_true("classic packed-AMK differential",
      compare_packed_amk_steps("classic", false));
  check_true("expanded packed-AMK differential",
      compare_packed_amk_steps("expanded", true));
  core_61::set_packed_amk_enabled(true);
}
#endif

int main(void) {
#if MK61_CORE_HOT_TABLES_IN_SRAM > 0
  test_hot_table_cache_eviction();
#endif
#if MK61_CORE_BODY_PROFILE
  core_61::reset_body_profile();
#endif
  test_pure_helpers();
  test_transcendental();
  test_authentic_core_smoke();
  test_rom_command_hooks();
  test_mk61_command_hooks();
  test_random_seed_hook();
  test_program_boundary_yield();
  test_core_boundaries();
  test_context_slot_arbitration();
  test_save_restore();

#if MK61_CORE_BODY_PROFILE
  dump_body_profile();
#endif
#if MK61_CORE_NATIVE_HOT_PATHS
  test_native_hot_paths();
#endif
#if MK61_CORE_PACKED_AMK
  test_packed_amk();
#endif

  if(g_failures == 0) {
    std::printf("mk_math_self_test: ok\n");
    return 0;
  }
  std::printf("mk_math_self_test: %d failure(s)\n", g_failures);
  return 1;
}
