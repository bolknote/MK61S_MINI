#include "tinybasic_text.hpp"
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
#include <string.h>
#include "language_vm_abi.hpp"
#include "loadable_module_abi.hpp"
#include "mk_math.hpp"

namespace {
using namespace language_vm;
OverlayRequest* active;
ExecutionState& state() { return *active->state; }
ExecuteRequest& request() { return *active->execution; }

bool background(void*) {
  idle_main_process();
  kbd::scan();
  if (!kbd::take_immediate_press(KEY_ESC) && kbd::last_key() != KEY_ESC_PRESS)
    return true;
  kbd::handoff(kbd::Event(KEY_ESC_PRESS));
  state().cancelled = true;
  return false;
}
double math(void*, Function f, double a, double b) {
  if ((uint8_t)f == 255) return mk_math::pow(a, b);
  const AngleUnit unit = read_grade_switch();
  const bool basic = state().language == Language::BASIC;
  if (basic && f <= Function::TAN && unit != RADIAN)
    a = a * 3.14159265358979323846 / (unit == DEGREE ? 180 : 200);
  double value;
  switch (f) {
    case Function::SIN: value = mk_math::sin(a); break;
    case Function::COS: value = mk_math::cos(a); break;
    case Function::TAN: value = mk_math::tan(a); break;
    case Function::ASIN: value = mk_math::asin(a); break;
    case Function::ACOS: value = mk_math::acos(a); break;
    case Function::ATAN: value = mk_math::atan(a); break;
    case Function::LN: value = mk_math::ln(a); break;
    case Function::LOG10: value = mk_math::log10(a); break;
    case Function::EXP: value = mk_math::exp(a); break;
    case Function::SQRT: value = mk_math::sqrt(a); break;
    default: return __builtin_nan("");
  }
  if (basic && f >= Function::ASIN && f <= Function::ATAN && unit != RADIAN)
    value = value * (unit == DEGREE ? 180 : 200) / 3.14159265358979323846;
  return value;
}
double random(void*) {
  const auto domain = state().language == Language::BASIC
                          ? entropy_pool::Domain::TINYBASIC
                          : entropy_pool::Domain::FOCAL;
  return (double)(entropy_pool::next_u32(domain) >> 8) / 16777216.0;
}
double dynamic_value(void*, Function f) {
  if (f == Function::COLS) return main_lcd().cols();
  if (f == Function::ROWS) return main_lcd().rows();
  return state().array_count ? (double)((state().array_count - 1) * 2) : 0;
}
bool reference(void*, bool write, uint8_t ref, double& value) {
  if (ref >= 20) return false;
  return portable_system::call(write ? MK61_SYS_REF_WRITE : MK61_SYS_REF_READ,
                               ref < 4 ? (u32)ref : (u32)MK61_SERVICE_REF_R,
                               ref < 4 ? 0 : ref - 4, 0, &value) != 0;
}
bool append(const char* text, uint16_t length, bool separate) {
  auto& s = state();
  if (s.language == Language::BASIC) {
    if (tinybasic_text::append(s.output, sizeof(s.output), s.output_cursor, text, length))
      return true;
    s.failure = Error::FULL;
    return false;
  }
  size_t used = strlen(s.output);
  if (separate && used && used + 1 < sizeof(s.output)) s.output[used++] = ' ';
  if (s.language == Language::BASIC && length >= sizeof(s.output) - used) {
    s.failure = Error::FULL;
    return false;
  }
  while (length-- && used + 1 < sizeof(s.output)) s.output[used++] = *text++;
  s.output[used] = 0;
  return true;
}
void flush(bool empty) {
  auto& s = state();
  const uint8_t rows = main_lcd().rows();
  if (!rows || (!s.output[0] && !empty)) return;
  const uint8_t n = main_lcd().printWrappedText(
      s.output, (u16)strlen(s.output), s.row, (u8)(rows - s.row), false, empty);
  const uint16_t following = (uint16_t)s.row + n;
  s.row = following < rows ? (uint8_t)following : (uint8_t)(rows - 1);
  s.output[0] = 0;
  s.output_cursor = 0;
}
bool io(void*, Event event, const char* text, uint16_t length, double& value) {
  auto& s = state();
  const bool basic = s.language == Language::BASIC;
  switch (event) {
    case Event::PRINT_BEGIN:
      s.width = 0;
      request().pause_final = 0;
      if (!basic) {
        s.row = 0;
        s.output[0] = 0;
        s.output_cursor = 0;
      }
      return true;
    case Event::TEXT: return append(text, length, !basic);
    case Event::NUMBER: {
      char number[24];
      if (!portable_system::format_number(value, basic ? 10 : 8, number,
                                          sizeof(number))) return false;
      if (basic)
        for (int n = (int)s.width - (int)strlen(number); n > 0; --n)
          if (!append(" ", 1, false)) return false;
      return append(number, (uint16_t)strlen(number), !basic);
    }
    case Event::FORMAT: {
      const double n = mk_math::floor(value + .5);
      if (value < 0 || value > 63 || mk_math::fabs(value - n) > 1e-7) {
        state().failure = Error::FORMAT;
        return false;
      }
      s.width = (uint8_t)n;
      return true;
    }
    case Event::SEPARATOR: {
      unsigned n = length == 2 ? 8U - (s.output_cursor % 8U) : length;
      while (n--) if (!append(" ", 1, false)) return false;
      return true;
    }
    case Event::FLUSH: flush(true); return true;
    case Event::PRINT_END: if (!length) flush(basic); return true;
    // The kernel yields before dispatching this event. No parser/editor is
    // linked into the hot image, and no callback survives an APP replacement.
    case Event::READ_INPUT: return false;
    case Event::WAIT: {
      if (!basic) {
        const char* rows[] = {"ASK", "Press any key"};
        portable_system::text_rows(rows, 2);
      }
      const i32 key = kbd::get_key_wait();
      request().pause_final = basic;
      if (key != KEY_ESC && key != KEY_ESC_PRESS) return true;
      kbd::handoff(kbd::Event(KEY_ESC_PRESS));
      s.cancelled = true;
      s.normal_stop = basic && request().mode == 0;
      return false;
    }
    case Event::CLEAR:
      main_lcd().clear();
      s.row = 0;
      s.output[0] = 0;
      s.output_cursor = 0;
      return true;
    case Event::FINISH: flush(false); return true;
    case Event::TARGET_REF:
      return value != 19 ||
             portable_system::call(MK61_SYS_SETTINGS, MK61_SYS_REGISTER_F) != 0;
  }
  return false;
}
const Services services = {nullptr, background, math, random,
                           dynamic_value, reference, io, true};

__attribute__((noinline)) void evaluate_expression(const View& view) {
  const Bindings bindings = {request().variables, request().array, state().array_count,
                             state().stack, MAX_STACK};
  request().result = evaluate_input(view, state(), bindings, services);
}
uint32_t execute(OverlayRequest* payload) {
  if (!execution_compatible(payload)) return 0;
  auto& r = *payload->execution;
  View view;
  const bool expression = payload->action == OverlayAction::EXPRESSION;
  r.result = {};
  if (!validated_view(*payload, view)) {
    r.result.error = Error::INVALID_IMAGE; return 1;
  }
  active = payload;
  auto& s = state();
  if (expression) {
    evaluate_expression(view);
  } else if (payload->action != OverlayAction::ABORT) {
    const Bindings bindings = {r.variables, r.array, s.array_count,
                               s.stack, MAX_STACK};
    const bool resume = payload->action == OverlayAction::RESUME;
    if (resume && s.control.sp >= MAX_STACK) {
      r.result.error = Error::STACK;
    } else {
      if (resume) s.stack[s.control.sp++] = s.input_value;
      r.result = run(view, s.control, bindings, services, 0, resume);
      r.error_column = source_column(view, r.result.pc);
      s.steps += r.result.steps;
      r.result.steps = s.steps;
      if (r.result.error == Error::YIELDED) {
        const uint8_t* p = view.bytes + r.result.pc + 1;
        s.prompt_offset = (uint16_t)(r.result.pc + 3);
        s.prompt_length = (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
        r.pause_final = 0;
      }
    }
  } else {
    // ABORT is issued only after the input APP returned or failed to load.
    r.result.error = s.cancelled ? Error::STOPPED : Error::IO;
  }
  active = nullptr;
  return 1;
}
}  // namespace
extern "C" u32 mk61_app_initialize(const mk61_app_api* api, u32 crc, u32 kind) {
  return portable_system::bind(api, crc, kind) ? 0 : MK61_APP_RUNTIME_ERROR;
}
extern "C" u32 mk61_app_command(u32 command, u32 argument0, u32, u32, u32) {
  if (command == (u32)loadable_module::Command::LANGUAGE_VM_INFO) return OVERLAY_MAGIC;
  return command == (u32)loadable_module::Command::LANGUAGE_VM_RUN
             ? execute((OverlayRequest*)(usize)argument0) : 0;
}
#endif
