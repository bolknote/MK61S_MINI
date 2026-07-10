#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

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
extern "C" const char* TinyBasicTestLcdLine(int row);
extern "C" void TinyBasicTestEditSequence(const int* keys, int count, char* out, int size);
extern "C" void TinyBasicTestFormatNumber(double value, char* out, int size);

static constexpr int KEY_K = 37;
static constexpr int KEY_OK = 29;
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
  const int slot = TinyBasicTestAddProgram(
    "10 A=1 BAD\n"
    "20 PRINT A\n",
    "BAD");
  assert(slot >= 0);
  TinyBasicTestRun(slot);
  assert(std::strcmp(TinyBasicTestError(), "HOW?") == 0);
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
  test_mk_register_references();
  test_mk_reference_rejects_unrepresentable_values();
  test_input_mk_stack_reference();
  test_mk_rf_requires_expanded_mode();
  test_if_and_goto();
  test_gosub();
  test_for_next();
  test_input();
  test_bad_expression_tail();
  test_editor_has_no_operator_macros();
  std::printf("tinybasic_self_test: ok\n");
  return 0;
}
