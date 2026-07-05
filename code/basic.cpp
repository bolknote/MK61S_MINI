#ifdef BASIC_HOST_TEST
#include "rust_types.h"
#include "basic.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const u8 G_RUS             = 0x05;
static const u8 LCD_NOT_EQU_CHAR  = 0xB7;
static const int KEY_LEFT = 34;
static const int KEY_RIGHT = 24;
static const int KEY_OK = 29;
static const int KEY_ESC = 39;
static const int KEY_K = 37;
static const int KEY_ALPHA = KEY_K + 1;
static const int KEY_DEGREE = 4;
static const int KEY_LEFT_PRESS = KEY_LEFT;
static const int KEY_RIGHT_PRESS = KEY_RIGHT;
static const int KEY_OK_PRESS = KEY_OK;
static const int KEY_ESC_PRESS = KEY_ESC;
static constexpr isize MAX_SLOT_FOR_PROGRAM = 99;
static constexpr usize SIZEOF_SLOT_NAME = 16;

inline isize HexdecimalDigit(char Symbol) {
  if(Symbol >= '0' && Symbol <= '9') return Symbol - '0';
  if(Symbol >= 'A' && Symbol <= 'F') return Symbol - 'A' + 10;
  if(Symbol >= 'a' && Symbol <= 'f') return Symbol - 'a' + 10;
  return -1;
}

class MK61Display {
  public:
    MK61Display(void) : x(0), y(0) { clear(); }

    void clear(void) {
      memset(lines, ' ', sizeof(lines));
      for(int row = 0; row < 4; row++) lines[row][16] = 0;
      x = 0;
      y = 0;
    }

    void setCursor(u8 col, u8 row) {
      x = (col < 16) ? col : 15;
      y = (row < 4) ? row : 3;
    }

    void write(u8 value) {
      if(x < 16 && y < 4) lines[y][x++] = (char) value;
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
    void print(int value, int base) {
      char buffer[16];
      if(base == 16) snprintf(buffer, sizeof(buffer), "%X", value);
      else snprintf(buffer, sizeof(buffer), "%d", value);
      print(buffer);
    }
    void createChar(u8, uint8_t*) {}
    const char* line(u8 row) const { return lines[(row < 4) ? row : 0]; }

  private:
    u8 x;
    u8 y;
    char lines[4][17];
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display&) {}
};

MK61Display lcd;

enum class key_state {PRESSED=0, RELEASED=0x40};

bool cir_buff_write(i8) { return true; }
i8 cir_buff_get(usize) { return -1; }
i32 cir_buff_read(void) { return -1; }

namespace kbd {
  inline void push(i8) {}
  inline i32 last_key(void) { return -1; }
  inline i32 get_key(void) { return -1; }
  void test(void) {}
  void debounce_init(void) {}
  void init(void) {}
  i32 get_key(key_state) { return -1; }
  i32 get_key_wait(void) { return KEY_OK; }
  void exclude_before(i32) {}
  void clear_hold_key(void) {}
  isize scan(void) { return 0; }
  isize scan_and_debounced(void) { return 0; }
}

static u32 basic_host_millis;
u32 millis(void) { return basic_host_millis += 17; }
void delay(usize ms) { basic_host_millis += (u32) ms; }

typedef enum {
  X1 = 0,
  X  = 1,
  Y  = 2,
  Z  = 3,
  T  = 4
} stack;

u8 ringM[15 * 42 + 128];

static double host_stack_value[5];
static double host_register_value[15];

static void format_mk61_number(double value, char out[15]) {
  char sign = ' ';
  if(value < 0.0) {
    sign = '-';
    value = -value;
  }

  int pow10 = 0;
  double normalized = 0.0;
  if(value > 0.0) {
    pow10 = (int) floor(log10(value));
    normalized = value / pow(10.0, pow10);
    if(normalized >= 10.0) {
      normalized /= 10.0;
      pow10++;
    }
    if(normalized < 1.0) {
      normalized *= 10.0;
      pow10--;
    }
  }

  long scaled = (long) floor(normalized * 10000000.0 + 0.5);
  if(scaled >= 100000000L) {
    scaled /= 10;
    pow10++;
  }

  out[0] = sign;
  out[1] = (char) ('0' + (scaled / 10000000L) % 10);
  out[2] = '.';
  long place = 1000000L;
  for(int pos = 3; pos <= 9; pos++) {
    out[pos] = (char) ('0' + (scaled / place) % 10);
    place /= 10;
  }
  out[10] = ' ';
  out[11] = pow10 < 0 ? '-' : ' ';
  int abs_pow = pow10 < 0 ? -pow10 : pow10;
  out[12] = (char) ('0' + (abs_pow / 10) % 10);
  out[13] = (char) ('0' + abs_pow % 10);
  out[14] = 0;
}

namespace core_61 {
  struct bcd_value {
    u32 mantissa;
    u16 signs_and_pow;
  };

  static constexpr usize MAX_PROGRAM_STEP = 112;
  static u8 host_ip;

  u8 get_IP(void) { return host_ip; }
  usize program_steps(void) { return MAX_PROGRAM_STEP; }

  void get_stack_register(stack reg, bcd_value& value) {
    value.mantissa = (u32) (host_stack_value[(int) reg] * 1000.0);
    value.signs_and_pow = 0;
  }

  void set_stack_register(stack reg, bcd_value* value) {
    host_stack_value[(int) reg] = ((double) value->mantissa) / 1000.0;
  }
}

const char* read_stack_register(stack reg, char cvalue[15], const char*) {
  format_mk61_number(host_stack_value[(int) reg], cvalue);
  return cvalue;
}

void write_stack_register(stack reg, char sign, char cmantissa[8], isize pow10) {
  long scaled = 0;
  for(int i = 0; i < 8; i++) scaled = scaled * 10 + (cmantissa[i] - '0');
  double value = ((double) scaled) / 10000000.0 * pow(10.0, (double) pow10);
  if(sign == '-') value = -value;
  host_stack_value[(int) reg] = value;
}

void MK61Emu_ReadRegister(int nReg, char* buffer, const char* symbols) {
  (void) symbols;
  format_mk61_number(host_register_value[nReg], buffer);
}

void MK61Emu_WriteRegister(int nReg, char* buffer) {
  long scaled = 0;
  for(int i = 0; i < 8; i++) scaled = scaled * 10 + (buffer[i] - '0');
  int pow10 = (buffer[9] - '0') * 10 + (buffer[10] - '0');
  host_register_value[nReg] = ((double) scaled) / 10000000.0 * pow(10.0, (double) pow10);
}

bool Load(usize) { return true; }
u8 load_word(isize, isize) { return 0; }
bool IsOccupied(usize) { return false; }
char* ReadSlotName(usize, char*) { return NULL; }

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

#else
#include "rust_types.h"
#include "Arduino.h"
#include "lcd_gui.hpp"
#include "tools.hpp"
#include "menu.hpp"
#include "basic.hpp"
#include "keyboard.h"
#include "cross_hal.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

#if MK61_ENABLE_BASIC

using namespace kbd;

extern MK61Display lcd;

static const char basic_display_symbols[16] = {
    'O', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', 'L', 'C', G_RUS, 'E', ' '
};

/*
   Cx,  Bx, MUL, DIV, NON,
  POW,  XY, ADD, SUB, NON,
  NEG, _3_, _6_, _9_, NON,
  DOT, _2_, _5_, _8_, NON,
  _0_, _1_, _4_, _7_, NON,
  JSR, JMP,  xP,  Px, NON,
  RUN, RET,  SF,  SB, NON,
  NON, NON,   K,   F, NON
*/
static const char BASIC_key[40] = {
   '%', '%', '*', '/', '%',
  '?', '%', '+', '-', '%',
   '%', '3', '6', '9', '%',
  '.', '2', '5', '8', '%',
  '0', '1', '4', '7', '%',
  ' ', '%', '%', '%', '%',
  (char) LCD_NOT_EQU_CHAR, (char) 0xA6, '=', '<', '%',
  '%', '%', '%', '%', '%'
};

enum class BasicEditShift : u8 {
  NONE,
  ALPHA,
  K
};

static const char* const BASIC_key_text[40] = {
  NULL, NULL, "*", "/", NULL,
  "?", NULL, "+", "-", NULL,
  NULL, "3", "6", "9", NULL,
  ".", "2", "5", "8", NULL,
  "0", "1", "4", "7", NULL,
  " ", NULL, NULL, NULL, NULL,
  "<>", ">=", "=", "<", NULL,
  NULL, NULL, NULL, NULL, NULL
};

static const char* const BASIC_alpha_key_text[40] = {
  "D", "E", "F", "G", NULL,
  "C", NULL, NULL, "X", "H",
  "B", NULL, NULL, NULL, "I",
  "A", "Z", "W", NULL, "J",
  "T", "Y", NULL, NULL, "K",
  "S", "$", "V", "U", "L",
  "R", NULL, NULL, NULL, "M",
  "Q", "P", "O", NULL, "N"
};

static const char* const BASIC_Kshift_key_text[40] = {
  "~", ":", "(", ")", NULL,
  "^", "\"", NULL, ">", "#",
  "&", NULL, NULL, NULL, NULL,
  "|", "Z", "W", NULL, NULL,
  NULL, "Y", NULL, NULL, NULL,
  ",", NULL, "V", "U", NULL,
  NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL
};

static constexpr int BASIC_PROGRAM_COUNT       = 8;
static constexpr int BASIC_SOURCE_SIZE         = 512;
static constexpr int BASIC_NAME_SIZE           = 16;
static constexpr int BASIC_STRING_SIZE         = 24;
static constexpr int BASIC_MAX_STATEMENTS      = 96;
static constexpr int BASIC_MAX_EXPRESSIONS     = 160;
static constexpr int BASIC_MAX_LABELS          = 32;
static constexpr int BASIC_FOR_STACK_DEPTH     = 8;
static constexpr int BASIC_CALL_DEPTH          = 2;
static constexpr int BASIC_MAX_ARGS            = 4;
static constexpr int BASIC_VARIABLE_COUNT      = 26 * 11;
static constexpr int BASIC_RUNTIME_STEPS_LIMIT = 2048;

static constexpr u32 CURSOR_BLINK_MS = 850;
static constexpr u8  CURSOR_ASCII    = 0xFF;

static constexpr i32 BASIC_SCAN_B_UP  = 1;
static constexpr i32 BASIC_SCAN_PRINT = 5;
static constexpr i32 BASIC_SCAN_USER  = 19;
static constexpr i32 BASIC_SCAN_JMP   = 26;
static constexpr i32 BASIC_SCAN_XP    = 27;
static constexpr i32 BASIC_SCAN_PX    = 28;
static constexpr i32 BASIC_SCAN_RUN   = 30;
static constexpr i32 BASIC_SCAN_RET   = 31;
static constexpr i32 BASIC_SCAN_SF    = 32;
static constexpr i32 BASIC_SCAN_SB    = 33;
static constexpr i32 BASIC_SCAN_LOAD  = 35;
static constexpr i32 BASIC_SCAN_SAVE  = 36;

enum class TokenKind : u8 {
  END,
  IDENT,
  NUMBER,
  STRING,
  SYMBOL,
  OP
};

enum class BasicOp : u8 {
  NONE,
  ADD,
  SUB,
  MUL,
  DIV,
  POW,
  EQ,
  NE,
  LT,
  LE,
  GT,
  GE,
  AND,
  OR,
  XOR,
  NOT
};

enum class ExprKind : u8 {
  NONE,
  NUMBER,
  STRING,
  NUM_VAR,
  STR_VAR,
  MK_REF,
  UNARY,
  BINARY,
  CALL,
  MK_CALL
};

enum class StmtKind : u8 {
  NOP,
  LABEL,
  PRINT,
  INPUT_STMT,
  ASSIGN_NUM,
  ASSIGN_STR,
  IF,
  FOR,
  NXT,
  DO_BEGIN,
  DO_WH,
  WHILE_BEGIN,
  WHILE_END,
  GO,
  CLR,
  LD,
  HLT,
  MK_SAVE,
  MK_RESTORE,
  MK_BIND,
  CALL
};

enum class TargetKind : u8 {
  NONE,
  NUM_VAR,
  STR_VAR,
  MK_REF
};

enum class MkRefKind : u8 {
  X,
  Y,
  Z,
  T,
  R
};

struct Token {
  TokenKind kind;
  BasicOp op;
  char symbol;
  char text[BASIC_NAME_SIZE];
  double number;
};

struct BasicExpr {
  ExprKind kind;
  BasicOp op;
  i16 left;
  i16 right;
  u16 var_index;
  u8 mk_ref;
  u8 mk_reg;
  u8 arg_count;
  i16 args[BASIC_MAX_ARGS];
  double number;
  char text[BASIC_STRING_SIZE + 1];
};

struct BasicStmt {
  StmtKind kind;
  i16 next;
  i16 expr0;
  i16 expr1;
  i16 expr2;
  i16 jump;
  i16 child0;
  i16 child1;
  u16 var_index;
  u8 target_kind;
  u8 label;
  u8 mk_step;
  u8 mk_ref;
  u8 mk_reg;
  char text[BASIC_NAME_SIZE];
};

struct BasicLabel {
  u8 label;
  i16 stmt;
};

struct BasicAst {
  bool ok;
  char error[17];
  BasicStmt stmts[BASIC_MAX_STATEMENTS];
  BasicExpr exprs[BASIC_MAX_EXPRESSIONS];
  BasicLabel labels[BASIC_MAX_LABELS];
  i16 first_stmt;
  i16 stmt_count;
  i16 expr_count;
  i16 label_count;
  char program_name[BASIC_NAME_SIZE];
};

struct BasicProgram {
  bool used;
  char name[BASIC_NAME_SIZE];
  char source[BASIC_SOURCE_SIZE];
  u16 source_len;
};

struct BasicTarget {
  TargetKind kind;
  u16 var_index;
  u8 mk_ref;
  u8 mk_reg;
};

struct BasicValue {
  bool is_string;
  double number;
  char text[BASIC_STRING_SIZE + 1];
};

struct ForFrame {
  i16 for_stmt;
  u16 var_index;
  double end_value;
  double step_value;
};

struct BasicMkContext {
  bool valid;
  core_61::bcd_value stack_value[4];
  u8 reg_value[15][42];
};

static BasicProgram programs[BASIC_PROGRAM_COUNT];
static i8 basic_step_program[core_61::MAX_PROGRAM_STEP];
static BasicAst ast;
static BasicAst ast_call_stack[BASIC_CALL_DEPTH];
static u8 ast_call_sp;

static double numeric_vars[BASIC_VARIABLE_COUNT];
static bool numeric_var_set[BASIC_VARIABLE_COUNT];
static char string_vars[BASIC_VARIABLE_COUNT][BASIC_STRING_SIZE + 1];
static bool string_var_set[BASIC_VARIABLE_COUNT];
static BasicMkContext mk_context;
static int NextBasic;

static void basic_print_ascii_line(u8 row, const char* text) {
  lcd.setCursor(0, row);
  u8 used = 0;
  if(text != NULL) {
    while(text[used] != 0 && used < 16) {
      lcd.write((u8) text[used]);
      used++;
    }
  }
  while(used++ < 16) lcd.write((u8) ' ');
}

static bool basic_language_is_ru(void) {
#ifdef BASIC_HOST_TEST
  return false;
#else
  return library_mk61::language_is_ru();
#endif
}

static void basic_print_text_at(u8 x, u8 y, const char* en, const char* ru, u8 width = 16) {
#ifdef BASIC_HOST_TEST
  (void) ru;
#endif
#ifndef BASIC_HOST_TEST
  if(basic_language_is_ru()) {
    library_mk61::print_localized_at(x, y, ru, en, width);
    return;
  }
#endif

  lcd.setCursor(x, y);
  u8 used = 0;
  while(en != NULL && en[used] != 0 && used < width) lcd.write((u8) en[used++]);
  while(used++ < width) lcd.write((u8) ' ');
}

static void basic_message_i18n(const char* en0, const char* ru0, const char* en1 = NULL, const char* ru1 = NULL) {
  if(ru0 == NULL) ru0 = en0;
  if(ru1 == NULL) ru1 = en1;

#ifndef BASIC_HOST_TEST
  if(basic_language_is_ru()) {
    {
      MK61DisplayUpdate update(lcd);
      lcd.clear();
    }
    lcd_ru::print_lines(ru0, ru1 == NULL ? "" : ru1);
    return;
  }
#endif

  MK61DisplayUpdate update(lcd);
  lcd.clear();
  basic_print_ascii_line(0, en0);
  if(en1 != NULL) basic_print_ascii_line(1, en1);
}

static const char* basic_error_ru_text(const char* text) {
  struct ErrorMap {
    const char* en;
    const char* ru;
  };

  static const ErrorMap errors[] = {
    {"expr overflow", "много выраж."},
    {"stmt overflow", "много строк"},
    {"label overflow", "много меток"},
    {"dup label", "метка занята"},
    {"$var?", "$перем?"},
    {".ref?", ".ссылка?"},
    {"statement?", "оператор?"},
    {"input target?", "куда ввод?"},
    {"TH?", "нет TH"},
    {"FOR var?", "FOR перем?"},
    {"FOR =?", "FOR =?"},
    {"TO?", "нет TO"},
    {"GO label?", "GO метка?"},
    {"mk step?", "MK шаг?"},
    {"mk step range", "MK шаг вне"},
    {"mk =?", "MK =?"},
    {"mk name?", "MK имя?"},
    {"LET target?", "LET куда?"},
    {"LET =?", "LET =?"},
    {") missing", "нет )"},
    {"expr?", "выражение?"},
    {"name?", "имя?"},
    {"args overflow", "много арг."},
    {"loop stack", "стек циклов"},
    {"NXT?", "нет NXT"},
    {"END?", "нет END"},
    {"loop open", "цикл открыт"},
    {"program full", "нет места"},
    {"no program", "нет программ"},
    {"call depth", "стек вызовов"},
    {"run limit", "цикл завис"},
    {"FOR stack", "стек FOR"},
    {"NXT stack", "стек NXT"},
    {"no label", "нет метки"},
    {"LD failed", "LD не найден"}
  };

  for(usize i = 0; i < sizeof(errors) / sizeof(errors[0]); i++) {
    if(strcmp(text, errors[i].en) == 0) return errors[i].ru;
  }
  return text;
}

static bool basic_error(const char* text) {
  char line[17];
  strncpy(line, text, sizeof(line) - 1);
  line[sizeof(line) - 1] = 0;
  basic_message_i18n("Error BASIC!", "Ошибка БЕЙСИК", line, basic_error_ru_text(text));
  kbd::get_key_wait();
  return false;
}

static char basic_upper(char c) {
  if(c >= 'a' && c <= 'z') return (char) (c - 'a' + 'A');
  return c;
}

static bool basic_is_alpha(char c) {
  c = basic_upper(c);
  return c >= 'A' && c <= 'Z';
}

static bool basic_is_digit(char c) {
  return c >= '0' && c <= '9';
}

static bool basic_streq(const char* a, const char* b) {
  while(*a != 0 && *b != 0) {
    if(basic_upper(*a++) != basic_upper(*b++)) return false;
  }
  return *a == 0 && *b == 0;
}

static void basic_copy_name(char* dst, const char* src) {
  u8 i = 0;
  while(i < BASIC_NAME_SIZE - 1 && src[i] != 0 && src[i] != ' ') {
    dst[i] = basic_upper(src[i]);
    i++;
  }
  dst[i] = 0;
}

static void basic_display_program_name(const char* name, char* out, usize size) {
  if(size == 0) return;
  out[0] = 0;

  if(basic_language_is_ru() && basic_streq(name, "BASIC")) {
    strncpy(out, "БЕЙСИК", size - 1);
    out[size - 1] = 0;
    return;
  }

  const char basic_prefix[] = "BASIC";
  bool has_basic_prefix = basic_language_is_ru();
  for(u8 i = 0; has_basic_prefix && i < 5; i++) {
    if(name[i] == 0 || basic_upper(name[i]) != basic_prefix[i]) has_basic_prefix = false;
  }

  if(has_basic_prefix) {
    bool digits_only = name[5] != 0;
    for(u8 i = 5; name[i] != 0; i++) {
      if(!basic_is_digit(name[i])) {
        digits_only = false;
        break;
      }
    }
    if(digits_only) {
      snprintf(out, size, "БЕЙСИК%s", name + 5);
      return;
    }
  }

  strncpy(out, name, size - 1);
  out[size - 1] = 0;
}

static void basic_clear_vars(void) {
  memset(numeric_vars, 0, sizeof(numeric_vars));
  memset(numeric_var_set, 0, sizeof(numeric_var_set));
  memset(string_vars, 0, sizeof(string_vars));
  memset(string_var_set, 0, sizeof(string_var_set));
}

static int variable_index_from_name(const char* name) {
  if(!basic_is_alpha(name[0])) return -1;
  const int letter = basic_upper(name[0]) - 'A';
  if(name[1] == 0) return letter * 11;
  if(name[2] == 0 && basic_is_digit(name[1])) return letter * 11 + 1 + (name[1] - '0');
  return -1;
}

static stack stack_from_mk_ref(u8 mk_ref) {
  switch((MkRefKind) mk_ref) {
    case MkRefKind::X: return stack::X;
    case MkRefKind::Y: return stack::Y;
    case MkRefKind::Z: return stack::Z;
    case MkRefKind::T: return stack::T;
    case MkRefKind::R: break;
  }
  return stack::X;
}

static double parse_mk61_display_number(const char* value) {
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
  return strtod(buffer, NULL);
}

static double read_mk_ref(u8 mk_ref, u8 mk_reg) {
  char value[15];
  value[14] = 0;
  if((MkRefKind) mk_ref == MkRefKind::R) {
    MK61Emu_ReadRegister(mk_reg, value, basic_display_symbols);
  } else {
    read_stack_register(stack_from_mk_ref(mk_ref), value, basic_display_symbols);
  }
  return parse_mk61_display_number(value);
}

static void double_to_mk61_parts(double value, char& sign, char mantissa[8], isize& pow10) {
  if(value < 0) {
    sign = '-';
    value = -value;
  } else {
    sign = ' ';
  }

  if(value == 0.0) {
    memset(mantissa, '0', 8);
    pow10 = 0;
    return;
  }

  pow10 = (isize) floor(log10(value));
  double normalized = value / pow(10.0, (double) pow10);
  if(normalized >= 10.0) {
    normalized /= 10.0;
    pow10++;
  }
  if(normalized < 1.0) {
    normalized *= 10.0;
    pow10--;
  }

  long scaled = (long) floor(normalized * 10000000.0 + 0.5);
  if(scaled >= 100000000L) {
    scaled /= 10;
    pow10++;
  }

  for(int i = 7; i >= 0; i--) {
    mantissa[i] = (char) ('0' + (scaled % 10));
    scaled /= 10;
  }
}

static void write_mk_ref(u8 mk_ref, u8 mk_reg, double value) {
  char sign;
  char mantissa[8];
  isize pow10;
  double_to_mk61_parts(value, sign, mantissa, pow10);

  if((MkRefKind) mk_ref == MkRefKind::R) {
    char buffer[12];
    memcpy(buffer, mantissa, 8);
    buffer[8] = ' ';
    const isize bounded_pow = (pow10 < 0) ? -pow10 : pow10;
    buffer[9] = (char) ('0' + ((bounded_pow / 10) % 10));
    buffer[10] = (char) ('0' + (bounded_pow % 10));
    buffer[11] = 0;
    MK61Emu_WriteRegister(mk_reg, buffer);
    return;
  }

  write_stack_register(stack_from_mk_ref(mk_ref), sign, mantissa, pow10);
}

class Lexer {
  public:
    explicit Lexer(const char* source) : src(source), pos(0) {
      next();
    }

    const Token& current(void) const { return tok; }

    usize position(void) const { return tok_start; }

    void restore(usize new_pos) {
      pos = new_pos;
      next();
    }

    void next(void) {
      while(src[pos] == ' ' || src[pos] == '\t' || src[pos] == '\r' || src[pos] == '\n') pos++;
      tok_start = pos;

      memset(&tok, 0, sizeof(tok));
      tok.kind = TokenKind::END;
      tok.op = BasicOp::NONE;

      const unsigned char c = (unsigned char) src[pos];
      if(c == 0) return;

      if(basic_is_alpha((char) c) || c == '_') {
        tok.kind = TokenKind::IDENT;
        u8 i = 0;
        while(i < BASIC_NAME_SIZE - 1) {
          const char ch = src[pos];
          if(!(basic_is_alpha(ch) || basic_is_digit(ch) || ch == '_')) break;
          tok.text[i++] = basic_upper(ch);
          pos++;
        }
        tok.text[i] = 0;
        return;
      }

      if(basic_is_digit((char) c)) {
        tok.kind = TokenKind::NUMBER;
        char buffer[24];
        u8 i = 0;
        while(i < sizeof(buffer) - 1) {
          const char ch = src[pos];
          if(!(basic_is_digit(ch) || ch == '.' || ch == 'E' || ch == 'e' || ch == '+' || ch == '-')) break;
          buffer[i++] = ch;
          pos++;
          if((ch == '+' || ch == '-') && i > 1 && buffer[i - 2] != 'E' && buffer[i - 2] != 'e') {
            pos--;
            i--;
            break;
          }
        }
        buffer[i] = 0;
        tok.number = strtod(buffer, NULL);
        return;
      }

      if(c == '"') {
        tok.kind = TokenKind::STRING;
        pos++;
        u8 i = 0;
        while(src[pos] != 0 && src[pos] != '"' && i < BASIC_STRING_SIZE) tok.text[i++] = src[pos++];
        tok.text[i] = 0;
        if(src[pos] == '"') pos++;
        return;
      }

      tok.kind = TokenKind::SYMBOL;
      tok.symbol = src[pos++];

      switch(c) {
        case '+': tok.kind = TokenKind::OP; tok.op = BasicOp::ADD; break;
        case '-': tok.kind = TokenKind::OP; tok.op = BasicOp::SUB; break;
        case '*':
          tok.kind = TokenKind::OP;
          if(src[pos] == '*') {
            pos++;
            tok.op = BasicOp::POW;
          } else {
            tok.op = BasicOp::MUL;
          }
          break;
        case '/': tok.kind = TokenKind::OP; tok.op = BasicOp::DIV; break;
        case '=': tok.kind = TokenKind::OP; tok.op = BasicOp::EQ; break;
        case '<':
          tok.kind = TokenKind::OP;
          if(src[pos] == '=') {
            pos++;
            tok.op = BasicOp::LE;
          } else if(src[pos] == '>') {
            pos++;
            tok.op = BasicOp::NE;
          } else {
            tok.op = BasicOp::LT;
          }
          break;
        case '>':
          tok.kind = TokenKind::OP;
          if(src[pos] == '=') {
            pos++;
            tok.op = BasicOp::GE;
          } else {
            tok.op = BasicOp::GT;
          }
          break;
        case '!':
          tok.kind = TokenKind::OP;
          if(src[pos] == '=') pos++;
          tok.op = BasicOp::NE;
          break;
        case '&': tok.kind = TokenKind::OP; tok.op = BasicOp::AND; break;
        case '|': tok.kind = TokenKind::OP; tok.op = BasicOp::OR; break;
        case '^': tok.kind = TokenKind::OP; tok.op = BasicOp::XOR; break;
        case '~': tok.kind = TokenKind::OP; tok.op = BasicOp::NOT; break;
        default:
          if(c == (unsigned char) LCD_NOT_EQU_CHAR) {
            tok.kind = TokenKind::OP;
            tok.op = BasicOp::NE;
          } else if(c == 0xA6) {
            tok.kind = TokenKind::OP;
            tok.op = BasicOp::GE;
          }
          break;
      }
    }

  private:
    const char* src;
    usize pos;
    usize tok_start;
    Token tok;
};

static void ast_reset(BasicAst& a) {
  memset(&a, 0, sizeof(a));
  a.ok = true;
  a.first_stmt = -1;
  for(int i = 0; i < BASIC_MAX_STATEMENTS; i++) {
    a.stmts[i].next = -1;
    a.stmts[i].expr0 = -1;
    a.stmts[i].expr1 = -1;
    a.stmts[i].expr2 = -1;
    a.stmts[i].jump = -1;
    a.stmts[i].child0 = -1;
    a.stmts[i].child1 = -1;
  }
}

static bool ast_fail(BasicAst& a, const char* error) {
  if(!a.ok) return false;
  a.ok = false;
  strncpy(a.error, error, sizeof(a.error) - 1);
  a.error[sizeof(a.error) - 1] = 0;
  return false;
}

static i16 ast_new_expr(BasicAst& a, ExprKind kind) {
  if(a.expr_count >= BASIC_MAX_EXPRESSIONS) {
    ast_fail(a, "expr overflow");
    return -1;
  }
  const i16 id = a.expr_count++;
  memset(&a.exprs[id], 0, sizeof(BasicExpr));
  a.exprs[id].kind = kind;
  a.exprs[id].left = -1;
  a.exprs[id].right = -1;
  for(int i = 0; i < BASIC_MAX_ARGS; i++) a.exprs[id].args[i] = -1;
  return id;
}

static i16 ast_new_stmt(BasicAst& a, StmtKind kind) {
  if(a.stmt_count >= BASIC_MAX_STATEMENTS) {
    ast_fail(a, "stmt overflow");
    return -1;
  }
  const i16 id = a.stmt_count++;
  memset(&a.stmts[id], 0, sizeof(BasicStmt));
  a.stmts[id].kind = kind;
  a.stmts[id].next = -1;
  a.stmts[id].expr0 = -1;
  a.stmts[id].expr1 = -1;
  a.stmts[id].expr2 = -1;
  a.stmts[id].jump = -1;
  a.stmts[id].child0 = -1;
  a.stmts[id].child1 = -1;
  return id;
}

static void ast_add_label(BasicAst& a, u8 label, i16 stmt) {
  if(a.label_count >= BASIC_MAX_LABELS) {
    ast_fail(a, "label overflow");
    return;
  }
  for(int i = 0; i < a.label_count; i++) {
    if(a.labels[i].label == label) {
      ast_fail(a, "dup label");
      return;
    }
  }
  a.labels[a.label_count].label = label;
  a.labels[a.label_count].stmt = stmt;
  a.label_count++;
}

static i16 ast_find_label(const BasicAst& a, u8 label) {
  for(int i = 0; i < a.label_count; i++) {
    if(a.labels[i].label == label) return a.labels[i].stmt;
  }
  return -1;
}

class Parser {
  public:
    Parser(const char* source, BasicAst& output) : lex(source), out(output), last_top(-1) {}

    bool parse_program(void) {
      ast_reset(out);

      while(out.ok && lex.current().kind != TokenKind::END) {
        if(accept_symbol(':') || accept_symbol(';')) continue;
        const i16 stmt = parse_statement(true);
        if(stmt < 0) break;
        link_top(stmt);
        accept_symbol(':');
        accept_symbol(';');
      }

      if(out.ok) link_loops();
      if(out.ok && out.program_name[0] == 0) strcpy(out.program_name, "BASIC");
      return out.ok;
    }

  private:
    Lexer lex;
    BasicAst& out;
    i16 last_top;

    bool is_keyword(const char* text) const {
      const Token& t = lex.current();
      return t.kind == TokenKind::IDENT && basic_streq(t.text, text);
    }

    bool accept_keyword(const char* text) {
      if(!is_keyword(text)) return false;
      lex.next();
      return true;
    }

    bool accept_symbol(char c) {
      if(lex.current().kind != TokenKind::SYMBOL || lex.current().symbol != c) return false;
      lex.next();
      return true;
    }

    bool accept_op(BasicOp op) {
      if(lex.current().kind != TokenKind::OP || lex.current().op != op) return false;
      lex.next();
      return true;
    }

    void link_top(i16 stmt) {
      if(stmt < 0) return;
      if(out.first_stmt < 0) out.first_stmt = stmt;
      if(last_top >= 0) out.stmts[last_top].next = stmt;
      last_top = stmt;
    }

    bool parse_label_token(u8& label) {
      const Token& t = lex.current();
      if(t.kind == TokenKind::NUMBER) {
        if(t.number < 0 || t.number > 99) return false;
        label = (u8) t.number;
        lex.next();
        return true;
      }
      if(t.kind == TokenKind::IDENT && t.text[1] == 0) {
        label = (u8) t.text[0];
        lex.next();
        return true;
      }
      return false;
    }

    bool parse_target(BasicTarget& target) {
      memset(&target, 0, sizeof(target));
      target.kind = TargetKind::NONE;

      if(accept_symbol('$')) {
        if(lex.current().kind != TokenKind::IDENT) return ast_fail(out, "$var?");
        const int idx = variable_index_from_name(lex.current().text);
        if(idx < 0) return ast_fail(out, "$var?");
        target.kind = TargetKind::STR_VAR;
        target.var_index = (u16) idx;
        lex.next();
        return true;
      }

      if(accept_symbol('.')) {
        if(lex.current().kind != TokenKind::IDENT) return ast_fail(out, ".ref?");
        if(basic_streq(lex.current().text, "X")) {
          target.kind = TargetKind::MK_REF;
          target.mk_ref = (u8) MkRefKind::X;
          lex.next();
          return true;
        }
        if(basic_streq(lex.current().text, "Y")) {
          target.kind = TargetKind::MK_REF;
          target.mk_ref = (u8) MkRefKind::Y;
          lex.next();
          return true;
        }
        if(basic_streq(lex.current().text, "Z")) {
          target.kind = TargetKind::MK_REF;
          target.mk_ref = (u8) MkRefKind::Z;
          lex.next();
          return true;
        }
        if(basic_streq(lex.current().text, "T")) {
          target.kind = TargetKind::MK_REF;
          target.mk_ref = (u8) MkRefKind::T;
          lex.next();
          return true;
        }
        if(lex.current().text[0] == 'R') {
          const int reg = HexdecimalDigit(lex.current().text[1]);
          if(reg >= 0 && reg <= 0x0E && lex.current().text[2] == 0) {
            target.kind = TargetKind::MK_REF;
            target.mk_ref = (u8) MkRefKind::R;
            target.mk_reg = (u8) reg;
            lex.next();
            return true;
          }
        }
        return ast_fail(out, ".ref?");
      }

      if(lex.current().kind != TokenKind::IDENT) return false;
      const int idx = variable_index_from_name(lex.current().text);
      if(idx < 0) return false;
      target.kind = TargetKind::NUM_VAR;
      target.var_index = (u16) idx;
      lex.next();
      return true;
    }

    i16 parse_statement(bool top_level) {
      const usize label_pos = lex.position();
      u8 label = 0;
      if(parse_label_token(label) && accept_symbol(':')) {
        const i16 stmt = ast_new_stmt(out, StmtKind::LABEL);
        out.stmts[stmt].label = label;
        ast_add_label(out, label, stmt);
        return stmt;
      }
      lex.restore(label_pos);

      if(accept_keyword("REM")) {
        while(lex.current().kind != TokenKind::END && !is_statement_separator()) lex.next();
        return ast_new_stmt(out, StmtKind::NOP);
      }

      if(accept_keyword("PRINT") || accept_symbol('?')) return parse_print();
      if(accept_keyword("INPUT") || accept_keyword("IN")) return parse_input();
      if(accept_keyword("IF")) return parse_if();
      if(accept_keyword("FOR")) return parse_for();
      if(accept_keyword("NEXT") || accept_keyword("NXT")) return parse_nxt();
      if(accept_keyword("DO")) return ast_new_stmt(out, StmtKind::DO_BEGIN);
      if(accept_keyword("WHILE") || accept_keyword("WH")) return parse_wh();
      if(accept_keyword("END")) return ast_new_stmt(out, StmtKind::WHILE_END);
      if(accept_keyword("GOTO") || accept_keyword("GO")) return parse_go();
      if(accept_keyword("CLR")) return ast_new_stmt(out, StmtKind::CLR);
      if(accept_keyword("LOAD") || accept_keyword("LD")) return parse_ld();
      if(accept_keyword("STOP") || accept_keyword("HLT")) return parse_hlt();
      if(accept_keyword("LET")) return parse_assignment();

      const usize context_pos = lex.position();
      if(accept_op(BasicOp::LT) && accept_keyword("MK")) return ast_new_stmt(out, StmtKind::MK_SAVE);
      lex.restore(context_pos);
      if(accept_keyword("MK")) {
        if(accept_op(BasicOp::LT)) return ast_new_stmt(out, StmtKind::MK_RESTORE);
        if(accept_symbol('.')) return parse_mk_bind();
        lex.restore(context_pos);
      }

      const usize assignment_pos = lex.position();
      BasicTarget target;
      if(parse_target(target) && accept_op(BasicOp::EQ)) return finish_assignment(target);
      lex.restore(assignment_pos);

      if(lex.current().kind == TokenKind::IDENT) {
        return parse_call_statement();
      }

      (void) top_level;
      ast_fail(out, "statement?");
      return -1;
    }

    bool is_statement_separator(void) const {
      if(lex.current().kind == TokenKind::END) return true;
      return lex.current().kind == TokenKind::SYMBOL &&
             (lex.current().symbol == ':' || lex.current().symbol == ';');
    }

    i16 parse_print(void) {
      const i16 stmt = ast_new_stmt(out, StmtKind::PRINT);
      out.stmts[stmt].expr0 = parse_expression();
      return stmt;
    }

    i16 parse_input(void) {
      BasicTarget target;
      if(!parse_target(target)) {
        ast_fail(out, "input target?");
        return -1;
      }
      const i16 stmt = ast_new_stmt(out, StmtKind::INPUT_STMT);
      apply_target(stmt, target);
      return stmt;
    }

    i16 parse_if(void) {
      const i16 stmt = ast_new_stmt(out, StmtKind::IF);
      out.stmts[stmt].expr0 = parse_expression();
      if(!(accept_keyword("THEN") || accept_keyword("TH"))) {
        ast_fail(out, "TH?");
        return -1;
      }
      out.stmts[stmt].child0 = parse_statement(false);
      if(accept_keyword("ELSE") || accept_keyword("EL")) out.stmts[stmt].child1 = parse_statement(false);
      return stmt;
    }

    i16 parse_for(void) {
      BasicTarget target;
      if(!parse_target(target) || target.kind != TargetKind::NUM_VAR) {
        ast_fail(out, "FOR var?");
        return -1;
      }
      if(!accept_op(BasicOp::EQ)) {
        ast_fail(out, "FOR =?");
        return -1;
      }
      const i16 stmt = ast_new_stmt(out, StmtKind::FOR);
      out.stmts[stmt].var_index = target.var_index;
      out.stmts[stmt].expr0 = parse_expression();
      if(!accept_keyword("TO")) {
        ast_fail(out, "TO?");
        return -1;
      }
      out.stmts[stmt].expr1 = parse_expression();
      if(accept_keyword("STEP")) out.stmts[stmt].expr2 = parse_expression();
      return stmt;
    }

    i16 parse_nxt(void) {
      const i16 stmt = ast_new_stmt(out, StmtKind::NXT);
      if(lex.current().kind == TokenKind::IDENT) {
        const int idx = variable_index_from_name(lex.current().text);
        if(idx >= 0) out.stmts[stmt].var_index = (u16) idx;
        lex.next();
      }
      return stmt;
    }

    i16 parse_wh(void) {
      const i16 stmt = ast_new_stmt(out, StmtKind::WHILE_BEGIN);
      out.stmts[stmt].expr0 = parse_expression();
      return stmt;
    }

    i16 parse_go(void) {
      u8 label = 0;
      if(!parse_label_token(label)) {
        ast_fail(out, "GO label?");
        return -1;
      }
      const i16 stmt = ast_new_stmt(out, StmtKind::GO);
      out.stmts[stmt].label = label;
      return stmt;
    }

    i16 parse_ld(void) {
      const i16 stmt = ast_new_stmt(out, StmtKind::LD);
      if(lex.current().kind == TokenKind::STRING || lex.current().kind == TokenKind::IDENT) {
        basic_copy_name(out.stmts[stmt].text, lex.current().text);
        lex.next();
      } else {
        out.stmts[stmt].expr0 = parse_expression();
      }
      return stmt;
    }

    i16 parse_hlt(void) {
      const i16 stmt = ast_new_stmt(out, StmtKind::HLT);
      if(lex.current().kind == TokenKind::IDENT || lex.current().kind == TokenKind::STRING) {
        basic_copy_name(out.stmts[stmt].text, lex.current().text);
        basic_copy_name(out.program_name, lex.current().text);
        lex.next();
      }
      return stmt;
    }

    i16 parse_mk_bind(void) {
      if(lex.current().kind != TokenKind::NUMBER) {
        ast_fail(out, "mk step?");
        return -1;
      }
      const int step = (int) lex.current().number;
      lex.next();
      if(step < 0 || step >= (int) core_61::MAX_PROGRAM_STEP) {
        ast_fail(out, "mk step range");
        return -1;
      }
      if(!accept_op(BasicOp::EQ)) {
        ast_fail(out, "mk =?");
        return -1;
      }
      if(lex.current().kind != TokenKind::IDENT && lex.current().kind != TokenKind::STRING) {
        ast_fail(out, "mk name?");
        return -1;
      }
      const i16 stmt = ast_new_stmt(out, StmtKind::MK_BIND);
      out.stmts[stmt].mk_step = (u8) step;
      basic_copy_name(out.stmts[stmt].text, lex.current().text);
      lex.next();
      return stmt;
    }

    i16 parse_assignment(void) {
      BasicTarget target;
      if(!parse_target(target)) {
        ast_fail(out, "LET target?");
        return -1;
      }
      if(!accept_op(BasicOp::EQ)) {
        ast_fail(out, "LET =?");
        return -1;
      }
      return finish_assignment(target);
    }

    i16 finish_assignment(const BasicTarget& target) {
      const i16 stmt = ast_new_stmt(out, target.kind == TargetKind::STR_VAR ? StmtKind::ASSIGN_STR : StmtKind::ASSIGN_NUM);
      apply_target(stmt, target);
      out.stmts[stmt].expr0 = parse_expression();
      return stmt;
    }

    i16 parse_call_statement(void) {
      const i16 expr = parse_primary();
      if(expr < 0) return -1;
      const i16 stmt = ast_new_stmt(out, StmtKind::CALL);
      out.stmts[stmt].expr0 = expr;
      return stmt;
    }

    void apply_target(i16 stmt, const BasicTarget& target) {
      out.stmts[stmt].target_kind = (u8) target.kind;
      out.stmts[stmt].var_index = target.var_index;
      out.stmts[stmt].mk_ref = target.mk_ref;
      out.stmts[stmt].mk_reg = target.mk_reg;
    }

    i16 parse_expression(int min_prec = 0) {
      i16 left = parse_unary();
      while(out.ok) {
        if(lex.current().kind != TokenKind::OP) break;
        const BasicOp op = lex.current().op;
        const int prec = precedence(op);
        if(prec < min_prec) break;
        lex.next();
        const int next_min = (op == BasicOp::POW) ? prec : prec + 1;
        const i16 right = parse_expression(next_min);
        const i16 node = ast_new_expr(out, ExprKind::BINARY);
        out.exprs[node].op = op;
        out.exprs[node].left = left;
        out.exprs[node].right = right;
        left = node;
      }
      return left;
    }

    int precedence(BasicOp op) const {
      switch(op) {
        case BasicOp::OR: return 1;
        case BasicOp::XOR: return 2;
        case BasicOp::AND: return 3;
        case BasicOp::EQ:
        case BasicOp::NE:
        case BasicOp::LT:
        case BasicOp::LE:
        case BasicOp::GT:
        case BasicOp::GE: return 4;
        case BasicOp::ADD:
        case BasicOp::SUB: return 5;
        case BasicOp::MUL:
        case BasicOp::DIV: return 6;
        case BasicOp::POW: return 7;
        case BasicOp::NOT:
        case BasicOp::NONE: break;
      }
      return -1;
    }

    i16 parse_unary(void) {
      if(accept_op(BasicOp::SUB)) {
        const i16 node = ast_new_expr(out, ExprKind::UNARY);
        out.exprs[node].op = BasicOp::SUB;
        out.exprs[node].left = parse_unary();
        return node;
      }
      if(accept_op(BasicOp::NOT)) {
        const i16 node = ast_new_expr(out, ExprKind::UNARY);
        out.exprs[node].op = BasicOp::NOT;
        out.exprs[node].left = parse_unary();
        return node;
      }
      if(accept_op(BasicOp::ADD)) return parse_unary();
      return parse_primary();
    }

    i16 parse_primary(void) {
      const Token& t = lex.current();
      if(t.kind == TokenKind::NUMBER) {
        const i16 node = ast_new_expr(out, ExprKind::NUMBER);
        out.exprs[node].number = t.number;
        lex.next();
        return node;
      }
      if(t.kind == TokenKind::STRING) {
        const i16 node = ast_new_expr(out, ExprKind::STRING);
        strncpy(out.exprs[node].text, t.text, BASIC_STRING_SIZE);
        lex.next();
        return node;
      }
      if(accept_symbol('$')) {
        if(lex.current().kind != TokenKind::IDENT) {
          ast_fail(out, "$var?");
          return -1;
        }
        const int idx = variable_index_from_name(lex.current().text);
        if(idx < 0) {
          ast_fail(out, "$var?");
          return -1;
        }
        const i16 node = ast_new_expr(out, ExprKind::STR_VAR);
        out.exprs[node].var_index = (u16) idx;
        lex.next();
        return node;
      }
      if(accept_symbol('.')) return parse_mk_ref_expr();
      if(accept_symbol('#')) return parse_named_call(ExprKind::MK_CALL);
      if(accept_symbol('(')) {
        const i16 expr = parse_expression();
        if(!accept_symbol(')')) ast_fail(out, ") missing");
        return expr;
      }
      if(t.kind == TokenKind::IDENT) {
        const usize save = lex.position();
        char name[BASIC_NAME_SIZE];
        basic_copy_name(name, t.text);
        lex.next();
        if(accept_symbol('(')) return finish_call(name, ExprKind::CALL);
        lex.restore(save);

        const int idx = variable_index_from_name(lex.current().text);
        if(idx >= 0) {
          const i16 node = ast_new_expr(out, ExprKind::NUM_VAR);
          out.exprs[node].var_index = (u16) idx;
          lex.next();
          return node;
        }

        return parse_named_call(ExprKind::CALL);
      }
      ast_fail(out, "expr?");
      return -1;
    }

    i16 parse_mk_ref_expr(void) {
      BasicTarget target;
      memset(&target, 0, sizeof(target));
      if(lex.current().kind != TokenKind::IDENT) {
        ast_fail(out, ".ref?");
        return -1;
      }
      char name[BASIC_NAME_SIZE];
      basic_copy_name(name, lex.current().text);
      lex.next();
      const i16 node = ast_new_expr(out, ExprKind::MK_REF);
      if(basic_streq(name, "X")) out.exprs[node].mk_ref = (u8) MkRefKind::X;
      else if(basic_streq(name, "Y")) out.exprs[node].mk_ref = (u8) MkRefKind::Y;
      else if(basic_streq(name, "Z")) out.exprs[node].mk_ref = (u8) MkRefKind::Z;
      else if(basic_streq(name, "T")) out.exprs[node].mk_ref = (u8) MkRefKind::T;
      else if(name[0] == 'R' && name[2] == 0 && HexdecimalDigit(name[1]) >= 0) {
        out.exprs[node].mk_ref = (u8) MkRefKind::R;
        out.exprs[node].mk_reg = (u8) HexdecimalDigit(name[1]);
      } else {
        ast_fail(out, ".ref?");
      }
      return node;
    }

    i16 parse_named_call(ExprKind kind) {
      if(lex.current().kind != TokenKind::IDENT) {
        ast_fail(out, "name?");
        return -1;
      }
      char name[BASIC_NAME_SIZE];
      basic_copy_name(name, lex.current().text);
      lex.next();
      if(accept_symbol('(')) return finish_call(name, kind);
      const i16 node = ast_new_expr(out, kind);
      basic_copy_name(out.exprs[node].text, name);
      return node;
    }

    i16 finish_call(const char* name, ExprKind kind) {
      const i16 node = ast_new_expr(out, kind);
      basic_copy_name(out.exprs[node].text, name);
      while(out.ok && !accept_symbol(')')) {
        if(out.exprs[node].arg_count >= BASIC_MAX_ARGS) {
          ast_fail(out, "args overflow");
          break;
        }
        out.exprs[node].args[out.exprs[node].arg_count++] = parse_expression();
        if(!accept_symbol(',')) {
          if(!accept_symbol(')')) ast_fail(out, ") missing");
          break;
        }
      }
      return node;
    }

    void link_loops(void) {
      i16 loop_stack[BASIC_FOR_STACK_DEPTH];
      u8 loop_type[BASIC_FOR_STACK_DEPTH];
      i8 sp = -1;

      for(i16 i = 0; i < out.stmt_count && out.ok; i++) {
        BasicStmt& s = out.stmts[i];
        switch(s.kind) {
          case StmtKind::FOR:
            if(sp + 1 >= BASIC_FOR_STACK_DEPTH) {
              ast_fail(out, "loop stack");
              return;
            }
            loop_stack[++sp] = i;
            loop_type[sp] = 1;
            break;
          case StmtKind::NXT:
            if(sp < 0 || loop_type[sp] != 1) {
              ast_fail(out, "NXT?");
              return;
            }
            s.jump = loop_stack[sp];
            out.stmts[loop_stack[sp]].jump = i;
            sp--;
            break;
          case StmtKind::DO_BEGIN:
            if(sp + 1 >= BASIC_FOR_STACK_DEPTH) {
              ast_fail(out, "loop stack");
              return;
            }
            loop_stack[++sp] = i;
            loop_type[sp] = 2;
            break;
          case StmtKind::WHILE_BEGIN:
            if(sp >= 0 && loop_type[sp] == 2) {
              s.kind = StmtKind::DO_WH;
              s.jump = loop_stack[sp];
              out.stmts[loop_stack[sp]].jump = i;
              sp--;
            } else {
              if(sp + 1 >= BASIC_FOR_STACK_DEPTH) {
                ast_fail(out, "loop stack");
                return;
              }
              loop_stack[++sp] = i;
              loop_type[sp] = 3;
            }
            break;
          case StmtKind::WHILE_END:
            if(sp < 0 || loop_type[sp] != 3) {
              ast_fail(out, "END?");
              return;
            }
            s.jump = loop_stack[sp];
            out.stmts[loop_stack[sp]].jump = i;
            sp--;
            break;
          default:
            break;
        }
      }

      if(sp >= 0) ast_fail(out, "loop open");
    }
};

static bool compile_source(const char* source, BasicAst& output) {
  Parser parser(source, output);
  if(!parser.parse_program()) return basic_error(output.error);
  return true;
}

static int find_program_by_name(const char* name) {
  for(int i = 0; i < BASIC_PROGRAM_COUNT; i++) {
    if(programs[i].used && basic_streq(programs[i].name, name)) return i;
  }
  return -1;
}

static int find_free_program(void) {
  for(int i = 0; i < BASIC_PROGRAM_COUNT; i++) {
    if(!programs[i].used) return i;
  }
  return -1;
}

static int basic_program_count(void) {
  int count = 0;
  for(int i = 0; i < BASIC_PROGRAM_COUNT; i++) {
    if(programs[i].used) count++;
  }
  return count;
}

static int next_used_program(int from, int delta, bool allow_new) {
  const int limit = allow_new ? BASIC_PROGRAM_COUNT : BASIC_PROGRAM_COUNT - 1;
  int pos = from;
  for(int tries = 0; tries <= BASIC_PROGRAM_COUNT; tries++) {
    pos += delta;
    if(pos < 0) pos = limit;
    if(pos > limit) pos = 0;
    if(pos == BASIC_PROGRAM_COUNT) return pos;
    if(programs[pos].used) return pos;
  }
  return allow_new ? BASIC_PROGRAM_COUNT : -1;
}

static void draw_program_select(int active, bool allow_new) {
  char line1[17];
  char ru_line_buffer[32];
  if(allow_new && active == BASIC_PROGRAM_COUNT) {
    strcpy(line1, ">NEW");
  } else if(active >= 0 && active < BASIC_PROGRAM_COUNT && programs[active].used) {
    line1[0] = '>';
    strncpy(&line1[1], programs[active].name, sizeof(line1) - 2);
    line1[sizeof(line1) - 1] = 0;
  } else {
    strcpy(line1, ">empty");
  }

  const char* ru_line1 = line1;
  if(allow_new && active == BASIC_PROGRAM_COUNT) ru_line1 = ">НОВАЯ";
  else if(active >= 0 && active < BASIC_PROGRAM_COUNT && programs[active].used) {
    char display_name[22];
    basic_display_program_name(programs[active].name, display_name, sizeof(display_name));
    ru_line_buffer[0] = '>';
    strncpy(&ru_line_buffer[1], display_name, sizeof(ru_line_buffer) - 2);
    ru_line_buffer[sizeof(ru_line_buffer) - 1] = 0;
    ru_line1 = ru_line_buffer;
  } else {
    ru_line1 = ">ПУСТО";
  }

  basic_message_i18n("BASIC program", "Программа", line1, ru_line1);
}

static int select_basic_program(bool allow_new) {
  int active = -1;
  for(int i = 0; i < BASIC_PROGRAM_COUNT; i++) {
    if(programs[i].used) {
      active = i;
      break;
    }
  }
  if(active < 0) active = allow_new ? BASIC_PROGRAM_COUNT : -1;
  if(active < 0) {
    basic_message_i18n("BASIC is empty", "БЕЙСИК пуст", "Press any key", "Любая клавиша");
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
}

static void display_ast_ok(const BasicProgram& program) {
  char line[17];
  char ru_line[32];
  snprintf(line, sizeof(line), "%s %d/%d", program.name, ast.stmt_count, ast.expr_count);
  char display_name[18];
  basic_display_program_name(program.name, display_name, sizeof(display_name));
  snprintf(ru_line, sizeof(ru_line), "%s %d/%d", display_name, ast.stmt_count, ast.expr_count);
  basic_message_i18n("BASIC compiled", "БЕЙСИК готов", line, ru_line);
  delay(800);
}

bool CompileBasic(char* program) {
  const int slot = find_free_program();
  if(slot < 0) return basic_error("program full");

  strncpy(programs[slot].source, program, BASIC_SOURCE_SIZE - 1);
  programs[slot].source[BASIC_SOURCE_SIZE - 1] = 0;
  programs[slot].source_len = (u16) strlen(programs[slot].source);

  if(!compile_source(programs[slot].source, ast)) {
    memset(&programs[slot], 0, sizeof(programs[slot]));
    return false;
  }

  basic_copy_name(programs[slot].name, ast.program_name);
  if(programs[slot].name[0] == 0) snprintf(programs[slot].name, sizeof(programs[slot].name), "BASIC%d", slot);
  programs[slot].used = true;
  NextBasic = slot;
  display_ast_ok(programs[slot]);
  return true;
}

static bool compile_program_slot(int slot) {
  if(slot < 0 || slot >= BASIC_PROGRAM_COUNT || !programs[slot].used) return basic_error("no program");
  return compile_source(programs[slot].source, ast);
}

static BasicValue make_number(double value) {
  BasicValue out;
  memset(&out, 0, sizeof(out));
  out.is_string = false;
  out.number = value;
  return out;
}

static BasicValue make_string(const char* value) {
  BasicValue out;
  memset(&out, 0, sizeof(out));
  out.is_string = true;
  strncpy(out.text, value, BASIC_STRING_SIZE);
  return out;
}

static double basic_truth(double value) {
  return fabs(value) > 0.0000001 ? 1.0 : 0.0;
}

static bool eval_expr(i16 expr_id, BasicValue& value);

static double run_basic_function_call(int program) {
  if(program < 0 || program >= BASIC_PROGRAM_COUNT || !programs[program].used) return 0.0;
  if(ast_call_sp >= BASIC_CALL_DEPTH) {
    basic_error("call depth");
    return 0.0;
  }

  ast_call_stack[ast_call_sp++] = ast;
  RunBasic(program);
  ast = ast_call_stack[--ast_call_sp];
  return read_mk_ref((u8) MkRefKind::X, 0);
}

static double eval_number(i16 expr_id) {
  BasicValue value;
  if(!eval_expr(expr_id, value)) return 0.0;
  if(value.is_string) return strtod(value.text, NULL);
  return value.number;
}

static bool eval_expr(i16 expr_id, BasicValue& value) {
  if(expr_id < 0 || expr_id >= ast.expr_count) {
    value = make_number(0);
    return false;
  }

  const BasicExpr& e = ast.exprs[expr_id];
  switch(e.kind) {
    case ExprKind::NUMBER:
      value = make_number(e.number);
      return true;
    case ExprKind::STRING:
      value = make_string(e.text);
      return true;
    case ExprKind::NUM_VAR:
      value = make_number(numeric_vars[e.var_index]);
      return true;
    case ExprKind::STR_VAR:
      value = make_string(string_vars[e.var_index]);
      return true;
    case ExprKind::MK_REF:
      value = make_number(read_mk_ref(e.mk_ref, e.mk_reg));
      return true;
    case ExprKind::UNARY:
      value = make_number(e.op == BasicOp::NOT ? !basic_truth(eval_number(e.left)) : -eval_number(e.left));
      return true;
    case ExprKind::BINARY: {
      const double a = eval_number(e.left);
      const double b = eval_number(e.right);
      switch(e.op) {
        case BasicOp::ADD: value = make_number(a + b); return true;
        case BasicOp::SUB: value = make_number(a - b); return true;
        case BasicOp::MUL: value = make_number(a * b); return true;
        case BasicOp::DIV: value = make_number(b == 0.0 ? 0.0 : a / b); return true;
        case BasicOp::POW: value = make_number(pow(a, b)); return true;
        case BasicOp::EQ: value = make_number(basic_truth(a == b)); return true;
        case BasicOp::NE: value = make_number(basic_truth(a != b)); return true;
        case BasicOp::LT: value = make_number(basic_truth(a < b)); return true;
        case BasicOp::LE: value = make_number(basic_truth(a <= b)); return true;
        case BasicOp::GT: value = make_number(basic_truth(a > b)); return true;
        case BasicOp::GE: value = make_number(basic_truth(a >= b)); return true;
        case BasicOp::AND: value = make_number(basic_truth(a) && basic_truth(b)); return true;
        case BasicOp::OR: value = make_number(basic_truth(a) || basic_truth(b)); return true;
        case BasicOp::XOR: value = make_number((bool) basic_truth(a) != (bool) basic_truth(b)); return true;
        case BasicOp::NOT: break;
        case BasicOp::NONE: break;
      }
      value = make_number(0);
      return true;
    }
    case ExprKind::CALL:
    case ExprKind::MK_CALL:
      break;
    case ExprKind::NONE:
      break;
  }

  char name[BASIC_NAME_SIZE];
  basic_copy_name(name, e.text);
  for(u8 i = 0; i < e.arg_count && i < BASIC_MAX_ARGS; i++) {
    numeric_vars[i * 11] = eval_number(e.args[i]);
    numeric_var_set[i * 11] = true;
  }

  if(e.kind == ExprKind::CALL) {
    if(basic_streq(name, "SIN")) value = make_number(sin(eval_number(e.args[0])));
    else if(basic_streq(name, "COS")) value = make_number(cos(eval_number(e.args[0])));
    else if(basic_streq(name, "TG") || basic_streq(name, "TAN")) value = make_number(tan(eval_number(e.args[0])));
    else if(basic_streq(name, "ASIN")) value = make_number(asin(eval_number(e.args[0])));
    else if(basic_streq(name, "ACOS")) value = make_number(acos(eval_number(e.args[0])));
    else if(basic_streq(name, "ATG") || basic_streq(name, "ATAN")) value = make_number(atan(eval_number(e.args[0])));
    else if(basic_streq(name, "ABS")) value = make_number(fabs(eval_number(e.args[0])));
    else if(basic_streq(name, "INT")) value = make_number(floor(eval_number(e.args[0])));
    else if(basic_streq(name, "SQRT")) value = make_number(sqrt(eval_number(e.args[0])));
    else {
      const int program = find_program_by_name(name);
      if(program >= 0) {
        value = make_number(run_basic_function_call(program));
      } else {
        value = make_number(0);
      }
    }
    return true;
  }

  value = make_number(read_mk_ref((u8) MkRefKind::X, 0));
  return true;
}

static void assign_number_target(const BasicStmt& stmt, double value) {
  if((TargetKind) stmt.target_kind == TargetKind::MK_REF) {
    write_mk_ref(stmt.mk_ref, stmt.mk_reg, value);
    return;
  }
  numeric_vars[stmt.var_index] = value;
  numeric_var_set[stmt.var_index] = true;
}

static void assign_string_target(const BasicStmt& stmt, const char* value) {
  strncpy(string_vars[stmt.var_index], value, BASIC_STRING_SIZE);
  string_vars[stmt.var_index][BASIC_STRING_SIZE] = 0;
  string_var_set[stmt.var_index] = true;
}

static void value_to_display_text(const BasicValue& value, char* buffer, usize size) {
  if(value.is_string) {
    strncpy(buffer, value.text, size - 1);
    buffer[size - 1] = 0;
    return;
  }
  snprintf(buffer, size, "%.8g", value.number);
}

static double read_number_from_keyboard(const BasicStmt& stmt) {
  char buffer[17];
  char en_prompt[17];
  char ru_prompt[17];
  memset(buffer, 0, sizeof(buffer));
  u8 len = 0;
  while(true) {
    if((TargetKind) stmt.target_kind == TargetKind::NUM_VAR) {
      const char var = (char) ('A' + (stmt.var_index / 11));
      snprintf(en_prompt, sizeof(en_prompt), "IN %c", var);
      snprintf(ru_prompt, sizeof(ru_prompt), "ВВОД %c", var);
    } else if((TargetKind) stmt.target_kind == TargetKind::MK_REF) {
      strcpy(en_prompt, "IN .MK");
      strcpy(ru_prompt, "ВВОД MK");
    } else {
      strcpy(en_prompt, "IN");
      strcpy(ru_prompt, "ВВОД");
    }
    basic_message_i18n(en_prompt, ru_prompt, buffer, buffer);

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
      char ch = BASIC_key[key];
      if(ch == (char) LCD_NOT_EQU_CHAR || ch == (char) 0xA6) ch = '-';
      if(ch == '%' || ch == '?' || ch == ' ') continue;
      if(len < sizeof(buffer) - 1) {
        buffer[len++] = ch;
        buffer[len] = 0;
      }
    }
  }
  return strtod(buffer, NULL);
}

static bool load_mk_program_by_name(const char* name) {
  if(name[0] != 0 && basic_is_digit(name[0])) {
    const int slot = atoi(name);
    if(slot >= 0 && slot <= MAX_SLOT_FOR_PROGRAM) return Load((usize) slot);
  }

  char slot_name[SIZEOF_SLOT_NAME];
  for(usize slot = 0; slot <= MAX_SLOT_FOR_PROGRAM; slot++) {
    if(!IsOccupied(slot)) continue;
    if(ReadSlotName(slot, slot_name) == NULL) continue;
    if(basic_streq(slot_name, name)) return Load(slot);
  }
  return false;
}

static void save_mk_context(void) {
  mk_context.valid = true;
  static const stack stack_regs[4] = {stack::X, stack::Y, stack::Z, stack::T};
  for(int i = 0; i < 4; i++) {
    memset(&mk_context.stack_value[i], 0, sizeof(core_61::bcd_value));
    core_61::get_stack_register(stack_regs[i], mk_context.stack_value[i]);
  }
  for(int i = 0; i < 15; i++) {
    memset(mk_context.reg_value[i], 0, sizeof(mk_context.reg_value[i]));
    memcpy(mk_context.reg_value[i], &ringM[i * 42], 42);
  }
}

static void restore_mk_context(void) {
  if(!mk_context.valid) return;
  static const stack stack_regs[4] = {stack::X, stack::Y, stack::Z, stack::T};
  for(int i = 0; i < 4; i++) {
    core_61::set_stack_register(stack_regs[i], &mk_context.stack_value[i]);
  }
  for(int i = 0; i < 15; i++) {
    memcpy(&ringM[i * 42], mk_context.reg_value[i], 42);
  }
}

static bool execute_statement(i16 stmt_id, i16& pc, ForFrame for_stack[BASIC_FOR_STACK_DEPTH], i8& for_sp, int& steps);

static bool execute_statement(i16 stmt_id, i16& pc, ForFrame for_stack[BASIC_FOR_STACK_DEPTH], i8& for_sp, int& steps) {
  if(stmt_id < 0 || stmt_id >= ast.stmt_count) return false;
  if(++steps > BASIC_RUNTIME_STEPS_LIMIT) {
    basic_error("run limit");
    return false;
  }

  const BasicStmt& stmt = ast.stmts[stmt_id];
  switch(stmt.kind) {
    case StmtKind::NOP:
    case StmtKind::LABEL:
      pc = stmt.next;
      return true;
    case StmtKind::PRINT: {
      BasicValue value;
      eval_expr(stmt.expr0, value);
      char line[17];
      value_to_display_text(value, line, sizeof(line));
      MK61DisplayUpdate update(lcd);
      lcd.setCursor(0, 0);
      lcd.print("                ");
      lcd.setCursor(0, 0);
      lcd.print(line);
      pc = stmt.next;
      return true;
    }
    case StmtKind::INPUT_STMT:
      assign_number_target(stmt, read_number_from_keyboard(stmt));
      pc = stmt.next;
      return true;
    case StmtKind::ASSIGN_NUM:
      assign_number_target(stmt, eval_number(stmt.expr0));
      pc = stmt.next;
      return true;
    case StmtKind::ASSIGN_STR: {
      BasicValue value;
      eval_expr(stmt.expr0, value);
      if(value.is_string) assign_string_target(stmt, value.text);
      else {
        char temp[BASIC_STRING_SIZE + 1];
        snprintf(temp, sizeof(temp), "%.8g", value.number);
        assign_string_target(stmt, temp);
      }
      pc = stmt.next;
      return true;
    }
    case StmtKind::IF:
      if(basic_truth(eval_number(stmt.expr0))) {
        if(stmt.child0 >= 0) {
          const StmtKind child_kind = ast.stmts[stmt.child0].kind;
          i16 child_pc = stmt.child0;
          if(!execute_statement(stmt.child0, child_pc, for_stack, for_sp, steps)) return false;
          if(child_kind == StmtKind::GO) {
            pc = child_pc;
            return true;
          }
        }
      } else if(stmt.child1 >= 0) {
        const StmtKind child_kind = ast.stmts[stmt.child1].kind;
        i16 child_pc = stmt.child1;
        if(!execute_statement(stmt.child1, child_pc, for_stack, for_sp, steps)) return false;
        if(child_kind == StmtKind::GO) {
          pc = child_pc;
          return true;
        }
      }
      pc = stmt.next;
      return true;
    case StmtKind::FOR: {
      numeric_vars[stmt.var_index] = eval_number(stmt.expr0);
      numeric_var_set[stmt.var_index] = true;
      if(for_sp + 1 >= BASIC_FOR_STACK_DEPTH) {
        basic_error("FOR stack");
        return false;
      }
      ForFrame& frame = for_stack[++for_sp];
      frame.for_stmt = stmt_id;
      frame.var_index = stmt.var_index;
      frame.end_value = eval_number(stmt.expr1);
      frame.step_value = (stmt.expr2 >= 0) ? eval_number(stmt.expr2) : 1.0;
      pc = stmt.next;
      return true;
    }
    case StmtKind::NXT: {
      if(for_sp < 0) {
        basic_error("NXT stack");
        return false;
      }
      ForFrame& frame = for_stack[for_sp];
      numeric_vars[frame.var_index] += frame.step_value;
      const double value = numeric_vars[frame.var_index];
      const bool again = (frame.step_value >= 0) ? (value <= frame.end_value) : (value >= frame.end_value);
      if(again) {
        pc = ast.stmts[frame.for_stmt].next;
      } else {
        for_sp--;
        pc = stmt.next;
      }
      return true;
    }
    case StmtKind::DO_BEGIN:
      pc = stmt.next;
      return true;
    case StmtKind::DO_WH:
      pc = basic_truth(eval_number(stmt.expr0)) ? ast.stmts[stmt.jump].next : stmt.next;
      return true;
    case StmtKind::WHILE_BEGIN:
      pc = basic_truth(eval_number(stmt.expr0)) ? stmt.next : ast.stmts[stmt.jump].next;
      return true;
    case StmtKind::WHILE_END:
      pc = stmt.jump;
      return true;
    case StmtKind::GO: {
      const i16 label = ast_find_label(ast, stmt.label);
      if(label < 0) {
        basic_error("no label");
        return false;
      }
      pc = ast.stmts[label].next;
      return true;
    }
    case StmtKind::CLR:
      basic_clear_vars();
      pc = stmt.next;
      return true;
    case StmtKind::LD:
      if(!load_mk_program_by_name(stmt.text)) basic_error("LD failed");
      pc = stmt.next;
      return true;
    case StmtKind::HLT:
      return false;
    case StmtKind::MK_SAVE:
      save_mk_context();
      pc = stmt.next;
      return true;
    case StmtKind::MK_RESTORE:
      restore_mk_context();
      pc = stmt.next;
      return true;
    case StmtKind::MK_BIND: {
      const int program = find_program_by_name(stmt.text);
      if(program >= 0) basic_step_program[stmt.mk_step] = (i8) program;
      else basic_error("mk name?");
      pc = stmt.next;
      return true;
    }
    case StmtKind::CALL: {
      BasicValue value;
      eval_expr(stmt.expr0, value);
      pc = stmt.next;
      return true;
    }
  }
  pc = stmt.next;
  return true;
}

void RunBasic(int BasicN) {
  if(!compile_program_slot(BasicN)) return;

  ForFrame for_stack[BASIC_FOR_STACK_DEPTH];
  i8 for_sp = -1;
  i16 pc = ast.first_stmt;
  int steps = 0;

  while(pc >= 0) {
    if(!execute_statement(pc, pc, for_stack, for_sp, steps)) break;
  }
}

bool BasicRunAssignedForStep(int mk61_step) {
  if(mk61_step < 0 || mk61_step >= (int) core_61::MAX_PROGRAM_STEP) return false;
  const int program = basic_step_program[mk61_step];
  if(program < 0 || program >= BASIC_PROGRAM_COUNT || !programs[program].used) return false;
  RunBasic(program);
  return true;
}

bool BasicHasAssignedStep(int mk61_step) {
  if(mk61_step < 0 || mk61_step >= (int) core_61::MAX_PROGRAM_STEP) return false;
  const int program = basic_step_program[mk61_step];
  return program >= 0 && program < BASIC_PROGRAM_COUNT && programs[program].used;
}

bool BasicIsReady(void) {
  return basic_program_count() > 0;
}

void InitBasic(void) {
  memset(programs, 0, sizeof(programs));
  for(usize i = 0; i < core_61::MAX_PROGRAM_STEP; i++) basic_step_program[i] = -1;
  basic_clear_vars();
  memset(&mk_context, 0, sizeof(mk_context));
  ast_reset(ast);
  NextBasic = -1;
}

int AssignBasic(void) {
  const int program = select_basic_program(false);
  if(program < 0) return -1;
  const int step = core_61::get_IP();
  if(step >= 0 && step < (int) core_61::MAX_PROGRAM_STEP) {
    basic_step_program[step] = (i8) program;
    char line[17];
    snprintf(line, sizeof(line), basic_language_is_ru() ? "шаг %d" : "step %d", step);
    basic_message_i18n("BASIC assigned", "БЕЙСИК связан", line, line);
    delay(900);
  }
  return program;
}

bool BASIC_library_select(void) {
  const int program = select_basic_program(false);
  if(program >= 0) RunBasic(program);
  return true;
}

static void draw_basic_editor(const char* source, u16 len, u16 cursor, u16 window, int slot) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();
  lcd.setCursor(0, 0);
  for(u8 i = 0; i < 16; i++) {
    const u16 pos = window + i;
    lcd.write((u8) ((pos < len) ? source[pos] : ' '));
  }
  lcd.setCursor((u8) (cursor - window), 0);
  lcd.write(CURSOR_ASCII);
  if(slot == BASIC_PROGRAM_COUNT) basic_print_text_at(0, 1, "NEW", "НОВАЯ", 5);
  else {
    char display_name[22];
    basic_display_program_name(programs[slot].name, display_name, sizeof(display_name));
    basic_print_text_at(0, 1, programs[slot].name, display_name, 10);
  }
  lcd.setCursor(10, 1);
  lcd.print(cursor);
  lcd.print('/');
  lcd.print(len);
}

static bool store_edited_program(int slot, char* source) {
  if(slot == BASIC_PROGRAM_COUNT) {
    slot = find_free_program();
    if(slot < 0) return basic_error("program full");
  }

  if(!compile_source(source, ast)) {
    return false;
  }

  strncpy(programs[slot].source, source, BASIC_SOURCE_SIZE - 1);
  programs[slot].source[BASIC_SOURCE_SIZE - 1] = 0;
  programs[slot].source_len = (u16) strlen(programs[slot].source);
  basic_copy_name(programs[slot].name, ast.program_name);
  if(programs[slot].name[0] == 0) snprintf(programs[slot].name, sizeof(programs[slot].name), "BASIC%d", slot);
  programs[slot].used = true;
  NextBasic = slot;
  display_ast_ok(programs[slot]);
  return true;
}

static bool basic_cursor_inside_string(const char* source, u16 cursor) {
  bool inside = false;
  for(u16 i = 0; i < cursor && source[i] != 0; i++) {
    if(source[i] == '"') inside = !inside;
  }
  return inside;
}

static bool basic_token_equals(const char* source, int start, int end, const char* token) {
  int pos = start;
  while(pos < end && *token != 0) {
    if(basic_upper(source[pos]) != basic_upper(*token)) return false;
    pos++;
    token++;
  }
  return pos == end && *token == 0;
}

static bool basic_cursor_expects_statement(const char* source, u16 cursor) {
  if(basic_cursor_inside_string(source, cursor)) return false;

  int pos = (int) cursor - 1;
  while(pos >= 0 && (source[pos] == ' ' || source[pos] == '\t')) pos--;
  if(pos < 0) return true;
  if(source[pos] == ':' || source[pos] == ';') return true;

  const int end = pos + 1;
  while(pos >= 0 && (basic_is_alpha(source[pos]) || basic_is_digit(source[pos]))) pos--;
  const int start = pos + 1;
  if(start >= end) return false;

  return basic_token_equals(source, start, end, "TH") ||
         basic_token_equals(source, start, end, "THEN") ||
         basic_token_equals(source, start, end, "EL") ||
         basic_token_equals(source, start, end, "ELSE");
}

static const char* basic_statement_insert_text(i32 key_code) {
  switch(key_code) {
    case BASIC_SCAN_PRINT: return "? ";
    case BASIC_SCAN_B_UP:  return "IN ";
    case BASIC_SCAN_USER:  return "IF ";
    case BASIC_SCAN_XP:    return "FOR ";
    case BASIC_SCAN_PX:    return "NXT ";
    case BASIC_SCAN_JMP:   return "GO ";
    case BASIC_SCAN_RUN:   return "HLT ";
    case BASIC_SCAN_RET:   return "END";
    case BASIC_SCAN_SF:    return "DO";
    case BASIC_SCAN_SB:    return "WH ";
    case BASIC_SCAN_LOAD:  return "LD ";
    case BASIC_SCAN_SAVE:  return "CLR";
    default: break;
  }
  return NULL;
}

static const char* basic_editor_insert_text_for_key(BasicEditShift shift, i32 key_code, const char* source, u16 cursor) {
  if(key_code < 0 || key_code >= 40) return NULL;

  switch(shift) {
    case BasicEditShift::NONE:
      if(basic_cursor_expects_statement(source, cursor)) {
        const char* statement_text = basic_statement_insert_text(key_code);
        if(statement_text != NULL) return statement_text;
      }
      return BASIC_key_text[key_code];
    case BasicEditShift::ALPHA:
      return BASIC_alpha_key_text[key_code];
    case BasicEditShift::K:
      return BASIC_Kshift_key_text[key_code];
  }

  return NULL;
}

static bool basic_editor_insert_text(char* source, u16& len, u16& cursor, const char* text) {
  if(text == NULL || text[0] == 0) return false;
  const usize text_len = strlen(text);
  if((usize) len + text_len >= BASIC_SOURCE_SIZE) return false;
  memmove(&source[cursor + text_len], &source[cursor], len - cursor + 1);
  memcpy(&source[cursor], text, text_len);
  cursor = (u16) (cursor + text_len);
  len = (u16) (len + text_len);
  return true;
}

void EditBasic(void) {
  int slot = select_basic_program(true);
  if(slot < 0) return;

  char source[BASIC_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  if(slot < BASIC_PROGRAM_COUNT && programs[slot].used) strncpy(source, programs[slot].source, sizeof(source) - 1);

  u16 len = (u16) strlen(source);
  u16 cursor = len;
  u16 window = (cursor > 15) ? cursor - 15 : 0;
  BasicEditShift shift = BasicEditShift::NONE;
  u32 blink_time = millis() + CURSOR_BLINK_MS;

  kbd::debounce_init();
  while(true) {
    const u32 now = millis();
    draw_basic_editor(source, len, cursor, window, slot);
    if(now >= blink_time) blink_time = now + CURSOR_BLINK_MS;

    kbd::scan_and_debounced();
    i32 key_code = kbd::get_key(key_state::PRESSED);
    if(key_code < 0) {
      delay(30);
      continue;
    }

    const bool shifted_key = shift != BasicEditShift::NONE;

    if(!shifted_key && (key_code == KEY_K || key_code == KEY_ALPHA)) {
      shift = (key_code == KEY_K) ? BasicEditShift::K : BasicEditShift::ALPHA;
      continue;
    }

    if(!shifted_key && (key_code == KEY_ESC || key_code == KEY_ESC_PRESS)) {
      store_edited_program(slot, source);
      return;
    }

    if(!shifted_key && (key_code == KEY_LEFT || key_code == KEY_LEFT_PRESS)) {
      if(cursor > 0) cursor--;
    } else if(!shifted_key && (key_code == KEY_RIGHT || key_code == KEY_RIGHT_PRESS)) {
      if(cursor < len) cursor++;
    } else if(!shifted_key && key_code == KEY_DEGREE) {
      if(cursor > 0) {
        memmove(&source[cursor - 1], &source[cursor], len - cursor + 1);
        cursor--;
        len--;
      }
    } else if(!shifted_key && key_code == 0) {
      memset(source, 0, sizeof(source));
      len = 0;
      cursor = 0;
    } else if(!shifted_key && (key_code == KEY_OK || key_code == KEY_OK_PRESS)) {
      if(len < BASIC_SOURCE_SIZE - 1) {
        memmove(&source[cursor + 1], &source[cursor], len - cursor + 1);
        source[cursor++] = ':';
        len++;
      }
    } else {
      basic_editor_insert_text(source, len, cursor, basic_editor_insert_text_for_key(shift, key_code, source, cursor));
    }

    shift = BasicEditShift::NONE;
    if(cursor < window) window = cursor;
    if(cursor > window + 15) window = cursor - 15;
  }
}

static bool BASIC_clear_data(void) {
  basic_clear_vars();
  basic_message_i18n("BASIC data", "Данные", "cleared", "очищены");
  delay(700);
  return true;
}

static bool BASIC_assign_menu(void) {
  AssignBasic();
  return true;
}

static bool BASIC_run_menu(void) {
  return BASIC_library_select();
}

static bool BASIC_edit_menu(void) {
  EditBasic();
  return true;
}

static constexpr t_punct BASIC_EDIT_PUNCT   = {.size = 10, .action = &BASIC_edit_menu,  .text = "Edit BASIC"};
static constexpr t_punct BASIC_RUN_PUNCT    = {.size = 9,  .action = &BASIC_run_menu,   .text = "Run BASIC"};
static constexpr t_punct BASIC_ASSIGN_PUNCT = {.size = 12, .action = &BASIC_assign_menu,.text = "Assign STEP"};
static constexpr t_punct BASIC_CLEAR_PUNCT  = {.size = 10, .action = &BASIC_clear_data, .text = "Clear DATA"};

#ifndef BASIC_HOST_TEST
static constexpr t_punct RU_BASIC_EDIT_PUNCT   = {.size = 15, .action = &BASIC_edit_menu,  .text = "Правка"};
static constexpr t_punct RU_BASIC_RUN_PUNCT    = {.size = 15, .action = &BASIC_run_menu,   .text = "Запуск"};
static constexpr t_punct RU_BASIC_ASSIGN_PUNCT = {.size = 15, .action = &BASIC_assign_menu,.text = "Назначить шаг"};
static constexpr t_punct RU_BASIC_CLEAR_PUNCT  = {.size = 15, .action = &BASIC_clear_data, .text = "Сброс данных"};
#endif

bool BASIC_menu_select(void) {
  t_punct* items[] = {
#ifndef BASIC_HOST_TEST
    (t_punct*) (basic_language_is_ru() ? &RU_BASIC_EDIT_PUNCT : &BASIC_EDIT_PUNCT),
    (t_punct*) (basic_language_is_ru() ? &RU_BASIC_RUN_PUNCT : &BASIC_RUN_PUNCT),
    (t_punct*) (basic_language_is_ru() ? &RU_BASIC_ASSIGN_PUNCT : &BASIC_ASSIGN_PUNCT),
    (t_punct*) (basic_language_is_ru() ? &RU_BASIC_CLEAR_PUNCT : &BASIC_CLEAR_PUNCT)
#else
    (t_punct*) &BASIC_EDIT_PUNCT,
    (t_punct*) &BASIC_RUN_PUNCT,
    (t_punct*) &BASIC_ASSIGN_PUNCT,
    (t_punct*) &BASIC_CLEAR_PUNCT
#endif
  };
  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  menu.select();
  return true;
}

#ifdef BASIC_SELF_TEST
extern "C" void BasicTestReset(void) {
  InitBasic();
  lcd.clear();
  ast_call_sp = 0;
  #ifdef BASIC_HOST_TEST
    memset(host_stack_value, 0, sizeof(host_stack_value));
    memset(host_register_value, 0, sizeof(host_register_value));
    memset(ringM, 0, sizeof(ringM));
  #endif
}

extern "C" bool BasicTestCompile(const char* source) {
  return compile_source(source, ast);
}

extern "C" const char* BasicTestError(void) {
  return ast.error;
}

extern "C" int BasicTestAddProgram(const char* source) {
  const int slot = find_free_program();
  if(slot < 0) return -1;

  strncpy(programs[slot].source, source, BASIC_SOURCE_SIZE - 1);
  programs[slot].source[BASIC_SOURCE_SIZE - 1] = 0;
  programs[slot].source_len = (u16) strlen(programs[slot].source);

  if(!compile_source(programs[slot].source, ast)) {
    memset(&programs[slot], 0, sizeof(programs[slot]));
    return -1;
  }

  basic_copy_name(programs[slot].name, ast.program_name);
  if(programs[slot].name[0] == 0) snprintf(programs[slot].name, sizeof(programs[slot].name), "BASIC%d", slot);
  programs[slot].used = true;
  NextBasic = slot;
  return slot;
}

extern "C" void BasicTestRun(int slot) {
  lcd.clear();
  RunBasic(slot);
}

extern "C" double BasicTestNumber(const char* name) {
  if(name == NULL) return 0.0;
  const int idx = variable_index_from_name(name);
  return (idx < 0) ? 0.0 : numeric_vars[idx];
}

extern "C" const char* BasicTestString(const char* name) {
  if(name == NULL) return "";
  if(name[0] == '$') name++;
  const int idx = variable_index_from_name(name);
  return (idx < 0) ? "" : string_vars[idx];
}

extern "C" void BasicTestEditSequence(const int* keys, int count, char* out, int size) {
  if(out == NULL || size <= 0) return;

  char source[BASIC_SOURCE_SIZE];
  memset(source, 0, sizeof(source));
  u16 len = 0;
  u16 cursor = 0;
  BasicEditShift shift = BasicEditShift::NONE;

  for(int i = 0; i < count; i++) {
    const i32 key_code = keys[i];
    const bool shifted_key = shift != BasicEditShift::NONE;

    if(!shifted_key && (key_code == KEY_K || key_code == KEY_ALPHA)) {
      shift = (key_code == KEY_K) ? BasicEditShift::K : BasicEditShift::ALPHA;
      continue;
    }

    if(!shifted_key && (key_code == KEY_OK || key_code == KEY_OK_PRESS)) {
      basic_editor_insert_text(source, len, cursor, ":");
    } else {
      basic_editor_insert_text(source, len, cursor, basic_editor_insert_text_for_key(shift, key_code, source, cursor));
    }
    shift = BasicEditShift::NONE;
  }

  strncpy(out, source, (usize) size - 1);
  out[size - 1] = 0;
}

extern "C" const char* BasicTestLcdLine(int row) {
  return lcd.line((u8) row);
}

extern "C" double BasicTestMkX(void) {
  return read_mk_ref((u8) MkRefKind::X, 0);
}

extern "C" bool BasicTestStepAssigned(int step) {
  return BasicHasAssignedStep(step);
}
#endif

#endif
