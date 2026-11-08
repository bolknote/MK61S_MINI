/* Finite, portable diagnostic. No clock/PLL/settings writes: COMPUTE is only
 * a workload hint. The host owns the directory containing this APP. */
#include "mk61_app.h"

#define ROUNDS 4096U
#define BATCH 1024U

static const mk61_app_services* services;
static uint32_t micros_now(void) {
  return services->call(MK61_SERVICE_MICROS, 0, 0, 0, NULL);
}
static uint32_t workload(uint32_t rounds, uint32_t* elapsed, uint32_t* maximum_gap) {
  uint32_t value = 0x31415926U;
  uint32_t before = micros_now(), previous = before;
  *maximum_gap = 0;
  for(uint32_t round = 0; round < rounds; ++round) {
    for(uint32_t i = 0; i < BATCH; ++i) {
      value ^= value << 13;
      value ^= value >> 17;
      value ^= value << 5;
    }
    mk61_api->service();
    const uint32_t now = micros_now(), gap = now - previous;
    if(gap > *maximum_gap) *maximum_gap = gap;
    previous = now;
  }
  *elapsed = previous - before;
  return value;
}
uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->current.phase > ROUNDS) return 0;
  /* A bounded shorter phase exercises the same binary in the ARM model.
   * An ordinary launch always uses the complete fixed hardware workload. */
  const uint32_t rounds = flow->current.phase ? flow->current.phase : ROUNDS;
  services = mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_UI | MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_FORMAT);
  if(!services || !mk61_app_compute_hz(services)) return 0;
  mk61_service_file app = {0};
  if(!services->call(MK61_SERVICE_FILE_ENTRY, 0, flow->current.file_id, 0, &app)) return 0;
  uint32_t elapsed[3], gaps[3], hash[3], hz[3];
  mk61_api->delay_ms(10);
  hz[0] = mk61_app_compute_hz(services);
  hash[0] = workload(rounds, elapsed, gaps);
  uint32_t token = mk61_app_compute_begin(services);
  if(!token) return 0;
  hz[1] = mk61_app_compute_hz(services);
  hash[1] = workload(rounds, elapsed + 1, gaps + 1);
  const uint32_t end_ok = mk61_app_compute_end(services, token);
  const uint32_t duplicate_rejected = !mk61_app_compute_end(services, token);
  mk61_api->delay_ms(10);
  hz[2] = mk61_app_compute_hz(services);
  hash[2] = workload(rounds, elapsed + 2, gaps + 2);
  char report[320];
  const int bytes = mk61_app_snprintf(services, report, sizeof(report),
      "COMPUTE V=1 N=%lu HASH=%lu HZ0=%lu HZ1=%lu HZ2=%lu US0=%lu US1=%lu US2=%lu GAP0=%lu GAP1=%lu GAP2=%lu END=%lu DUP=%lu MATCH=%lu\n",
      (unsigned long)(rounds * BATCH), (unsigned long)hash[0],
      (unsigned long)hz[0], (unsigned long)hz[1], (unsigned long)hz[2],
      (unsigned long)elapsed[0], (unsigned long)elapsed[1], (unsigned long)elapsed[2],
      (unsigned long)gaps[0], (unsigned long)gaps[1], (unsigned long)gaps[2],
      (unsigned long)end_ok, (unsigned long)duplicate_rejected,
      (unsigned long)(hash[0] == hash[1] && hash[1] == hash[2]));
  if(bytes <= 0 || bytes >= (int)sizeof(report)) return 0;
  mk61_service_write file = {"clock", (const uint8_t*)report, (uint32_t)bytes,
      MK61_SERVICE_INVALID_ID};
  if(!services->call(MK61_SERVICE_FILE_WRITE, app.parent,
      MK61_SERVICE_INVALID_ID, MK61_SERVICE_FILE_TEXT, &file)) return 0;
  mk61_app_flow_exit(flow, end_ok && duplicate_rejected &&
      hash[0] == hash[1] && hash[1] == hash[2] ? MK61_APP_OK : MK61_APP_RUNTIME_ERROR,
      MK61_FLOW_OK);
  return 1; /* FLOW_STEP accepted and populated flow->action. */
}
