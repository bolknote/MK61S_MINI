#include "mk61_app.h"
#include <assert.h>
static unsigned probes,begins,ends;
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
  assert(op==MK61_SERVICE_COMPUTE && c==0 && payload==NULL);
  if(a==MK61_COMPUTE_PROBE){assert(!b);++probes;return MK61_COMPUTE_MAGIC;}
  if(a==MK61_COMPUTE_BEGIN){assert(!b);++begins;return 42;}
  if(a==MK61_COMPUTE_END){assert(b==42);++ends;return 1;}
  assert(a==MK61_COMPUTE_HZ && !b);return 120000000;
}
static uint32_t unsupported(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
  (void)op;(void)a;(void)b;(void)c;(void)payload;return 0;
}
int main(void) {
  mk61_app_services services={0};services.call=call;
  assert(!mk61_app_compute_begin(NULL) && !mk61_app_compute_hz(NULL));
  assert(!mk61_app_compute_end(&services,0) && ends==0);
  const uint32_t token=mk61_app_compute_begin(&services);assert(token==42);
  assert(mk61_app_compute_hz(&services)==120000000 && mk61_app_compute_end(&services,token));
  assert(probes==2 && begins==1 && ends==1);
  services.call=unsupported;
  assert(!mk61_app_compute_begin(&services) && !mk61_app_compute_hz(&services));
  services.call=NULL;assert(!mk61_app_compute_begin(&services) && !mk61_app_compute_end(&services,42));
  return 0;
}
