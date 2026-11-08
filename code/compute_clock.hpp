#ifndef MK61_COMPUTE_CLOCK_HPP
#define MK61_COMPUTE_CLOCK_HPP
#include "compute_clock_plan.hpp"

#if defined(MK61_NATIVE_RUNTIME) || \
    (defined(MK61_CORE_STANDALONE) && defined(PICO_ON_DEVICE) && PICO_ON_DEVICE) || \
    defined(MK61_COMPUTE_CLOCK_TEST)
#define MK61_COMPUTE_CLOCK_SUPPORTED 1
#else
#define MK61_COMPUTE_CLOCK_SUPPORTED 0
#endif

namespace compute_clock {
#if MK61_COMPUTE_CLOCK_SUPPORTED
Platform platform();
uint8_t active_profile();
bool configure(uint8_t); // Startup only, before USB/peripheral clients begin.
uint32_t frequency_hz();
void poll(uint32_t now_ms);
bool acquire();
void release();
bool pause();
void resume();
// The audio floor applies only to configured Pico compute profiles. Audio
// begins before core-1 callbacks are installed and ends after they stop.
void audio_floor(bool);
uint32_t service(uint32_t operation,uint32_t token);
struct Owner {
  Owner* previous;
  uint16_t generation,depth;
  explicit Owner(bool join_existing=false);
  ~Owner();
  Owner(const Owner&)=delete;
};
namespace backend {
bool configure(uint8_t profile);
bool set_fast(bool);
uint32_t hz();
uint32_t now_ms();
}
#else
inline Platform platform(){return Platform::F411;}
inline uint8_t active_profile(){return 0;}
inline bool configure(uint8_t profile){return profile==0;}
inline uint32_t frequency_hz(){return 0;}
inline void poll(uint32_t){}
inline bool acquire(){return false;}
inline void release(){}
inline bool pause(){return false;}
inline void resume(){}
inline void audio_floor(bool){}
inline uint32_t service(uint32_t,uint32_t){return 0;}
struct Owner {explicit Owner(bool=false){}};
#endif
struct Scope {
  bool active;
  explicit Scope(bool needed=true):active(needed && acquire()){}
  ~Scope(){if(active)release();}
  Scope(const Scope&)=delete;
};
struct Wait {
  bool active;
  explicit Wait(bool needed=true):active(needed && pause()){}
  ~Wait(){if(active)resume();}
  Wait(const Wait&)=delete;
};
}
#endif
