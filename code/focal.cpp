#ifndef FOCAL_HOST_TEST
#include "program_store.hpp"
#endif

#ifdef FOCAL_HOST_TEST
#include "rust_types.h"
#include "focal.hpp"
#include "keyboard_layout.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if MK61_ENABLE_FOCAL
static const int KEY_LEFT = keyboard_layout::ACTIVE.left;
static const int KEY_RIGHT = keyboard_layout::ACTIVE.right;
static const int KEY_OK = keyboard_layout::ACTIVE.ok;
static const int KEY_ESC = keyboard_layout::ACTIVE.esc;
static const int KEY_K = keyboard_layout::ACTIVE.k;
static const int KEY_ALPHA = keyboard_layout::ACTIVE.alpha;
static const int KEY_CX = keyboard_layout::ACTIVE.cx;
static const int KEY_PP = keyboard_layout::ACTIVE.pp;
static const int KEY_SHG_RIGHT_PRESS = keyboard_layout::ACTIVE.shg_right;
static const int KEY_SHG_LEFT_PRESS = keyboard_layout::ACTIVE.shg_left;
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

namespace mk61_ref {
  double host_stack_value[5];
  double host_register_value[16];
  bool host_rf_enabled;
}

class MK61Display {
  public:
    static constexpr u8 MAX_ROWS = 8;
    MK61Display(void) : x(0), y(0), row_count(MAX_ROWS) { clear(); }

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
    void blinkOn(void) {}
    void blinkOff(void) {}
    bool supportsCursor(void) const { return false; }
    bool hasHardwareCursor(void) const { return false; }

    void write(u8 value) {
      if(x < 16 && y < MAX_ROWS) lines[y][x++] = (char) value;
    }

    void print(const char* text) {
      if(text == NULL) return;
      while(*text != 0) write((u8) *text++);
    }

    void print(char value) { write((u8) value); }
    void print(int value) {
      char buffer[16];
      snprintf(buffer, sizeof(buffer), "%d", value);
      print(buffer);
    }

    u8 rows(void) const { return row_count; }
    void setRows(u8 rows) { row_count = (rows < 1) ? 1 : ((rows > MAX_ROWS) ? MAX_ROWS : rows); }
    const char* line(u8 row) const { return lines[(row < MAX_ROWS) ? row : 0]; }

  private:
    u8 x;
    u8 y;
    u8 row_count;
    char lines[MAX_ROWS][17];
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display&) {}
};

MK61Display lcd;

enum class key_state {PRESSED=0, RELEASED=0x40};

namespace kbd {
  static bool host_alpha_pressed;
  void debounce_init(void) {}
  isize scan_and_debounced(void) { return 0; }
  i32 get_key(key_state) { return -1; }
  i32 get_key_wait(void) { return KEY_OK; }
  bool is_key_pressed(i32 key_code) { return key_code == KEY_ALPHA && host_alpha_pressed; }
}

static u32 focal_host_millis;
u32 millis(void) { return focal_host_millis += 17; }
void delay(usize ms) { focal_host_millis += (u32) ms; }

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
#include "focal.hpp"
#include "keyboard.h"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#include "entropy_pool.hpp"
#include "development.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

#include "bounded_string.hpp"
#include "mk_math.hpp"
#ifdef FOCAL_HOST_TEST
#define MK61_REF_HOST_TEST
#endif
#include "mk61_ref.hpp"

#ifdef FOCAL_HOST_TEST
#define TEXT_EDITOR_HOST_TEST
#endif
#include "text_editor.hpp"
#ifndef FOCAL_HOST_TEST
#include "language_workspace.hpp"
#endif

#if MK61_ENABLE_FOCAL

static constexpr u16 FOCAL_INVALID_STORE_ID = 0xFFFF;
static constexpr u16 FOCAL_ROOT_STORE_ID = 0xFFFF;

using namespace kbd;

extern MK61Display lcd;
#ifndef FOCAL_HOST_TEST
extern void idle_main_process(void);
#endif

static constexpr int FOCAL_PROGRAM_COUNT       = 1;
static constexpr int FOCAL_SOURCE_SIZE         = 1537;
static constexpr int FOCAL_NAME_SIZE           = 32;
#ifndef FOCAL_HOST_TEST
static_assert(FOCAL_SOURCE_SIZE == program_store::MAX_MK61_TEXT_SIZE + 1,
              "FOCAL editor quota must match the filesystem quota");
static_assert(FOCAL_NAME_SIZE == program_store::NAME_SIZE,
              "FOCAL names must match the filesystem quota");
#endif
static constexpr int FOCAL_LINE_TEXT_SIZE      = 80;
static constexpr int FOCAL_LINE_BUFFER_SIZE    = 128;
static constexpr int FOCAL_MAX_LINES           = 80;
static constexpr int FOCAL_EXPR_BUFFER_SIZE    = 112;
static constexpr int FOCAL_PRINT_BUFFER_SIZE   = 96;
static constexpr int FOCAL_CALL_DEPTH          = 8;

static constexpr u32 SMS_INPUT_TIMEOUT_MS = text_editor::SMS_INPUT_TIMEOUT_MS;
static constexpr u8  SMS_CURSOR_ASCII    = text_editor::SMS_CURSOR_ASCII;

enum class FocalOp : u8 {
  NOP,
  ASK,
  BRANCH,
  COMMENT,
  DO,
  EXIT,
  FOR,
  GOTO,
  PRINT,
  RETURN,
  SET
};

enum class FocalFlowKind : u8 {
  NEXT,
  JUMP,
  STOP,
  INTERRUPTED,
  RETURNED,
  ERROR
};

enum class FocalParseResult : u8 {
  OK,
  LINE,
  SYNTAX,
  FULL
};

using FocalEditShift = text_editor::Shift;
using FocalSmsState = text_editor::SmsState;

struct FocalAddress {
  i16 major;
  i16 minor;
  bool has_minor;
};

struct FocalLine {
  FocalAddress number;
  FocalOp op;
  u16 operand_offset;
};

struct FocalStatement {
  FocalOp op;
  char operand[FOCAL_LINE_TEXT_SIZE];
};

enum class FocalTargetKind : u8 {
  VAR,
  MK_REF
};

struct FocalTarget {
  FocalTargetKind kind;
  int var_index;
  mk61_ref::Ref mk_ref;
};

struct FocalAst {
  FocalLine lines[FOCAL_MAX_LINES];
  i16 line_count;
  char operand_pool[FOCAL_SOURCE_SIZE];
  u16 operand_used;
};

struct FocalProgram {
  bool used;
  u16 store_id;
  u16 parent_id;
  char name[FOCAL_NAME_SIZE];
  char source[FOCAL_SOURCE_SIZE];
  u16 source_len;
};

struct FocalFlow {
  FocalFlowKind kind;
  i16 pc;
};

struct FocalRuntime {
  FocalProgram programs[FOCAL_PROGRAM_COUNT];
  FocalAst focal_ast;
  double focal_vars[26];
  i8 NextFocal;
  char focal_last_error[17];
};

static_assert(sizeof(FocalAst) < 3072, "FOCAL parsed representation must remain compact");
static_assert(sizeof(FocalRuntime) < 5120, "FOCAL runtime must leave workspace headroom");

#ifdef FOCAL_HOST_TEST
static FocalRuntime focal_runtime_storage;
static FocalRuntime& focal_runtime(void) {
  return focal_runtime_storage;
}
#else
static_assert(sizeof(FocalRuntime) <= language_workspace::SIZE, "FOCAL runtime does not fit language workspace");

class FocalWorkspaceScope {
  public:
    FocalWorkspaceScope(void)
      : lease(language_workspace::Owner::FOCAL, sizeof(FocalRuntime)) {
      if(!lease.ok() || !lease.fresh()) return;
      FocalRuntime* runtime = (FocalRuntime*) lease.data();
      memset(runtime, 0, sizeof(*runtime));
      runtime->NextFocal = -1;
    }

    bool ok(void) const { return lease.ok(); }

  private:
    language_workspace::Lease lease;
};

static FocalRuntime& focal_runtime(void) {
  void* memory = language_workspace::data(language_workspace::Owner::FOCAL);
  if(memory == NULL) __builtin_trap();
  return *((FocalRuntime*) memory);
}
#endif

#define programs         (focal_runtime().programs)
#define focal_ast        (focal_runtime().focal_ast)
#define focal_vars       (focal_runtime().focal_vars)
#define NextFocal        (focal_runtime().NextFocal)
#define focal_last_error (focal_runtime().focal_last_error)
#ifdef FOCAL_HOST_TEST
static u32 focal_random_state = 0x3B6B120EUL;
static double focal_host_ask_value = 0.0;
static bool focal_host_ask_cancelled = false;
static int focal_host_ask_wait_count = 0;
static bool focal_host_store_write_ok = true;
static bool focal_host_store_remove_ok = true;
static char focal_host_stored_source[FOCAL_SOURCE_SIZE];
#endif

static const char* focal_ast_operand(const FocalAst& ast, const FocalLine& line) {
  return line.operand_offset < ast.operand_used ? ast.operand_pool + line.operand_offset : "";
}

#if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
static const char* focal_trace_op_name(FocalOp op) {
  switch(op) {
    case FocalOp::NOP:     return "NOP";
    case FocalOp::ASK:     return "ASK";
    case FocalOp::BRANCH:  return "BRANCH";
    case FocalOp::COMMENT: return "COMMENT";
    case FocalOp::DO:      return "DO";
    case FocalOp::EXIT:    return "EXIT";
    case FocalOp::FOR:     return "FOR";
    case FocalOp::GOTO:    return "GOTO";
    case FocalOp::PRINT:   return "PRINT";
    case FocalOp::RETURN:  return "RETURN";
    case FocalOp::SET:     return "SET";
  }
  return "?";
}

static const char* focal_trace_flow_name(FocalFlowKind kind) {
  switch(kind) {
    case FocalFlowKind::NEXT:     return "NEXT";
    case FocalFlowKind::JUMP:     return "JUMP";
    case FocalFlowKind::STOP:     return "STOP";
    case FocalFlowKind::INTERRUPTED: return "INTERRUPTED";
    case FocalFlowKind::RETURNED: return "RETURNED";
    case FocalFlowKind::ERROR:    return "ERROR";
  }
  return "?";
}

static void focal_trace_header(void) {
  Serial.print("[FOCAL] ");
}

static void focal_trace_text(const char* text) {
  focal_trace_header();
  Serial.println(text);
  Serial.flush();
}

static void focal_trace_int(const char* label, isize value) {
  focal_trace_header();
  Serial.print(label);
  Serial.println(value);
  Serial.flush();
}

static void focal_trace_string(const char* label, const char* value) {
  focal_trace_header();
  Serial.print(label);
  Serial.print("'");
  Serial.print(value == NULL ? "" : value);
  Serial.println("'");
  Serial.flush();
}

static void focal_trace_line(const char* prefix, i16 pc, const FocalLine& line) {
  focal_trace_header();
  Serial.print(prefix);
  Serial.print(" pc=");
  Serial.print(pc);
  Serial.print(" addr=");
  Serial.print(line.number.major);
  if(line.number.has_minor) {
    Serial.print(".");
    if(line.number.minor < 10) Serial.print("0");
    Serial.print(line.number.minor);
  }
  Serial.print(" op=");
  Serial.print(focal_trace_op_name(line.op));
  Serial.print(" operand='");
  Serial.print(focal_ast_operand(focal_ast, line));
  Serial.println("'");
  Serial.flush();
}

static void focal_trace_flow(const FocalFlow& flow) {
  focal_trace_header();
  Serial.print("flow=");
  Serial.print(focal_trace_flow_name(flow.kind));
  Serial.print(" pc=");
  Serial.println(flow.pc);
  Serial.flush();
}
#else
static inline void focal_trace_text(const char*) {}
static inline void focal_trace_int(const char*, isize) {}
static inline void focal_trace_string(const char*, const char*) {}
static inline void focal_trace_line(const char*, i16, const FocalLine&) {}
static inline void focal_trace_flow(const FocalFlow&) {}
#endif

static const char* focal_plain_key_text(i32 key_code) {
  return text_editor::plain_text_for_key(key_code);
}

static const char* focal_kshift_key_text(i32 key_code) {
  return text_editor::kshift_text_for_key(key_code);
}

static int focal_digit_from_key(i32 key_code) {
  return text_editor::digit_from_key(key_code);
}

static const char* focal_sms_letters_for_key(i32 key_code) {
  return text_editor::sms_letters_for_key(key_code);
}

static bool focal_sms_key_is_letters(i32 key_code) {
  return text_editor::sms_key_is_letters(key_code);
}

static bool focal_sms_key_is_space(i32 key_code) {
  return text_editor::sms_key_is_space(key_code);
}

static const char* focal_symbol_for_digit_key(i32 key_code) {
  return text_editor::symbol_for_digit_key(key_code);
}

static void focal_sms_reset(FocalSmsState& sms) {
  text_editor::sms_reset(sms);
}

static char focal_upper(char ch) {
  if(ch >= 'a' && ch <= 'z') return (char) (ch - 'a' + 'A');
  return ch;
}

static bool focal_is_space(char ch) {
  return ch == ' ' || ch == '\t';
}

static bool focal_is_digit(char ch) {
  return ch >= '0' && ch <= '9';
}

static bool focal_is_alpha(char ch) {
  ch = focal_upper(ch);
  return ch >= 'A' && ch <= 'Z';
}

static bool focal_streq(const char* a, const char* b) {
  while(*a != 0 && *b != 0) {
    if(focal_upper(*a++) != focal_upper(*b++)) return false;
  }
  return *a == 0 && *b == 0;
}

static const char* focal_skip_spaces(const char* text) {
  while(focal_is_space(*text)) text++;
  return text;
}

struct FocalOperatorName {
  FocalOp op;
  char short_name;
  const char* full_name;
};

static const FocalOperatorName FOCAL_OPERATOR_NAMES[] = {
  {FocalOp::ASK,     'A', "ASK"},
  {FocalOp::BRANCH,  'B', "BRANCH"},
  {FocalOp::COMMENT, 'C', "COMMENT"},
  {FocalOp::DO,      'D', "DO"},
  {FocalOp::EXIT,    'E', "EXIT"},
  {FocalOp::FOR,     'F', "FOR"},
  {FocalOp::GOTO,    'G', "GOTO"},
  {FocalOp::PRINT,   'P', "PRINT"},
  {FocalOp::RETURN,  'R', "RETURN"},
  {FocalOp::SET,     'S', "SET"}
};

static const FocalOperatorName* focal_operator_name(FocalOp op) {
  for(usize i = 0; i < sizeof(FOCAL_OPERATOR_NAMES) / sizeof(FOCAL_OPERATOR_NAMES[0]); i++) {
    if(FOCAL_OPERATOR_NAMES[i].op == op) return &FOCAL_OPERATOR_NAMES[i];
  }
  return NULL;
}

static bool focal_operator_from_range(const char* begin, const char* end, FocalOp& op) {
  if(begin == NULL || end <= begin) return false;
  const usize length = (usize) (end - begin);
  for(usize i = 0; i < sizeof(FOCAL_OPERATOR_NAMES) / sizeof(FOCAL_OPERATOR_NAMES[0]); i++) {
    const FocalOperatorName& name = FOCAL_OPERATOR_NAMES[i];
    bool matches = length == 1 && focal_upper(*begin) == name.short_name;
    const usize full_length = strlen(name.full_name);
    if(length == full_length) {
      matches = true;
      for(usize j = 0; j < length; j++) {
        if(focal_upper(begin[j]) != name.full_name[j]) {
          matches = false;
          break;
        }
      }
    }
    if(matches) {
      op = name.op;
      return true;
    }
  }
  return false;
}

static void focal_copy_text(char* dst, usize dst_size, const char* src) {
  bounded_string::copy(dst, dst_size, src);
}

static void focal_append_char(char*& out, char* end, char ch) {
  if(out < end) *out++ = ch;
}

static void focal_append_uint(char*& out, char* end, unsigned long long value) {
  char digits[24];
  u8 count = 0;
  do {
    digits[count++] = (char) ('0' + (value % 10ULL));
    value /= 10ULL;
  } while(value > 0 && count < sizeof(digits));
  while(count > 0) focal_append_char(out, end, digits[--count]);
}

static void focal_format_fixed(double value, int decimals, char* out, usize size) {
  if(size == 0) return;
  if(decimals < 0) decimals = 0;
  if(decimals > 12) decimals = 12;

  const bool negative = value < 0.0;
  double abs_value = negative ? -value : value;
  unsigned long long scale = 1ULL;
  for(int i = 0; i < decimals; i++) scale *= 10ULL;

  const unsigned long long scaled = (unsigned long long) (abs_value * (double) scale + 0.5);
  const unsigned long long integer = scaled / scale;
  unsigned long long fraction = (scale == 0ULL) ? 0ULL : (scaled % scale);

  char temp[40];
  char* cursor = temp;
  char* end = temp + sizeof(temp) - 1;
  if(negative && scaled != 0ULL) focal_append_char(cursor, end, '-');
  focal_append_uint(cursor, end, integer);
  if(decimals > 0) {
    focal_append_char(cursor, end, '.');
    char fractional[13];
    for(int i = decimals - 1; i >= 0; i--) {
      fractional[i] = (char) ('0' + (fraction % 10ULL));
      fraction /= 10ULL;
    }
    for(int i = 0; i < decimals; i++) focal_append_char(cursor, end, fractional[i]);
    while(cursor > temp && *(cursor - 1) == '0') cursor--;
    if(cursor > temp && *(cursor - 1) == '.') cursor--;
  }
  *cursor = 0;
  focal_copy_text(out, size, temp);
}

static void focal_format_number(double value, char* out, usize size) {
  if(size == 0) return;
  if(mk_math::is_nan(value)) {
    focal_copy_text(out, size, "NAN");
    return;
  }
  if(mk_math::is_inf(value)) {
    focal_copy_text(out, size, value < 0.0 ? "-INF" : "INF");
    return;
  }
  if(value == 0.0) {
    focal_copy_text(out, size, "0");
    return;
  }

  const double abs_value = mk_math::fabs(value);
  int exp10 = mk_math::log10_floor(abs_value);
  if(exp10 >= 8 || exp10 < -4) {
    char mantissa[24];
    double scaled = value / mk_math::pow10_int(exp10);
    focal_format_fixed(scaled, 7, mantissa, sizeof(mantissa));
    if(mantissa[0] == '1' && mantissa[1] == '0') {
      exp10++;
      focal_format_fixed(value < 0.0 ? -1.0 : 1.0, 7, mantissa, sizeof(mantissa));
    }
    char temp[32];
    focal_copy_text(temp, sizeof(temp), mantissa);
    strncat(temp, "E", sizeof(temp) - strlen(temp) - 1);
    char* cursor = temp + strlen(temp);
    char* end = temp + sizeof(temp) - 1;
    if(exp10 < 0) {
      focal_append_char(cursor, end, '-');
      focal_append_uint(cursor, end, (unsigned long long) -exp10);
    } else {
      focal_append_char(cursor, end, '+');
      focal_append_uint(cursor, end, (unsigned long long) exp10);
    }
    *cursor = 0;
    focal_copy_text(out, size, temp);
    return;
  }

  int decimals = 7 - exp10;
  if(decimals < 0) decimals = 0;
  focal_format_fixed(value, decimals, out, size);
}

static void focal_copy_trim(char* dst, usize dst_size, const char* begin, const char* end) {
  if(dst_size == 0) return;
  while(begin < end && focal_is_space(*begin)) begin++;
  while(end > begin && focal_is_space(*(end - 1))) end--;
  const usize len = (usize) (end - begin);
  const usize copy_len = (len < dst_size - 1) ? len : dst_size - 1;
  memcpy(dst, begin, copy_len);
  dst[copy_len] = 0;
}

#ifndef FOCAL_HOST_TEST
static bool focal_language_is_ru(void) {
  return library_mk61::language_is_ru();
}
#endif

static const char* focal_error_ru_text(const char* error) {
  if(focal_streq(error, "LINE?")) return "СТРОКА?";
  if(focal_streq(error, "SYNTAX?")) return "СИНТАКСИС?";
  if(focal_streq(error, "VAR?")) return "ПЕРЕМ?";
  if(focal_streq(error, "FUNC?")) return "ФУНК?";
  if(focal_streq(error, "FOR?")) return "ЦИКЛ?";
  if(focal_streq(error, "FULL?")) return "НЕТ МЕСТА";
  if(focal_streq(error, "RETURN?")) return "ВОЗВРАТ?";
  if(focal_streq(error, "STACK?")) return "СТЕК?";
  if(focal_streq(error, "MATH?")) return "МАТ?";
  if(focal_streq(error, "MK?")) return "МК?";
  if(focal_streq(error, "NAME?")) return "ИМЯ?";
  if(focal_streq(error, "SLOT?")) return "СЛОТ?";
  return "ОШИБКА?";
}

static void focal_display_line(u8 row, const char* text) {
  MK61DisplayUpdate update(lcd);
  lcd.setCursor(0, row);
  for(u8 i = 0; i < 16; i++) lcd.write((u8) ' ');
  lcd.setCursor(0, row);
  if(text != NULL) lcd.print(text);
}

static void focal_message_i18n(const char* en0, const char* ru0, const char* en1, const char* ru1) {
#ifdef FOCAL_HOST_TEST
  (void) ru0;
  (void) ru1;
#endif
  MK61DisplayUpdate update(lcd);
  lcd.clear();
#ifndef FOCAL_HOST_TEST
  if(focal_language_is_ru()) {
    lcd_ru::print_lines(ru0, ru1);
    return;
  }
#endif
  lcd.setCursor(0, 0);
  lcd.print(en0);
  lcd.setCursor(0, 1);
  lcd.print(en1);
}

static bool focal_error(const char* error) {
  focal_trace_string("ERROR ", error);
  focal_copy_text(focal_last_error, sizeof(focal_last_error), error);
  focal_message_i18n(error, focal_error_ru_text(error), "FOCAL", "ФОКАЛ");
  return false;
}

static void focal_show_stopped(void) {
  focal_message_i18n("FOCAL stopped", "ФОКАЛ стоп", "ESC", "ESC");
}

static bool focal_runtime_interrupted(void) {
#ifndef FOCAL_HOST_TEST
  idle_main_process();
  kbd::scan_and_debounced();
  const i32 key = kbd::last_key();
  if(key == KEY_ESC || key == KEY_ESC_PRESS) {
    (void) kbd::get_key();
    kbd::clear_hold_key();
    focal_show_stopped();
    return true;
  }
#endif
  return false;
}

static void focal_clear_vars(void) {
  memset(focal_vars, 0, sizeof(focal_vars));
}

static void focal_ast_reset(FocalAst& ast) {
  memset(&ast, 0, sizeof(ast));
}

static int focal_address_compare(const FocalAddress& a, const FocalAddress& b) {
  if(a.major != b.major) return (a.major < b.major) ? -1 : 1;
  const i16 aminor = a.has_minor ? a.minor : -1;
  const i16 bminor = b.has_minor ? b.minor : -1;
  if(aminor == bminor) return 0;
  return (aminor < bminor) ? -1 : 1;
}

static bool focal_address_equal(const FocalAddress& a, const FocalAddress& b) {
  return a.major == b.major && a.minor == b.minor && a.has_minor == b.has_minor;
}

static bool focal_parse_address(const char*& p, FocalAddress& out) {
  p = focal_skip_spaces(p);
  if(!focal_is_digit(*p)) return false;

  int major = 0;
  while(focal_is_digit(*p)) {
    major = major * 10 + (*p++ - '0');
    if(major > 999) return false;
  }

  int minor = 0;
  bool has_minor = false;
  if(*p == '.') {
    has_minor = true;
    p++;
    if(!focal_is_digit(*p)) return false;
    while(focal_is_digit(*p)) {
      minor = minor * 10 + (*p++ - '0');
      if(minor > 999) return false;
    }
  }

  out.major = (i16) major;
  out.minor = (i16) minor;
  out.has_minor = has_minor;
  return true;
}

static int focal_find_exact_address(const FocalAddress& address) {
  for(i16 i = 0; i < focal_ast.line_count; i++) {
    if(focal_address_equal(focal_ast.lines[i].number, address)) return i;
  }
  return -1;
}

static int focal_find_address(const FocalAddress& address) {
  if(address.has_minor) return focal_find_exact_address(address);
  for(i16 i = 0; i < focal_ast.line_count; i++) {
    if(focal_ast.lines[i].number.major == address.major) return i;
  }
  return -1;
}

static int focal_find_group_start(i16 major) {
  for(i16 i = 0; i < focal_ast.line_count; i++) {
    if(focal_ast.lines[i].number.major == major) return i;
  }
  return -1;
}

static bool focal_parse_operator(const char*& p, FocalOp& op) {
  p = focal_skip_spaces(p);
  const char* begin = p;
  while(focal_is_alpha(*p)) p++;
  return focal_operator_from_range(begin, p, op);
}

static FocalParseResult focal_parse_statement_text(const char* text, FocalStatement& statement) {
  const char* p = text;
  if(!focal_parse_operator(p, statement.op)) return FocalParseResult::SYNTAX;
  p = focal_skip_spaces(p);
  if(strlen(p) >= sizeof(statement.operand)) return FocalParseResult::FULL;
  focal_copy_text(statement.operand, sizeof(statement.operand), p);
  return FocalParseResult::OK;
}

static bool focal_parse_mk_ref_token(const char*& p, const char* end, mk61_ref::Ref& ref) {
  p = focal_skip_spaces(p);
  if(p >= end || *p != '.') return false;
  const char* cursor = p + 1;
  if(cursor >= end || !focal_is_alpha(*cursor)) return false;

  char name[4];
  u8 len = 0;
  while(cursor < end && (focal_is_alpha(*cursor) || focal_is_digit(*cursor))) {
    if(len < sizeof(name) - 1) name[len++] = focal_upper(*cursor);
    cursor++;
  }
  name[len] = 0;

  if(!mk61_ref::parse_name(name, ref)) return false;
  if(ref.kind == mk61_ref::Kind::R && !mk61_ref::register_available(ref.reg)) return false;
  p = cursor;
  return true;
}

static bool focal_parse_target_token(const char*& p, const char* end, FocalTarget& target) {
  p = focal_skip_spaces(p);
  if(p >= end) return false;

  mk61_ref::Ref ref;
  if(*p == '.') {
    if(!focal_parse_mk_ref_token(p, end, ref)) return false;
    target.kind = FocalTargetKind::MK_REF;
    target.var_index = -1;
    target.mk_ref = ref;
    return true;
  }

  if(!focal_is_alpha(*p)) return false;
  const int var_index = focal_upper(*p++) - 'A';
  if(var_index < 0 || var_index >= 26) return false;
  target.kind = FocalTargetKind::VAR;
  target.var_index = var_index;
  target.mk_ref = {mk61_ref::Kind::X, 0};
  return true;
}

static bool focal_target_assignment(const char* text, FocalTarget& target, const char*& expr_begin) {
  const char* begin = focal_skip_spaces(text);
  const char* end = begin + strlen(begin);
  const char* p = begin;
  if(!focal_parse_target_token(p, end, target)) return false;
  p = focal_skip_spaces(p);
  if(p >= end || *p != '=') return false;
  expr_begin = p + 1;
  return true;
}

static bool focal_target_only(const char* text, FocalTarget& target) {
  const char* begin = focal_skip_spaces(text);
  const char* end = begin + strlen(begin);
  const char* p = begin;
  if(!focal_parse_target_token(p, end, target)) return false;
  p = focal_skip_spaces(p);
  return p == end;
}

static FocalParseResult focal_parse_line_text(const char* text, FocalAddress& number, FocalStatement& statement) {
  const char* p = text;
  if(!focal_parse_address(p, number)) return FocalParseResult::LINE;
  if(!number.has_minor) return FocalParseResult::LINE;
  p = focal_skip_spaces(p);
  return focal_parse_statement_text(p, statement);
}

static bool focal_validate_statement(FocalOp op, const char* operand);

static bool focal_compile_source(const char* source, FocalAst& ast) {
  focal_ast_reset(ast);
  if(source == NULL) return focal_error("SYNTAX?");
  if(strlen(source) >= FOCAL_SOURCE_SIZE) return focal_error("FULL?");

  const char* cursor = source;
  while(*cursor != 0) {
    while(*cursor == '\n' || *cursor == '\r') cursor++;
    if(*cursor == 0) break;

    const char* line_begin = cursor;
    while(*cursor != 0 && *cursor != '\n' && *cursor != '\r') cursor++;
    const char* line_end = cursor;

    while(line_begin < line_end && focal_is_space(*line_begin)) line_begin++;
    while(line_end > line_begin && focal_is_space(*(line_end - 1))) line_end--;
    const usize line_len = (usize) (line_end - line_begin);
    if(line_len >= FOCAL_LINE_BUFFER_SIZE) return focal_error("FULL?");

    char line_text[FOCAL_LINE_BUFFER_SIZE];
    memcpy(line_text, line_begin, line_len);
    line_text[line_len] = 0;
    if(line_text[0] == 0) continue;

    if(ast.line_count >= FOCAL_MAX_LINES) return focal_error("FULL?");

    FocalAddress number = {};
    FocalStatement statement = {};
    const FocalParseResult parse_result = focal_parse_line_text(line_text, number, statement);
    if(parse_result == FocalParseResult::LINE) return focal_error("LINE?");
    if(parse_result == FocalParseResult::SYNTAX) return focal_error("SYNTAX?");
    if(parse_result == FocalParseResult::FULL) return focal_error("FULL?");
    if(!focal_validate_statement(statement.op, statement.operand)) return false;

    const usize operand_size = strlen(statement.operand) + 1;
    if((usize) ast.operand_used + operand_size > sizeof(ast.operand_pool)) return focal_error("FULL?");

    FocalLine& line = ast.lines[ast.line_count];
    memset(&line, 0, sizeof(line));
    line.number = number;
    line.op = statement.op;
    line.operand_offset = ast.operand_used;
    memcpy(ast.operand_pool + ast.operand_used, statement.operand, operand_size);
    ast.operand_used = (u16) (ast.operand_used + operand_size);
    ast.line_count++;
  }

  if(ast.line_count == 0) return focal_error("LINE?");

  for(i16 i = 0; i < ast.line_count - 1; i++) {
    for(i16 j = i + 1; j < ast.line_count; j++) {
      if(focal_address_compare(ast.lines[j].number, ast.lines[i].number) < 0) {
        const FocalLine temp = ast.lines[i];
        ast.lines[i] = ast.lines[j];
        ast.lines[j] = temp;
      }
    }
  }

  for(i16 i = 1; i < ast.line_count; i++) {
    if(focal_address_compare(ast.lines[i - 1].number, ast.lines[i].number) == 0) {
      return focal_error("LINE?");
    }
  }

  focal_last_error[0] = 0;
  return true;
}

struct ExprParser {
  const char* p;
  const char* end;
  bool ok;
  bool evaluate;
  char error[17];
};

static void expr_set_error(ExprParser& parser, const char* error) {
  if(!parser.ok) return;
  parser.ok = false;
  focal_copy_text(parser.error, sizeof(parser.error), error);
}

static void expr_skip_spaces(ExprParser& parser) {
  while(parser.p < parser.end && focal_is_space(*parser.p)) parser.p++;
}

static bool expr_match(ExprParser& parser, char ch) {
  expr_skip_spaces(parser);
  if(parser.p >= parser.end || *parser.p != ch) return false;
  parser.p++;
  return true;
}

static double expr_checked(ExprParser& parser, double value) {
  if(parser.evaluate && (mk_math::is_nan(value) || mk_math::is_inf(value))) {
    expr_set_error(parser, "MATH?");
    return 0.0;
  }
  return parser.evaluate ? value : 0.0;
}

static double expr_parse_mk_ref(ExprParser& parser) {
  mk61_ref::Ref ref;
  if(!focal_parse_mk_ref_token(parser.p, parser.end, ref)) {
    expr_set_error(parser, "MK?");
    return 0.0;
  }

  if(!parser.evaluate) return 0.0;

  double value = 0.0;
  if(!mk61_ref::read(ref, value)) {
    expr_set_error(parser, "MK?");
    return 0.0;
  }
  return expr_checked(parser, value);
}

static double expr_parse_additive(ExprParser& parser);

static double focal_rnd(void) {
#ifdef FOCAL_HOST_TEST
  focal_random_state = focal_random_state * 1103515245UL + 12345UL;
  return (double) ((focal_random_state >> 8) & 0x00FFFFFFUL) / 16777216.0;
#else
  return (double) (entropy_pool::next_u32(entropy_pool::Domain::FOCAL) >> 8) / 16777216.0;
#endif
}

static double expr_parse_identifier(ExprParser& parser) {
  char name[12];
  u8 len = 0;
  while(parser.p < parser.end && focal_is_alpha(*parser.p)) {
    if(len < sizeof(name) - 1) name[len++] = focal_upper(*parser.p);
    parser.p++;
  }
  name[len] = 0;

  if(focal_streq(name, "PI")) return parser.evaluate ? 3.14159265358979323846 : 0.0;
  if(len == 1) {
    const int idx = name[0] - 'A';
    if(idx < 0 || idx >= 26) {
      expr_set_error(parser, "VAR?");
      return 0.0;
    }
    return expr_checked(parser, parser.evaluate ? focal_vars[idx] : 0.0);
  }

  if(!expr_match(parser, '(')) {
    expr_set_error(parser, "FUNC?");
    return 0.0;
  }

  if(focal_streq(name, "RND")) {
    if(!expr_match(parser, ')')) {
      expr_set_error(parser, "FUNC?");
      return 0.0;
    }
    return parser.evaluate ? expr_checked(parser, focal_rnd()) : 0.0;
  }

  const double a = expr_parse_additive(parser);
  double b = 0.0;
  if(focal_streq(name, "MAX")) {
    if(!expr_match(parser, ',')) {
      expr_set_error(parser, "FUNC?");
      return 0.0;
    }
    b = expr_parse_additive(parser);
  }
  if(!expr_match(parser, ')')) {
    expr_set_error(parser, "FUNC?");
    return 0.0;
  }

  const bool known = focal_streq(name, "SIN") || focal_streq(name, "COS") ||
                     focal_streq(name, "TG") || focal_streq(name, "ASIN") ||
                     focal_streq(name, "ACOS") || focal_streq(name, "ATG") ||
                     focal_streq(name, "LN") || focal_streq(name, "LG") ||
                     focal_streq(name, "EXP") || focal_streq(name, "SQRT") ||
                     focal_streq(name, "ABS") || focal_streq(name, "INT") ||
                     focal_streq(name, "FRAC") || focal_streq(name, "ROUND") ||
                     focal_streq(name, "SGN") || focal_streq(name, "MAX");
  if(!known) {
    expr_set_error(parser, "FUNC?");
    return 0.0;
  }
  if(!parser.evaluate) return 0.0;
  if(mk_math::is_nan(a) || mk_math::is_inf(a) ||
     (focal_streq(name, "MAX") && (mk_math::is_nan(b) || mk_math::is_inf(b)))) {
    expr_set_error(parser, "MATH?");
    return 0.0;
  }

  if(focal_streq(name, "SIN")) return expr_checked(parser, mk_math::sin(a));
  if(focal_streq(name, "COS")) return expr_checked(parser, mk_math::cos(a));
  if(focal_streq(name, "TG")) return expr_checked(parser, mk_math::tan(a));
  if(focal_streq(name, "ASIN")) return expr_checked(parser, mk_math::asin(a));
  if(focal_streq(name, "ACOS")) return expr_checked(parser, mk_math::acos(a));
  if(focal_streq(name, "ATG")) return expr_checked(parser, mk_math::atan(a));
  if(focal_streq(name, "LN")) return expr_checked(parser, mk_math::ln(a));
  if(focal_streq(name, "LG")) return expr_checked(parser, mk_math::log10(a));
  if(focal_streq(name, "EXP")) return expr_checked(parser, mk_math::exp(a));
  if(focal_streq(name, "SQRT")) return expr_checked(parser, mk_math::sqrt(a));
  if(focal_streq(name, "ABS")) return expr_checked(parser, mk_math::fabs(a));
  if(focal_streq(name, "INT")) return expr_checked(parser, mk_math::floor(a));
  if(focal_streq(name, "FRAC")) return expr_checked(parser, mk_math::frac(a));
  if(focal_streq(name, "ROUND")) return expr_checked(parser, mk_math::round_half(a));
  if(focal_streq(name, "SGN")) return (a > 0.0) ? 1.0 : ((a < 0.0) ? -1.0 : 0.0);
  if(focal_streq(name, "MAX")) return (a > b) ? a : b;

  return 0.0;
}

static double expr_parse_primary(ExprParser& parser) {
  expr_skip_spaces(parser);
  if(parser.p >= parser.end) {
    expr_set_error(parser, "SYNTAX?");
    return 0.0;
  }

  if(expr_match(parser, '(')) {
    const double value = expr_parse_additive(parser);
    if(!expr_match(parser, ')')) expr_set_error(parser, "SYNTAX?");
    return value;
  }

  if(focal_is_alpha(*parser.p)) return expr_parse_identifier(parser);
  if(*parser.p == '.' && parser.p + 1 < parser.end && focal_is_alpha(*(parser.p + 1))) {
    return expr_parse_mk_ref(parser);
  }

  const char* after = NULL;
  const double value = mk_math::strtod(parser.p, &after);
  if(after != NULL && after > parser.p && after <= parser.end) {
    parser.p = after;
    return expr_checked(parser, value);
  }

  expr_set_error(parser, "SYNTAX?");
  return 0.0;
}

static double expr_parse_unary(ExprParser& parser) {
  expr_skip_spaces(parser);
  if(expr_match(parser, '+')) return expr_parse_unary(parser);
  if(expr_match(parser, '-')) return expr_checked(parser, -expr_parse_unary(parser));
  return expr_parse_primary(parser);
}

static double expr_parse_power(ExprParser& parser) {
  double left = expr_parse_unary(parser);
  expr_skip_spaces(parser);
  if(expr_match(parser, '^')) {
    const double right = expr_parse_power(parser);
    if(parser.evaluate) left = expr_checked(parser, mk_math::pow(left, right));
  }
  return left;
}

static double expr_parse_multiplicative(ExprParser& parser) {
  double left = expr_parse_power(parser);
  while(parser.ok) {
    if(expr_match(parser, '*')) {
      const double right = expr_parse_power(parser);
      if(parser.evaluate) left = expr_checked(parser, left * right);
    } else if(expr_match(parser, '/')) {
      const double right = expr_parse_power(parser);
      if(parser.evaluate && right == 0.0) {
        expr_set_error(parser, "MATH?");
        return 0.0;
      }
      if(parser.evaluate) left = expr_checked(parser, left / right);
    } else {
      break;
    }
  }
  return left;
}

static double expr_parse_additive(ExprParser& parser) {
  double left = expr_parse_multiplicative(parser);
  while(parser.ok) {
    if(expr_match(parser, '+')) {
      const double right = expr_parse_multiplicative(parser);
      if(parser.evaluate) left = expr_checked(parser, left + right);
    } else if(expr_match(parser, '-')) {
      const double right = expr_parse_multiplicative(parser);
      if(parser.evaluate) left = expr_checked(parser, left - right);
    }
    else break;
  }
  return left;
}

static bool focal_parse_expr_range(const char* begin, const char* end, bool evaluate,
                                   double& value, char* error, usize error_size) {
  char buffer[FOCAL_EXPR_BUFFER_SIZE];
  while(begin < end && focal_is_space(*begin)) begin++;
  while(end > begin && focal_is_space(*(end - 1))) end--;
  const usize len = (usize) (end - begin);
  if(len == 0) {
    focal_copy_text(error, error_size, "SYNTAX?");
    return false;
  }
  if(len >= sizeof(buffer)) {
    focal_copy_text(error, error_size, "FULL?");
    return false;
  }
  memcpy(buffer, begin, len);
  buffer[len] = 0;

  ExprParser parser;
  parser.p = buffer;
  parser.end = buffer + strlen(buffer);
  parser.ok = true;
  parser.evaluate = evaluate;
  parser.error[0] = 0;

  value = expr_parse_additive(parser);
  expr_skip_spaces(parser);
  if(parser.ok && parser.p != parser.end) expr_set_error(parser, "SYNTAX?");
  if(parser.ok && evaluate && (mk_math::is_nan(value) || mk_math::is_inf(value))) expr_set_error(parser, "MATH?");
  if(!parser.ok) {
    focal_copy_text(error, error_size, parser.error[0] != 0 ? parser.error : "SYNTAX?");
    return false;
  }
  if(error_size > 0) error[0] = 0;
  return true;
}

static bool focal_validate_expr_range(const char* begin, const char* end) {
  double ignored = 0.0;
  char error[17];
  if(focal_parse_expr_range(begin, end, false, ignored, error, sizeof(error))) return true;
  return focal_error(error);
}

static bool focal_eval_expr_range(const char* begin, const char* end, double& value) {
  char error[17];
  if(focal_parse_expr_range(begin, end, true, value, error, sizeof(error))) return true;
  return focal_error(error);
}

static bool focal_eval_expr_text(const char* text, double& value) {
  if(text == NULL) return focal_error("SYNTAX?");
  return focal_eval_expr_range(text, text + strlen(text), value);
}

static const char* focal_find_top_level(const char* begin, const char* end, char target) {
  int depth = 0;
  bool in_string = false;
  for(const char* p = begin; p < end; p++) {
    if(*p == '"') {
      in_string = !in_string;
      continue;
    }
    if(in_string) continue;
    if(*p == '(') depth++;
    else if(*p == ')' && depth > 0) depth--;
    else if(*p == target && depth == 0) return p;
  }
  return NULL;
}

struct FocalOperatorRange {
  u16 start;
  u16 end;
  FocalOp op;
};

static const char* focal_skip_spaces_to(const char* p, const char* end) {
  while(p < end && focal_is_space(*p)) p++;
  return p;
}

static bool focal_statement_operator_range(const char* source, const char* statement_begin,
                                           const char* line_end, FocalOperatorRange& range) {
  const char* word_begin = focal_skip_spaces_to(statement_begin, line_end);
  const char* word_end = word_begin;
  while(word_end < line_end && focal_is_alpha(*word_end)) word_end++;
  FocalOp op = FocalOp::NOP;
  if(!focal_operator_from_range(word_begin, word_end, op)) return false;
  range.start = (u16) (word_begin - source);
  range.end = (u16) (word_end - source);
  range.op = op;
  return true;
}

static bool focal_find_next_operator_range(const char* source, u16 len, u16 from,
                                           FocalOperatorRange& range) {
  if(source == NULL || from > len) return false;
  u16 line_start = 0;
  while(line_start <= len) {
    const u16 line_end_offset = text_editor::line_end_for_start(source, line_start, len);
    const char* line_end = source + line_end_offset;
    const char* p = focal_skip_spaces_to(source + line_start, line_end);
    FocalAddress address = {};
    if(p < line_end && focal_parse_address(p, address) && p <= line_end) {
      FocalOperatorRange current = {};
      if(focal_statement_operator_range(source, p, line_end, current)) {
        while(true) {
          if(current.start >= from) {
            range = current;
            return true;
          }
          if(current.op != FocalOp::FOR) break;
          const char* operand_begin = source + current.end;
          const char* semi = focal_find_top_level(operand_begin, line_end, ';');
          if(semi == NULL || !focal_statement_operator_range(source, semi + 1, line_end, current)) break;
        }
      }
    }
    if(line_end_offset >= len) break;
    const u16 next = text_editor::next_line_start(source, line_start, len);
    if(next <= line_start) break;
    line_start = next;
  }
  return false;
}

static bool focal_transform_operator_names(char* source, u16 capacity, bool expand) {
  if(source == NULL || capacity == 0) return false;
  const usize bounded_len = text_editor::bounded_length(source, capacity);
  if(bounded_len >= capacity || bounded_len > 0xFFFFu) return false;
  u16 len = (u16) bounded_len;
  u16 search = 0;
  FocalOperatorRange range = {};
  while(focal_find_next_operator_range(source, len, search, range)) {
    const FocalOperatorName* name = focal_operator_name(range.op);
    if(name == NULL) return false;
    char short_text[2] = {name->short_name, 0};
    const char* replacement = expand ? name->full_name : short_text;
    u16 cursor = range.end;
    if(!text_editor::replace_range(source, len, cursor, capacity, range.start, range.end, replacement)) {
      return false;
    }
    search = cursor;
  }
  return true;
}

static bool focal_expand_operator_names(char* source, u16 capacity) {
  return focal_transform_operator_names(source, capacity, true);
}

static bool focal_compact_operator_names(char* source, u16 capacity) {
  return focal_transform_operator_names(source, capacity, false);
}

static bool focal_parse_var_assignment(const char* text, int& var_index, const char*& expr_begin) {
  const char* p = focal_skip_spaces(text);
  if(!focal_is_alpha(*p)) return false;
  var_index = focal_upper(*p++) - 'A';
  p = focal_skip_spaces(p);
  if(*p != '=') return false;
  expr_begin = p + 1;
  return var_index >= 0 && var_index < 26;
}

static bool focal_parse_address_complete(const char* text, bool allow_group, FocalAddress& address) {
  const char* p = focal_skip_spaces(text);
  if(!focal_parse_address(p, address)) return false;
  p = focal_skip_spaces(p);
  return *p == 0 && (allow_group || address.has_minor);
}

static bool focal_validate_print(const char* operand) {
  const char* begin = operand;
  const char* end = operand + strlen(operand);
  if(focal_skip_spaces(begin) == end) return focal_error("SYNTAX?");

  while(begin < end) {
    const char* comma = focal_find_top_level(begin, end, ',');
    const char* item_end = comma == NULL ? end : comma;
    while(begin < item_end && focal_is_space(*begin)) begin++;
    while(item_end > begin && focal_is_space(*(item_end - 1))) item_end--;
    if(begin == item_end) return focal_error("SYNTAX?");

    if((item_end - begin) == 1 && *begin == '!') {
      // Допустимый элемент перевода строки.
    } else if(*begin == '"') {
      const char* quote = begin + 1;
      while(quote < item_end && *quote != '"') quote++;
      if(quote != item_end - 1) return focal_error("SYNTAX?");
    } else if(!focal_validate_expr_range(begin, item_end)) {
      return false;
    }

    if(comma == NULL) break;
    begin = comma + 1;
  }
  return true;
}

static bool focal_validate_branch(const char* operand) {
  const char* begin = focal_skip_spaces(operand);
  if(*begin != '(') return focal_error("SYNTAX?");

  const char* expr_begin = begin + 1;
  int depth = 1;
  const char* expr_end = expr_begin;
  while(*expr_end != 0 && depth > 0) {
    if(*expr_end == '(') depth++;
    else if(*expr_end == ')') depth--;
    if(depth > 0) expr_end++;
  }
  if(depth != 0) return focal_error("SYNTAX?");
  if(!focal_validate_expr_range(expr_begin, expr_end)) return false;

  const char* list_begin = expr_end + 1;
  const char* list_end = operand + strlen(operand);
  for(int i = 0; i < 3; i++) {
    const char* comma = i < 2 ? focal_find_top_level(list_begin, list_end, ',') : NULL;
    const char* item_end = comma == NULL ? list_end : comma;
    while(list_begin < item_end && focal_is_space(*list_begin)) list_begin++;
    while(item_end > list_begin && focal_is_space(*(item_end - 1))) item_end--;
    const usize len = (usize) (item_end - list_begin);
    if(len == 0 || len >= 24) return focal_error("SYNTAX?");
    char item[24];
    memcpy(item, list_begin, len);
    item[len] = 0;
    FocalAddress address;
    if(!focal_parse_address_complete(item, false, address)) return focal_error("LINE?");
    if(i < 2) {
      if(comma == NULL) return focal_error("SYNTAX?");
      list_begin = comma + 1;
    }
  }
  return true;
}

static bool focal_validate_for(const char* operand) {
  const char* operand_end = operand + strlen(operand);
  const char* semi = focal_find_top_level(operand, operand_end, ';');
  if(semi == NULL) return focal_error("FOR?");

  const usize head_len = (usize) (semi - operand);
  if(head_len >= FOCAL_EXPR_BUFFER_SIZE) return focal_error("FULL?");
  char head[FOCAL_EXPR_BUFFER_SIZE];
  memcpy(head, operand, head_len);
  head[head_len] = 0;

  const char* expr_begin = NULL;
  int var_index = -1;
  if(!focal_parse_var_assignment(head, var_index, expr_begin)) return focal_error("FOR?");

  const char* head_end = head + strlen(head);
  const char* comma1 = focal_find_top_level(expr_begin, head_end, ',');
  if(comma1 == NULL) return focal_error("FOR?");
  const char* comma2 = focal_find_top_level(comma1 + 1, head_end, ',');
  const char* comma3 = comma2 == NULL ? NULL : focal_find_top_level(comma2 + 1, head_end, ',');
  if(comma3 != NULL) return focal_error("FOR?");

  if(!focal_validate_expr_range(expr_begin, comma1)) return false;
  if(comma2 == NULL) {
    if(!focal_validate_expr_range(comma1 + 1, head_end)) return false;
  } else {
    if(!focal_validate_expr_range(comma1 + 1, comma2) ||
       !focal_validate_expr_range(comma2 + 1, head_end)) return false;
  }

  const char* body = focal_skip_spaces(semi + 1);
  if(*body == 0) return focal_error("FOR?");
  FocalStatement statement = {};
  const FocalParseResult parse_result = focal_parse_statement_text(body, statement);
  if(parse_result == FocalParseResult::FULL) return focal_error("FULL?");
  if(parse_result != FocalParseResult::OK) return focal_error("SYNTAX?");
  return focal_validate_statement(statement.op, statement.operand);
}

static bool focal_validate_statement(FocalOp op, const char* operand) {
  const char* p = focal_skip_spaces(operand);
  switch(op) {
    case FocalOp::ASK: {
      if(*p == 0) return true;
      FocalTarget target;
      return focal_target_only(p, target) || focal_error("VAR?");
    }
    case FocalOp::SET: {
      FocalTarget target;
      const char* expr_begin = NULL;
      if(!focal_target_assignment(p, target, expr_begin)) return focal_error("SYNTAX?");
      return focal_validate_expr_range(expr_begin, expr_begin + strlen(expr_begin));
    }
    case FocalOp::FOR:
      return focal_validate_for(p);
    case FocalOp::DO: {
      FocalAddress address;
      return focal_parse_address_complete(p, true, address) || focal_error("LINE?");
    }
    case FocalOp::GOTO: {
      FocalAddress address;
      return focal_parse_address_complete(p, false, address) || focal_error("LINE?");
    }
    case FocalOp::BRANCH:
      return focal_validate_branch(p);
    case FocalOp::PRINT:
      return focal_validate_print(p);
    case FocalOp::EXIT:
    case FocalOp::RETURN:
    case FocalOp::NOP:
      return *p == 0 || focal_error("SYNTAX?");
    case FocalOp::COMMENT:
      return true;
  }
  return focal_error("SYNTAX?");
}

enum class FocalInputResult : u8 {
  VALUE,
  CANCELLED,
  ERROR
};

static bool focal_parse_input_number(const char* text, double& value) {
  if(text == NULL || text[0] == 0) return false;
  const char* end = NULL;
  value = mk_math::strtod(text, &end);
  return end != NULL && end > text && *end == 0 && !mk_math::is_nan(value) && !mk_math::is_inf(value);
}

static FocalInputResult focal_read_number_from_keyboard(const char* target_name, double& value) {
#ifdef FOCAL_HOST_TEST
  (void) target_name;
  if(focal_host_ask_cancelled) return FocalInputResult::CANCELLED;
  value = focal_host_ask_value;
  return (mk_math::is_nan(value) || mk_math::is_inf(value)) ? FocalInputResult::ERROR : FocalInputResult::VALUE;
#else
  char buffer[17];
  char prompt[17];
  memset(buffer, 0, sizeof(buffer));
  u16 len = 0;
  bool alpha_shift = false;
  snprintf(prompt, sizeof(prompt), focal_language_is_ru() ? "ВВОД %s" : "ASK %s", target_name);
  while(true) {
    focal_message_i18n(prompt, prompt, buffer, buffer);
    const i32 key = kbd::get_key_wait();
    #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
      focal_trace_header();
      Serial.print("ASK key=");
      Serial.print(key);
      Serial.print(" buf='");
      Serial.print(buffer);
      Serial.println("'");
      Serial.flush();
    #endif
    if(key == KEY_ALPHA) {
      alpha_shift = true;
      continue;
    }
    const bool alpha_key = alpha_shift || kbd::is_key_pressed(KEY_ALPHA);
    alpha_shift = false;
    if(key == KEY_ESC || key == KEY_ESC_PRESS) return FocalInputResult::CANCELLED;
    if(key == KEY_OK || key == KEY_OK_PRESS) {
      if(focal_parse_input_number(buffer, value)) return FocalInputResult::VALUE;
      focal_message_i18n("Invalid number", "Неверное число", "Try again", "Повторите");
      delay(600);
      continue;
    }
    if(key == KEY_CX) {
      text_editor::apply_single_line_cx(buffer, len, sizeof(buffer), alpha_key);
      continue;
    }
    if(key >= 0 && key < 40) {
      const char* text = focal_plain_key_text(key);
      if(text == NULL || text[1] != 0) continue;
      const char ch = text[0];
      const bool digit = ch >= '0' && ch <= '9';
      const bool sign = (ch == '-' || ch == '+') && len == 0;
      const bool dot = ch == '.' && strchr(buffer, '.') == NULL;
      if((digit || sign || dot) && len < sizeof(buffer) - 1) {
        buffer[len++] = ch;
        buffer[len] = 0;
      }
    }
  }
#endif
}

static bool focal_wait_for_key(void) {
#ifdef FOCAL_HOST_TEST
  focal_host_ask_wait_count++;
  return !focal_host_ask_cancelled;
#else
  focal_message_i18n("ASK", "ВВОД", "Press any key", "Любая клавиша");
  const i32 key = kbd::get_key_wait();
  return key != KEY_ESC && key != KEY_ESC_PRESS;
#endif
}

static FocalFlow focal_flow(FocalFlowKind kind, i16 pc) {
  FocalFlow flow;
  flow.kind = kind;
  flow.pc = pc;
  return flow;
}

static bool focal_execute_statement(FocalOp op, const char* operand, i16 current_pc, int depth, FocalFlow& flow);
static bool focal_execute_statement(const FocalLine& line, i16 current_pc, int depth, FocalFlow& flow);

static bool focal_execute_inline_statement(const char* text, i16 current_pc, int depth, FocalFlow& flow) {
  FocalStatement statement = {};
  const FocalParseResult parse_result = focal_parse_statement_text(text, statement);
  if(parse_result != FocalParseResult::OK || !focal_validate_statement(statement.op, statement.operand)) {
    flow = focal_flow(FocalFlowKind::ERROR, current_pc);
    if(focal_last_error[0] != 0) return false;
    return focal_error(parse_result == FocalParseResult::FULL ? "FULL?" : "SYNTAX?");
  }
  return focal_execute_statement(statement.op, statement.operand, current_pc, depth, flow);
}

static bool focal_execute_group(i16 major, int depth, FocalFlow& flow) {
  focal_trace_int("DO group start ", major);
  if(depth >= FOCAL_CALL_DEPTH) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("STACK?");
  }

  int pc = focal_find_group_start(major);
  if(pc < 0) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("LINE?");
  }

  while(pc >= 0 && pc < focal_ast.line_count && focal_ast.lines[pc].number.major == major) {
    FocalFlow local_flow = focal_flow(FocalFlowKind::NEXT, (i16) (pc + 1));
    if(!focal_execute_statement(focal_ast.lines[pc], (i16) pc, depth + 1, local_flow)) {
      flow = local_flow;
      return false;
    }
    if(local_flow.kind == FocalFlowKind::NEXT) {
      pc = local_flow.pc;
      continue;
    }
    if(local_flow.kind == FocalFlowKind::RETURNED) {
      flow = focal_flow(FocalFlowKind::NEXT, 0);
      return true;
    }
    flow = local_flow;
    return local_flow.kind != FocalFlowKind::ERROR;
  }

  focal_trace_int("DO group end ", major);
  flow = focal_flow(FocalFlowKind::NEXT, 0);
  return true;
}

static char focal_hex_char(u8 value) {
  return (value < 10) ? (char) ('0' + value) : (char) ('A' + value - 10);
}

static void focal_target_name(const FocalTarget& target, char* out, usize size) {
  if(size == 0) return;
  if(target.kind == FocalTargetKind::VAR) {
    out[0] = (char) ('A' + target.var_index);
    if(size > 1) out[1] = 0;
    return;
  }

  if(size < 3) {
    out[0] = 0;
    return;
  }
  out[0] = '.';
  switch(target.mk_ref.kind) {
    case mk61_ref::Kind::X:
      out[1] = 'X';
      out[2] = 0;
      return;
    case mk61_ref::Kind::Y:
      out[1] = 'Y';
      out[2] = 0;
      return;
    case mk61_ref::Kind::Z:
      out[1] = 'Z';
      out[2] = 0;
      return;
    case mk61_ref::Kind::T:
      out[1] = 'T';
      out[2] = 0;
      return;
    case mk61_ref::Kind::R:
      if(size < 4) {
        out[0] = 0;
        return;
      }
      out[1] = 'R';
      out[2] = focal_hex_char(target.mk_ref.reg);
      out[3] = 0;
      return;
  }
  out[0] = 0;
}

static bool focal_write_target(const FocalTarget& target, double value) {
  if(mk_math::is_nan(value) || mk_math::is_inf(value)) return focal_error("MATH?");
  if(target.kind == FocalTargetKind::VAR) {
    focal_vars[target.var_index] = value;
    return true;
  }
  if(!mk61_ref::write(target.mk_ref, value)) return focal_error("MK?");
  return true;
}

static bool focal_execute_set(const char* operand) {
  FocalTarget target;
  const char* expr_begin = NULL;
  if(!focal_target_assignment(operand, target, expr_begin)) return focal_error("SYNTAX?");
  double value = 0.0;
  if(!focal_eval_expr_text(expr_begin, value)) return false;
  if(!focal_write_target(target, value)) return false;
  #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
    char name[5];
    focal_target_name(target, name, sizeof(name));
    focal_trace_header();
    Serial.print("SET ");
    Serial.print(name);
    Serial.print("=");
    Serial.println(value, 10);
    Serial.flush();
  #endif
  return true;
}

static bool focal_execute_ask(const char* operand, bool& cancelled) {
  cancelled = false;
  const char* p = focal_skip_spaces(operand);
  if(*p == 0) {
    cancelled = !focal_wait_for_key();
    return true;
  }
  FocalTarget target;
  if(!focal_target_only(p, target)) return focal_error("VAR?");
  char name[5];
  focal_target_name(target, name, sizeof(name));
  double value = 0.0;
  const FocalInputResult result = focal_read_number_from_keyboard(name, value);
  if(result == FocalInputResult::CANCELLED) {
    cancelled = true;
    return true;
  }
  if(result == FocalInputResult::ERROR) return focal_error("MATH?");
  return focal_write_target(target, value);
}

static void focal_append_print(char* out, usize size, const char* text) {
  if(out[0] != 0) strncat(out, " ", size - strlen(out) - 1);
  strncat(out, text, size - strlen(out) - 1);
}

static void focal_flush_print_line(char* output, u8 row) {
  if(output[0] == 0) return;
  #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
    focal_trace_header();
    Serial.print("PRINT row=");
    Serial.print(row);
    Serial.print(" text='");
    Serial.print(output);
    Serial.println("'");
    Serial.flush();
  #endif
  focal_display_line(row, output);
  output[0] = 0;
}

static bool focal_execute_print(const char* operand) {
  const char* begin = operand;
  const char* end = operand + strlen(operand);
  char output[FOCAL_PRINT_BUFFER_SIZE];
  output[0] = 0;
  u8 output_row = 0;

  while(begin < end) {
    const char* comma = focal_find_top_level(begin, end, ',');
    const char* item_end = (comma == NULL) ? end : comma;
    while(begin < item_end && focal_is_space(*begin)) begin++;
    while(item_end > begin && focal_is_space(*(item_end - 1))) item_end--;

    if(begin < item_end) {
      if((item_end - begin) == 1 && *begin == '!') {
        focal_flush_print_line(output, output_row);
        if(output_row + 1 < lcd.rows()) output_row++;
      } else if(*begin == '"') {
        const char* text_begin = begin + 1;
        const char* quote = text_begin;
        while(quote < item_end && *quote != '"') quote++;
        if(quote != item_end - 1) return focal_error("SYNTAX?");
        char text[FOCAL_PRINT_BUFFER_SIZE];
        const usize text_len = (usize) (quote - text_begin);
        if(text_len >= sizeof(text)) return focal_error("FULL?");
        memcpy(text, text_begin, text_len);
        text[text_len] = 0;
        focal_append_print(output, sizeof(output), text);
      } else {
        double value = 0.0;
        if(!focal_eval_expr_range(begin, item_end, value)) return false;
        char number[24];
        focal_format_number(value, number, sizeof(number));
        focal_append_print(output, sizeof(output), number);
      }
    }

    if(comma == NULL) break;
    begin = comma + 1;
  }

  focal_flush_print_line(output, output_row);
  return true;
}

#ifndef FOCAL_HOST_TEST
static i32 focal_wait_for_fresh_key(void);
#endif

static void focal_wait_after_menu_run(void) {
#ifndef FOCAL_HOST_TEST
  focal_trace_text("WAIT after run");
  focal_wait_for_fresh_key();
#endif
}

#ifndef FOCAL_HOST_TEST
static void focal_wait_keys_released(void) {
  kbd::clear_hold_key();
  while(kbd::get_key() >= 0) {
  }
  while(kbd::any_key_pressed()) {
    kbd::scan_and_debounced();
    delay(10);
  }
  kbd::debounce_init();
}

static i32 focal_wait_for_fresh_key(void) {
  focal_wait_keys_released();
  while(true) {
    const i32 scan_code = kbd::scan_and_debounced();
    if(scan_code >= 0 && scan_code < (i32) key_state::RELEASED) {
      kbd::exclude_before(scan_code);
      kbd::clear_hold_key();
      return scan_code;
    }
    delay(10);
  }
}
#endif

static bool focal_execute_goto(const char* operand, FocalFlow& flow) {
  const char* p = operand;
  FocalAddress address;
  if(!focal_parse_address(p, address)) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("LINE?");
  }
  const int target = focal_find_address(address);
  if(target < 0) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("LINE?");
  }
  flow = focal_flow(FocalFlowKind::JUMP, (i16) target);
  return true;
}

static bool focal_execute_branch(const char* operand, FocalFlow& flow) {
  const char* begin = focal_skip_spaces(operand);
  if(*begin != '(') {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("SYNTAX?");
  }

  const char* expr_begin = begin + 1;
  int depth = 1;
  const char* expr_end = expr_begin;
  while(*expr_end != 0 && depth > 0) {
    if(*expr_end == '(') depth++;
    else if(*expr_end == ')') depth--;
    if(depth > 0) expr_end++;
  }
  if(depth != 0) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("SYNTAX?");
  }

  double value = 0.0;
  if(!focal_eval_expr_range(expr_begin, expr_end, value)) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return false;
  }

  const char* list_begin = expr_end + 1;
  const char* list_end = operand + strlen(operand);
  FocalAddress addresses[3];
  for(int i = 0; i < 3; i++) {
    const char* comma = (i < 2) ? focal_find_top_level(list_begin, list_end, ',') : NULL;
    const char* item_end = (comma == NULL) ? list_end : comma;
    char item[24];
    focal_copy_trim(item, sizeof(item), list_begin, item_end);
    const char* item_p = item;
    if(!focal_parse_address(item_p, addresses[i])) {
      flow = focal_flow(FocalFlowKind::ERROR, -1);
      return focal_error("LINE?");
    }
    if(i < 2) {
      if(comma == NULL) {
        flow = focal_flow(FocalFlowKind::ERROR, -1);
        return focal_error("SYNTAX?");
      }
      list_begin = comma + 1;
    }
  }

  const int selected = (value < 0.0) ? 0 : ((value > 0.0) ? 2 : 1);
  const int target = focal_find_address(addresses[selected]);
  if(target < 0) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("LINE?");
  }
  flow = focal_flow(FocalFlowKind::JUMP, (i16) target);
  return true;
}

static bool focal_execute_do(const char* operand, i16 current_pc, int depth, FocalFlow& flow) {
  const char* p = operand;
  FocalAddress address;
  if(!focal_parse_address(p, address)) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("LINE?");
  }
  #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
    focal_trace_header();
    Serial.print("DO operand='");
    Serial.print(operand);
    Serial.print("' major=");
    Serial.print(address.major);
    Serial.print(" has_minor=");
    Serial.print(address.has_minor ? 1 : 0);
    Serial.print(" minor=");
    Serial.println(address.minor);
    Serial.flush();
  #endif

  if(address.has_minor) {
    const int target = focal_find_exact_address(address);
    if(target < 0) {
      flow = focal_flow(FocalFlowKind::ERROR, -1);
      return focal_error("LINE?");
    }

    FocalFlow local_flow = focal_flow(FocalFlowKind::NEXT, (i16) (target + 1));
    if(!focal_execute_statement(focal_ast.lines[target], (i16) target, depth + 1, local_flow)) {
      flow = local_flow;
      return false;
    }
    if(local_flow.kind == FocalFlowKind::STOP || local_flow.kind == FocalFlowKind::INTERRUPTED ||
       local_flow.kind == FocalFlowKind::ERROR) {
      flow = local_flow;
      return local_flow.kind != FocalFlowKind::ERROR;
    }
    flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
    return true;
  }

  FocalFlow group_flow = focal_flow(FocalFlowKind::NEXT, 0);
  if(!focal_execute_group(address.major, depth, group_flow)) {
    flow = group_flow;
    return false;
  }
  if(group_flow.kind == FocalFlowKind::NEXT) {
    flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
    return true;
  }
  flow = group_flow;
  return group_flow.kind != FocalFlowKind::ERROR;
}

static bool focal_execute_for(const char* operand, i16 current_pc, int depth, FocalFlow& flow) {
  const char* semi = focal_find_top_level(operand, operand + strlen(operand), ';');
  if(semi == NULL) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("FOR?");
  }

  char head[FOCAL_EXPR_BUFFER_SIZE];
  focal_copy_trim(head, sizeof(head), operand, semi);
  const char* expr_begin = NULL;
  int var_index = -1;
  if(!focal_parse_var_assignment(head, var_index, expr_begin)) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("FOR?");
  }

  const char* head_end = head + strlen(head);
  const char* comma1 = focal_find_top_level(expr_begin, head_end, ',');
  if(comma1 == NULL) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("FOR?");
  }
  const char* comma2 = focal_find_top_level(comma1 + 1, head_end, ',');

  double start_value = 0.0;
  double step_value = 1.0;
  double end_value = 0.0;
  if(!focal_eval_expr_range(expr_begin, comma1, start_value)) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return false;
  }
  if(comma2 == NULL) {
    if(!focal_eval_expr_range(comma1 + 1, head_end, end_value)) {
      flow = focal_flow(FocalFlowKind::ERROR, -1);
      return false;
    }
  } else {
    if(!focal_eval_expr_range(comma1 + 1, comma2, step_value) ||
       !focal_eval_expr_range(comma2 + 1, head_end, end_value)) {
      flow = focal_flow(FocalFlowKind::ERROR, -1);
      return false;
    }
  }

  if(step_value == 0.0) {
    flow = focal_flow(FocalFlowKind::ERROR, -1);
    return focal_error("FOR?");
  }

  #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
    focal_trace_header();
    Serial.print("FOR ");
    Serial.write((char) ('A' + var_index));
    Serial.print(" start=");
    Serial.print(start_value, 10);
    Serial.print(" step=");
    Serial.print(step_value, 10);
    Serial.print(" end=");
    Serial.println(end_value, 10);
    Serial.flush();
  #endif

  const char* body = focal_skip_spaces(semi + 1);
  for(double value = start_value; (step_value > 0.0) ? (value <= end_value) : (value >= end_value);) {
    focal_vars[var_index] = value;
    #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
      focal_trace_header();
      Serial.print("FOR iter ");
      Serial.write((char) ('A' + var_index));
      Serial.print("=");
      Serial.print(value, 10);
      Serial.print(" body='");
      Serial.print(body);
      Serial.println("'");
      Serial.flush();
    #endif
    FocalFlow body_flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
    if(!focal_execute_inline_statement(body, current_pc, depth, body_flow)) {
      flow = body_flow;
      return false;
    }
    if(body_flow.kind != FocalFlowKind::NEXT) {
      flow = body_flow;
      return body_flow.kind != FocalFlowKind::ERROR;
    }
    if(value == end_value) break;
    const double next = value + step_value;
    if(mk_math::is_nan(next) || mk_math::is_inf(next) || next == value) {
      flow = focal_flow(FocalFlowKind::ERROR, current_pc);
      return focal_error("FOR?");
    }
    value = next;
  }

  flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
  return true;
}

static bool focal_execute_statement(const FocalLine& line, i16 current_pc, int depth, FocalFlow& flow) {
  focal_trace_line("EXEC", current_pc, line);
  return focal_execute_statement(line.op, focal_ast_operand(focal_ast, line), current_pc, depth, flow);
}

static bool focal_execute_statement(FocalOp op, const char* operand, i16 current_pc, int depth, FocalFlow& flow) {
  if(focal_runtime_interrupted()) {
    flow = focal_flow(FocalFlowKind::INTERRUPTED, current_pc);
    return true;
  }
  if(depth >= FOCAL_CALL_DEPTH) {
    flow = focal_flow(FocalFlowKind::ERROR, current_pc);
    return focal_error("STACK?");
  }

  switch(op) {
    case FocalOp::NOP:
    case FocalOp::COMMENT:
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    case FocalOp::ASK: {
      bool cancelled = false;
      if(!focal_execute_ask(operand, cancelled)) {
        flow = focal_flow(FocalFlowKind::ERROR, current_pc);
        return false;
      }
      if(cancelled) {
        focal_show_stopped();
        flow = focal_flow(FocalFlowKind::INTERRUPTED, current_pc);
        return true;
      }
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    }
    case FocalOp::SET:
      if(!focal_execute_set(operand)) {
        flow = focal_flow(FocalFlowKind::ERROR, current_pc);
        return false;
      }
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    case FocalOp::PRINT:
      if(!focal_execute_print(operand)) {
        flow = focal_flow(FocalFlowKind::ERROR, current_pc);
        return false;
      }
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    case FocalOp::EXIT:
      flow = focal_flow(FocalFlowKind::STOP, current_pc);
      return true;
    case FocalOp::RETURN:
      flow = focal_flow(FocalFlowKind::RETURNED, current_pc);
      return true;
    case FocalOp::GOTO:
      return focal_execute_goto(operand, flow);
    case FocalOp::BRANCH:
      return focal_execute_branch(operand, flow);
    case FocalOp::DO:
      return focal_execute_do(operand, current_pc, depth, flow);
    case FocalOp::FOR:
      return focal_execute_for(operand, current_pc, depth, flow);
  }

  flow = focal_flow(FocalFlowKind::ERROR, current_pc);
  return focal_error("SYNTAX?");
}

static int focal_program_count(void) {
#ifndef FOCAL_HOST_TEST
  return program_store::count(program_store::ProgramType::FOCAL);
#else
  int count = 0;
  for(int i = 0; i < FOCAL_PROGRAM_COUNT; i++) {
    if(programs[i].used) count++;
  }
  return count;
#endif
}

static int find_free_program(void) {
  for(int i = 0; i < FOCAL_PROGRAM_COUNT; i++) {
    if(!programs[i].used) return i;
  }
  return -1;
}

static int find_program_by_name(const char* name) {
  for(int i = 0; i < FOCAL_PROGRAM_COUNT; i++) {
    if(programs[i].used && focal_streq(programs[i].name, name)) return i;
  }
  return -1;
}

static int focal_choose_program_slot(const char* name) {
  const int existing = find_program_by_name(name);
  if(existing >= 0) return existing;

  const int free_slot = find_free_program();
  if(free_slot >= 0) return free_slot;

  return (NextFocal >= 0 && NextFocal < FOCAL_PROGRAM_COUNT) ? NextFocal : 0;
}

static bool focal_store_name_is_valid(const char* name) {
  return name != NULL && name[0] != 0 && strlen(name) < FOCAL_NAME_SIZE;
}

static bool focal_persist_write(FocalProgram& program) {
#ifdef FOCAL_HOST_TEST
  if(!focal_host_store_write_ok) return false;
  focal_copy_text(focal_host_stored_source, sizeof(focal_host_stored_source), program.source);
  return true;
#else
  u16 id = program.store_id;
  if(!program_store::write_file(program.parent_id, program.store_id,
                                program_store::ProgramType::FOCAL,
                                program.name, (const u8*) program.source,
                                program.source_len, &id)) return false;
  program.store_id = id;
  return true;
#endif
}

static bool focal_persist_remove(const FocalProgram& program) {
#ifdef FOCAL_HOST_TEST
  (void) program;
  return focal_host_store_remove_ok;
#else
  if(program.store_id != FOCAL_INVALID_STORE_ID) {
    return program_store::remove_id(program.store_id);
  }
  return program_store::remove(program_store::ProgramType::FOCAL,
                               program.name);
#endif
}

static bool focal_persist_exists(const char* name) {
#ifdef FOCAL_HOST_TEST
  return find_program_by_name(name) >= 0;
#else
  return program_store::exists(program_store::ProgramType::FOCAL, name);
#endif
}

#ifndef FOCAL_HOST_TEST
static int load_focal_program_from_store(const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::FOCAL ||
     !focal_store_name_is_valid(entry.name)) return -1;

  focal_trace_string("LOAD name=", entry.name);
  char source[FOCAL_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  u16 len = 0;
  if(!program_store::read_id(entry.id, (u8*) source,
                             FOCAL_SOURCE_SIZE - 1, &len)) return -1;
  source[len] = 0;
  focal_trace_int("LOAD len=", len);
  focal_trace_string("LOAD source=", source);
  if(!focal_expand_operator_names(source, sizeof(source))) {
    focal_error("FULL?");
    return -1;
  }

  const int slot = focal_choose_program_slot(entry.name);
  focal_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  focal_copy_text(programs[slot].name, sizeof(programs[slot].name), entry.name);
  programs[slot].store_id = entry.id;
  programs[slot].parent_id = entry.parent_id;
  programs[slot].used = true;
  NextFocal = (i8) slot;
  return slot;
}

static int load_focal_program_from_store(u16 id) {
  program_store::Entry entry;
  return program_store::entry_by_id(id, entry)
    ? load_focal_program_from_store(entry)
    : -1;
}

static int load_focal_program_from_store(const char* name) {
  if(!focal_store_name_is_valid(name)) return -1;
  const int count = program_store::count(program_store::ProgramType::FOCAL);
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(program_store::entry(program_store::ProgramType::FOCAL, i, entry) &&
       strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
      return load_focal_program_from_store(entry);
    }
  }
  return -1;
}
#endif

static void focal_program_default_name(int slot, char* out, usize size) {
  snprintf(out, size, "FOCAL%d", slot);
}

static void focal_display_program_name(const char* name, char* out, usize size) {
  if(size == 0) return;
  out[0] = 0;

#ifndef FOCAL_HOST_TEST
  const char focal_prefix[] = "FOCAL";
  bool has_focal_prefix = focal_language_is_ru();
  for(u8 i = 0; has_focal_prefix && i < 5; i++) {
    if(name[i] == 0 || focal_upper(name[i]) != focal_prefix[i]) has_focal_prefix = false;
  }

  if(has_focal_prefix) {
    bool digits_only = name[5] != 0;
    for(u8 i = 5; name[i] != 0; i++) {
      if(!focal_is_digit(name[i])) {
        digits_only = false;
        break;
      }
    }
    if(digits_only) {
      snprintf(out, size, "ФОКАЛ%s", name + 5);
      return;
    }
  }
#endif

  focal_copy_text(out, size, name);
}

static void display_focal_ok(const FocalProgram& program) {
  // Число строк выводится в верхней строке: рядом с именем оно выглядело так,
  // будто программу переименовали в "NAME <цифра>".
  char top_en[17];
  char top_ru[32];
  snprintf(top_en, sizeof(top_en), "FOCAL: %u lines",
           (unsigned) (u8) focal_ast.line_count);
  snprintf(top_ru, sizeof(top_ru), "ФОКАЛ готов: %d", (int) focal_ast.line_count);
  char display_name[24];
  focal_display_program_name(program.name, display_name, sizeof(display_name));
  focal_message_i18n(top_en, top_ru, display_name, display_name);
  delay(700);
}

static void display_focal_saved(const FocalProgram& program) {
  char display_name[24];
  focal_display_program_name(program.name, display_name, sizeof(display_name));
  focal_message_i18n("FOCAL saved", "ФОКАЛ сохранен", display_name, display_name);
  delay(700);
}

bool CompileFocal(const char* program) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
  const int slot = find_free_program();
  if(slot < 0) return focal_error("FULL?");

  if(!focal_compile_source(program, focal_ast)) return false;

  FocalProgram candidate = {};
  candidate.store_id = FOCAL_INVALID_STORE_ID;
  candidate.parent_id = FOCAL_ROOT_STORE_ID;
  focal_copy_text(candidate.source, sizeof(candidate.source), program);
  if(!focal_expand_operator_names(candidate.source, sizeof(candidate.source))) return focal_error("FULL?");
  candidate.source_len = (u16) strlen(candidate.source);
  focal_program_default_name(slot, candidate.name, sizeof(candidate.name));
  candidate.used = true;
  if(!focal_compact_operator_names(candidate.source, sizeof(candidate.source))) return focal_error("FULL?");
  candidate.source_len = (u16) strlen(candidate.source);
  if(!focal_persist_write(candidate)) return focal_error("FULL?");
  if(!focal_expand_operator_names(candidate.source, sizeof(candidate.source))) {
    (void) focal_persist_remove(candidate);
    return focal_error("FULL?");
  }
  candidate.source_len = (u16) strlen(candidate.source);

  programs[slot] = candidate;
  NextFocal = (i8) slot;
  display_focal_ok(programs[slot]);
  return true;
}

static bool compile_program_slot(int slot) {
  if(slot < 0 || slot >= FOCAL_PROGRAM_COUNT || !programs[slot].used) return focal_error("LINE?");
  focal_trace_int("compile slot=", slot);
  focal_trace_string("compile name=", programs[slot].name);
  focal_trace_int("compile source_len=", programs[slot].source_len);
  focal_trace_string("compile source=", programs[slot].source);
  return focal_compile_source(programs[slot].source, focal_ast);
}

FocalRunStatus RunFocal(int FocalN) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return FocalRunStatus::UNAVAILABLE;
#endif
  if(!compile_program_slot(FocalN)) return FocalRunStatus::COMPILE_ERROR;
  focal_trace_int("RUN slot=", FocalN);
  focal_trace_int("RUN lines=", focal_ast.line_count);
  for(i16 i = 0; i < focal_ast.line_count; i++) {
    focal_trace_line("LINE", i, focal_ast.lines[i]);
  }

  i16 pc = 0;
  while(pc >= 0 && pc < focal_ast.line_count) {
    FocalFlow flow = focal_flow(FocalFlowKind::NEXT, (i16) (pc + 1));
    if(!focal_execute_statement(focal_ast.lines[pc], pc, 0, flow)) return FocalRunStatus::RUNTIME_ERROR;
    focal_trace_flow(flow);
    if(flow.kind == FocalFlowKind::NEXT || flow.kind == FocalFlowKind::JUMP) {
      pc = flow.pc;
      continue;
    }
    if(flow.kind == FocalFlowKind::RETURNED) {
      focal_error("RETURN?");
      return FocalRunStatus::RUNTIME_ERROR;
    }
    if(flow.kind == FocalFlowKind::INTERRUPTED) return FocalRunStatus::STOPPED;
    if(flow.kind == FocalFlowKind::ERROR) return FocalRunStatus::RUNTIME_ERROR;
    if(flow.kind == FocalFlowKind::STOP) return FocalRunStatus::COMPLETED;
    return FocalRunStatus::RUNTIME_ERROR;
  }
  focal_trace_text("RUN end");
  return FocalRunStatus::COMPLETED;
}

FocalRunStatus RunFocalProgram(const char* name) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return FocalRunStatus::UNAVAILABLE;
#endif
#ifndef FOCAL_HOST_TEST
  const int slot = load_focal_program_from_store(name);
#else
  const int slot = find_program_by_name(name);
#endif
  if(slot < 0) return FocalRunStatus::NOT_FOUND;
  const FocalRunStatus status = RunFocal(slot);
  focal_wait_after_menu_run();
  return status;
}

FocalRunStatus RunFocalProgram(u16 id) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return FocalRunStatus::UNAVAILABLE;
  const int slot = load_focal_program_from_store(id);
#else
  const int slot = id < FOCAL_PROGRAM_COUNT ? (int) id : -1;
#endif
  if(slot < 0) return FocalRunStatus::NOT_FOUND;
  const FocalRunStatus status = RunFocal(slot);
  focal_wait_after_menu_run();
  return status;
}

bool FocalIsReady(void) {
  return focal_program_count() > 0;
}

void InitFocal(void) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return;
#endif
  memset(programs, 0, sizeof(programs));
  for(int i = 0; i < FOCAL_PROGRAM_COUNT; i++) {
    programs[i].store_id = FOCAL_INVALID_STORE_ID;
    programs[i].parent_id = FOCAL_ROOT_STORE_ID;
  }
  focal_ast_reset(focal_ast);
  focal_clear_vars();
  NextFocal = -1;
  focal_last_error[0] = 0;
#ifdef FOCAL_HOST_TEST
  focal_random_state = 0x3B6B120EUL;
  focal_host_ask_cancelled = false;
  focal_host_ask_wait_count = 0;
  focal_host_store_write_ok = true;
  focal_host_store_remove_ok = true;
  focal_host_stored_source[0] = 0;
#endif
}

[[maybe_unused]] static int next_used_program(int active, int delta, bool allow_new) {
  const int max_index = allow_new ? FOCAL_PROGRAM_COUNT : FOCAL_PROGRAM_COUNT - 1;
  int current = active;
  for(int i = 0; i <= max_index; i++) {
    current += delta;
    if(current < 0) current = max_index;
    if(current > max_index) current = 0;
    if(current == FOCAL_PROGRAM_COUNT) return current;
    if(programs[current].used) return current;
  }
  return active;
}

[[maybe_unused]] static void draw_program_select(int active, bool allow_new) {
#ifndef FOCAL_HOST_TEST
  const int stored_count = program_store::count(program_store::ProgramType::FOCAL);
  if(allow_new && active == stored_count) {
    focal_message_i18n("FOCAL program", "Программа", ">NEW", ">НОВАЯ");
    return;
  }

  program_store::Entry entry;
  if(active >= 0 && program_store::entry(program_store::ProgramType::FOCAL, active, entry)) {
    char line1[17];
    char ru_line1[17];
    char display_name[24];
    focal_display_program_name(entry.name, display_name, sizeof(display_name));
    snprintf(line1, sizeof(line1), ">%s", entry.name);
    snprintf(ru_line1, sizeof(ru_line1), ">%s", display_name);
    focal_message_i18n("FOCAL program", "Программа", line1, ru_line1);
    return;
  }

  focal_message_i18n("FOCAL program", "Программа", ">EMPTY", ">ПУСТО");
  (void) allow_new;
#else
  char line1[17];
  char ru_line1[17];
  if(allow_new && active == FOCAL_PROGRAM_COUNT) {
    focal_copy_text(line1, sizeof(line1), ">NEW");
    focal_copy_text(ru_line1, sizeof(ru_line1), ">НОВАЯ");
  } else if(active >= 0 && active < FOCAL_PROGRAM_COUNT && programs[active].used) {
    char display_name[24];
    focal_display_program_name(programs[active].name, display_name, sizeof(display_name));
    snprintf(line1, sizeof(line1), ">%s", programs[active].name);
    snprintf(ru_line1, sizeof(ru_line1), ">%s", display_name);
  } else {
    focal_copy_text(line1, sizeof(line1), ">EMPTY");
    focal_copy_text(ru_line1, sizeof(ru_line1), ">ПУСТО");
  }
  focal_message_i18n("FOCAL program", "Программа", line1, ru_line1);
#endif
}

static int select_focal_program(bool allow_new, u16* new_parent = NULL) {
#ifndef FOCAL_HOST_TEST
  program_store::Entry entry = {};
  u16 directory = FOCAL_ROOT_STORE_ID;
  const ProgramStoreFileDialogResult result = program_store_choose_file(
      program_store::ProgramType::FOCAL, FOCAL_ROOT_STORE_ID, allow_new,
      entry, directory);
  if(result == ProgramStoreFileDialogResult::CANCELLED) return -1;
  if(result == ProgramStoreFileDialogResult::NEW_FILE) {
    if(new_parent != NULL) *new_parent = directory;
    return FOCAL_PROGRAM_COUNT;
  }
  return load_focal_program_from_store(entry);
#else
  if(new_parent != NULL) *new_parent = FOCAL_ROOT_STORE_ID;
  int active = -1;
  for(int i = 0; i < FOCAL_PROGRAM_COUNT; i++) {
    if(programs[i].used) {
      active = i;
      break;
    }
  }
  if(active < 0) active = allow_new ? FOCAL_PROGRAM_COUNT : -1;
  if(active < 0) {
    focal_message_i18n("FOCAL is empty", "ФОКАЛ пуст", "Press any key", "Любая клавиша");
    kbd::get_key_wait();
    return -1;
  }

  while(true) {
    draw_program_select(active, allow_new);
    const i32 key = kbd::get_key_wait();
    switch(key) {
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
  if(!workspace_scope.ok()) return false;
#endif
  const int program = select_focal_program(false);
  if(program >= 0) {
    RunFocal(program);
    focal_wait_after_menu_run();
  }
  return true;
}

static u16 focal_line_start_for_cursor(const char* source, u16 cursor) {
  return text_editor::line_start_for_cursor(source, cursor);
}

static bool focal_operator_range_for_cursor(const char* source, u16 len, u16 cursor,
                                            FocalOperatorRange& atomic_range) {
  u16 search = 0;
  FocalOperatorRange range = {};
  while(focal_find_next_operator_range(source, len, search, range)) {
    u16 end = range.end;
    while(end < len && focal_is_space(source[end])) end++;
    if(cursor > range.start && cursor <= end) {
      atomic_range = range;
      atomic_range.end = end;
      return true;
    }
    if(range.start >= cursor) break;
    search = range.end;
  }
  return false;
}

static bool focal_editor_move_cursor_left(const char* source, u16& cursor) {
  const u16 len = source == NULL ? 0 : (u16) strlen(source);
  FocalOperatorRange range = {};
  if(focal_operator_range_for_cursor(source, len, cursor, range)) {
    cursor = range.start;
    return true;
  }
  return text_editor::move_cursor_left(source, cursor);
}

static bool focal_editor_move_cursor_right(const char* source, u16 len, u16& cursor) {
  FocalOperatorRange range = {};
  u16 search = 0;
  while(focal_find_next_operator_range(source, len, search, range)) {
    u16 end = range.end;
    while(end < len && focal_is_space(source[end])) end++;
    if(cursor >= range.start && cursor < end) {
      cursor = end;
      return true;
    }
    if(range.start > cursor) break;
    search = range.end;
  }
  return text_editor::move_cursor_right(source, len, cursor);
}

static bool focal_editor_backspace(char* source, u16& len, u16& cursor, u16 capacity) {
  FocalOperatorRange range = {};
  if(focal_operator_range_for_cursor(source, len, cursor, range)) {
    return text_editor::replace_range(source, len, cursor, capacity, range.start, range.end, "");
  }
  return text_editor::backspace(source, len, cursor);
}

[[maybe_unused]] static bool focal_editor_move_cursor_line(const char* source, u16 len, u16& cursor, int delta) {
  return text_editor::move_cursor_line(source, len, cursor, delta);
}

static void focal_editor_ensure_cursor_visible(const char* source, u16 len, u16 cursor, u16& view_top) {
  text_editor::ensure_cursor_visible(lcd, source, len, cursor, view_top);
}

static void draw_focal_editor(const char* source, u16 len, u16 cursor, u16 view_top, int slot, bool sms_cursor = false) {
  text_editor::draw(lcd, source, len, cursor, view_top, sms_cursor);
  (void) slot;
}

static bool focal_find_expression_before_cursor(const char* source, u16 cursor, u16& start, u16& end) {
  end = cursor;
  while(end > 0 && focal_is_space(source[end - 1])) end--;
  if(end == 0) return false;

  start = end;
  int depth = 0;
  bool in_string = false;
  while(start > 0) {
    const char ch = source[start - 1];
    if(ch == '"') {
      in_string = !in_string;
      start--;
      continue;
    }
    if(in_string) {
      start--;
      continue;
    }
    if(ch == ')') {
      depth++;
      start--;
      continue;
    }
    if(ch == '(' && depth > 0) {
      depth--;
      start--;
      continue;
    }
    if(depth == 0 && (ch == '\n' || ch == '\r' || ch == '=' || ch == ';' || ch == ',')) break;
    start--;
  }

  const bool at_line_start = start == 0 || source[start - 1] == '\n' || source[start - 1] == '\r';
  const bool after_statement = start > 0 && source[start - 1] == ';';
  while(start < end && focal_is_space(source[start])) start++;

  // В начале строки (или после разделителя FOR) пропускаем адрес и имя
  // оператора. Макрос должен охватывать операнд PRINT, а не весь фрагмент
  // исходного текста "1.10 PRINT X".
  if(at_line_start || after_statement) {
    const char* p = source + start;
    const char* const segment_end = source + end;
    bool has_address = false;
    if(at_line_start) {
      FocalAddress address = {};
      const char* after_address = p;
      if(focal_parse_address(after_address, address)) {
        p = after_address;
        has_address = true;
      }
    }
    while(p < segment_end && focal_is_space(*p)) p++;
    const char* const operator_begin = p;
    while(p < segment_end && focal_is_alpha(*p)) p++;
    FocalOp op;
    const bool explicit_operator = has_address || after_statement || p - operator_begin > 1;
    if(explicit_operator && p > operator_begin && focal_operator_from_range(operator_begin, p, op)) {
      while(p < segment_end && focal_is_space(*p)) p++;
      start = (u16) (p - source);
    } else if(has_address) {
      // Отдельный адрес строки относится к структуре редактора, а не является числовым операндом.
      return false;
    }
  }
  return start < end;
}

static bool focal_segment_is_wrapped(const char* begin, const char* end) {
  if(end - begin < 2 || *begin != '(' || *(end - 1) != ')') return false;
  int depth = 0;
  for(const char* p = begin; p < end; p++) {
    if(*p == '(') depth++;
    else if(*p == ')') {
      depth--;
      if(depth == 0 && p != end - 1) return false;
    }
  }
  return depth == 0;
}

static bool focal_segment_is_simple(const char* begin, const char* end) {
  if(begin >= end) return false;
  if(focal_segment_is_wrapped(begin, end)) return true;

  if(focal_is_alpha(*begin)) {
    const char* p = begin;
    while(p < end && focal_is_alpha(*p)) p++;
    if(p == end) return true;
    if(*p == '(' && *(end - 1) == ')') {
      return focal_segment_is_wrapped(p, end);
    }
  }

  char buffer[FOCAL_EXPR_BUFFER_SIZE];
  focal_copy_trim(buffer, sizeof(buffer), begin, end);
  const char* after = NULL;
  mk_math::strtod(buffer, &after);
  return after != NULL && *after == 0;
}

static bool focal_editor_apply_expr_macro(char* source, u16& len, u16& cursor, u16 capacity, i32 key_code) {
  const keyboard_layout::Mapping& keys = keyboard_layout::ACTIVE;
  const bool square = key_code == keys.mul;
  const bool inverse = key_code == keys.div;
  const bool power10 = key_code == keys.digit[0];
  const char* function = NULL;
  if(key_code == keys.sub) function = "SQRT";
  else if(key_code == keys.neg) function = "ABS";
  else if(key_code == keys.digit[1]) function = "EXP";
  else if(key_code == keys.digit[2]) function = "LG";
  else if(key_code == keys.digit[3]) function = "LN";
  else if(key_code == keys.digit[4]) function = "ASIN";
  else if(key_code == keys.digit[5]) function = "ACOS";
  else if(key_code == keys.digit[6]) function = "ATG";
  else if(key_code == keys.digit[7]) function = "SIN";
  else if(key_code == keys.digit[8]) function = "COS";
  else if(key_code == keys.digit[9]) function = "TG";
  if(!square && !inverse && !power10 && function == NULL) return false;

  u16 start = 0;
  u16 end = 0;
  if(!focal_find_expression_before_cursor(source, cursor, start, end)) return false;
  const usize expr_len = (usize) (end - start);
  if(expr_len >= FOCAL_EXPR_BUFFER_SIZE) return false;

  double ignored = 0.0;
  char error[17];
  if(!focal_parse_expr_range(&source[start], &source[end], false, ignored, error, sizeof(error))) return false;

  const bool simple = focal_segment_is_simple(&source[start], &source[end]);
  char expr[FOCAL_EXPR_BUFFER_SIZE];
  focal_copy_trim(expr, sizeof(expr), &source[start], &source[end]);

  char replacement[FOCAL_EXPR_BUFFER_SIZE + 8];
  int written = -1;
  if(square) {
    written = snprintf(replacement, sizeof(replacement), simple ? "%s^2" : "(%s)^2", expr);
  } else if(inverse) {
    written = snprintf(replacement, sizeof(replacement), simple ? "1/%s" : "1/(%s)", expr);
  } else if(power10) {
    written = snprintf(replacement, sizeof(replacement), simple ? "10^%s" : "10^(%s)", expr);
  } else {
    written = snprintf(replacement, sizeof(replacement), "%s(%s)", function, expr);
  }
  if(written < 0 || (usize) written >= sizeof(replacement)) return false;
  return text_editor::replace_range(source, len, cursor, capacity, start, end, replacement);
}

static bool focal_cursor_inside_string(const char* source, u16 cursor) {
  bool inside = false;
  for(u16 i = 0; i < cursor && source[i] != 0; i++) {
    if(source[i] == '"') inside = !inside;
  }
  return inside;
}

static bool focal_cursor_expects_statement(const char* source, u16 cursor) {
  if(focal_cursor_inside_string(source, cursor)) return false;

  const u16 line_start = focal_line_start_for_cursor(source, cursor);
  int pos = (int) cursor - 1;
  while(pos >= 0 && (source[pos] == ' ' || source[pos] == '\t')) pos--;
  if(pos >= (int) line_start && source[pos] == ';') return true;

  const char* p = source + line_start;
  const char* end = source + cursor;
  while(p < end && focal_is_space(*p)) p++;

  FocalAddress address;
  if(!focal_parse_address(p, address)) return false;

  bool has_space_after_address = false;
  while(p < end && focal_is_space(*p)) {
    has_space_after_address = true;
    p++;
  }
  return has_space_after_address && p == end;
}

static bool focal_cursor_after_line_address(const char* source, u16 cursor, FocalAddress* out = NULL) {
  if(focal_cursor_inside_string(source, cursor)) return false;

  const u16 line_start = focal_line_start_for_cursor(source, cursor);
  const char* p = source + line_start;
  const char* end = source + cursor;
  while(p < end && focal_is_space(*p)) p++;

  FocalAddress address;
  if(!focal_parse_address(p, address)) return false;
  if(out != NULL) *out = address;
  return p == end;
}

static const char* focal_statement_insert_text(i32 key_code, bool leading_space = false) {
  const keyboard_layout::Mapping& keys = keyboard_layout::ACTIVE;
  if(key_code == keys.dot) return leading_space ? " ASK " : "ASK ";
  if(key_code == keys.neg) return leading_space ? " BRANCH " : "BRANCH ";
  if(key_code == keys.power) return leading_space ? " COMMENT " : "COMMENT ";
  if(key_code == keys.cx) return leading_space ? " DO " : "DO ";
  if(key_code == keys.bx) return leading_space ? " EXIT" : "EXIT";
  if(key_code == keys.mul) return leading_space ? " FOR " : "FOR ";
  if(key_code == keys.degree) return leading_space ? " GOTO " : "GOTO ";
  if(key_code == keys.radian) return leading_space ? " PRINT " : "PRINT ";
  if(key_code == keys.x_to_p) return leading_space ? " SET " : "SET ";
  if(key_code == keys.ret) return leading_space ? " RETURN" : "RETURN";
  return NULL;
}

static const char* focal_editor_insert_text_for_key(FocalEditShift shift, i32 key_code, const char* source, u16 cursor) {
  if(key_code < 0 || key_code >= 40) return NULL;
  switch(shift) {
    case FocalEditShift::NONE:
      if(focal_cursor_expects_statement(source, cursor)) {
        const char* statement = focal_statement_insert_text(key_code);
        if(statement != NULL) return statement;
      }
      FocalAddress address;
      if(focal_cursor_after_line_address(source, cursor, &address)) {
        if(key_code == keyboard_layout::ACTIVE.dot && !address.has_minor) return focal_plain_key_text(key_code);
        const char* statement = focal_statement_insert_text(key_code, true);
        if(statement != NULL) return statement;
      }
      return focal_plain_key_text(key_code);
    case FocalEditShift::ALPHA:
      return NULL;
    case FocalEditShift::K: {
      const char* punctuation = focal_kshift_key_text(key_code);
      if(punctuation != NULL) return punctuation;
      FocalAddress address;
      if(focal_cursor_after_line_address(source, cursor, &address)) {
        const char* statement = focal_statement_insert_text(key_code, true);
        if(statement != NULL) return statement;
      } else {
        const char* statement = focal_statement_insert_text(key_code);
        if(statement != NULL) return statement;
      }
      return NULL;
    }
  }
  return NULL;
}

static const char* focal_editor_insert_text_hook(text_editor::Shift shift, i32 key_code, const char* source, u16 cursor, void*) {
  return focal_editor_insert_text_for_key((FocalEditShift) shift, key_code, source, cursor);
}

static bool focal_editor_apply_alpha_macro_hook(char* source, u16& len, u16& cursor, u16 capacity, i32 key_code, void*) {
  return focal_editor_apply_expr_macro(source, len, cursor, capacity, key_code);
}

static bool focal_editor_move_cursor_horizontal_hook(const char* source, u16 len, u16& cursor, int delta, void*) {
  if(delta < 0) return focal_editor_move_cursor_left(source, cursor);
  if(delta > 0) return focal_editor_move_cursor_right(source, len, cursor);
  return false;
}

static bool focal_editor_backspace_hook(char* source, u16& len, u16& cursor, u16 capacity, void*) {
  return focal_editor_backspace(source, len, cursor, capacity);
}

static const text_editor::KeyMap FOCAL_EDITOR_KEYS = {
  (i32) KEY_LEFT,
  KEY_LEFT_PRESS,
  (i32) KEY_RIGHT,
  KEY_RIGHT_PRESS,
  (i32) KEY_OK,
  KEY_OK_PRESS,
  (i32) KEY_ESC,
  KEY_ESC_PRESS,
  KEY_SHG_LEFT_PRESS,
  KEY_SHG_RIGHT_PRESS,
  (i32) KEY_K,
  KEY_ALPHA,
  (i32) KEY_PP
};

static const text_editor::Hooks FOCAL_EDITOR_HOOKS = {
  &focal_editor_insert_text_hook,
  &focal_editor_apply_alpha_macro_hook,
  &focal_editor_move_cursor_horizontal_hook,
  &focal_editor_backspace_hook,
  NULL
};

static bool focal_confirm_save(void) {
  focal_message_i18n("Save FOCAL?", "Сохранить?", "OK=yes ESC=no", "OK=да ESC=нет");
  while(true) {
    const i32 key = kbd::get_key_wait();
    if(key == KEY_OK || key == KEY_OK_PRESS) return true;
    if(key == KEY_ESC || key == KEY_ESC_PRESS) return false;
  }
}

static void draw_focal_name_editor(const char* name, u16 cursor, bool sms_cursor) {
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
  focal_message_i18n("FOCAL name", "Имя ФОКАЛ", line, line);
  MK61DisplayUpdate update(lcd);
  const u8 cursor_col = (u8) (1 + cursor - window);
  lcd.setCursor(cursor_col, 1);
  if(lcd.supportsCursor()) lcd.cursorOn();
  else lcd.write(sms_cursor ? SMS_CURSOR_ASCII : text_editor::CURSOR_ASCII);
}

static bool focal_name_insert_char(char* name, u16& len, u16& cursor, char ch) {
  if(ch == ' ' && len == 0) return false;
  char text[2] = {focal_upper(ch), 0};
  return text_editor::insert_text(name, len, cursor, FOCAL_NAME_SIZE, text);
}

static bool focal_name_sms_tap(char* name, u16& len, u16& cursor, FocalSmsState& sms, i32 key_code, u32 now) {
  const char* letters = focal_sms_letters_for_key(key_code);
  if(letters == NULL || letters[0] == 0) {
    focal_sms_reset(sms);
    return false;
  }

  if(sms.active && sms.key_code == key_code && cursor > 0) {
    const usize count = strlen(letters);
    sms.index = (u8) ((sms.index + 1) % count);
    name[cursor - 1] = letters[sms.index];
    sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
    return true;
  }

  sms.active = true;
  sms.key_code = key_code;
  sms.index = 0;
  sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
  return focal_name_insert_char(name, len, cursor, letters[0]);
}

[[maybe_unused]] static bool focal_input_program_name(char* name, usize size) {
  if(size == 0) return false;
  name[size - 1] = 0;
  u16 len = (u16) strlen(name);
  if(len >= size) len = (u16) size - 1;
  u16 cursor = len;
  FocalSmsState sms = {};
  FocalEditShift shift = FocalEditShift::NONE;

  while(true) {
    const u32 now = millis();
    if(sms.active && now >= sms.deadline_ms) focal_sms_reset(sms);
    draw_focal_name_editor(name, cursor, sms.active);
    const i32 key = kbd::get_key_wait();
    const bool shifted_key = shift != FocalEditShift::NONE;
    const int digit = focal_digit_from_key(key);

    if(!shifted_key && sms.active) {
      if(focal_sms_key_is_letters(key)) {
        focal_name_sms_tap(name, len, cursor, sms, key, now);
        continue;
      }
      if(focal_sms_key_is_space(key)) {
        focal_sms_reset(sms);
        focal_name_insert_char(name, len, cursor, ' ');
        continue;
      }
      if(digit == 0) {
        focal_sms_reset(sms);
        continue;
      }
      if(key == KEY_PP) {
        focal_sms_reset(sms);
        focal_name_insert_char(name, len, cursor, ' ');
        continue;
      }
      focal_sms_reset(sms);
    }

    if(!shifted_key && (key == KEY_K || key == KEY_ALPHA)) {
      shift = (key == KEY_K) ? FocalEditShift::K : FocalEditShift::ALPHA;
      focal_sms_reset(sms);
      continue;
    }
    if(!shifted_key && (key == KEY_OK || key == KEY_OK_PRESS)) return len > 0;
    if(!shifted_key && (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if(key == KEY_CX &&
        (shift == FocalEditShift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      focal_sms_reset(sms);
      len = 0;
      cursor = 0;
      name[0] = 0;
      shift = FocalEditShift::NONE;
      continue;
    }
    if((key == KEY_LEFT || key == KEY_LEFT_PRESS) &&
        (shift == FocalEditShift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      focal_sms_reset(sms);
      shift = FocalEditShift::NONE;
      continue;
    }
    if(!shifted_key && (key == KEY_LEFT || key == KEY_LEFT_PRESS)) {
      focal_sms_reset(sms);
      text_editor::move_cursor_left(name, cursor);
      continue;
    }
    if(!shifted_key && (key == KEY_RIGHT || key == KEY_RIGHT_PRESS)) {
      focal_sms_reset(sms);
      text_editor::move_cursor_right(name, len, cursor);
      continue;
    }
    if(!shifted_key && key == KEY_CX) {
      focal_sms_reset(sms);
      text_editor::backspace(name, len, cursor);
      continue;
    }

    if(shift == FocalEditShift::ALPHA && digit >= 0) {
      const char* symbol = focal_symbol_for_digit_key(key);
      if(symbol != NULL && symbol[0] != 0) focal_name_insert_char(name, len, cursor, symbol[0]);
      shift = FocalEditShift::NONE;
      focal_sms_reset(sms);
      continue;
    }
    if(shift == FocalEditShift::ALPHA) {
      shift = FocalEditShift::NONE;
      focal_sms_reset(sms);
      continue;
    }
    if(shift == FocalEditShift::K && focal_sms_key_is_letters(key)) {
      focal_name_sms_tap(name, len, cursor, sms, key, now);
      shift = FocalEditShift::NONE;
      continue;
    }
    if(shift == FocalEditShift::K && focal_sms_key_is_space(key)) {
      focal_sms_reset(sms);
      focal_name_insert_char(name, len, cursor, ' ');
      shift = FocalEditShift::NONE;
      continue;
    }
    if(shift == FocalEditShift::K) {
      const char* punctuation = focal_kshift_key_text(key);
      focal_sms_reset(sms);
      if(punctuation != NULL && punctuation[0] != 0 && punctuation[1] == 0) {
        focal_name_insert_char(name, len, cursor, punctuation[0]);
      }
      shift = FocalEditShift::NONE;
      continue;
    }
    if(key == KEY_PP) {
      focal_sms_reset(sms);
      focal_name_insert_char(name, len, cursor, ' ');
      shift = FocalEditShift::NONE;
      continue;
    }
    if(digit >= 0) {
      focal_sms_reset(sms);
      focal_name_insert_char(name, len, cursor, (char) ('0' + digit));
      shift = FocalEditShift::NONE;
      continue;
    }

    shift = FocalEditShift::NONE;
  }
}

static bool store_edited_program(int slot, char* source, const char* store_name,
                                 u16 target_parent = FOCAL_ROOT_STORE_ID) {
  if(slot < 0 || slot > FOCAL_PROGRAM_COUNT) return focal_error("SLOT?");
  if(source == NULL || strlen(source) >= FOCAL_SOURCE_SIZE) return focal_error("FULL?");
  if(!focal_store_name_is_valid(store_name)) return focal_error("NAME?");

  char old_name[FOCAL_NAME_SIZE] = "";
  FocalProgram previous = {};
  previous.store_id = FOCAL_INVALID_STORE_ID;
  previous.parent_id = target_parent;
  if(slot >= 0 && slot < FOCAL_PROGRAM_COUNT && programs[slot].used) {
    focal_copy_text(old_name, sizeof(old_name), programs[slot].name);
    previous = programs[slot];
  }

  if(slot == FOCAL_PROGRAM_COUNT) {
    slot = focal_choose_program_slot(store_name);
  }
  if(slot < 0 || slot >= FOCAL_PROGRAM_COUNT) return focal_error("SLOT?");

  if(old_name[0] != 0 && previous.store_id == FOCAL_INVALID_STORE_ID &&
     !focal_streq(old_name, store_name) && focal_persist_exists(store_name)) {
    return focal_error("NAME?");
  }

  FocalProgram candidate = {};
  candidate.store_id = previous.store_id;
  candidate.parent_id = target_parent;
  focal_copy_text(candidate.source, sizeof(candidate.source), source);
  if(!focal_expand_operator_names(candidate.source, sizeof(candidate.source))) return focal_error("FULL?");
  candidate.source_len = (u16) strlen(candidate.source);
  focal_copy_text(candidate.name, sizeof(candidate.name), store_name);
  candidate.used = true;

  if(!focal_compact_operator_names(candidate.source, sizeof(candidate.source))) return focal_error("FULL?");
  candidate.source_len = (u16) strlen(candidate.source);
  if(!focal_persist_write(candidate)) return focal_error("FULL?");
  if(!focal_expand_operator_names(candidate.source, sizeof(candidate.source))) {
    if(previous.store_id == FOCAL_INVALID_STORE_ID) {
      (void) focal_persist_remove(candidate);
    }
    return focal_error("FULL?");
  }
  candidate.source_len = (u16) strlen(candidate.source);
  if(old_name[0] != 0 && previous.store_id == FOCAL_INVALID_STORE_ID &&
     !focal_streq(old_name, candidate.name) && !focal_persist_remove(previous)) {
    (void) focal_persist_remove(candidate);
    return focal_error("FULL?");
  }

  programs[slot] = candidate;
  NextFocal = (i8) slot;
  display_focal_saved(programs[slot]);
  return true;
}

static void EditFocalSlot(int slot,
                          u16 new_parent = FOCAL_ROOT_STORE_ID) {
  char source[FOCAL_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  if(slot >= 0 && slot < FOCAL_PROGRAM_COUNT && programs[slot].used) focal_copy_text(source, sizeof(source), programs[slot].source);

  text_editor::Buffer editor;
  text_editor::init(editor, source, FOCAL_SOURCE_SIZE);
#if defined(MK61_DISPLAY_LCD1602) && !defined(FOCAL_HOST_TEST)
  text_editor::DisplaySession display_session(lcd);
#endif
  bool dirty = true;

  kbd::debounce_init();
  while(true) {
    const u32 now = millis();
    if(editor.sms.active && now >= editor.sms.deadline_ms) {
      text_editor::sms_reset(editor.sms);
      dirty = true;
    }
    if(dirty) {
      focal_editor_ensure_cursor_visible(source, editor.len, editor.cursor, editor.view_top);
      draw_focal_editor(source, editor.len, editor.cursor, editor.view_top, slot, editor.sms.active);
      dirty = false;
    }

    kbd::scan_and_debounced();
    i32 key_code = kbd::get_key(key_state::PRESSED);
    if(key_code < 0) {
      lcd.flush();
      delay(1);
      continue;
    }
    if(key_code == KEY_CX &&
        (editor.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      text_editor::clear_current_line(editor.source, editor.len, editor.cursor, editor.capacity);
      editor.shift = text_editor::Shift::NONE;
      dirty = true;
      continue;
    }
    if((key_code == KEY_LEFT || key_code == KEY_LEFT_PRESS) &&
        (editor.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      editor.shift = text_editor::Shift::NONE;
      dirty = true;
      continue;
    }
    const text_editor::KeyResult result = text_editor::handle_key(editor, FOCAL_EDITOR_KEYS, FOCAL_EDITOR_HOOKS, key_code, now);
    dirty = result != text_editor::KeyResult::NONE;

    if(result == text_editor::KeyResult::SAVE) {
      lcd.cursorOff();
      if(!focal_confirm_save()) return;
      char name[FOCAL_NAME_SIZE];
      memset(name, 0, sizeof(name));
      if(slot >= 0 && slot < FOCAL_PROGRAM_COUNT && programs[slot].used) focal_copy_text(name, sizeof(name), programs[slot].name);
      else focal_program_default_name(find_free_program() < 0 ? 0 : find_free_program(), name, sizeof(name));
      u16 parent = (slot >= 0 && slot < FOCAL_PROGRAM_COUNT &&
                    programs[slot].used)
          ? programs[slot].parent_id : new_parent;
#ifndef FOCAL_HOST_TEST
      if(!program_store_choose_save_target(program_store::ProgramType::FOCAL,
                                           parent, name, sizeof(name),
                                           parent)) {
        kbd::debounce_init();
        dirty = true;
        continue;
      }
#else
      if(!focal_input_program_name(name, sizeof(name))) return;
#endif
      if(store_edited_program(slot, source, name, parent)) return;
      delay(700);
      kbd::debounce_init();
      dirty = true;
      continue;
    }
  }
}

void EditFocal(void) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return;
#endif
  u16 new_parent = FOCAL_ROOT_STORE_ID;
  const int slot = select_focal_program(true, &new_parent);
  if(slot < 0) return;
  EditFocalSlot(slot, new_parent);
}

bool EditFocalProgram(const char* name) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
#ifndef FOCAL_HOST_TEST
  const int slot = load_focal_program_from_store(name);
  if(slot < 0) return false;
  EditFocalSlot(slot);
  return true;
#else
  (void) name;
  return false;
#endif
}

bool EditFocalProgram(u16 id) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
  const int slot = load_focal_program_from_store(id);
  if(slot < 0) return false;
  EditFocalSlot(slot);
  return true;
#else
  (void) id;
  return false;
#endif
}

static bool FOCAL_clear_data(void) {
  focal_clear_vars();
  focal_message_i18n("FOCAL data", "Данные", "cleared", "очищены");
  delay(700);
  return true;
}

static bool FOCAL_run_menu(void) {
  return FOCAL_library_select();
}

static bool FOCAL_edit_menu(void) {
  EditFocal();
  return true;
}

static constexpr t_punct FOCAL_EDIT_PUNCT  = {.size = 10, .action = &FOCAL_edit_menu,  .text = "Edit FOCAL"};
static constexpr t_punct FOCAL_RUN_PUNCT   = {.size = 9,  .action = &FOCAL_run_menu,   .text = "Run FOCAL"};
static constexpr t_punct FOCAL_CLEAR_PUNCT = {.size = 10, .action = &FOCAL_clear_data, .text = "Clear DATA"};

#ifndef FOCAL_HOST_TEST
static constexpr t_punct RU_FOCAL_EDIT_PUNCT  = {.size = 15, .action = &FOCAL_edit_menu,  .text = "Правка"};
static constexpr t_punct RU_FOCAL_RUN_PUNCT   = {.size = 15, .action = &FOCAL_run_menu,   .text = "Запуск"};
static constexpr t_punct RU_FOCAL_CLEAR_PUNCT = {.size = 15, .action = &FOCAL_clear_data, .text = "Сброс данных"};
#endif

bool FOCAL_menu_select(void) {
#ifndef FOCAL_HOST_TEST
  FocalWorkspaceScope workspace_scope;
  if(!workspace_scope.ok()) return false;
#endif
  t_punct* items[] = {
#ifndef FOCAL_HOST_TEST
    (t_punct*) (focal_language_is_ru() ? &RU_FOCAL_EDIT_PUNCT : &FOCAL_EDIT_PUNCT),
    (t_punct*) (focal_language_is_ru() ? &RU_FOCAL_RUN_PUNCT : &FOCAL_RUN_PUNCT),
    (t_punct*) (focal_language_is_ru() ? &RU_FOCAL_CLEAR_PUNCT : &FOCAL_CLEAR_PUNCT)
#else
    (t_punct*) &FOCAL_EDIT_PUNCT,
    (t_punct*) &FOCAL_RUN_PUNCT,
    (t_punct*) &FOCAL_CLEAR_PUNCT
#endif
  };
  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  menu.select();
  return true;
}

#ifdef FOCAL_SELF_TEST
extern "C" void FocalTestReset(void) {
  InitFocal();
  lcd.clear();
#ifdef FOCAL_HOST_TEST
  mk61_ref::host_reset();
  kbd::host_alpha_pressed = false;
#endif
}

extern "C" bool FocalTestCompile(const char* source) {
  return focal_compile_source(source, focal_ast);
}

extern "C" const char* FocalTestError(void) {
  return focal_last_error;
}

extern "C" void FocalTestSetAlphaHeld(bool held) {
#ifdef FOCAL_HOST_TEST
  kbd::host_alpha_pressed = held;
#else
  (void) held;
#endif
}

extern "C" int FocalTestAddProgram(const char* source) {
  const int slot = find_free_program();
  if(slot < 0) return -1;
  if(!focal_compile_source(source, focal_ast)) return -1;
  focal_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  focal_program_default_name(slot, programs[slot].name, sizeof(programs[slot].name));
  programs[slot].used = true;
  NextFocal = (i8) slot;
  return slot;
}

extern "C" bool FocalTestStoreDraft(const char* source, const char* name) {
  if(source == NULL || strlen(source) >= FOCAL_SOURCE_SIZE) return focal_error("FULL?");
  char buffer[FOCAL_SOURCE_SIZE];
  focal_copy_text(buffer, sizeof(buffer), source);
  return store_edited_program(FOCAL_PROGRAM_COUNT, buffer, name == NULL ? "DRAFT" : name);
}

extern "C" bool FocalTestStoreSlot(int slot, const char* source, const char* name) {
  if(source == NULL || strlen(source) >= FOCAL_SOURCE_SIZE) return focal_error("FULL?");
  char buffer[FOCAL_SOURCE_SIZE];
  focal_copy_text(buffer, sizeof(buffer), source);
  return store_edited_program(slot, buffer, name == NULL ? "DRAFT" : name);
}

extern "C" void FocalTestSetStoreResults(bool write_ok, bool remove_ok) {
#ifdef FOCAL_HOST_TEST
  focal_host_store_write_ok = write_ok;
  focal_host_store_remove_ok = remove_ok;
#else
  (void) write_ok;
  (void) remove_ok;
#endif
}

extern "C" int FocalTestAstSize(void) {
  return (int) sizeof(FocalAst);
}

extern "C" int FocalTestRuntimeSize(void) {
  return (int) sizeof(FocalRuntime);
}

extern "C" const char* FocalTestProgramName(int slot) {
  return (slot >= 0 && slot < FOCAL_PROGRAM_COUNT && programs[slot].used) ? programs[slot].name : "";
}

extern "C" const char* FocalTestProgramSource(int slot) {
  return (slot >= 0 && slot < FOCAL_PROGRAM_COUNT && programs[slot].used) ? programs[slot].source : "";
}

extern "C" const char* FocalTestStoredProgramSource(void) {
#ifdef FOCAL_HOST_TEST
  return focal_host_stored_source;
#else
  return "";
#endif
}

extern "C" bool FocalTestExpandOperators(const char* input, char* out, int size) {
  if(input == NULL || out == NULL || size <= 0 || size > 0xFFFF || strlen(input) >= (usize) size) return false;
  focal_copy_text(out, (usize) size, input);
  return focal_expand_operator_names(out, (u16) size);
}

extern "C" void FocalTestSetAskValue(double value) {
#ifdef FOCAL_HOST_TEST
  focal_host_ask_value = value;
#else
  (void) value;
#endif
}

extern "C" void FocalTestSetAskCancelled(bool cancelled) {
#ifdef FOCAL_HOST_TEST
  focal_host_ask_cancelled = cancelled;
#else
  (void) cancelled;
#endif
}

extern "C" int FocalTestAskWaitCount(void) {
#ifdef FOCAL_HOST_TEST
  return focal_host_ask_wait_count;
#else
  return 0;
#endif
}

extern "C" bool FocalTestParseInputNumber(const char* text, double* value) {
  double parsed = 0.0;
  const bool ok = focal_parse_input_number(text, parsed);
  if(ok && value != NULL) *value = parsed;
  return ok;
}

extern "C" void FocalTestRun(int slot) {
  lcd.clear();
  (void) RunFocal(slot);
}

extern "C" int FocalTestRunStatus(int slot) {
  lcd.clear();
  return (int) RunFocal(slot);
}

extern "C" double FocalTestNumber(const char* name) {
  if(name == NULL || name[0] == 0) return 0.0;
  const int idx = focal_upper(name[0]) - 'A';
  return (idx < 0 || idx >= 26) ? 0.0 : focal_vars[idx];
}

extern "C" double FocalTestMkX(void) {
  return mk61_ref::host_get_stack(mk61_ref::Kind::X);
}

extern "C" bool FocalTestWriteMkX(double value) {
  const mk61_ref::Ref ref = {mk61_ref::Kind::X, 0};
  return mk61_ref::write(ref, value);
}

extern "C" double FocalTestMkRegister(int reg) {
  return reg >= 0 && reg < 16 ? mk61_ref::host_get_register((u8) reg) : 0.0;
}

extern "C" void FocalTestSetRfEnabled(bool enabled) {
  mk61_ref::host_set_rf_enabled(enabled);
}

extern "C" const char* FocalTestLcdLine(int row) {
  return lcd.line((u8) row);
}

extern "C" void FocalTestDrawNewEditor(const char* source, int cursor) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  u16 view_top = focal_line_start_for_cursor(source, safe_cursor);
  focal_editor_ensure_cursor_visible(source, len, safe_cursor, view_top);
  draw_focal_editor(source, len, safe_cursor, view_top, FOCAL_PROGRAM_COUNT);
}

extern "C" void FocalTestDrawNewEditorSms(const char* source, int cursor) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  u16 view_top = focal_line_start_for_cursor(source, safe_cursor);
  focal_editor_ensure_cursor_visible(source, len, safe_cursor, view_top);
  draw_focal_editor(source, len, safe_cursor, view_top, FOCAL_PROGRAM_COUNT, true);
}

extern "C" void FocalTestSetLcdRows(int rows) {
  lcd.setRows((u8) rows);
}

extern "C" int FocalTestEnsureViewTop(const char* source, int cursor, int view_top) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  u16 safe_view_top = (view_top < 0) ? 0 : (u16) view_top;
  focal_editor_ensure_cursor_visible(source, len, safe_cursor, safe_view_top);
  return safe_view_top;
}

extern "C" void FocalTestDrawNewEditorAt(const char* source, int cursor, int view_top) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  u16 safe_view_top = (view_top < 0) ? 0 : (u16) view_top;
  focal_editor_ensure_cursor_visible(source, len, safe_cursor, safe_view_top);
  draw_focal_editor(source, len, safe_cursor, safe_view_top, FOCAL_PROGRAM_COUNT);
}

extern "C" int FocalTestMoveCursorLine(const char* source, int cursor, int delta) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  focal_editor_move_cursor_line(source, len, safe_cursor, delta);
  return safe_cursor;
}

extern "C" int FocalTestMoveCursorHorizontal(const char* source, int cursor, int delta) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  if(delta < 0) focal_editor_move_cursor_left(source, safe_cursor);
  else if(delta > 0) focal_editor_move_cursor_right(source, len, safe_cursor);
  return safe_cursor;
}

extern "C" int FocalTestMoveCursorLineKey(const char* source, int cursor, int key_code) {
  if(source == NULL) source = "";
  const u16 len = (u16) strlen(source);
  u16 safe_cursor = (cursor < 0) ? 0 : (u16) cursor;
  if(safe_cursor > len) safe_cursor = len;
  if(key_code == KEY_SHG_LEFT_PRESS) focal_editor_move_cursor_line(source, len, safe_cursor, -1);
  else if(key_code == KEY_SHG_RIGHT_PRESS) focal_editor_move_cursor_line(source, len, safe_cursor, 1);
  return safe_cursor;
}

extern "C" void FocalTestEditSequence(const int* keys, int count, char* out, int size) {
  if(out == NULL || size <= 0) return;

  char source[FOCAL_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  text_editor::Buffer editor;
  text_editor::init(editor, source, FOCAL_SOURCE_SIZE);

  for(int i = 0; i < count; i++) {
    const u32 now = millis();
    const i32 key_code = keys[i];
    if(key_code == KEY_CX &&
        (editor.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      text_editor::clear_current_line(editor.source, editor.len, editor.cursor, editor.capacity);
      editor.shift = text_editor::Shift::NONE;
      continue;
    }
    if((key_code == KEY_LEFT || key_code == KEY_LEFT_PRESS) &&
        (editor.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);
      editor.shift = text_editor::Shift::NONE;
      continue;
    }
    text_editor::handle_key(editor, FOCAL_EDITOR_KEYS, FOCAL_EDITOR_HOOKS, key_code, now);
  }

  bounded_string::copy(out, (usize) size, source);
}

extern "C" bool FocalTestApplyExprMacro(const char* input, int key_code, char* out, int size) {
  if(input == NULL || out == NULL || size <= 0 || strlen(input) >= FOCAL_SOURCE_SIZE) return false;
  char source[FOCAL_SOURCE_SIZE];
  focal_copy_text(source, sizeof(source), input);
  u16 len = (u16) strlen(source);
  u16 cursor = len;
  const bool applied = focal_editor_apply_expr_macro(source, len, cursor, FOCAL_SOURCE_SIZE, key_code);
  focal_copy_text(out, (usize) size, source);
  return applied;
}
#endif

#endif
