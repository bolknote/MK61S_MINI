#include "builtin_font.hpp"

#include <assert.h>
#include <stdio.h>

int main() {
#if defined(MK61_LCD1602_A02)
  // The A02 CGROM supplies the complete standard Russian alphabet.
  assert(builtin_font::rows5x8(0x0410) == nullptr);
  assert(builtin_font::rows5x8(0x0411) == nullptr);
  assert(builtin_font::rows5x8(0x042F) == nullptr);
#elif defined(MK61_OLED1602_WS0010)
  // FT=10 supplies standard Russian in both cases.
  assert(builtin_font::rows5x8(0x0410) == nullptr);
  assert(builtin_font::rows5x8(0x0430) == nullptr);
#else
  // A00 supplies Latin-shaped Russian letters in CGROM. Only the remaining
  // uppercase Russian letters belong in firmware.
  assert(builtin_font::rows5x8(0x0410) == nullptr); // А -> A in CGROM
  assert(builtin_font::rows5x8(0x0411) != nullptr); // Б needs CGRAM
  assert(builtin_font::rows5x8(0x042F) != nullptr); // Я needs CGRAM
#endif

  static constexpr u16 unsupported[] = {
    0x0404, 0x0454, 0x0406, 0x0456, 0x0407,
    0x0457, 0x0490, 0x0491, 0x040E, 0x045E,
  };
  for(const u16 codepoint : unsupported) {
    assert(builtin_font::rows5x8(codepoint) == nullptr);
  }

  printf("builtin_font_profile_self_test: ok\n");
  return 0;
}
