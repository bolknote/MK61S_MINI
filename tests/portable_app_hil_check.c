/* Physical startup check: the host recognizes the complete bitmap. A dirty
 * .data or .bss produces a different image, even if main's result is ignored. */
#include "mk61_app.h"

static unsigned initialized = 40;
static unsigned launches;
static uint8_t frame[192 * 64 / 8];

int main(void) {
  unsigned ok = initialized == 40 && launches == 0;
  for(unsigned i = 0; i < sizeof(frame); ++i)
    if(frame[i] != 0) ok = 0;
  initialized += 2;
  ++launches;
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
      MK61_APP_CAP_TIME | MK61_APP_CAP_GRAPHICS | MK61_APP_CAP_KEYBOARD)) return 2;
  if(!mk61_api->graphics_begin()) return 3;
  for(unsigned i = 0; i < sizeof(frame); ++i)
    frame[i] = ok ? (uint8_t) ((i * 17U + i / 16U) ^ 0xA5U) : 0xFF;
  if(!mk61_api->graphics_present(frame, sizeof(frame))) {
    mk61_api->graphics_end();
    return 4;
  }
  while(mk61_api->key_poll() != MK61_APP_KEY_ESC) mk61_api->delay_ms(10);
  mk61_api->graphics_end();
  return ok ? 0 : 1;
}
