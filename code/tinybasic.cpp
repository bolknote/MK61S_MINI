#if defined(MK61_BUILD_TINYBASIC_MODULE)
  #define TinyBASIC_library_select mk61_module_tinybasic_library_select
  #define TinyBASIC_menu_select mk61_module_tinybasic_menu_select
  #define CompileTinyBasic mk61_module_compile_tinybasic
  #define InitTinyBasic mk61_module_init_tinybasic
  #define TinyBasicIsReady mk61_module_tinybasic_is_ready
  #define RunTinyBasic mk61_module_run_tinybasic
  #define RunTinyBasicProgram mk61_module_run_tinybasic_program
  #define RunTinyBasicProgramStatus mk61_module_run_tinybasic_program_status
  #define EditTinyBasic mk61_module_edit_tinybasic
  #define EditTinyBasicProgram mk61_module_edit_tinybasic_program
#endif

#ifdef TINYBASIC_HOST_TEST
#include "rust_types.h"
#include "tinybasic.hpp"
#include "keyboard_layout.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MK61_TINYBASIC_IS_LOADABLE
  #define MK61_TINYBASIC_IS_LOADABLE 0
#endif

#if MK61_ENABLE_TINYBASIC && \
    (!MK61_TINYBASIC_IS_LOADABLE || defined(MK61_BUILD_TINYBASIC_MODULE) || \
     defined(TINYBASIC_HOST_TEST))
static const int KEY_LEFT = keyboard_layout::active().left;
static const int KEY_RIGHT = keyboard_layout::active().right;
static const int KEY_OK = keyboard_layout::active().ok;
static const int KEY_ESC = keyboard_layout::active().esc;
static const int KEY_K = keyboard_layout::active().k;
static const int KEY_ALPHA = keyboard_layout::active().alpha;
static const int KEY_CX = keyboard_layout::active().cx;
static const int KEY_PP = keyboard_layout::active().pp;
static const int KEY_SHG_RIGHT_PRESS = keyboard_layout::active().shg_right;
static const int KEY_SHG_LEFT_PRESS = keyboard_layout::active().shg_left;
static const int KEY_LEFT_PRESS = KEY_LEFT;
static const int KEY_RIGHT_PRESS = KEY_RIGHT;
static const int KEY_OK_PRESS = KEY_OK;
static const int KEY_ESC_PRESS = KEY_ESC;

namespace lcd_display {
  static constexpr u8 COLS = 16;
}

typedef enum {
  X1 = 0,
  X  = 1,
  Y  = 2,
  Z  = 3,
  T  = 4
} stack;

typedef enum {
  RADIAN = 10,
  DEGREE = 11,
  GRADE = 12
} AngleUnit;

static AngleUnit tinybasic_host_angle_unit = RADIAN;
AngleUnit read_grade_switch(void) { return tinybasic_host_angle_unit; }

namespace mk61_ref {
  double host_stack_value[5];
  double host_register_value[16];
  bool host_rf_enabled;
}

class MK61Display {
  public:
    static constexpr u8 MAX_ROWS = 8;
    MK61Display(void) : x(0), y(0), row_count(MAX_ROWS), reported_cols(16) {
      clear();
    }
    void clear(void) {
      memset(lines, ' ', sizeof(lines));
      for(int row = 0; row < MAX_ROWS; row++) lines[row][16] = 0;
      x = 0;
      y = 0;
    }
    void flush(void) {}
    void setCursor(u8 col, u8 row) {
      x = (col < 16) ? col : 15;
      y = (row < MAX_ROWS) ? row : (MAX_ROWS - 1);
    }
    void cursorOn(void) {}
    void cursorOff(void) {}
    bool supportsCursor(void) const { return false; }
    void write(u8 value) {
      if(x < 16 && y < MAX_ROWS) lines[y][x++] = (char) value;
    }
    void print(const char* text) {
      if(text == NULL) return;
      while(*text != 0) write((u8) *text++);
    }
    void print(char value) { write((u8) value); }
    u8 cols(void) const { return reported_cols; }
    void setReportedCols(u8 cols) { reported_cols = cols; }
    u8 rows(void) const { return row_count; }
    void setRows(u8 rows) { row_count = (rows < 1) ? 1 : ((rows > MAX_ROWS) ? MAX_ROWS : rows); }
    const char* line(u8 row) const { return lines[(row < MAX_ROWS) ? row : 0]; }
  private:
    u8 x;
    u8 y;
    u8 row_count;
    u8 reported_cols;
    char lines[MAX_ROWS][17];
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display&) {}
};

static MK61Display host_lcd;
MK61Display& main_lcd(void) { return host_lcd; }

enum class key_state {PRESSED=0, RELEASED=0x40};

namespace kbd {
  static bool host_alpha_pressed;
  static bool host_wait_esc;
  isize scan(void) { return 0; }
  i32 get_key(key_state) { return -1; }
  i32 get_key_wait(void) { return host_wait_esc ? KEY_ESC : KEY_OK; }
  bool is_key_pressed(i32 key_code) { return key_code == KEY_ALPHA && host_alpha_pressed; }
}

static u32 tinybasic_host_millis;
u32 millis(void) { return tinybasic_host_millis += 17; }
void delay(usize ms) { tinybasic_host_millis += (u32) ms; }

typedef bool (*menu_action)(void);
struct t_punct {
  u8 size;
  menu_action action;
  char text[16];
};

class class_menu {
  public:
    class_menu(t_punct**, int) {}
    void select(void) {}
};

namespace library_mk61 {
  bool language_is_ru(void) { return false; }
}
#endif

#else
#include "rust_types.h"
#include "Arduino.h"
#include "lcd_gui.hpp"
#include "tools.hpp"
#include "menu.hpp"
#include "tinybasic.hpp"
#include "keyboard.h"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#include "program_store.hpp"
#include "entropy_pool.hpp"
#include "development.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

#include "bounded_string.hpp"
#include "number_format.hpp"
#include "utf8_codec.hpp"

#include <type_traits>

#if MK61_ENABLE_TINYBASIC && \
    (!MK61_TINYBASIC_IS_LOADABLE || defined(MK61_BUILD_TINYBASIC_MODULE) || \
     defined(TINYBASIC_HOST_TEST))

static constexpr u16 TB_INVALID_STORE_ID = 0xFFFF;
static constexpr u16 TB_ROOT_STORE_ID = 0xFFFF;

#include "mk_math.hpp"
#ifdef TINYBASIC_HOST_TEST
#define MK61_REF_HOST_TEST
#endif
#include "mk61_ref.hpp"

#ifdef TINYBASIC_HOST_TEST
#define TEXT_EDITOR_HOST_TEST
#endif
#include "text_editor.hpp"
#ifndef TINYBASIC_HOST_TEST
#include "language_workspace.hpp"
#endif

using namespace kbd;

#ifndef TINYBASIC_HOST_TEST
extern void idle_main_process(void);
#endif

#ifndef TINYBASIC_HOST_TEST
static void tb_activate_inherited_text_font(void) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  if((portable_system::call(MK61_SERVICE_CAPABILITIES) &
      MK61_SERVICE_CAP_TEXT_FONT) != 0) {
    (void) portable_system::call(
        MK61_SYS_TEXT_FONT, MK61_SYS_TEXT_FONT_ACTIVATE);
  }
#else
  (void) program_store_text_font_activate();
#endif
}
#endif

#ifdef TINYBASIC_HOST_TEST
static constexpr int TB_PROGRAM_COUNT = 8;
#else
static constexpr int TB_PROGRAM_COUNT = 1;
#endif
static_assert(TB_PROGRAM_COUNT > 0 && TB_PROGRAM_COUNT <= 127,
              "TinyBASIC source index must fit signed byte snapshot field");
static constexpr int TB_SOURCE_SIZE = 3585;
static constexpr int TB_NAME_SIZE = 32;
#ifndef TINYBASIC_HOST_TEST
static_assert(TB_SOURCE_SIZE == program_store::MAX_TINYBASIC_TEXT_SIZE + 1,
              "Tiny BASIC editor quota must match the filesystem quota");
static_assert(TB_NAME_SIZE == program_store::NAME_SIZE,
              "Tiny BASIC names must match the filesystem quota");
#endif
static constexpr int TB_MAX_LINES = 192;
static_assert(TB_MAX_LINES <= 255, "TinyBASIC line count must fit one byte");
static constexpr int TB_PRINT_BUFFER_SIZE = 96;
static constexpr int TB_CALL_DEPTH = 16;
static constexpr int TB_FOR_DEPTH = 16;
static constexpr int TB_EXPR_DEPTH = 96;
static constexpr int TB_COMMAND_DEPTH = 16;
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
static constexpr i32 TB_EDITOR_BACKSPACE_KEY = -1;
#else
static constexpr i32 TB_EDITOR_BACKSPACE_KEY = KEY_CX;
#endif

enum class TbFlowKind : u8 {
  NEXT,
  JUMP,
  STOP,
  INTERRUPTED,
  ERROR
};

enum class TbCommand : u8 {
  CMD_NONE,
  CMD_REM,
  CMD_LET,
  CMD_PRINT,
  CMD_INPUT,
  CMD_IF,
  CMD_GOTO,
  CMD_GOSUB,
  CMD_RETURN,
  CMD_FOR,
  CMD_NEXT,
  CMD_CLS,
  CMD_PAUSE,
  CMD_END
};

// PATB keeps dispatch information beside the keyword spelling.  The low bits
// identify the command; the high bits tell the scanner how that command ends.
static constexpr u8 TB_COMMAND_ID_MASK = 0x1F;
static constexpr u8 TB_COMMAND_SEMICOLON_ITEMS = 0x20;
static constexpr u8 TB_COMMAND_TERMINAL = 0x40;

enum class TbFunction : u8 {
  NONE,
  SIZE,
  COLS,
  ROWS,
  PI,
  RND,
  SIN,
  COS,
  TG,
  ASIN,
  ACOS,
  ATG,
  LN,
  LG,
  EXP,
  SQRT,
  ABS,
  INT,
  FRAC,
  ROUND,
  SGN,
  MAX
};

struct TbLine {
  i16 number;
  u16 offset;
  u16 len;
};

struct TbAst {
  u8 line_count;
  u16 source_len;
  TbLine lines[TB_MAX_LINES];
};

struct TbProgram {
  u16 store_id;
  u16 parent_id;
  char name[TB_NAME_SIZE];
  char source[TB_SOURCE_SIZE];
  u16 source_len;
};

static bool tb_program_used(const TbProgram& program) {
  // Every stored BASIC program has at least one numbered source line.
  return program.source_len != 0;
}

struct TbFlow {
  TbFlowKind kind;
  i16 pc;
  u16 offset;
};

struct TbForFrame {
  double limit;
  double step;
  i16 return_pc;
  u16 return_offset;
  i8 var_index;
};

struct TbReturnFrame {
  i16 pc;
  u16 offset;
};

struct TbRunState {
  i8 call_sp;
  i8 for_sp;
  TbReturnFrame call_stack[TB_CALL_DEPTH];
  TbForFrame for_stack[TB_FOR_DEPTH];
};

static_assert(sizeof(TbForFrame) == 24,
              "TinyBASIC FOR frame must remain compact");
static_assert(sizeof(TbRunState) == 456,
              "TinyBASIC control stacks must remain compact");

// Like PATB's DE text pointer and fixed interpreter variables, command
// execution carries one compact context instead of passing the same seven
// values independently through every statement and nested IF.
struct TbCommandContext {
  const char* cursor;
  const char* end;
  const char* source;
  TbRunState* state;
  TbFlow* flow;
  i16 current_pc;
  u8 depth;
  bool execute;
};

struct TbWord {
  const char* begin;
  u8 length;
  bool dotted;
  const char* end;
};

enum class TbTargetKind : u8 {
  VAR,
  MK_REF,
  ARRAY
};

struct TbTarget {
  int index;
  mk61_ref::Ref mk_ref;
  TbTargetKind kind;
};

struct TinyBasicRuntime {
  TbProgram programs[TB_PROGRAM_COUNT];
  TbAst tb_ast;
  double tb_vars[26];
  i8 NextTinyBasic;
  char tb_last_error[17];
  char tb_pending_print[TB_PRINT_BUFFER_SIZE];
  u8 tb_print_row;
};

static_assert(std::is_standard_layout<TinyBasicRuntime>::value,
              "TinyBASIC snapshot runtime must have stable layout");
static_assert(std::is_trivially_copyable<TinyBasicRuntime>::value,
              "TinyBASIC snapshot runtime must be byte-copyable");
#ifndef TINYBASIC_HOST_TEST
static_assert(shared_memory::snapshot_schema::TINYBASIC_RUNTIME != 0,
              "TinyBASIC snapshot schema must be explicit");
#endif

static void tinybasic_reset_runtime(TinyBasicRuntime& runtime) {
  memset(&runtime, 0, sizeof(runtime));
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    runtime.programs[i].store_id = TB_INVALID_STORE_ID;
    runtime.programs[i].parent_id = TB_ROOT_STORE_ID;
  }
  runtime.NextTinyBasic = -1;
}

#ifdef TINYBASIC_HOST_TEST
static TinyBasicRuntime tinybasic_runtime_storage;
static double tinybasic_array_storage[384];
static TinyBasicRuntime& tinybasic_runtime(void) {
  return tinybasic_runtime_storage;
}
static double* tinybasic_array_data(void) {
  return tinybasic_array_storage;
}
static usize tinybasic_array_capacity(void) {
  return sizeof(tinybasic_array_storage) / sizeof(tinybasic_array_storage[0]);
}
#else
static_assert(sizeof(TinyBasicRuntime) <= language_workspace::SIZE, "TinyBASIC runtime does not fit language workspace");

static constexpr usize tinybasic_array_offset(void) {
  return (sizeof(TinyBasicRuntime) + alignof(double) - 1U) &
         ~(alignof(double) - 1U);
}
static_assert(tinybasic_array_offset() + 128U * sizeof(double) <=
                  language_workspace::SIZE,
              "TinyBASIC workspace must retain a useful PATB array");

class TinyBasicWorkspaceScope {
  public:
    TinyBasicWorkspaceScope(void)
      : lease(language_workspace::Owner::TINYBASIC, language_workspace::SIZE) {
      if(!lease.ok() || !lease.fresh()) return;
      memset(lease.data(), 0, lease.size());
      TinyBasicRuntime* runtime = (TinyBasicRuntime*) lease.data();
      tinybasic_reset_runtime(*runtime);
    }

    bool ok(void) const { return lease.ok(); }

  private:
    language_workspace::Lease lease;
};

static TinyBasicRuntime& tinybasic_runtime(void) {
  void* memory = language_workspace::data(language_workspace::Owner::TINYBASIC);
  if(memory == NULL) __builtin_trap();
  return *((TinyBasicRuntime*) memory);
}

static double* tinybasic_array_data(void) {
  u8* memory = (u8*) language_workspace::data(
      language_workspace::Owner::TINYBASIC);
  return memory == NULL
      ? NULL : (double*) (memory + tinybasic_array_offset());
}

static usize tinybasic_array_capacity(void) {
  return (language_workspace::SIZE - tinybasic_array_offset()) /
         sizeof(double);
}
#endif

#define programs         (tinybasic_runtime().programs)
#define tb_ast           (tinybasic_runtime().tb_ast)
#define tb_vars          (tinybasic_runtime().tb_vars)
#define NextTinyBasic    (tinybasic_runtime().NextTinyBasic)
#define tb_last_error    (tinybasic_runtime().tb_last_error)
#define tb_pending_print (tinybasic_runtime().tb_pending_print)
#define tb_print_row     (tinybasic_runtime().tb_print_row)

// PAUSE already provides the acknowledgement that the generic runner normally
// requests after a program. Keep it only while no later screen/input activity
// has made another final acknowledgement useful.
static bool tb_pause_is_final = false;
static TinyBasicRunMode tb_run_mode = TinyBasicRunMode::INTERACTIVE;

class TinyBasicRunModeScope {
  public:
    explicit TinyBasicRunModeScope(TinyBasicRunMode mode)
        : previous(tb_run_mode) {
      tb_run_mode = mode;
    }
    ~TinyBasicRunModeScope(void) { tb_run_mode = previous; }

  private:
    TinyBasicRunMode previous;
};

static bool tb_runs_inside_m61(void) {
  return tb_run_mode == TinyBasicRunMode::M61_SCENARIO;
}

static void tinybasic_clear_array(void) {
  double* const array = tinybasic_array_data();
  if(array != NULL) {
    memset(array, 0, tinybasic_array_capacity() * sizeof(array[0]));
  }
}

// PATB exposes SIZE in compatibility bytes and permits @(0)..@(SIZE/2).
// The source quota and the array have separate physical storage here, but the
// reported capacity still shrinks as the source grows, preserving the original
// observable contract without sacrificing floating-point array values.
static usize tinybasic_array_max_index(void) {
  const usize capacity = tinybasic_array_capacity();
  if(capacity == 0) return 0;
  const usize source_len = tb_ast.source_len;
  const usize unused_source = source_len < (usize) (TB_SOURCE_SIZE - 1)
      ? (usize) (TB_SOURCE_SIZE - 1) - source_len : 0;
  const usize source_limited = unused_source / 2U;
  const usize physical_max = capacity - 1U;
  return source_limited < physical_max ? source_limited : physical_max;
}

static double tinybasic_size_value(void) {
  return (double) (tinybasic_array_max_index() * 2U);
}

static bool tinybasic_array_index(double value, int& index) {
  if(!mk_math::is_finite(value) || value < 0.0) return false;
  const double rounded = mk_math::floor(value + 0.5);
  if(mk_math::fabs(value - rounded) > 0.0000001 ||
     rounded > (double) tinybasic_array_max_index()) return false;
  index = (int) rounded;
  return true;
}

#ifdef TINYBASIC_HOST_TEST
static u32 tb_random_state = 0x3B6B120EUL;
static double tb_host_input_value = 0.0;
static char tb_host_input_expression[128];
static double tb_host_input_values[16];
static u8 tb_host_input_count = 0;
static u8 tb_host_input_index = 0;
static char tb_host_last_prompt[TB_PRINT_BUFFER_SIZE];
static int tb_host_wait_count = 0;
#endif

static char tb_upper(char ch) {
  if(ch >= 'a' && ch <= 'z') return (char) (ch - 'a' + 'A');
  return ch;
}

static bool tb_is_space(char ch) {
  return ch == ' ' || ch == '\t';
}

static bool tb_is_digit(char ch) {
  return ch >= '0' && ch <= '9';
}

static bool tb_is_alpha(char ch) {
  ch = tb_upper(ch);
  return ch >= 'A' && ch <= 'Z';
}

static text_editor::KeyResult tinybasic_handle_editor_key(
    text_editor::Buffer& editor, const char* ok_insert_text,
    i32 key_code, u32 now) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  return text_editor::portable_handle_default_key(
      editor, ok_insert_text, key_code, now);
#else
  static const text_editor::KeyMap keys = {
    (i32) KEY_LEFT, KEY_LEFT_PRESS, (i32) KEY_RIGHT, KEY_RIGHT_PRESS,
    (i32) KEY_OK, KEY_OK_PRESS, (i32) KEY_ESC, KEY_ESC_PRESS,
    KEY_SHG_LEFT_PRESS, KEY_SHG_RIGHT_PRESS, (i32) KEY_K, KEY_ALPHA, (i32) KEY_PP
  };
  static const text_editor::Hooks hooks = {NULL, NULL, NULL, NULL, NULL};
  const text_editor::Options options = {
    ok_insert_text, true, true, true, true, TB_EDITOR_BACKSPACE_KEY
  };
  return text_editor::handle_key(editor, keys, hooks, options, key_code, now);
#endif
}

static bool tb_streq(const char* a, const char* b) {
  while(*a != 0 && *b != 0) {
    if(tb_upper(*a++) != tb_upper(*b++)) return false;
  }
  return *a == 0 && *b == 0;
}

static const char* tb_skip_spaces(const char* text) {
  while(tb_is_space(*text)) text++;
  return text;
}

static void tb_copy_text(char* dst, usize dst_size, const char* src) {
  bounded_string::copy(dst, dst_size, src);
}

static void tb_copy_range(char* dst, usize dst_size, const char* begin, const char* end) {
  if(dst_size == 0) return;
  const usize len = (usize) (end - begin);
  const usize copy_len = (len < dst_size - 1) ? len : dst_size - 1;
  memcpy(dst, begin, copy_len);
  dst[copy_len] = 0;
}

#ifndef TINYBASIC_HOST_TEST
static bool tinybasic_language_is_ru(void) {
  return library_mk61::language_is_ru();
}
#endif

static void tb_message_i18n(const char* en0, const char* ru0, const char* en1, const char* ru1) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
#ifndef TINYBASIC_HOST_TEST
  if(tinybasic_language_is_ru()) {
    lcd_ru::print_lines(ru0, ru1);
    return;
  }
#endif
  main_lcd().setCursor(0, 0);
  main_lcd().print(en0);
  main_lcd().setCursor(0, 1);
  main_lcd().print(en1);
  (void) ru0;
  (void) ru1;
}

static void tb_print_display_text(const char* text) {
  if(text == NULL) return;
#ifdef TINYBASIC_HOST_TEST
  main_lcd().print(text);
#else
  while(*text != 0) {
    const utf8_codec::Decoded decoded = utf8_codec::decode_cstring(text);
    if(decoded.size == 0) break;
    // One-byte values retain TinyBasic's historical raw/control-token path.
    // Valid multibyte UTF-8 is the Unicode text path used by FMK fonts.
    if(decoded.valid && decoded.size > 1) {
      main_lcd().writeCodepoint(decoded.codepoint <= 0xFFFFU
          ? (u16) decoded.codepoint : (u16) '?');
    } else {
      main_lcd().write((u8) *text);
    }
    text += decoded.size;
  }
#endif
}

enum class TbError : u8 { WHAT, HOW, SORRY };

static bool tb_error_code(TbError error) {
  tb_pause_is_final = false;
  const char* en = "SORRY";
  const char* ru = "НЕТ МЕСТА";
  if(error == TbError::WHAT) {
    en = "WHAT?";
    ru = "ЧТО?";
  } else if(error == TbError::HOW) {
    en = "HOW?";
    ru = "КАК?";
  }
  tb_copy_text(tb_last_error, sizeof(tb_last_error), en);
  tb_message_i18n(en, ru, "TinyBASIC", "TinyBASIC");
  return false;
}

// The interpreter has exactly the three canonical Palo Alto errors.  Mapping
// their literal first byte here keeps every call site readable while avoiding
// dozens of repeated literal-address loads in the ARM module.
#define tb_error(message) tb_error_code( \
    (message)[0] == 'W' ? TbError::WHAT : \
    (message)[0] == 'H' ? TbError::HOW : TbError::SORRY)

static void tb_display_line(u8 row, const char* text) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().setCursor(0, row);
  for(u8 i = 0; i < main_lcd().cols(); i++) {
    main_lcd().write((u8) ' ');
  }
  main_lcd().setCursor(0, row);
  tb_print_display_text(text);
}

static void tb_clear_output(void) {
  tb_pause_is_final = false;
  main_lcd().clear();
  tb_pending_print[0] = 0;
  tb_print_row = 0;
}

static bool tb_pause(void) {
  const i32 key = kbd::get_key_wait();
  tb_pause_is_final = true;
  return key != KEY_ESC && key != KEY_ESC_PRESS;
}

static void tb_report_interrupted(void) {
#ifndef TINYBASIC_HOST_TEST
  // Consume the complete ESC gesture.  Otherwise its release (or a queued
  // debounced press after the immediate edge) can leak into the calculator
  // and open its menu immediately after the scenario has been cancelled.
  kbd::handoff(kbd::Event(KEY_ESC_PRESS));
#endif
  if(!tb_runs_inside_m61()) {
    tb_message_i18n("TinyBASIC stop", "TinyBASIC стоп", "ESC", "ESC");
  }
}

static void tb_format_number(double value, char* out, usize size) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && !defined(TINYBASIC_HOST_TEST)
  if(!portable_system::format_number(value, 10, out, size) && size != 0) {
    out[0] = 0;
  }
#else
  (void) number_format::general(value, 10, out, size);
#endif
}

static bool tb_parse_number_text(const char* text, double& value,
                                 const char*& end) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && !defined(TINYBASIC_HOST_TEST)
  return portable_system::parse_number(text, value, end);
#else
  end = NULL;
  value = mk_math::strtod(text, &end);
  return end != text;
#endif
}

static void tb_ast_reset(TbAst& ast) {
  memset(&ast, 0, sizeof(ast));
}

static TbFlow tb_flow(TbFlowKind kind, i16 pc, u16 offset = 0) {
  TbFlow flow;
  flow.kind = kind;
  flow.pc = pc;
  flow.offset = offset;
  return flow;
}

static bool tb_read_word(const char* p, TbWord& out,
                         const char* limit = NULL) {
  p = tb_skip_spaces(p);
  if((limit != NULL && p >= limit) || !tb_is_alpha(*p)) return false;
  const char* const begin = p;
  u8 len = 0;
  while((limit == NULL || p < limit) && tb_is_alpha(*p)) {
    if(len != 0xFF) len++;
    p++;
  }
  out.begin = begin;
  out.length = len;
  out.dotted = (limit == NULL || p < limit) && *p == '.';
  if(out.dotted) p++;
  out.end = p;
  return len > 0;
}

static bool tb_word_matches(const TbWord& word, const char* full, u8 min_abbrev) {
  const usize full_len = strlen(full);
  if(!word.dotted && word.length != full_len) return false;
  if(word.dotted && (word.length < min_abbrev || word.length > full_len)) {
    return false;
  }
  for(usize i = 0; i < word.length; i++) {
    if(tb_upper(word.begin[i]) != full[i]) return false;
  }
  return true;
}

// Each record is: result id, packed minimum abbreviation/full length, bytes.
// Both lengths fit four bits; minimum 15 marks an exact-only word such as PI.
// A zero result id terminates the table.
static const u8 TB_COMMAND_WORDS[] = {
  (u8) TbCommand::CMD_REM,    0x33, 'R', 'E', 'M',
  (u8) TbCommand::CMD_REM,    0x36, 'R', 'E', 'M', 'A', 'R', 'K',
  (u8) TbCommand::CMD_LET,    0x13, 'L', 'E', 'T',
  (u8) TbCommand::CMD_PRINT | TB_COMMAND_SEMICOLON_ITEMS,
                              0x15, 'P', 'R', 'I', 'N', 'T',
  (u8) TbCommand::CMD_INPUT | TB_COMMAND_SEMICOLON_ITEMS,
                              0x25, 'I', 'N', 'P', 'U', 'T',
  (u8) TbCommand::CMD_IF,     0x12, 'I', 'F',
  (u8) TbCommand::CMD_GOTO | TB_COMMAND_TERMINAL,
                              0x14, 'G', 'O', 'T', 'O',
  (u8) TbCommand::CMD_GOSUB,  0x35, 'G', 'O', 'S', 'U', 'B',
  (u8) TbCommand::CMD_RETURN | TB_COMMAND_TERMINAL,
                              0x16, 'R', 'E', 'T', 'U', 'R', 'N',
  (u8) TbCommand::CMD_FOR,    0x13, 'F', 'O', 'R',
  (u8) TbCommand::CMD_NEXT,   0x14, 'N', 'E', 'X', 'T',
  (u8) TbCommand::CMD_CLS,    0x13, 'C', 'L', 'S',
  (u8) TbCommand::CMD_PAUSE,  0x35, 'P', 'A', 'U', 'S', 'E',
  (u8) TbCommand::CMD_END | TB_COMMAND_TERMINAL,
                              0x13, 'E', 'N', 'D',
  (u8) TbCommand::CMD_END | TB_COMMAND_TERMINAL,
                              0x14, 'S', 'T', 'O', 'P',
  0
};

static const u8 TB_FUNCTION_WORDS[] = {
  (u8) TbFunction::SIZE,  0x14, 'S', 'I', 'Z', 'E',
  (u8) TbFunction::COLS,  0xF4, 'C', 'O', 'L', 'S',
  (u8) TbFunction::ROWS,  0xF4, 'R', 'O', 'W', 'S',
  (u8) TbFunction::PI,    0xF2, 'P', 'I',
  (u8) TbFunction::RND,   0x13, 'R', 'N', 'D',
  (u8) TbFunction::SIN,   0x23, 'S', 'I', 'N',
  (u8) TbFunction::COS,   0x13, 'C', 'O', 'S',
  (u8) TbFunction::TG,    0x12, 'T', 'G',
  (u8) TbFunction::ASIN,  0x24, 'A', 'S', 'I', 'N',
  (u8) TbFunction::ACOS,  0x24, 'A', 'C', 'O', 'S',
  (u8) TbFunction::ATG,   0x23, 'A', 'T', 'G',
  (u8) TbFunction::LN,    0x22, 'L', 'N',
  (u8) TbFunction::LG,    0x22, 'L', 'G',
  (u8) TbFunction::EXP,   0x13, 'E', 'X', 'P',
  (u8) TbFunction::SQRT,  0x24, 'S', 'Q', 'R', 'T',
  (u8) TbFunction::ABS,   0x13, 'A', 'B', 'S',
  (u8) TbFunction::INT,   0x13, 'I', 'N', 'T',
  (u8) TbFunction::FRAC,  0x14, 'F', 'R', 'A', 'C',
  (u8) TbFunction::ROUND, 0x25, 'R', 'O', 'U', 'N', 'D',
  (u8) TbFunction::SGN,   0x23, 'S', 'G', 'N',
  (u8) TbFunction::MAX,   0x13, 'M', 'A', 'X',
  0
};

static u8 tb_lookup_word(const TbWord& word, const u8* table) {
  while(*table != 0) {
    const u8 result = *table++;
    const u8 lengths = *table++;
    const u8 min_abbrev = lengths >> 4;
    const u8 full_len = lengths & 0x0F;
    bool matches = word.dotted
        ? word.length >= min_abbrev && word.length <= full_len
        : word.length == full_len;
    for(u8 i = 0; matches && i < word.length; i++) {
      matches = tb_upper(word.begin[i]) == (char) table[i];
    }
    if(matches) return result;
    table += full_len;
  }
  return 0;
}

static bool tb_parse_mk_ref_token(const char*& p, const char* end,
                                  mk61_ref::Ref& ref) {
  p = tb_skip_spaces(p);
  if(p >= end || *p != '.') return false;
  const char* cursor = p + 1;
  if(cursor >= end || !tb_is_alpha(*cursor)) return false;
  const char first = tb_upper(*cursor++);
  ref.reg = 0;
  if(first == 'R') {
    if(cursor >= end) return false;
    const char digit = tb_upper(*cursor++);
    ref.reg = (u8) (digit - '0');
    if(ref.reg > 9) {
      ref.reg = (u8) (digit - 'A' + 10);
      if(ref.reg < 10 || ref.reg > 15) return false;
    }
    ref.kind = mk61_ref::Kind::R;
  } else {
    if(first == 'T') ref.kind = mk61_ref::Kind::T;
    else if(first >= 'X' && first <= 'Z') {
      ref.kind = (mk61_ref::Kind) (first - 'X');
    } else return false;
  }
  if(cursor < end && (tb_is_alpha(*cursor) || tb_is_digit(*cursor))) {
    return false;
  }
  p = cursor;
  return true;
}

static bool tb_read_mk_ref(const mk61_ref::Ref& ref, double& value) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && !defined(TINYBASIC_HOST_TEST)
  return portable_system::call(
      MK61_SYS_REF_READ, (u32) ref.kind, ref.reg, 0, &value);
#else
  return mk61_ref::read(ref, value);
#endif
}

static bool tb_eval_expr_range(const char* begin, const char* end,
                               double& value, const char** out_pos,
                               bool evaluate);

static bool tb_parse_target_token(const char*& p, const char* end, TbTarget& target, bool require_available = true) {
  p = tb_skip_spaces(p);
  if(p >= end) return false;

  if(*p == '@') {
    const char* cursor = tb_skip_spaces(p + 1);
    if(cursor >= end || *cursor != '(') return false;
    cursor++;
    double index_value = 0.0;
    const char* after_index = NULL;
    if(!tb_eval_expr_range(cursor, end, index_value, &after_index,
                           require_available)) return false;
    after_index = tb_skip_spaces(after_index);
    if(after_index >= end || *after_index != ')') return false;
    target.kind = TbTargetKind::ARRAY;
    target.mk_ref = {mk61_ref::Kind::X, 0};
    target.index = 0;
    if(require_available &&
       !tinybasic_array_index(index_value, target.index)) return false;
    p = after_index + 1;
    return true;
  }

  mk61_ref::Ref ref;
  if(*p == '.') {
    if(!tb_parse_mk_ref_token(p, end, ref)) return false;
    if(require_available && ref.kind == mk61_ref::Kind::R && ref.reg == 15 &&
       !mk61_ref::register_available(15)) return false;
    target.kind = TbTargetKind::MK_REF;
    target.index = -1;
    target.mk_ref = ref;
    return true;
  }

  if(!tb_is_alpha(*p)) return false;
  const int var = tb_upper(*p++) - 'A';
  if(var < 0 || var >= 26) return false;
  target.kind = TbTargetKind::VAR;
  target.index = var;
  target.mk_ref = {mk61_ref::Kind::X, 0};
  return true;
}

static bool tb_write_target(const TbTarget& target, double value) {
  if(target.kind == TbTargetKind::VAR) {
    tb_vars[target.index] = value;
    return true;
  }
  if(target.kind == TbTargetKind::ARRAY) {
    double* const array = tinybasic_array_data();
    if(array == NULL || target.index < 0 ||
       (usize) target.index >= tinybasic_array_capacity()) return false;
    array[target.index] = value;
    return true;
  }
  return mk61_ref::write(target.mk_ref, value);
}

static bool tb_parse_command_word(const char*& p, u8& command_token) {
  TbWord word;
  if(!tb_read_word(p, word)) return false;
  const u8 result = tb_lookup_word(word, TB_COMMAND_WORDS);
  if(result == 0) return false;
  command_token = result;
  p = word.end;
  return true;
}

static bool tb_consume_word(const char*& p, const char* full, u8 min_abbrev) {
  TbWord word;
  if(!tb_read_word(p, word)) return false;
  if(!tb_word_matches(word, full, min_abbrev)) return false;
  p = word.end;
  return true;
}

static bool tb_looks_like_command_start(const char* begin, const char* end) {
  const char* cursor = tb_skip_spaces(begin);
  if(cursor >= end) return false;
  const char* saved = cursor;
  u8 command_token = 0;
  if(tb_parse_command_word(cursor, command_token)) return true;
  cursor = saved;
  TbTarget target;
  if(!tb_parse_target_token(cursor, end, target, false)) return false;
  cursor = tb_skip_spaces(cursor);
  return cursor < end && *cursor == '=';
}

// PATB uses ';' between commands.  The MK-61 dialect already used ';' as the
// compact PRINT/INPUT item separator, so within those two commands it remains
// an item separator unless the following text is recognisably another command
// or assignment.  ':' is always accepted as the existing unambiguous extension.
static const char* tb_find_command_end(const char* begin, const char* end,
                                       bool semicolon_may_be_item) {
  int depth = 0;
  char quote = 0;
  for(const char* p = begin; p < end; p++) {
    if(quote != 0) {
      if(*p == quote) quote = 0;
      continue;
    }
    if(*p == '"' || *p == '\'') {
      quote = *p;
      continue;
    }
    if(*p == '(') {
      depth++;
      continue;
    }
    if(*p == ')' && depth > 0) {
      depth--;
      continue;
    }
    if(depth != 0) continue;
    if(*p == ':') return p;
    if(*p == ';' &&
       (!semicolon_may_be_item ||
        tb_looks_like_command_start(p + 1, end))) return p;
  }
  return end;
}

enum class TbTextItemKind : u8 { NONE, RANGE, CONTROL, ERROR };

struct TbTextItem {
  const char* begin;
  const char* end;
  char control;
};

// Shared equivalent of PATB's QTSTG: PRINT and INPUT use exactly the same
// quoted-string and up-arrow syntax.
__attribute__((noinline)) static TbTextItemKind tb_parse_text_item(
    const char*& p, const char* end, TbTextItem& item) {
  if(p >= end) return TbTextItemKind::NONE;
  if(*p == '"' || *p == '\'') {
    const char quote = *p++;
    item.begin = p;
    while(p < end && *p != quote) p++;
    if(p >= end) return TbTextItemKind::ERROR;
    item.end = p++;
    return TbTextItemKind::RANGE;
  }
  if(*p == '^') {
    p++;
    if(p >= end || !tb_is_alpha(*p)) return TbTextItemKind::ERROR;
    item.control = (char) (tb_upper(*p++) ^ 0x40);
    return TbTextItemKind::CONTROL;
  }
  return TbTextItemKind::NONE;
}

static double tb_trig_to_radians(double value) {
  const AngleUnit unit = read_grade_switch();
  if(unit == DEGREE) return value * 3.14159265358979323846 / 180.0;
  if(unit == GRADE) return value * 3.14159265358979323846 / 200.0;
  return value;
}

static double tb_trig_from_radians(double value) {
  const AngleUnit unit = read_grade_switch();
  if(unit == DEGREE) return value * 180.0 / 3.14159265358979323846;
  if(unit == GRADE) return value * 200.0 / 3.14159265358979323846;
  return value;
}

static double tb_apply_math_function(TbFunction function, double value) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && !defined(TINYBASIC_HOST_TEST) && \
    !MK61_APP_LOCAL_FLOAT_MATH
  // The portable module already obtains all transcendental operations from
  // one resident entry point.  TbFunction keeps the same order as that API.
  static_assert(
      (u8) TbFunction::SIN  - (u8) TbFunction::SIN == MK61_SYS_SIN &&
      (u8) TbFunction::COS  - (u8) TbFunction::SIN == MK61_SYS_COS &&
      (u8) TbFunction::TG   - (u8) TbFunction::SIN == MK61_SYS_TAN &&
      (u8) TbFunction::ASIN - (u8) TbFunction::SIN == MK61_SYS_ASIN &&
      (u8) TbFunction::ACOS - (u8) TbFunction::SIN == MK61_SYS_ACOS &&
      (u8) TbFunction::ATG  - (u8) TbFunction::SIN == MK61_SYS_ATAN &&
      (u8) TbFunction::LN   - (u8) TbFunction::SIN == MK61_SYS_LN &&
      (u8) TbFunction::LG   - (u8) TbFunction::SIN == MK61_SYS_LOG10 &&
      (u8) TbFunction::EXP  - (u8) TbFunction::SIN == MK61_SYS_EXP &&
      (u8) TbFunction::SQRT - (u8) TbFunction::SIN == MK61_SYS_SQRT,
      "Tiny BASIC math functions must follow the resident API order");
  const u8 operation = (u8) function - (u8) TbFunction::SIN;
  if(operation < 3) value = tb_trig_to_radians(value);
  value = portable_system::api->math(operation, value, 0.0);
  return operation >= 3 && operation < 6
      ? tb_trig_from_radians(value) : value;
#else
  switch(function) {
    case TbFunction::SIN:  return mk_math::sin(tb_trig_to_radians(value));
    case TbFunction::COS:  return mk_math::cos(tb_trig_to_radians(value));
    case TbFunction::TG:   return mk_math::tan(tb_trig_to_radians(value));
    case TbFunction::ASIN: return tb_trig_from_radians(mk_math::asin(value));
    case TbFunction::ACOS: return tb_trig_from_radians(mk_math::acos(value));
    case TbFunction::ATG:  return tb_trig_from_radians(mk_math::atan(value));
    case TbFunction::LN:   return mk_math::ln(value);
    case TbFunction::LG:   return mk_math::log10(value);
    case TbFunction::EXP:  return mk_math::exp(value);
    case TbFunction::SQRT: return mk_math::sqrt(value);
    default:               return 0.0;
  }
#endif
}

static double tb_next_random(void) {
#ifdef TINYBASIC_HOST_TEST
  tb_random_state = tb_random_state * 25173UL + 13849UL;
  return (double) (tb_random_state & 0xFFFFUL) / 65536.0;
#else
  return (double) (entropy_pool::next_u32(entropy_pool::Domain::TINYBASIC) >> 8) / 16777216.0;
#endif
}

enum class TbBinaryOp : u8 {
  NONE,
  NOT_EQUAL,
  LESS_EQUAL,
  GREATER_EQUAL,
  LESS,
  GREATER,
  EQUAL,
  ADD,
  SUBTRACT,
  OR,
  XOR,
  MULTIPLY,
  DIVIDE,
  MOD,
  AND
};

static constexpr u8 tb_binary_word(TbBinaryOp operation, u8 level,
                                   u8 length) {
  return (u8) operation | (u8) (level << 4) | (u8) ((length - 1) << 6);
}

// Record layout: packed operation/precedence/length, then spelling.  The
// operation fits four bits, precedence two bits and (length - 1) two bits.
// Longer comparison spellings precede their one-character prefixes.
static const u8 TB_BINARY_WORDS[] = {
  tb_binary_word(TbBinaryOp::NOT_EQUAL,     0, 2), '<', '>',
  tb_binary_word(TbBinaryOp::NOT_EQUAL,     0, 1), '#',
  tb_binary_word(TbBinaryOp::LESS_EQUAL,    0, 2), '<', '=',
  tb_binary_word(TbBinaryOp::GREATER_EQUAL, 0, 2), '>', '=',
  tb_binary_word(TbBinaryOp::LESS,          0, 1), '<',
  tb_binary_word(TbBinaryOp::GREATER,       0, 1), '>',
  tb_binary_word(TbBinaryOp::EQUAL,         0, 1), '=',
  tb_binary_word(TbBinaryOp::ADD,           1, 1), '+',
  tb_binary_word(TbBinaryOp::SUBTRACT,      1, 1), '-',
  tb_binary_word(TbBinaryOp::OR,            1, 2), 'O', 'R',
  tb_binary_word(TbBinaryOp::XOR,           1, 3), 'X', 'O', 'R',
  tb_binary_word(TbBinaryOp::MULTIPLY,      2, 1), '*',
  tb_binary_word(TbBinaryOp::DIVIDE,        2, 1), '/',
  tb_binary_word(TbBinaryOp::MOD,           2, 3), 'M', 'O', 'D',
  tb_binary_word(TbBinaryOp::AND,           2, 3), 'A', 'N', 'D',
  0
};

class TbExprParser {
  public:
    TbExprParser(const char* begin, const char* end, bool evaluate = true)
      : p(begin), end(end), depth(0), evaluate(evaluate) {}

    bool eval(double& out) {
      out = parse_binary(0);
      if(depth < 0) return false;
      if(evaluate && !mk_math::is_finite(out)) return false;
      return true;
    }

    const char* position(void) const { return p; }

  private:
    const char* p;
    const char* end;
    i8 depth;
    bool evaluate;

    bool enter(void) {
      if(depth < 0 || depth >= TB_EXPR_DEPTH) {
        depth = -1;
        return false;
      }
      depth++;
      return true;
    }

    void leave(void) {
      if(depth > 0) depth--;
    }

    void skip(void) {
      while(p < end && tb_is_space(*p)) p++;
    }

    bool match_char(char ch) {
      skip();
      if(p < end && *p == ch) {
        p++;
        return true;
      }
      return false;
    }

    bool match_not(void) {
      skip();
      if(end - p < 3 || tb_upper(p[0]) != 'N' ||
         tb_upper(p[1]) != 'O' || tb_upper(p[2]) != 'T') return false;
      if(end - p > 3 && (tb_is_alpha(p[3]) || p[3] == '.')) return false;
      p += 3;
      return true;
    }

    bool match_binary(u8 level, TbBinaryOp& operation) {
      skip();
      const u8* item = TB_BINARY_WORDS;
      while(*item != 0) {
        const u8 descriptor = *item++;
        const TbBinaryOp candidate = (TbBinaryOp) (descriptor & 0x0F);
        const u8 candidate_level = (descriptor >> 4) & 0x03;
        const u8 length = (descriptor >> 6) + 1;
        bool matches = candidate_level == level &&
                       (usize) (end - p) >= length;
        for(u8 i = 0; matches && i < length; i++) {
          matches = tb_upper(p[i]) == (char) item[i];
        }
        if(matches && tb_is_alpha((char) item[0]) &&
           p + length < end && tb_is_alpha(p[length])) {
          matches = false;
        }
        if(matches) {
          p += length;
          operation = candidate;
          return true;
        }
        item += length;
      }
      operation = TbBinaryOp::NONE;
      return false;
    }

    double apply_binary(TbBinaryOp operation, double left, double right) {
      if(!evaluate) return 0.0;
      switch(operation) {
        case TbBinaryOp::NOT_EQUAL:     return left != right ? 1.0 : 0.0;
        case TbBinaryOp::LESS_EQUAL:    return left <= right ? 1.0 : 0.0;
        case TbBinaryOp::GREATER_EQUAL: return left >= right ? 1.0 : 0.0;
        case TbBinaryOp::LESS:          return left < right ? 1.0 : 0.0;
        case TbBinaryOp::GREATER:       return left > right ? 1.0 : 0.0;
        case TbBinaryOp::EQUAL:         return left == right ? 1.0 : 0.0;
        case TbBinaryOp::ADD:           return left + right;
        case TbBinaryOp::SUBTRACT:      return left - right;
        case TbBinaryOp::OR:
          return left != 0.0 || right != 0.0 ? 1.0 : 0.0;
        case TbBinaryOp::XOR:
          return (left != 0.0) != (right != 0.0) ? 1.0 : 0.0;
        case TbBinaryOp::MULTIPLY:      return left * right;
        case TbBinaryOp::DIVIDE:
          if(right != 0.0) return left / right;
          break;
        case TbBinaryOp::MOD:
          if(right != 0.0) {
            return left - mk_math::floor(left / right) * right;
          }
          break;
        case TbBinaryOp::AND:
          return left != 0.0 && right != 0.0 ? 1.0 : 0.0;
        case TbBinaryOp::NONE:
          break;
      }
      depth = -1;
      return 0.0;
    }

    double parse_binary(u8 level) {
      if(level >= 3) return parse_prefix(false);
      double left = parse_binary((u8) (level + 1));
      while(depth >= 0) {
        TbBinaryOp operation;
        if(!match_binary(level, operation)) break;
        const double right = parse_binary((u8) (level + 1));
        left = apply_binary(operation, left, right);
      }
      return left;
    }

    __attribute__((noinline)) double parse_prefix(bool power_operand) {
      if(!enter()) return 0.0;
      double value = 0.0;
      if(match_char('+')) {
        value = parse_prefix(power_operand);
      } else if(match_char('-')) {
        value = parse_prefix(power_operand);
        if(evaluate) value = -value;
      } else if(match_not()) {
        value = parse_prefix(power_operand);
        if(evaluate) value = value == 0.0 ? 1.0 : 0.0;
      } else {
        value = power_operand ? parse_primary() : parse_power();
      }
      leave();
      return value;
    }

    double parse_power(void) {
      double left = parse_primary();
      while(depth >= 0 && match_char('^')) {
        const double right = parse_prefix(true);
        if(evaluate) left = mk_math::pow(left, right);
      }
      return left;
    }

    double parse_primary(void) {
      if(!enter()) return 0.0;
      const double value = parse_primary_inner();
      leave();
      return value;
    }

    double parse_primary_inner(void) {
      skip();
      if(p >= end) {
        depth = -1;
        return 0.0;
      }

      if(match_char('(')) {
        const double value = parse_binary(0);
        if(!match_char(')')) depth = -1;
        return value;
      }

      if(*p == '.' && p + 1 < end && tb_is_alpha(*(p + 1))) {
        mk61_ref::Ref ref;
        if(!tb_parse_mk_ref_token(p, end, ref)) {
          depth = -1;
          return 0.0;
        }
        if(!evaluate) return 0.0;
        double value = 0.0;
        if(!tb_read_mk_ref(ref, value)) {
          depth = -1;
          return 0.0;
        }
        return value;
      }

      if(*p == '@') {
        p++;
        if(!match_char('(')) {
          depth = -1;
          return 0.0;
        }
        const double index_value = parse_binary(0);
        if(!match_char(')')) {
          depth = -1;
          return 0.0;
        }
        if(!evaluate) return 0.0;
        int index = 0;
        if(!tinybasic_array_index(index_value, index)) {
          depth = -1;
          return 0.0;
        }
        double* const array = tinybasic_array_data();
        if(array == NULL) {
          depth = -1;
          return 0.0;
        }
        return array[index];
      }

      if(tb_is_digit(*p) || *p == '.') {
        const char* after = NULL;
        double value = 0.0;
        if(!tb_parse_number_text(p, value, after) || after > end) {
          depth = -1;
          return 0.0;
        }
        p = after;
        if(evaluate && !mk_math::is_finite(value)) depth = -1;
        return evaluate ? value : 0.0;
      }

      if(tb_is_alpha(*p)) {
        TbWord function;
        if(!tb_read_word(p, function, end)) {
          depth = -1;
          return 0.0;
        }
        p = function.end;

        if(!function.dotted && function.length == 1) {
          const char variable = tb_upper(*function.begin);
          if(variable >= 'A' && variable <= 'Z') {
            return evaluate ? tb_vars[variable - 'A'] : 0.0;
          }
        }
        const TbFunction function_id =
            (TbFunction) tb_lookup_word(function, TB_FUNCTION_WORDS);
        if(function_id == TbFunction::SIZE) {
          return evaluate ? tinybasic_size_value() : 0.0;
        }
        if(function_id == TbFunction::COLS) {
          return evaluate ? (double) main_lcd().cols() : 0.0;
        }
        if(function_id == TbFunction::ROWS) {
          return evaluate ? (double) main_lcd().rows() : 0.0;
        }
        if(function_id == TbFunction::PI) {
          return evaluate ? 3.14159265358979323846 : 0.0;
        }
        if(function_id == TbFunction::NONE) {
          depth = -1;
          return 0.0;
        }

        if(!match_char('(')) {
          depth = -1;
          return 0.0;
        }

        if(function_id == TbFunction::RND) {
          skip();
          if(match_char(')')) return evaluate ? tb_next_random() : 0.0;
          const double max_value = parse_binary(0);
          if(!match_char(')')) depth = -1;
          if(!evaluate) return 0.0;
          if(!(max_value >= 1.0 && max_value <= DBL_MAX)) {
            depth = -1;
            return 0.0;
          }
          const double limit = mk_math::floor(max_value);
          return 1.0 + mk_math::floor(tb_next_random() * limit);
        }

        const double a = parse_binary(0);
        double b = 0.0;
        bool has_b = false;
        if(match_char(',')) {
          b = parse_binary(0);
          has_b = true;
        }
        if(!match_char(')')) {
          depth = -1;
          return 0.0;
        }

        if((function_id == TbFunction::MAX) != has_b) {
          depth = -1;
          return 0.0;
        }
        if(!evaluate) {
          return 0.0;
        }

        if(function_id >= TbFunction::SIN &&
           function_id <= TbFunction::SQRT) {
          return tb_apply_math_function(function_id, a);
        }

        switch(function_id) {
          case TbFunction::ABS:   return mk_math::fabs(a);
          case TbFunction::INT:   return mk_math::floor(a);
          case TbFunction::FRAC:  return mk_math::frac(a);
          case TbFunction::ROUND:
            return a >= 0.0 ? mk_math::floor(a + 0.5)
                            : -mk_math::floor(-a + 0.5);
          case TbFunction::SGN:
            return (a > 0.0) ? 1.0 : ((a < 0.0) ? -1.0 : 0.0);
          case TbFunction::MAX:   return (a > b) ? a : b;
          case TbFunction::NONE:
          case TbFunction::SIZE:
          case TbFunction::COLS:
          case TbFunction::ROWS:
          case TbFunction::PI:
          case TbFunction::RND:
          case TbFunction::SIN:
          case TbFunction::COS:
          case TbFunction::TG:
          case TbFunction::ASIN:
          case TbFunction::ACOS:
          case TbFunction::ATG:
          case TbFunction::LN:
          case TbFunction::LG:
          case TbFunction::EXP:
          case TbFunction::SQRT:
            break;
        }
      }

      depth = -1;
      return 0.0;
    }
};

static bool tb_eval_expr_range(const char* begin, const char* end, double& value, const char** out_pos = NULL, bool evaluate = true) {
  TbExprParser parser(begin, end, evaluate);
  if(!parser.eval(value)) return false;
  const char* pos = parser.position();
  if(out_pos != NULL) *out_pos = pos;
  else if(tb_skip_spaces(pos) < end) return false;
  return true;
}

static bool tb_validate_expr_range(const char* begin, const char* end, const char** out_pos = NULL) {
  double ignored = 0.0;
  return tb_eval_expr_range(begin, end, ignored, out_pos, false);
}

static bool tb_validate_command_list(const char* begin, const char* end,
                                     u8 depth = 0);

static bool tb_parse_line_number(const char*& p, i16& number) {
  p = tb_skip_spaces(p);
  if(!tb_is_digit(*p)) return false;
  int value = 0;
  while(tb_is_digit(*p)) {
    value = value * 10 + (*p++ - '0');
    if(value > 32767) return false;
  }
  if(value < 1) return false;
  number = (i16) value;
  return true;
}

static bool tb_compile_source(const char* source, TbAst& ast) {
  tb_ast_reset(ast);
  if(source == NULL) return tb_error("WHAT?");
  usize source_len = 0;
  while(source_len < TB_SOURCE_SIZE && source[source_len] != 0) source_len++;
  if(source_len >= TB_SOURCE_SIZE) return tb_error("SORRY");
  ast.source_len = (u16) source_len;

  const char* cursor = source;
  while(*cursor != 0) {
    while(*cursor == '\n' || *cursor == '\r') cursor++;
    if(*cursor == 0) break;

    const char* line_begin = cursor;
    while(*cursor != 0 && *cursor != '\n' && *cursor != '\r') cursor++;
    const char* line_end = cursor;

    while(line_begin < line_end && tb_is_space(*line_begin)) line_begin++;
    while(line_end > line_begin && tb_is_space(*(line_end - 1))) line_end--;
    if(line_begin >= line_end) continue;
    if(ast.line_count >= TB_MAX_LINES) return tb_error("SORRY");

    const char* p = line_begin;
    i16 number = 0;
    if(!tb_parse_line_number(p, number)) return tb_error("WHAT?");
    if(p >= line_end || !tb_is_space(*p)) return tb_error("WHAT?");
    p = tb_skip_spaces(p);
    if(p >= line_end) return tb_error("WHAT?");
    if(!tb_validate_command_list(p, line_end)) return tb_error("WHAT?");

    TbLine line = {
      number, (u16) (p - source), (u16) (line_end - p)
    };
    i16 insert = ast.line_count;
    while(insert > 0 && ast.lines[insert - 1].number > number) {
      ast.lines[insert] = ast.lines[insert - 1];
      insert--;
    }
    if(insert > 0 && ast.lines[insert - 1].number == number) {
      return tb_error("WHAT?");
    }
    ast.lines[insert] = line;
    ast.line_count++;
  }

  if(ast.line_count == 0) return tb_error("WHAT?");
  tb_last_error[0] = 0;
  return true;
}

bool CompileTinyBasic(char* program) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
  return tb_compile_source(program, tb_ast);
}

static int tb_find_line_number(int number) {
  for(i16 i = 0; i < tb_ast.line_count; i++) {
    if(tb_ast.lines[i].number == number) return i;
  }
  return -1;
}

static int tb_line_number_from_value(double value) {
  if(!mk_math::is_finite(value) || value < 1.0 || value > 32767.0) return -1;
  const double rounded = mk_math::floor(value + 0.5);
  if(mk_math::fabs(value - rounded) > 0.0000001) return -1;
  return (int) rounded;
}

static void tb_flush_print(void) {
  tb_display_line(tb_print_row, tb_pending_print);
  tb_pending_print[0] = 0;
  if(tb_print_row + 1 < main_lcd().rows()) tb_print_row++;
}

static bool tb_append_print_range(const char* begin, const char* end) {
  const usize used = strlen(tb_pending_print);
  const usize added = (usize) (end - begin);
  if(used + added >= sizeof(tb_pending_print)) return false;
  memcpy(tb_pending_print + used, begin, added);
  tb_pending_print[used + added] = 0;
  return true;
}

static bool tb_append_print(const char* text) {
  return tb_append_print_range(text, text + strlen(text));
}

static bool tb_append_print_separator(char sep) {
  if(sep != ',') return true;
  static constexpr usize TAB_WIDTH = 8;
  const usize used = strlen(tb_pending_print);
  usize spaces = TAB_WIDTH - (used % TAB_WIDTH);
  if(spaces == 0) spaces = TAB_WIDTH;
  while(spaces-- > 0) {
    if(!tb_append_print(" ")) return false;
  }
  return true;
}

#ifndef TINYBASIC_HOST_TEST
static usize tb_utf8_length(const char* begin, const char* end) {
  usize length = 0;
  while(begin != NULL && begin < end) {
    const utf8_codec::Decoded decoded = utf8_codec::decode(
        (const u8*) begin, (usize) (end - begin));
    if(decoded.size == 0) break;
    begin += decoded.size;
    length++;
  }
  return length;
}

static const char* tb_utf8_advance(const char* begin, const char* end,
                                   usize count) {
  while(begin != NULL && begin < end && count-- != 0) {
    const utf8_codec::Decoded decoded = utf8_codec::decode(
        (const u8*) begin, (usize) (end - begin));
    if(decoded.size == 0) break;
    begin += decoded.size;
  }
  return begin;
}

static void tb_input_message(const char* prompt, const char* value) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();

  const u8 cols = main_lcd().cols();
  const u8 rows = main_lcd().rows();
  if(cols == 0 || rows == 0) return;

  // Keep one row for the editable value.  A long question is split over the
  // remaining rows instead of being destroyed at the old 16-character LCD
  // boundary.  If a two-line character display cannot hold the whole prompt,
  // its actionable tail (normally the choices) is more useful than its start.
  const u8 prompt_rows = rows > 1 ? (u8) (rows - 1U) : 0U;
  const usize prompt_capacity = (usize) prompt_rows * cols;
  const char* visible = prompt != NULL ? prompt : "";
  const char* const visible_end = visible + strlen(visible);
  const usize prompt_length = tb_utf8_length(visible, visible_end);
  if(prompt_length > prompt_capacity) {
    visible = tb_utf8_advance(
        visible, visible_end, prompt_length - prompt_capacity);
    const char* partial = visible;
    while(partial < visible_end && *partial != ' ') {
      partial = tb_utf8_advance(partial, visible_end, 1);
    }
    if(partial < visible_end) {
      while(partial < visible_end && *partial == ' ') partial++;
      visible = partial;
    }
  }

  u8 row = 0;
  const char* offset = visible;
  while(row < prompt_rows && offset < visible_end) {
    const usize remaining = tb_utf8_length(offset, visible_end);
    const char* line_end = tb_utf8_advance(
        offset, visible_end, remaining < cols ? remaining : cols);
    if(remaining > cols) {
      const char* break_at = line_end;
      while(break_at > offset && break_at[-1] != ' ') {
        break_at--;
      }
      if(break_at > offset) line_end = break_at - 1;
    }
    char line[TB_PRINT_BUFFER_SIZE];
    tb_copy_range(line, sizeof(line), offset, line_end);
    main_lcd().setCursor(0, row++);
    tb_print_display_text(line);
    offset = line_end;
    while(offset < visible_end && *offset == ' ') offset++;
  }

  const u8 input_row = rows > 1 ? row : 0U;
  main_lcd().setCursor(0, input_row);
  main_lcd().print("> ");
  tb_print_display_text(value);
}
#endif

static bool tb_read_number_from_keyboard(const char* prompt, double& value) {
  tb_pause_is_final = false;
#ifdef TINYBASIC_HOST_TEST
  tb_copy_text(tb_host_last_prompt, sizeof(tb_host_last_prompt), prompt);
  if(tb_host_input_expression[0] != 0) {
    const char* const end = tb_host_input_expression +
                            strlen(tb_host_input_expression);
    return tb_eval_expr_range(tb_host_input_expression, end, value);
  }
  if(tb_host_input_index < tb_host_input_count) {
    value = tb_host_input_values[tb_host_input_index++];
    return true;
  }
  value = tb_host_input_value;
  return true;
#else
  char buffer[65];
  memset(buffer, 0, sizeof(buffer));
  text_editor::Buffer editor = {
    buffer, sizeof(buffer), 0, 0, 0, text_editor::Shift::NONE,
    {false, -1, 0, 0}
  };
  while(true) {
    const u32 now = millis();
    if(text_editor::sms_expired(editor.sms, now)) {
      text_editor::sms_reset(editor.sms);
    }
    tb_input_message(prompt, buffer);
    const i32 key = kbd::get_key_wait();
    if(editor.shift == text_editor::Shift::NONE &&
       (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if(editor.shift == text_editor::Shift::NONE &&
       (key == KEY_OK || key == KEY_OK_PRESS)) {
      if(editor.len != 0 &&
         tb_eval_expr_range(buffer, buffer + editor.len, value)) {
        return true;
      }
      tb_message_i18n("WHAT?", "ЧТО?", "number", "число");
      delay(500);
      buffer[0] = 0;
      editor.len = editor.cursor = editor.view_top = 0;
      editor.shift = text_editor::Shift::NONE;
      text_editor::sms_reset(editor.sms);
      continue;
    }
    (void) tinybasic_handle_editor_key(editor, "", key, now);
  }
#endif
}

static bool tb_process_command_list(TbCommandContext& context);

static bool tb_process_assignment(const char* begin, const char* end,
                                  bool execute) {
  const char* p = tb_skip_spaces(begin);
  TbTarget target;
  if(!tb_parse_target_token(p, end, target, execute)) {
    return tb_error("WHAT?");
  }
  p = tb_skip_spaces(p);
  if(p >= end || *p != '=') return tb_error("WHAT?");
  p++;
  while(true) {
    double value = 0.0;
    const char* after_value = NULL;
    if(!tb_eval_expr_range(p, end, value, &after_value, execute)) {
      return tb_error("HOW?");
    }
    if(execute && !tb_write_target(target, value)) return tb_error("HOW?");
    p = tb_skip_spaces(after_value);
    if(p >= end) break;
    if(*p != ',') return tb_error("WHAT?");
    p++;

    const char* explicit_cursor = p;
    TbTarget explicit_target;
    if(tb_parse_target_token(explicit_cursor, end, explicit_target, execute)) {
      explicit_cursor = tb_skip_spaces(explicit_cursor);
      if(explicit_cursor < end && *explicit_cursor == '=') {
        target = explicit_target;
        p = explicit_cursor + 1;
        continue;
      }
    }

    if(target.kind != TbTargetKind::VAR || target.index + 1 >= 26) {
      return tb_error("HOW?");
    }
    target.index++;
  }
  return true;
}

static bool tb_process_print(const char* begin, const char* end,
                             bool execute) {
  if(execute) tb_pause_is_final = false;
  const char* p = begin;
  char trailing_sep = 0;
  // MK-61 keeps its compact display-friendly default.  PATB's historical
  // eight-column layout is available explicitly with PRINT #8,... .
  int field_width = 0;
  if(tb_skip_spaces(p) >= end) {
    if(execute) tb_flush_print();
    return true;
  }

  while(p < end) {
    p = tb_skip_spaces(p);
    if(p >= end) break;
    if(*p == ',' || *p == ';') {
      trailing_sep = *p++;
      if(execute && trailing_sep == ',' && !tb_append_print(" ")) {
        return tb_error("SORRY");
      }
      continue;
    }
    bool item_was_format = false;
    TbTextItem text_item;
    const TbTextItemKind text_kind =
        tb_parse_text_item(p, end, text_item);
    if(text_kind == TbTextItemKind::ERROR) return tb_error("WHAT?");
    if(text_kind == TbTextItemKind::RANGE) {
      if(execute && !tb_append_print_range(text_item.begin, text_item.end)) {
        return tb_error("SORRY");
      }
    } else if(text_kind == TbTextItemKind::CONTROL) {
      if(execute && !tb_append_print_range(
          &text_item.control, &text_item.control + 1)) {
        return tb_error("SORRY");
      }
    } else {
      const bool format = *p == '#';
      item_was_format = format;
      if(format) p++;
      double value = 0.0;
      const char* after_value = NULL;
      if(!tb_eval_expr_range(p, end, value, &after_value, execute)) {
        return tb_error("HOW?");
      }
      if(execute && format) {
        const double rounded = mk_math::floor(value + 0.5);
        if(value < 0.0 || value > 63.0 ||
           mk_math::fabs(value - rounded) > 0.0000001) {
          return tb_error("HOW?");
        }
        field_width = (int) rounded;
      } else if(execute) {
        char number[24];
        tb_format_number(value, number, sizeof(number));
        const int number_len = (int) strlen(number);
        for(int spaces = field_width - number_len; spaces > 0; spaces--) {
          if(!tb_append_print(" ")) return tb_error("SORRY");
        }
        if(!tb_append_print(number)) return tb_error("SORRY");
      }
      p = after_value;
    }

    p = tb_skip_spaces(p);
    if(p < end && (*p == ',' || *p == ';')) {
      trailing_sep = *p++;
      if(execute && !item_was_format &&
         !tb_append_print_separator(trailing_sep)) return tb_error("SORRY");
      continue;
    }
    if(p < end) return tb_error("WHAT?");
    trailing_sep = 0;
    break;
  }

  if(execute && trailing_sep == 0) tb_flush_print();
  return true;
}

static bool tb_process_input(const char* begin, const char* end,
                             i16 current_pc, TbFlow* flow,
                             bool execute) {
  const char* p = begin;
  char prompt[TB_PRINT_BUFFER_SIZE] = ":";
  const usize prompt_size = sizeof(prompt);
  bool custom_prompt = false;
  bool has_target = false;
  while(p < end) {
    p = tb_skip_spaces(p);
    if(p >= end) break;
    TbTextItem text_item;
    const TbTextItemKind text_kind =
        tb_parse_text_item(p, end, text_item);
    if(text_kind == TbTextItemKind::ERROR) return tb_error("WHAT?");
    const bool prompt_item = text_kind != TbTextItemKind::NONE;
    if(text_kind == TbTextItemKind::RANGE) {
      if(execute) {
        const usize used = custom_prompt ? strlen(prompt) : 0;
        if(!custom_prompt) prompt[0] = 0;
        tb_copy_range(prompt + used, prompt_size - used,
                      text_item.begin, text_item.end);
        custom_prompt = true;
      }
    } else if(text_kind == TbTextItemKind::CONTROL) {
      if(execute) {
        const usize used = custom_prompt ? strlen(prompt) : 0;
        if(!custom_prompt) prompt[0] = 0;
        if(used + 1 < prompt_size) {
          prompt[used] = text_item.control;
          prompt[used + 1] = 0;
        }
        custom_prompt = true;
      }
    } else {
      const char* const target_begin = p;
      TbTarget target;
      if(!tb_parse_target_token(p, end, target, execute)) {
        return tb_error("WHAT?");
      }
      has_target = true;
      if(execute && !custom_prompt) {
        const usize target_len = (usize) (p - target_begin);
        const usize copy_len = target_len < prompt_size - 2
            ? target_len : prompt_size - 2;
        memcpy(prompt, target_begin, copy_len);
        prompt[copy_len] = ':';
        prompt[copy_len + 1] = 0;
      }
      if(execute) {
        double value = 0.0;
        if(!tb_read_number_from_keyboard(prompt, value)) {
          tb_pending_print[0] = 0;
          tb_report_interrupted();
          *flow = tb_flow(tb_runs_inside_m61()
              ? TbFlowKind::INTERRUPTED : TbFlowKind::STOP, current_pc);
          return true;
        }
        if(!tb_write_target(target, value)) return tb_error("HOW?");
        prompt[0] = ':';
        prompt[1] = 0;
        custom_prompt = false;
      }
    }

    p = tb_skip_spaces(p);
    if(p < end) {
      if(*p == ',' || *p == ';') p++;
      else if(!prompt_item ||
              (*p != '@' && *p != '.' && !tb_is_alpha(*p))) {
        return tb_error("WHAT?");
      }
    }
  }
  return has_target;
}

static bool tb_execute_goto_like(const char* begin, const char* end,
                                 TbFlow& flow) {
  double value = 0.0;
  if(!tb_eval_expr_range(begin, end, value)) return tb_error("HOW?");
  const int number = tb_line_number_from_value(value);
  const int pc = (number < 0) ? -1 : tb_find_line_number(number);
  if(pc < 0) return tb_error("HOW?");
  flow = tb_flow(TbFlowKind::JUMP, (i16) pc);
  return true;
}

struct TbLoopSearch {
  i8 target_var;
  i8 nested_vars[TB_FOR_DEPTH];
  u8 depth;
  bool found;
  const char* after;
};

__attribute__((noinline)) static bool tb_scan_loop_events(
    const char* begin, const char* end, TbLoopSearch& search,
    u8 command_depth = 0) {
  const char* cursor = begin;
  while(cursor < end && !search.found) {
    cursor = tb_skip_spaces(cursor);
    if(cursor >= end) return true;
    const char* command_start = cursor;
    u8 command_token = 0;
    if(!tb_parse_command_word(cursor, command_token)) {
      cursor = command_start;
      const char* segment_end = tb_find_command_end(cursor, end, false);
      cursor = (segment_end < end) ? segment_end + 1 : segment_end;
      continue;
    }
    const TbCommand command =
        (TbCommand) (command_token & TB_COMMAND_ID_MASK);
    if(command == TbCommand::CMD_REM) return true;
    if(command == TbCommand::CMD_IF) {
      if(command_depth >= TB_COMMAND_DEPTH) return false;
      const char* after_expr = NULL;
      if(!tb_validate_expr_range(cursor, end, &after_expr)) return false;
      cursor = after_expr;
      (void) tb_consume_word(cursor, "THEN", 1);
      return tb_scan_loop_events(cursor, end, search, (u8) (command_depth + 1));
    }

    const char* segment_end = tb_find_command_end(
        cursor, end, command_token & TB_COMMAND_SEMICOLON_ITEMS);
    if(command == TbCommand::CMD_FOR || command == TbCommand::CMD_NEXT) {
      const char* var = tb_skip_spaces(cursor);
      if(var >= segment_end || !tb_is_alpha(*var)) return false;
      const int var_index = tb_upper(*var) - 'A';
      if(command == TbCommand::CMD_FOR) {
        if(search.depth >= TB_FOR_DEPTH) return false;
        search.nested_vars[search.depth++] = var_index;
      } else if(search.depth > 0) {
        if(search.nested_vars[search.depth - 1] != var_index) return false;
        search.depth--;
      } else {
        if(search.target_var != var_index) return false;
        search.found = true;
        search.after = (segment_end < end) ? segment_end + 1 : segment_end;
      }
    }
    cursor = (segment_end < end) ? segment_end + 1 : segment_end;
  }
  return true;
}

__attribute__((noinline)) static bool tb_find_after_matching_next(
    const char* source, i16 start_pc, u16 start_offset, int var_index,
    i16& target_pc, u16& target_offset) {
  TbLoopSearch search;
  memset(&search, 0, sizeof(search));
  search.target_var = var_index;
  if(source == NULL) return tb_error("HOW?");
  for(i16 pc = start_pc; pc < tb_ast.line_count; pc++) {
    const TbLine& line = tb_ast.lines[pc];
    const char* line_begin = source + line.offset;
    const char* line_end = line_begin + line.len;
    const char* scan_begin = line_begin;
    if(pc == start_pc) {
      if(start_offset > line.len) return false;
      scan_begin += start_offset;
    }
    if(!tb_scan_loop_events(scan_begin, line_end, search)) return false;
    if(search.found) {
      if(search.after < line_end) {
        target_pc = pc;
        target_offset = (u16) (search.after - line_begin);
      } else {
        target_pc = (i16) (pc + 1);
        target_offset = 0;
      }
      return true;
    }
  }
  return false;
}

static bool tb_process_for(const char* begin, const char* end,
                           const TbReturnFrame& continuation,
                           const char* source,
                           TbRunState* state, TbFlow* flow,
                           bool execute) {
  const char* p = tb_skip_spaces(begin);
  if(p >= end || !tb_is_alpha(*p)) return tb_error("WHAT?");
  const int var = tb_upper(*p++) - 'A';
  p = tb_skip_spaces(p);
  if(p >= end || *p != '=') return tb_error("WHAT?");
  p++;
  const char* after_start = NULL;
  double start_value = 0.0;
  if(!tb_eval_expr_range(p, end, start_value, &after_start, execute)) {
    return tb_error("HOW?");
  }
  p = after_start;
  if(!tb_consume_word(p, "TO", 1)) return tb_error("WHAT?");
  double limit = 0.0;
  const char* after_limit = NULL;
  if(!tb_eval_expr_range(p, end, limit, &after_limit, execute)) {
    return tb_error("HOW?");
  }
  p = tb_skip_spaces(after_limit);
  double step = 1.0;
  if(p < end) {
    if(!tb_consume_word(p, "STEP", 1) ||
       !tb_eval_expr_range(p, end, step, NULL, execute)) {
      return tb_error("HOW?");
    }
  }
  if(!execute) return true;
  tb_vars[var] = start_value;
  const bool outside = step < 0.0 ? start_value < limit : start_value > limit;
  if(outside) {
    i16 target_pc = -1;
    u16 target_offset = 0;
    if(!tb_find_after_matching_next(source, continuation.pc,
                                    continuation.offset, var,
                                    target_pc, target_offset)) {
      return tb_error("HOW?");
    }
    *flow = tb_flow(TbFlowKind::JUMP, target_pc, target_offset);
    return true;
  }

  for(i8 index = state->for_sp; index >= 0; index--) {
    if(state->for_stack[index].var_index == var) {
      state->for_sp = (i8) (index - 1);
      break;
    }
  }
  if(state->for_sp + 1 >= TB_FOR_DEPTH) return tb_error("HOW?");
  TbForFrame& frame = state->for_stack[++state->for_sp];
  frame.var_index = var;
  frame.limit = limit;
  frame.step = step;
  frame.return_pc = continuation.pc;
  frame.return_offset = continuation.offset;
  return true;
}

static bool tb_process_next(const char* begin, const char* end,
                            TbRunState* state, TbFlow* flow,
                            bool execute) {
  const char* p = tb_skip_spaces(begin);
  if(p >= end || !tb_is_alpha(*p)) return tb_error("WHAT?");
  const int var = tb_upper(*p++) - 'A';
  p = tb_skip_spaces(p);
  if(p < end) return tb_error("WHAT?");
  if(!execute) return true;
  while(state->for_sp >= 0 &&
        state->for_stack[state->for_sp].var_index != var) {
    state->for_sp--;
  }
  if(state->for_sp < 0) return tb_error("HOW?");
  TbForFrame& frame = state->for_stack[state->for_sp];
  tb_vars[var] += frame.step;
  const bool inside = frame.step < 0.0
      ? tb_vars[var] >= frame.limit : tb_vars[var] <= frame.limit;
  if(inside) {
    *flow = tb_flow(TbFlowKind::JUMP, frame.return_pc,
                    frame.return_offset);
  } else {
    state->for_sp--;
  }
  return true;
}

static bool tb_process_one(TbCommandContext& context) {
  const char*& cursor = context.cursor;
  const char* const end = context.end;
  TbRunState* const state = context.state;
  TbFlow* const flow = context.flow;
  const i16 current_pc = context.current_pc;
  const bool execute = context.execute;
  cursor = tb_skip_spaces(cursor);
  if(cursor >= end) return false;

  const char* command_start = cursor;
  u8 command_token = 0;
  const bool has_command = tb_parse_command_word(cursor, command_token);

  if(!has_command) {
    cursor = command_start;
    const char* segment_end = tb_find_command_end(cursor, end, false);
    if(!tb_process_assignment(cursor, segment_end, execute)) return false;
    cursor = (segment_end < end) ? segment_end + 1 : segment_end;
    return true;
  }

  const TbCommand command =
      (TbCommand) (command_token & TB_COMMAND_ID_MASK);

  if(command == TbCommand::CMD_REM) {
    cursor = end;
    return true;
  }

  if(command == TbCommand::CMD_IF) {
    if(context.depth >= TB_COMMAND_DEPTH) return tb_error("HOW?");
    double condition = 0.0;
    const char* after_expr = NULL;
    if(!tb_eval_expr_range(cursor, end, condition, &after_expr, execute)) {
      return tb_error("HOW?");
    }
    cursor = after_expr;
    (void) tb_consume_word(cursor, "THEN", 1);
    cursor = tb_skip_spaces(cursor);
    if(cursor >= end) return tb_error("WHAT?");
    if(!execute || condition != 0.0) {
      context.depth++;
      const bool ok = tb_process_command_list(context);
      context.depth--;
      if(!ok) return false;
    }
    cursor = end;
    return true;
  }

  const char* segment_end = tb_find_command_end(
      cursor, end, command_token & TB_COMMAND_SEMICOLON_ITEMS);
  TbReturnFrame continuation = {(i16) (current_pc + 1), 0};
  if(execute && segment_end < end && tb_skip_spaces(segment_end + 1) < end) {
    if(context.source == NULL) return tb_error("HOW?");
    const char* const line_begin =
        context.source + tb_ast.lines[current_pc].offset;
    continuation.pc = current_pc;
    continuation.offset = (u16) (segment_end + 1 - line_begin);
  }

  if((command_token & TB_COMMAND_TERMINAL) && segment_end < end) {
    return tb_error("WHAT?");
  }

  switch(command) {
    case TbCommand::CMD_LET:
      if(!tb_process_assignment(cursor, segment_end, execute)) return false;
      break;
    case TbCommand::CMD_PRINT:
      if(!tb_process_print(cursor, segment_end, execute)) return false;
      break;
    case TbCommand::CMD_INPUT:
      if(!tb_process_input(cursor, segment_end, current_pc, flow, execute)) {
        return false;
      }
      break;
    case TbCommand::CMD_GOTO:
      if(!execute) {
        if(!tb_validate_expr_range(cursor, segment_end)) return false;
        break;
      }
      if(!tb_execute_goto_like(cursor, segment_end, *flow)) return false;
      cursor = end;
      return true;
    case TbCommand::CMD_GOSUB:
      if(!execute) {
        if(!tb_validate_expr_range(cursor, segment_end)) return false;
        break;
      }
      if(!tb_execute_goto_like(cursor, segment_end, *flow)) return false;
      if(state->call_sp + 1 >= TB_CALL_DEPTH) return tb_error("HOW?");
      state->call_stack[++state->call_sp] = continuation;
      cursor = end;
      return true;
    case TbCommand::CMD_RETURN:
      if(tb_skip_spaces(cursor) < segment_end) return tb_error("WHAT?");
      if(!execute) break;
      if(state->call_sp < 0) return tb_error("HOW?");
      *flow = tb_flow(TbFlowKind::JUMP,
                      state->call_stack[state->call_sp].pc,
                      state->call_stack[state->call_sp].offset);
      state->call_sp--;
      cursor = end;
      return true;
    case TbCommand::CMD_FOR:
      if(!tb_process_for(cursor, segment_end, continuation, context.source,
                         state, flow, execute)) return false;
      break;
    case TbCommand::CMD_NEXT:
      if(!tb_process_next(cursor, segment_end, state, flow, execute)) {
        return false;
      }
      break;
    case TbCommand::CMD_CLS:
      if(tb_skip_spaces(cursor) < segment_end) return tb_error("WHAT?");
      if(execute) tb_clear_output();
      break;
    case TbCommand::CMD_PAUSE:
      if(tb_skip_spaces(cursor) < segment_end) return tb_error("WHAT?");
      if(execute && !tb_pause()) {
        if(tb_runs_inside_m61()) {
          tb_report_interrupted();
          *flow = tb_flow(TbFlowKind::INTERRUPTED, current_pc);
        } else {
          // Historical interactive behaviour: ESC dismisses PAUSE and ends
          // this TinyBASIC run without replacing the program's last screen.
          *flow = tb_flow(TbFlowKind::STOP, current_pc);
        }
        cursor = end;
        return true;
      }
      break;
    case TbCommand::CMD_END:
      if(tb_skip_spaces(cursor) < segment_end) return tb_error("WHAT?");
      if(!execute) break;
      *flow = tb_flow(TbFlowKind::STOP, current_pc);
      cursor = end;
      return true;
    case TbCommand::CMD_REM:
    case TbCommand::CMD_IF:
    case TbCommand::CMD_NONE:
      break;
  }

  cursor = (segment_end < end) ? segment_end + 1 : segment_end;
  return true;
}

static bool tb_process_command_list(TbCommandContext& context) {
  while(context.cursor < context.end &&
        (!context.execute || context.flow->kind == TbFlowKind::NEXT)) {
    if(!tb_process_one(context)) {
      if(context.execute) {
        *context.flow = tb_flow(TbFlowKind::ERROR, context.current_pc);
      }
      return false;
    }
  }
  return true;
}

static bool tb_validate_command_list(const char* begin, const char* end,
                                     u8 depth) {
  TbCommandContext context = {
    begin, end, NULL, NULL, NULL, -1, depth, false
  };
  return tb_process_command_list(context);
}

static bool tb_execute_command_list(const char* begin, const char* end,
                                    const char* source, i16 current_pc,
                                    TbRunState& state, TbFlow& flow,
                                    u8 depth = 0) {
  TbCommandContext context = {
    begin, end, source, &state, &flow, current_pc, depth, true
  };
  return tb_process_command_list(context);
}

static bool tb_runtime_interrupted(void) {
#ifndef TINYBASIC_HOST_TEST
  idle_main_process();
  kbd::scan();
  if(kbd::take_immediate_press(KEY_ESC) || kbd::last_key() == KEY_ESC_PRESS) {
    tb_report_interrupted();
    return true;
  }
#endif
  return false;
}

#ifndef TINYBASIC_HOST_TEST

static void tinybasic_wait_after_run(void) {
  while(true) {
    idle_main_process();
    const i32 scan_code = kbd::poll_event().code();

    if(scan_code >= 0 && scan_code < (i32) key_state::RELEASED) {
      kbd::handoff(kbd::Event(scan_code));
      return;
    }
    delay(10);
  }
}
#else
static void tinybasic_wait_after_run(void) { tb_host_wait_count++; }
#endif

static void tinybasic_finish_wait(void) {
  if(!tb_pause_is_final) tinybasic_wait_after_run();
}

static TinyBasicRunStatus tb_run_program(
    int program_index,
    TinyBasicRunMode mode = TinyBasicRunMode::INTERACTIVE) {
  TinyBasicRunModeScope mode_scope(mode);
  tb_pause_is_final = false;
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return TinyBasicRunStatus::UNAVAILABLE;
  main_lcd().endUiText();
  tb_activate_inherited_text_font();
#endif
  if(program_index < 0 || program_index >= TB_PROGRAM_COUNT ||
     !tb_program_used(programs[program_index])) {
    tb_error("HOW?");
    return TinyBasicRunStatus::NOT_FOUND;
  }
  if(!tb_compile_source(programs[program_index].source, tb_ast)) {
    return TinyBasicRunStatus::COMPILE_ERROR;
  }
  const char* const source = programs[program_index].source;

  main_lcd().clear();
  tb_pending_print[0] = 0;
  tb_print_row = 0;

  TbRunState state;
  memset(&state, 0, sizeof(state));
  state.call_sp = -1;
  state.for_sp = -1;

  i16 pc = 0;
  u16 entry_offset = 0;
  bool succeeded = true;
  bool interrupted = false;
  while(pc >= 0 && pc < tb_ast.line_count) {
    if(tb_runtime_interrupted()) {
      interrupted = true;
      break;
    }
    TbFlow flow = tb_flow(TbFlowKind::NEXT, (i16) (pc + 1));
    const TbLine& line = tb_ast.lines[pc];
    if(entry_offset > line.len) {
      succeeded = tb_error("HOW?");
      break;
    }
    const char* line_begin = source + line.offset;
    const char* begin = line_begin + entry_offset;
    const char* end = line_begin + line.len;
    entry_offset = 0;
    if(!tb_execute_command_list(begin, end, source, pc, state, flow)) {
      succeeded = false;
      break;
    }
    if(flow.kind == TbFlowKind::NEXT) pc = (i16) (pc + 1);
    else if(flow.kind == TbFlowKind::JUMP) {
      pc = flow.pc;
      entry_offset = flow.offset;
    }
    else {
      if(flow.kind == TbFlowKind::INTERRUPTED) interrupted = true;
      break;
    }
  }
  if(succeeded && !interrupted && tb_pending_print[0] != 0) tb_flush_print();
  else if(!succeeded || interrupted) tb_pending_print[0] = 0;
  if(interrupted) return TinyBasicRunStatus::STOPPED;
  return succeeded ? TinyBasicRunStatus::COMPLETED
                   : TinyBasicRunStatus::RUNTIME_ERROR;
}

void RunTinyBasic(int program_index) {
  (void) tb_run_program(program_index);
}

static int find_free_program(void) {
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(!tb_program_used(programs[i])) return i;
  }
  return -1;
}

static int find_program_by_name(const char* name) {
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(tb_program_used(programs[i]) && tb_streq(programs[i].name, name)) return i;
  }
  return -1;
}

static void tb_program_default_name(int slot, char* out, usize size) {
  snprintf(out, size, "TINY%d", slot);
}

#ifndef TINYBASIC_HOST_TEST
static int tb_alloc_program_slot(const char* name) {
  const int existing = find_program_by_name(name);
  if(existing >= 0) return existing;
  const int free_slot = find_free_program();
  if(free_slot >= 0) return free_slot;
  const int slot = (NextTinyBasic >= 0 && NextTinyBasic < TB_PROGRAM_COUNT) ? NextTinyBasic : 0;
  return slot;
}

static bool tb_store_name_is_valid(const char* name) {
  return name != NULL && name[0] != 0 && strlen(name) < program_store::NAME_SIZE;
}

static int load_tinybasic_program_from_store(const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::TINYBASIC ||
     !tb_store_name_is_valid(entry.name)) return -1;
  const int slot = tb_alloc_program_slot(entry.name);
  TbProgram& program = programs[slot];
  u16 len = 0;
  if(!program_store::read_id(entry.id, (u8*) program.source,
                             TB_SOURCE_SIZE - 1, &len)) return -1;
  program.source[len] = 0;
  program.source_len = len;
  tb_copy_text(program.name, sizeof(program.name), entry.name);
  program.store_id = entry.id;
  program.parent_id = entry.parent_id;
  NextTinyBasic = (i8) slot;
  return slot;
}

static int load_tinybasic_program_from_store(u16 id) {
  program_store::Entry entry;
  return program_store::entry_by_id(id, entry)
    ? load_tinybasic_program_from_store(entry)
    : -1;
}

static int load_tinybasic_program_from_store(const char* name) {
  if(!tb_store_name_is_valid(name)) return -1;
  const int count = program_store::count(program_store::ProgramType::TINYBASIC);
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(program_store::entry(program_store::ProgramType::TINYBASIC, i, entry) &&
       strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
      return load_tinybasic_program_from_store(entry);
    }
  }
  return -1;
}
#endif

static int tinybasic_program_count(void) {
#ifndef TINYBASIC_HOST_TEST
  return program_store::count(program_store::ProgramType::TINYBASIC);
#else
  int count = 0;
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(tb_program_used(programs[i])) count++;
  }
  return count;
#endif
}

bool TinyBasicIsReady(void) {
  return tinybasic_program_count() > 0;
}

void InitTinyBasic(void) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return;
#endif
  tinybasic_reset_runtime(tinybasic_runtime());
  tinybasic_clear_array();
#ifdef TINYBASIC_HOST_TEST
  tb_random_state = 0x3B6B120EUL;
  tb_host_input_expression[0] = 0;
  tb_host_input_count = 0;
  tb_host_input_index = 0;
  tb_host_last_prompt[0] = 0;
  tinybasic_host_angle_unit = RADIAN;
  tb_host_wait_count = 0;
#endif
}

[[maybe_unused]] static void draw_program_select(int active, bool allow_new) {
#ifndef TINYBASIC_HOST_TEST
  const int stored_count = program_store::count(program_store::ProgramType::TINYBASIC);
  if(allow_new && active == stored_count) {
    tb_message_i18n("TinyBASIC", "TinyBASIC", ">NEW", ">НОВАЯ");
    return;
  }
  program_store::Entry entry;
  if(active >= 0 && program_store::entry(program_store::ProgramType::TINYBASIC, active, entry)) {
    char line1[17];
    snprintf(line1, sizeof(line1), ">%s", entry.name);
    tb_message_i18n("TinyBASIC", "TinyBASIC", line1, line1);
    return;
  }
  tb_message_i18n("TinyBASIC", "TinyBASIC", ">EMPTY", ">ПУСТО");
#else
  char line1[17];
  if(allow_new && active == TB_PROGRAM_COUNT) tb_copy_text(line1, sizeof(line1), ">NEW");
  else if(active >= 0 && active < TB_PROGRAM_COUNT &&
          tb_program_used(programs[active])) {
    snprintf(line1, sizeof(line1), ">%s", programs[active].name);
  } else tb_copy_text(line1, sizeof(line1), ">EMPTY");
  tb_message_i18n("TinyBASIC", "TinyBASIC", line1, line1);
#endif
}

[[maybe_unused]] static int next_used_program(int active, int delta, bool allow_new) {
  const int max_index = allow_new ? TB_PROGRAM_COUNT : TB_PROGRAM_COUNT - 1;
  int current = active;
  for(int i = 0; i <= max_index; i++) {
    current += delta;
    if(current < 0) current = max_index;
    if(current > max_index) current = 0;
    if(current == TB_PROGRAM_COUNT) return current;
    if(tb_program_used(programs[current])) return current;
  }
  return active;
}

static int select_tinybasic_program(bool allow_new,
                                    u16* new_parent = NULL) {
#ifndef TINYBASIC_HOST_TEST
  program_store::Entry entry = {};
  u16 directory = TB_ROOT_STORE_ID;
  const ProgramStoreFileDialogResult result = program_store_choose_file(
      program_store::ProgramType::TINYBASIC, TB_ROOT_STORE_ID, allow_new,
      entry, directory);
  if(result == ProgramStoreFileDialogResult::CANCELLED) return -1;
  if(result == ProgramStoreFileDialogResult::NEW_FILE) {
    if(new_parent != NULL) *new_parent = directory;
    return TB_PROGRAM_COUNT;
  }
  return load_tinybasic_program_from_store(entry);
#else
  if(new_parent != NULL) *new_parent = TB_ROOT_STORE_ID;
  int active = -1;
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(tb_program_used(programs[i])) {
      active = i;
      break;
    }
  }
  if(active < 0) active = allow_new ? TB_PROGRAM_COUNT : -1;
  if(active < 0) return -1;
  while(true) {
    draw_program_select(active, allow_new);
    const i32 key = kbd::get_key_wait();
    switch(key) {
      case KEY_LEFT: active = next_used_program(active, -1, allow_new); break;
      case KEY_RIGHT: active = next_used_program(active, 1, allow_new); break;
      case KEY_OK: return active;
      case KEY_ESC: return -1;
    }
  }
#endif
}

bool TinyBASIC_library_select(void) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
  const int program = select_tinybasic_program(false);
  if(program >= 0) {
    (void) tb_run_program(program);
    tinybasic_finish_wait();
  }
  return true;
}

static void draw_tinybasic_editor(const char* source, u16 len, u16 cursor, u16 view_top, bool sms_cursor = false) {
  text_editor::draw(main_lcd(), source, len, cursor, view_top, sms_cursor);
}

static bool tb_confirm_save(void) {
  tb_message_i18n("Save TinyBASIC?", "Сохранить?", "OK=yes ESC=no", "OK=да ESC=нет");
  while(true) {
    const i32 key = kbd::get_key_wait();
    if(key == KEY_OK || key == KEY_OK_PRESS) return true;
    if(key == KEY_ESC || key == KEY_ESC_PRESS) return false;
  }
}

static bool tb_name_insert_char(char* name, u16& len, u16& cursor, char ch) {
  if(ch == ' ' && len == 0) return false;
  char text[2] = {tb_upper(ch), 0};
  return text_editor::insert_text(name, len, cursor, TB_NAME_SIZE, text);
}

static void tb_draw_name_editor(const char* name, u16 cursor, bool sms_cursor) {
  const u16 len = (u16) strlen(name);
  if(cursor > len) cursor = len;
  const u16 window = (cursor > lcd_display::COLS - 2) ? (u16) (cursor - (lcd_display::COLS - 2)) : 0;
  char line[17];
  line[0] = '>';
  u8 pos = 1;
  while(pos < lcd_display::COLS && name[window + pos - 1] != 0) {
    line[pos] = name[window + pos - 1];
    pos++;
  }
  while(pos < lcd_display::COLS) line[pos++] = ' ';
  line[lcd_display::COLS] = 0;
  tb_message_i18n("TinyBASIC name", "Имя", line, line);

  MK61DisplayUpdate update(main_lcd());
  const u8 cursor_col = (u8) (1 + cursor - window);
  main_lcd().setCursor(cursor_col, 1);
  if(main_lcd().supportsCursor()) main_lcd().cursorOn();
  else main_lcd().write(sms_cursor ? text_editor::SMS_CURSOR_ASCII : text_editor::CURSOR_ASCII);
}

[[maybe_unused]] static bool tb_input_program_name(char* name, usize size) {
  if(size == 0) return false;
  name[size - 1] = 0;
  u16 len = (u16) strlen(name);
  if(len >= size) len = (u16) size - 1;
  u16 cursor = len;
  text_editor::SmsState sms = {};
  text_editor::Shift shift = text_editor::Shift::NONE;
  while(true) {
    const u32 now = millis();
    if(sms.active && now >= sms.deadline_ms) text_editor::sms_reset(sms);
    tb_draw_name_editor(name, cursor, sms.active);
    const i32 key = kbd::get_key_wait();
    const bool shifted = shift != text_editor::Shift::NONE;
    const int digit = text_editor::digit_from_key(key);

    if(!shifted && sms.active) {
      if(text_editor::sms_key_is_letters(key)) {
        text_editor::sms_tap(name, len, cursor, TB_NAME_SIZE, sms, key, now);
        continue;
      }
      if(text_editor::sms_key_is_space(key)) {
        text_editor::sms_reset(sms);
        tb_name_insert_char(name, len, cursor, ' ');
        continue;
      }
      if(digit == 0) {
        text_editor::sms_reset(sms);
        continue;
      }
      if(key == KEY_PP) {
        text_editor::sms_reset(sms);
        tb_name_insert_char(name, len, cursor, ' ');
        continue;
      }
      text_editor::sms_reset(sms);
    }

    if(!shifted && (key == KEY_K || key == KEY_ALPHA)) {
      shift = (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
      text_editor::sms_reset(sms);
      continue;
    }
    if(!shifted && (key == KEY_OK || key == KEY_OK_PRESS)) return len > 0;
    if(!shifted && (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if(key == KEY_CX &&
        (shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      len = 0;
      cursor = 0;
      name[0] = 0;
      shift = text_editor::Shift::NONE;
      continue;
    }
    if((key == KEY_LEFT || key == KEY_LEFT_PRESS) &&
        (shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(!shifted && (key == KEY_LEFT || key == KEY_LEFT_PRESS)) {
      text_editor::sms_reset(sms);
      text_editor::move_cursor_left(name, cursor);
      continue;
    }
    if(!shifted && (key == KEY_RIGHT || key == KEY_RIGHT_PRESS)) {
      text_editor::sms_reset(sms);
      text_editor::move_cursor_right(name, len, cursor);
      continue;
    }
    if(!shifted && key == KEY_CX) {
      text_editor::sms_reset(sms);
      text_editor::backspace(name, len, cursor);
      continue;
    }

    if(shift == text_editor::Shift::ALPHA && digit >= 0) {
      const char* symbol = text_editor::symbol_for_digit_key(key);
      if(symbol != NULL && symbol[0] != 0) tb_name_insert_char(name, len, cursor, symbol[0]);
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    if(shift == text_editor::Shift::ALPHA) {
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    if(shift == text_editor::Shift::K && text_editor::sms_key_is_letters(key)) {
      text_editor::sms_tap(name, len, cursor, TB_NAME_SIZE, sms, key, now);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(shift == text_editor::Shift::K && text_editor::sms_key_is_space(key)) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, ' ');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(shift == text_editor::Shift::K) {
      const char* punctuation = text_editor::kshift_text_for_key(key);
      text_editor::sms_reset(sms);
      if(punctuation != NULL && punctuation[0] != 0 && punctuation[1] == 0) {
        tb_name_insert_char(name, len, cursor, punctuation[0]);
      }
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(key == KEY_PP) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, ' ');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(digit >= 0) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, (char) ('0' + digit));
      shift = text_editor::Shift::NONE;
      continue;
    }
    shift = text_editor::Shift::NONE;
  }
}

static bool store_edited_program(int slot, char* source, const char* store_name,
                                 u16 target_parent = TB_ROOT_STORE_ID) {
  if(slot < 0 || slot > TB_PROGRAM_COUNT) return tb_error("SORRY");
  if(!tb_compile_source(source, tb_ast)) return false;

  char old_name[TB_NAME_SIZE] = "";
  u16 store_id = TB_INVALID_STORE_ID;
  u16 parent_id = target_parent;
  if(slot >= 0 && slot < TB_PROGRAM_COUNT && tb_program_used(programs[slot])) {
    tb_copy_text(old_name, sizeof(old_name), programs[slot].name);
    store_id = programs[slot].store_id;
    parent_id = target_parent;
  }

  if(slot == TB_PROGRAM_COUNT) {
#ifdef TINYBASIC_HOST_TEST
    slot = find_free_program();
    if(slot < 0) return tb_error("SORRY");
#else
    slot = tb_alloc_program_slot(store_name);
#endif
  }
  if(slot < 0 || slot >= TB_PROGRAM_COUNT) return tb_error("SORRY");
  char final_name[TB_NAME_SIZE];
  if(store_name != NULL && store_name[0] != 0) tb_copy_text(final_name, sizeof(final_name), store_name);
  else tb_program_default_name(slot, final_name, sizeof(final_name));
  const u16 source_len = (u16) strlen(source);
#ifndef TINYBASIC_HOST_TEST
  // Сначала сохраняем во флеш-память. Состояние редактора в ОЗУ фиксируется
  // только после успешной записи всего исходного текста, поэтому при ошибке
  // предыдущая программа остаётся целой.
  u16 saved_id = store_id;
  if(!program_store::write_file(parent_id, store_id,
                                program_store::ProgramType::TINYBASIC,
                                final_name, (const u8*) source, source_len,
                                &saved_id)) {
    return tb_error("SORRY");
  }
  if(store_id == TB_INVALID_STORE_ID && old_name[0] != 0 &&
     !tb_streq(old_name, final_name)) {
    program_store::remove(program_store::ProgramType::TINYBASIC, old_name);
  }
  store_id = saved_id;
#endif
  tb_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = source_len;
  tb_copy_text(programs[slot].name, sizeof(programs[slot].name), final_name);
  programs[slot].store_id = store_id;
  programs[slot].parent_id = parent_id;
  NextTinyBasic = (i8) slot;
  if(!tb_compile_source(programs[slot].source, tb_ast)) return false;
  tb_message_i18n("TinyBASIC ready", "TinyBASIC готов", programs[slot].name, programs[slot].name);
  delay(700);
  return true;
}

static void EditTinyBasicSlot(int slot,
                              u16 new_parent = TB_ROOT_STORE_ID) {
  if(slot < 0 || slot > TB_PROGRAM_COUNT) return;
  const bool new_program = slot == TB_PROGRAM_COUNT;
  if(new_program) {
    const int free_slot = find_free_program();
    slot = free_slot >= 0 ? free_slot
        : ((NextTinyBasic >= 0 && NextTinyBasic < TB_PROGRAM_COUNT)
            ? NextTinyBasic : 0);
  }
  if(slot < 0 || slot >= TB_PROGRAM_COUNT) return;

  const bool original_used = tb_program_used(programs[slot]);
  const u16 original_id = programs[slot].store_id;
#ifdef TINYBASIC_HOST_TEST
  (void) original_id;
#endif
  if(new_program) {
    programs[slot].source[0] = 0;
    programs[slot].source_len = 0;
    programs[slot].name[0] = 0;
    programs[slot].store_id = TB_INVALID_STORE_ID;
    programs[slot].parent_id = new_parent;
  }
  char* const source = programs[slot].source;

  const auto restore_original = [&]() {
#ifndef TINYBASIC_HOST_TEST
    if(original_used && original_id != TB_INVALID_STORE_ID) {
      (void) load_tinybasic_program_from_store(original_id);
      return;
    }
#endif
    if(!original_used) {
      memset(&programs[slot], 0, sizeof(programs[slot]));
      programs[slot].store_id = TB_INVALID_STORE_ID;
      programs[slot].parent_id = TB_ROOT_STORE_ID;
    }
  };

  text_editor::Buffer editor = {
    source, TB_SOURCE_SIZE, programs[slot].source_len, 0, 0,
    text_editor::Shift::NONE, {false, -1, 0, 0}
  };
#if (defined(MK61_DISPLAY_LCD1602) && !defined(TINYBASIC_HOST_TEST)) || defined(MK61_BUILD_PORTABLE_SYSTEM)
  text_editor::DisplaySession display_session(main_lcd());
#endif
  bool dirty = true;
#ifndef TINYBASIC_HOST_TEST
  u32 display_mode_revision = main_lcd().displayModeRevision();
#endif

  while(true) {
#ifndef TINYBASIC_HOST_TEST
    // Редактор владеет циклом переднего плана, поэтому сам должен поддерживать
    // пульс USB-экрана, виртуальные клавиши и передачу кадров.
    idle_main_process();
    const u32 next_display_mode_revision =
      main_lcd().displayModeRevision();
    if(next_display_mode_revision != display_mode_revision) {
      display_mode_revision = next_display_mode_revision;
      dirty = true;
    }
#endif
    const u32 now = millis();
    if(editor.sms.active && now >= editor.sms.deadline_ms) {
      text_editor::sms_reset(editor.sms);
      dirty = true;
    }
    if(dirty) {
      text_editor::ensure_cursor_visible(main_lcd(), source, editor.len, editor.cursor, editor.view_top);
      draw_tinybasic_editor(source, editor.len, editor.cursor, editor.view_top, editor.sms.active);
      dirty = false;
    }
    kbd::scan();
    i32 key_code = kbd::get_key(key_state::PRESSED);
    if(key_code < 0) {
      main_lcd().flush();
      delay(1);
      continue;
    }
    if(key_code == KEY_CX && editor.shift != text_editor::Shift::ALPHA &&
       kbd::is_key_pressed(KEY_ALPHA)) {
      editor.shift = text_editor::Shift::ALPHA;
    }
    if((key_code == KEY_LEFT || key_code == KEY_LEFT_PRESS) &&
        (editor.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      editor.shift = text_editor::Shift::NONE;
      dirty = true;
      continue;
    }
    const text_editor::KeyResult result =
        tinybasic_handle_editor_key(editor, "\n", key_code, now);
    dirty = result != text_editor::KeyResult::NONE;
    if(result == text_editor::KeyResult::SAVE) {
#ifndef TINYBASIC_HOST_TEST
      kbd::handoff(kbd::Event(key_code));
#endif
      main_lcd().cursorOff();
      if(!tb_confirm_save()) {
        restore_original();
        return;
      }
      char name[TB_NAME_SIZE];
      memset(name, 0, sizeof(name));
      if(slot >= 0 && slot < TB_PROGRAM_COUNT &&
         tb_program_used(programs[slot])) {
        tb_copy_text(name, sizeof(name), programs[slot].name);
      }
      else tb_program_default_name(find_free_program() < 0 ? 0 : find_free_program(), name, sizeof(name));
      u16 parent = (slot >= 0 && slot < TB_PROGRAM_COUNT &&
                    tb_program_used(programs[slot]))
          ? programs[slot].parent_id : new_parent;
#ifndef TINYBASIC_HOST_TEST
      if(!program_store_choose_save_target(
          program_store::ProgramType::TINYBASIC, parent, name,
          sizeof(name), parent)) {

        dirty = true;
        continue;
      }
#else
      if(!tb_input_program_name(name, sizeof(name))) {

        dirty = true;
        continue;
      }
#endif
      if(store_edited_program(slot, source, name, parent)) return;
      delay(700);

      dirty = true;
    }
  }
}

void EditTinyBasic(void) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return;
#endif
  u16 new_parent = TB_ROOT_STORE_ID;
  const int slot = select_tinybasic_program(true, &new_parent);
  if(slot < 0) return;
  EditTinyBasicSlot(slot, new_parent);
}

bool EditTinyBasicProgram(const char* name) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
#ifndef TINYBASIC_HOST_TEST
  const int slot = load_tinybasic_program_from_store(name);
  if(slot < 0) return false;
  EditTinyBasicSlot(slot);
  return true;
#else
  (void) name;
  return false;
#endif
}

bool EditTinyBasicProgram(u16 id) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
  const int slot = load_tinybasic_program_from_store(id);
  if(slot < 0) return false;
  EditTinyBasicSlot(slot);
  return true;
#else
  (void) id;
  return false;
#endif
}

bool RunTinyBasicProgram(const char* name) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
#ifndef TINYBASIC_HOST_TEST
  const int slot = load_tinybasic_program_from_store(name);
#else
  const int slot = find_program_by_name(name);
#endif
  if(slot < 0) return false;
  const TinyBasicRunStatus status = tb_run_program(slot);
  tinybasic_finish_wait();
  return status == TinyBasicRunStatus::COMPLETED ||
         status == TinyBasicRunStatus::STOPPED;
}

bool RunTinyBasicProgram(u16 id) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
  const int slot = load_tinybasic_program_from_store(id);
#else
  const int slot = id < TB_PROGRAM_COUNT ? (int) id : -1;
#endif
  if(slot < 0) return false;
  const TinyBasicRunStatus status = tb_run_program(slot);
  tinybasic_finish_wait();
  return status == TinyBasicRunStatus::COMPLETED ||
         status == TinyBasicRunStatus::STOPPED;
}

TinyBasicRunStatus RunTinyBasicProgramStatus(u16 id,
                                              TinyBasicRunMode mode) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return TinyBasicRunStatus::UNAVAILABLE;
  const int slot = load_tinybasic_program_from_store(id);
#else
  const int slot = id < TB_PROGRAM_COUNT ? (int) id : -1;
#endif
  if(slot < 0) return TinyBasicRunStatus::NOT_FOUND;
  const TinyBasicRunStatus status = tb_run_program(slot, mode);
  if(mode == TinyBasicRunMode::INTERACTIVE) tinybasic_finish_wait();
  return status;
}

static bool TinyBASIC_run_menu(void) {
  return TinyBASIC_library_select();
}

static bool TinyBASIC_edit_menu(void) {
  EditTinyBasic();
  return true;
}

static bool TinyBASIC_clear_data(void) {
  memset(tb_vars, 0, sizeof(tb_vars));
  tinybasic_clear_array();
  tb_message_i18n("TinyBASIC data", "Данные", "cleared", "очищены");
  delay(700);
  return true;
}

static constexpr t_punct TB_EDIT_PUNCT  = {.size = 10, .action = &TinyBASIC_edit_menu,  .text = "Edit TBasic"};
static constexpr t_punct TB_RUN_PUNCT   = {.size = 10, .action = &TinyBASIC_run_menu,   .text = "Run TBasic"};
static constexpr t_punct TB_CLEAR_PUNCT = {.size = 10, .action = &TinyBASIC_clear_data, .text = "Clear DATA"};

#ifndef TINYBASIC_HOST_TEST
static constexpr t_punct RU_TB_EDIT_PUNCT  = {.size = 15, .action = &TinyBASIC_edit_menu,  .text = "Правка"};
static constexpr t_punct RU_TB_RUN_PUNCT   = {.size = 15, .action = &TinyBASIC_run_menu,   .text = "Запуск"};
static constexpr t_punct RU_TB_CLEAR_PUNCT = {.size = 15, .action = &TinyBASIC_clear_data, .text = "Сброс данных"};
#endif

bool TinyBASIC_menu_select(void) {
#ifndef TINYBASIC_HOST_TEST
  TinyBasicWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
  t_punct* items[] = {
#ifndef TINYBASIC_HOST_TEST
    (t_punct*) (tinybasic_language_is_ru() ? &RU_TB_EDIT_PUNCT : &TB_EDIT_PUNCT),
    (t_punct*) (tinybasic_language_is_ru() ? &RU_TB_RUN_PUNCT : &TB_RUN_PUNCT),
    (t_punct*) (tinybasic_language_is_ru() ? &RU_TB_CLEAR_PUNCT : &TB_CLEAR_PUNCT)
#else
    (t_punct*) &TB_EDIT_PUNCT,
    (t_punct*) &TB_RUN_PUNCT,
    (t_punct*) &TB_CLEAR_PUNCT
#endif
  };
  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  menu.select();
  return true;
}

#ifdef TINYBASIC_SELF_TEST
extern "C" void TinyBasicTestReset(void) {
  InitTinyBasic();
  main_lcd().clear();
#ifdef TINYBASIC_HOST_TEST
  mk61_ref::host_reset();
  kbd::host_alpha_pressed = false;
  kbd::host_wait_esc = false;
  main_lcd().setReportedCols(16);
  main_lcd().setRows(MK61Display::MAX_ROWS);
#endif
}

extern "C" void TinyBasicTestSetAlphaHeld(bool held) {
#ifdef TINYBASIC_HOST_TEST
  kbd::host_alpha_pressed = held;
#else
  (void) held;
#endif
}

extern "C" void TinyBasicTestSetPauseEsc(bool enabled) {
#ifdef TINYBASIC_HOST_TEST
  kbd::host_wait_esc = enabled;
#else
  (void) enabled;
#endif
}

extern "C" bool TinyBasicTestCompile(const char* source) {
  return tb_compile_source(source, tb_ast);
}

extern "C" const char* TinyBasicTestError(void) {
  return tb_last_error;
}

extern "C" int TinyBasicTestAddProgram(const char* source, const char* name) {
  const int slot = find_free_program();
  if(slot < 0) return -1;
  if(!tb_compile_source(source, tb_ast)) return -1;
  tb_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  if(!tb_compile_source(programs[slot].source, tb_ast)) return -1;
  tb_copy_text(programs[slot].name, sizeof(programs[slot].name), name == NULL ? "TEST" : name);
  NextTinyBasic = (i8) slot;
  return slot;
}

extern "C" void TinyBasicTestSetInput(double value) {
  tb_host_input_value = value;
  tb_host_input_expression[0] = 0;
  tb_host_input_count = 0;
  tb_host_input_index = 0;
}

extern "C" void TinyBasicTestSetInputExpression(const char* expression) {
  tb_host_input_count = 0;
  tb_host_input_index = 0;
  tb_copy_text(tb_host_input_expression,
               sizeof(tb_host_input_expression), expression);
}

extern "C" void TinyBasicTestSetInputs(const double* values, int count) {
  tb_host_input_count = 0;
  tb_host_input_index = 0;
  tb_host_input_expression[0] = 0;
  if(values == NULL || count <= 0) return;
  const int capacity = (int) (sizeof(tb_host_input_values) /
                              sizeof(tb_host_input_values[0]));
  if(count > capacity) count = capacity;
  for(int index = 0; index < count; ++index) {
    tb_host_input_values[index] = values[index];
  }
  tb_host_input_count = (u8) count;
}

extern "C" const char* TinyBasicTestLastPrompt(void) {
  return tb_host_last_prompt;
}

extern "C" void TinyBasicTestRun(int slot) {
  main_lcd().clear();
  RunTinyBasic(slot);
}

extern "C" bool TinyBasicTestRunResult(int slot) {
  main_lcd().clear();
  return TinyBasicRunSucceeded(tb_run_program(slot));
}

extern "C" void TinyBasicTestClearData(void) {
  memset(tb_vars, 0, sizeof(tb_vars));
}

extern "C" int TinyBasicTestWaitCount(void) {
#ifdef TINYBASIC_HOST_TEST
  return tb_host_wait_count;
#else
  return 0;
#endif
}

extern "C" bool TinyBasicTestStoreEdited(int slot, char* source, const char* name) {
  return store_edited_program(slot, source, name);
}

extern "C" void TinyBasicTestSetGeometry(int cols, int rows) {
#ifdef TINYBASIC_HOST_TEST
  main_lcd().setReportedCols(
      (u8) (cols < 1 ? 1 : (cols > 255 ? 255 : cols)));
  main_lcd().setRows(
      (u8) (rows < 1 ? 1 : (rows > 255 ? 255 : rows)));
#else
  (void) cols;
  (void) rows;
#endif
}

extern "C" double TinyBasicTestNumber(const char* name) {
  if(name == NULL || name[0] == 0) return 0.0;
  const int idx = tb_upper(name[0]) - 'A';
  return (idx < 0 || idx >= 26) ? 0.0 : tb_vars[idx];
}

extern "C" double TinyBasicTestMkX(void) {
  return mk61_ref::host_get_stack(mk61_ref::Kind::X);
}

extern "C" double TinyBasicTestMkRegister(int reg) {
  return reg >= 0 && reg < 16 ? mk61_ref::host_get_register((u8) reg) : 0.0;
}

extern "C" void TinyBasicTestSetRfEnabled(bool enabled) {
  mk61_ref::host_set_rf_enabled(enabled);
}

extern "C" void TinyBasicTestSetAngleMode(int mode) {
#ifdef TINYBASIC_HOST_TEST
  if(mode == DEGREE || mode == GRADE || mode == RADIAN) tinybasic_host_angle_unit = (AngleUnit) mode;
#else
  (void) mode;
#endif
}

extern "C" const char* TinyBasicTestLcdLine(int row) {
  return main_lcd().line((u8) row);
}

extern "C" void TinyBasicTestFormatNumber(double value, char* out, int size) {
  tb_format_number(value, out, (usize) size);
}

extern "C" void TinyBasicTestEditSequence(const int* keys, int count, char* out, int size) {
  if(out == NULL || size <= 0) return;
  char source[TB_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  text_editor::Buffer editor;
  text_editor::init(editor, source, TB_SOURCE_SIZE);
  for(int i = 0; i < count; i++) {
    const u32 now = millis();
    const i32 key_code = keys[i];
    if(key_code == KEY_CX && editor.shift != text_editor::Shift::ALPHA &&
       kbd::is_key_pressed(KEY_ALPHA)) {
      editor.shift = text_editor::Shift::ALPHA;
    }
    if((key_code == KEY_LEFT || key_code == KEY_LEFT_PRESS) &&
        (editor.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      editor.shift = text_editor::Shift::NONE;
      continue;
    }
    tinybasic_handle_editor_key(editor, "\n", key_code, now);
  }
  bounded_string::copy(out, (usize) size, source);
}
#endif

#endif
