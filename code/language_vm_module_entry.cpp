#include <stdio.h>
#include "tinybasic_diagnostic.hpp"
#include "tinybasic_text.hpp"
#if !defined(MK61_BUILD_LANGUAGE_VM_MODULE)
#include "config.h"
#endif
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE) || MK61_RESIDENT_LANGUAGE_VM
#include <string.h>

#include "language_vm_abi.hpp"
#include "loadable_module_abi.hpp"
#include "mk8_literal.hpp"
#include "mk_math.hpp"
#include "text_editor.hpp"
#if !defined(MK61_BUILD_LANGUAGE_VM_MODULE)
#include <math.h>

#include "Arduino.h"
#include "cross_hal.h"
#include "entropy_pool.hpp"
#include "keyboard.h"
#include "loadable_system_api.hpp"
#include "mk61emu_core.h"
#include "tools.hpp"
#include "menu.hpp"
extern void idle_main_process(void);
namespace portable_system {
static u32 call(u32 op, u32 a = 0, u32 b = 0, u32 c = 0, void* payload = nullptr) {
  return loadable_module::app_services().call(op, a, b, c, payload);
}
static bool parse_number(const char* text, double& value, const char*& end) {
  mk61_system_number_parse request = {0, text, 0};
  if (!call(MK61_SYS_NUMBER_PARSE, 0, 0, 0, &request)) return false;
  value = request.value;
  end = text + request.consumed;
  return true;
}
static bool format_number(double value, u8 digits, char* output, usize size) {
  mk61_system_number_format request = {value, output, (u32)size, digits};
  return call(MK61_SYS_NUMBER_FORMAT, 0, 0, 0, &request) != 0;
}
static void text_rows(const char* const* rows, u32 count) {
  call(MK61_SYS_TEXT_ROWS, count, 0, 0, (void*)rows);
}
static void edit_key(text_editor::Buffer& editor, i32 key, u32 now) {
  mk61_system_edit_key request = {};
  request.source = editor.source;
  request.capacity = editor.capacity;
  request.length = editor.len;
  request.cursor = editor.cursor;
  request.top = editor.view_top;
  request.shift = (u32)editor.shift;
  request.sms_active = editor.sms.active;
  request.sms_index = editor.sms.index;
  request.sms_deadline = editor.sms.deadline_ms;
  request.sms_key = editor.sms.key_code;
  request.ok_text = "";
  request.options = 31;
  request.key = key;
  request.now = now;
  request.backspace_key = -1;
  call(MK61_SYS_EDITOR_KEY, 0, 0, 0, &request);
  editor.len = (u16)request.length;
  editor.cursor = (u16)request.cursor;
  editor.view_top = (u16)request.top;
  editor.shift = (text_editor::Shift)request.shift;
  editor.sms = {request.sms_active != 0, request.sms_key, (u8)request.sms_index,
                request.sms_deadline};
}
}  // namespace portable_system
#endif

namespace {
using namespace language_vm;
struct Runtime {
  State state;
  double stack[MAX_STACK];
  ExecuteRequest* request;
  Language language;
  char output[96];
  uint8_t row, width, output_cursor;
  bool cancelled, normal_stop;
  Error failure;
};
static Runtime runtime;

bool background(void*) {
  idle_main_process();
  kbd::scan();
  if (kbd::take_immediate_press(KEY_ESC) || kbd::last_key() == KEY_ESC_PRESS) {
    kbd::handoff(kbd::Event(KEY_ESC_PRESS));
    runtime.cancelled = true;
    return false;
  }
  return true;
}
double math(void*, Function f, double a, double b) {
  if ((uint8_t)f == 255) return mk_math::pow(a, b);
  const AngleUnit unit = read_grade_switch();
  const bool basic = runtime.language == Language::BASIC;
  if (basic && f <= Function::TAN && unit != RADIAN)
    a = a * 3.14159265358979323846 / (unit == DEGREE ? 180 : 200);
  double value = 0;
#if !defined(MK61_BUILD_LANGUAGE_VM_MODULE) && MK61_APP_LOCAL_FLOAT_MATH
  // Compiler APPs carry no local libm. This matched resident profile supplies
  // the same selected float functions as the former VM.APP.
  switch (f) {
    case Function::LN:
      return (double)::logf((float)a);
    case Function::LOG10:
      return (double)::log10f((float)a);
    case Function::EXP:
      return (double)::expf((float)a);
    case Function::SQRT:
      return (double)::sqrtf((float)a);
    default:
      break;
  }
#endif
  switch (f) {
    case Function::SIN:
      value = mk_math::sin(a);
      break;
    case Function::COS:
      value = mk_math::cos(a);
      break;
    case Function::TAN:
      value = mk_math::tan(a);
      break;
    case Function::ASIN:
      value = mk_math::asin(a);
      break;
    case Function::ACOS:
      value = mk_math::acos(a);
      break;
    case Function::ATAN:
      value = mk_math::atan(a);
      break;
    case Function::LN:
      value = mk_math::ln(a);
      break;
    case Function::LOG10:
      value = mk_math::log10(a);
      break;
    case Function::EXP:
      value = mk_math::exp(a);
      break;
    case Function::SQRT:
      value = mk_math::sqrt(a);
      break;
    default:
      return __builtin_nan("");
  }
  if (basic && f >= Function::ASIN && f <= Function::ATAN && unit != RADIAN)
    value = value * (unit == DEGREE ? 180 : 200) / 3.14159265358979323846;
  return value;
}
double random(void*) {
  const auto domain = runtime.language == Language::BASIC
                          ? entropy_pool::Domain::TINYBASIC
                          : entropy_pool::Domain::FOCAL;
  return (double)(entropy_pool::next_u32(domain) >> 8) / 16777216.0;
}
double dynamic_value(void*, Function f) {
  if (f == Function::COLS) return main_lcd().cols();
  if (f == Function::ROWS) return main_lcd().rows();
  return runtime.state.array_count ? (double)((runtime.state.array_count - 1) * 2) : 0;
}
bool reference(void*, bool write, uint8_t ref, double& value) {
  if (ref >= 20) return false;
  return portable_system::call(write ? MK61_SYS_REF_WRITE : MK61_SYS_REF_READ,
                               ref < 4 ? (u32)ref : (u32)MK61_SERVICE_REF_R,
                               ref < 4 ? 0 : ref - 4, 0, &value) != 0;
}
bool append(const char* text, uint16_t length, bool separate) {
  if (runtime.language == Language::BASIC) {
    if (tinybasic_text::append(runtime.output, sizeof(runtime.output), runtime.output_cursor, text,
                               length))
      return true;
    runtime.failure = Error::FULL;
    return false;
  }
  size_t used = strlen(runtime.output);
  if (separate && used && used + 1 < sizeof(runtime.output))
    runtime.output[used++] = ' ';
  if (runtime.language == Language::BASIC && length >= sizeof(runtime.output) - used) {
    runtime.failure = Error::FULL;
    return false;
  }
  while (length-- && used + 1 < sizeof(runtime.output))
    runtime.output[used++] = *text++;
  runtime.output[used] = 0;
  return true;
}
void flush(bool empty) {
  const uint8_t rows = main_lcd().rows();
  if (!rows) return;
  if (!runtime.output[0] && !empty) return;
  const uint8_t n =
      main_lcd().printWrappedText(runtime.output, (u16)strlen(runtime.output),
                                  runtime.row, (u8)(rows - runtime.row), false, empty);
  const uint16_t next = (uint16_t)runtime.row + n;
  runtime.row = next < rows ? (uint8_t)next : (uint8_t)(rows - 1);
  runtime.output[0] = 0;
  runtime.output_cursor = 0;
}
bool io(void*, Event, const char*, uint16_t, double&);
const Services services = {nullptr,       background, math, random,
                           dynamic_value, reference,  io};

bool input(const char* prompt, uint16_t length, double& value) {
  char text[65] = {};
  text_editor::Buffer editor;
  text_editor::init(editor, text, sizeof(text));
  runtime.request->pause_final = 0;
  for (;;) {
    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear();
      const uint8_t rows = main_lcd().rows();
      const uint8_t n = rows > 1 ? main_lcd().printWrappedText(
                                       prompt, length, 0, (u8)(rows - 1), true, false)
                                 : 0;
      main_lcd().setCursor(0, n);
      main_lcd().print("> ");
      main_lcd().print(text);
    }
    const i32 key = kbd::get_key_wait();
    if (editor.shift == text_editor::Shift::NONE &&
        (key == KEY_ESC || key == KEY_ESC_PRESS)) {
      kbd::handoff(kbd::Event(KEY_ESC_PRESS));
      runtime.cancelled = true;
      runtime.normal_stop =
          runtime.language == Language::BASIC && runtime.request->mode == 0;
      return false;
    }
    if (editor.shift == text_editor::Shift::NONE &&
        (key == KEY_OK || key == KEY_OK_PRESS)) {
      if (runtime.language == Language::FOCAL) {
        const char* end = nullptr;
        if (portable_system::parse_number(text, value, end)) {
          while (*end == ' ' || *end == '\t') ++end;
          if (!*end && mk_math::is_finite(value)) return true;
        }
      } else {
        uint8_t image[768];
        const auto compiled =
            compile_expression(Language::BASIC, text, editor.len, image, sizeof(image));
        View view;
        if (compiled.error == Error::NONE &&
            inspect(image, compiled.size, view) == Error::NONE) {
          State expression = {};
          double stack[MAX_STACK];
          expression.variables = runtime.request->variables;
          expression.array = runtime.request->array;
          expression.array_count = runtime.state.array_count;
          expression.stack = stack;
          expression.stack_capacity = MAX_STACK;
          const auto result = run(view, expression, services);
          if (result.error == Error::NONE) {
            value = stack[0];
            return true;
          }
          if (runtime.cancelled) return false;
        }
      }
      const char* message[] = {"Invalid number", "Try again"};
      portable_system::text_rows(message, 2);
      delay(500);
      text_editor::init(editor, text, sizeof(text));
      continue;
    }
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
    text_editor::portable_handle_default_key(editor, "", key, millis());
#else
    portable_system::edit_key(editor, key, millis());
#endif
  }
}
bool io(void*, Event event, const char* text, uint16_t length, double& value) {
  const bool basic = runtime.language == Language::BASIC;
  switch (event) {
    case Event::PRINT_BEGIN:
      runtime.width = 0;
      runtime.request->pause_final = 0;
      if (!basic) {
        runtime.row = 0;
        runtime.output[0] = 0;
        runtime.output_cursor = 0;
      }
      return true;
    case Event::TEXT:
      return append(text, length, !basic);
    case Event::NUMBER: {
      char number[24];
      if (!portable_system::format_number(value, basic ? 10 : 8, number,
                                          sizeof(number)))
        return false;
      if (basic)
        for (int n = (int)runtime.width - (int)strlen(number); n > 0; --n)
          if (!append(" ", 1, false)) return false;
      return append(number, (uint16_t)strlen(number), !basic);
    }
    case Event::FORMAT: {
      const double n = mk_math::floor(value + .5);
      if (value < 0 || value > 63 || mk_math::fabs(value - n) > 1e-7) {
        runtime.failure = Error::FORMAT;
        return false;
      }
      runtime.width = (uint8_t)n;
      return true;
    }
    case Event::SEPARATOR: {
      unsigned n = length == 2 ? 8U - (runtime.output_cursor % 8U) : length;
      while (n--)
        if (!append(" ", 1, false)) return false;
      return true;
    }
    case Event::FLUSH:
      flush(true);
      return true;
    case Event::PRINT_END:
      if (!length) flush(basic);
      return true;
    case Event::READ_INPUT:
      return input(text, length, value);
    case Event::WAIT: {
      if (!basic) {
        const char* rows[] = {"ASK", "Press any key"};
        portable_system::text_rows(rows, 2);
      }
      const i32 key = kbd::get_key_wait();
      runtime.request->pause_final = basic;
      if (key != KEY_ESC && key != KEY_ESC_PRESS) return true;
      kbd::handoff(kbd::Event(KEY_ESC_PRESS));
      runtime.cancelled = true;
      runtime.normal_stop = basic && runtime.request->mode == 0;
      return false;
    }
    case Event::CLEAR:
      main_lcd().clear();
      runtime.row = 0;
      runtime.output[0] = 0;
      runtime.output_cursor = 0;
      return true;
    case Event::FINISH:
      flush(false);
      return true;
    case Event::TARGET_REF:
      return value != 19 ||
             portable_system::call(MK61_SYS_SETTINGS, MK61_SYS_REGISTER_F) != 0;
  }
  return false;
}
uint32_t execute(ExecuteRequest* request) {
  if (!request || request->size != sizeof(*request) ||
      request->version != REQUEST_VERSION || !request->variables ||
      request->image_size > MAX_IMAGE || request->array_count > 385 ||
      request->mode > 1 || request->reserved)
    return 0;
  View view;
  request->result = {};
  const Error checked = inspect(request->image, (uint16_t)request->image_size, view);
  if (checked != Error::NONE) {
    request->result.error = checked;
    return 1;
  }
  runtime = {};
  runtime.request = request;
  runtime.language = view.language;
  runtime.state.variables = request->variables;
  runtime.state.array = request->array;
  runtime.state.array_count = (uint16_t)request->array_count;
  if (view.language == Language::BASIC && !view.expression) {
    const uint16_t source_limit = (uint16_t)((3584 - view.source_size) / 2 + 1);
    if (runtime.state.array_count > source_limit)
      runtime.state.array_count = source_limit;
  }
  runtime.state.stack = runtime.stack;
  runtime.state.stack_capacity = MAX_STACK;
  main_lcd().endUiText();
  if ((portable_system::call(MK61_SERVICE_CAPABILITIES) & MK61_SERVICE_CAP_TEXT_FONT) !=
      0)
    portable_system::call(MK61_SYS_TEXT_FONT, MK61_SYS_TEXT_FONT_ACTIVATE);
  main_lcd().clear();
  request->result = run(view, runtime.state, services);
  request->error_column = source_column(view, request->result.pc);
  if (runtime.cancelled)
    request->result.error = runtime.normal_stop ? Error::NONE : Error::STOPPED;
  else if (runtime.failure != Error::NONE)
    request->result.error = runtime.failure;
  if (request->result.error != Error::NONE &&
      !(request->mode == 1 && request->result.error == Error::STOPPED)) {
    char position[24];
    snprintf(position, sizeof(position), "TinyBASIC %lu:%u", (unsigned long)request->result.line,
             (unsigned)request->error_column);
    const char* rows[] = {
        view.language == Language::BASIC ? position : error_name(request->result.error),
        view.language == Language::BASIC
            ? tinybasic_diagnostic::reason(request->result.error, library_mk61::language_is_ru())
            : "FOCAL"};
    portable_system::text_rows(rows, 2);
  }
  if (request->mode == 0 &&
      (view.language == Language::FOCAL || !request->pause_final)) {
    for (;;) {
      idle_main_process();
      const auto event = kbd::poll_event();
      if (event.code() >= 0 && event.code() < (i32)key_state::RELEASED) {
        if (view.language == Language::BASIC && request->result.error != Error::NONE &&
            request->result.error != Error::STOPPED && event.code() == KEY_OK)
          request->edit_requested = 1;
        kbd::handoff(event);
        break;
      }
      delay(10);
    }
  }
  runtime.request = nullptr;
  return 1;
}
}  // namespace
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
extern "C" u32 mk61_app_initialize(const mk61_app_api* api, u32 crc, u32 kind) {
  return portable_system::bind(api, crc, kind) ? 0 : MK61_APP_RUNTIME_ERROR;
}
extern "C" u32 mk61_app_command(u32 command, u32 argument0, u32, u32, u32) {
  return command == (u32)loadable_module::Command::LANGUAGE_VM_RUN
             ? execute((language_vm::ExecuteRequest*)(usize)argument0)
             : 0;
}
#else
#include "language_vm_resident.hpp"
__attribute__((noinline)) bool language_vm::execute_resident(ExecuteRequest& request) {
  return execute(&request) != 0;
}
#endif
#endif
