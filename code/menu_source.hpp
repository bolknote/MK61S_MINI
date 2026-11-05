#ifndef MK61_MENU_SOURCE_HPP
#define MK61_MENU_SOURCE_HPP
#include "loadable_app_services.h"
#include "loadable_app_api.h"
#include "mk8_codec.hpp"
#include <string.h>
namespace menu_source {
template<class Display>
bool run(mk61_service_menu_source& source, const mk61_app_api& api, Display display) {
  if(!source.title || !source.label || !source.count || source.count > 65535 ||
     source.selected >= source.count || strnlen(source.title, 128) == 128 ||
     !mk8::text_valid((const uint8_t*)source.title, strlen(source.title))) return false;
  display(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT, 0, 0, nullptr);
  const unsigned rows = api.display_rows();
  if(rows < 2) return false;
  const unsigned visible = rows - 1;
  for(;;) {
    display(MK61_SERVICE_DISPLAY_BEGIN_UPDATE, 0, 0, nullptr);
    display(MK61_SERVICE_DISPLAY_CLEAR, 0, 0, nullptr);
    display(MK61_SERVICE_DISPLAY_UI_LINE, 0, 0, (void*)source.title);
    const unsigned top = source.selected / visible * visible;
    bool valid = true;
    for(unsigned row = 0; row < visible && top + row < source.count; ++row) {
      char text[128]{};
      if(!source.label(source.context, top + row, text, sizeof(text)) ||
         strnlen(text, sizeof(text)) == sizeof(text) ||
         !mk8::text_valid((const uint8_t*)text, strlen(text))) { valid = false; break; }
      display(MK61_SERVICE_DISPLAY_UI_LINE, row + 1, top + row == source.selected ? '>' : ' ', text);
    }
    display(MK61_SERVICE_DISPLAY_END_UPDATE, 0, 0, nullptr);
    if(!valid) return false;
    const int key = api.key_wait();
    if(key == MK61_APP_KEY_OK) return true;
    if(key == MK61_APP_KEY_ESC || key == MK61_APP_KEY_USER) return false;
    if((key == MK61_APP_KEY_LEFT || key == MK61_APP_KEY_SHIFT_LEFT || key == MK61_APP_KEY_BACKWARD) && source.selected) --source.selected;
    if((key == MK61_APP_KEY_RIGHT || key == MK61_APP_KEY_SHIFT_RIGHT || key == MK61_APP_KEY_FORWARD) && source.selected + 1 < source.count) ++source.selected;
  }
}
}
#endif
