// Diagnostic replacement for the pinned Pico SDK's pico_malloc wrappers.
// It retains their mutex and recoverable OOM behavior, while recording the
// outermost public or newlib-reentrant allocation on each core.
#include "heap_trace.hpp"
#include "pico.h"
#include "pico/malloc.h"
#include "pico/multicore.h"
#include <cstddef>
#include <cstdint>
#include <reent.h>
#if PICO_USE_MALLOC_MUTEX
#include "pico/mutex.h"
auto_init_mutex(malloc_mutex);
#endif
#if defined(__PICOLIBC__) && __PICOLIBC__
#error "Heap tracing currently matches the Pico SDK newlib wrappers"
#endif

extern "C" {
void* __real_malloc(size_t);void* __real_calloc(size_t,size_t);
void* __real_realloc(void*,size_t);void __real_free(void*);
void* __real__malloc_r(struct _reent*,size_t);void* __real__calloc_r(struct _reent*,size_t,size_t);
void* __real__realloc_r(struct _reent*,void*,size_t);void __real__free_r(struct _reent*,void*);
}
namespace {
unsigned depth[2]{};
struct Scope {
    unsigned core;bool outer;
    Scope() : core(get_core_num()),outer(depth[core]++==0) {}
    ~Scope() { --depth[core]; }
};
#if PICO_USE_MALLOC_MUTEX
void enter() { mutex_enter_blocking(&malloc_mutex); }
void leave() { mutex_exit(&malloc_mutex); }
#else
void enter() {}
void leave() {}
#endif
uint32_t bytes(size_t n,size_t each=1) {
    return each && n>UINT32_MAX/each?UINT32_MAX:(uint32_t)(n*each);
}
}
#define SITE __builtin_return_address(0)
#if defined(PICO_ON_DEVICE)
#define HEAP_TRACE_CODE __attribute__((noinline,section(".ai_diagnostic_extension"),optimize("Os")))
#else
#define HEAP_TRACE_CODE __attribute__((noinline))
#endif
extern "C" HEAP_TRACE_CODE void* __wrap_malloc(size_t n) {
    Scope scope;enter();void* p=__real_malloc(n);
    if(scope.outer) picocalc::heap_trace::record(picocalc::heap_trace::ALLOC,p,bytes(n),SITE);
    leave();
    return p;
}
extern "C" HEAP_TRACE_CODE void* __wrap_calloc(size_t n,size_t each) {
    Scope scope;enter();void* p=__real_calloc(n,each);
    if(scope.outer) picocalc::heap_trace::record(picocalc::heap_trace::CALLOC,p,bytes(n,each),SITE);
    leave();
    return p;
}
extern "C" HEAP_TRACE_CODE void* __wrap_realloc(void* old,size_t n) {
    Scope scope;enter();void* p=__real_realloc(old,n);
    if(scope.outer) picocalc::heap_trace::realloc_result(old,p,bytes(n),SITE);
    leave();
    return p;
}
extern "C" HEAP_TRACE_CODE void __wrap_free(void* p) {
    Scope scope;enter();__real_free(p);
    if(scope.outer) picocalc::heap_trace::record(picocalc::heap_trace::FREE,p,0,SITE);
    leave();
}
extern "C" HEAP_TRACE_CODE void* __wrap__malloc_r(struct _reent* r,size_t n) {
    Scope scope;void* p=__real__malloc_r(r,n);
    if(scope.outer) picocalc::heap_trace::record(picocalc::heap_trace::ALLOC,p,bytes(n),SITE);
    return p;
}
extern "C" HEAP_TRACE_CODE void* __wrap__calloc_r(struct _reent* r,size_t n,size_t each) {
    Scope scope;void* p=__real__calloc_r(r,n,each);
    if(scope.outer) picocalc::heap_trace::record(picocalc::heap_trace::CALLOC,p,bytes(n,each),SITE);
    return p;
}
extern "C" HEAP_TRACE_CODE void* __wrap__realloc_r(struct _reent* r,void* old,size_t n) {
    Scope scope;void* p=__real__realloc_r(r,old,n);
    if(scope.outer) picocalc::heap_trace::realloc_result(old,p,bytes(n),SITE);
    return p;
}
extern "C" HEAP_TRACE_CODE void __wrap__free_r(struct _reent* r,void* p) {
    Scope scope;__real__free_r(r,p);
    if(scope.outer) picocalc::heap_trace::record(picocalc::heap_trace::FREE,p,0,SITE);
}
#undef SITE
