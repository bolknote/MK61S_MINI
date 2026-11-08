#include "compute_gap_probe_app.h"
static volatile uint32_t sink;
uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->current.phase > 4096) return 0;
  const unsigned rounds = flow->current.phase ? flow->current.phase : 4096;
  const mk61_app_services* s = mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_FORMAT);
  if(!s || gap_call(s, 0xC001, 0) != 0x47415031) return 0;
  mk61_service_file app = {0};
  if(!s->call(MK61_SERVICE_FILE_ENTRY, 0, flow->current.file_id, 0, &app)) return 0;
  for(unsigned phase = 0; phase < 3; ++phase) {
    mk61_api->delay_ms(10);
    uint32_t token = phase == 1 ? mk61_app_compute_begin(s) : 0;
    gap_call(s, 0xC002, 0);
    uint32_t value = 0x31415926;
    for(unsigned round = 0; round < rounds; ++round) {
      for(unsigned i = 0; i < 1024; ++i) {
        value ^= value << 13; value ^= value >> 17; value ^= value << 5;
      }
      mk61_api->service();
      (void)mk61_api->key_poll();
      if(phase == 1 && (round & 63U) == 0) mk61_api->delay_ms(1);
    }
    sink = value;
    const char* name = phase == 0 ? "low0" : phase == 1 ? "high" : "low1";
    if(!gap_report(s, app.parent, name)) return 0;
    if(token && !mk61_app_compute_end(s, token)) return 0;
  }
  mk61_app_flow_exit(flow, MK61_APP_OK, MK61_FLOW_OK);
  return 1;
}
