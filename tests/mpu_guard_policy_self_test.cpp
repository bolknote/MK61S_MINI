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

  const Layout portable = with_app_execution(f411, 8);
  assert(portable.valid && portable.required_regions == 8);
  assert(portable.sram_execute_never && portable.guard_base == f411.guard_base);
  assert(!with_app_execution(f411, 7).valid);
  assert(with_app_execution(f401, 2).required_regions == 2);
  // Decode actual MPU base/size/SRD at every minimum-size (32-byte) block
  // of SRAM, for every possible rounded APP size. Include globals and stack.
  u8 maximum_regions = 0;
  for(u32 bytes = 32; bytes <= 20U * 1024U; bytes += 32) {
    const u32 begin = f411.guard_base - bytes;
    AppRegion regions[APP_REGION_COUNT] = {};
    u8 count = 0;
    for(u32 cursor = begin; cursor < f411.guard_base;) {
      assert(count < APP_REGION_COUNT);
      const AppRegion region = next_app_region(cursor, f411.guard_base);
      assert(power_of_two(region.size) && (region.base & (region.size - 1)) == 0);
      assert(region.end > cursor && region.end <= f411.guard_base);
      regions[count++] = region;
      cursor = region.end;
    }
    if(count > maximum_regions) maximum_regions = count;
    for(u32 address = f411.ram_start; address < f411.ram_end; address += 32) {
      bool executable = false;
      for(u8 i = 0; i < count; ++i) {
        const AppRegion& r = regions[i];
        if(address < r.base || address >= r.base + r.size) continue;
        if(r.size < 256 || (r.disabled_subregions &
            (1U << ((address - r.base) / (r.size / 8)))) == 0) executable = true;
      }
      assert(executable == (address >= begin && address < f411.guard_base));
    }
  }
  assert(maximum_regions == APP_REGION_COUNT);
  // Exhaust every 256-aligned end in F411 SRAM and every 32-byte payload
  // size through the unchanged 20-KiB limit. Decode only the real MPU
  // base/size/SRD fields; the planner's cached end is not the coverage oracle.
  unsigned placements=0;u8 displaced_max=0;
  for(u32 end=f411.ram_start+APP_END_ALIGNMENT;end<=f411.guard_base;end+=APP_END_ALIGNMENT)
    for(u32 bytes=32;bytes<=20U*1024U && bytes<=end-f411.ram_start;bytes+=32) {
      const u32 begin=end-bytes;u32 cursor=begin,covered=begin;u8 count=0;
      while(cursor<end) {
        assert(count++<APP_REGION_COUNT);
        const auto region=next_app_region(cursor,end);
        assert(power_of_two(region.size) && !(region.base&(region.size-1)));
        const u32 step=region.size>=256?region.size/8:region.size;
        const u32 parts=region.size>=256?8:1;
        for(u32 i=0;i<parts;++i) {
          if(region.size>=256 && (region.disabled_subregions&(1U<<i)))continue;
          const u32 first=region.base+i*step;
          assert(first==covered && first>=begin && step<=end-first);
          covered=first+step;
        }
        assert(covered==region.end && covered>cursor);cursor=region.end;
      }
      assert(covered==end);if(count>displaced_max)displaced_max=count;++placements;
    }
  assert(displaced_max==APP_REGION_COUNT && placements>250000);
  // An arbitrary end can really require six slots. The allocator's alignment
  // rule is necessary; do not solve it by widening executable SRAM.
  unsigned unaligned_count=0;
  for(u32 cursor=0x200136E0U;cursor<0x20014920U;++unaligned_count)
    cursor=next_app_region(cursor,0x20014920U).end;
  assert(unaligned_count==6);
  std::cout<<"MPU displaced APP: "<<placements<<" exact spans, maximum "
           <<unsigned(displaced_max)<<" regions, six-region rejection case PASS\n";

  assert(next_app_region(f411.guard_base - 1, f411.guard_base).size == 0);
  assert(next_app_region(f411.guard_base, f411.guard_base).size == 0);

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
