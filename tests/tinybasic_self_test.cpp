#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>

#include "tinybasic.hpp"

extern "C" void TinyBasicTestReset(void);
extern "C" bool TinyBasicTestCompile(const char* source);
extern "C" const char* TinyBasicTestError(void);
extern "C" int TinyBasicTestAddProgram(const char* source, const char* name);
extern "C" void TinyBasicTestSetInput(double value);
extern "C" void TinyBasicTestSetInputExpression(const char* expression);
extern "C" void TinyBasicTestSetInputs(const double* values, int count);
extern "C" const char* TinyBasicTestLastPrompt(void);
extern "C" void TinyBasicTestRun(int slot);
extern "C" double TinyBasicTestNumber(const char* name);
extern "C" double TinyBasicTestMkX(void);
extern "C" double TinyBasicTestMkRegister(int reg);
extern "C" void TinyBasicTestSetRfEnabled(bool enabled);
extern "C" void TinyBasicTestSetAngleMode(int mode);
extern "C" const char* TinyBasicTestLcdLine(int row);
extern "C" void TinyBasicTestEditSequence(const int* keys, int count, char* out, int size);
extern "C" void TinyBasicTestSetAlphaHeld(bool held);
extern "C" void TinyBasicTestSetPauseEsc(bool enabled);
extern "C" void TinyBasicTestFormatNumber(double value, char* out, int size);
extern "C" bool TinyBasicTestRunResult(int slot);
extern "C" void TinyBasicTestClearData(void);
extern "C" int TinyBasicTestWaitCount(void);
extern "C" bool TinyBasicTestStoreEdited(int slot, char* source, const char* name);
extern "C" void TinyBasicTestSetGeometry(int cols, int rows);
static constexpr int KEY_K = 37;
static constexpr int KEY_OK = 29;
static constexpr int KEY_CX = 0;
static constexpr int KEY_PP = 25;
static constexpr int KEY_LEFT = 34;
static constexpr int KEY_ALPHA = 38;
static constexpr int KEY_RADIAN = 14;
static constexpr int KEY_RET = 31;

static void test_compile_and_print(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 A=14/5\n"
    "20 PRINT A\n"
    "30 END\n",
    "DIV");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "2.8", 3) == 0);
}

static void test_line_index_orders_source_and_rejects_duplicates(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "30 END\n"
    "20 A=A+1\n"
    "10 A=1\n",
    "ORDER");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 2.0) < 0.000001);

  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 A=1\n10 A=2\n"));
}

static void test_if_and_goto(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 A=1\n"
    "20 IF A>0 GOTO 50\n"
    "30 PRINT \"BAD\"\n"
    "40 END\n"
    "50 PRINT \"OK\"\n"
    "60 END\n",
    "IF");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "OK", 2) == 0);
}

static void test_gosub(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 A=3\n"
    "20 GOSUB 100\n"
    "30 END\n"
    "100 A=A*A\n"
    "110 RETURN\n",
    "SUB");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestNumber("A") - 9.0) < 0.000001);
}

static void test_for_next(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 S=0\n"
    "20 FOR I=1 TO 4\n"
    "30 S=S+I\n"
    "40 NEXT I\n"
    "50 PRINT S\n",
    "FOR");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestNumber("S") - 10.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "10", 2) == 0);
}

static void test_input(void) {
  TinyBasicTestReset();
  TinyBasicTestSetInput(7.0);
  const int slot = TinyBasicTestAddProgram(
    "10 INPUT \"A\", A\n"
    "20 PRINT A*2\n",
    "IN");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestNumber("A") - 7.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "14", 2) == 0);

  // Prompt storage is independent of the current viewport width.  The device
  // renderer can wrap it over several graphical rows; truncating it here used
  // to turn High Noon's first question into just "DO YOU WANT INST".
  TinyBasicTestReset();
  TinyBasicTestSetInput(0.0);
  const char* const question = "DO YOU WANT INSTRUCTIONS? 1 YES 0 NO";
  const int long_prompt = TinyBasicTestAddProgram(
    "10 INPUT \"DO YOU WANT INSTRUCTIONS? 1 YES 0 NO\", A\n",
    "LONGIN");
  assert(long_prompt >= 0);
  assert(TinyBasicTestRunResult(long_prompt));
  assert(std::strcmp(TinyBasicTestLastPrompt(), question) == 0);
}

static void test_bad_expression_tail(void) {
  TinyBasicTestReset();
  assert(!TinyBasicTestCompile(
    "10 A=1 BAD\n"
    "20 PRINT A\n"));
  assert(std::strcmp(TinyBasicTestError(), "WHAT?") == 0);
}

static void test_compile_rejects_invalid_statements(void) {
  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 A=\n"));
  assert(std::strcmp(TinyBasicTestError(), "WHAT?") == 0);

  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 THIS IS NOT BASIC\n"));
  assert(!TinyBasicTestCompile("10PRINT \"NO SEPARATOR\"\n"));
  assert(!TinyBasicTestCompile("10 IF 0 GARBAGE\n20 END\n"));
  assert(!TinyBasicTestCompile("10 PRINT \"OK\" GARBAGE\n"));
  assert(!TinyBasicTestCompile("10 SIN=1\n"));
  assert(!TinyBasicTestCompile("10 GOTO 20:PRINT \"BAD\"\n20 END\n"));
  assert(!TinyBasicTestCompile("10 INPUT \"PROMPT ONLY\"\n"));
  assert(!TinyBasicTestCompile(
    "10 A=------------------------------------------------------------------------"
    "----------------------------------------1\n"));
  assert(!TinyBasicTestCompile(
    "10 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 "
    "IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 A=1\n"));

  char oversized[3700];
  std::memset(oversized, 'X', sizeof(oversized));
  std::memcpy(oversized, "10 REM ", 7);
  oversized[sizeof(oversized) - 1] = 0;
  assert(!TinyBasicTestCompile(oversized));
  assert(std::strcmp(TinyBasicTestError(), "SORRY") == 0);
}

static void test_keyword_abbreviations(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 A=0\n"
    "20 F. I=1 TO 2\n"
    "30 A=A+I\n"
    "40 N. I\n"
    "50 I. A=3 GOS. 100\n"
    "60 P. A\n"
    "70 E.\n"
    "100 A=A+1\n"
    "110 R.\n",
    "ABBREV");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 4.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "4", 1) == 0);
}

static void test_boolean_truth_table(void) {
  struct Case {
    const char* expression;
    double expected;
  };
  const Case cases[] = {
    {"0 AND 0", 0.0}, {"0 AND 1", 0.0}, {"1 AND 0", 0.0}, {"1 AND 1", 1.0},
    {"0 OR 0", 0.0},  {"0 OR 1", 1.0},  {"1 OR 0", 1.0},  {"1 OR 1", 1.0},
    {"0 XOR 0", 0.0}, {"0 XOR 1", 1.0}, {"1 XOR 0", 1.0}, {"1 XOR 1", 0.0}
  };
  for(const Case& item : cases) {
    TinyBasicTestReset();
    char source[64];
    std::snprintf(source, sizeof(source), "10 A=%s\n", item.expression);
    const int slot = TinyBasicTestAddProgram(source, "BOOL");
    assert(slot >= 0);
    assert(TinyBasicTestRunResult(slot));
    assert(std::fabs(TinyBasicTestNumber("A") - item.expected) < 0.000001);
  }
}

static void test_expression_semantics(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 A=-2^2\n"
    "20 B=2^3^2\n"
    "30 C=ROUND(-1.5)\n"
    "40 D=ROUND(1.5)\n"
    "50 E=2+3*4\n"
    "60 F=(2+3)*4\n"
    "70 G=5 MOD 2\n"
    "80 H=1 OR 0 AND 0\n"
    "90 I=0 OR 1 AND 0\n"
    "100 J=2+3=5\n"
    "110 K=1<2<1\n"
    "120 L=2^-2^3\n"
    "130 M=3<=3\n"
    "140 N=3>=4\n"
    "150 O=3#4\n"
    "160 P=ROUND(-1.4)\n"
    "170 Q=ROUND(-.5)\n"
    "180 R=ROUND(.5)\n",
    "EXPR");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") + 4.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("B") - 64.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("C") + 2.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("D") - 2.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("E") - 14.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("F") - 20.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("G") - 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("H") - 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("I")) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("J") - 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("K")) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("L") - 0.015625) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("M") - 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("N")) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("O") - 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("P") + 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("Q") + 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("R") - 1.0) < 0.000001);

  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 A=SIN(0,123)\n"));
  assert(!TinyBasicTestCompile("10 A=MAX(1)\n"));
  assert(!TinyBasicTestCompile("10 A=MAX(1,2,3)\n"));
  assert(!TinyBasicTestCompile("10 A=PI.\n"));
}

static void test_cls_and_pause(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
      "10 PRINT \"OLD\"\n"
      "20 PRINT \"STALE\"\n"
      "30 CLS\n"
      "40 PRINT \"NEW\"\n"
      "50 PAUSE\n"
      "60 A=1\n",
      "SCREEN");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::strncmp(TinyBasicTestLcdLine(0), "NEW", 3) == 0);
  assert(TinyBasicTestLcdLine(1)[0] == ' ');
  assert(std::fabs(TinyBasicTestNumber("A") - 1.0) < 0.000001);

  TinyBasicTestReset();
  assert(TinyBasicTestCompile("10 C.\n20 PAU.\n"));
  assert(!TinyBasicTestCompile("10 CLS 1\n"));
  assert(!TinyBasicTestCompile("10 PAUSE 1\n"));
}

static void test_zero_trip_for(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 S=0\n"
    "20 FOR I=2 TO 1\n"
    "30 S=S+1\n"
    "40 NEXT I: S=S+10\n"
    "50 END\n",
    "ZEROFOR");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("S") - 10.0) < 0.000001);

  TinyBasicTestReset();
  const int nested = TinyBasicTestAddProgram(
    "10 S=0\n"
    "20 FOR I=3 TO 1\n"
    "30 FOR J=1 TO 2\n"
    "40 S=S+1\n"
    "50 NEXT J\n"
    "60 NEXT I:S=9\n",
    "NESTZERO");
  assert(nested >= 0);
  assert(TinyBasicTestRunResult(nested));
  assert(std::fabs(TinyBasicTestNumber("S") - 9.0) < 0.000001);
}

static void test_print_syntax_and_spacing(void) {
  TinyBasicTestReset();
  int slot = TinyBasicTestAddProgram("10 PRINT \"  X  \"\n", "SPACES");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::strncmp(TinyBasicTestLcdLine(0), "  X  ", 5) == 0);

  TinyBasicTestReset();
  slot = TinyBasicTestAddProgram("10 PRINT \"A\",\"B\"\n", "TABS");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::strncmp(TinyBasicTestLcdLine(0), "A       B", 9) == 0);

  TinyBasicTestReset();
  TinyBasicTestSetGeometry(8, 4);
  slot = TinyBasicTestAddProgram(
    "10 PRINT \"ONE TWO THREE FOUR\"\n",
    "WRAPPRINT");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::strncmp(TinyBasicTestLcdLine(0), "ONE TWO", 7) == 0);
  assert(std::strncmp(TinyBasicTestLcdLine(1), "THREE", 5) == 0);
  assert(std::strncmp(TinyBasicTestLcdLine(2), "FOUR", 4) == 0);

  TinyBasicTestReset();
  TinyBasicTestSetGeometry(5, 4);
  slot = TinyBasicTestAddProgram(
    "10 PRINT \"ABCDEFGHIJK\"\n",
    "HARDWRAP");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::strncmp(TinyBasicTestLcdLine(0), "ABCDE", 5) == 0);
  assert(std::strncmp(TinyBasicTestLcdLine(1), "FGHIJ", 5) == 0);
  assert(TinyBasicTestLcdLine(2)[0] == 'K');

  TinyBasicTestReset();
  char source[160];
  std::strcpy(source, "10 PRINT \"");
  const int prefix = (int) std::strlen(source);
  std::memset(source + prefix, 'X', 96);
  std::strcpy(source + prefix + 96, "\"\n");
  slot = TinyBasicTestAddProgram(source, "LONGPRINT");
  assert(slot >= 0);
  assert(!TinyBasicTestRunResult(slot));
  assert(std::strcmp(TinyBasicTestError(), "SORRY") == 0);
}

static void test_runtime_math_errors_are_safe(void) {
  TinyBasicTestReset();
  int slot = TinyBasicTestAddProgram("10 A=RND(1E100)\n", "BIGRND");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(TinyBasicTestNumber("A") >= 1.0);
  assert(TinyBasicTestNumber("A") <= 1E100);

  TinyBasicTestReset();
  slot = TinyBasicTestAddProgram("10 A=RND(SQRT(-1))\n", "NANRND");
  assert(slot >= 0);
  assert(!TinyBasicTestRunResult(slot));
  assert(std::strcmp(TinyBasicTestError(), "HOW?") == 0);

  TinyBasicTestReset();
  slot = TinyBasicTestAddProgram("10 GOTO SQRT(-1)\n", "NANGOTO");
  assert(slot >= 0);
  assert(!TinyBasicTestRunResult(slot));
  assert(std::strcmp(TinyBasicTestError(), "HOW?") == 0);

  TinyBasicTestReset();
  slot = TinyBasicTestAddProgram("10 PRINT \"X\";:A=1/0\n", "ERRLCD");
  assert(slot >= 0);
  assert(!TinyBasicTestRunResult(slot));
  assert(std::strncmp(TinyBasicTestLcdLine(0), "HOW?", 4) == 0);

  TinyBasicTestReset();
  slot = TinyBasicTestAddProgram("10 .X=1E100\n", "MKOVER");
  assert(slot >= 0);
  assert(!TinyBasicTestRunResult(slot));
  assert(std::strcmp(TinyBasicTestError(), "HOW?") == 0);
}

static void test_variables_persist_until_clear(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram("10 A=A+1\n", "PERSIST");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 1.0) < 0.000001);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 2.0) < 0.000001);
  TinyBasicTestClearData();
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 1.0) < 0.000001);
}

static void test_run_api_reports_runtime_failure(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram("10 A=1/0\n", "FAILAPI");
  assert(slot >= 0);
  assert(!RunTinyBasicProgram("FAILAPI"));
  assert(std::strcmp(TinyBasicTestError(), "HOW?") == 0);
  assert(TinyBasicTestWaitCount() == 1);
}

static void test_m61_mode_esc_at_pause_is_silent_stop(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
      "10 PRINT \"GAME\"\n"
      "20 PAUSE\n"
      "30 A=1\n",
      "M61ESC");
  assert(slot >= 0);
  TinyBasicTestSetPauseEsc(true);
  const TinyBasicRunStatus status = RunTinyBasicProgramStatus(
      (u16) slot, TinyBasicRunMode::M61_SCENARIO);
  TinyBasicTestSetPauseEsc(false);

  assert(status == TinyBasicRunStatus::STOPPED);
  assert(std::fabs(TinyBasicTestNumber("A")) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "GAME", 4) == 0);
  assert(TinyBasicTestWaitCount() == 0);
}

static void test_failed_edit_keeps_previous_program(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram("10 A=5\n", "EDITSAFE");
  assert(slot >= 0);
  char invalid[] = "10 A=\n";
  assert(!TinyBasicTestStoreEdited(slot, invalid, "EDITSAFE"));
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 5.0) < 0.000001);
}

static void test_editor_has_no_operator_macros(void) {
  TinyBasicTestReset();
  char out[64];

  const int print_key_without_sms[] = {KEY_RADIAN};
  TinyBasicTestEditSequence(print_key_without_sms, 1, out, sizeof(out));
  assert(std::strcmp(out, "") == 0);

  const int colon_and_semicolon[] = {KEY_K, KEY_OK, KEY_K, KEY_RET};
  TinyBasicTestEditSequence(colon_and_semicolon, 4, out, sizeof(out));
  assert(std::strcmp(out, ":;") == 0);
}

static void test_editor_cx_backspace_and_f_cx_clear_line(void) {
  TinyBasicTestReset();
  char out[32];

  const int cx[] = {21, 20, KEY_CX};
  TinyBasicTestEditSequence(cx, 3, out, sizeof(out));
  assert(std::strcmp(out, "1") == 0);

  const int f_left_is_not_backspace[] = {21, 20, KEY_ALPHA, KEY_LEFT};
  TinyBasicTestEditSequence(f_left_is_not_backspace, 4, out, sizeof(out));
  assert(std::strcmp(out, "10") == 0);

  const int clear_then_remove_line[] = {
    21, 20, KEY_OK, 16, 20, KEY_ALPHA, KEY_CX, KEY_ALPHA, KEY_CX
  };
  TinyBasicTestEditSequence(clear_then_remove_line, 9, out, sizeof(out));
  assert(std::strcmp(out, "10") == 0);

  TinyBasicTestSetAlphaHeld(true);
  const int held_f_cx[] = {21, 20, 16, KEY_CX};
  TinyBasicTestEditSequence(held_f_cx, 4, out, sizeof(out));
  TinyBasicTestSetAlphaHeld(false);
  assert(std::strcmp(out, "") == 0);
}

static void test_editor_pp_is_space(void) {
  TinyBasicTestReset();
  char out[8];
  const int pp[] = {KEY_PP};
  TinyBasicTestEditSequence(pp, 1, out, sizeof(out));
  assert(std::strcmp(out, " ") == 0);
}

static void expect_format(double value, const char* expected) {
  char out[32];
  TinyBasicTestFormatNumber(value, out, sizeof(out));
  if(std::strcmp(out, expected) != 0) {
    std::printf("format %.17g: got \"%s\", want \"%s\"\n", value, out, expected);
    assert(false);
  }
}

// Форматировщик прошивки не должен зависеть от поддержки float в printf
// (newlib-nano компонуется без неё), поэтому здесь он сравнивается со старым
// поведением "%.10g".
static void test_format_number(void) {
  expect_format(0.0, "0");
  expect_format(1.0, "1");
  expect_format(-1.0, "-1");
  expect_format(2.8, "2.8");
  expect_format(14.0 / 5.0, "2.8");
  expect_format(0.5, "0.5");
  expect_format(-0.125, "-0.125");
  expect_format(10.0, "10");
  expect_format(1234567890.0, "1234567890");
  expect_format(0.0001, "0.0001");
  expect_format(1.0 / 3.0, "0.3333333333");
  expect_format(-2.0 / 3.0, "-0.6666666667");
  expect_format(12345678901.0, "1.23456789E+10");
  expect_format(0.00001, "1E-5");
  expect_format(-0.0000123, "-1.23E-5");
  expect_format(9.99999999999e9, "10000000000");
  expect_format(std::numeric_limits<double>::denorm_min(), "4.940656458E-324");
}

// Трансцендентные функции теперь направляются через mk_math:: (здесь подсистема
// LIBM); это подтверждает, что подключение даёт ожидаемые значения.
static void test_mk_math_dispatch(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 A=SIN(0)+COS(0)+SQRT(16)+LN(EXP(1))\n"
    "20 PRINT A\n",
    "MATH");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestNumber("A") - 6.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "6", 1) == 0);
}

static void test_trig_angle_modes(void) {
  TinyBasicTestReset();
  TinyBasicTestSetAngleMode(11); // градусы
  int slot = TinyBasicTestAddProgram(
    "10 A=SIN(30)\n"
    "20 B=ASIN(.5)\n",
    "DEGREES");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 0.5) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("B") - 30.0) < 0.000001);

  TinyBasicTestReset();
  TinyBasicTestSetAngleMode(12); // грады
  slot = TinyBasicTestAddProgram("10 A=SIN(100)\n", "GRADES");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 1.0) < 0.000001);
}

static void test_mk_register_references(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 .x=42\n"
    "20 A=.x+1\n"
    "30 LET .R0=A\n"
    "40 LET .re=.R0+2\n"
    "50 PRINT .re\n",
    "MKREF");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestMkX() - 42.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("A") - 43.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(0) - 43.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(14) - 45.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "45", 2) == 0);

  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 .R00=1\n"));
  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 A=.RZ\n"));
  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 .XX=1\n"));
}

static void test_mk_reference_rejects_unrepresentable_values(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 .X=1E100\n"
    "20 END\n",
    "MKRANGE");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::strcmp(TinyBasicTestError(), "HOW?") == 0);
}

static void test_input_mk_stack_reference(void) {
  TinyBasicTestReset();
  TinyBasicTestSetInput(7.0);
  const int slot = TinyBasicTestAddProgram(
    "10 INPUT .Y\n"
    "20 A=.Y\n",
    "INMK");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestNumber("A") - 7.0) < 0.000001);
}

static void test_mk_rf_requires_expanded_mode(void) {
  TinyBasicTestReset();
  int slot = TinyBasicTestAddProgram(
    "10 .RF=1\n"
    "20 END\n",
    "BADRF");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::strcmp(TinyBasicTestError(), "WHAT?") == 0);

  TinyBasicTestReset();
  TinyBasicTestSetRfEnabled(true);
  slot = TinyBasicTestAddProgram(
    "10 .RF=-7\n"
    "20 A=.RF\n",
    "RF");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestMkRegister(15) + 7.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("A") + 7.0) < 0.000001);
}

static void test_palo_alto_arrays_size_and_assignment_lists(void) {
  TinyBasicTestReset();
  assert(TinyBasicTestCompile("10 LET A=4,B=5\n"));
  assert(TinyBasicTestCompile("10 @(0)=9\n"));
  assert(TinyBasicTestCompile("10 A=@(0)\n"));
  assert(TinyBasicTestCompile("10 A=SIZE\n"));
  assert(TinyBasicTestCompile("10 A=S.\n"));
  assert(TinyBasicTestCompile("10 A=A.(-3)\n"));
  assert(TinyBasicTestCompile("10 A=SIN.(0)\n"));
  assert(TinyBasicTestCompile("10 A=1#2\n"));
  const int slot = TinyBasicTestAddProgram(
    "10 LET A=4,B=5,@(0)=A+B,@(1)=@(0)*2\n"
    "20 C=@(1)\n"
    "30 D=SIZE\n"
    "40 E=S.\n"
    "50 F=A.(-3)\n"
    "60 G=SIN.(0)\n"
    "70 H=1#2\n",
    "PATBARRAY");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("C") - 18.0) < 0.000001);
  assert(TinyBasicTestNumber("D") >= 2.0);
  assert(TinyBasicTestNumber("D") == TinyBasicTestNumber("E"));
  assert(std::fabs(TinyBasicTestNumber("F") - 3.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("G")) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("H") - 1.0) < 0.000001);
}

static void test_palo_alto_step_semicolon_and_gosub_resume(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 S=0;FOR I=3 TO 1 STEP -1;S=S+I;NEXT I;GOSUB 100;S=S+10;END\n"
    "100 S=S+1;RETURN\n",
    "PATBFLOW");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("S") - 17.0) < 0.000001);

  TinyBasicTestReset();
  const int unwind = TinyBasicTestAddProgram(
    "10 FOR I=1 TO 2;FOR J=1 TO 2;NEXT I;S=S+1\n",
    "NEXTUNWIND");
  assert(unwind >= 0);
  assert(TinyBasicTestRunResult(unwind));
  assert(std::fabs(TinyBasicTestNumber("S") - 1.0) < 0.000001);

  TinyBasicTestReset();
  const int negative_skip = TinyBasicTestAddProgram(
    "10 S=1;FOR I=1 TO 3 STEP -1;S=99;NEXT I;S=S+1\n",
    "NEGSZ");
  assert(negative_skip >= 0);
  assert(TinyBasicTestRunResult(negative_skip));
  assert(std::fabs(TinyBasicTestNumber("S") - 2.0) < 0.000001);
}

static void test_palo_alto_print_format_and_input_expression(void) {
  TinyBasicTestReset();
  TinyBasicTestSetInputExpression("2+3*4");
  const int slot = TinyBasicTestAddProgram(
    "10 INPUT 'VALUE?'A\n"
    "20 PRINT #6,A\n",
    "PATBIO");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 14.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "    14", 6) == 0);
}

static void test_expanded_tinybasic_limits(void) {
  TinyBasicTestReset();
  char source[3400];
  std::size_t used = 0;
  for(int line = 1; line <= 120; line++) {
    const int written = std::snprintf(
        source + used, sizeof(source) - used,
        "%d REM ABCDEFGH\n", line * 10);
    assert(written > 0 && (std::size_t) written < sizeof(source) - used);
    used += (std::size_t) written;
  }
  assert(used > 1536 && used < sizeof(source));
  assert(TinyBasicTestCompile(source));

  TinyBasicTestReset();
  const int nested = TinyBasicTestAddProgram(
    "10 FOR A=1 TO 1\n"
    "20 FOR B=1 TO 1\n"
    "30 FOR C=1 TO 1\n"
    "40 FOR D=1 TO 1\n"
    "50 FOR E=1 TO 1\n"
    "60 FOR F=1 TO 1\n"
    "70 FOR G=1 TO 1\n"
    "80 FOR H=1 TO 1\n"
    "90 FOR I=1 TO 1\n"
    "100 FOR J=1 TO 1\n"
    "110 FOR K=1 TO 1\n"
    "120 FOR L=1 TO 1\n"
    "130 S=1\n"
    "140 NEXT L\n150 NEXT K\n160 NEXT J\n170 NEXT I\n"
    "180 NEXT H\n190 NEXT G\n200 NEXT F\n210 NEXT E\n"
    "220 NEXT D\n230 NEXT C\n240 NEXT B\n250 NEXT A\n",
    "DEEPFOR");
  assert(nested >= 0);
  assert(TinyBasicTestRunResult(nested));
  assert(std::fabs(TinyBasicTestNumber("S") - 1.0) < 0.000001);

  TinyBasicTestReset();
  const int deep_gosub = TinyBasicTestAddProgram(
    "10 GOSUB 100\n20 END\n"
    "100 A=A+1;GOSUB 110;RETURN\n"
    "110 A=A+1;GOSUB 120;RETURN\n"
    "120 A=A+1;GOSUB 130;RETURN\n"
    "130 A=A+1;GOSUB 140;RETURN\n"
    "140 A=A+1;GOSUB 150;RETURN\n"
    "150 A=A+1;GOSUB 160;RETURN\n"
    "160 A=A+1;GOSUB 170;RETURN\n"
    "170 A=A+1;GOSUB 180;RETURN\n"
    "180 A=A+1;GOSUB 190;RETURN\n"
    "190 A=A+1;GOSUB 200;RETURN\n"
    "200 A=A+1;GOSUB 210;RETURN\n"
    "210 A=A+1;RETURN\n",
    "DEEPGOSUB");
  assert(deep_gosub >= 0);
  assert(TinyBasicTestRunResult(deep_gosub));
  assert(std::fabs(TinyBasicTestNumber("A") - 12.0) < 0.000001);

  TinyBasicTestReset();
  assert(TinyBasicTestCompile(
    "10 A=------------------------------------------------------------------------"
    "--------1\n"));
}

static int add_shipping_program(const char* path, const char* name) {
  FILE* file = std::fopen(path, "rb");
  assert(file != nullptr);
  char source[3585];
  const size_t size = std::fread(source, 1, sizeof(source), file);
  assert(!std::ferror(file));
  assert(std::fgetc(file) == EOF);
  std::fclose(file);
  assert(size <= 3584);
  source[size] = 0;
  assert(TinyBasicTestCompile(source));
  const int slot = TinyBasicTestAddProgram(source, name);
  assert(slot >= 0);
  return slot;
}

static void test_high_noon_package(int argc, char** argv) {
  assert(argc == 5);
  TinyBasicTestReset();
  (void) add_shipping_program(argv[1], "INTRO");
  (void) add_shipping_program(argv[2], "PLAYER");
  (void) add_shipping_program(argv[3], "BART");
  (void) add_shipping_program(argv[4], "REWARD");
  TinyBasicTestSetGeometry(47, 10);

  const double no_instructions[] = {0};
  TinyBasicTestSetInputs(no_instructions, 1);
  assert(RunTinyBasicProgram("INTRO"));
  assert(std::strcmp(TinyBasicTestLastPrompt(),
                     "ПОКАЗАТЬ ИНСТРУКЦИЮ? 1 ДА 0 НЕТ") == 0);
  // The zero branch now reaches the game immediately.  A standalone
  // interactive run therefore gets the runner's normal final wait; the real
  // M61 scenario dispatcher starts PLAYER without that acknowledgement.
  assert(TinyBasicTestWaitCount() == 1);
  assert(std::fabs(TinyBasicTestMkRegister(0) - 100.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(2)) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(3)) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(4)) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(14) - 1.0) < 0.000001);

  const double advance[] = {1, 10};
  TinyBasicTestSetInputs(advance, 2);
  assert(RunTinyBasicProgram("PLAYER"));
  assert(std::fabs(TinyBasicTestMkRegister(0) - 90.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(1) - 1.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(14) - 2.0) < 0.000001);

  assert(RunTinyBasicProgram("BART"));
  assert(std::fabs(TinyBasicTestMkRegister(14) - 1.0) < 0.000001);
  assert(TinyBasicTestMkRegister(0) <= 90.0 ||
         TinyBasicTestMkRegister(3) == 1.0);

  const double surrender[] = {5, 1};
  TinyBasicTestSetInputs(surrender, 2);
  assert(RunTinyBasicProgram("PLAYER"));
  assert(std::fabs(TinyBasicTestMkRegister(1) - 5.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(14) - 99.0) < 0.000001);

  assert(RunTinyBasicProgram("REWARD"));
  assert(std::fabs(TinyBasicTestMkRegister(14) - 99.0) < 0.000001);
  // Both receipt borders are generated from the live viewport width.  The
  // final FOR/NEXT leaves I at COLS+1; a fixed 40+14-character decoration
  // would not exercise the runtime geometry at all.
  assert(std::fabs(TinyBasicTestNumber("I") - 48.0) < 0.000001);

  const double stand[] = {2};
  TinyBasicTestSetInputs(stand, 1);
  TinyBasicTestSetPauseEsc(true);
  assert(RunTinyBasicProgram("PLAYER"));
  TinyBasicTestSetPauseEsc(false);
  assert(std::fabs(TinyBasicTestMkRegister(14) - 99.0) < 0.000001);
  assert(TinyBasicTestWaitCount() == 1);
}

int main(int argc, char** argv) {
  test_compile_and_print();
  test_line_index_orders_source_and_rejects_duplicates();
  test_format_number();
  test_mk_math_dispatch();
  test_trig_angle_modes();
  test_mk_register_references();
  test_mk_reference_rejects_unrepresentable_values();
  test_input_mk_stack_reference();
  test_mk_rf_requires_expanded_mode();
  test_palo_alto_arrays_size_and_assignment_lists();
  test_palo_alto_step_semicolon_and_gosub_resume();
  test_palo_alto_print_format_and_input_expression();
  test_expanded_tinybasic_limits();
  test_if_and_goto();
  test_gosub();
  test_for_next();
  test_input();
  test_bad_expression_tail();
  test_compile_rejects_invalid_statements();
  test_keyword_abbreviations();
  test_boolean_truth_table();
  test_expression_semantics();
  assert(!TinyBasicTestCompile("10 A=LOADFONT(\"HighNoon\")\n"));
  test_cls_and_pause();
  test_zero_trip_for();
  test_print_syntax_and_spacing();
  test_runtime_math_errors_are_safe();
  test_variables_persist_until_clear();
  test_run_api_reports_runtime_failure();
  test_m61_mode_esc_at_pause_is_silent_stop();
  test_failed_edit_keeps_previous_program();
  test_editor_has_no_operator_macros();
  test_editor_cx_backspace_and_f_cx_clear_line();
  test_editor_pp_is_space();
  if(argc > 1) test_high_noon_package(argc, argv);
  std::printf("tinybasic_self_test: ok\n");
  return 0;
}
