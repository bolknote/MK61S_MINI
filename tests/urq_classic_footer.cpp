// Render the Classic hints for the hardware controller using resident fonts.
#include "../examples/portable-apps/URQ/classic_view.hpp"
#include "../code/builtin_font.hpp"
#include <assert.h>
#include <stdio.h>

const mk61_app_api* mk61_api = nullptr;

static uint32_t font(uint32_t service, uint32_t, uint32_t cp, uint32_t, void* raw) {
  assert(service == MK61_SERVICE_FONT);
  builtin_font::Raster glyph{};
  assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8, uint16_t(cp), glyph));
  auto& result = *static_cast<mk61_service_glyph*>(raw);
  result.width = glyph.width; result.height = glyph.height;
  memcpy(result.pixels, glyph.data, 8);
  return 1;
}

int main() {
  mk61_app_services services{};
  services.call = font;
  const char* const hints[] = {
    M8("OK/→:далее ESC:выход"), M8("OK:действия ←→:текст USER:меню"),
    M8("←→ OK:выбор ESC:текст USER:меню"), M8("Любая клавиша"), M8("Готово")
  };
  for(const char* hint : hints) {
    uint8_t pixels[classic_view::BYTES]{};
    classic_view::Canvas{&services, pixels}.hint(hint);
    if(fwrite(pixels + 7 * classic_view::WIDTH, 1, classic_view::WIDTH, stdout) != classic_view::WIDTH)
      return 1;
  }
  const char* const titles[] = {M8("МЕНЮ ИГРЫ"), M8("ИНВЕНТАРЬ")};
  for(unsigned i = 0; i < 2; ++i) {
    uint8_t pixels[classic_view::BYTES]{};
    classic_view::Canvas canvas{&services, pixels};
    canvas.box(0, 0, classic_view::WIDTH, 8);
    canvas.text(4, 0, titles[i], true, true, 150);
    canvas.text(171, 0, i ? "1/1" : "1/6", true, true, classic_view::WIDTH);
    if(fwrite(pixels, 1, classic_view::WIDTH, stdout) != classic_view::WIDTH) return 1;
  }
}
