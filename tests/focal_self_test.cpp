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
extern "C" void FocalTestDrawNewEditorSms(const char* source, int cursor);
extern "C" void FocalTestSetLcdRows(int rows);
extern "C" int FocalTestEnsureViewTop(const char* source, int cursor, int view_top);
extern "C" void FocalTestDrawNewEditorAt(const char* source, int cursor, int view_top);
extern "C" int FocalTestMoveCursorLine(const char* source, int cursor, int delta);
extern "C" int FocalTestMoveCursorHorizontal(const char* source, int cursor, int delta);
extern "C" int FocalTestMoveCursorLineKey(const char* source, int cursor, int key_code);
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

static void test_print_newline(void) {
  FocalTestReset();
  const int slot = add_program("01.10 S A=7\n01.20 S B=9\n01.30 P A,!,B\n01.40 E");
  FocalTestRun(slot);
  CHECK_STARTS(FocalTestLcdLine(0), "7");
  CHECK_STARTS(FocalTestLcdLine(1), "9");
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

  const int square[] = {37, 11, 11, 38, 2};
  FocalTestEditSequence(square, (int) (sizeof(square) / sizeof(square[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "X^2") == 0);

  const int inverse[] = {37, 18, 7, 37, 18, 18, 38, 3};
  FocalTestEditSequence(inverse, (int) (sizeof(inverse) / sizeof(inverse[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1/(A+B)") == 0);

  const int pow10[] = {37, 11, 11, 38, 5};
  FocalTestEditSequence(pow10, (int) (sizeof(pow10) / sizeof(pow10[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "10^X") == 0);
}

static void test_editor_digit_symbol_and_sms_input(void) {
  FocalTestReset();
  char out[64];

  const int digits[] = {20, 21, 16, 11, 22, 17, 12, 23, 18, 13};
  FocalTestEditSequence(digits, (int) (sizeof(digits) / sizeof(digits[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "0123456789") == 0);

  const int symbols[] = {38, 20, 38, 21, 38, 16, 38, 11, 38, 22, 38, 17, 38, 12, 38, 23, 38, 18, 38, 13};
  FocalTestEditSequence(symbols, (int) (sizeof(symbols) / sizeof(symbols[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "!@#$%^&*()") == 0);

  const int sms_cycle[] = {37, 18, 18, 18};
  FocalTestEditSequence(sms_cycle, (int) (sizeof(sms_cycle) / sizeof(sms_cycle[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "C") == 0);

  const int sms_text[] = {37, 18, 13, 13, 12};
  FocalTestEditSequence(sms_text, (int) (sizeof(sms_text) / sizeof(sms_text[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "AEM") == 0);

  const int f_a_is_not_letter_input[] = {38, 15};
  FocalTestEditSequence(f_a_is_not_letter_input, (int) (sizeof(f_a_is_not_letter_input) / sizeof(f_a_is_not_letter_input[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "") == 0);

  const int sms_seven_exits_with_space[] = {37, 18, 18, 23, 16};
  FocalTestEditSequence(sms_seven_exits_with_space, (int) (sizeof(sms_seven_exits_with_space) / sizeof(sms_seven_exits_with_space[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "B 2") == 0);

  const int sms_one_cycles_pqrs[] = {37, 21, 21, 21, 21};
  FocalTestEditSequence(sms_one_cycles_pqrs, (int) (sizeof(sms_one_cycles_pqrs) / sizeof(sms_one_cycles_pqrs[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "S") == 0);

  const int sms_space_exits[] = {37, 18, 25, 16};
  FocalTestEditSequence(sms_space_exits, (int) (sizeof(sms_space_exits) / sizeof(sms_space_exits[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "A 2") == 0);

  const int k_zero_does_not_start_sms[] = {37, 20};
  FocalTestEditSequence(k_zero_does_not_start_sms, (int) (sizeof(k_zero_does_not_start_sms) / sizeof(k_zero_does_not_start_sms[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "") == 0);
}

static void test_editor_operator_keys_insert_full_names(void) {
  FocalTestReset();
  char out[128];

  const int branch_no_space[] = {21, 15, 21, 20, 10};
  FocalTestEditSequence(branch_no_space, (int) (sizeof(branch_no_space) / sizeof(branch_no_space[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.10 BRANCH ") == 0);

  const int k_branch_no_space[] = {21, 15, 21, 20, 37, 10};
  FocalTestEditSequence(k_branch_no_space, (int) (sizeof(k_branch_no_space) / sizeof(k_branch_no_space[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.10 BRANCH ") == 0);

  const int ask[] = {21, 15, 21, 20, 25, 15};
  FocalTestEditSequence(ask, (int) (sizeof(ask) / sizeof(ask[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.10 ASK ") == 0);

  const int k_ask[] = {21, 15, 21, 20, 37, 15};
  FocalTestEditSequence(k_ask, (int) (sizeof(k_ask) / sizeof(k_ask[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.10 ASK ") == 0);

  const int print[] = {21, 15, 16, 20, 25, 14};
  FocalTestEditSequence(print, (int) (sizeof(print) / sizeof(print[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.20 PRINT ") == 0);

  const int go_to[] = {21, 15, 11, 20, 25, 4};
  FocalTestEditSequence(go_to, (int) (sizeof(go_to) / sizeof(go_to[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.30 GOTO ") == 0);

  const int k_go_to[] = {21, 15, 11, 20, 37, 4};
  FocalTestEditSequence(k_go_to, (int) (sizeof(k_go_to) / sizeof(k_go_to[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.30 GOTO ") == 0);

  const int k_print[] = {21, 15, 16, 20, 37, 14};
  FocalTestEditSequence(k_print, (int) (sizeof(k_print) / sizeof(k_print[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.20 PRINT ") == 0);

  const int set[] = {21, 15, 22, 20, 25, 27};
  FocalTestEditSequence(set, (int) (sizeof(set) / sizeof(set[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.40 SET ") == 0);

  const int set_equals[] = {21, 15, 22, 20, 25, 27, 37, 11, 11, 37, 7};
  FocalTestEditSequence(set_equals, (int) (sizeof(set_equals) / sizeof(set_equals[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.40 SET X=") == 0);

  const int return_op[] = {21, 15, 17, 20, 25, 31};
  FocalTestEditSequence(return_op, (int) (sizeof(return_op) / sizeof(return_op[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1.50 RETURN") == 0);
}

static void test_editor_backspace_is_f_left(void) {
  FocalTestReset();
  char out[32];

  const int f_left[] = {21, 20, 38, 34};
  FocalTestEditSequence(f_left, (int) (sizeof(f_left) / sizeof(f_left[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "1") == 0);

  const int degree_is_not_backspace[] = {21, 20, 4};
  FocalTestEditSequence(degree_is_not_backspace, (int) (sizeof(degree_is_not_backspace) / sizeof(degree_is_not_backspace[0])), out, sizeof(out));
  CHECK(std::strcmp(out, "10 GOTO ") == 0);
}

static void test_editor_draws_cursor(void) {
  FocalTestReset();
  FocalTestDrawNewEditor("", 0);
  CHECK(FocalTestLcdLine(0)[0] == '>');
  CHECK(FocalTestLcdLine(0)[1] == (char) 0xFF);

  FocalTestDrawNewEditor("01.10 COMMENT LONG LINE", 21);
  CHECK(FocalTestLcdLine(0)[0] == '>');
  CHECK(FocalTestLcdLine(0)[15] == (char) 0xFF);

  FocalTestDrawNewEditorSms("", 0);
  CHECK(FocalTestLcdLine(0)[0] == '>');
  CHECK(FocalTestLcdLine(0)[1] == '_');
}

static void test_editor_draws_visible_program_lines(void) {
  FocalTestReset();
  FocalTestDrawNewEditor("1.10 ASK X\n1.20 PRINT X\n1.30 EXIT\n1.40 COMMENT END\n1.50 EXIT", 0);
  CHECK(FocalTestLcdLine(0)[0] == '>');
  CHECK_STARTS(FocalTestLcdLine(1), " 1.20 PRINT X");
  CHECK_STARTS(FocalTestLcdLine(2), " 1.30 EXIT");
  CHECK_STARTS(FocalTestLcdLine(3), " 1.40 COMMENT");
}

static void test_editor_two_line_viewport_scrolls_like_a00(void) {
  FocalTestReset();
  FocalTestSetLcdRows(2);

  const char* one_line_and_new = "1.10 ASK X\n";
  int view_top = FocalTestEnsureViewTop(one_line_and_new, (int) std::strlen(one_line_and_new), 0);
  CHECK(view_top == 0);
  FocalTestDrawNewEditorAt(one_line_and_new, (int) std::strlen(one_line_and_new), view_top);
  CHECK_STARTS(FocalTestLcdLine(0), " 1.10 ASK X");
  CHECK(FocalTestLcdLine(1)[0] == '>');
  CHECK(FocalTestLcdLine(1)[1] == (char) 0xFF);

  const char* two_lines_and_new = "1.10 ASK X\n1.20 PRINT X\n";
  view_top = FocalTestEnsureViewTop(two_lines_and_new, (int) std::strlen(two_lines_and_new), view_top);
  CHECK(view_top == 11);
  FocalTestDrawNewEditorAt(two_lines_and_new, (int) std::strlen(two_lines_and_new), view_top);
  CHECK_STARTS(FocalTestLcdLine(0), " 1.20 PRINT X");
  CHECK(FocalTestLcdLine(1)[0] == '>');
  CHECK(FocalTestLcdLine(1)[1] == (char) 0xFF);

  FocalTestSetLcdRows(4);
}

static void test_editor_line_navigation(void) {
  const char* source = "ABC\nD\nEFGH";
  CHECK(FocalTestMoveCursorLine(source, 1, 1) == 5);
  CHECK(FocalTestMoveCursorLine(source, 5, 1) == 7);
  CHECK(FocalTestMoveCursorLine(source, 7, -1) == 5);
  CHECK(FocalTestMoveCursorHorizontal(source, 3, 1) == 3);
  CHECK(FocalTestMoveCursorHorizontal(source, 4, -1) == 4);
  CHECK(FocalTestMoveCursorLineKey(source, 5, 32) == 1);
  CHECK(FocalTestMoveCursorLineKey(source, 1, 33) == 5);
}

int main(void) {
  test_compile_rejects_basic_aliases();
  test_arithmetic_and_print();
  test_print_newline();
  test_for_loop_sum();
  test_for_loop_start_step_end();
  test_do_exact_line();
  test_do_group();
  test_return_early_from_group();
  test_goto_and_branch();
  test_functions();
  test_editor_shift_parentheses();
  test_editor_expression_macros();
  test_editor_digit_symbol_and_sms_input();
  test_editor_operator_keys_insert_full_names();
  test_editor_backspace_is_f_left();
  test_editor_draws_cursor();
  test_editor_draws_visible_program_lines();
  test_editor_two_line_viewport_scrolls_like_a00();
  test_editor_line_navigation();

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
