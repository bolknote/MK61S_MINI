#ifndef MK61_PICOCALC_AI_HARNESS_HPP
#define MK61_PICOCALC_AI_HARNESS_HPP
#include "loadable_app_api.h"
#include "loadable_app_services.h"
namespace picocalc::ai {
struct Host {
  const mk61_app_api *api;
  const mk61_app_services *services;
  // One existing keyboard queue, enabled by TEXT_BEGIN. Function keys are
  // retained as physical wire codes instead of discarded by text mapping.
  int (*key)();
  const char *initial_file;
  const char *diagnostic_directory=nullptr;
  // Freeze presentation only; keyboard, USB and watchdog service stay live.
  void (*render)(bool enabled)=nullptr;
  uint32_t (*revision)()=nullptr;
};
unsigned run(const Host &host);
unsigned benchmark(const Host &host);
} // namespace picocalc::ai
#endif
