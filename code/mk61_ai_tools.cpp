#include "mk61emu_core.h"

#include "mk61_ai_harness.hpp"
#include "mk61_ref.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace mk61ai {
namespace {
struct Run {
  unsigned count = 0, limit = 0, trace_count = 0;
  bool limited = false;
  Trace *trace = nullptr;
  static bool boundary(const core_61::Mk61ProgramBoundaryContext &c,
                       void *context) {
    auto &r = *static_cast<Run *>(context);
    if (r.count >= r.limit) {
      r.limited = true;
      return true;
    }
    ++r.count;
    if (r.trace) {
      if (r.trace_count == 16) {
        std::memmove(r.trace, r.trace + 1, 15 * sizeof(Trace));
        --r.trace_count;
      }
      auto &e = r.trace[r.trace_count++];
      e.pc = c.address;
      e.opcode = c.opcode;
      if (!mk61_ref::try_read_stack_number(stack::X, e.x))
        e.x = NAN;
    }
    return false;
  }
};
bool set_inputs(const Example &e) {
  for (unsigned i = 0; i < INPUT_COUNT; ++i)
    if (e.inputs & (1U << i)) {
      const mk61_ref::Ref ref =
          i < 15 ? mk61_ref::Ref{mk61_ref::Kind::R, std::uint8_t(i)}
                 : mk61_ref::Ref{
                       mk61_ref::Kind(unsigned(mk61_ref::Kind::X) + i - 15), 0};
      if (!mk61_ref::write(ref, e.values[i]))
        return false;
    }
  return true;
}
} // namespace
Result execute(const Program &program, const Example &example,
               std::uint32_t revision, bool (*service)(void *), void *context,
               Trace *trace, unsigned *trace_count) {
  Result result{};
  result.version = program.version;
  result.task_revision = revision;
  result.test_revision = example.revision;
  result.status = Execution::INVALID;
  if (trace_count)
    *trace_count = 0;
  if (!valid_program(program) || !example.max_commands || !example.max_frames ||
      example.angle > 2 || example.scenario_count > SCENARIO_STEPS)
    return result;
  core_61::ContextBuffer live{}, scratch{};
  if (core_61::is_RUN() || core_61::active_program_bank() != 0 ||
      core_61::registered_mk61_command_hook_count() ||
      !core_61::save_context(live)) {
    result.status = Execution::BUSY;
    return result;
  }
  if (service && !service(context)) {
    result.status = Execution::CANCELLED;
    return result;
  }
  Run run{};
  run.limit = std::min(unsigned(example.max_commands), 4096U);
  run.trace = trace;
  if (!core_61::set_mk61_program_boundary_hook(Run::boundary, &run)) {
    result.status = Execution::BUSY;
    return result;
  }
  bool owns_hook = true, checks = true;
  unsigned frames = 0;
  const unsigned maximum = std::min(unsigned(example.max_frames), 16384U);
  auto ref = [](unsigned i) {
    return i < 15
               ? mk61_ref::Ref{mk61_ref::Kind::R, std::uint8_t(i)}
               : mk61_ref::Ref{
                     mk61_ref::Kind(unsigned(mk61_ref::Kind::X) + i - 15), 0};
  };
  auto read = [&](unsigned i) {
    double value = NAN;
    mk61_ref::read(ref(i), value);
    return value;
  };
  auto matches = [&](double actual, double expected) {
    return std::isfinite(actual) && std::isfinite(expected) &&
           std::fabs(actual - expected) <=
               std::max(example.absolute,
                        std::fabs(expected) * example.relative);
  };
  auto check = [&](unsigned i, double expected, unsigned stage) {
    if (!matches(read(i), expected)) {
      checks = false;
      result.mismatch |= 1U << i;
      if (result.failed_stage == 255)
        result.failed_stage = std::uint8_t(stage);
    }
  };
  auto frame = [&]() {
    if (frames >= maximum || run.limited) {
      result.status = Execution::LIMIT;
      return false;
    }
    core_61::step();
    ++frames;
    if (run.limited) {
      result.status = Execution::LIMIT;
      return false;
    }
    if (service && (frames & 3U) == 0) {
      if (!core_61::save_context(scratch)) {
        result.status = Execution::ERROR;
        return false;
      }
      core_61::clear_mk61_program_boundary_hook();
      owns_hook = false;
      if (!core_61::restore_context(live)) {
        result.status = Execution::ERROR;
        return false;
      }
      if (!service(context)) {
        result.status = Execution::CANCELLED;
        return false;
      }
      if (!core_61::set_mk61_program_boundary_hook(Run::boundary, &run)) {
        result.status = Execution::BUSY;
        return false;
      }
      owns_hook = true;
      if (!core_61::restore_context(scratch)) {
        result.status = Execution::ERROR;
        return false;
      }
    }
    return true;
  };
  auto press = [&](unsigned key) {
    if (!(key >> 4) || (key >> 4) > 11 || !(key & 15) || (key & 15) > 9) {
      result.status = Execution::INVALID;
      return false;
    }
    core_61::clear_displayed();
    MK61Emu_SetKeyPress(key >> 4, key & 15);
    bool ok = true;
    for (unsigned i = 0; i < 4; ++i) {
      if (!frame()) {
        ok = false;
        break;
      }
      if (core_61::is_RUN())
        break;
    }
    MK61Emu_SetKeyPress(0, 0);
    return ok;
  };
  auto stopped = [&]() {
    while (core_61::is_RUN() || !core_61::is_displayed())
      if (!frame())
        return false;
    result.status =
        core_61::has_error() ? Execution::ERROR : Execution::STOPPED;
    return result.status == Execution::STOPPED;
  };
  core_61::set_expanded_program_mode(false);
  core_61::configure_random_seed(false, 1);
  core_61::enable();
  MK61Emu_SetAngleUnit(example.angle == 0   ? DEGREE
                       : example.angle == 2 ? GRADE
                                            : RADIAN);
  std::uint8_t page[core_61::CODE_PAGE_BUFFER_SIZE];
  std::memset(page, 0x50, sizeof(page));
  std::memcpy(page, program.bytes, program.size);
  core_61::set_code_page(page);
  core_61::set_IP(0);
  double initial[INPUT_COUNT]{};
  bool ok = set_inputs(example);
  for (unsigned i = 0; i < INPUT_COUNT; ++i)
    if (example.preserve & (1U << i))
      initial[i] = read(i);
  if (ok)
    ok = press(0x29) && stopped();
  if (ok) {
    const auto mask = expectation_mask(example);
    for (unsigned i = 0; i < INPUT_COUNT; ++i)
      if (mask & (1U << i))
        check(i, expected_value(example, i), 0);
    ok = checks;
    for (unsigned j = 0; j < example.scenario_count && ok; ++j) {
      const auto &step = example.scenario[j];
      if (step.input_index != 255 &&
          (step.input_index >= INPUT_COUNT ||
           !mk61_ref::write(ref(step.input_index), step.input))) {
        result.status = Execution::INVALID;
        ok = false;
        break;
      }
      ok = press(step.key) && stopped();
      if (!ok)
        break;
      if (step.output_index != 255) {
        if (step.output_index >= INPUT_COUNT) {
          result.status = Execution::INVALID;
          ok = false;
          break;
        }
        result.stage_values[j] = read(step.output_index);
        check(step.output_index, step.expected, j + 1);
      }
      result.completed_stages = std::uint8_t(j + 1);
      ok = checks;
    }
    if (ok)
      for (unsigned i = 0; i < INPUT_COUNT; ++i)
        if (example.preserve & (1U << i))
          check(i, initial[i], example.scenario_count);
  }
  if (result.status != Execution::CANCELLED &&
      result.status != Execution::BUSY) {
    result.pc = core_61::get_IP();
    for (unsigned i = 0; i < INPUT_COUNT; ++i)
      result.actual[i] = read(i);
    result.x = result.actual[15];
    if (!std::isfinite(result.x) && result.status == Execution::STOPPED)
      result.status = Execution::ERROR;
  }
  result.commands = run.count;
  result.passed = ok && checks && has_expectations(example) &&
                  result.status == Execution::STOPPED;
  if (owns_hook)
    core_61::clear_mk61_program_boundary_hook();
  if (!core_61::restore_context(live)) {
    result.status = Execution::ERROR;
    result.passed = false;
  }
  if (trace_count)
    *trace_count = run.trace_count;
  return result;
}
bool capture_program(Program &p) {
  if (core_61::is_RUN() || core_61::active_program_bank() != 0)
    return false;
  Program next{};
  next.size = PROGRAM_SIZE;
  for (unsigned i = 0; i < PROGRAM_SIZE; ++i)
    if (!core_61::read_absolute_program(i, next.bytes[i]))
      return false;
  p = next;
  return true;
}
bool apply_program(const Program &p) {
  if (!valid_program(p) || core_61::is_RUN() ||
      core_61::active_program_bank() != 0 || core_61::expanded_program_is_on())
    return false;
  for (unsigned i = 0; i < PROGRAM_SIZE; ++i)
    if (!core_61::write_absolute_program(i, i < p.size ? p.bytes[i] : 0x50))
      return false;
  core_61::set_IP(0);
  return true;
}
bool load_example_inputs(const Example &e) {
  if (e.angle > 2 || core_61::is_RUN() || core_61::active_program_bank() != 0)
    return false;
  core_61::ContextBuffer saved{};
  if (!core_61::save_context(saved))
    return false;
  if (set_inputs(e)) {
    MK61Emu_SetAngleUnit(e.angle == 0 ? DEGREE : e.angle == 2 ? GRADE : RADIAN);
    return true;
  }
  core_61::restore_context(saved);
  return false;
}
} // namespace mk61ai
