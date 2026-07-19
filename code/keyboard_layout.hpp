#ifndef MK61_KEYBOARD_LAYOUT_HPP
#define MK61_KEYBOARD_LAYOUT_HPP

#include "rust_types.h"

namespace keyboard_layout {

struct Mapping {
  i32 cx;
  i32 bx;
  i32 mul;
  i32 div;
  i32 power;
  i32 xy;
  i32 add;
  i32 sub;
  i32 neg;
  i32 dot;
  i32 digit[10];
  i32 pp;
  i32 bp;
  i32 x_to_p;
  i32 p_to_x;
  i32 run;
  i32 ret;
  i32 frw;
  i32 bkw;
  i32 k;
  i32 alpha;
  i32 degree;
  i32 grade;
  i32 radian;
  i32 user;
  i32 save;
  i32 load;
  i32 left;
  i32 right;
  i32 ok;
  i32 esc;
  i32 shg_left;
  i32 shg_right;
};

static constexpr Mapping MINI = {
  0, 1, 2, 3, 5, 6, 7, 8, 10, 15,
  {20, 21, 16, 11, 22, 17, 12, 23, 18, 13},
  25, 26, 27, 28, 30, 31, 32, 33, 37, 38,
  4, 9, 14, 19, 36, 35, 34, 24, 29, 39, 32, 33
};

static constexpr Mapping CLASSIC = {
  0, 5, 10, 15, 1, 6, 11, 16, 2, 3,
  {4, 9, 8, 7, 14, 13, 12, 19, 18, 17},
  20, 21, 22, 23, 25, 26, 28, 27, 24, 29,
  30, 31, 32, 35, 34, 33, 38, 36, 37, 39, 27, 28
};

// The 40TH board uses the same physical 5x8 matrix as mk61s-mini. Its
// calculator key translation is also the mini table in cross_hal.cpp.
static constexpr Mapping FORTIETH = MINI;

#if defined(MK61_KEYBOARD_CLASSIC)
static constexpr Mapping ACTIVE = CLASSIC;
#elif defined(MK61_KEYBOARD_40TH)
static constexpr Mapping ACTIVE = FORTIETH;
#else
static constexpr Mapping ACTIVE = MINI;
#endif

static_assert(MINI.k != MINI.right, "mini K and Right must be distinct");
static_assert(MINI.alpha != MINI.ok, "mini F and OK must be distinct");
static_assert(CLASSIC.k != CLASSIC.right, "classic K and Right must be distinct");
static_assert(CLASSIC.alpha != CLASSIC.ok, "classic F and OK must be distinct");
static_assert(FORTIETH.k != FORTIETH.right, "40TH K and Right must be distinct");
static_assert(FORTIETH.alpha != FORTIETH.ok, "40TH F and OK must be distinct");

inline int digit_from_key(const Mapping& mapping, i32 key_code) {
  for(int digit = 0; digit <= 9; digit++) {
    if(key_code == mapping.digit[digit]) return digit;
  }
  return -1;
}

} // namespace keyboard_layout

#endif
