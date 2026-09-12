#ifndef MK61_MARKDOWN_UI_FONT_HPP
#define MK61_MARKDOWN_UI_FONT_HPP

#include "config.h"
#include "loadable_app_services.h"
#if MK61_UI_FONT_CLIENT && !defined(MK61_BUILD_PORTABLE_SYSTEM)
#include "ui_font_service.hpp"
#endif

namespace markdown_ui_font {

class Source {
 public:
  Source() : info{} {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && MK61_PORTABLE_UI_FONTS
    if(portable_system::api != nullptr &&
       (portable_system::call(MK61_SERVICE_CAPABILITIES) & MK61_SERVICE_CAP_UI_FONT)) {
      if(!portable_system::call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_INFO,
                                0, sizeof(info), &info)) info = {};
    }
#elif MK61_UI_FONT_CLIENT
    ui_font_service::call(main_lcd().uiFontFamily(), main_lcd().uiFontSize(),
                         MK61_UI_FONT_INFO, 0, sizeof(info), &info);
#endif
    if(!valid()) info = {};
  }

  bool enabled() const { return info.family != 0; }
  uint8_t height() const { return info.size; }
  uint8_t ascent() const { return info.ascent; }
  uint8_t line_gap() const { return info.line_gap; }

  bool glyph(uint16_t codepoint, mk61_service_ui_glyph& out) const {
    if(!enabled()) return false;
    out = {};
    out.family = info.family;
    out.size = info.size;
    bool ok = false;
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && MK61_PORTABLE_UI_FONTS
    ok = portable_system::call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_GLYPH,
                               codepoint, sizeof(out), &out) != 0;
#elif MK61_UI_FONT_CLIENT
    ok = ui_font_service::call(info.family, info.size, MK61_UI_FONT_GLYPH,
                               codepoint, sizeof(out), &out) != 0;
#else
    (void) codepoint;
#endif
    // A portable module validates the wire data before indexing its bitmap.
    return ok && out.family == info.family && out.size == info.size &&
      out.width > 0 && out.width <= 16 && out.height > 0 && out.height <= info.size &&
      out.bearing_x <= 16 && out.advance <= 32 &&
      out.advance > out.bearing_x + out.width &&
      info.ascent >= out.bearing_y &&
      static_cast<int>(out.height) - out.bearing_y <= info.descent;
  }

  static bool pixel(const mk61_service_ui_glyph& value, uint8_t x, uint8_t y) {
    if(x >= value.width || y >= value.height || value.width > 16 || value.height > 16) return false;
    const unsigned offset = static_cast<unsigned>(y) * ((value.width + 7U) / 8U) + x / 8U;
    return (value.pixels[offset] & (0x80U >> (x % 8U))) != 0;
  }

  static uint8_t italic_shift(const mk61_service_ui_glyph& value, uint8_t row) {
    return row < value.height ? static_cast<uint8_t>((value.height - 1U - row) / 3U) : 0;
  }

  static uint8_t advance(const mk61_service_ui_glyph& value, bool bold, bool italic) {
    return static_cast<uint8_t>(value.advance + (bold ? 1U : 0U) +
                               (italic ? italic_shift(value, 0) : 0U));
  }

 private:
  mk61_service_ui_font_info info;
  bool valid() const {
    return (info.family == 1 || info.family == 2) &&
      (info.size == 12 || info.size == 14 || info.size == 16) &&
      info.ascent + info.descent == info.size && info.ascent > 0 &&
      info.line_gap == (info.size == 12 ? 1 : 2);
  }
};

} // namespace markdown_ui_font

#endif
