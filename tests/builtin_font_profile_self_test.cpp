#include "builtin_font.hpp"

#include <assert.h>
#include <stdio.h>

int main() {
#if defined(MK61_LCD1602_A02)
  // The A02 CGROM supplies the complete standard Russian alphabet.
  assert(builtin_font::rows5x8(0x0410) == nullptr);
  assert(builtin_font::rows5x8(0x0411) == nullptr);
  assert(builtin_font::rows5x8(0x042F) == nullptr);
  assert(builtin_font::rows5x8(0x0404) != nullptr);
  assert(builtin_font::rows5x8(0x0454) == nullptr);
#elif defined(MK61_OLED1602_WS0010)
  // FT=10 supplies standard Russian in both cases, while the supplemental
  // Ukrainian/Belarusian characters still need CGRAM bitmaps.
  assert(builtin_font::rows5x8(0x0410) == nullptr);
  assert(builtin_font::rows5x8(0x0430) == nullptr);
  assert(builtin_font::rows5x8(0x0404) != nullptr);
  assert(builtin_font::rows5x8(0x0454) != nullptr);
#else
  // A00 supplies Latin-shaped Russian letters in CGROM.  Only the remaining
  // uppercase letters and uppercase supplemental set belong in firmware.
  assert(builtin_font::rows5x8(0x0410) == nullptr); // А -> A in CGROM
  assert(builtin_font::rows5x8(0x0411) != nullptr); // Б needs CGRAM
  assert(builtin_font::rows5x8(0x042F) != nullptr); // Я needs CGRAM
  assert(builtin_font::rows5x8(0x0404) != nullptr);
  assert(builtin_font::rows5x8(0x0454) == nullptr);
#endif

  printf("builtin_font_profile_self_test: ok\n");
  return 0;
}
