// Host self test for the mk_math CORE backend.
//
// Compiles the real MK-61 engine (mk61emu_core.cpp) together with the CORE math
// backend (mk_math_core.cpp) and checks that every transcendental matches libm
// within the calculator's 8-digit precision, that pow() behaves, that the pure
// libm-free helpers agree with <math.h>, and that borrowing the core leaves the
// live user state untouched.

#include <cmath>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "mk_math.hpp"       // MK61_MATH_BACKEND == CORE (set via -D)
#include "mk61emu_core.h"

static int g_failures = 0;

static void check_near(const char* label, double got, double want, double tol) {
  const double diff = std::fabs(got - want);
  const double scale = std::fabs(want) > 1.0 ? std::fabs(want) : 1.0;
  if(diff > tol * scale) {
    std::printf("  FAIL %-14s got=%.10g want=%.10g diff=%.3g\n", label, got, want, diff);
    g_failures++;
  } else {
    std::printf("  ok   %-14s got=%.10g want=%.10g\n", label, got, want);
  }
}

static void check_true(const char* label, bool cond) {
  if(!cond) {
    std::printf("  FAIL %s\n", label);
    g_failures++;
  } else {
    std::printf("  ok   %s\n", label);
  }
}

static const char SYMBOLS[16] = {
    '0','1','2','3','4','5','6','7','8','9','-',' ',' ',' ',' ',' '
};

// Read any live stack register the same way the interpreters read X.
static double read_live_reg(stack reg) {
  char value[15];
  value[14] = 0;
  read_stack_register(reg, value, SYMBOLS);

  char buffer[24];
  char* out = buffer;
  if(value[0] == '-') *out++ = '-';
  for(int i = 1; i <= 9; i++) {
    if(value[i] == ' ') continue;
    *out++ = value[i];
  }
  *out++ = 'e';
  *out++ = (value[11] == '-') ? '-' : '+';
  *out++ = value[12];
  *out++ = value[13];
  *out = 0;
  return mk_math::atof(buffer);
}

static double read_live_x(void) { return read_live_reg(stack::X); }

struct MatrixKey { int x, y; };

static void press_matrix(MatrixKey key) {
  core_61::clear_displayed();
  for(int i = 0; i < 4; i++) {
    MK61Emu_SetKeyPress(key.x, key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0, 0);
  for(int i = 0; i < 512; i++) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }
}

static void test_pure_helpers(void) {
  std::printf("pure helpers vs <math.h>:\n");
  const double xs[] = {3.14, -3.14, 2.5, -2.5, 0.0, 7.0, -7.0, 123.456, -0.001};
  for(double x : xs) {
    check_near("floor", mk_math::floor(x), std::floor(x), 1e-12);
    check_near("ceil", mk_math::ceil(x), std::ceil(x), 1e-12);
    check_near("trunc", mk_math::trunc(x), std::trunc(x), 1e-12);
    check_near("fabs", mk_math::fabs(x), std::fabs(x), 1e-12);
  }
  check_near("pow10_int+3", mk_math::pow10_int(3), 1000.0, 1e-12);
  check_near("pow10_int-2", mk_math::pow10_int(-2), 0.01, 1e-12);
  check_true("pow10_int max", mk_math::is_inf(mk_math::pow10_int(INT_MAX)));
  check_true("pow10_int min", mk_math::pow10_int(INT_MIN) == 0.0);
  check_true("log10_floor 100", mk_math::log10_floor(100.0) == 2);
  check_true("log10_floor 0.01", mk_math::log10_floor(0.01) == -2);
  check_true("log10_floor 5", mk_math::log10_floor(5.0) == 0);
  check_true("log10_floor 0.5", mk_math::log10_floor(0.5) == -1);

  const char* endp = nullptr;
  check_near("atof int", mk_math::atof("123"), 123.0, 1e-9);
  check_near("atof frac", mk_math::atof("3.14159"), 3.14159, 1e-9);
  check_near("atof sci", mk_math::atof("-1.5e3"), -1500.0, 1e-9);
  check_near("atof huge int", mk_math::atof("123456789012345678901"), 1.2345678901234568e20, 1e-15);
  check_near("atof leading 0", mk_math::atof("0.00000000000000000000125"), 1.25e-21, 1e-15);
  check_true("atof overflow", mk_math::is_inf(mk_math::atof("1e999999")));
  check_true("atof underflow", mk_math::atof("1e-999999") == 0.0);
  check_true("atof zero huge", mk_math::atof("0e999999") == 0.0);
  double v = mk_math::strtod("42.5abc", &endp);
  check_near("strtod value", v, 42.5, 1e-9);
  check_true("strtod endptr", endp != nullptr && *endp == 'a');
  check_true("pow10 huge", std::isinf(mk_math::pow10_int(INT_MAX)));
  check_true("pow10 tiny", mk_math::pow10_int(INT_MIN) == 0.0);
  check_true("pow10 subnormal", mk_math::pow10_int(-309) > 0.0);
  check_true("log10 invalid", mk_math::log10_floor(0.0) == 0);

  const char* huge_end = nullptr;
  const double huge = mk_math::strtod("1e999999999999999999999", &huge_end);
  check_true("strtod huge", std::isinf(huge));
  check_true("strtod huge end", huge_end != nullptr && *huge_end == 0);
  check_true("strtod tiny", mk_math::strtod("1e-999999999999999999999", nullptr) == 0.0);
  check_near("strtod 20 digits", mk_math::strtod("12345678901234567890", nullptr), 1.2345678901234567e19, 1e-15);
}

static void test_transcendental(void) {
  std::printf("CORE transcendental vs libm (tol 1e-6):\n");
  const double tol = 1e-6;

  check_near("sin(1)",   mk_math::sin(1.0),   std::sin(1.0),   tol);
  check_near("sin(-0.7)",mk_math::sin(-0.7),  std::sin(-0.7),  tol);
  check_near("cos(1)",   mk_math::cos(1.0),   std::cos(1.0),   tol);
  check_near("cos(2)",   mk_math::cos(2.0),   std::cos(2.0),   tol);
  check_near("tan(0.5)", mk_math::tan(0.5),   std::tan(0.5),   tol);
  check_near("asin(.5)", mk_math::asin(0.5),  std::asin(0.5),  tol);
  check_near("acos(.5)", mk_math::acos(0.5),  std::acos(0.5),  tol);
  check_near("atan(.5)", mk_math::atan(0.5),  std::atan(0.5),  tol);
  check_near("ln(2)",    mk_math::ln(2.0),    std::log(2.0),   tol);
  check_near("ln(10)",   mk_math::ln(10.0),   std::log(10.0),  tol);
  check_near("log10(100)",mk_math::log10(100.0), std::log10(100.0), tol);
  check_near("exp(1)",   mk_math::exp(1.0),   std::exp(1.0),   tol);
  check_near("exp(-2)",  mk_math::exp(-2.0),  std::exp(-2.0),  tol);
  check_near("sqrt(2)",  mk_math::sqrt(2.0),  std::sqrt(2.0),  tol);
  check_near("sqrt(1024)",mk_math::sqrt(1024.0), 32.0,         tol);

  check_near("pow(2,10)", mk_math::pow(2.0, 10.0), 1024.0,      tol);
  check_near("pow(1.5,3)",mk_math::pow(1.5, 3.0),  std::pow(1.5, 3.0), tol);
  check_near("pow(4,0.5)",mk_math::pow(4.0, 0.5),  2.0,         tol);
  check_near("pow(x,0)",  mk_math::pow(7.0, 0.0),  1.0,         tol);
  check_near("pow(-2,3)", mk_math::pow(-2.0, 3.0), -8.0,        tol);

  check_true("sqrt domain", mk_math::is_nan(mk_math::sqrt(-4.0)));
  check_true("ln domain", mk_math::is_nan(mk_math::ln(-1.0)));
  check_true("asin domain", mk_math::is_nan(mk_math::asin(2.0)));
  check_true("input overflow", mk_math::is_nan(mk_math::sin(1e100)));
  check_true("non-finite input", mk_math::is_nan(mk_math::cos(__builtin_huge_val())));
}

static void test_authentic_core_smoke(void) {
  std::printf("authentic ROM/core arithmetic smoke:\n");
  core_61::set_expanded_program_mode(false);
  core_61::enable();
  MK61Emu_SetAngleUnit(DEGREE);

  const MatrixKey key_2 = {4, 1};
  const MatrixKey key_3 = {5, 1};
  const MatrixKey key_enter = {11, 8};
  const MatrixKey key_add = {2, 8};
  press_matrix(key_2);
  press_matrix(key_enter);
  press_matrix(key_3);
  press_matrix(key_add);
  check_near("2 ENTER 3 +", read_live_x(), 5.0, 1e-8);
}

static void test_core_boundaries(void) {
  std::printf("core boundary regressions:\n");
  core_61::set_expanded_program_mode(false);
  core_61::enable();

  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
  const char* run_indicator = MK61Emu_GetIndicatorStr(SYMBOLS);
  check_true("RUN indicator bounded", std::strlen(run_indicator) < INDICATOR_STRING_LENGTH);
  check_true("GetComma exported", MK61Emu_GetComma() == core_61::COMMA_RUN_POSITION);

  char update_buffer[INDICATOR_STRING_LENGTH + 2];
  std::memset(update_buffer, 0, sizeof(update_buffer));
  update_buffer[INDICATOR_STRING_LENGTH] = 'A';
  update_buffer[INDICATOR_STRING_LENGTH + 1] = 'B';
  core_61::update_indicator(update_buffer, SYMBOLS);
  check_true("update indicator bounded",
    update_buffer[INDICATOR_STRING_LENGTH] == 'A' &&
    update_buffer[INDICATOR_STRING_LENGTH + 1] == 'B');

  m_IK1302.comma = 10;
  check_true("left comma bounded", std::strlen(MK61Emu_GetIndicatorStr(SYMBOLS)) < INDICATOR_STRING_LENGTH);

  char valid_mantissa[8] = {'1','2','3','4','5','6','7','8'};
  char invalid_mantissa[8] = {'1','2','3','x','5','6','7','8'};
  u8 ring_before[SIZE_RING_M];
  std::memcpy(ring_before, ringM, sizeof(ringM));
  check_true("reject exponent +100", !write_stack_register(stack::X, ' ', valid_mantissa, 100));
  check_true("reject exponent -100", !write_stack_register(stack::X, ' ', valid_mantissa, -100));
  check_true("reject bad BCD digit", !write_stack_register(stack::X, ' ', invalid_mantissa, 0));
  check_true("rejection is atomic", std::memcmp(ring_before, ringM, sizeof(ringM)) == 0);

  char terminated[15];
  std::memset(terminated, 'X', sizeof(terminated));
  read_stack_register(stack::X, terminated, SYMBOLS);
  check_true("stack text terminated", terminated[14] == 0);

  for(int expanded = 0; expanded <= 1; expanded++) {
    core_61::set_expanded_program_mode(expanded != 0);
    core_61::enable();
    u8 input[core_61::CODE_PAGE_BUFFER_SIZE] = {};
    u8 output[core_61::CODE_PAGE_BUFFER_SIZE] = {};
    for(usize i = 0; i < core_61::program_steps(); i++) input[i] = (u8) ((i * 37u + 11u) & 0xFFu);
    core_61::set_code_page(input);
    core_61::get_code_page(output);
    check_true(expanded ? "expanded code page" : "classic code page",
      std::memcmp(input, output, core_61::program_steps()) == 0);
  }

  core_61::set_expanded_program_mode(true);
  core_61::enable();
  ringM[15 * 42 + 21] = 7;
  check_true("R_F seeded", MK61Emu_Read_R_mantissa(15) != 0);
  core_61::clear_memory_registers();
  check_true("R_F cleared", MK61Emu_Read_R_mantissa(15) == 0);
}

static void test_save_restore(void) {
  std::printf("core context save/restore isolation:\n");
  core_61::enable();
  MK61Emu_SetAngleUnit(DEGREE);
  core_61::edit_program = true;

  // Load the whole stack with distinct values.
  char mX[8] = {'1','2','3','4','5','0','0','0'}; write_stack_register(stack::X, ' ', mX, 2); // 123.45
  char mY[8] = {'6','7','8','9','0','0','0','0'}; write_stack_register(stack::Y, '-', mY, 0); // -6.789
  char mZ[8] = {'1','1','1','1','1','1','1','1'}; write_stack_register(stack::Z, ' ', mZ, 1); // 11.111111
  char mT[8] = {'9','8','7','6','5','4','3','2'}; write_stack_register(stack::T, ' ', mT, -3); // 0.0098765...

  const double bX = read_live_reg(stack::X);
  const double bY = read_live_reg(stack::Y);
  const double bZ = read_live_reg(stack::Z);
  const double bT = read_live_reg(stack::T);
  // X2 == the screen/display latch, kept separately from stack X.
  char x2_before[24]; std::strncpy(x2_before, MK61Emu_GetIndicatorStr(SYMBOLS), sizeof(x2_before) - 1);
  x2_before[sizeof(x2_before) - 1] = 0;

  // Borrow the core for a normal op and for a domain error (√ of a negative,
  // which latches ЕГГОГ inside the borrow); neither may leak into live state.
  (void) mk_math::sin(1.0);
  (void) mk_math::sqrt(-4.0);

  char x2_after[24]; std::strncpy(x2_after, MK61Emu_GetIndicatorStr(SYMBOLS), sizeof(x2_after) - 1);
  x2_after[sizeof(x2_after) - 1] = 0;

  check_true("angle preserved (DEGREE)", MK61Emu_GetAngleUnit() == DEGREE);
  check_true("edit mode preserved", core_61::edit_program);
  check_near("X preserved", read_live_reg(stack::X), bX, 1e-6);
  check_near("Y preserved", read_live_reg(stack::Y), bY, 1e-6);
  check_near("Z preserved", read_live_reg(stack::Z), bZ, 1e-6);
  check_near("T preserved", read_live_reg(stack::T), bT, 1e-6);
  check_true("X2/display preserved", std::strcmp(x2_before, x2_after) == 0);
}

int main(void) {
  test_pure_helpers();
  test_transcendental();
  test_authentic_core_smoke();
  test_core_boundaries();
  test_save_restore();

  if(g_failures == 0) {
    std::printf("mk_math_self_test: ok\n");
    return 0;
  }
  std::printf("mk_math_self_test: %d failure(s)\n", g_failures);
  return 1;
}
