#ifndef MK61_EXPLORER_VIEW_HPP
#define MK61_EXPLORER_VIEW_HPP

#include "rust_types.h"

// Native monochrome presentation only. File ownership and launch policy stay
// with the platform browser; drawing never opens a file or allocates memory.
namespace explorer_view {
constexpr u16 ICON_WIDTH = 32, ICON_HEIGHT = 32;
constexpr usize ICON_BYTES = 128;
constexpr usize MAX_ICON_FILE_BYTES = 140;
constexpr const char* ICON_NAME = "autoexec.wbmp";
enum class Mode : u8 { ICONS, LIST };
enum class Packing : u8 { ROW_MSB, PAGE_LSB };
enum class Kind : u8 { FILE, DIRECTORY };
struct Icon { u8 pixels[ICON_BYTES]; };
struct Glyph {
  u8 width, height, advance, bearing_x;
  i8 bearing_y;
  u8 pixels[32];
};
using GlyphProvider = bool (*)(void*, u8 height, u16 codepoint, Glyph&);

// All accepted WBMP Type 0 headers are checked by the shared decoder. Other
// dimensions, truncated/oversized input and malformed files use a fallback.
bool decode_icon(const u8* data, usize size, Icon& out);

struct Geometry {
  u16 width, height;
  Mode mode;
  bool classic() const { return width == 192 && height == 64; }
  bool supported() const { return classic() || (width == 320 && height == 320); }
  u8 font_height() const { return classic() ? 8 : 16; }
  u8 page_size() const { return mode == Mode::ICONS ? (classic() ? 3 : 9) : (classic() ? 5 : 9); }
  u16 label_width() const { return mode == Mode::ICONS ? (classic() ? 60 : 94) : width - (classic()?12:32); }
};

class Canvas {
 public:
  Canvas(u8* data, usize bytes, Geometry geometry, Packing packing,
         GlyphProvider provider, void* context = nullptr);
  bool ok() const { return valid_; }
  void clear();
  void pixel(i16 x, i16 y, bool ink = true);
  void rectangle(i16 x,i16 y,u16 width,u16 height,bool ink=true);
  u16 measure(const char* m8,u8 height) const;
  void text(i16 x,i16 y,const char* m8,u8 height,u16 max_width,bool ink=true);
  void header(const char* title,const char* progress,const char* file,bool parent);
  void item(u8 slot,const char* name,Kind kind,const Icon* icon,bool selected,u8 offset=0);
  void empty(const char* text);
 private:
  bool glyph(u8 height,u8 m8,Glyph& out) const;
  u8* data_;
  usize bytes_;
  Geometry geometry_;
  Packing packing_;
  GlyphProvider provider_;
  void* context_;
  bool valid_;
};
} // namespace explorer_view
#endif
