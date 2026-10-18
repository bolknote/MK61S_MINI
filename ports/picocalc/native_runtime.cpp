#include "native_runtime.hpp"
#include <cstddef>
// Export the selected IEEE ARMv6-M EABI helpers with their original calling
// conventions, including uldivmod's four-register result, without wrappers.
#if defined(PICO_ON_DEVICE)
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
#include <cstdlib>
#include <new>
// Pico SDK's ordinary new/delete use malloc/free with exceptions disabled.
// The standard nothrow overloads otherwise pull in libstdc++ exception handlers
// and libgcc's unwinder even though this firmware cannot throw an exception.
void* operator new(std::size_t n,const std::nothrow_t&) noexcept {return std::malloc(n);}
void* operator new[](std::size_t n,const std::nothrow_t&) noexcept {return std::malloc(n);}
void operator delete(void* p,const std::nothrow_t&) noexcept {std::free(p);}
void operator delete[](void* p,const std::nothrow_t&) noexcept {std::free(p);}
#endif
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
