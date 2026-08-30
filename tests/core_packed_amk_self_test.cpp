#include <cassert>
#include <cstdint>
#include <cstdio>

#include "core_packed_amk.hpp"

int main() {
  for(unsigned a = 0; a <= 67; a++) {
    for(unsigned b = 0; b <= 67; b++) {
      for(unsigned c = 0; c <= 67; c++) {
        for(unsigned latch_bits = 0; latch_bits < 8; latch_bits++) {
          const core_packed_amk::Selection reference =
              core_packed_amk::select_reference(
                  (u8) a, (u8) b, (u8) c,
                  (latch_bits & 1U) != 0,
                  (latch_bits & 2U) != 0,
                  (latch_bits & 4U) != 0);
          const core_packed_amk::Selection modeled =
              core_packed_amk::select_instruction_model(
                  (u8) a, (u8) b, (u8) c,
                  (latch_bits & 1U) != 0,
                  (latch_bits & 2U) != 0,
                  (latch_bits & 4U) != 0);
          assert(reference.ik1302 == modeled.ik1302);
          assert(reference.ik1303 == modeled.ik1303);
          assert(reference.ik1306 == modeled.ik1306);
        }
      }
    }
  }

  static_assert(core_packed_amk::adjust_reference(59, false) == 59);
  static_assert(core_packed_amk::adjust_reference(60, false) == 61);
  static_assert(core_packed_amk::adjust_reference(67, false) == 68);
  static_assert(core_packed_amk::adjust_reference(60, true) == 60);
  std::puts("core_packed_amk_self_test: ok");
  return 0;
}
