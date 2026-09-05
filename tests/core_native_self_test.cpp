// Compare the actual decoder with the actual shortcuts, without exporting
// private chip state or adding test code/data to an Arduino build.
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void observe_core_boundary(unsigned cycle, unsigned boundary);
#define MK61_CORE_TEST_BOUNDARY(cycle, boundary) \
  observe_core_boundary(cycle, boundary)
#include "../code/mk61emu_core.cpp"
#undef MK61_CORE_TEST_BOUNDARY

#if !MK61_CORE_NATIVE_HOT_PATHS || MK61_CORE_PACKED_AMK || defined(ARDUINO)
#error This test requires host native paths and the independent scalar decoder
#endif

namespace native_test {
using State = core_61::ContextBuffer;
using Path = core_61::NativeHotPath;
static constexpr unsigned region1[] = {
  0,1,2,3,4,5,3,4,5,3,4,5,3,4,5,3,4,5,3,4,5,3,4,5,6,7,8
};
static unsigned long long body_cases = 0, compared_frames = 0, compared_steps = 0;
static const char* scenario = "initialization";

static void require(bool condition, const char* message) {
  if(!condition) {
    std::fprintf(stderr, "FAIL [%s]: %s\n", scenario, message);
    std::exit(1);
  }
}

static State snapshot() {
  State result = {};
  require(core_61::save_context(result), "cannot save complete core state");
  return result;
}

static bool same(const State& a, const State& b) {
  return std::memcmp(a.bytes, b.bytes, sizeof(a.bytes)) == 0;
}

static void restore(const State& state) {
  require(core_61::restore_context(state), "cannot restore complete core state");
}

static void initialize(bool expanded) {
  core_61::clear_mk61_program_boundary_hook();
  core_61::configure_random_seed(false, 1);
  core_61::set_expanded_program_mode(expanded);
  core_61::set_native_hot_paths_enabled(false);
  MK61Emu_SetAngleUnit(RADIAN);
  core_61::enable();
}

static void native_body(unsigned body) {
  switch(body) {
    case 0: native_ik1306_zero_body(Path::IK1306_ZERO_REGION1); break;
    case 1: native_ik1306_zero_body(Path::IK1306_ZERO_REGION2); break;
    case 2: native_ik1306_region3_06(); break;
    case 3: native_ik1306_region3_07(); break;
    case 4: native_ik1306_region3_09(); break;
    case 5:
      for(unsigned i = 0; i < 27; ++i) native_ik1306_wait_tick(i, region1[i]);
      break;
    default: require(false, "invalid test body");
  }
}

static void decoder_body(unsigned body) {
  if(body == 0 || body == 5) {
    for(unsigned i = 0; i < 27; ++i) IK1306_Tick(i, region1[i]);
  } else {
    const unsigned start = body == 1 ? 27 : 36;
    for(unsigned i = start; i < 42 && (body != 1 || i < 36); ++i)
      IK1306_Tick(i, i - start);
  }
}

static void check_bodies(bool expanded) {
  scenario = expanded ? "expanded body enumeration" : "classic body enumeration";
  initialize(expanded);
  const State clean = snapshot();
  static const unsigned bodies[] = {0, 0, 6, 7, 9, 0x40};
  bool missing_p_caught = false, missing_carry_caught = false;
  bool lost_l_caught = false, wrong_body_caught = false;
  for(unsigned body = 0; body < 6; ++body) {
    for(unsigned pattern = 0; pattern < 4; ++pattern) {
      restore(clean);
      // Different surrounding registers and ring contents, including A..F.
      for(unsigned i = 0; i < sizeof(ringM); ++i)
        ringM[i] = (i * 7 + pattern * 3) & 15;
      for(unsigned i = 0; i < 42; ++i) {
        m_IK1306.R[i] = (i + pattern * 5) & 15;
        m_IK1306.ST[i] = (15 - i * 3 + pattern) & 15;
      }
      m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[bodies[body] * 16];
      m_IK1306.MOD = pattern;
      m_IK1306.T = pattern & 1;
      m_IK1306.flag_FC = (pattern >> 1) & 1;
      m_IK1306.AMK = 67;
      const IK1306 base = m_IK1306;
      std::array<u8, SIZE_RING_M> memory;
      std::memcpy(memory.data(), ringM, sizeof(ringM));
      // All R36/R39/S nibbles and incoming L/P bits, for each surrounding
      // pattern. S1 also visits all 16 nibbles; no decimal-only assumption.
      for(unsigned low = 0; low < 16; ++low)
        for(unsigned high = 0; high < 16; ++high)
          for(unsigned s = 0; s < 16; ++s)
            for(unsigned flags = 0; flags < 4; ++flags) {
              m_IK1306 = base;
              m_IK1306.R[36] = low;
              m_IK1306.R[39] = high;
              m_IK1306.S = s;
              m_IK1306.S1 = (low + high + s + pattern) & 15;
              m_IK1306.L = flags & 1;
              m_IK1306.P = flags >> 1;
              if(body == 5) {
                ringM[(m_IK1306.pM - ringM) + 22] = low;
                memory[(m_IK1306.pM - ringM) + 22] = low;
              }
              const IK1306 before = m_IK1306;
              decoder_body(body);
              const State reference = snapshot();
              m_IK1306 = before;
              std::memcpy(ringM, memory.data(), sizeof(ringM));
              native_body(body);
              const State actual = snapshot();
              if(!same(reference, actual)) {
                std::fprintf(stderr,
                    "body=%u pattern=%u R36=%X R39=%X S=%X L/P=%u\n",
                    body, pattern, low, high, s, flags);
                require(false, "native body differs from scalar microticks");
              }
              ++body_cases;

              // Deliberately broken executions must fail the same comparator.
              if(body == 0 && before.P && !missing_p_caught) {
                m_IK1306.P = before.P; // omit the zero body's P clear
                missing_p_caught = !same(reference, snapshot());
                m_IK1306.P = 0;
              }
              if(body == 2 && low + s > 15 && !missing_carry_caught) {
                m_IK1306.R[39] = high; // discard carry into the high nibble
                missing_carry_caught = !same(reference, snapshot());
              }
              if(body == 4 && before.L && !lost_l_caught) {
                m_IK1306.L = 0; // reset must preserve L
                lost_l_caught = !same(reference, snapshot());
              }
              if(body == 2 && !wrong_body_caught) {
                m_IK1306 = before;
                native_body(0); // shortcut selected for the wrong body
                wrong_body_caught = !same(reference, snapshot());
              }
            }
    }
  }
  require(missing_p_caught && missing_carry_caught && lost_l_caught && wrong_body_caught,
      "body comparator failed to detect an injected defect");
  std::printf("PASS %s: 393216 cases; 4 body mutants detected\n", scenario);
}

static void check_wait_timing(bool expanded) {
  scenario = expanded ? "expanded wait timing" : "classic wait timing";
  initialize(expanded);
  const State clean = snapshot();
  unsigned cases = 0;
  bool late_read_caught = false, late_wake_caught = false;
  // Independently change each sampled nibble immediately before/on/after its
  // actual read. Compare every microtick, not just the end of the 27-tick body.
  for(unsigned position = 1; position <= 22; position += 3)
    for(int delta : {-1, 0, 1})
      for(unsigned initial = 0; initial < 16; ++initial)
        for(unsigned incoming = 0; incoming < 16; ++incoming)
          for(unsigned mod : {0U, 1U}) {
            restore(clean);
            m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[0x40 * 16];
            m_IK1306.MOD = mod;
            m_IK1306.pM[position] = initial;
            m_IK1306.R[36] = 1;
            m_IK1306.R[39] = 0;
            const State start = snapshot();
            std::array<State, 27> trace;
            const unsigned change = position + delta;
            for(unsigned i = 0; i < 27; ++i) {
              if(i == change) m_IK1306.pM[position] = incoming;
              IK1306_Tick(i, region1[i]);
              trace[i] = snapshot();
            }
            // A whole waiting command leaves ASP=01 until S reports a wake.
            m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[0];
            decoder_body(1);
            m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[6 * 16];
            decoder_body(2);
            const State end = snapshot();

            restore(start);
            for(unsigned i = 0; i < 27; ++i) {
              if(i == change) m_IK1306.pM[position] = incoming;
              native_ik1306_wait_tick(i, region1[i]);
              require(same(trace[i], snapshot()), "wait differs at a signal read microtick");
              if(position == 22 && initial == 0 && incoming == 15 && mod == 0) {
                if(delta == 1 && i == 23) {
                  const u32 s = m_IK1306.S;
                  m_IK1306.S = m_IK1306.pM[22]; // wrongly sample one tick late
                  late_read_caught |= !same(trace[i], snapshot());
                  m_IK1306.S = s;
                }
                if(delta == 0 && i == 25) {
                  const u32 s = m_IK1306.S;
                  m_IK1306.S = 0; // defer the wake flag past its required tick
                  late_wake_caught |= !same(trace[i], snapshot());
                  m_IK1306.S = s;
                }
              }
            }
            m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[0];
            native_body(1);
            m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[6 * 16];
            native_body(2);
            require(same(end, snapshot()), "wait left a different next ROM address");
            if(position == 22) {
              const unsigned sampled = delta <= 0 ? incoming : initial;
              require(m_IK1306.R[36] == (sampled == 15 ? 2 : 1),
                  "wake occurred on the wrong side of the flag read");
            }
            ++cases;
          }
  require(late_read_caught && late_wake_caught, "timing comparator missed a delayed signal");
  std::printf("PASS %s: %u transitions, every microtick; late read/wake mutants detected\n",
      scenario, cases);
}

enum class Fault { NONE, TRANSIENT_P, RING_PHASE, DELAY_YIELD };
struct DetectedFault {};
struct Frame {
  std::array<u32, 6> event;
  State state;
  bool yielded;
  bool program_dispatching;
  u8 rom_depth, command_depth;
};
static std::vector<Frame> reference_trace;
static unsigned trace_mode = 0; // 0: off, 1: recording, 2: comparing
static usize trace_position = 0;
static bool mismatch = false, fault_applied = false;
static Fault fault = Fault::NONE;
static int yield_address = -1;
static unsigned long long command_events[2][2] = {}, rom_events[3] = {}, yields = 0;
static std::vector<u8> program_addresses;

static void observe(std::array<u32, 6> event) {
  if(trace_mode == 0) return;
  Frame current = {event, snapshot(), core_61::program_boundary_yielded(),
      mk61_program_boundary_dispatching, rom_command_hook_dispatch_depth,
      mk61_command_hook_dispatch_depth};
  if(trace_mode == 1) {
    reference_trace.push_back(current);
    return;
  }
  bool equal = trace_position < reference_trace.size();
  if(equal) {
    const Frame& expected = reference_trace[trace_position];
    equal = expected.event == current.event && expected.yielded == current.yielded &&
        expected.program_dispatching == current.program_dispatching &&
        expected.rom_depth == current.rom_depth && expected.command_depth == current.command_depth &&
        same(expected.state, current.state);
  }
  if(!equal && !mismatch && fault == Fault::NONE) {
    std::fprintf(stderr, "first mismatch: step=%llu frame=%lu kind=%u cycle=%u boundary=%u\n",
        compared_steps, (unsigned long) trace_position, event[0], event[1], event[2]);
  }
  mismatch |= !equal;
  ++trace_position;
  // Stop a corrupted transport before it can create out-of-range pointers.
  // The P mutant deliberately continues to prove that step-end equality is
  // insufficient even when execution naturally repairs the transient value.
  if(!equal && fault != Fault::NONE && fault != Fault::TRANSIENT_P)
    throw DetectedFault{};
}

static void command_hook(core_61::Mk61CommandHookContext& context, void*) {
  if(trace_mode == 1) ++command_events[(unsigned) context.source][(unsigned) context.phase];
  observe({1, (u32) context.phase, (u32) context.source, context.opcode,
      context.replacement_opcode, context.sequence});
}

static void rom_hook(core_61::RomCommandHookContext& context, void*) {
  if(trace_mode == 1) ++rom_events[(unsigned) context.chip];
  observe({2, (u32) context.chip, context.address, context.replacement_address, 0, 0});
}

static bool program_hook(const core_61::Mk61ProgramBoundaryContext& context, void*) {
  bool stop = context.address == yield_address;
  if(trace_mode == 1) program_addresses.push_back(context.address);
  if(trace_mode == 2 && fault == Fault::DELAY_YIELD && stop && !fault_applied) {
    stop = false;
    fault_applied = true;
  }
  if(trace_mode == 1 && stop) ++yields;
  observe({3, context.address, context.opcode, (u32) stop, 0, 0});
  return stop;
}

static void compare_step(Fault injected = Fault::NONE) {
  const State start = snapshot();
  require(!mk61_program_boundary_dispatching && rom_command_hook_dispatch_depth == 0 &&
      mk61_command_hook_dispatch_depth == 0, "test step started inside a callback");
  reference_trace.clear();
  core_61::set_native_hot_paths_enabled(false);
  trace_mode = 1;
  core_61::step();
  observe({4, 0, 0, 0, 0, 0});
  const State end = snapshot();
  const bool end_yielded = core_61::program_boundary_yielded();

  trace_mode = 0;
  restore(start);
  core_61::set_native_hot_paths_enabled(true);
  trace_position = 0;
  mismatch = fault_applied = false;
  fault = injected;
  trace_mode = 2;
  try {
    core_61::step();
    observe({4, 0, 0, 0, 0, 0});
  } catch(const DetectedFault&) {
    // Expected only for deliberately injected defects in this host test.
    mk61_program_boundary_dispatching = false;
    rom_command_hook_dispatch_depth = mk61_command_hook_dispatch_depth = 0;
  }
  trace_mode = 0;
  mismatch |= trace_position != reference_trace.size();
  if(injected == Fault::NONE) {
    require(!mismatch, "boundary state or event ordering differs");
  } else {
    require(fault_applied && mismatch, "trace comparator missed an injected defect");
    if(injected == Fault::TRANSIENT_P)
      require(same(end, snapshot()), "transient mutant did not disappear by step end");
  }
  compared_frames += trace_position;
  ++compared_steps;
  fault = Fault::NONE;
  // Follow only the decoder's trajectory, never the candidate's history.
  restore(end);
  mk61_program_boundary_yielded = end_yielded;
  core_61::set_native_hot_paths_enabled(false);
}
} // namespace native_test

static void observe_core_boundary(unsigned cycle, unsigned boundary) {
  using namespace native_test;
  if(trace_mode == 2 && !fault_applied) {
    if(fault == Fault::TRANSIENT_P && boundary == 27) {
      // A no-op tick in the next region clears P again. Step-end comparison
      // alone misses this defect; the region boundary must catch it.
      m_IK1306.P ^= 1;
      fault_applied = true;
    } else if(fault == Fault::RING_PHASE && boundary == 43) {
      const usize offset = m_IK1306.pM - ringM;
      m_IK1306.pM = &ringM[(offset + core_61::ring_size() - 42) % core_61::ring_size()];
      fault_applied = true;
    }
  }
  observe({0, cycle, boundary, 0, 0, 0});
}

namespace native_test {
static void press(unsigned x, unsigned y) {
  core_61::clear_displayed();
  for(unsigned i = 0; i < 4; ++i) {
    MK61Emu_SetKeyPress(x, y);
    compare_step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0, 0);
  for(unsigned i = 0; i < 512; ++i) {
    compare_step();
    if(core_61::is_RUN() || core_61::is_displayed()) return;
  }
  require(false, "keyboard operation did not settle");
}

static void program(const u8* code, usize size) {
  std::array<u8, core_61::CODE_PAGE_BUFFER_SIZE> page;
  page.fill(0x50);
  require(size <= core_61::program_steps(), "test program too long");
  std::memcpy(page.data(), code, size);
  core_61::set_code_page(page.data());
  core_61::set_IP(0);
}

static void finish_program() {
  for(unsigned i = 0; i < 256 && core_61::is_RUN(); ++i) compare_step();
  require(!core_61::is_RUN(), "program did not stop");
}

struct BranchEvents {
  unsigned operand_commands = 0;
  std::vector<u8> completed_at;
};

static void branch_command_hook(core_61::Mk61CommandHookContext& context, void* data) {
  command_hook(context, nullptr);
  if(trace_mode != 1 || context.source != core_61::Mk61CommandSource::PROGRAM) return;
  auto& events = *static_cast<BranchEvents*>(data);
  if(context.opcode == 0x09) ++events.operand_commands;
  if(context.phase == core_61::Mk61CommandHookPhase::AFTER_EXECUTE)
    events.completed_at.push_back(core_61::get_IP());
}

static void check_branch_operands(bool expanded) {
  scenario = expanded ? "expanded branch operands" : "classic branch operands";
  // An operand equal to opcode 09 must not invoke its command hook. AFTER
  // for the branch must wait for the destination/fall-through, not the operand.
  for(u8 opcode : {0x51, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E}) {
    for(int value : {-1, 0, 1}) {
      initialize(expanded);
      require(write_stack_register(stack::X, value < 0 ? '-' : ' ',
          value == 0 ? "00000000" : "10000000", 0), "cannot seed branch input");
      const u8 code[] = {opcode, 0x09, 0x50, 0, 0, 0, 0, 0, 0, 0x50};
      program(code, sizeof(code));
      BranchEvents events;
      auto operand_hook = core_61::register_mk61_command_hook(0x09,
          core_61::Mk61CommandHookPhase::BEFORE_EXECUTE, branch_command_hook, &events);
      auto after_hook = core_61::register_mk61_command_hook(opcode,
          core_61::Mk61CommandHookPhase::AFTER_EXECUTE, branch_command_hook, &events);
      require(operand_hook != 0 && after_hook != 0, "cannot register branch command hooks");
      require(core_61::set_mk61_program_boundary_hook(program_hook), "cannot register branch boundary hook");
      yield_address = -1;
      program_addresses.clear();
      press(2, 9);
      finish_program();
      if(program_addresses.size() != 2 || program_addresses[0] != 0 ||
          (program_addresses[1] != 2 && program_addresses[1] != 9)) {
        std::fprintf(stderr, "opcode=%02X X=%d addresses:", opcode, value);
        for(u8 address : program_addresses) std::fprintf(stderr, " %u", address);
        std::fprintf(stderr, "\n");
        require(false, "direct branch exposed an operand or lost a command");
      }
      require(events.operand_commands == 0, "branch operand invoked a command hook");
      require(events.completed_at == std::vector<u8>({program_addresses.back()}),
          "branch AFTER fired before the address operand was consumed");
      require(core_61::unregister_mk61_command_hook(operand_hook) &&
          core_61::unregister_mk61_command_hook(after_hook), "cannot unregister branch hooks");
    }
  }
  // The same address is first data, then executable code: skip it only once.
  initialize(expanded);
  const u8 into_operand[] = {0x51, 0x01, 0x50};
  program(into_operand, sizeof(into_operand));
  require(core_61::set_mk61_program_boundary_hook(program_hook), "cannot register self-target hook");
  program_addresses.clear();
  press(2, 9);
  finish_program();
  require(program_addresses == std::vector<u8>({0, 1, 2}),
      "jump to its own operand lost the real command at that address");

  // A pending jump operand must not consume a slot in the five CALL frames.
  initialize(expanded);
  std::array<u8, 61> nested;
  nested.fill(0x50);
  for(unsigned address = 0; address <= 40; address += 10) {
    nested[address] = 0x53;
    nested[address + 1] = (u8) (((address + 10) / 10) << 4);
    if(address != 0) nested[address + 2] = 0x52;
  }
  nested[50] = 0x51; nested[51] = 0x60; nested[60] = 0x52;
  program(nested.data(), nested.size());
  require(core_61::set_mk61_program_boundary_hook(program_hook), "cannot register nested jump hook");
  program_addresses.clear();
  press(2, 9);
  finish_program();
  require(program_addresses == std::vector<u8>({0, 10, 20, 30, 40, 50, 60, 42, 32, 22, 12, 2}),
      "JMP inside five CALL frames lost a boundary or exposed an operand");

  // Pending input must survive cold context save/restore independently of
  // the active command flag; its maximum address uses all seven packed bits.
  const State clean = snapshot();
  for(bool active : {false, true}) {
    mk61_jump_operand = (u8) core_61::program_steps();
    active_mk61_command.active = active;
    const State pending = snapshot();
    mk61_jump_operand = 0;
    active_mk61_command.active = !active;
    restore(pending);
    require(mk61_jump_operand == core_61::program_steps() &&
        active_mk61_command.active == active, "pending branch operand was not restored");
  }
  restore(clean);
  core_61::clear_mk61_program_boundary_hook();
  std::printf("PASS %s: 27 branch inputs, self-target, five CALL frames, AFTER timing, context restoration\n", scenario);
}

static void check_scenarios(bool expanded) {
  scenario = expanded ? "expanded boundary traces" : "classic boundary traces";
  initialize(expanded);
  core_61::reset_native_hot_path_counts();
  const auto steps_before = compared_steps, frames_before = compared_frames;
  std::vector<core_61::Mk61CommandHookHandle> commands;
  for(u8 opcode : {0x01, 0x02, 0x10, 0x50, 0x53, 0x52})
    for(auto phase : {core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
                      core_61::Mk61CommandHookPhase::AFTER_EXECUTE}) {
      auto handle = core_61::register_mk61_command_hook(opcode, phase, command_hook);
      require(handle != core_61::INVALID_MK61_COMMAND_HOOK, "command hook registration failed");
      commands.push_back(handle);
    }
  // Observe the next command on each chip, guaranteeing each hook is exercised.
  std::vector<core_61::RomCommandHookHandle> rom_hooks;
  const u8 addresses[] = {
    (u8) (m_IK1302.R[36] + 16 * m_IK1302.R[39]),
    (u8) (m_IK1303.R[36] + 16 * m_IK1303.R[39]),
    (u8) (m_IK1306.R[36] + 16 * m_IK1306.R[39])
  };
  for(unsigned chip = 0; chip < 3; ++chip) {
    auto handle = core_61::register_rom_command_hook(
        (core_61::RomChip) chip, addresses[chip], rom_hook);
    require(handle != core_61::INVALID_ROM_COMMAND_HOOK, "ROM hook registration failed");
    rom_hooks.push_back(handle);
  }
  compare_step();
  compare_step(Fault::TRANSIENT_P);
  compare_step(Fault::RING_PHASE);

  // Arithmetic, stack, register store/recall, held/released keys.
  press(4, 1); // 2
  press(11, 8); // ENTER
  press(5, 1); // 3
  press(2, 8); // +
  press(6, 9); press(7, 1); // X->P5
  press(8, 9); press(7, 1); // P5->X

  // Transcendentals use ROM behavior exactly, with no libm/tolerance oracle.
  for(AngleUnit angle : {RADIAN, DEGREE, GRADE}) {
    initialize(expanded);
    MK61Emu_SetAngleUnit(angle);
    press(3, 1); press(2, 1); // 10
    press(11, 9); press(8, 1); // F atan
    if(angle == RADIAN) {
      core_61::bcd_value x = {};
      core_61::get_stack_register(stack::X, x);
      // Existing decoder regression fixture, not a new hardware measurement.
      // The public packed BCD stores the leading digit in the low nibble:
      // 0x67211741 is the mantissa 1.4711276.
      if(x.mantissa != 0x67211741 || x.signs_and_pow != 0)
        std::fprintf(stderr, "atan(10): mantissa=%08X signs/power=%04X\n",
            x.mantissa, x.signs_and_pow);
      require(x.mantissa == 0x67211741 && x.signs_and_pow == 0,
          "atan(10) no longer matches the existing ROM decoder result");
    }
    press(11, 9); press(9, 1); // F sin
    press(11, 9); press(3, 1); // F exp
  }

  // Division by zero and recovery through Cx exercise the ROM error path.
  initialize(expanded);
  press(3, 1); press(11, 8); press(2, 1); press(5, 8); // 1 ENTER 0 /
  // The displayed flag can still describe the previous X while this slow
  // ROM operation runs. Wait for the error itself, comparing every step.
  for(unsigned i = 0; i < 512 && !core_61::has_error(); ++i) compare_step();
  if(!core_61::has_error()) {
    std::fprintf(stderr, "division indicator nibbles:");
    for(auto pos : indicator_pos) std::fprintf(stderr, " %X", m_IK1302.R[pos]);
    std::fprintf(stderr, "\n");
  }
  require(core_61::has_error(), "division by zero did not reach the ROM error state");
  press(10, 8); // Cx
  for(unsigned i = 0; i < 512 && core_61::has_error(); ++i) compare_step();
  require(!core_61::has_error(), "Cx did not recover from the ROM error state");
  press(4, 1);

  // Real program boundaries: halt, repeated halt, resume one command, finish.
  initialize(expanded);
  const u8 simple[] = {0x01, 0x02, 0x50};
  program(simple, sizeof(simple));
  yield_address = 0;
  require(core_61::set_mk61_program_boundary_hook(program_hook), "boundary hook registration failed");
  press(2, 9);
  for(unsigned i = 0; i < 32 && !core_61::program_boundary_yielded(); ++i) compare_step();
  require(core_61::program_boundary_yielded() && core_61::get_IP() == 0,
      "program did not yield before its first command");
  compare_step();
  compare_step(Fault::DELAY_YIELD);
  yield_address = 1;
  for(unsigned i = 0; i < 32 && core_61::get_IP() != 1; ++i) compare_step();
  require(core_61::program_boundary_yielded() && core_61::get_IP() == 1,
      "resume did not yield before the next command");
  yield_address = -1;
  finish_program();

  // CALL/RETURN and an absolute jump: operands must never become hook events.
  initialize(expanded);
  const u8 branches[] = {0x53, 0x06, 0x51, 0x09, 0x00, 0x00, 0x01, 0x52, 0x00, 0x50};
  program(branches, sizeof(branches));
  require(core_61::set_mk61_program_boundary_hook(program_hook), "branch hook registration failed");
  program_addresses.clear();
  press(2, 9);
  finish_program();
  const std::vector<u8> correct_boundaries = {0, 6, 7, 2, 9};
  if(program_addresses != correct_boundaries) {
    std::fprintf(stderr, "branch command addresses:");
    for(u8 address : program_addresses) std::fprintf(stderr, " %u", address);
    std::fprintf(stderr, "\n");
    require(false, "CALL/RETURN/JMP command boundary order is wrong");
  }
  core_61::clear_mk61_program_boundary_hook();

  // Independent deterministic key timing, including short pulses, long holds,
  // F/K prefixes and invalid matrix coordinates (released by the core API).
  initialize(expanded);
  const unsigned keys[][2] = {{2,1}, {3,1}, {11,8}, {2,8}, {11,9}, {10,9}, {8,1}, {0,0}, {99,99}};
  u32 random = 0x61C0FFEE;
  for(unsigned i = 0; i < 96; ++i) {
    random = random * 1664525U + 1013904223U;
    const auto& key = keys[(random >> 16) % (sizeof(keys) / sizeof(keys[0]))];
    MK61Emu_SetKeyPress(key[0], key[1]);
    compare_step();
  }
  for(unsigned i = 0; i < (unsigned) Path::COUNT; ++i) {
    const auto count = core_61::native_hot_path_count((Path) i);
    require(count != 0, "a native path was not exercised by integrated scenarios");
    std::printf("  native path %u: %llu calls\n", i, (unsigned long long) count);
  }
  for(auto handle : commands)
    require(core_61::unregister_mk61_command_hook(handle), "command hook removal failed");
  for(auto handle : rom_hooks)
    require(core_61::unregister_rom_command_hook(handle), "ROM hook removal failed");
  std::printf("PASS %s: %llu steps, %llu state/event frames; 3 trace mutants detected\n",
      scenario, compared_steps - steps_before, compared_frames - frames_before);
}
} // namespace native_test

int main() {
  using namespace native_test;
  std::setvbuf(stdout, nullptr, _IONBF, 0);
  for(bool expanded : {false, true}) {
    check_bodies(expanded);
    check_wait_timing(expanded);
    check_scenarios(expanded);
    check_branch_operands(expanded);
  }
  for(unsigned source = 0; source < 2; ++source)
    for(unsigned phase = 0; phase < 2; ++phase)
      require(command_events[source][phase] != 0, "command event source/phase not covered");
  for(auto count : rom_events) require(count != 0, "ROM hook for a chip not covered");
  require(yields != 0, "program yield events not covered");
  std::printf("PASS native verification: %llu body cases, %llu steps, %llu frames; "
      "9 defect types detected in both ring modes\n", body_cases, compared_steps, compared_frames);
  return 0;
}
