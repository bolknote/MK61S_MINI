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

int main(void) {
  test_short_register_name_does_not_read_past_end();
  test_valid_and_invalid_names();
  printf("mk61_ref_self_test: ok\n");
  return 0;
}
