#ifndef MK61_UI_DISPLAY_TEST_PANEL_HPP
#define MK61_UI_DISPLAY_TEST_PANEL_HPP
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>

// Only the hardware boundary is replaced. The production MK61Display, font
// lookup, damage tracking and eight-row page renderer are linked unmodified.
#define ERM19264_UC1609_H
enum LCD_Return_Codes_e { LCD_Success = 0 };
namespace ui_display_test {
using Frame = std::array<uint8_t, 192U * 8U>;
inline Frame frame{};
inline unsigned transfers = 0;
inline bool sleeping = false;
inline void reset() { frame.fill(0); transfers = 0; sleeping = false; }
}
class ERM19264_UC1609 {
 public:
  ERM19264_UC1609(int16_t, int16_t, int8_t, int8_t, int8_t) {}
  void LCDbegin(uint8_t, uint8_t) {}
  bool LCDSetSleep(bool value) { ui_display_test::sleeping = value; return true; }
  void LCDEnable(uint8_t) {}
  void LCDBuffer(int16_t x, int16_t y, uint8_t width, uint8_t height,
                 uint8_t* pixels) {
    assert(x >= 0 && y >= 0 && x + width <= 192 && y + height <= 64);
    assert(y % 8 == 0 && height % 8 == 0);
    assert(pixels != nullptr);
    for(unsigned page = 0; page < height / 8U; ++page) {
      std::memcpy(ui_display_test::frame.data() + (y / 8U + page) * 192U + x,
                  pixels + page * width, width);
    }
    ++ui_display_test::transfers;
  }
  LCD_Return_Codes_e LCDBitmap(int16_t x, int16_t y, uint8_t width,
                              uint8_t height, const uint8_t* pixels) {
    LCDBuffer(x, y, width, height, const_cast<uint8_t*>(pixels));
    return LCD_Success;
  }
};
#endif
