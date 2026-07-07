// Host self test for the mk_math CORE backend.
//
// Compiles the real MK-61 engine (mk61emu_core.cpp) together with the CORE math
// backend (mk_math_core.cpp) and checks that every transcendental matches libm
// within the calculator's 8-digit precision, that pow() behaves, that the pure
// libm-free helpers agree with <math.h>, and that borrowing the core leaves the
// live user state untouched.

#include <cmath>
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
  check_true("log10_floor 100", mk_math::log10_floor(100.0) == 2);
  check_true("log10_floor 0.01", mk_math::log10_floor(0.01) == -2);
  check_true("log10_floor 5", mk_math::log10_floor(5.0) == 0);
  check_true("log10_floor 0.5", mk_math::log10_floor(0.5) == -1);

  const char* endp = nullptr;
  check_near("atof int", mk_math::atof("123"), 123.0, 1e-9);
  check_near("atof frac", mk_math::atof("3.14159"), 3.14159, 1e-9);
  check_near("atof sci", mk_math::atof("-1.5e3"), -1500.0, 1e-9);
  double v = mk_math::strtod("42.5abc", &endp);
  check_near("strtod value", v, 42.5, 1e-9);
  check_true("strtod endptr", endp != nullptr && *endp == 'a');
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
}

static void test_save_restore(void) {
  std::printf("core context save/restore isolation:\n");
  core_61::enable();
  MK61Emu_SetAngleUnit(DEGREE);

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
  check_near("X preserved", read_live_reg(stack::X), bX, 1e-6);
  check_near("Y preserved", read_live_reg(stack::Y), bY, 1e-6);
  check_near("Z preserved", read_live_reg(stack::Z), bZ, 1e-6);
  check_near("T preserved", read_live_reg(stack::T), bT, 1e-6);
  check_true("X2/display preserved", std::strcmp(x2_before, x2_after) == 0);
}

int main(void) {
  test_pure_helpers();
  test_transcendental();
  test_save_restore();

  if(g_failures == 0) {
    std::printf("mk_math_self_test: ok\n");
    return 0;
  }
  std::printf("mk_math_self_test: %d failure(s)\n", g_failures);
  return 1;
}
