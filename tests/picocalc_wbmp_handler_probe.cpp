// Invoke the installed, unmodified WBMP.APP FILE_OPEN through the public ABI.
#include "mk61_app.h"
#include <stdint.h>
#ifndef PICO_APPS_DIRECTORY
#define PICO_APPS_DIRECTORY "/MK61S-PicoCalc-0.5"
#endif

uint32_t mk61_app_flow_step(mk61_app_flow *flow) {
  if (!mk61_app_flow_compatible(flow) || flow->context_size != 64)
    return 2;
  const auto *services = mk61_app_get_services(
      mk61_api, MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_APP_FLOW);
  if (!services)
    return 3;
  if (flow->current.phase == 0) {
    mk61_service_file app{}, image{};
    if (services->call(MK61_SERVICE_FILE_RESOLVE, MK61_SERVICE_ROOT_ID,
                       MK61_SERVICE_FILE_APP,
                       (uint32_t)(uintptr_t)(PICO_APPS_DIRECTORY "/WBMP.APP"),
                       &app) ||
        services->call(
            MK61_SERVICE_FILE_RESOLVE, MK61_SERVICE_ROOT_ID,
            MK61_SERVICE_FILE_WBMP,
            (uint32_t)(uintptr_t)(PICO_APPS_DIRECTORY "/PATTERN.wbmp"), &image))
      return 4;
    auto *args = (uint32_t *)flow->context;
    args[0] = (uint32_t)(uintptr_t)mk61_api;
    args[1] = image.id;
    args[2] = args[3] = 0;
    mk61_app_flow_call(flow,
                       mk61_app_flow_direct(MK61_APP_KIND_APPLICATION, app.id,
                                            MK61_APP_FILE_OPEN, 0),
                       1);
    return 1;
  }
  if (flow->current.phase != 1 || flow->status != MK61_FLOW_OK || flow->result)
    return 5;
  static const char message[] = "PICO WBMP FILE_OPEN PASS\n";
  services->call(MK61_SERVICE_DEBUG_WRITE, sizeof(message) - 1, 0, 0,
                 (void *)message);
  mk61_app_flow_exit(flow, 0, MK61_FLOW_OK);
  return 1;
}
