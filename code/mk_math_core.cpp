// CORE math backend: transcendental functions evaluated on the MK-61 engine.
//
// Enabled only when MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE. Under the LIBM
// backend this translation unit is empty, so it can stay in the build unchanged.
//
// Each call borrows the calculator: the live user state is snapshotted, the core
// is reset to a clean calculator, the argument is written to X, the function
// keystrokes are replayed, the result is read back from X, and finally the user
// state is restored. Precision is the native 8 significant digits of the MK-61.

#include "config.h"

#if MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE

#include "mk_math.hpp"
#include "mk61emu_core.h"
#include <string.h>

namespace {

// Fixed MK-61 key-matrix codes (the emulated calculator's own scan codes, not
// the host keyboard layout). Function keys are reached with the F prefix.
struct MatrixKey { int x, y; };
const MatrixKey KEY_F   = {11, 9};
const MatrixKey KEY_1   = {3, 1};   // F 1 -> eˣ
const MatrixKey KEY_2   = {4, 1};   // F 2 -> lg
const MatrixKey KEY_3   = {5, 1};   // F 3 -> ln
const MatrixKey KEY_4   = {6, 1};   // F 4 -> arcsin
const MatrixKey KEY_5   = {7, 1};   // F 5 -> arccos
const MatrixKey KEY_6   = {8, 1};   // F 6 -> arctg
const MatrixKey KEY_7   = {9, 1};   // F 7 -> sin
const MatrixKey KEY_8   = {10, 1};  // F 8 -> cos
const MatrixKey KEY_9   = {11, 1};  // F 9 -> tg
const MatrixKey KEY_SUB = {3, 8};   // F "−" -> √

// Symbol set for read_stack_register: raw digits so parsing needs no remapping.
const char CORE_SYMBOLS[16] = {
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', ' ', ' ', ' ', ' ', ' '
};

void press(const MatrixKey& key) {
  core_61::clear_displayed();
  // Hold phase, mirroring hidden_press_key() in library_pmk.cpp.
  for(int i = 0; i < 4; i++) {
    MK61Emu_SetKeyPress(key.x, key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0, 0);
  // Settle phase: run until the result is latched onto the display.
  for(int i = 0; i < 512; i++) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }
}

bool set_x(double value) {
  if(!mk_math::is_finite(value)) return false;
  char sign = (value < 0.0) ? '-' : ' ';
  double a = mk_math::fabs(value);
  char mantissa[8];
  isize pow10 = 0;

  if(a == 0.0) {
    memset(mantissa, '0', 8);
  } else {
    pow10 = (isize) mk_math::log10_floor(a);
    if(pow10 < -99 || pow10 > 99) return false;
    double normalized = a / mk_math::pow10_int((int) pow10);
    if(normalized >= 10.0) { normalized /= 10.0; pow10++; }
    if(normalized < 1.0)   { normalized *= 10.0; pow10--; }
    long scaled = (long) mk_math::floor(normalized * 10000000.0 + 0.5);
    if(scaled >= 100000000L) {
      scaled /= 10;
      pow10++;
      if(pow10 > 99) return false;
    }
    for(int i = 7; i >= 0; i--) { mantissa[i] = (char) ('0' + (scaled % 10)); scaled /= 10; }
  }
  return write_stack_register(stack::X, sign, mantissa, pow10);
}

double read_x(void) {
  char value[15];
  value[14] = 0;
  read_stack_register(stack::X, value, CORE_SYMBOLS);

  // cvalue holds "d.ddddddd" in [1..9] (decimal point at index 2), then a space,
  // an exponent sign, and two exponent digits. Keep the '.' so the value is not
  // scaled by 10^7.
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

// Borrow the core to run F+<key> on the argument, then hand it back untouched.
//
// The whole live state is snapshotted first, so restoring it afterwards puts
// back every user-visible register byte-for-byte: the stack (X1/X/Y/Z/T), the
// memory registers, the angle unit, the screen register X2 (display latch) and
// any pending error latch. A domain error during the borrow (e.g. √ of a
// negative) therefore cannot leak out - restore_context() wipes it.
double eval_unary(double x, const MatrixKey& op) {
  if(!mk_math::is_finite(x)) return __builtin_nan("");
  if(x != 0.0) {
    const int exponent = mk_math::log10_floor(mk_math::fabs(x));
    if(exponent < -99 || exponent > 99) return __builtin_nan("");
  }
  core_61::save_context();

  core_61::enable();          // clean calculator: no leftover prefix/error
  MK61Emu_SetAngleUnit(RADIAN);
  double result = __builtin_nan("");
  if(set_x(x)) {
    press(KEY_F);
    press(op);
    // An error indication takes a few additional engine steps to propagate
    // from the microcode state into the display ring. Normal results are
    // already stable at this point and remain unchanged during these steps.
    for(int i = 0; i < 4 && !core_61::is_RUN(); i++) core_61::step();
    if(!core_61::has_error()) result = read_x();
  }

  core_61::restore_context(); // hand the calculator back exactly as it was
  return result;
}

} // namespace

namespace mk_math {

double sin(double x)   { return eval_unary(x, KEY_7); }
double cos(double x)   { return eval_unary(x, KEY_8); }
double tan(double x)   { return eval_unary(x, KEY_9); }
double asin(double x)  { return eval_unary(x, KEY_4); }
double acos(double x)  { return eval_unary(x, KEY_5); }
double atan(double x)  { return eval_unary(x, KEY_6); }
double ln(double x)    { return eval_unary(x, KEY_3); }
double log10(double x) { return eval_unary(x, KEY_2); }
double exp(double x)   { return eval_unary(x, KEY_1); }
double sqrt(double x)  { return eval_unary(x, KEY_SUB); }

// pow(base, exponent) as exp(exponent * ln(base)); the 2-key xʸ protocol is
// fragile, so this composition is used instead (see plan).
double pow(double base, double exponent) {
  if(is_nan(base) || is_nan(exponent)) return __builtin_nan("");
  if(exponent == 0.0) return 1.0;
  if(base == 0.0) return (exponent > 0.0) ? 0.0 : __builtin_huge_val();
  if(base > 0.0) return mk_math::exp(exponent * mk_math::ln(base));

  // base < 0: real only for integer exponents.
  const double rounded = mk_math::round_half(exponent);
  if(!is_finite(rounded) || exponent != rounded) return __builtin_nan("");

  const double magnitude = mk_math::exp(exponent * mk_math::ln(-base));
  if(mk_math::is_nan(magnitude)) return magnitude;
  const bool odd = mk_math::fabs(rounded) < 9007199254740992.0 && ((((long long) rounded) & 1LL) != 0);
  return odd ? -magnitude : magnitude;
}

} // namespace mk_math

#endif // MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE
