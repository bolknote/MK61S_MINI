#ifdef TINYBASIC_HOST_TEST
#include "rust_types.h"
#include "tinybasic.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if MK61_ENABLE_TINYBASIC
static const int KEY_LEFT = 34;
static const int KEY_RIGHT = 24;
static const int KEY_OK = 29;
static const int KEY_ESC = 39;
static const int KEY_K = 37;
static const int KEY_ALPHA = KEY_K + 1;
static const int KEY_DEGREE = 4;
static const int KEY_PP = 25;
static const int KEY_RET = 31;
static const int KEY_FRW = 32;
static const int KEY_BKW = 33;
static const int KEY_SHG_RIGHT_PRESS = KEY_BKW;
static const int KEY_SHG_LEFT_PRESS = KEY_FRW;
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
    bool supportsCursor(void) const { return false; }
    void write(u8 value) {
      if(x < 16 && y < MAX_ROWS) lines[y][x++] = (char) value;
    }
    void print(const char* text) {
      if(text == NULL) return;
      while(*text != 0) write((u8) *text++);
    }
    void print(char value) { write((u8) value); }
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
  bool is_key_pressed(i32) { return false; }
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

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

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

#if MK61_ENABLE_TINYBASIC

using namespace kbd;

extern MK61Display lcd;
#ifndef TINYBASIC_HOST_TEST
extern void idle_main_process(void);
#endif

#ifdef TINYBASIC_HOST_TEST
static constexpr int TB_PROGRAM_COUNT = 8;
#else
static constexpr int TB_PROGRAM_COUNT = 1;
#endif
static constexpr int TB_SOURCE_SIZE = 1024;
static constexpr int TB_MAX_LINES = 96;
static constexpr int TB_NAME_SIZE = 16;
static constexpr int TB_PRINT_BUFFER_SIZE = 96;
static constexpr int TB_CALL_DEPTH = 8;
static constexpr int TB_FOR_DEPTH = 8;

enum class TbFlowKind : u8 {
  NEXT,
  JUMP,
  STOP,
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
  CMD_END,
  CMD_STOP
};

struct TbLine {
  i16 number;
  u16 offset;
  u16 len;
};

struct TbAst {
  bool ok;
  char error[17];
  const char* source;
  TbLine lines[TB_MAX_LINES];
  i16 line_count;
};

struct TbProgram {
  bool used;
  char name[TB_NAME_SIZE];
  char source[TB_SOURCE_SIZE];
  u16 source_len;
};

struct TbFlow {
  TbFlowKind kind;
  i16 pc;
};

struct TbForFrame {
  int var_index;
  double limit;
  i16 return_pc;
};

struct TbRunState {
  i16 call_stack[TB_CALL_DEPTH];
  i8 call_sp;
  TbForFrame for_stack[TB_FOR_DEPTH];
  i8 for_sp;
};

struct TbWord {
  char text[12];
  bool dotted;
  const char* end;
};

enum class TbTargetKind : u8 {
  VAR,
  MK_REF
};

struct TbTarget {
  TbTargetKind kind;
  int var_index;
  mk61_ref::Ref mk_ref;
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

#ifdef TINYBASIC_HOST_TEST
static TinyBasicRuntime tinybasic_runtime_storage;
static TinyBasicRuntime& tinybasic_runtime(void) {
  return tinybasic_runtime_storage;
}
#else
static_assert(sizeof(TinyBasicRuntime) <= language_workspace::SIZE, "TinyBASIC runtime does not fit language workspace");
static TinyBasicRuntime& tinybasic_runtime(void) {
  void* memory = language_workspace::acquire(language_workspace::Owner::TINYBASIC, sizeof(TinyBasicRuntime));
  return *((TinyBasicRuntime*) memory);
}
#endif

#define programs         (tinybasic_runtime().programs)
#define tb_ast           (tinybasic_runtime().tb_ast)
#define tb_vars          (tinybasic_runtime().tb_vars)
#define NextTinyBasic    (tinybasic_runtime().NextTinyBasic)
#define tb_last_error    (tinybasic_runtime().tb_last_error)
#define tb_pending_print (tinybasic_runtime().tb_pending_print)
#define tb_print_row     (tinybasic_runtime().tb_print_row)

static u32 tb_random_state = 0x3B6B120EUL;
#ifdef TINYBASIC_HOST_TEST
static double tb_host_input_value = 0.0;
#endif

static const char* const TB_key_text[40] = {
  NULL, NULL, "*", "/", NULL,
  "^", NULL, "+", "-", NULL,
  NULL, "3", "6", "9", NULL,
  ".", "2", "5", "8", NULL,
  "0", "1", "4", "7", NULL,
  " ", NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL
};

static const char* tinybasic_kshift_text(i32 key_code) {
  switch(key_code) {
    case KEY_OK:     return ":";
    case KEY_RET:    return ";";
    case KEY_PP:     return ",";
    case KEY_LEFT:   return "(";
    case KEY_RIGHT:  return ")";
    case 6:          return "\"";
    case 7:          return "=";
    case 15:         return "'";
    case 30:         return "!";
    case 32:         return "<";
    case 8:          return ">";
    default: break;
  }
  return NULL;
}

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
  if(dst_size == 0) return;
  if(src == NULL) src = "";
  strncpy(dst, src, dst_size - 1);
  dst[dst_size - 1] = 0;
}

static void tb_copy_trim(char* dst, usize dst_size, const char* begin, const char* end) {
  while(begin < end && tb_is_space(*begin)) begin++;
  while(end > begin && tb_is_space(*(end - 1))) end--;
  const usize len = (usize) (end - begin);
  const usize copy_len = (len < dst_size - 1) ? len : dst_size - 1;
  if(dst_size == 0) return;
  memcpy(dst, begin, copy_len);
  dst[copy_len] = 0;
}

#ifndef TINYBASIC_HOST_TEST
static bool tinybasic_language_is_ru(void) {
  return library_mk61::language_is_ru();
}
#endif

static void tb_message_i18n(const char* en0, const char* ru0, const char* en1, const char* ru1) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();
#ifndef TINYBASIC_HOST_TEST
  if(tinybasic_language_is_ru()) {
    lcd_ru::print_lines(ru0, ru1);
    return;
  }
#endif
  lcd.setCursor(0, 0);
  lcd.print(en0);
  lcd.setCursor(0, 1);
  lcd.print(en1);
  (void) ru0;
  (void) ru1;
}

static const char* tb_error_ru_text(const char* error) {
  if(tb_streq(error, "WHAT?")) return "ЧТО?";
  if(tb_streq(error, "HOW?")) return "КАК?";
  if(tb_streq(error, "SORRY")) return "НЕТ МЕСТА";
  return "ОШИБКА";
}

static bool tb_error(const char* error) {
  tb_copy_text(tb_last_error, sizeof(tb_last_error), error);
  tb_copy_text(tb_ast.error, sizeof(tb_ast.error), error);
  tb_message_i18n(error, tb_error_ru_text(error), "TinyBASIC", "TinyBASIC");
  return false;
}

static void tb_display_line(u8 row, const char* text) {
  MK61DisplayUpdate update(lcd);
  lcd.setCursor(0, row);
  for(u8 i = 0; i < 16; i++) lcd.write((u8) ' ');
  lcd.setCursor(0, row);
  if(text != NULL) lcd.print(text);
}

static void tb_append_char(char*& out, char* end, char ch) {
  if(out < end) *out++ = ch;
}

static void tb_append_uint(char*& out, char* end, unsigned long long value) {
  char digits[24];
  u8 count = 0;
  do {
    digits[count++] = (char) ('0' + (value % 10ULL));
    value /= 10ULL;
  } while(value > 0 && count < sizeof(digits));
  while(count > 0) tb_append_char(out, end, digits[--count]);
}

static void tb_format_fixed(double value, int decimals, char* out, usize size) {
  if(size == 0) return;
  if(decimals < 0) decimals = 0;
  if(decimals > 13) decimals = 13; // 10 significant digits at exp10 = -4 need 13 decimals

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
  if(negative && scaled != 0ULL) tb_append_char(cursor, end, '-');
  tb_append_uint(cursor, end, integer);
  if(decimals > 0) {
    tb_append_char(cursor, end, '.');
    char fractional[14];
    for(int i = decimals - 1; i >= 0; i--) {
      fractional[i] = (char) ('0' + (fraction % 10ULL));
      fraction /= 10ULL;
    }
    for(int i = 0; i < decimals; i++) tb_append_char(cursor, end, fractional[i]);
    while(cursor > temp && *(cursor - 1) == '0') cursor--;
    if(cursor > temp && *(cursor - 1) == '.') cursor--;
  }
  *cursor = 0;
  tb_copy_text(out, size, temp);
}

// TinyBASIC prints numbers with 10 significant digits, like the "%.10g" it
// used before. The firmware links newlib-nano without float printf support
// (no "-u _printf_float"), where snprintf silently drops %g values, so the
// number is formatted by hand the same way BASIC and FOCAL do.
static void tb_format_number(double value, char* out, usize size) {
  if(size == 0) return;
  if(mk_math::is_nan(value)) {
    tb_copy_text(out, size, "NAN");
    return;
  }
  if(mk_math::is_inf(value)) {
    tb_copy_text(out, size, value < 0.0 ? "-INF" : "INF");
    return;
  }
  if(value == 0.0) {
    tb_copy_text(out, size, "0");
    return;
  }

  const double abs_value = mk_math::fabs(value);
  int exp10 = mk_math::log10_floor(abs_value);
  if(exp10 >= 10 || exp10 < -4) { // %g switches to scientific outside [-4, precision)
    char mantissa[24];
    double scaled = abs_value / mk_math::pow10_int(exp10);
    tb_format_fixed(scaled, 9, mantissa, sizeof(mantissa));
    if(mantissa[0] == '1' && mantissa[1] == '0') { // rounding overflowed to 10.0
      exp10++;
      tb_format_fixed(1.0, 9, mantissa, sizeof(mantissa));
    }
    char temp[40];
    char* cursor = temp;
    char* end = temp + sizeof(temp) - 1;
    if(value < 0.0) tb_append_char(cursor, end, '-');
    for(const char* m = mantissa; *m != 0; m++) tb_append_char(cursor, end, *m);
    tb_append_char(cursor, end, 'E');
    if(exp10 < 0) {
      tb_append_char(cursor, end, '-');
      tb_append_uint(cursor, end, (unsigned long long) -exp10);
    } else {
      tb_append_char(cursor, end, '+');
      tb_append_uint(cursor, end, (unsigned long long) exp10);
    }
    *cursor = 0;
    tb_copy_text(out, size, temp);
    return;
  }

  int decimals = 9 - exp10;
  if(decimals < 0) decimals = 0;
  tb_format_fixed(value, decimals, out, size);
}

static void tb_ast_reset(TbAst& ast) {
  memset(&ast, 0, sizeof(ast));
  ast.ok = true;
}

static TbFlow tb_flow(TbFlowKind kind, i16 pc) {
  TbFlow flow;
  flow.kind = kind;
  flow.pc = pc;
  return flow;
}

static bool tb_read_word(const char* p, TbWord& out) {
  p = tb_skip_spaces(p);
  if(!tb_is_alpha(*p)) return false;
  u8 len = 0;
  while(tb_is_alpha(*p) && len < sizeof(out.text) - 1) out.text[len++] = tb_upper(*p++);
  while(tb_is_alpha(*p)) p++;
  out.dotted = *p == '.';
  if(out.dotted) p++;
  out.text[len] = 0;
  out.end = p;
  return len > 0;
}

static bool tb_word_matches(const TbWord& word, const char* full, u8 min_abbrev) {
  const usize word_len = strlen(word.text);
  const usize full_len = strlen(full);
  if(!word.dotted) return word_len == full_len && tb_streq(word.text, full);
  if(word_len < min_abbrev || word_len > full_len) return false;
  for(usize i = 0; i < word_len; i++) {
    if(word.text[i] != full[i]) return false;
  }
  return true;
}

static bool tb_parse_mk_ref_token(const char*& p, const char* end, mk61_ref::Ref& ref) {
  p = tb_skip_spaces(p);
  if(p >= end || *p != '.') return false;
  const char* cursor = p + 1;
  if(cursor >= end || !tb_is_alpha(*cursor)) return false;

  char name[4];
  u8 len = 0;
  while(cursor < end && (tb_is_alpha(*cursor) || tb_is_digit(*cursor))) {
    if(len < sizeof(name) - 1) name[len++] = tb_upper(*cursor);
    cursor++;
  }
  name[len] = 0;

  if(!mk61_ref::parse_name(name, ref)) return false;
  if(ref.kind == mk61_ref::Kind::R && !mk61_ref::register_available(ref.reg)) return false;
  p = cursor;
  return true;
}

static bool tb_parse_target_token(const char*& p, const char* end, TbTarget& target) {
  p = tb_skip_spaces(p);
  if(p >= end) return false;

  mk61_ref::Ref ref;
  if(*p == '.') {
    if(!tb_parse_mk_ref_token(p, end, ref)) return false;
    target.kind = TbTargetKind::MK_REF;
    target.var_index = -1;
    target.mk_ref = ref;
    return true;
  }

  if(!tb_is_alpha(*p)) return false;
  const int var = tb_upper(*p++) - 'A';
  if(var < 0 || var >= 26) return false;
  target.kind = TbTargetKind::VAR;
  target.var_index = var;
  target.mk_ref = {mk61_ref::Kind::X, 0};
  return true;
}

static bool tb_write_target(const TbTarget& target, double value) {
  if(target.kind == TbTargetKind::VAR) {
    tb_vars[target.var_index] = value;
    return true;
  }
  return mk61_ref::write(target.mk_ref, value);
}

static bool tb_parse_command_word(const char*& p, TbCommand& command) {
  TbWord word;
  if(!tb_read_word(p, word)) return false;
  if(tb_word_matches(word, "REM", 3) || tb_word_matches(word, "REMARK", 3)) command = TbCommand::CMD_REM;
  else if(tb_word_matches(word, "LET", 1)) command = TbCommand::CMD_LET;
  else if(tb_word_matches(word, "PRINT", 1)) command = TbCommand::CMD_PRINT;
  else if(tb_word_matches(word, "INPUT", 2)) command = TbCommand::CMD_INPUT;
  else if(tb_word_matches(word, "IF", 1)) command = TbCommand::CMD_IF;
  else if(tb_word_matches(word, "GOTO", 1)) command = TbCommand::CMD_GOTO;
  else if(tb_word_matches(word, "GOSUB", 3)) command = TbCommand::CMD_GOSUB;
  else if(tb_word_matches(word, "RETURN", 1)) command = TbCommand::CMD_RETURN;
  else if(tb_word_matches(word, "FOR", 1)) command = TbCommand::CMD_FOR;
  else if(tb_word_matches(word, "NEXT", 1)) command = TbCommand::CMD_NEXT;
  else if(tb_word_matches(word, "END", 1)) command = TbCommand::CMD_END;
  else if(tb_word_matches(word, "STOP", 1)) command = TbCommand::CMD_STOP;
  else return false;
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

static const char* tb_find_top_level(const char* begin, const char* end, char target) {
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
    if(*p == '(') depth++;
    else if(*p == ')' && depth > 0) depth--;
    else if(*p == target && depth == 0) return p;
  }
  return NULL;
}

class TbExprParser {
  public:
    TbExprParser(const char* begin, const char* end) : p(begin), end(end), ok(true) {}

    bool eval(double& out) {
      out = parse_compare();
      if(!ok) return false;
      return true;
    }

    const char* position(void) const { return p; }

  private:
    const char* p;
    const char* end;
    bool ok;

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

    bool match_word(const char* word) {
      skip();
      const usize len = strlen(word);
      if((usize) (end - p) < len) return false;
      for(usize i = 0; i < len; i++) {
        if(tb_upper(p[i]) != word[i]) return false;
      }
      if(p + len < end && tb_is_alpha(p[len])) return false;
      p += len;
      return true;
    }

    double parse_compare(void) {
      double left = parse_add();
      while(ok) {
        skip();
        if(p >= end) break;
        if(p + 1 < end && p[0] == '<' && p[1] == '>') {
          p += 2;
          left = (left != parse_add()) ? 1.0 : 0.0;
        } else if(p + 1 < end && p[0] == '<' && p[1] == '=') {
          p += 2;
          left = (left <= parse_add()) ? 1.0 : 0.0;
        } else if(p + 1 < end && p[0] == '>' && p[1] == '=') {
          p += 2;
          left = (left >= parse_add()) ? 1.0 : 0.0;
        } else if(*p == '<') {
          p++;
          left = (left < parse_add()) ? 1.0 : 0.0;
        } else if(*p == '>') {
          p++;
          left = (left > parse_add()) ? 1.0 : 0.0;
        } else if(*p == '=') {
          p++;
          left = (left == parse_add()) ? 1.0 : 0.0;
        } else {
          break;
        }
      }
      return left;
    }

    double parse_add(void) {
      double left = parse_mul();
      while(ok) {
        if(match_char('+')) left += parse_mul();
        else if(match_char('-')) left -= parse_mul();
        else if(match_word("OR")) left = (left != 0.0 || parse_mul() != 0.0) ? 1.0 : 0.0;
        else if(match_word("XOR")) {
          const bool a = left != 0.0;
          const bool b = parse_mul() != 0.0;
          left = (a != b) ? 1.0 : 0.0;
        } else break;
      }
      return left;
    }

    double parse_mul(void) {
      double left = parse_power();
      while(ok) {
        if(match_char('*')) left *= parse_power();
        else if(match_char('/')) {
          const double right = parse_power();
          if(right == 0.0) ok = false;
          else left /= right;
        } else if(match_word("MOD")) {
          const double right = parse_power();
          if(right == 0.0) ok = false;
          else left = left - mk_math::floor(left / right) * right;
        } else if(match_word("AND")) {
          left = (left != 0.0 && parse_power() != 0.0) ? 1.0 : 0.0;
        } else break;
      }
      return left;
    }

    double parse_power(void) {
      double left = parse_unary();
      while(ok && match_char('^')) left = mk_math::pow(left, parse_unary());
      return left;
    }

    double parse_unary(void) {
      if(match_char('+')) return parse_unary();
      if(match_char('-')) return -parse_unary();
      if(match_word("NOT")) return parse_unary() == 0.0 ? 1.0 : 0.0;
      return parse_primary();
    }

    double parse_primary(void) {
      skip();
      if(p >= end) {
        ok = false;
        return 0.0;
      }

      if(match_char('(')) {
        const double value = parse_compare();
        if(!match_char(')')) ok = false;
        return value;
      }

      if(*p == '.' && p + 1 < end && tb_is_alpha(*(p + 1))) {
        mk61_ref::Ref ref;
        if(!tb_parse_mk_ref_token(p, end, ref)) {
          ok = false;
          return 0.0;
        }
        double value = 0.0;
        if(!mk61_ref::read(ref, value)) {
          ok = false;
          return 0.0;
        }
        return value;
      }

      if(tb_is_digit(*p) || *p == '.') {
        const char* after = NULL;
        const double value = mk_math::strtod(p, &after);
        if(after == p || after > end) {
          ok = false;
          return 0.0;
        }
        p = after;
        return value;
      }

      if(tb_is_alpha(*p)) {
        char word[12];
        u8 len = 0;
        while(p < end && tb_is_alpha(*p) && len < sizeof(word) - 1) word[len++] = tb_upper(*p++);
        while(p < end && tb_is_alpha(*p)) p++;
        word[len] = 0;

        if(len == 1 && word[0] >= 'A' && word[0] <= 'Z') return tb_vars[word[0] - 'A'];
        if(tb_streq(word, "PI")) return 3.14159265358979323846;

        if(!match_char('(')) {
          ok = false;
          return 0.0;
        }

        if(tb_streq(word, "RND")) {
          skip();
          if(match_char(')')) return tb_next_random();
          const double max_value = parse_compare();
          if(!match_char(')')) ok = false;
          const int limit = (int) mk_math::floor(max_value);
          if(limit < 1) {
            ok = false;
            return 0.0;
          }
          return 1.0 + mk_math::floor(tb_next_random() * limit);
        }

        const double a = parse_compare();
        double b = 0.0;
        bool has_b = false;
        if(match_char(',')) {
          b = parse_compare();
          has_b = true;
        }
        if(!match_char(')')) {
          ok = false;
          return 0.0;
        }

        if(tb_streq(word, "SIN")) return mk_math::sin(a);
        if(tb_streq(word, "COS")) return mk_math::cos(a);
        if(tb_streq(word, "TG")) return mk_math::tan(a);
        if(tb_streq(word, "ASIN")) return mk_math::asin(a);
        if(tb_streq(word, "ACOS")) return mk_math::acos(a);
        if(tb_streq(word, "ATG")) return mk_math::atan(a);
        if(tb_streq(word, "LN")) return mk_math::ln(a);
        if(tb_streq(word, "LG")) return mk_math::log10(a);
        if(tb_streq(word, "EXP")) return mk_math::exp(a);
        if(tb_streq(word, "SQRT")) return mk_math::sqrt(a);
        if(tb_streq(word, "ABS")) return mk_math::fabs(a);
        if(tb_streq(word, "INT")) return mk_math::floor(a);
        if(tb_streq(word, "FRAC")) return a - mk_math::floor(a);
        if(tb_streq(word, "ROUND")) return mk_math::floor(a + 0.5);
        if(tb_streq(word, "SGN")) return (a > 0.0) ? 1.0 : ((a < 0.0) ? -1.0 : 0.0);
        if(tb_streq(word, "MAX") && has_b) return (a > b) ? a : b;
      }

      ok = false;
      return 0.0;
    }

    static double tb_next_random(void) {
      tb_random_state = tb_random_state * 25173UL + 13849UL;
      return (double) (tb_random_state & 0xFFFFUL) / 65536.0;
    }
};

static bool tb_eval_expr_range(const char* begin, const char* end, double& value, const char** out_pos = NULL) {
  TbExprParser parser(begin, end);
  if(!parser.eval(value)) return false;
  const char* pos = parser.position();
  if(out_pos != NULL) *out_pos = pos;
  else if(tb_skip_spaces(pos) < end) return false;
  return true;
}

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
  ast.source = source;

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
    p = tb_skip_spaces(p);
    if(p >= line_end) return tb_error("WHAT?");

    TbLine& line = ast.lines[ast.line_count++];
    line.number = number;
    line.offset = (u16) (p - source);
    line.len = (u16) (line_end - p);
  }

  if(ast.line_count == 0) return tb_error("WHAT?");

  for(i16 i = 0; i < ast.line_count - 1; i++) {
    for(i16 j = i + 1; j < ast.line_count; j++) {
      if(ast.lines[j].number < ast.lines[i].number) {
        const TbLine temp = ast.lines[i];
        ast.lines[i] = ast.lines[j];
        ast.lines[j] = temp;
      }
    }
  }
  for(i16 i = 1; i < ast.line_count; i++) {
    if(ast.lines[i - 1].number == ast.lines[i].number) return tb_error("WHAT?");
  }
  ast.ok = true;
  tb_last_error[0] = 0;
  return true;
}

bool CompileTinyBasic(char* program) {
  return tb_compile_source(program, tb_ast);
}

static int tb_find_line_number(int number) {
  for(i16 i = 0; i < tb_ast.line_count; i++) {
    if(tb_ast.lines[i].number == number) return i;
  }
  return -1;
}

static int tb_line_number_from_value(double value) {
  const int number = (int) mk_math::floor(value + 0.5);
  if(mk_math::fabs(value - number) > 0.0000001 || number < 1 || number > 32767) return -1;
  return number;
}

static void tb_flush_print(void) {
  tb_display_line(tb_print_row, tb_pending_print);
  tb_pending_print[0] = 0;
  if(tb_print_row + 1 < lcd.rows()) tb_print_row++;
}

static void tb_append_print(const char* text) {
  strncat(tb_pending_print, text, sizeof(tb_pending_print) - strlen(tb_pending_print) - 1);
}

static void tb_append_print_separator(char sep) {
  if(sep == ',') tb_append_print(" ");
}

static double tb_read_number_from_keyboard(const char* prompt) {
#ifdef TINYBASIC_HOST_TEST
  (void) prompt;
  return tb_host_input_value;
#else
  char buffer[17];
  memset(buffer, 0, sizeof(buffer));
  u8 len = 0;
  while(true) {
    tb_message_i18n(prompt, prompt, buffer, buffer);
    const i32 key = kbd::get_key_wait();
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
      const char* text = TB_key_text[key];
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
  return mk_math::atof(buffer);
#endif
}

static bool tb_execute_command_list(const char* begin, const char* end, i16 current_pc, TbRunState& state, TbFlow& flow);

static bool tb_execute_assignment(const char* begin, const char* end) {
  const char* p = tb_skip_spaces(begin);
  TbTarget target;
  if(!tb_parse_target_token(p, end, target)) return tb_error("WHAT?");
  p = tb_skip_spaces(p);
  if(*p != '=') return tb_error("WHAT?");
  p++;

  if(target.kind == TbTargetKind::MK_REF) {
    double value = 0.0;
    if(!tb_eval_expr_range(p, end, value)) return tb_error("HOW?");
    if(!tb_write_target(target, value)) return tb_error("HOW?");
    return true;
  }

  int var = target.var_index;
  while(true) {
    const char* item_end = tb_find_top_level(p, end, ',');
    if(item_end == NULL) item_end = end;
    double value = 0.0;
    if(!tb_eval_expr_range(p, item_end, value)) return tb_error("HOW?");
    if(var < 0 || var >= 26) return tb_error("HOW?");
    tb_vars[var++] = value;
    if(item_end >= end) break;
    p = item_end + 1;
  }
  return true;
}

static bool tb_execute_print(const char* begin, const char* end) {
  const char* p = begin;
  char trailing_sep = 0;
  if(tb_skip_spaces(p) >= end) {
    tb_flush_print();
    return true;
  }

  while(p < end) {
    p = tb_skip_spaces(p);
    if(p >= end) break;
    if(*p == '"' || *p == '\'') {
      const char quote = *p++;
      const char* text_begin = p;
      while(p < end && *p != quote) p++;
      if(p >= end) return tb_error("WHAT?");
      char text[TB_PRINT_BUFFER_SIZE];
      tb_copy_trim(text, sizeof(text), text_begin, p);
      tb_append_print(text);
      p++;
    } else {
      const char* comma = tb_find_top_level(p, end, ',');
      const char* semi = tb_find_top_level(p, end, ';');
      const char* item_end = end;
      if(comma != NULL && comma < item_end) item_end = comma;
      if(semi != NULL && semi < item_end) item_end = semi;
      double value = 0.0;
      if(!tb_eval_expr_range(p, item_end, value)) return tb_error("HOW?");
      char number[24];
      tb_format_number(value, number, sizeof(number));
      tb_append_print(number);
      p = item_end;
    }

    p = tb_skip_spaces(p);
    if(p < end && (*p == ',' || *p == ';')) {
      trailing_sep = *p++;
      tb_append_print_separator(trailing_sep);
      continue;
    }
    trailing_sep = 0;
    break;
  }

  if(trailing_sep == 0) tb_flush_print();
  return true;
}

static bool tb_execute_input(const char* begin, const char* end) {
  const char* p = begin;
  char prompt[17] = ":";
  while(p < end) {
    p = tb_skip_spaces(p);
    if(p >= end) break;
    if(*p == '"' || *p == '\'') {
      const char quote = *p++;
      const char* text_begin = p;
      while(p < end && *p != quote) p++;
      if(p >= end) return tb_error("WHAT?");
      tb_copy_trim(prompt, sizeof(prompt), text_begin, p);
      p++;
    } else {
      TbTarget target;
      if(!tb_parse_target_token(p, end, target)) return tb_error("WHAT?");
      if(!tb_write_target(target, tb_read_number_from_keyboard(prompt))) return tb_error("HOW?");
      prompt[0] = ':';
      prompt[1] = 0;
    }

    p = tb_skip_spaces(p);
    if(p < end && (*p == ',' || *p == ';')) p++;
  }
  return true;
}

static bool tb_execute_goto_like(const char* begin, const char* end, TbFlow& flow, bool gosub, i16 current_pc, TbRunState& state) {
  double value = 0.0;
  if(!tb_eval_expr_range(begin, end, value)) return tb_error("HOW?");
  const int number = tb_line_number_from_value(value);
  const int pc = (number < 0) ? -1 : tb_find_line_number(number);
  if(pc < 0) return tb_error("HOW?");
  if(gosub) {
    if(state.call_sp + 1 >= TB_CALL_DEPTH) return tb_error("HOW?");
    state.call_stack[++state.call_sp] = (i16) (current_pc + 1);
  }
  flow = tb_flow(TbFlowKind::JUMP, (i16) pc);
  return true;
}

static bool tb_execute_for(const char* begin, const char* end, i16 current_pc, TbRunState& state) {
  const char* p = tb_skip_spaces(begin);
  if(!tb_is_alpha(*p)) return tb_error("WHAT?");
  const int var = tb_upper(*p++) - 'A';
  p = tb_skip_spaces(p);
  if(*p != '=') return tb_error("WHAT?");
  p++;
  const char* after_start = NULL;
  double start_value = 0.0;
  if(!tb_eval_expr_range(p, end, start_value, &after_start)) return tb_error("HOW?");
  p = after_start;
  if(!tb_consume_word(p, "TO", 1)) return tb_error("WHAT?");
  double limit = 0.0;
  if(!tb_eval_expr_range(p, end, limit)) return tb_error("HOW?");
  if(state.for_sp + 1 >= TB_FOR_DEPTH) return tb_error("HOW?");
  tb_vars[var] = start_value;
  TbForFrame& frame = state.for_stack[++state.for_sp];
  frame.var_index = var;
  frame.limit = limit;
  frame.return_pc = (i16) (current_pc + 1);
  return true;
}

static bool tb_execute_next(const char* begin, const char* end, TbRunState& state, TbFlow& flow) {
  const char* p = tb_skip_spaces(begin);
  if(!tb_is_alpha(*p)) return tb_error("WHAT?");
  const int var = tb_upper(*p++) - 'A';
  p = tb_skip_spaces(p);
  if(p < end) return tb_error("WHAT?");
  if(state.for_sp < 0) return tb_error("HOW?");
  TbForFrame& frame = state.for_stack[state.for_sp];
  if(frame.var_index != var) return tb_error("HOW?");
  tb_vars[var] += 1.0;
  if(tb_vars[var] <= frame.limit) {
    flow = tb_flow(TbFlowKind::JUMP, frame.return_pc);
  } else {
    state.for_sp--;
  }
  return true;
}

static bool tb_execute_one(const char*& cursor, const char* end, i16 current_pc, TbRunState& state, TbFlow& flow) {
  cursor = tb_skip_spaces(cursor);
  if(cursor >= end) return true;

  const char* command_start = cursor;
  TbCommand command = TbCommand::CMD_NONE;
  const bool has_command = tb_parse_command_word(cursor, command);

  if(!has_command) {
    cursor = command_start;
    const char* segment_end = tb_find_top_level(cursor, end, ':');
    if(segment_end == NULL) segment_end = end;
    if(!tb_execute_assignment(cursor, segment_end)) return false;
    cursor = (segment_end < end) ? segment_end + 1 : segment_end;
    return true;
  }

  if(command == TbCommand::CMD_REM) {
    cursor = end;
    return true;
  }

  if(command == TbCommand::CMD_IF) {
    double condition = 0.0;
    const char* after_expr = NULL;
    if(!tb_eval_expr_range(cursor, end, condition, &after_expr)) return tb_error("HOW?");
    cursor = after_expr;
    (void) tb_consume_word(cursor, "THEN", 1);
    if(condition != 0.0) {
      if(!tb_execute_command_list(cursor, end, current_pc, state, flow)) return false;
    }
    cursor = end;
    return true;
  }

  const char* segment_end = tb_find_top_level(cursor, end, ':');
  if(segment_end == NULL) segment_end = end;

  switch(command) {
    case TbCommand::CMD_LET:
      if(!tb_execute_assignment(cursor, segment_end)) return false;
      break;
    case TbCommand::CMD_PRINT:
      if(!tb_execute_print(cursor, segment_end)) return false;
      break;
    case TbCommand::CMD_INPUT:
      if(!tb_execute_input(cursor, segment_end)) return false;
      break;
    case TbCommand::CMD_GOTO:
      if(!tb_execute_goto_like(cursor, segment_end, flow, false, current_pc, state)) return false;
      cursor = end;
      return true;
    case TbCommand::CMD_GOSUB:
      if(!tb_execute_goto_like(cursor, segment_end, flow, true, current_pc, state)) return false;
      cursor = end;
      return true;
    case TbCommand::CMD_RETURN:
      if(state.call_sp < 0) return tb_error("HOW?");
      flow = tb_flow(TbFlowKind::JUMP, state.call_stack[state.call_sp--]);
      cursor = end;
      return true;
    case TbCommand::CMD_FOR:
      if(!tb_execute_for(cursor, segment_end, current_pc, state)) return false;
      cursor = end;
      return true;
    case TbCommand::CMD_NEXT:
      if(!tb_execute_next(cursor, segment_end, state, flow)) return false;
      break;
    case TbCommand::CMD_END:
    case TbCommand::CMD_STOP:
      flow = tb_flow(TbFlowKind::STOP, current_pc);
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

static bool tb_execute_command_list(const char* begin, const char* end, i16 current_pc, TbRunState& state, TbFlow& flow) {
  const char* cursor = begin;
  while(cursor < end && flow.kind == TbFlowKind::NEXT) {
    if(!tb_execute_one(cursor, end, current_pc, state, flow)) {
      flow = tb_flow(TbFlowKind::ERROR, current_pc);
      return false;
    }
  }
  return true;
}

static bool tb_runtime_interrupted(void) {
#ifndef TINYBASIC_HOST_TEST
  idle_main_process();
  kbd::scan_and_debounced();
  const i32 key = kbd::last_key();
  if(key == KEY_ESC || key == KEY_ESC_PRESS) {
    (void) kbd::get_key();
    kbd::clear_hold_key();
    tb_message_i18n("TinyBASIC stop", "TinyBASIC стоп", "ESC", "ESC");
    return true;
  }
#endif
  return false;
}

void RunTinyBasic(int program_index) {
  if(program_index < 0 || program_index >= TB_PROGRAM_COUNT || !programs[program_index].used) {
    tb_error("HOW?");
    return;
  }
  if(!tb_compile_source(programs[program_index].source, tb_ast)) return;

  lcd.clear();
  memset(tb_vars, 0, sizeof(tb_vars));
  tb_pending_print[0] = 0;
  tb_print_row = 0;

  TbRunState state;
  memset(&state, 0, sizeof(state));
  state.call_sp = -1;
  state.for_sp = -1;

  i16 pc = 0;
  while(pc >= 0 && pc < tb_ast.line_count) {
    if(tb_runtime_interrupted()) break;
    TbFlow flow = tb_flow(TbFlowKind::NEXT, (i16) (pc + 1));
    const TbLine& line = tb_ast.lines[pc];
    const char* begin = tb_ast.source + line.offset;
    const char* end = begin + line.len;
    if(!tb_execute_command_list(begin, end, pc, state, flow)) break;
    if(flow.kind == TbFlowKind::NEXT) pc = (i16) (pc + 1);
    else if(flow.kind == TbFlowKind::JUMP) pc = flow.pc;
    else break;
  }
  if(tb_pending_print[0] != 0) tb_flush_print();
}

static int find_free_program(void) {
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(!programs[i].used) return i;
  }
  return -1;
}

static int find_program_by_name(const char* name) {
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(programs[i].used && tb_streq(programs[i].name, name)) return i;
  }
  return -1;
}

static void tb_program_default_name(int slot, char* out, usize size) {
  snprintf(out, size, "TINY%d", slot);
}

#ifndef TINYBASIC_HOST_TEST
static void tb_release_program_slot(int slot) {
  if(slot < 0 || slot >= TB_PROGRAM_COUNT) return;
  memset(&programs[slot], 0, sizeof(programs[slot]));
}

static int tb_alloc_program_slot(const char* name) {
  const int existing = find_program_by_name(name);
  if(existing >= 0) return existing;
  const int free_slot = find_free_program();
  if(free_slot >= 0) return free_slot;
  const int slot = (NextTinyBasic >= 0 && NextTinyBasic < TB_PROGRAM_COUNT) ? NextTinyBasic : 0;
  tb_release_program_slot(slot);
  return slot;
}

static bool tb_store_name_is_valid(const char* name) {
  return name != NULL && name[0] != 0 && strlen(name) < program_store::NAME_SIZE;
}

static int load_tinybasic_program_from_store(const char* name, bool compile = true) {
  if(!tb_store_name_is_valid(name)) return -1;
  char source[TB_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  u16 len = 0;
  if(!program_store::read(program_store::ProgramType::TINYBASIC, name, (u8*) source, TB_SOURCE_SIZE - 1, &len)) return -1;
  source[len] = 0;
  if(compile && !tb_compile_source(source, tb_ast)) return -1;
  const int slot = tb_alloc_program_slot(name);
  tb_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  tb_copy_text(programs[slot].name, sizeof(programs[slot].name), name);
  programs[slot].used = true;
  NextTinyBasic = (i8) slot;
  if(compile && !tb_compile_source(programs[slot].source, tb_ast)) return -1;
  return slot;
}
#endif

static int tinybasic_program_count(void) {
#ifndef TINYBASIC_HOST_TEST
  return program_store::count(program_store::ProgramType::TINYBASIC);
#else
  int count = 0;
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(programs[i].used) count++;
  }
  return count;
#endif
}

bool TinyBasicIsReady(void) {
  return tinybasic_program_count() > 0;
}

void InitTinyBasic(void) {
  memset(programs, 0, sizeof(programs));
  tb_ast_reset(tb_ast);
  memset(tb_vars, 0, sizeof(tb_vars));
  tb_last_error[0] = 0;
  tb_pending_print[0] = 0;
  tb_print_row = 0;
  NextTinyBasic = -1;
  tb_random_state = 0x3B6B120EUL;
}

static void draw_program_select(int active, bool allow_new) {
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
  else if(active >= 0 && active < TB_PROGRAM_COUNT && programs[active].used) {
    snprintf(line1, sizeof(line1), ">%s", programs[active].name);
  } else tb_copy_text(line1, sizeof(line1), ">EMPTY");
  tb_message_i18n("TinyBASIC", "TinyBASIC", line1, line1);
#endif
}

static int next_used_program(int active, int delta, bool allow_new) {
  const int max_index = allow_new ? TB_PROGRAM_COUNT : TB_PROGRAM_COUNT - 1;
  int current = active;
  for(int i = 0; i <= max_index; i++) {
    current += delta;
    if(current < 0) current = max_index;
    if(current > max_index) current = 0;
    if(current == TB_PROGRAM_COUNT) return current;
    if(programs[current].used) return current;
  }
  return active;
}

static int select_tinybasic_program(bool allow_new) {
#ifndef TINYBASIC_HOST_TEST
  const int stored_count = program_store::count(program_store::ProgramType::TINYBASIC);
  if(stored_count <= 0 && !allow_new) {
    tb_message_i18n("TinyBASIC empty", "TinyBASIC пуст", "Press any key", "Любая клавиша");
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
        if(allow_new && active == stored_count) return TB_PROGRAM_COUNT;
        {
          program_store::Entry entry;
          if(!program_store::entry(program_store::ProgramType::TINYBASIC, active, entry)) return -1;
          return load_tinybasic_program_from_store(entry.name, !allow_new);
        }
      case KEY_ESC:
        return -1;
    }
  }
#else
  int active = -1;
  for(int i = 0; i < TB_PROGRAM_COUNT; i++) {
    if(programs[i].used) {
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
  const int program = select_tinybasic_program(false);
  if(program >= 0) RunTinyBasic(program);
  return true;
}

static const text_editor::KeyMap TB_EDITOR_KEYS = {
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

static const char* tinybasic_editor_insert_text_hook(text_editor::Shift shift, i32 key_code, const char*, u16, void*) {
  if(key_code < 0 || key_code >= 40) return NULL;
  switch(shift) {
    case text_editor::Shift::NONE:
      return TB_key_text[key_code];
    case text_editor::Shift::ALPHA:
      return NULL;
    case text_editor::Shift::K:
      return tinybasic_kshift_text(key_code);
  }
  return NULL;
}

static const text_editor::Hooks TB_EDITOR_HOOKS = {
  &tinybasic_editor_insert_text_hook,
  NULL,
  NULL
};

static const text_editor::Options TB_EDITOR_OPTIONS = {
  "\n",
  true,
  true,
  true,
  -1
};

static void draw_tinybasic_editor(const char* source, u16 len, u16 cursor, u16 view_top, bool sms_cursor = false) {
  text_editor::draw(lcd, source, len, cursor, view_top, sms_cursor);
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
  if(ch == ' ') return false;
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

  MK61DisplayUpdate update(lcd);
  const u8 cursor_col = (u8) (1 + cursor - window);
  lcd.setCursor(cursor_col, 1);
  if(lcd.supportsCursor()) lcd.cursorOn();
  else lcd.write(sms_cursor ? text_editor::SMS_CURSOR_ASCII : text_editor::CURSOR_ASCII);
}

static bool tb_input_program_name(char* name, usize size) {
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
    if(!shifted && (key == KEY_K || key == KEY_ALPHA)) {
      shift = (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
      text_editor::sms_reset(sms);
      continue;
    }
    if(!shifted && (key == KEY_OK || key == KEY_OK_PRESS)) return len > 0;
    if(!shifted && (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if((key == KEY_LEFT || key == KEY_LEFT_PRESS) &&
        (shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      text_editor::backspace(name, len, cursor);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(!shifted && key == KEY_DEGREE) {
      text_editor::sms_reset(sms);
      text_editor::backspace(name, len, cursor);
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
    if(!shifted && key == 0) {
      text_editor::sms_reset(sms);
      len = 0;
      cursor = 0;
      name[0] = 0;
      continue;
    }

    const int digit = text_editor::digit_from_key(key);
    if(shift == text_editor::Shift::ALPHA && digit >= 0) {
      const char* symbol = text_editor::symbol_for_digit_key(key);
      if(symbol != NULL && symbol[0] != 0) tb_name_insert_char(name, len, cursor, symbol[0]);
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    const char* letters = text_editor::sms_letters_for_key(key);
    if(letters != NULL) {
      if(sms.active && sms.key_code == key && cursor > 0) {
        const usize count = strlen(letters);
        sms.index = (u8) ((sms.index + 1) % count);
        name[cursor - 1] = letters[sms.index];
        sms.deadline_ms = now + text_editor::SMS_INPUT_TIMEOUT_MS;
      } else {
        sms.active = true;
        sms.key_code = key;
        sms.index = 0;
        sms.deadline_ms = now + text_editor::SMS_INPUT_TIMEOUT_MS;
        tb_name_insert_char(name, len, cursor, letters[0]);
      }
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(text_editor::sms_key_is_space(key)) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, ' ');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(digit == 0 || key == KEY_PP) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, '0');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(digit == 1) {
      text_editor::sms_reset(sms);
      tb_name_insert_char(name, len, cursor, '1');
      shift = text_editor::Shift::NONE;
      continue;
    }
    shift = text_editor::Shift::NONE;
  }
}

static bool store_edited_program(int slot, char* source, const char* store_name) {
  if(slot < 0 || slot > TB_PROGRAM_COUNT) return tb_error("SORRY");
  char old_name[TB_NAME_SIZE] = "";
  if(slot >= 0 && slot < TB_PROGRAM_COUNT && programs[slot].used) {
    tb_copy_text(old_name, sizeof(old_name), programs[slot].name);
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
  if(!tb_compile_source(source, tb_ast)) return false;
  tb_copy_text(programs[slot].source, sizeof(programs[slot].source), source);
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  if(!tb_compile_source(programs[slot].source, tb_ast)) return false;
  if(store_name != NULL && store_name[0] != 0) tb_copy_text(programs[slot].name, sizeof(programs[slot].name), store_name);
  else tb_program_default_name(slot, programs[slot].name, sizeof(programs[slot].name));
  programs[slot].used = true;
  NextTinyBasic = (i8) slot;
#ifndef TINYBASIC_HOST_TEST
  if(!program_store::write(program_store::ProgramType::TINYBASIC, programs[slot].name, (const u8*) programs[slot].source, programs[slot].source_len)) {
    return tb_error("SORRY");
  }
  if(old_name[0] != 0 && !tb_streq(old_name, programs[slot].name)) {
    program_store::remove(program_store::ProgramType::TINYBASIC, old_name);
  }
#endif
  tb_message_i18n("TinyBASIC ready", "TinyBASIC готов", programs[slot].name, programs[slot].name);
  delay(700);
  return true;
}

static void EditTinyBasicSlot(int slot) {
  char source[TB_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  if(slot >= 0 && slot < TB_PROGRAM_COUNT && programs[slot].used) tb_copy_text(source, sizeof(source), programs[slot].source);

  text_editor::Buffer editor;
  text_editor::init(editor, source, TB_SOURCE_SIZE);
  bool dirty = true;
  kbd::debounce_init();
  while(true) {
    const u32 now = millis();
    if(editor.sms.active && now >= editor.sms.deadline_ms) {
      text_editor::sms_reset(editor.sms);
      dirty = true;
    }
    if(dirty) {
      text_editor::ensure_cursor_visible(lcd, source, editor.len, editor.cursor, editor.view_top);
      draw_tinybasic_editor(source, editor.len, editor.cursor, editor.view_top, editor.sms.active);
      dirty = false;
    }
    kbd::scan_and_debounced();
    i32 key_code = kbd::get_key(key_state::PRESSED);
    if(key_code < 0) {
      lcd.flush();
      delay(1);
      continue;
    }
    const text_editor::KeyResult result = text_editor::handle_key(editor, TB_EDITOR_KEYS, TB_EDITOR_HOOKS, TB_EDITOR_OPTIONS, key_code, now);
    dirty = result != text_editor::KeyResult::NONE;
    if(result == text_editor::KeyResult::SAVE) {
      lcd.cursorOff();
      if(!tb_confirm_save()) return;
      char name[TB_NAME_SIZE];
      memset(name, 0, sizeof(name));
      if(slot >= 0 && slot < TB_PROGRAM_COUNT && programs[slot].used) tb_copy_text(name, sizeof(name), programs[slot].name);
      else tb_program_default_name(find_free_program() < 0 ? 0 : find_free_program(), name, sizeof(name));
      if(tb_input_program_name(name, sizeof(name)) && store_edited_program(slot, source, name)) return;
      kbd::debounce_init();
      return;
    }
  }
}

void EditTinyBasic(void) {
  const int slot = select_tinybasic_program(true);
  if(slot < 0) return;
  EditTinyBasicSlot(slot);
}

bool EditTinyBasicProgram(const char* name) {
#ifndef TINYBASIC_HOST_TEST
  const int slot = load_tinybasic_program_from_store(name, false);
  if(slot < 0) return false;
  EditTinyBasicSlot(slot);
  return true;
#else
  (void) name;
  return false;
#endif
}

bool RunTinyBasicProgram(const char* name) {
#ifndef TINYBASIC_HOST_TEST
  const int slot = load_tinybasic_program_from_store(name);
#else
  const int slot = find_program_by_name(name);
#endif
  if(slot < 0) return false;
  RunTinyBasic(slot);
  return true;
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
  lcd.clear();
#ifdef TINYBASIC_HOST_TEST
  mk61_ref::host_reset();
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
  programs[slot].used = true;
  NextTinyBasic = (i8) slot;
  return slot;
}

extern "C" void TinyBasicTestSetInput(double value) {
  tb_host_input_value = value;
}

extern "C" void TinyBasicTestRun(int slot) {
  lcd.clear();
  RunTinyBasic(slot);
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

extern "C" const char* TinyBasicTestLcdLine(int row) {
  return lcd.line((u8) row);
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
    text_editor::handle_key(editor, TB_EDITOR_KEYS, TB_EDITOR_HOOKS, TB_EDITOR_OPTIONS, keys[i], now);
  }
  strncpy(out, source, (usize) size - 1);
  out[size - 1] = 0;
}
#endif

#endif
