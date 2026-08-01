#include <cassert>
#include <iostream>

#include "mpu_guard_policy.hpp"

int main(void) {
  using namespace mpu_guard_policy;

  static_assert(power_of_two(32), "minimum MPU region");
  static_assert(power_of_two(256), "guard MPU region");
  static_assert(!power_of_two(48), "invalid MPU region");
  static_assert(region_size_encoding(32) == 4, "32-byte encoding");
  static_assert(region_size_encoding(256) == 7, "256-byte encoding");
  static_assert(region_size_encoding(64 * 1024) == 15,
                "64-KiB encoding");
  static_assert(region_size_encoding(128 * 1024) == 16,
                "128-KiB encoding");

  const Layout f401 = make_layout(
      F401_PROFILE, 0x2000E4D0UL, 0x2000FFF0UL, 8);
  assert(f401.valid);
  assert(f401.required_regions == 2);
  assert(f401.guard_base == 0x2000E700UL);
  assert(f401.guard_end == 0x2000E800UL);
  assert(!f401.sram_execute_never);

  assert(!make_layout(F401_PROFILE, 0x2000E701UL,
                      0x2000FFF0UL, 8).valid);
  assert(!make_layout(F401_PROFILE, 0x2000E4D0UL,
                      0x2000E7FCUL, 8).valid);
  assert(!make_layout(F401_PROFILE, 0x2000E4D0UL,
                      0x2000FFF0UL, 1).valid);

  const Layout f411 = make_layout(
      F411_PROFILE, 0x2000AD88UL, 0x2001FFF0UL, 8);
  assert(f411.valid);
  assert(f411.required_regions == 3);
  assert(f411.guard_base == 0x2001BF00UL);
  assert(f411.guard_end == 0x2001C000UL);
  assert(f411.sram_execute_never);

  assert(!make_layout(F411_PROFILE, 0x2001BF01UL,
                      0x2001FFF0UL, 8).valid);
  assert(!make_layout(F411_PROFILE, 0x2000AD88UL,
                      0x2001FFF0UL, 2).valid);

  const Profile bad_guard = {
      0x20000000UL, 64UL * 1024UL, 6UL * 1024UL, 192UL, false};
  assert(!make_layout(bad_guard, 0x20001000UL,
                      0x2000FFF0UL, 8).valid);

  std::cout << "mpu_guard_policy_self_test: ok\n";
  return 0;
}
