#include "mk61_app.h"

/* Volatile inputs keep this example's arithmetic in the compiled APP. */
static volatile double x = 3, y = 4;

int main(void) {
  const mk61_app_services* services = mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_MATH | MK61_SERVICE_CAP_FORMAT);
  if(!services) return MK61_APP_RUNTIME_ERROR;

  const double distance = services->math(MK61_SERVICE_SQRT, x*x + y*y, 0);
  char text[32];
  const int length = mk61_app_snprintf(services, text, sizeof(text),
                                      "sqrt(3^2+4^2)=%d", (int) distance);
  if(length < 0 || (uint32_t) length >= sizeof(text)) return MK61_APP_RUNTIME_ERROR;
  mk61_api->display_clear();
  mk61_api->display_write_utf8(0, 0, text, (uint32_t) length);
  mk61_api->key_wait();
  return MK61_APP_OK;
}
