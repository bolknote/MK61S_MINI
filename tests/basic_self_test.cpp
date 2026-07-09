#include <cmath>
#include <cstdio>
#include <cstring>

#ifndef MK61_ENABLE_BASIC
#define MK61_ENABLE_BASIC 1
#endif

#if MK61_ENABLE_BASIC

extern "C" void BasicTestReset(void);
extern "C" bool BasicTestCompile(const char* source);
extern "C" int BasicTestAddProgram(const char* source);
extern "C" void BasicTestRun(int slot);
extern "C" double BasicTestNumber(const char* name);
extern "C" const char* BasicTestString(const char* name);
extern "C" const char* BasicTestLcdLine(int row);
extern "C" double BasicTestMkX(void);
extern "C" double BasicTestMkRegister(int reg);
extern "C" void BasicTestSetRfEnabled(bool enabled);
extern "C" bool BasicTestStepAssigned(int step);
extern "C" const char* BasicTestError(void);
extern "C" void BasicTestEditSequence(const int* keys, int count, char* out, int size);

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
  const int slot = BasicTestAddProgram(source);
  if(slot < 0) std::printf("add_program failed: %s source='%s'\n", BasicTestError(), source);
  CHECK(slot >= 0);
  return slot;
}

static void test_compile_rejects_bad_syntax(void) {
  BasicTestReset();
  const bool valid_ok = BasicTestCompile("A=1+2*3:HLT OK");
  if(!valid_ok) std::printf("compile failed: %s\n", BasicTestError());
  CHECK(valid_ok);
  CHECK(!BasicTestCompile("IF A=1 B=2:HLT BAD"));
}

static void test_arithmetic_and_print(void) {
  BasicTestReset();
  const int slot = add_program("A=1+2*3:? A:HLT ARITH");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("A"), 7.0);
  CHECK_STARTS(BasicTestLcdLine(0), "7");
}

static void test_multiline_program(void) {
  BasicTestReset();
  const int slot = add_program("A=1\nB=A+2\n? B\nHLT MULTI");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("B"), 3.0);
  CHECK_STARTS(BasicTestLcdLine(0), "3");
}

static void test_if_then_else(void) {
  BasicTestReset();
  const int slot = add_program("A=0:IF A=1 TH B=1 EL B=2:HLT IFEL");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("B"), 2.0);
}

static void test_for_next_loop(void) {
  BasicTestReset();
  const int slot = add_program("S=0:FOR I=1 TO 5:S=S+I:NXT I:? S:HLT SUM");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("S"), 15.0);
  CHECK_STARTS(BasicTestLcdLine(0), "15");
}

static void test_while_end_loop(void) {
  BasicTestReset();
  const int slot = add_program("A=0:S=0:WH A<4:S=S+A:A=A+1:END:HLT WHILE");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("A"), 4.0);
  CHECK_NEAR(BasicTestNumber("S"), 6.0);
}

static void test_do_while_loop(void) {
  BasicTestReset();
  const int slot = add_program("A=0:DO:A=A+1:WH A<3:HLT DOWH");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("A"), 3.0);
}

static void test_labels_and_go_from_if(void) {
  BasicTestReset();
  const int slot = add_program("A=0:1:A=A+1:IF A<3 TH GO 1:HLT LOOP");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("A"), 3.0);
}

static void test_string_variables(void) {
  BasicTestReset();
  const int slot = add_program("$A=\"HI\":? $A:HLT STR");
  BasicTestRun(slot);
  CHECK(std::strcmp(BasicTestString("$A"), "HI") == 0);
  CHECK_STARTS(BasicTestLcdLine(0), "HI");
}

static void test_mk_stack_reference(void) {
  BasicTestReset();
  const int slot = add_program(".X=42:A=.X:HLT MKREF");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("A"), 42.0);
  CHECK_NEAR(BasicTestMkX(), 42.0);
}

static void test_mk_register_references(void) {
  BasicTestReset();
  const int slot = add_program(".R0=12.5:.RE=.R0+2:A=.RE:.Y=-3:B=.Y:HLT MKREG");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestMkRegister(0), 12.5);
  CHECK_NEAR(BasicTestMkRegister(14), 14.5);
  CHECK_NEAR(BasicTestNumber("A"), 14.5);
  CHECK_NEAR(BasicTestNumber("B"), -3.0);
}

static void test_mk_rf_requires_expanded_mode(void) {
  BasicTestReset();
  CHECK(!BasicTestCompile(".RF=1:HLT BADRF"));

  BasicTestReset();
  BasicTestSetRfEnabled(true);
  const int slot = add_program(".RF=-7:A=.RF:HLT RF");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestMkRegister(15), -7.0);
  CHECK_NEAR(BasicTestNumber("A"), -7.0);
}

static void test_mk_step_binding(void) {
  BasicTestReset();
  add_program("? \"X\":HLT FOO");
  const int bind = add_program("MK.7=FOO:HLT BIND");
  BasicTestRun(bind);
  CHECK(BasicTestStepAssigned(7));
}

static void test_basic_function_call_returns_x(void) {
  BasicTestReset();
  add_program(".X=9:HLT FOO");
  const int caller = add_program("B=FOO():HLT CALLER");
  BasicTestRun(caller);
  CHECK_NEAR(BasicTestNumber("B"), 9.0);
}

static void test_editor_shift_and_statement_keys(void) {
  BasicTestReset();
  char out[64];

  const int shifted[] = {37, 27, 37, 17, 37, 1, 37, 0};
  BasicTestEditSequence(shifted, (int) (sizeof(shifted) / sizeof(shifted[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "VW:~") == 0);

  const int alpha_service[] = {38, 0, 38, 1, 38, 9, 38, 29, 38, 39};
  BasicTestEditSequence(alpha_service, (int) (sizeof(alpha_service) / sizeof(alpha_service[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "DEHLN") == 0);

  const int green_symbols[] = {37, 10, 37, 5, 37, 15, 37, 25};
  BasicTestEditSequence(green_symbols, (int) (sizeof(green_symbols) / sizeof(green_symbols[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "&^|,") == 0);

  const int backspace[] = {21, 16, 4, 11};
  BasicTestEditSequence(backspace, (int) (sizeof(backspace) / sizeof(backspace[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "13") == 0);

  const int statement[] = {5, 29, 26, 29, 30, 29, 1};
  BasicTestEditSequence(statement, (int) (sizeof(statement) / sizeof(statement[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "? \nGO \nHLT \nIN ") == 0);
}

static void test_logical_not_operator(void) {
  BasicTestReset();
  const int slot = add_program("A=~0:B=~1:HLT NOT");
  BasicTestRun(slot);
  CHECK_NEAR(BasicTestNumber("A"), 1.0);
  CHECK_NEAR(BasicTestNumber("B"), 0.0);
}

int main(void) {
  test_compile_rejects_bad_syntax();
  test_arithmetic_and_print();
  test_multiline_program();
  test_if_then_else();
  test_for_next_loop();
  test_while_end_loop();
  test_do_while_loop();
  test_labels_and_go_from_if();
  test_string_variables();
  test_mk_stack_reference();
  test_mk_register_references();
  test_mk_rf_requires_expanded_mode();
  test_mk_step_binding();
  test_basic_function_call_returns_x();
  test_editor_shift_and_statement_keys();
  test_logical_not_operator();

  if(failures != 0) {
    std::printf("basic_self_test: %d failure(s)\n", failures);
    return 1;
  }

  std::printf("basic_self_test: ok\n");
  return 0;
}
#else
int main(void) {
  std::printf("basic_self_test: skipped (MK61_ENABLE_BASIC=0)\n");
  return 0;
}
#endif
