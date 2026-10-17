#ifndef MK61_PICOCALC_NATIVE_RUNTIME_HPP
#define MK61_PICOCALC_NATIVE_RUNTIME_HPP
#include "loadable_app_services.h"
namespace picocalc {
#if defined(PICO_ON_DEVICE)
extern const mk61_service_runtime_function native_runtime[MK61_RUNTIME_COUNT];
#endif
} // namespace picocalc
#endif
