/* Physical wrapper for the same service probe used by the ARM tests.
 * The terminal currently ignores main's return value, so report it in pixels. */
#define main services_probe
#include "portable_app_services_probe.c"
#undef main

static uint8_t service_frame[192 * 64 / 8];

int main(void) {
  const unsigned result = (unsigned) services_probe();
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
      MK61_APP_CAP_TIME | MK61_APP_CAP_GRAPHICS | MK61_APP_CAP_KEYBOARD) ||
      !mk61_api->graphics_begin()) return MK61_APP_RUNTIME_ERROR;
  for(unsigned i = 0; i < sizeof(service_frame); ++i)
    service_frame[i] = (uint8_t) ((i * 29U + i / 7U) ^ 0x61U);
  service_frame[0] = 'A';
  service_frame[1] = 'P';
  service_frame[2] = 'I';
  service_frame[3] = (uint8_t) result;
  if(!mk61_api->graphics_present(service_frame, sizeof(service_frame))) {
    mk61_api->graphics_end();
    return MK61_APP_RUNTIME_ERROR;
  }
  while(mk61_api->key_poll() != MK61_APP_KEY_ESC) mk61_api->delay_ms(10);
  mk61_api->graphics_end();
  return (int) result;
}
