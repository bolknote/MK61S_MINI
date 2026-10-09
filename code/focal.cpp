#if defined(MK61_BUILD_FOCAL_MODULE)
#define FOCAL_library_select mk61_module_focal_library_select
#define FOCAL_menu_select mk61_module_focal_menu_select
#define CompileFocal mk61_module_compile_focal
#define InitFocal mk61_module_init_focal
#define FocalIsReady mk61_module_focal_is_ready
#define RunFocal mk61_module_run_focal
#define RunFocalProgram mk61_module_run_focal_program
#define EditFocal mk61_module_edit_focal
#define EditFocalProgram mk61_module_edit_focal_program
#endif
#ifdef FOCAL_HOST_TEST
#include "focal.hpp"
#include "../tests/focal_host_fixture.hpp"
#include "keyboard_layout.hpp"
#include "rust_types.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MK61_FOCAL_IS_LOADABLE
#define MK61_FOCAL_IS_LOADABLE 0
#endif

#if MK61_ENABLE_FOCAL && defined(MK61_BUILD_FOCAL_MODULE) &&                   \
    !defined(MK61_LANGUAGE_VM_COMPILER)
#error "FOCAL.APP requires MK61_LANGUAGE_VM_COMPILER and a matched shared VM"
#endif
#if MK61_ENABLE_FOCAL &&                                                       \
    (!MK61_FOCAL_IS_LOADABLE || defined(MK61_BUILD_FOCAL_MODULE) ||            \
     defined(FOCAL_HOST_TEST))
static const int KEY_LEFT = keyboard_layout::active().left;
static const int KEY_RIGHT = keyboard_layout::active().right;
static const int KEY_OK = keyboard_layout::active().ok;
static const int KEY_ESC = keyboard_layout::active().esc;
static const int KEY_K = keyboard_layout::active().k;
static const int KEY_ALPHA = keyboard_layout::active().alpha;
static const int KEY_CX = keyboard_layout::active().cx;
static const int KEY_PP = keyboard_layout::active().pp;
[[maybe_unused]] static const int KEY_SHG_RIGHT_PRESS =
    keyboard_layout::active().shg_right;
[[maybe_unused]] static const int KEY_SHG_LEFT_PRESS =
    keyboard_layout::active().shg_left;
static const int KEY_LEFT_PRESS = KEY_LEFT;
static const int KEY_RIGHT_PRESS = KEY_RIGHT;
static const int KEY_OK_PRESS = KEY_OK;
static const int KEY_ESC_PRESS = KEY_ESC;

namespace lcd_display {
static constexpr u8 COLS = 16;
}

typedef enum { X1 = 0, X = 1, Y = 2, Z = 3, T = 4 } stack;

typedef enum { RADIAN = 10, DEGREE = 11, GRADE = 12 } AngleUnit;

static AngleUnit focal_host_angle_unit = RADIAN;
AngleUnit read_grade_switch(void) { return focal_host_angle_unit; }

namespace mk61_ref {
double host_stack_value[5];
double host_register_value[16];
bool host_rf_enabled;
} // namespace mk61_ref

class MK61Display {
public:
  static constexpr u8 MAX_ROWS = 10;
  static constexpr u8 MAX_COLS = 64;
  MK61Display(void) : x(0), y(0), row_count(8), reported_cols(16) { clear(); }
  void clear(void) {
    memset(lines, ' ', sizeof(lines));
    for (int row = 0; row < MAX_ROWS; row++)
      lines[row][reported_cols] = 0;
    x = 0;
    y = 0;
  }
  void flush(void) {}
  void setCursor(u8 col, u8 row) {
    x = (col < reported_cols) ? col : (reported_cols - 1);
    y = (row < MAX_ROWS) ? row : (MAX_ROWS - 1);
  }
  void cursorOn(void) {}
  void cursorOff(void) {}
  bool supportsCursor(void) const { return false; }
  void write(u8 value) {
    if (x < reported_cols && y < MAX_ROWS)
      lines[y][x++] = (char)value;
  }
  void print(const char *text) {
    if (text == NULL)
      return;
    while (*text != 0)
      write((u8)*text++);
  }
  void print(char value) { write((u8)value); }
  u8 cols(void) const { return reported_cols; }
  void setReportedCols(u8 cols) {
    reported_cols = cols < 1 ? 1 : (cols > MAX_COLS ? MAX_COLS : cols);
    for (u8 row = 0; row < MAX_ROWS; row++) {
      for (u8 col = 0; col < reported_cols; col++)
        if (lines[row][col] == 0)
          lines[row][col] = ' ';
      lines[row][reported_cols] = 0;
    }
  }
  u8 rows(void) const { return row_count; }
  void setRows(u8 rows) {
    row_count = (rows < 1) ? 1 : ((rows > MAX_ROWS) ? MAX_ROWS : rows);
  }
  const char *line(u8 row) const { return lines[(row < MAX_ROWS) ? row : 0]; }

private:
  u8 x;
  u8 y;
  u8 row_count;
  u8 reported_cols;
  char lines[MAX_ROWS][MAX_COLS + 1];
};

class MK61DisplayUpdate {
public:
  explicit MK61DisplayUpdate(MK61Display &) {}
};

static MK61Display host_lcd;
MK61Display &main_lcd(void) { return host_lcd; }

enum class key_state { PRESSED = 0, RELEASED = 0x40 };

namespace kbd {
static bool host_alpha_pressed;
static bool host_wait_esc;
static i32 host_keys[32];
static u8 host_key_count, host_key_index;
static int host_key_reads;
isize scan(void) { return 0; }
i32 get_key(key_state) { return -1; }
i32 get_key_wait(void) {
  host_key_reads++;
  while (host_key_index < host_key_count) {
    const i32 key = host_keys[host_key_index++];
    if (key >= 0 && key < (i32)key_state::RELEASED)
      return key;
  }
  return host_wait_esc ? KEY_ESC : KEY_OK;
}
bool is_key_pressed(i32 key_code) {
  return key_code == KEY_ALPHA && host_alpha_pressed;
}
} // namespace kbd

static u32 focal_host_millis;
u32 millis(void) { return focal_host_millis += 17; }
void delay(usize ms) { focal_host_millis += (u32)ms; }

typedef bool (*menu_action)(void);
struct t_punct {
  u8 size;
  menu_action action;
  char text[16];
};

class class_menu {
public:
  class_menu(t_punct **, int) {}
  void select(void) {}
};

namespace library_mk61 {
bool language_is_ru(void) { return focal_host_fixture::russian; }
} // namespace library_mk61
#endif

#else
#include "Arduino.h"
#include "cross_hal.h"
#include "development.hpp"
#include "entropy_pool.hpp"
#include "focal.hpp"
#include "keyboard.h"
#include "lcd_gui.hpp"
#include "lcd_ru.hpp"
#include "menu.hpp"
#include "program_store.hpp"
#include "rust_types.h"
#include "tools.hpp"
#include <new>

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

#include "bounded_string.hpp"
#include "mk8_literal.hpp"
#include "number_format.hpp"
#if MK61_ENABLE_FOCAL &&                                                       \
    (!MK61_FOCAL_IS_LOADABLE || defined(MK61_BUILD_FOCAL_MODULE) ||            \
     defined(FOCAL_HOST_TEST))
#include "mk_math.hpp"
#ifdef FOCAL_HOST_TEST
#define MK61_REF_HOST_TEST
#define TEXT_EDITOR_HOST_TEST
#endif
#include "focal_editor.hpp"
#include "focal_syntax.hpp"
#include "focal_text.hpp"
#include "focal_trace.hpp"
#include "language_bytecode.hpp"
#include "mk61_ref.hpp"
#if defined(MK61_LANGUAGE_VM_COMPILER)
#include "language_vm_abi.hpp"
#endif
#ifndef FOCAL_HOST_TEST
#include "language_workspace.hpp"
extern void idle_main_process(void);
#endif
using namespace kbd;
static constexpr int TB_PROGRAM_COUNT = 1, TB_SOURCE_SIZE = 1537,
                     TB_NAME_SIZE = 32;
static constexpr u16 TB_INVALID_STORE_ID = 0xFFFF, TB_ROOT_STORE_ID = 0xFFFF;
struct TbProgram {
#if defined(MK61_LANGUAGE_VM_COMPILER)
  u32 source_revision;
#endif
  u16 store_id, parent_id;
  char name[TB_NAME_SIZE], source[TB_SOURCE_SIZE];
  u16 source_len;
};
static bool tb_program_used(const TbProgram &p) { return p.source_len != 0; }
struct FocalRuntime {
  TbProgram programs[TB_PROGRAM_COUNT];
  language_vm::CompileResult compile_result;
#if !defined(MK61_LANGUAGE_VM_COMPILER)
  language_vm::Value variables[26], array[64];
#endif
  i8 NextFocal;
  char tb_last_error[17], tb_pending_print[96];
  u8 tb_print_row;
};
static void focal_reset_runtime(FocalRuntime &runtime) {
  runtime.compile_result = {};
#if !defined(MK61_LANGUAGE_VM_COMPILER)
  for (auto &v : runtime.variables)
    v = 0;
  for (auto &v : runtime.array)
    v = 0;
#endif
  runtime.NextFocal = -1;
  runtime.tb_last_error[0] = 0;
  runtime.tb_pending_print[0] = 0;
  runtime.tb_print_row = 0;
  for (auto &p : runtime.programs) {
    memset(&p, 0, sizeof(p));
    p.store_id = p.parent_id = 0xFFFF;
  }
}
#ifdef FOCAL_HOST_TEST
static FocalRuntime runtime_storage;
static FocalRuntime &focal_runtime() { return runtime_storage; }
#else
static_assert(sizeof(FocalRuntime) <= language_workspace::SIZE,
              "FOCAL workspace budget");
class FocalWorkspaceScope {
  language_workspace::Lease lease;

public:
  explicit FocalWorkspaceScope(usize requested = sizeof(FocalRuntime))
      : lease(language_workspace::Owner::FOCAL,
#if defined(MK61_LANGUAGE_VM_COMPILER)
              requested
#else
              language_workspace::SIZE
#endif
        ) {
#if !defined(MK61_LANGUAGE_VM_COMPILER)
    (void)requested;
#endif
    if (lease.ok() && lease.fresh()) {
      auto *r = new (lease.data()) FocalRuntime;
      focal_reset_runtime(*r);
    }
  }
  bool ok() const { return lease.ok(); }
};
static FocalRuntime &focal_runtime() {
  void *p = language_workspace::data(language_workspace::Owner::FOCAL);
  if (!p)
    __builtin_trap();
  return *static_cast<FocalRuntime *>(p);
}
#endif
#define programs (focal_runtime().programs)
#define next_compiled (focal_runtime().compile_result)
#define NextFocal (focal_runtime().NextFocal)
#define tb_last_error (focal_runtime().tb_last_error)
#define tb_pending_print (focal_runtime().tb_pending_print)
#define tb_print_row (focal_runtime().tb_print_row)
[[maybe_unused]] static bool tb_pause_is_final = false;
[[maybe_unused]] static char tb_upper(char c) { return focal_next::upper(c); }
static bool tb_streq(const char *a, const char *b) {
  while (*a && *b && focal_next::upper(*a) == focal_next::upper(*b)) {
    ++a;
    ++b;
  }
  return !*a && !*b;
}
static void tb_copy_text(char *d, usize n, const char *s) {
  bounded_string::copy(d, n, s);
}
static text_editor::KeyResult focal_handle_editor_key(text_editor::Buffer &e,
                                                      const char *enter,
                                                      i32 key, u32 now) {
  return focal_editor::handle(e, enter, key, now);
}
#ifndef FOCAL_HOST_TEST
[[maybe_unused]] static void tb_activate_inherited_text_font(void) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  if ((portable_system::call(MK61_SERVICE_CAPABILITIES) &
       MK61_SERVICE_CAP_TEXT_FONT) != 0) {
    (void)portable_system::call(MK61_SYS_TEXT_FONT,
                                MK61_SYS_TEXT_FONT_ACTIVATE);
  }
#else
  (void)program_store_text_font_activate();
#endif
}
#endif
static bool focal_language_is_ru(void) {
  return library_mk61::language_is_ru();
}

static void tb_message_i18n(const char *en0, const char *ru0, const char *en1,
                            const char *ru1) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
#ifndef FOCAL_HOST_TEST
  lcd_ru::print_lines(focal_language_is_ru() ? ru0 : en0,
                      focal_language_is_ru() ? ru1 : en1);
  return;
#endif
  main_lcd().setCursor(0, 0);
  main_lcd().print(focal_language_is_ru() ? ru0 : en0);
  main_lcd().setCursor(0, 1);
  main_lcd().print(focal_language_is_ru() ? ru1 : en1);
  (void)ru0;
  (void)ru1;
}

[[maybe_unused]] static void tb_print_display_text(const char *text) {
  if (text == NULL)
    return;
#ifdef FOCAL_HOST_TEST
  main_lcd().print(text);
#else
  while (*text != 0)
    main_lcd().writeCodepoint(mk8::codepoint((u8)*text++));
#endif
}

enum class TbError : u8 { WHAT, HOW, SORRY };

static bool tb_error(const char *message) {
  tb_copy_text(tb_last_error, sizeof(tb_last_error), message);
  const char *localized = message;
  static const struct {
    const char *en;
    const char *ru;
  } errors[] = {{"LINE?", M8("СТРОКА?")},    {"SYNTAX?", M8("СИНТАКСИС?")},
                {"VAR?", M8("ПЕРЕМ?")},      {"FUNC?", M8("ФУНК?")},
                {"FOR?", M8("ЦИКЛ?")},       {"FULL?", M8("НЕТ МЕСТА")},
                {"RETURN?", M8("ВОЗВРАТ?")}, {"STACK?", M8("СТЕК?")},
                {"MATH?", M8("МАТ?")},       {"MK?", M8("МК?")},
                {"NAME?", M8("ИМЯ?")},       {"SLOT?", M8("СЛОТ?")}};
  for (const auto &error : errors)
    if (!strcmp(message, error.en)) {
      localized = error.ru;
      break;
    }
  focal_trace_message("ERROR", message);
  tb_message_i18n(message, localized, "FOCAL", M8("ФОКАЛ"));
  return false;
}
static const char *focal_error_name(language_vm::Error error) {
  using E = language_vm::Error;
  switch (error) {
  case E::NONE:
    return "OK";
  case E::FULL:
    return "FULL?";
  case E::LINE:
  case E::MISSING_LINE:
  case E::LINE_NUMBER:
    return "LINE?";
  case E::VARIABLE:
  case E::ARRAY_RANGE:
    return "VAR?";
  case E::REGISTER:
    return "MK?";
  case E::FUNCTION:
    return "FUNC?";
  case E::FOR:
    return "FOR?";
  case E::RETURN:
    return "RETURN?";
  case E::STACK:
  case E::CALL_STACK:
  case E::LOOP_STACK:
    return "STACK?";
  case E::MATH:
  case E::DIV_ZERO:
    return "MATH?";
  case E::STOPPED:
    return "STOP";
  default:
    return "SYNTAX?";
  }
}
static bool tb_compile_source(const char *source) {
  tb_last_error[0] = 0;
  const usize n = text_editor::bounded_length(source, TB_SOURCE_SIZE);
  if (n >= TB_SOURCE_SIZE)
    return tb_error("FULL?");
  const bool rf = mk61_ref::register_available(15);
  next_compiled =
      language_vm::compile(language_vm::Language::FOCAL, source, (u16)n,
                           nullptr, language_vm::MAX_IMAGE, rf);
  if (next_compiled.error != language_vm::Error::NONE)
    return tb_error(focal_error_name(next_compiled.error));
  return true;
}
static void focal_clear_array() {
#if defined(MK61_LANGUAGE_VM_COMPILER)
  if (language_vm::frontend_request)
    language_vm::frontend_request->clear_requested = 1;
#else
  for (auto &v : focal_runtime().variables)
    v = 0;
  for (auto &v : focal_runtime().array)
    v = 0;
#endif
}
static void focal_finish_wait() {
#if defined(MK61_LANGUAGE_VM_COMPILER)
  if (language_vm::frontend_request &&
      language_vm::frontend_request->run_requested)
    return;
#endif
#ifndef FOCAL_HOST_TEST
  if (!tb_pause_is_final) {
    while (true) {
      idle_main_process();
      auto event = kbd::poll_event();
      if (event.code() >= 0 && event.code() < (i32)key_state::RELEASED) {
        kbd::handoff(event);
        break;
      }
      delay(10);
    }
  }
#endif
}

#if !defined(MK61_LANGUAGE_VM_COMPILER)
static bool tb_runtime_interrupted() {
#ifndef FOCAL_HOST_TEST
  idle_main_process();
  kbd::scan();
  if (kbd::take_immediate_press(KEY_ESC) || kbd::last_key() == KEY_ESC_PRESS) {
    kbd::handoff(kbd::Event(KEY_ESC_PRESS));
    return true;
  }
#endif
  return false;
}
static bool next_text(void *, const char *p, unsigned n) {
  if (n >= sizeof(tb_pending_print) - strlen(tb_pending_print))
    return false;
  strncat(tb_pending_print, p, n);
  tb_pause_is_final = false;
  return true;
}
static bool next_newline(void *) {
#ifdef FOCAL_HOST_TEST
  main_lcd().setCursor(0, tb_print_row);
  main_lcd().print(tb_pending_print);
  if (tb_print_row + 1 < main_lcd().rows())
    ++tb_print_row;
#else
  const auto rows = main_lcd().rows();
  auto written = main_lcd().printWrappedText(
      tb_pending_print, (u16)strlen(tb_pending_print), tb_print_row,
      (u8)(rows - tb_print_row), false, true);
  if (rows)
    tb_print_row = (u8)((tb_print_row + written) < rows ? tb_print_row + written
                                                        : rows - 1);
#endif
  tb_pending_print[0] = 0;
  tb_pause_is_final = false;
  return true;
}
static bool next_number(void *, double value, unsigned width,
                        unsigned precision) {
  char number[48];
  number_format::general(value, precision, number, sizeof(number));
  const auto n = strlen(number);
  for (unsigned i = (unsigned)n; i < width; ++i)
    if (!next_text(nullptr, " ", 1))
      return false;
  return next_text(nullptr, number, (unsigned)n);
}
static bool next_reference(void *, bool write, uint8_t ref, double &value) {
  mk61_ref::Ref r = ref < 4 ? mk61_ref::Ref{(mk61_ref::Kind)ref, 0}
                            : mk61_ref::Ref{mk61_ref::Kind::R, (u8)(ref - 4)};
  return write ? mk61_ref::write(r, value) : mk61_ref::read(r, value);
}
static double next_math_radians(void *, language_vm::Function fn, double a,
                                double b) {
  using F = language_vm::Function;
  if ((uint8_t)fn == 255)
    return mk_math::pow(a, b);
  if (fn <= F::SQRT) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && !MK61_APP_LOCAL_FLOAT_MATH
    return portable_system::api->math((u32)fn, a, 0);
#else
    switch (fn) {
    case F::SIN:
      return mk_math::sin(a);
    case F::COS:
      return mk_math::cos(a);
    case F::TAN:
      return mk_math::tan(a);
    case F::ASIN:
      return mk_math::asin(a);
    case F::ACOS:
      return mk_math::acos(a);
    case F::ATAN:
      return mk_math::atan(a);
    case F::LN:
      return mk_math::ln(a);
    case F::LOG10:
      return mk_math::log10(a);
    case F::EXP:
      return mk_math::exp(a);
    case F::SQRT:
      return mk_math::sqrt(a);
    default:
      break;
    }
#endif
  }
  switch (fn) {
  case F::ABS:
    return mk_math::fabs(a);
  case F::INT:
    return mk_math::floor(a);
  case F::FRAC:
    return mk_math::frac(a);
  case F::ROUND:
    return mk_math::round_half(a);
  case F::SGN:
    return a < 0 ? -1 : a > 0 ? 1 : 0;
  case F::MAX:
    return a > b ? a : b;
  default:
    return 0;
  }
}
static double next_math(void *context, language_vm::Function function, double a,
                        double b) {
  const auto unit = read_grade_switch();
  if (function <= language_vm::Function::TAN && unit != RADIAN)
    a = a * 3.14159265358979323846 / (unit == DEGREE ? 180 : 200);
  double value = next_math_radians(context, function, a, b);
  if (function >= language_vm::Function::ASIN &&
      function <= language_vm::Function::ATAN && unit != RADIAN)
    value = value * (unit == DEGREE ? 180 : 200) / 3.14159265358979323846;
  return value;
}
static double next_random(void *) {
#ifdef FOCAL_HOST_TEST
  static u32 state = 0x3B6B120E;
  state = state * 25173 + 13849;
  return double(state & 65535) / 65536;
#else
  return (double)(entropy_pool::next_u32(entropy_pool::Domain::FOCAL) >> 8) /
         16777216.0;
#endif
}
static bool next_service(void *) { return !tb_runtime_interrupted(); }
static void next_clear(void *) {
  main_lcd().clear();
  tb_pending_print[0] = 0;
  tb_print_row = 0;
}
static bool next_wait(void *) {
  tb_pause_is_final = true;
  return kbd::get_key_wait() != KEY_ESC;
}
#ifdef FOCAL_HOST_TEST
static double host_input_values[16];
static unsigned host_input_count = 0, host_input_index = 0;
static char host_prompt[96];
#endif
static bool next_input(void *, const char *prompt, double &value) {
  tb_pause_is_final = false;
#ifdef FOCAL_HOST_TEST
  tb_copy_text(host_prompt, sizeof(host_prompt), prompt);
  if (host_input_index == host_input_count)
    return false;
  value = host_input_values[host_input_index++];
  return true;
#else
  char buffer[65] = {};
  text_editor::Buffer editor = {
      buffer,           sizeof(buffer), 0, 0, 0, text_editor::Shift::NONE,
      {false, -1, 0, 0}};
  while (true) {
    idle_main_process();
    if (text_editor::sms_expired(editor.sms, millis()))
      text_editor::sms_reset(editor.sms);
    main_lcd().clear();
    const auto rows = main_lcd().rows();
    auto written = main_lcd().printWrappedText(
        prompt, (u16)strlen(prompt), 0, rows > 1 ? rows - 1 : 0, true, false);
    main_lcd().setCursor(0, rows > 1 ? written : 0);
    main_lcd().print("> ");
    tb_print_display_text(buffer);
    i32 key = kbd::get_key_wait();
    if (editor.shift == text_editor::Shift::NONE && key == KEY_ESC) {
      kbd::handoff(kbd::Event(key));
      return false;
    }
    if (editor.shift == text_editor::Shift::NONE && key == KEY_OK) {
      if (editor.len) {
        uint8_t image[256];
        auto result = language_vm::compile_expression(
            language_vm::Language::FOCAL, buffer, editor.len, image,
            sizeof(image));
        language_vm::View view;
        if (result.error == language_vm::Error::NONE &&
            language_vm::inspect(image, result.size, view) ==
                language_vm::Error::NONE) {
          language_vm::State state = {};
          language_vm::Value stack[language_vm::MAX_STACK];
          state.variables = focal_runtime().variables;
          state.array = focal_runtime().array;
          state.array_count = 64;
          state.stack = stack;
          state.stack_capacity = language_vm::MAX_STACK;
          const language_vm::Services services = {
              nullptr, nullptr,        next_math, next_random,
              nullptr, next_reference, nullptr};
          auto run = language_vm::run(view, state, services);
          if (run.error == language_vm::Error::NONE) {
            value = stack[0].number();
            return true;
          }
        }
      }
      tb_message_i18n("number?", M8("число?"), "", "");
      delay(400);
      continue;
    }
    // Numeric input is an expression field, never an operator field.
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
    (void)text_editor::portable_handle_default_key(editor, "", key, millis());
#else
    const auto &k = keyboard_layout::active();
    const text_editor::KeyMap map = {
        k.left, k.left,     k.right,     k.right, k.ok,    k.ok, k.esc,
        k.esc,  k.shg_left, k.shg_right, k.k,     k.alpha, k.pp};
    const text_editor::Hooks hooks = {nullptr, nullptr, nullptr, nullptr,
                                      nullptr};
    const text_editor::Options options = {"", true, true, true, true, k.cx};
    (void)text_editor::handle_key(editor, map, hooks, options, key, millis());
#endif
  }
#endif
}
#endif
#if defined(MK61_LANGUAGE_VM_COMPILER)
uint16_t language_vm::frontend_source_id() {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope;
  if (!scope.ok())
    return 0xFFFF;
#endif
  return NextFocal < 0 ? 0xFFFF : programs[NextFocal].store_id;
}
#endif
static FocalRunStatus tb_run_program(int slot) {
  focal_trace_message("RUN", slot >= 0 && slot < TB_PROGRAM_COUNT
                                 ? programs[slot].name
                                 : nullptr);
  if (slot < 0 || slot >= TB_PROGRAM_COUNT || !tb_program_used(programs[slot]))
    return FocalRunStatus::NOT_FOUND;
#if defined(MK61_LANGUAGE_VM_COMPILER)
  if (!language_vm::compatible(language_vm::frontend_request))
    return FocalRunStatus::UNAVAILABLE;
  auto &request = *language_vm::frontend_request;
  language_vm::ResourceSource resource = {programs[slot].store_id,
                                          programs[slot].source_revision,
                                          request.resources};
  request.compiled = language_vm::compile(
      language_vm::Language::FOCAL, programs[slot].source,
      programs[slot].source_len, request.output, (u16)request.capacity,
      mk61_ref::register_available(15), &resource);
  if (!request.output && request.compiled.error == language_vm::Error::FULL &&
      resource.mode == language_vm::ResourceMode::EMBEDDED) {
    request.resources = resource.mode = language_vm::ResourceMode::SOURCE;
    request.capacity = language_vm::MAX_IMAGE;
    request.compiled = language_vm::compile(
        language_vm::Language::FOCAL, programs[slot].source,
        programs[slot].source_len, nullptr, language_vm::MAX_IMAGE,
        mk61_ref::register_available(15), &resource);
  }
  request.source_id = programs[slot].store_id;
  request.source_revision = programs[slot].source_revision;
  request.language = (u8)language_vm::Language::FOCAL;
  request.run_requested = request.compiled.error == language_vm::Error::NONE;
  if (!request.run_requested)
    tb_error(focal_error_name(request.compiled.error));
  return request.run_requested ? FocalRunStatus::COMPLETED
                               : FocalRunStatus::COMPILE_ERROR;
#else
  if (!tb_compile_source(programs[slot].source))
    return FocalRunStatus::COMPILE_ERROR;
#ifdef FOCAL_HOST_TEST
  uint8_t image[language_vm::MAX_IMAGE];
#else
  constexpr unsigned image_offset = (sizeof(FocalRuntime) + 3u) & ~3u;
  auto *image =
      (uint8_t *)language_workspace::data(language_workspace::Owner::FOCAL) +
      image_offset;
#endif
#ifdef FOCAL_HOST_TEST
  constexpr unsigned image_capacity = language_vm::MAX_IMAGE;
#else
  constexpr unsigned image_capacity = language_workspace::SIZE - image_offset;
#endif
  auto result =
      language_vm::compile(language_vm::Language::FOCAL, programs[slot].source,
                           programs[slot].source_len, image, image_capacity,
                           mk61_ref::register_available(15));
  language_vm::View view;
  if (result.error != language_vm::Error::NONE ||
      language_vm::inspect(image, result.size, view) !=
          language_vm::Error::NONE)
    return FocalRunStatus::COMPILE_ERROR;
  next_clear(nullptr);
  language_vm::State state = {};
  language_vm::Value stack[language_vm::MAX_STACK];
  state.variables = focal_runtime().variables;
  state.array = focal_runtime().array;
  state.array_count = 64;
  state.stack = stack;
  state.stack_capacity = language_vm::MAX_STACK;
  struct Context {
    unsigned width = 0, precision = 8;
    bool cancelled = false;
  } context;
  language_vm::Services services = {
      &context,
      next_service,
      next_math,
      next_random,
      nullptr,
      next_reference,
      [](void *ptr, language_vm::Event event, const char *text, uint16_t length,
         double &value) {
        auto &c = *(Context *)ptr;
        switch (event) {
        case language_vm::Event::TRACE:
          focal_trace_execution(text, length, value);
          return true;
        case language_vm::Event::PRINT_BEGIN:
          tb_pending_print[0] = 0;
          tb_print_row = 0;
          c.width = 0;
          c.precision = 8;
          return true;
        case language_vm::Event::TEXT:
          if (tb_pending_print[0] && !next_text(nullptr, " ", 1))
            return false;
          return next_text(nullptr, text, length);
        case language_vm::Event::NUMBER:
          if (tb_pending_print[0] && !next_text(nullptr, " ", 1))
            return false;
          return next_number(nullptr, value, c.width, c.precision);
        case language_vm::Event::PRECISION:
          c.width = (unsigned)value;
          c.precision = length;
          return true;
        case language_vm::Event::FLUSH:
          return next_newline(nullptr);
        case language_vm::Event::PRINT_END:
          return !tb_pending_print[0] || next_newline(nullptr);
        case language_vm::Event::READ_INPUT: {
          char prompt[96];
          if (length >= sizeof(prompt))
            return false;
          memcpy(prompt, text, length);
          prompt[length] = 0;
          if (next_input(nullptr, prompt, value))
            return true;
          c.cancelled = true;
          return false;
        }
        case language_vm::Event::WAIT:
          if (next_wait(nullptr))
            return true;
          c.cancelled = true;
          return false;
        case language_vm::Event::CLEAR:
          next_clear(nullptr);
          return true;
        case language_vm::Event::FINISH:
          if (tb_pending_print[0])
            return next_newline(nullptr);
          return true;
        default:
          return true;
        }
      }};
  auto run = language_vm::run(view, state, services);
  if (run.error == language_vm::Error::STOPPED || context.cancelled)
    return FocalRunStatus::STOPPED;
  if (run.error != language_vm::Error::NONE) {
    tb_error(focal_error_name(run.error));
    return FocalRunStatus::RUNTIME_ERROR;
  }
  return FocalRunStatus::COMPLETED;
#endif
}
#if defined(MK61_LANGUAGE_VM_COMPILER)
bool language_vm::frontend_emit() {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope;
  if (!scope.ok())
    return false;
#endif
  if (!compatible(frontend_request))
    return false;
  frontend_request->retained_source = 1;
  return tb_run_program(NextFocal) == FocalRunStatus::COMPLETED;
}
#endif
static int find_free_program();
static void tb_program_default_name(int, char *, usize);
static bool store_edited_program(int, char *, const char *, u16);
static void focal_display_program_name(const char *name, char *output,
                                       usize capacity) {
  if (focal_language_is_ru() && strlen(name) > 5 &&
      focal_next::equal(name, name + 5, "FOCAL")) {
    const char *p = name + 5;
    while (focal_next::digit(*p))
      ++p;
    if (!*p) {
      snprintf(output, capacity, M8("ФОКАЛ%s"), name + 5);
      return;
    }
  }
  tb_copy_text(output, capacity, name);
}
static unsigned focal_source_lines(const char *source) {
  unsigned count = 0;
  const char *p = source;
  while (*p) {
    const char *end = p;
    while (*end && *end != '\n' && *end != '\r')
      ++end;
    const char *first = p;
    focal_next::Address a;
    if (focal_next::address(first, end, a) && a.exact)
      ++count;
    p = end;
    while (*p == '\r' || *p == '\n')
      ++p;
  }
  return count;
}
static void display_focal_ok(int slot) {
  char english[32], russian[32], name[32];
  unsigned lines = focal_source_lines(programs[slot].source);
  snprintf(english, sizeof(english), "FOCAL: %u lines", lines);
  snprintf(russian, sizeof(russian), M8("ФОКАЛ готов: %u"), lines);
  focal_display_program_name(programs[slot].name, name, sizeof(name));
  tb_message_i18n(english, russian, name, name);
  delay(700);
}
static void display_focal_saved(int slot) {
  char name[32];
  focal_display_program_name(programs[slot].name, name, sizeof(name));
  tb_message_i18n("FOCAL saved", M8("ФОКАЛ сохранен"), name, name);
  delay(700);
}
static bool focal_persist_write(u16 parent, u16 preferred, const char *name,
                                const char *source, u16 length, u16 &saved) {
#ifdef FOCAL_HOST_TEST
  return focal_host_fixture::write(parent, preferred, name, source, length,
                                   saved);
#else
  return program_store::write_file(parent, preferred,
                                   program_store::ProgramType::FOCAL, name,
                                   (const u8 *)source, length, &saved);
#endif
}
static bool focal_persist_remove(u16 id, const char *name) {
#ifdef FOCAL_HOST_TEST
  return focal_host_fixture::remove(id, name);
#else
  return id == TB_INVALID_STORE_ID
             ? program_store::remove(program_store::ProgramType::FOCAL, name)
             : program_store::remove_id(id);
#endif
}
static bool focal_persist_exists(const char *name) {
#ifdef FOCAL_HOST_TEST
  return focal_host_fixture::exists(name);
#else
  return program_store::exists(program_store::ProgramType::FOCAL, name);
#endif
}
static constexpr usize FOCAL_EDITOR_OFFSET = (sizeof(FocalRuntime) + 3u) & ~3u;
[[maybe_unused]] static constexpr usize FOCAL_EDITOR_WORKSPACE =
    FOCAL_EDITOR_OFFSET + TB_SOURCE_SIZE;
#if defined(MK61_LANGUAGE_VM_COMPILER) && !defined(FOCAL_HOST_TEST)
static_assert(FOCAL_EDITOR_WORKSPACE <= language_vm::COMPILER_WORKSPACE_SIZE,
              "FOCAL editor must retain the protected VM values");
#endif
static char *focal_editor_source() {
#ifdef FOCAL_HOST_TEST
  static char source[TB_SOURCE_SIZE];
  return source;
#else
  return (char *)language_workspace::data(language_workspace::Owner::FOCAL) +
         FOCAL_EDITOR_OFFSET;
#endif
}
bool CompileFocal(const char *source) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope(FOCAL_EDITOR_WORKSPACE);
  if (!scope.ok())
    return false;
#endif
  const int slot = find_free_program();
  if (slot < 0)
    return tb_error("FULL?");
  if (!source || !tb_compile_source(source))
    return false;
  char *staging = focal_editor_source();
  if (!focal_text::editor_copy(source, staging, TB_SOURCE_SIZE))
    return tb_error("FULL?");
  char name[TB_NAME_SIZE];
  tb_program_default_name(slot, name, sizeof(name));
  if (!store_edited_program(slot, staging, name, TB_ROOT_STORE_ID))
    return false;
  display_focal_ok(slot);
  return true;
}
FocalRunStatus RunFocal(int slot) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope;
  if (!scope.ok())
    return FocalRunStatus::UNAVAILABLE;
#endif
  return tb_run_program(slot);
}
static int find_free_program(void) {
  for (int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if (!tb_program_used(programs[i]))
      return i;
  }
  return -1;
}

static int find_program_by_name(const char *name) {
  for (int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if (tb_program_used(programs[i]) && tb_streq(programs[i].name, name))
      return i;
  }
  return -1;
}

static void tb_program_default_name(int slot, char *out, usize size) {
  snprintf(out, size, "FOCAL%d", slot);
}

#ifndef FOCAL_HOST_TEST
static int tb_alloc_program_slot(const char *name) {
  const int existing = find_program_by_name(name);
  if (existing >= 0)
    return existing;
  const int free_slot = find_free_program();
  if (free_slot >= 0)
    return free_slot;
  const int slot =
      (NextFocal >= 0 && NextFocal < TB_PROGRAM_COUNT) ? NextFocal : 0;
  return slot;
}

static bool tb_store_name_is_valid(const char *name) {
  return name != NULL && name[0] != 0 &&
         strlen(name) < program_store::NAME_SIZE;
}

static int load_focal_program_from_store(const program_store::Entry &entry) {
  if (entry.kind != program_store::NodeKind::FILE ||
      entry.type != program_store::ProgramType::FOCAL ||
      !tb_store_name_is_valid(entry.name))
    return -1;
  const int slot = tb_alloc_program_slot(entry.name);
  TbProgram &program = programs[slot];
  u16 len = 0;
#if defined(MK61_LANGUAGE_VM_COMPILER)
  program.source_revision = portable_system::call(MK61_SYS_RESOURCE_READ);
#endif
  focal_trace_message("LOAD", entry.name);
  if (!program_store::read_id(entry.id, (u8 *)program.source,
                              TB_SOURCE_SIZE - 1, &len))
    return -1;
#if defined(MK61_LANGUAGE_VM_COMPILER)
  if (program.source_revision != portable_system::call(MK61_SYS_RESOURCE_READ))
    return -1;
#endif
  program.source[len] = 0;
  program.source_len = len;
  tb_copy_text(program.name, sizeof(program.name), entry.name);
  program.store_id = entry.id;
  program.parent_id = entry.parent_id;
  NextFocal = (i8)slot;
  return slot;
}

static int load_focal_program_from_store(u16 id) {
  program_store::Entry entry;
  return program_store::entry_by_id(id, entry)
             ? load_focal_program_from_store(entry)
             : -1;
}

static int load_focal_program_from_store(const char *name) {
  if (!tb_store_name_is_valid(name))
    return -1;
  const int count = program_store::count(program_store::ProgramType::FOCAL);
  for (int i = 0; i < count; i++) {
    program_store::Entry entry;
    if (program_store::entry(program_store::ProgramType::FOCAL, i, entry) &&
        strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
      return load_focal_program_from_store(entry);
    }
  }
  return -1;
}
#endif

static int focal_program_count(void) {
#ifndef FOCAL_HOST_TEST
  return program_store::count(program_store::ProgramType::FOCAL);
#else
  int count = 0;
  for (int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if (tb_program_used(programs[i]))
      count++;
  }
  return count;
#endif
}

bool FocalIsReady(void) { return focal_program_count() > 0; }

void InitFocal() {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope;
  if (!scope.ok())
    return;
#endif
  focal_reset_runtime(focal_runtime());
}
[[maybe_unused]] static void draw_program_select(int active, bool allow_new) {
#ifndef FOCAL_HOST_TEST
  const int stored_count =
      program_store::count(program_store::ProgramType::FOCAL);
  if (allow_new && active == stored_count) {
    tb_message_i18n("FOCAL", "FOCAL", ">NEW", M8(">НОВАЯ"));
    return;
  }
  program_store::Entry entry;
  if (active >= 0 &&
      program_store::entry(program_store::ProgramType::FOCAL, active, entry)) {
    char line1[17];
    snprintf(line1, sizeof(line1), ">%s", entry.name);
    tb_message_i18n("FOCAL", "FOCAL", line1, line1);
    return;
  }
  tb_message_i18n("FOCAL", "FOCAL", ">EMPTY", M8(">ПУСТО"));
#else
  char line1[17];
  if (allow_new && active == TB_PROGRAM_COUNT)
    tb_copy_text(line1, sizeof(line1), ">NEW");
  else if (active >= 0 && active < TB_PROGRAM_COUNT &&
           tb_program_used(programs[active])) {
    snprintf(line1, sizeof(line1), ">%s", programs[active].name);
  } else
    tb_copy_text(line1, sizeof(line1), ">EMPTY");
  tb_message_i18n("FOCAL", "FOCAL", line1, line1);
#endif
}

[[maybe_unused]] static int next_used_program(int active, int delta,
                                              bool allow_new) {
  const int max_index = allow_new ? TB_PROGRAM_COUNT : TB_PROGRAM_COUNT - 1;
  int current = active;
  for (int i = 0; i <= max_index; i++) {
    current += delta;
    if (current < 0)
      current = max_index;
    if (current > max_index)
      current = 0;
    if (current == TB_PROGRAM_COUNT)
      return current;
    if (tb_program_used(programs[current]))
      return current;
  }
  return active;
}

static int select_focal_program(bool allow_new, u16 *new_parent = NULL) {
#ifndef FOCAL_HOST_TEST
  program_store::Entry entry = {};
  u16 directory = TB_ROOT_STORE_ID;
  const ProgramStoreFileDialogResult result =
      program_store_choose_file(program_store::ProgramType::FOCAL,
                                TB_ROOT_STORE_ID, allow_new, entry, directory);
  if (result == ProgramStoreFileDialogResult::CANCELLED)
    return -1;
  if (result == ProgramStoreFileDialogResult::NEW_FILE) {
    if (new_parent != NULL)
      *new_parent = directory;
    return TB_PROGRAM_COUNT;
  }
  return load_focal_program_from_store(entry);
#else
  if (new_parent != NULL)
    *new_parent = TB_ROOT_STORE_ID;
  int active = -1;
  for (int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if (tb_program_used(programs[i])) {
      active = i;
      break;
    }
  }
  if (active < 0)
    active = allow_new ? TB_PROGRAM_COUNT : -1;
  if (active < 0)
    return -1;
  while (true) {
    draw_program_select(active, allow_new);
    const i32 key = kbd::get_key_wait();
    switch (key) {
    case KEY_LEFT:
      active = next_used_program(active, -1, allow_new);
      break;
    case KEY_RIGHT:
      active = next_used_program(active, 1, allow_new);
      break;
    case KEY_OK:
      return active;
    case KEY_ESC:
      return -1;
    }
  }
#endif
}

bool FOCAL_library_select(void) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if (!workspace_scope.ok())
    return false;
#endif
  const int program = select_focal_program(false);
  if (program >= 0) {
    (void)tb_run_program(program);
    focal_finish_wait();
  }
  return true;
}

static void draw_focal_editor(const char *source, u16 len, u16 cursor,
                              u16 view_top, bool sms_cursor = false) {
  text_editor::draw(main_lcd(), source, len, cursor, view_top, sms_cursor);
}

static bool tb_confirm_save(void) {
  tb_message_i18n("Save FOCAL?", M8("Сохранить?"), "OK=yes ESC=no",
                  M8("OK=да ESC=нет"));
  while (true) {
    const i32 key = kbd::get_key_wait();
    if (key == KEY_OK || key == KEY_OK_PRESS)
      return true;
    if (key == KEY_ESC || key == KEY_ESC_PRESS)
      return false;
  }
}

static bool tb_name_insert_char(char *name, u16 &len, u16 &cursor, char ch) {
  if (ch == ' ' && len == 0)
    return false;
  char text[2] = {tb_upper(ch), 0};
  return text_editor::insert_text(name, len, cursor, TB_NAME_SIZE, text);
}

static void tb_draw_name_editor(const char *name, u16 cursor, bool sms_cursor) {
  const u16 len = (u16)strlen(name);
  if (cursor > len)
    cursor = len;
  const u16 window = (cursor > lcd_display::COLS - 2)
                         ? (u16)(cursor - (lcd_display::COLS - 2))
                         : 0;
  char line[17];
  line[0] = '>';
  u8 pos = 1;
  while (pos < lcd_display::COLS && name[window + pos - 1] != 0) {
    line[pos] = name[window + pos - 1];
    pos++;
  }
  while (pos < lcd_display::COLS)
    line[pos++] = ' ';
  line[lcd_display::COLS] = 0;
  tb_message_i18n("FOCAL name", M8("Имя"), line, line);

  MK61DisplayUpdate update(main_lcd());
  const u8 cursor_col = (u8)(1 + cursor - window);
  main_lcd().setCursor(cursor_col, 1);
  if (main_lcd().supportsCursor())
    main_lcd().cursorOn();
  else
    main_lcd().write(sms_cursor ? text_editor::SMS_CURSOR_ASCII
                                : text_editor::CURSOR_ASCII);
}

[[maybe_unused]] static bool tb_input_program_name(char *name, usize size) {
  if (size == 0)
    return false;
  name[size - 1] = 0;
  u16 len = (u16)strlen(name);
  if (len >= size)
    len = (u16)size - 1;
  u16 cursor = len;
  text_editor::SmsState sms = {};
  text_editor::Shift shift = text_editor::Shift::NONE;
  while (true) {
    const u32 now = millis();
    if (sms.active && now >= sms.deadline_ms)
      text_editor::sms_reset(sms);
    tb_draw_name_editor(name, cursor, sms.active);
    const i32 key = kbd::get_key_wait();
    const bool shifted = shift != text_editor::Shift::NONE;
    const int digit = text_editor::digit_from_key(key);

    if (!shifted && sms.active) {
      if (text_editor::sms_key_is_letters(key)) {
        text_editor::sms_tap(name, len, cursor, TB_NAME_SIZE, sms, key, now);
        continue;
      }
      if (text_editor::sms_key_is_space(key)) {
        text_editor::sms_reset(sms);
        tb_name_insert_char(name, len, cursor, ' ');
        continue;
      }
      if (digit == 0) {
        text_editor::sms_reset(sms);
        continue;
      }
      if (key == KEY_PP) {
        text_editor::sms_reset(sms);
        tb_name_insert_char(name, len, cursor, ' ');
        continue;
      }
      text_editor::sms_reset(sms);
    }

    if (!shifted && (key == KEY_K || key == KEY_ALPHA)) {
      shift =
          (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
      text_editor::sms_reset(sms);
      continue;
    }
    if (!shifted && (key == KEY_OK || key == KEY_OK_PRESS))
      return len > 0;
    if (!shifted && (key == KEY_ESC || key == KEY_ESC_PRESS))
      return false;
    if (key == KEY_CX && (shift == text_editor::Shift::ALPHA ||
                          kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      len = 0;
      cursor = 0;
      name[0] = 0;
      shift = text_editor::Shift::NONE;
      continue;
    }
    if ((key == KEY_LEFT || key == KEY_LEFT_PRESS) &&
        (shift == text_editor::Shift::ALPHA ||
         kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if (!shifted && (key == KEY_LEFT || key == KEY_LEFT_PRESS)) {
      text_editor::sms_reset(sms);
      text_editor::move_cursor_left(name, cursor);
      continue;
    }
    if (!shifted && (key == KEY_RIGHT || key == KEY_RIGHT_PRESS)) {
      text_editor::sms_reset(sms);
      text_editor::move_cursor_right(name, len, cursor);
      continue;
    }
    if (!shifted && key == KEY_CX) {
      text_editor::sms_reset(sms);
      text_editor::backspace(name, len, cursor);
      continue;
    }

    if (shift == text_editor::Shift::ALPHA && digit >= 0) {
      const char *symbol = text_editor::symbol_for_digit_key(key);
      if (symbol != NULL && symbol[0] != 0)
        tb_name_insert_char(name, len, cursor, symbol[0]);
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    if (shift == text_editor::Shift::ALPHA) {
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    if (shift == text_editor::Shift::K &&
        text_editor::sms_key_is_letters(key)) {
      text_editor::sms_tap(name, len, cursor, TB_NAME_SIZE, sms, key, now);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if (shift == text_editor::Shift::K && text_editor::sms_key_is_space(key)) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, ' ');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if (shift == text_editor::Shift::K) {
      const char *punctuation = text_editor::kshift_text_for_key(key);
      text_editor::sms_reset(sms);
      if (punctuation != NULL && punctuation[0] != 0 && punctuation[1] == 0) {
        tb_name_insert_char(name, len, cursor, punctuation[0]);
      }
      shift = text_editor::Shift::NONE;
      continue;
    }
    if (key == KEY_PP) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, ' ');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if (digit >= 0) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, (char)('0' + digit));
      shift = text_editor::Shift::NONE;
      continue;
    }
    shift = text_editor::Shift::NONE;
  }
}

static bool store_edited_program(int slot, char *source, const char *name,
                                 u16 parent = TB_ROOT_STORE_ID) {
  if (slot < 0 || slot > TB_PROGRAM_COUNT)
    return tb_error("SLOT?");
  if (!source ||
      text_editor::bounded_length(source, TB_SOURCE_SIZE) >= TB_SOURCE_SIZE)
    return tb_error("FULL?");
  if (!name || !*name || strlen(name) >= TB_NAME_SIZE)
    return tb_error("NAME?");
  if (slot == TB_PROGRAM_COUNT) {
    slot = find_free_program();
    if (slot < 0)
      slot = 0;
  }
  const bool used = tb_program_used(programs[slot]);
  u16 previous = used ? programs[slot].store_id : TB_INVALID_STORE_ID;
  char old_name[TB_NAME_SIZE] = {};
  if (used)
    tb_copy_text(old_name, sizeof(old_name), programs[slot].name);
  const bool legacy_rename =
      previous == TB_INVALID_STORE_ID && *old_name && !tb_streq(old_name, name);
  if (legacy_rename && focal_persist_exists(name))
    return tb_error("NAME?");
  if (!focal_text::transform(source, TB_SOURCE_SIZE, true) ||
      !focal_text::transform(source, TB_SOURCE_SIZE, false))
    return tb_error("FULL?");
  u16 saved = previous;
  bool written = focal_persist_write(parent, previous, name, source,
                                     (u16)strlen(source), saved);
  bool expanded = focal_text::transform(source, TB_SOURCE_SIZE, true);
  if (!written || !expanded)
    return tb_error("FULL?");
  if (legacy_rename && !focal_persist_remove(previous, old_name)) {
    (void)focal_persist_remove(saved, name);
    return tb_error("FULL?");
  }
  // Retain the exact persisted text for source-backed resource offsets. Only
  // the separate editor view expands names; no caller's old slot is clobbered.
  tb_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  (void)focal_text::transform(programs[slot].source, TB_SOURCE_SIZE, false);
  programs[slot].source_len = (u16)strlen(programs[slot].source);
  programs[slot].store_id = saved;
  programs[slot].parent_id = parent;
  tb_copy_text(programs[slot].name, sizeof(programs[slot].name), name);
#if defined(MK61_LANGUAGE_VM_COMPILER)
  programs[slot].source_revision =
      portable_system::call(MK61_SYS_RESOURCE_READ);
#endif
  NextFocal = (i8)slot;
  focal_trace_message("SAVE", name);
  display_focal_saved(slot);
  return true;
}
static void EditFocalSlot(int slot, u16 new_parent = TB_ROOT_STORE_ID) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope editing(FOCAL_EDITOR_WORKSPACE);
  if (!editing.ok())
    return;
  tb_activate_inherited_text_font();
#endif
  if (slot < 0 || slot > TB_PROGRAM_COUNT)
    return;
  const bool new_program = slot == TB_PROGRAM_COUNT;
  if (new_program) {
    const int free_slot = find_free_program();
    slot = free_slot >= 0
               ? free_slot
               : ((NextFocal >= 0 && NextFocal < TB_PROGRAM_COUNT) ? NextFocal
                                                                   : 0);
  }
  if (slot < 0 || slot >= TB_PROGRAM_COUNT)
    return;

  const bool original_used = tb_program_used(programs[slot]);
  const u16 original_id = programs[slot].store_id;
#ifdef FOCAL_HOST_TEST
  (void)original_id;
#endif
  if (new_program) {
    programs[slot].source[0] = 0;
    programs[slot].source_len = 0;
    programs[slot].name[0] = 0;
    programs[slot].store_id = TB_INVALID_STORE_ID;
    programs[slot].parent_id = new_parent;
  }
  char *const source = focal_editor_source();
  if (!focal_text::editor_copy(programs[slot].source, source, TB_SOURCE_SIZE)) {
    tb_error("FULL?");
    return;
  }

  const auto restore_original = [&]() {
#ifndef FOCAL_HOST_TEST
    if (original_used && original_id != TB_INVALID_STORE_ID) {
      (void)load_focal_program_from_store(original_id);
      return;
    }
#endif
    if (!original_used) {
      memset(&programs[slot], 0, sizeof(programs[slot]));
      programs[slot].store_id = TB_INVALID_STORE_ID;
      programs[slot].parent_id = TB_ROOT_STORE_ID;
    }
  };

  text_editor::Buffer editor = {
      source, TB_SOURCE_SIZE,           (u16)strlen(source), 0,
      0,      text_editor::Shift::NONE, {false, -1, 0, 0}};
#if (defined(MK61_DISPLAY_LCD1602) && !defined(FOCAL_HOST_TEST)) ||            \
    defined(MK61_BUILD_PORTABLE_SYSTEM)
  text_editor::DisplaySession display_session(main_lcd());
#endif

  bool dirty = true;
#ifndef FOCAL_HOST_TEST
  u32 display_mode_revision = main_lcd().displayModeRevision();
#endif

  while (true) {
#ifndef FOCAL_HOST_TEST
    // Редактор владеет циклом переднего плана, поэтому сам должен поддерживать
    // пульс USB-экрана, виртуальные клавиши и передачу кадров.
    idle_main_process();
    const u32 next_display_mode_revision = main_lcd().displayModeRevision();
    if (next_display_mode_revision != display_mode_revision) {
      display_mode_revision = next_display_mode_revision;
      dirty = true;
    }
#endif
    const u32 now = millis();
    if (editor.sms.active && now >= editor.sms.deadline_ms) {
      text_editor::sms_reset(editor.sms);
      dirty = true;
    }
    if (dirty) {
      text_editor::ensure_cursor_visible(main_lcd(), source, editor.len,
                                         editor.cursor, editor.view_top);
      draw_focal_editor(source, editor.len, editor.cursor, editor.view_top,
                        editor.sms.active);
      dirty = false;
    }
    kbd::scan();
    i32 key_code = kbd::get_key(key_state::PRESSED);
    if (key_code < 0) {
      main_lcd().flush();
      delay(1);
      continue;
    }
    if (key_code == KEY_CX && editor.shift != text_editor::Shift::ALPHA &&
        kbd::is_key_pressed(KEY_ALPHA)) {
      editor.shift = text_editor::Shift::ALPHA;
    }
    if ((key_code == KEY_LEFT || key_code == KEY_LEFT_PRESS) &&
        (editor.shift == text_editor::Shift::ALPHA ||
         kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      editor.shift = text_editor::Shift::NONE;
      dirty = true;
      continue;
    }
    const text_editor::KeyResult result =
        focal_handle_editor_key(editor, "\n", key_code, now);
    dirty = result != text_editor::KeyResult::NONE;
    if (result == text_editor::KeyResult::SAVE) {
#ifndef FOCAL_HOST_TEST
      kbd::handoff(kbd::Event(key_code));
#endif
      main_lcd().cursorOff();
      if (!tb_confirm_save()) {
        restore_original();
        return;
      }
      char name[TB_NAME_SIZE];
      memset(name, 0, sizeof(name));
      if (slot >= 0 && slot < TB_PROGRAM_COUNT &&
          tb_program_used(programs[slot])) {
        tb_copy_text(name, sizeof(name), programs[slot].name);
      } else
        tb_program_default_name(find_free_program() < 0 ? 0
                                                        : find_free_program(),
                                name, sizeof(name));
      u16 parent = (slot >= 0 && slot < TB_PROGRAM_COUNT &&
                    tb_program_used(programs[slot]))
                       ? programs[slot].parent_id
                       : new_parent;
#ifndef FOCAL_HOST_TEST
      if (!program_store_choose_save_target(program_store::ProgramType::FOCAL,
                                            parent, name, sizeof(name),
                                            parent)) {

        dirty = true;
        continue;
      }
#else
      if (!tb_input_program_name(name, sizeof(name))) {

        dirty = true;
        continue;
      }
#endif
      if (store_edited_program(slot, source, name, parent))
        return;
      delay(700);
      editor.cursor = next_compiled.source_offset < editor.len
                          ? next_compiled.source_offset
                          : editor.len;
      editor.view_top = 0;
      dirty = true;
    }
  }
}

void EditFocal(void) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if (!workspace_scope.ok())
    return;
#endif
  u16 new_parent = TB_ROOT_STORE_ID;
  const int slot = select_focal_program(true, &new_parent);
  if (slot < 0)
    return;
  EditFocalSlot(slot, new_parent);
}

bool EditFocalProgram(const char *name) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if (!workspace_scope.ok())
    return false;
#endif
#ifndef FOCAL_HOST_TEST
  const int slot = load_focal_program_from_store(name);
  if (slot < 0)
    return false;
  EditFocalSlot(slot);
  return true;
#else
  (void)name;
  return false;
#endif
}

bool EditFocalProgram(u16 id) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if (!workspace_scope.ok())
    return false;
  const int slot = load_focal_program_from_store(id);
  if (slot < 0)
    return false;
  EditFocalSlot(slot);
  return true;
#else
  (void)id;
  return false;
#endif
}

FocalRunStatus RunFocalProgram(const char *name) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope;
  if (!scope.ok())
    return FocalRunStatus::UNAVAILABLE;
  int slot = load_focal_program_from_store(name);
#else
  int slot = find_program_by_name(name);
#endif
  auto status = tb_run_program(slot);
  focal_finish_wait();
  return status;
}
FocalRunStatus RunFocalProgram(u16 id) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope scope;
  if (!scope.ok())
    return FocalRunStatus::UNAVAILABLE;
  int slot = load_focal_program_from_store(id);
#else
  int slot = id < TB_PROGRAM_COUNT ? int(id) : -1;
#endif
  auto status = tb_run_program(slot);
  focal_finish_wait();
  return status;
}
static bool FOCAL_run_menu(void) { return FOCAL_library_select(); }

static bool FOCAL_edit_menu(void) {
  EditFocal();
  return true;
}

static bool FOCAL_clear_data(void) {

  focal_clear_array();
  tb_message_i18n("FOCAL data", M8("Данные"), "cleared", M8("очищены"));
  delay(700);
  return true;
}

static constexpr t_punct TB_EDIT_PUNCT = {
    .size = 10, .action = &FOCAL_edit_menu, .text = "Edit FOCAL"};
static constexpr t_punct TB_RUN_PUNCT = {
    .size = 10, .action = &FOCAL_run_menu, .text = "Run FOCAL"};
static constexpr t_punct TB_CLEAR_PUNCT = {
    .size = 10, .action = &FOCAL_clear_data, .text = "Clear DATA"};

#ifndef FOCAL_HOST_TEST
static constexpr auto RU_TB_EDIT_PUNCT =
    M8_PUNCT(15, &FOCAL_edit_menu, "Правка");
static constexpr auto RU_TB_RUN_PUNCT = M8_PUNCT(15, &FOCAL_run_menu, "Запуск");
static constexpr auto RU_TB_CLEAR_PUNCT =
    M8_PUNCT(15, &FOCAL_clear_data, "Сброс данных");
#endif

bool FOCAL_menu_select(void) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if (!workspace_scope.ok())
    return false;
#endif
  t_punct *items[] = {
#ifndef FOCAL_HOST_TEST
      (t_punct *)(focal_language_is_ru()
                      ? mk8::punct_view<t_punct>(RU_TB_EDIT_PUNCT)
                      : &TB_EDIT_PUNCT),
      (t_punct *)(focal_language_is_ru()
                      ? mk8::punct_view<t_punct>(RU_TB_RUN_PUNCT)
                      : &TB_RUN_PUNCT),
      (t_punct *)(focal_language_is_ru()
                      ? mk8::punct_view<t_punct>(RU_TB_CLEAR_PUNCT)
                      : &TB_CLEAR_PUNCT)
#else
      (t_punct *)&TB_EDIT_PUNCT, (t_punct *)&TB_RUN_PUNCT,
      (t_punct *)&TB_CLEAR_PUNCT
#endif
  };
  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  menu.select();
  return true;
}

#ifdef FOCAL_HOST_TEST
extern "C" void FocalNextReset() {
  focal_host_fixture::reset();
  InitFocal();
  focal_host_angle_unit = RADIAN;
  host_input_count = host_input_index = 0;
}
extern "C" int FocalNextRun(const char *source) {
  tb_copy_text(programs[0].source, sizeof(programs[0].source), source);
  programs[0].source_len = (u16)strlen(programs[0].source);
  NextFocal = 0;
  return (int)tb_run_program(0);
}
extern "C" bool FocalNextCompile(const char *source) {
  return tb_compile_source(source);
}
extern "C" double FocalNextVar(int index) {
  return focal_runtime().variables[index].number();
}
extern "C" double FocalNextArray(int name, int i, int j) {
  double key = 1.0 + name * 1073741824.0 + i * 32768.0 + j;
  for (unsigned n = 0; n < 64; n += 2)
    if (focal_runtime().array[n].number() == key)
      return focal_runtime().array[n + 1].number();
  return 0;
}
extern "C" void FocalNextInputs(const double *values, unsigned n) {
  host_input_count = n < 16 ? n : 16;
  host_input_index = 0;
  memcpy(host_input_values, values, host_input_count * sizeof(double));
}
extern "C" const char *FocalNextPrompt() { return host_prompt; }
extern "C" const char *FocalNextScreen(int row) { return main_lcd().line(row); }
extern "C" bool FocalTestExpandOperators(const char *input, char *output,
                                         int size) {
  return size > 0 && focal_text::editor_copy(input, output, (unsigned)size);
}
extern "C" void FocalNextAngleMode(int unit) {
  focal_host_angle_unit = (AngleUnit)unit;
}
extern "C" unsigned FocalNextRuntimeSize() { return sizeof(FocalRuntime); }
extern "C" void FocalNextEdit(const int *keys, int n, char *buffer, int size) {
  text_editor::Buffer editor = {buffer,
                                (u16)size,
                                (u16)strlen(buffer),
                                (u16)strlen(buffer),
                                0,
                                text_editor::Shift::NONE,
                                {false, -1, 0, 0}};
  for (int i = 0; i < n; ++i)
    (void)focal_editor::handle(editor, "\n", keys[i], (u32)(i * 100));
}
#endif
#endif
