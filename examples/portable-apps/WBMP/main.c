#include "mk61_app.h"

int main(void) {
  static const char text[] = "Open a WBMP file";
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
                            MK61_APP_CAP_TEXT_DISPLAY)) return 1;
  mk61_api->display_clear();
  return mk61_api->display_write_utf8(0, 0, text, sizeof(text) - 1) ? 0 : 1;
}
