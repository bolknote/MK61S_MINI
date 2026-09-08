#include "rust_types.h"

typedef enum {
  X1 = 0,
  X = 1,
  Y = 2,
  Z = 3,
  T = 4
} stack;

#define MK61_REF_HOST_TEST
#include "mk61_ref.hpp"

#include <assert.h>
#include <stdio.h>

namespace mk61_ref {
double host_stack_value[5];
double host_register_value[16];
bool host_rf_enabled;
}

static void test_short_register_name_does_not_read_past_end(void) {
  char short_name[2] = {'R', 0};
  mk61_ref::Ref ref = {};
  assert(!mk61_ref::parse_name(short_name, ref));
}

static void test_valid_and_invalid_names(void) {
  mk61_ref::Ref ref = {};
  assert(mk61_ref::parse_name("X", ref));
  assert(ref.kind == mk61_ref::Kind::X);

  assert(mk61_ref::parse_name("rF", ref));
  assert(ref.kind == mk61_ref::Kind::R);
  assert(ref.reg == 15);

  assert(!mk61_ref::parse_name("R00", ref));
  assert(!mk61_ref::parse_name("RZ", ref));
  assert(!mk61_ref::parse_name("", ref));
  assert(!mk61_ref::parse_name(NULL, ref));
}

static void test_raw_register_write_is_exact_and_bounded(void) {
  mk61_ref::host_reset();
  const u8 naval_battle_rb[12] = {
      8, 0xC, 0xE, 0xC, 6, 0xA, 0xB, 0xA, 9, 9, 0, 7};
  assert(mk61_ref::write_raw_register(0x0B, naval_battle_rb));
  assert(mk61_ref::host_register_is_raw()[0x0B]);
  assert(memcmp(mk61_ref::host_register_raw()[0x0B], naval_battle_rb,
                sizeof(naval_battle_rb)) == 0);
  const mk61_ref::Ref rb = {mk61_ref::Kind::R, 0x0B};
  assert(mk61_ref::write(rb, 12.5));
  assert(!mk61_ref::host_register_is_raw()[0x0B]);

  u8 invalid[12] = {};
  invalid[5] = 0x10;
  assert(!mk61_ref::write_raw_register(0, invalid));
  assert(!mk61_ref::host_register_is_raw()[0]);
  assert(!mk61_ref::write_raw_register(0x0F, naval_battle_rb));
  mk61_ref::host_set_rf_enabled(true);
  assert(mk61_ref::write_raw_register(0x0F, naval_battle_rb));
}

static void check_fraction7(u32 value, const char expected[9], isize exponent) {
  char mantissa[8] = {};
  isize actual_exponent = 0;
  assert(mk61_ref::fraction7_to_parts(value, mantissa, actual_exponent));
  assert(memcmp(mantissa, expected, 8) == 0);
  assert(actual_exponent == exponent);
}

static void test_random_fraction_is_exact(void) {
  check_fraction7(1,       "10000000", -7);
  check_fraction7(1234,    "12340000", -4);
  check_fraction7(1234567, "12345670", -1);
  check_fraction7(9999999, "99999990", -1);

  char mantissa[8] = {};
  isize exponent = 0;
  assert(!mk61_ref::fraction7_to_parts(0, mantissa, exponent));
  assert(!mk61_ref::fraction7_to_parts(10000000, mantissa, exponent));

  mk61_ref::host_reset();
  const mk61_ref::Ref r3 = {mk61_ref::Kind::R, 3};
  assert(mk61_ref::write_fraction7(r3, 1234));
  assert(!mk61_ref::host_register_is_raw()[3]);
  assert(mk61_ref::host_get_register(3) == 0.0001234);
}

int main(void) {
  test_short_register_name_does_not_read_past_end();
  test_valid_and_invalid_names();
  test_raw_register_write_is_exact_and_bounded();
  test_random_fraction_is_exact();
  printf("mk61_ref_self_test: ok\n");
  return 0;
}
