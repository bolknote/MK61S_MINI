#ifndef MK61_COMPUTE_GAP_PROBE_APP_H
#define MK61_COMPUTE_GAP_PROBE_APP_H
#include "mk61_app.h"
static uint32_t gap_call(const mk61_app_services* s, uint32_t operation, uint32_t index) {
  return s->call(MK61_SERVICE_COMPUTE, operation, index, 0, NULL);
}
static uint32_t gap_report(const mk61_app_services* s, uint32_t parent, const char* name) {
  gap_call(s, 0xC003, 0);
  char text[320];
  int used = mk61_app_snprintf(s, text, sizeof(text), "GAPS V=1");
  for(uint32_t i = 0; i < 8; ++i) {
    if(used < 0 || used >= (int)sizeof(text)) return 0;
    used += mk61_app_snprintf(s, text + used, sizeof(text) - (uint32_t)used,
        " M%u=%lu N%u=%lu", (unsigned)i, (unsigned long)gap_call(s, 0xC004, i),
        (unsigned)i, (unsigned long)gap_call(s, 0xC005, i));
  }
  if(used < 0 || used + 1 >= (int)sizeof(text)) return 0;
  text[used++] = '\n';
  mk61_service_write file = {name, (const uint8_t*)text, (uint32_t)used, MK61_SERVICE_INVALID_ID};
  return s->call(MK61_SERVICE_FILE_WRITE, parent, MK61_SERVICE_INVALID_ID,
      MK61_SERVICE_FILE_TEXT, &file);
}
#endif
