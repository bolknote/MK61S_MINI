#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>

extern "C" void TinyBasicTestReset(void);
extern "C" bool TinyBasicTestCompile(const char* source);
extern "C" const char* TinyBasicTestError(void);
extern "C" int TinyBasicTestAddProgram(const char* source, const char* name);
extern "C" void TinyBasicTestSetInput(double value);
extern "C" void TinyBasicTestRun(int slot);
extern "C" double TinyBasicTestNumber(const char* name);
extern "C" double TinyBasicTestMkX(void);
extern "C" double TinyBasicTestMkRegister(int reg);
extern "C" void TinyBasicTestSetRfEnabled(bool enabled);
extern "C" void TinyBasicTestSetAngleMode(int mode);
extern "C" const char* TinyBasicTestLcdLine(int row);
extern "C" void TinyBasicTestEditSequence(const int* keys, int count, char* out, int size);
extern "C" void TinyBasicTestSetAlphaHeld(bool held);
extern "C" void TinyBasicTestFormatNumber(double value, char* out, int size);
extern "C" bool TinyBasicTestRunResult(int slot);
extern "C" void TinyBasicTestClearData(void);
extern "C" int TinyBasicTestWaitCount(void);
extern "C" bool TinyBasicTestStoreEdited(int slot, char* source, const char* name);
bool RunTinyBasicProgram(const char* name);

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
    "--------1\n"));
  assert(!TinyBasicTestCompile(
    "10 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 "
    "IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 IF 1 A=1\n"));

  char oversized[1600];
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
    "40 D=ROUND(1.5)\n",
    "EXPR");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") + 4.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("B") - 64.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("C") + 2.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("D") - 2.0) < 0.000001);

  TinyBasicTestReset();
  assert(!TinyBasicTestCompile("10 A=SIN(0,123)\n"));
  assert(!TinyBasicTestCompile("10 A=MAX(1)\n"));
  assert(!TinyBasicTestCompile("10 A=MAX(1,2,3)\n"));
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

// The firmware formatter must not depend on printf float support (newlib-nano
// links without it), so it is compared against the old "%.10g" behaviour here.
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

// Transcendental functions now dispatch through mk_math:: (LIBM backend here);
// this confirms the wiring produces the expected values.
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
  TinyBasicTestSetAngleMode(11); // DEGREE
  int slot = TinyBasicTestAddProgram(
    "10 A=SIN(30)\n"
    "20 B=ASIN(.5)\n",
    "DEGREES");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 0.5) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("B") - 30.0) < 0.000001);

  TinyBasicTestReset();
  TinyBasicTestSetAngleMode(12); // GRADE
  slot = TinyBasicTestAddProgram("10 A=SIN(100)\n", "GRADES");
  assert(slot >= 0);
  assert(TinyBasicTestRunResult(slot));
  assert(std::fabs(TinyBasicTestNumber("A") - 1.0) < 0.000001);
}

static void test_mk_register_references(void) {
  TinyBasicTestReset();
  const int slot = TinyBasicTestAddProgram(
    "10 .X=42\n"
    "20 A=.X+1\n"
    "30 LET .R0=A\n"
    "40 LET .RE=.R0+2\n"
    "50 PRINT .RE\n",
    "MKREF");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::fabs(TinyBasicTestMkX() - 42.0) < 0.000001);
  assert(std::fabs(TinyBasicTestNumber("A") - 43.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(0) - 43.0) < 0.000001);
  assert(std::fabs(TinyBasicTestMkRegister(14) - 45.0) < 0.000001);
  assert(std::strncmp(TinyBasicTestLcdLine(0), "45", 2) == 0);
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

int main(void) {
  test_compile_and_print();
  test_format_number();
  test_mk_math_dispatch();
  test_trig_angle_modes();
  test_mk_register_references();
  test_mk_reference_rejects_unrepresentable_values();
  test_input_mk_stack_reference();
  test_mk_rf_requires_expanded_mode();
  test_if_and_goto();
  test_gosub();
  test_for_next();
  test_input();
  test_bad_expression_tail();
  test_compile_rejects_invalid_statements();
  test_keyword_abbreviations();
  test_boolean_truth_table();
  test_expression_semantics();
  test_zero_trip_for();
  test_print_syntax_and_spacing();
  test_runtime_math_errors_are_safe();
  test_variables_persist_until_clear();
  test_run_api_reports_runtime_failure();
  test_failed_edit_keeps_previous_program();
  test_editor_has_no_operator_macros();
  test_editor_cx_backspace_and_f_cx_clear_line();
  test_editor_pp_is_space();
  std::printf("tinybasic_self_test: ok\n");
  return 0;
}
