#include "native_runtime.hpp"
#include <cstddef>
// Export the selected IEEE ARMv6-M EABI helpers with their original calling
// conventions, including uldivmod's four-register result, without wrappers.
#if defined(PICO_ON_DEVICE)
#include <cstdlib>
#include <cstdint>
extern "C" { extern char __HeapLimit; void* _sbrk(int); }
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
void initialize_heap() {
    // Newlib's malloc_extend_top asks sbrk for the whole next allocation,
    // without subtracting the free top chunk. Near the fixed SRAM boundary
    // this can reject a 15 KiB viewer despite 19 KiB of contiguous space.
    // Grow the arena once, before APP/graphics allocations fragment it. Keep
    // room for malloc's header/minimum top chunk and free the block at once;
    // the linker still enforces the same heap/stack boundary.
    const auto end=(uintptr_t)_sbrk(0),limit=(uintptr_t)&__HeapLimit;
    if(end<limit && limit-end>32) {
        // The volatile pointer also keeps GCC from deleting the malloc/free
        // pair as an unused allocation.
        void* volatile reserve=std::malloc(limit-end-32);
        std::free(reserve);
    }
}
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
