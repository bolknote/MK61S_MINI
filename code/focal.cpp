#ifdef FOCAL_HOST_TEST
#include "rust_types.h"
#include "focal.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if MK61_ENABLE_FOCAL
static const int KEY_LEFT = 34;
static const int KEY_RIGHT = 24;
static const int KEY_OK = 29;
static const int KEY_ESC = 39;
static const int KEY_K = 37;
static const int KEY_ALPHA = KEY_K + 1;
static const int KEY_DEGREE = 4;
static const int KEY_RADIAN = 14;
static const int KEY_PP = 25;
static const int KEY_xP = 27;
static const int KEY_RET = 31;
static const int KEY_FRW = 32;
static const int KEY_BKW = 33;
static const int KEY_SHG_RIGHT_PRESS = KEY_BKW;
static const int KEY_SHG_LEFT_PRESS = KEY_FRW;
static const int KEY_LEFT_PRESS = KEY_LEFT;
static const int KEY_RIGHT_PRESS = KEY_RIGHT;
static const int KEY_OK_PRESS = KEY_OK;
static const int KEY_ESC_PRESS = KEY_ESC;

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
  void debounce_init(void) {}
  isize scan_and_debounced(void) { return 0; }
  i32 get_key(key_state) { return -1; }
  i32 get_key_wait(void) { return KEY_OK; }
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

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

#include "mk_math.hpp"

#ifdef FOCAL_HOST_TEST
#define TEXT_EDITOR_HOST_TEST
#endif
#include "text_editor.hpp"
#ifndef FOCAL_HOST_TEST
#include "language_workspace.hpp"
#endif

#if MK61_ENABLE_FOCAL

using namespace kbd;

extern MK61Display lcd;
#ifndef FOCAL_HOST_TEST
extern void idle_main_process(void);
#endif

#ifdef FOCAL_HOST_TEST
static constexpr int FOCAL_PROGRAM_COUNT       = 8;
#else
static constexpr int FOCAL_PROGRAM_COUNT       = 1;
#endif
static constexpr int FOCAL_SOURCE_SIZE         = 640;
static constexpr int FOCAL_LINE_TEXT_SIZE      = 80;
static constexpr int FOCAL_LINE_BUFFER_SIZE    = 128;
static constexpr int FOCAL_MAX_LINES           = 80;
static constexpr int FOCAL_NAME_SIZE           = 16;
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
  RETURNED,
  ERROR
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
  char operand[FOCAL_LINE_TEXT_SIZE];
};

struct FocalAst {
  bool ok;
  char error[17];
  FocalLine lines[FOCAL_MAX_LINES];
  i16 line_count;
};

struct FocalProgram {
  bool used;
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
  bool focal_var_set[26];
  i8 NextFocal;
  char focal_last_error[17];
};

#ifdef FOCAL_HOST_TEST
static FocalRuntime focal_runtime_storage;
static FocalRuntime& focal_runtime(void) {
  return focal_runtime_storage;
}
#else
static_assert(sizeof(FocalRuntime) <= language_workspace::SIZE, "FOCAL runtime does not fit language workspace");
static FocalRuntime& focal_runtime(void) {
  void* memory = language_workspace::acquire(language_workspace::Owner::FOCAL, sizeof(FocalRuntime));
  return *((FocalRuntime*) memory);
}
#endif

#define programs         (focal_runtime().programs)
#define focal_ast        (focal_runtime().focal_ast)
#define focal_vars       (focal_runtime().focal_vars)
#define focal_var_set    (focal_runtime().focal_var_set)
#define NextFocal        (focal_runtime().NextFocal)
#define focal_last_error (focal_runtime().focal_last_error)
#ifdef FOCAL_HOST_TEST
static u32 focal_random_state = 0x3B6B120EUL;
static double focal_host_ask_value = 0.0;
#endif

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
  Serial.print(line.operand);
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

static const char* const FOCAL_key_text[40] = {
  NULL, NULL, "*", "/", NULL,
  "^", NULL, "+", "-", NULL,
  NULL, "3", "6", "9", NULL,
  ".", "2", "5", "8", NULL,
  "0", "1", "4", "7", NULL,
  " ", NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL
};

static const char* const FOCAL_Kshift_key_text[40] = {
  NULL, NULL, NULL, NULL, NULL,
  NULL, "\"", "=", NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, ")",
  ",", NULL, NULL, NULL, NULL,
  "!", NULL, NULL, NULL, "(",
  NULL, NULL, NULL, NULL, NULL
};

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

static void focal_copy_text(char* dst, usize dst_size, const char* src) {
  if(dst_size == 0) return;
  if(src == NULL) src = "";
  strncpy(dst, src, dst_size - 1);
  dst[dst_size - 1] = 0;
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
  while(begin < end && focal_is_space(*begin)) begin++;
  while(end > begin && focal_is_space(*(end - 1))) end--;
  const usize len = (usize) (end - begin);
  const usize copy_len = (len < dst_size - 1) ? len : dst_size - 1;
  if(dst_size == 0) return;
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
  focal_copy_text(focal_ast.error, sizeof(focal_ast.error), error);
  focal_message_i18n(error, focal_error_ru_text(error), "FOCAL", "ФОКАЛ");
  return false;
}

static bool focal_runtime_interrupted(void) {
#ifndef FOCAL_HOST_TEST
  idle_main_process();
  kbd::scan_and_debounced();
  const i32 key = kbd::last_key();
  if(key == KEY_ESC || key == KEY_ESC_PRESS) {
    (void) kbd::get_key();
    kbd::clear_hold_key();
    focal_message_i18n("FOCAL stopped", "ФОКАЛ стоп", "ESC", "ESC");
    return true;
  }
#endif
  return false;
}

static void focal_clear_vars(void) {
  memset(focal_vars, 0, sizeof(focal_vars));
  memset(focal_var_set, 0, sizeof(focal_var_set));
}

static void focal_ast_reset(FocalAst& ast) {
  memset(&ast, 0, sizeof(ast));
  ast.ok = true;
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
  char word[12];
  u8 len = 0;
  while(focal_is_alpha(*p) && len < sizeof(word) - 1) word[len++] = focal_upper(*p++);
  while(focal_is_alpha(*p)) p++;
  word[len] = 0;
  if(len == 0) return false;

  if(focal_streq(word, "A") || focal_streq(word, "ASK")) op = FocalOp::ASK;
  else if(focal_streq(word, "B") || focal_streq(word, "BRANCH")) op = FocalOp::BRANCH;
  else if(focal_streq(word, "C") || focal_streq(word, "COMMENT")) op = FocalOp::COMMENT;
  else if(focal_streq(word, "D") || focal_streq(word, "DO")) op = FocalOp::DO;
  else if(focal_streq(word, "E") || focal_streq(word, "EXIT")) op = FocalOp::EXIT;
  else if(focal_streq(word, "F") || focal_streq(word, "FOR")) op = FocalOp::FOR;
  else if(focal_streq(word, "G") || focal_streq(word, "GOTO")) op = FocalOp::GOTO;
  else if(focal_streq(word, "P") || focal_streq(word, "PRINT")) op = FocalOp::PRINT;
  else if(focal_streq(word, "R") || focal_streq(word, "RETURN")) op = FocalOp::RETURN;
  else if(focal_streq(word, "S") || focal_streq(word, "SET")) op = FocalOp::SET;
  else return false;
  return true;
}

static bool focal_parse_statement_text(const char* text, FocalLine& line) {
  const char* p = text;
  if(!focal_parse_operator(p, line.op)) return false;
  p = focal_skip_spaces(p);
  focal_copy_text(line.operand, sizeof(line.operand), p);
  return true;
}

static bool focal_parse_line_text(const char* text, FocalLine& line) {
  const char* p = text;
  if(!focal_parse_address(p, line.number)) return false;
  p = focal_skip_spaces(p);
  return focal_parse_statement_text(p, line);
}

static bool focal_validate_statement(const FocalLine& line) {
  const char* p = focal_skip_spaces(line.operand);
  switch(line.op) {
    case FocalOp::ASK:
      return focal_is_alpha(*p) && !focal_is_alpha(*(p + 1));
    case FocalOp::SET:
      if(!focal_is_alpha(*p)) return false;
      p++;
      p = focal_skip_spaces(p);
      return *p == '=';
    case FocalOp::FOR:
      if(!focal_is_alpha(*p)) return false;
      return strchr(line.operand, '=') != NULL && strchr(line.operand, ';') != NULL;
    case FocalOp::DO:
    case FocalOp::GOTO: {
      FocalAddress address;
      return focal_parse_address(p, address);
    }
    case FocalOp::BRANCH:
      return *p == '(';
    case FocalOp::COMMENT:
    case FocalOp::EXIT:
    case FocalOp::PRINT:
    case FocalOp::RETURN:
    case FocalOp::NOP:
      return true;
  }
  return false;
}

static bool focal_compile_source(const char* source, FocalAst& ast) {
  focal_ast_reset(ast);
  if(source == NULL) return focal_error("SYNTAX?");

  const char* cursor = source;
  while(*cursor != 0) {
    while(*cursor == '\n' || *cursor == '\r') cursor++;
    if(*cursor == 0) break;

    const char* line_begin = cursor;
    while(*cursor != 0 && *cursor != '\n' && *cursor != '\r') cursor++;
    const char* line_end = cursor;

    char line_text[FOCAL_LINE_BUFFER_SIZE];
    focal_copy_trim(line_text, sizeof(line_text), line_begin, line_end);
    if(line_text[0] == 0) continue;

    if(ast.line_count >= FOCAL_MAX_LINES) return focal_error("FULL?");

    FocalLine& line = ast.lines[ast.line_count];
    memset(&line, 0, sizeof(line));
    if(!focal_parse_line_text(line_text, line)) return focal_error("LINE?");
    if(!focal_validate_statement(line)) return focal_error("SYNTAX?");
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

  ast.ok = true;
  ast.error[0] = 0;
  focal_last_error[0] = 0;
  return true;
}

struct ExprParser {
  const char* p;
  const char* end;
  bool ok;
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

static double expr_parse_additive(ExprParser& parser);
#ifndef FOCAL_HOST_TEST
static double focal_read_mk_x(void);
#endif

static double focal_rnd(void) {
#ifdef FOCAL_HOST_TEST
  focal_random_state = focal_random_state * 1103515245UL + 12345UL;
  return (double) ((focal_random_state >> 8) & 0x00FFFFFFUL) / 16777216.0;
#else
  hidden_press_key(sw::K);
  hidden_press_key(sw::Bx);
  return focal_read_mk_x();
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

  if(focal_streq(name, "PI")) return 3.14159265358979323846;
  if(len == 1) {
    const int idx = name[0] - 'A';
    if(idx < 0 || idx >= 26) {
      expr_set_error(parser, "VAR?");
      return 0.0;
    }
    return focal_vars[idx];
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
    return focal_rnd();
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

  if(focal_streq(name, "SIN")) return mk_math::sin(a);
  if(focal_streq(name, "COS")) return mk_math::cos(a);
  if(focal_streq(name, "TG")) return mk_math::tan(a);
  if(focal_streq(name, "ASIN")) return mk_math::asin(a);
  if(focal_streq(name, "ACOS")) return mk_math::acos(a);
  if(focal_streq(name, "ATG")) return mk_math::atan(a);
  if(focal_streq(name, "LN")) return mk_math::ln(a);
  if(focal_streq(name, "LG")) return mk_math::log10(a);
  if(focal_streq(name, "EXP")) return mk_math::exp(a);
  if(focal_streq(name, "SQRT")) return mk_math::sqrt(a);
  if(focal_streq(name, "ABS")) return mk_math::fabs(a);
  if(focal_streq(name, "INT")) return mk_math::floor(a);
  if(focal_streq(name, "FRAC")) return mk_math::frac(a);
  if(focal_streq(name, "ROUND")) return mk_math::round_half(a);
  if(focal_streq(name, "SGN")) return (a > 0.0) ? 1.0 : ((a < 0.0) ? -1.0 : 0.0);
  if(focal_streq(name, "MAX")) return (a > b) ? a : b;

  expr_set_error(parser, "FUNC?");
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

  const char* after = NULL;
  const double value = mk_math::strtod(parser.p, &after);
  if(after != NULL && after > parser.p && after <= parser.end) {
    parser.p = after;
    return value;
  }

  expr_set_error(parser, "SYNTAX?");
  return 0.0;
}

static double expr_parse_unary(ExprParser& parser) {
  expr_skip_spaces(parser);
  if(expr_match(parser, '+')) return expr_parse_unary(parser);
  if(expr_match(parser, '-')) return -expr_parse_unary(parser);
  return expr_parse_primary(parser);
}

static double expr_parse_power(ExprParser& parser) {
  double left = expr_parse_unary(parser);
  expr_skip_spaces(parser);
  if(expr_match(parser, '^')) {
    const double right = expr_parse_power(parser);
    left = mk_math::pow(left, right);
  }
  return left;
}

static double expr_parse_multiplicative(ExprParser& parser) {
  double left = expr_parse_power(parser);
  while(parser.ok) {
    if(expr_match(parser, '*')) {
      left *= expr_parse_power(parser);
    } else if(expr_match(parser, '/')) {
      const double right = expr_parse_power(parser);
      if(mk_math::fabs(right) < 1e-14) {
        expr_set_error(parser, "MATH?");
        return 0.0;
      }
      left /= right;
    } else {
      break;
    }
  }
  return left;
}

static double expr_parse_additive(ExprParser& parser) {
  double left = expr_parse_multiplicative(parser);
  while(parser.ok) {
    if(expr_match(parser, '+')) left += expr_parse_multiplicative(parser);
    else if(expr_match(parser, '-')) left -= expr_parse_multiplicative(parser);
    else break;
  }
  return left;
}

static bool focal_eval_expr_range(const char* begin, const char* end, double& value) {
  char buffer[FOCAL_EXPR_BUFFER_SIZE];
  focal_copy_trim(buffer, sizeof(buffer), begin, end);
  if(buffer[0] == 0) return focal_error("SYNTAX?");

  ExprParser parser;
  parser.p = buffer;
  parser.end = buffer + strlen(buffer);
  parser.ok = true;
  parser.error[0] = 0;

  value = expr_parse_additive(parser);
  expr_skip_spaces(parser);
  if(parser.ok && parser.p != parser.end) expr_set_error(parser, "SYNTAX?");
  if(!parser.ok) return focal_error(parser.error[0] != 0 ? parser.error : "SYNTAX?");
  return true;
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

static bool focal_parse_var_assignment(const char* text, int& var_index, const char*& expr_begin) {
  const char* p = focal_skip_spaces(text);
  if(!focal_is_alpha(*p)) return false;
  var_index = focal_upper(*p++) - 'A';
  p = focal_skip_spaces(p);
  if(*p != '=') return false;
  expr_begin = p + 1;
  return var_index >= 0 && var_index < 26;
}

static double focal_read_number_from_keyboard(char var_name) {
#ifdef FOCAL_HOST_TEST
  (void) var_name;
  return focal_host_ask_value;
#else
  char buffer[17];
  char prompt[17];
  memset(buffer, 0, sizeof(buffer));
  u8 len = 0;
  snprintf(prompt, sizeof(prompt), focal_language_is_ru() ? "ВВОД %c" : "ASK %c", var_name);
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
    if(key == KEY_OK || key == KEY_OK_PRESS || key == KEY_ESC || key == KEY_ESC_PRESS) break;
    if(key == 0) {
      len = 0;
      buffer[0] = 0;
      continue;
    }
    if(key == KEY_DEGREE && len > 0) {
      buffer[--len] = 0;
      continue;
    }
    if(key >= 0 && key < 40) {
      const char* text = FOCAL_key_text[key];
      if(text == NULL || text[1] != 0) continue;
      const char ch = text[0];
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-' || ch == '+') {
        if(len < sizeof(buffer) - 1) {
          buffer[len++] = ch;
          buffer[len] = 0;
        }
      }
    }
  }
  const double value = mk_math::atof(buffer);
  #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
    focal_trace_header();
    Serial.print("ASK ");
    Serial.print(var_name);
    Serial.print("=");
    Serial.println(value, 10);
    Serial.flush();
  #endif
  return value;
#endif
}

static FocalFlow focal_flow(FocalFlowKind kind, i16 pc) {
  FocalFlow flow;
  flow.kind = kind;
  flow.pc = pc;
  return flow;
}

#ifndef FOCAL_HOST_TEST
static const char focal_display_symbols[16] = {
    'O', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', 'L', 'C', G_RUS, 'E', ' '
};

static double focal_parse_mk61_display_number(const char* value) {
  char buffer[20];
  char* out = buffer;
  if(value[0] == '-') *out++ = '-';
  for(int i = 1; i <= 9; i++) {
    if(value[i] == ' ') continue;
    *out++ = (value[i] == 'O') ? '0' : value[i];
  }
  *out++ = 'e';
  *out++ = (value[11] == '-') ? '-' : '+';
  *out++ = (value[12] == 'O') ? '0' : value[12];
  *out++ = (value[13] == 'O') ? '0' : value[13];
  *out = 0;
  return mk_math::atof(buffer);
}

static double focal_read_mk_x(void) {
  char value[15];
  value[14] = 0;
  read_stack_register(stack::X, value, focal_display_symbols);
  return focal_parse_mk61_display_number(value);
}
#endif

static bool focal_execute_statement(const FocalLine& line, i16 current_pc, int depth, FocalFlow& flow);

static bool focal_execute_inline_statement(const char* text, i16 current_pc, int depth, FocalFlow& flow) {
  FocalLine line;
  memset(&line, 0, sizeof(line));
  line.number.major = 0;
  line.number.minor = 0;
  line.number.has_minor = true;
  if(!focal_parse_statement_text(text, line) || !focal_validate_statement(line)) {
    flow = focal_flow(FocalFlowKind::ERROR, current_pc);
    return focal_error("SYNTAX?");
  }
  return focal_execute_statement(line, current_pc, depth, flow);
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

static bool focal_execute_set(const char* operand) {
  int var_index = -1;
  const char* expr_begin = NULL;
  if(!focal_parse_var_assignment(operand, var_index, expr_begin)) return focal_error("SYNTAX?");
  double value = 0.0;
  if(!focal_eval_expr_text(expr_begin, value)) return false;
  focal_vars[var_index] = value;
  focal_var_set[var_index] = true;
  #if defined(MK61_FOCAL_TRACE) && !defined(FOCAL_HOST_TEST)
    focal_trace_header();
    Serial.print("SET ");
    Serial.write((char) ('A' + var_index));
    Serial.print("=");
    Serial.println(value, 10);
    Serial.flush();
  #endif
  return true;
}

static bool focal_execute_ask(const char* operand) {
  const char* p = focal_skip_spaces(operand);
  if(!focal_is_alpha(*p)) return focal_error("VAR?");
  const int var_index = focal_upper(*p) - 'A';
  if(var_index < 0 || var_index >= 26) return focal_error("VAR?");
  focal_vars[var_index] = focal_read_number_from_keyboard((char) ('A' + var_index));
  focal_var_set[var_index] = true;
  return true;
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
        begin++;
        const char* quote = begin;
        while(quote < item_end && *quote != '"') quote++;
        if(quote >= item_end) return focal_error("SYNTAX?");
        char text[FOCAL_PRINT_BUFFER_SIZE];
        focal_copy_trim(text, sizeof(text), begin, quote);
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
    if(local_flow.kind == FocalFlowKind::STOP || local_flow.kind == FocalFlowKind::ERROR) {
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

  if(mk_math::fabs(step_value) < 1e-14) {
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
  for(double value = start_value; (step_value > 0.0) ? (value <= end_value) : (value >= end_value); value += step_value) {
    focal_vars[var_index] = value;
    focal_var_set[var_index] = true;
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
  }

  flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
  return true;
}

static bool focal_execute_statement(const FocalLine& line, i16 current_pc, int depth, FocalFlow& flow) {
  focal_trace_line("EXEC", current_pc, line);
  if(focal_runtime_interrupted()) {
    flow = focal_flow(FocalFlowKind::STOP, current_pc);
    return true;
  }
  if(depth >= FOCAL_CALL_DEPTH) {
    flow = focal_flow(FocalFlowKind::ERROR, current_pc);
    return focal_error("STACK?");
  }

  switch(line.op) {
    case FocalOp::NOP:
    case FocalOp::COMMENT:
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    case FocalOp::ASK:
      if(!focal_execute_ask(line.operand)) {
        flow = focal_flow(FocalFlowKind::ERROR, current_pc);
        return false;
      }
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    case FocalOp::SET:
      if(!focal_execute_set(line.operand)) {
        flow = focal_flow(FocalFlowKind::ERROR, current_pc);
        return false;
      }
      flow = focal_flow(FocalFlowKind::NEXT, (i16) (current_pc + 1));
      return true;
    case FocalOp::PRINT:
      if(!focal_execute_print(line.operand)) {
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
      return focal_execute_goto(line.operand, flow);
    case FocalOp::BRANCH:
      return focal_execute_branch(line.operand, flow);
    case FocalOp::DO:
      return focal_execute_do(line.operand, current_pc, depth, flow);
    case FocalOp::FOR:
      return focal_execute_for(line.operand, current_pc, depth, flow);
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

#ifndef FOCAL_HOST_TEST
static void focal_release_program_slot(int slot) {
  if(slot < 0 || slot >= FOCAL_PROGRAM_COUNT) return;
  memset(&programs[slot], 0, sizeof(programs[slot]));
}

static int focal_alloc_program_slot(const char* name) {
  const int existing = find_program_by_name(name);
  if(existing >= 0) return existing;

  const int free_slot = find_free_program();
  if(free_slot >= 0) return free_slot;

  const int slot = (NextFocal >= 0 && NextFocal < FOCAL_PROGRAM_COUNT) ? NextFocal : 0;
  focal_release_program_slot(slot);
  return slot;
}

static bool focal_store_name_is_valid(const char* name) {
  return name != NULL && name[0] != 0 && strlen(name) < program_store::NAME_SIZE;
}

static int load_focal_program_from_store(const char* name, bool compile = true) {
  if(!focal_store_name_is_valid(name)) return -1;

  focal_trace_string("LOAD name=", name);
  char source[FOCAL_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  u16 len = 0;
  if(!program_store::read(program_store::ProgramType::FOCAL, name, (u8*) source, FOCAL_SOURCE_SIZE - 1, &len)) return -1;
  source[len] = 0;
  focal_trace_int("LOAD len=", len);
  focal_trace_string("LOAD source=", source);

  if(compile && !focal_compile_source(source, focal_ast)) return -1;
  if(compile) focal_trace_int("LOAD compiled lines=", focal_ast.line_count);

  const int slot = focal_alloc_program_slot(name);
  focal_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  focal_copy_text(programs[slot].name, sizeof(programs[slot].name), name);
  programs[slot].used = true;
  NextFocal = (i8) slot;
  return slot;
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
  char line[17];
  char display_name[24];
  focal_display_program_name(program.name, display_name, sizeof(display_name));
  snprintf(line, sizeof(line), "%s %d", display_name, (int) focal_ast.line_count);
  focal_message_i18n("FOCAL compiled", "ФОКАЛ готов", line, line);
  delay(700);
}

bool CompileFocal(char* program) {
  const int slot = find_free_program();
  if(slot < 0) return focal_error("FULL?");

  if(!focal_compile_source(program, focal_ast)) {
    memset(&programs[slot], 0, sizeof(programs[slot]));
    return false;
  }

  focal_copy_text(programs[slot].source, sizeof(programs[slot].source), program);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  focal_program_default_name(slot, programs[slot].name, sizeof(programs[slot].name));
  programs[slot].used = true;
  NextFocal = (i8) slot;
#ifndef FOCAL_HOST_TEST
  program_store::write(program_store::ProgramType::FOCAL, programs[slot].name, (const u8*) programs[slot].source, programs[slot].source_len);
#endif
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

void RunFocal(int FocalN) {
  if(!compile_program_slot(FocalN)) return;
  focal_trace_int("RUN slot=", FocalN);
  focal_trace_int("RUN lines=", focal_ast.line_count);
  for(i16 i = 0; i < focal_ast.line_count; i++) {
    focal_trace_line("LINE", i, focal_ast.lines[i]);
  }

  i16 pc = 0;
  while(pc >= 0 && pc < focal_ast.line_count) {
    FocalFlow flow = focal_flow(FocalFlowKind::NEXT, (i16) (pc + 1));
    if(!focal_execute_statement(focal_ast.lines[pc], pc, 0, flow)) break;
    focal_trace_flow(flow);
    if(flow.kind == FocalFlowKind::NEXT || flow.kind == FocalFlowKind::JUMP) {
      pc = flow.pc;
      continue;
    }
    if(flow.kind == FocalFlowKind::RETURNED) {
      focal_error("RETURN?");
      break;
    }
    break;
  }
  focal_trace_text("RUN end");
}

bool RunFocalProgram(const char* name) {
#ifndef FOCAL_HOST_TEST
  const int slot = load_focal_program_from_store(name);
#else
  const int slot = find_program_by_name(name);
#endif
  if(slot < 0) return false;
  RunFocal(slot);
  focal_wait_after_menu_run();
  return true;
}

bool FocalIsReady(void) {
  return focal_program_count() > 0;
}

void InitFocal(void) {
  memset(programs, 0, sizeof(programs));
  focal_ast_reset(focal_ast);
  focal_clear_vars();
  NextFocal = -1;
  focal_last_error[0] = 0;
#ifdef FOCAL_HOST_TEST
  focal_random_state = 0x3B6B120EUL;
#endif
}

static int next_used_program(int active, int delta, bool allow_new) {
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

static void draw_program_select(int active, bool allow_new) {
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

static int select_focal_program(bool allow_new) {
#ifndef FOCAL_HOST_TEST
  const int stored_count = program_store::count(program_store::ProgramType::FOCAL);
  if(stored_count <= 0 && !allow_new) {
    focal_message_i18n("FOCAL is empty", "ФОКАЛ пуст", "Press any key", "Любая клавиша");
    kbd::get_key_wait();
    return -1;
  }

  int active = (stored_count > 0) ? 0 : stored_count;
  while(true) {
    draw_program_select(active, allow_new);
    const i32 key = kbd::get_key_wait();
    switch(key) {
      case KEY_LEFT:
        if(allow_new) {
          active--;
          if(active < 0) active = stored_count;
        } else if(stored_count > 0) {
          active = (active <= 0) ? stored_count - 1 : active - 1;
        }
        break;
      case KEY_RIGHT:
        if(allow_new) {
          active++;
          if(active > stored_count) active = 0;
        } else if(stored_count > 0) {
          active = (active + 1) % stored_count;
        }
        break;
      case KEY_OK:
        if(allow_new && active == stored_count) {
          focal_wait_keys_released();
          return FOCAL_PROGRAM_COUNT;
        }
        {
          program_store::Entry entry;
          if(!program_store::entry(program_store::ProgramType::FOCAL, active, entry)) return -1;
          const int slot = load_focal_program_from_store(entry.name, !allow_new);
          focal_wait_keys_released();
          return slot;
        }
      case KEY_ESC:
        return -1;
    }
  }
#else
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

static bool focal_editor_move_cursor_left(const char* source, u16& cursor) {
  return text_editor::move_cursor_left(source, cursor);
}

static bool focal_editor_move_cursor_right(const char* source, u16 len, u16& cursor) {
  return text_editor::move_cursor_right(source, len, cursor);
}

static bool focal_editor_move_cursor_line(const char* source, u16 len, u16& cursor, int delta) {
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
  while(start < end && focal_is_space(source[start])) start++;
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
  if(key_code != 2 && key_code != 3 && key_code != 5) return false;

  u16 start = 0;
  u16 end = 0;
  if(!focal_find_expression_before_cursor(source, cursor, start, end)) return false;

  const bool simple = focal_segment_is_simple(&source[start], &source[end]);
  char expr[FOCAL_EXPR_BUFFER_SIZE];
  focal_copy_trim(expr, sizeof(expr), &source[start], &source[end]);

  char replacement[FOCAL_EXPR_BUFFER_SIZE + 8];
  if(key_code == 2) {
    snprintf(replacement, sizeof(replacement), simple ? "%s^2" : "(%s)^2", expr);
  } else if(key_code == 3) {
    snprintf(replacement, sizeof(replacement), simple ? "1/%s" : "1/(%s)", expr);
  } else {
    snprintf(replacement, sizeof(replacement), simple ? "10^%s" : "10^(%s)", expr);
  }
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
  switch(key_code) {
    case 15:         return leading_space ? " ASK " : "ASK ";
    case 10:         return leading_space ? " BRANCH " : "BRANCH ";
    case 5:          return leading_space ? " COMMENT " : "COMMENT ";
    case 0:          return leading_space ? " DO " : "DO ";
    case 1:          return leading_space ? " EXIT" : "EXIT";
    case 2:          return leading_space ? " FOR " : "FOR ";
    case KEY_DEGREE: return leading_space ? " GOTO " : "GOTO ";
    case KEY_RADIAN: return leading_space ? " PRINT " : "PRINT ";
    case KEY_xP:     return leading_space ? " SET " : "SET ";
    case KEY_RET:    return leading_space ? " RETURN" : "RETURN";
    default: break;
  }
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
        if(key_code == 15 && !address.has_minor) return FOCAL_key_text[key_code];
        const char* statement = focal_statement_insert_text(key_code, true);
        if(statement != NULL) return statement;
      }
      return FOCAL_key_text[key_code];
    case FocalEditShift::ALPHA:
      return NULL;
    case FocalEditShift::K: {
      FocalAddress address;
      if(focal_cursor_after_line_address(source, cursor, &address)) {
        const char* statement = focal_statement_insert_text(key_code, true);
        if(statement != NULL) return statement;
      } else {
        const char* statement = focal_statement_insert_text(key_code);
        if(statement != NULL) return statement;
      }
      return FOCAL_Kshift_key_text[key_code];
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

static void draw_focal_name_editor(const char* name, bool sms_cursor) {
  char line[17];
  snprintf(line, sizeof(line), ">%s", name);
  focal_message_i18n("FOCAL name", "Имя ФОКАЛ", line, line);
  if(sms_cursor) {
    MK61DisplayUpdate update(lcd);
    const u8 pos = (u8) strlen(line);
    lcd.setCursor(pos < 16 ? pos : 15, 1);
    lcd.write(SMS_CURSOR_ASCII);
  }
}

static bool focal_name_insert_char(char* name, u8& len, char ch) {
  if(ch == ' ') return false;
  if(len >= FOCAL_NAME_SIZE - 1) return false;
  name[len++] = focal_upper(ch);
  name[len] = 0;
  return true;
}

static bool focal_name_sms_tap(char* name, u8& len, FocalSmsState& sms, i32 key_code, u32 now) {
  const char* letters = focal_sms_letters_for_key(key_code);
  if(letters == NULL || letters[0] == 0) {
    focal_sms_reset(sms);
    return false;
  }

  if(sms.active && sms.key_code == key_code && len > 0) {
    const usize count = strlen(letters);
    sms.index = (u8) ((sms.index + 1) % count);
    name[len - 1] = letters[sms.index];
    sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
    return true;
  }

  sms.active = true;
  sms.key_code = key_code;
  sms.index = 0;
  sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
  return focal_name_insert_char(name, len, letters[0]);
}

static bool focal_input_program_name(char* name, usize size) {
  if(size == 0) return false;
  name[size - 1] = 0;
  u8 len = (u8) strlen(name);
  if(len >= size) len = (u8) size - 1;
  FocalSmsState sms = {};
  FocalEditShift shift = FocalEditShift::NONE;

  while(true) {
    const u32 now = millis();
    if(sms.active && now >= sms.deadline_ms) focal_sms_reset(sms);
    draw_focal_name_editor(name, sms.active);
    const i32 key = kbd::get_key_wait();
    const bool shifted_key = shift != FocalEditShift::NONE;

    if(!shifted_key && (key == KEY_K || key == KEY_ALPHA)) {
      shift = (key == KEY_K) ? FocalEditShift::K : FocalEditShift::ALPHA;
      focal_sms_reset(sms);
      continue;
    }
    if(!shifted_key && (key == KEY_OK || key == KEY_OK_PRESS)) return len > 0;
    if(!shifted_key && (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if(!shifted_key && key == KEY_DEGREE) {
      focal_sms_reset(sms);
      if(len > 0) name[--len] = 0;
      continue;
    }
    if(!shifted_key && key == 0) {
      focal_sms_reset(sms);
      len = 0;
      name[0] = 0;
      continue;
    }

    const int digit = focal_digit_from_key(key);
    if(shift == FocalEditShift::ALPHA && digit >= 0) {
      const char* symbol = focal_symbol_for_digit_key(key);
      if(symbol != NULL && symbol[0] != 0) focal_name_insert_char(name, len, symbol[0]);
      shift = FocalEditShift::NONE;
      focal_sms_reset(sms);
      continue;
    }
    if(focal_sms_key_is_letters(key)) {
      focal_name_sms_tap(name, len, sms, key, now);
      shift = FocalEditShift::NONE;
      continue;
    }
    if(focal_sms_key_is_space(key)) {
      focal_sms_reset(sms);
      focal_name_insert_char(name, len, ' ');
      shift = FocalEditShift::NONE;
      continue;
    }
    if(digit == 0 || key == KEY_PP) {
      focal_sms_reset(sms);
      focal_name_insert_char(name, len, '0');
      shift = FocalEditShift::NONE;
      continue;
    }
    if(digit == 1) {
      focal_sms_reset(sms);
      focal_name_insert_char(name, len, '1');
      shift = FocalEditShift::NONE;
      continue;
    }

    shift = FocalEditShift::NONE;
  }
}

static bool store_edited_program(int slot, char* source, const char* store_name) {
  char old_name[FOCAL_NAME_SIZE] = "";
  if(slot >= 0 && slot < FOCAL_PROGRAM_COUNT && programs[slot].used) {
    focal_copy_text(old_name, sizeof(old_name), programs[slot].name);
  }

  if(slot == FOCAL_PROGRAM_COUNT) {
#ifdef FOCAL_HOST_TEST
    slot = find_free_program();
    if(slot < 0) return focal_error("FULL?");
#else
    slot = focal_alloc_program_slot(store_name);
#endif
  }
  if(!focal_compile_source(source, focal_ast)) return false;

  focal_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  if(store_name != NULL && store_name[0] != 0) focal_copy_text(programs[slot].name, sizeof(programs[slot].name), store_name);
  else focal_program_default_name(slot, programs[slot].name, sizeof(programs[slot].name));
  programs[slot].used = true;
  NextFocal = (i8) slot;
#ifndef FOCAL_HOST_TEST
  if(!program_store::write(program_store::ProgramType::FOCAL, programs[slot].name, (const u8*) programs[slot].source, programs[slot].source_len)) {
    return focal_error("FULL?");
  }
  if(old_name[0] != 0 && !focal_streq(old_name, programs[slot].name)) {
    program_store::remove(program_store::ProgramType::FOCAL, old_name);
  }
#endif
  display_focal_ok(programs[slot]);
  return true;
}

static void EditFocalSlot(int slot) {
  char source[FOCAL_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  if(slot < FOCAL_PROGRAM_COUNT && programs[slot].used) focal_copy_text(source, sizeof(source), programs[slot].source);

  text_editor::Buffer editor;
  text_editor::init(editor, source, FOCAL_SOURCE_SIZE);
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
    const text_editor::KeyResult result = text_editor::handle_key(editor, FOCAL_EDITOR_KEYS, FOCAL_EDITOR_HOOKS, key_code, now);
    dirty = result != text_editor::KeyResult::NONE;

    if(result == text_editor::KeyResult::SAVE) {
      lcd.cursorOff();
      if(!focal_confirm_save()) return;
      char name[FOCAL_NAME_SIZE];
      memset(name, 0, sizeof(name));
      if(slot < FOCAL_PROGRAM_COUNT && programs[slot].used) focal_copy_text(name, sizeof(name), programs[slot].name);
      else focal_program_default_name(find_free_program() < 0 ? 0 : find_free_program(), name, sizeof(name));
      if(focal_input_program_name(name, sizeof(name)) && store_edited_program(slot, source, name)) return;
      kbd::debounce_init();
      return;
    }
  }
}

void EditFocal(void) {
  const int slot = select_focal_program(true);
  if(slot < 0) return;
  EditFocalSlot(slot);
}

bool EditFocalProgram(const char* name) {
#ifndef FOCAL_HOST_TEST
  const int slot = load_focal_program_from_store(name, false);
  if(slot < 0) return false;
  EditFocalSlot(slot);
  return true;
#else
  (void) name;
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
}

extern "C" bool FocalTestCompile(const char* source) {
  return focal_compile_source(source, focal_ast);
}

extern "C" const char* FocalTestError(void) {
  return focal_last_error;
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

extern "C" void FocalTestSetAskValue(double value) {
#ifdef FOCAL_HOST_TEST
  focal_host_ask_value = value;
#else
  (void) value;
#endif
}

extern "C" void FocalTestRun(int slot) {
  lcd.clear();
  RunFocal(slot);
}

extern "C" double FocalTestNumber(const char* name) {
  if(name == NULL || name[0] == 0) return 0.0;
  const int idx = focal_upper(name[0]) - 'A';
  return (idx < 0 || idx >= 26) ? 0.0 : focal_vars[idx];
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
    text_editor::handle_key(editor, FOCAL_EDITOR_KEYS, FOCAL_EDITOR_HOOKS, key_code, now);
  }

  strncpy(out, source, (usize) size - 1);
  out[size - 1] = 0;
}
#endif

#endif
