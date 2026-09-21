#include "mk61_app.h"

extern "C" int main(void) {
  static const char title[] = "HELLO APP";
  static const char prompt[] = "KEY TO EXIT";
  if((mk61_api->capabilities & MK61_APP_CAP_TEXT_DISPLAY) != 0) {
    mk61_api->display_clear();
    mk61_api->display_write_m8(0, 0, title, sizeof(title) - 1);
    if(mk61_api->display_rows() > 1) {
      mk61_api->display_write_m8(0, 1, prompt, sizeof(prompt) - 1);
    }
  }
  if((mk61_api->capabilities & MK61_APP_CAP_LED) != 0) {
    mk61_api->led_blink(2, 80, 80);
  }
  if((mk61_api->capabilities & MK61_APP_CAP_SOUND) != 0) {
    mk61_api->beep(880, 80, 35);
  }
  return (mk61_api->capabilities & MK61_APP_CAP_KEYBOARD) != 0
      ? mk61_api->key_wait() : 0;
}
