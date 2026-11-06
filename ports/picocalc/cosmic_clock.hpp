#ifndef MK61_COSMIC_CLOCK_HPP
#define MK61_COSMIC_CLOCK_HPP
#include <cstdint>
namespace picocalc::cosmic_clock {
using Writer=void(*)(void*,const char*,unsigned);
#if defined(MK61_PICOCALC_COSMIC_CLOCK_DIAG) && MK61_PICOCALC_COSMIC_CLOCK_DIAG
void bootstrap(); // Main's first statement, before TinyUSB/stdio/peripheral init.
void idle_check(bool(*predicate)());
bool command(const char* args,Writer writer,void* context);
uint32_t pwm_divider16();
#else
inline void bootstrap(){}
inline void idle_check(bool(*)()){}
#endif
}
#endif
