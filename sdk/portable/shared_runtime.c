#include "mk61_app.h"

const mk61_service_runtime_function* mk61_app_runtime;

int mk61_app_bind_runtime(const mk61_app_api* api) {
  const mk61_app_services* services =
      mk61_app_get_services(api, MK61_SERVICE_CAP_RUNTIME);
  if(!services || !services->runtime) return 0;
  for(uint32_t i = 0; i < MK61_RUNTIME_COUNT; ++i)
    if(!services->runtime[i]) return 0;
  mk61_app_runtime = services->runtime;
  return 1;
}
