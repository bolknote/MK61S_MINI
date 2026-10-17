#include "native_runtime.hpp"
#include <cstddef>
// The compiler provides IEEE ARMv6-M EABI helpers. Export their original calling
// conventions, including uldivmod's four-register result, without wrappers.
#if defined(PICO_ON_DEVICE)
namespace picocalc {
#define MK61_RUNTIME(name) extern "C" void pico_service_##name() asm(#name);
#define MK61_RUNTIME_ISO_C(name, result, ...)                                  \
  extern "C" result pico_service_##name(__VA_ARGS__) asm(#name);
#include "loadable_system_runtime.def"
#undef MK61_RUNTIME
#undef MK61_RUNTIME_ISO_C
const mk61_service_runtime_function native_runtime[MK61_RUNTIME_COUNT] = {
#define MK61_RUNTIME(name) pico_service_##name,
#define MK61_RUNTIME_ISO_C(name, result, ...)                                  \
  reinterpret_cast<mk61_service_runtime_function>(pico_service_##name),
#include "loadable_system_runtime.def"
#undef MK61_RUNTIME
#undef MK61_RUNTIME_ISO_C
};
} // namespace picocalc
#endif
