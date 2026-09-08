#include "rust_types.h"

typedef enum {
  X1 = 0,
  X = 1,
  Y = 2,
  Z = 3,
  T = 4
} stack;

static constexpr u32 MK61_SYS_SETTINGS = 1;
static constexpr u32 MK61_SYS_REGISTER_F = 2;
static constexpr u32 MK61_SYS_REF_READ = 3;
static constexpr u32 MK61_SYS_REF_WRITE = 4;

namespace portable_system {
u32 call(u32 operation, u32 a = 0, u32 b = 0, u32 c = 0,
         void* data = nullptr);
}

#define MK61_BUILD_PORTABLE_SYSTEM
#include "mk61_ref.hpp"

#include <assert.h>
#include <stdio.h>

namespace {
u32 captured_operation;
u32 captured_kind;
u32 captured_register;
double captured_number;
}

namespace portable_system {
u32 call(u32 operation, u32 a, u32 b, u32, void* data) {
  if(operation == MK61_SYS_SETTINGS) return a == MK61_SYS_REGISTER_F;
  if(operation == MK61_SYS_REF_WRITE) {
    assert(data != nullptr);
    captured_operation = operation;
    captured_kind = a;
    captured_register = b;
    captured_number = *static_cast<double*>(data);
    return 1;
  }
  return 0;
}
}

int main(void) {
  const mk61_ref::Ref r3 = {mk61_ref::Kind::R, 3};
  assert(mk61_ref::write_fraction7(r3, 1234));
  assert(captured_operation == MK61_SYS_REF_WRITE);
  assert(captured_kind == (u32) mk61_ref::Kind::R);
  assert(captured_register == 3);
  assert(captured_number == 0.0001234);

  const u8 raw[12] = {};
  assert(!mk61_ref::write_raw_register(3, raw));
  printf("mk61_ref_portable_self_test: ok\n");
  return 0;
}
