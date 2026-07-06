#include <cmath>
#include <cstdio>
#include <cstring>

#ifndef MK61_ENABLE_FOCAL
#define MK61_ENABLE_FOCAL 1
#endif

#if MK61_ENABLE_FOCAL

extern "C" void FocalTestReset(void);
extern "C" bool FocalTestCompile(const char* source);
extern "C" int FocalTestAddProgram(const char* source);
extern "C" void FocalTestRun(int slot);
extern "C" double FocalTestNumber(const char* name);
extern "C" const char* FocalTestLcdLine(int row);
extern "C" const char* FocalTestError(void);
extern "C" void FocalTestDrawNewEditor(const char* source, int cursor);
extern "C" void FocalTestEditSequence(const int* keys, int count, char* out, int size);

static int failures;

static void check_true(bool value, const char* expr, const char* file, int line) {
  if(value) return;
  std::printf("%s:%d: CHECK failed: %s\n", file, line, expr);
  failures++;
}

static void check_near(double actual, double expected, const char* expr, const char* file, int line) {
  if(std::fabs(actual - expected) <= 0.000001) return;
  std::printf("%s:%d: CHECK_NEAR failed: %s actual=%.10g expected=%.10g\n", file, line, expr, actual, expected);
  failures++;
}

static void check_starts(const char* actual, const char* expected, const char* expr, const char* file, int line) {
  if(std::strncmp(actual, expected, std::strlen(expected)) == 0) return;
  std::printf("%s:%d: CHECK_STARTS failed: %s actual='%s' expected prefix='%s'\n", file, line, expr, actual, expected);
  failures++;
}

#define CHECK(expr) check_true((expr), #expr, __FILE__, __LINE__)
#define CHECK_NEAR(actual, expected) check_near((actual), (expected), #actual, __FILE__, __LINE__)
#define CHECK_STARTS(actual, expected) check_starts((actual), (expected), #actual, __FILE__, __LINE__)

static int add_program(const char* source) {
  const int slot = FocalTestAddProgram(source);
  if(slot < 0) std::printf("add_program failed: %s source='%s'\n", FocalTestError(), source);
  CHECK(slot >= 0);
  return slot;
}

static void test_compile_rejects_basic_aliases(void) {
  FocalTestReset();
  CHECK(FocalTestCompile("01.10 S A=1+2*3\n01.20 P A\n01.30 E"));
  CHECK(!FocalTestCompile("01.10 TYPE A\n01.20 E"));
}

static void test_arithmetic_and_print(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S A=1+2*3\n01.20 P A\n01.30 E");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("A"), 7.0);
  CHECK_STARTS(FocalTestLcdLine(0), "7");
}

static void test_for_loop_sum(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S S=0\n01.20 F I=1,5; S S=S+I\n01.30 P S\n01.40 E");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("S"), 15.0);
  CHECK_STARTS(FocalTestLcdLine(0), "15");
}

static void test_for_loop_start_step_end(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S S=0\n01.20 F I=0,10,100; S S=S+I\n01.30 P S\n01.40 E");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("S"), 550.0);
  CHECK_STARTS(FocalTestLcdLine(0), "550");
}

static void test_do_exact_line(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S A=2\n01.20 D 2.10\n01.30 E\n02.10 S A=A+3\n02.20 S A=99");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("A"), 5.0);
}

static void test_do_group(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S A=0\n01.20 D 2\n01.30 E\n02.10 S A=A+1\n02.20 S A=A+2");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("A"), 3.0);
}

static void test_return_early_from_group(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S A=0\n01.20 D 2\n01.30 E\n02.10 S A=1\n02.20 R\n02.30 S A=9");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("A"), 1.0);
}

static void test_goto_and_branch(void) {
  FocalTestReset();
  const int slot = add_program(
    "01.10 S X=-2\n"
    "01.20 B (X) 1.40,1.60,1.80\n"
    "01.30 S A=9\n"
    "01.35 E\n"
    "01.40 S A=1\n"
    "01.50 G 1.90\n"
    "01.60 S A=0\n"
    "01.70 E\n"
    "01.80 S A=2\n"
    "01.90 P A\n"
    "02.00 E");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("A"), 1.0);
  CHECK_STARTS(FocalTestLcdLine(0), "1");
}

static void test_functions(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S A=ABS(-3)+INT(2.9)+MAX(4,5)\n01.20 S R=RND()\n01.30 P A\n01.40 E");
  FocalTestRun(slot);
  CHECK_NEAR(FocalTestNumber("A"), 10.0);
  CHECK(FocalTestNumber("R") >= 0.0);
  CHECK(FocalTestNumber("R") < 1.0);
  CHECK_STARTS(FocalTestLcdLine(0), "10");
}

static void test_editor_shift_parentheses(void) {
  FocalTestReset();
  char out[32];
  const int keys[] = {37, 34, 37, 24};
  FocalTestEditSequence(keys, (int) (sizeof(keys) / sizeof(keys[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "()") == 0);
}

static void test_editor_expression_macros(void) {
  FocalTestReset();
  char out[64];

  const int square[] = {38, 8, 38, 2};
  FocalTestEditSequence(square, (int) (sizeof(square) / sizeof(square[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "X^2") == 0);

  const int inverse[] = {38, 15, 7, 38, 10, 38, 3};
  FocalTestEditSequence(inverse, (int) (sizeof(inverse) / sizeof(inverse[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1/(A+B)") == 0);

  const int pow10[] = {38, 8, 38, 20};
  FocalTestEditSequence(pow10, (int) (sizeof(pow10) / sizeof(pow10[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "10^X") == 0);
}

static void test_editor_draws_cursor(void) {
  FocalTestReset();
  FocalTestDrawNewEditor("", 0);
  CHECK(FocalTestLcdLine(0)[0] == '>');
  CHECK(FocalTestLcdLine(0)[1] == (char) 0xFF);

  FocalTestDrawNewEditor("01.10 COMMENT LONG LINE", 21);
  CHECK(FocalTestLcdLine(0)[0] == '>');
  CHECK(FocalTestLcdLine(0)[15] == (char) 0xFF);
}

int main(void) {
  test_compile_rejects_basic_aliases();
  test_arithmetic_and_print();
  test_for_loop_sum();
  test_for_loop_start_step_end();
  test_do_exact_line();
  test_do_group();
  test_return_early_from_group();
  test_goto_and_branch();
  test_functions();
  test_editor_shift_parentheses();
  test_editor_expression_macros();
  test_editor_draws_cursor();

  if(failures != 0) {
    std::printf("focal_self_test: %d failure(s)\n", failures);
    return 1;
  }

  std::printf("focal_self_test: ok\n");
  return 0;
}
#else
int main(void) {
  std::printf("focal_self_test: skipped (MK61_ENABLE_FOCAL=0)\n");
  return 0;
}
#endif
