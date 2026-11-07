#ifndef MK61_COSMIC_CLOCK_HPP
#define MK61_COSMIC_CLOCK_HPP
#include <cstdint>
#if (defined(MK61_PICOCALC_COSMIC_CLOCK_DIAG) && MK61_PICOCALC_COSMIC_CLOCK_DIAG) || \
    (defined(MK61_PICOCALC_AUDIO_CLOCK) && MK61_PICOCALC_AUDIO_CLOCK) || \
    (defined(MK61_PICOCALC_AI_OVERCLOCK) && MK61_PICOCALC_AI_OVERCLOCK)
#define MK61_PICOCALC_MANAGED_CLOCK 1
#else
#define MK61_PICOCALC_MANAGED_CLOCK 0
#endif
namespace picocalc::cosmic_clock {
using Writer=void(*)(void*,const char*,unsigned);
#if MK61_PICOCALC_MANAGED_CLOCK
void bootstrap(); // Main's first statement, before TinyUSB/stdio/peripheral init.
void idle_check(bool(*predicate)());
bool command(const char* args,Writer writer,void* context);
uint32_t pwm_divider16();
#else
inline void bootstrap(){}
inline void idle_check(bool(*)()){}
#endif
#if defined(MK61_PICOCALC_AUDIO_CLOCK) && MK61_PICOCALC_AUDIO_CLOCK && \
    !(defined(MK61_PICOCALC_COSMIC_CLOCK_DIAG) && MK61_PICOCALC_COSMIC_CLOCK_DIAG) && \
    !(defined(MK61_PICOCALC_AI_OVERCLOCK) && MK61_PICOCALC_AI_OVERCLOCK)
#define MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK 1
bool audio_begin(); // Core 0, before installing a core-1 synth callback.
void audio_end();   // After that callback has stopped; idempotent.
#else
#define MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK 0
inline bool audio_begin(){return true;}
inline void audio_end(){}
#endif
}
#endif
