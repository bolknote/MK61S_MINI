#include "mk61_app.h"

/* Both .data and .bss deliberately participate in the repeat-launch check. */
static unsigned greeting = 40;
static unsigned launches;

int main(void) {
  if(greeting != 40 || launches != 0) return 1;
  greeting += 2;
  ++launches;
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
                            MK61_APP_CAP_TEXT_DISPLAY)) return 2;
  static const char text[] = "HELLO C APP";
  mk61_api->display_clear();
  return mk61_api->display_write_utf8(0, 0, text, sizeof(text) - 1) ? 0 : 3;
}
