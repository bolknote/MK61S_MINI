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
extern "C" const char* TinyBasicTestLcdLine(int row);
extern "C" void TinyBasicTestEditSequence(const int* keys, int count, char* out, int size);

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

int main(void) {
  test_compile_and_print();
  test_if_and_goto();
  test_gosub();
  test_for_next();
  test_input();
  test_bad_expression_tail();
  test_editor_has_no_operator_macros();
  std::printf("tinybasic_self_test: ok\n");
  return 0;
}
