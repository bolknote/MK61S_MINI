#ifndef MK61_PICOCALC_HEAP_TRACE_HPP
#define MK61_PICOCALC_HEAP_TRACE_HPP
#include <cstdint>

namespace picocalc::heap_trace {
enum Kind : uint8_t { ALLOC=1, CALLOC, FREE, REALLOC_OLD, REALLOC_NEW, MARK };
enum Phase : uint32_t { BEFORE_RELEASE=1, IMAGE_RESERVED, ENTER_APP, EXIT_APP, IMAGE_FREED, LOAD_FAILED };
struct Event { uint32_t address, value, site, info; };
using Writer=void(*)(void*,const char*,unsigned);

// Diagnostic builds only. Logging is bounded, takes no heap and records both
// cores. Events after the fixed buffer fills are counted as dropped.
void start();
void stop();
void record(Kind kind,const void* address,uint32_t value,const void* site);
void realloc_result(const void* previous,const void* result,uint32_t size,const void* site);
void mark(Phase phase,uint32_t detail=0);
bool report(Writer write,void* context);
}
#endif
