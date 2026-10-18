#ifndef MK61_PICOCALC_FONTS_HPP
#define MK61_PICOCALC_FONTS_HPP
#include "settings.hpp"
#include "loadable_app_services.h"
#include "prepared_font.hpp"

namespace picocalc { namespace fonts {
struct Item { u32 key; u8 family, size; char name[64]; };
unsigned count();
bool item(unsigned index, Item& out);
bool describe(u32 key, Item& out);
bool step(u32 key, int direction, Item& out);
u32 key(const Settings& settings);
// Validate/prepare a complete candidate before replacing the active font.
bool select(const Settings& settings);
bool install(const u8* data, unsigned size, u32 key, unsigned expected_height);
u32 service(const Settings& settings, u32 op, u32 cp, u32 size, void* out);
bool glyph(const Settings& settings, u32 cp, mk61_service_ui_glyph& out);
mk61_service_ui_font_info info(const Settings& settings);
const prepared_font::Face* external_face(const Settings& settings);
u32 revision();
} }
#endif
