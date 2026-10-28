#ifndef MK61_KEY_WAIT_BENCHMARK_HPP
#define MK61_KEY_WAIT_BENCHMARK_HPP
#include <stdint.h>
#ifndef MK61_KEY_WAIT_BENCHMARK
#define MK61_KEY_WAIT_BENCHMARK 0
#endif
#if MK61_KEY_WAIT_BENCHMARK != 0 && MK61_KEY_WAIT_BENCHMARK != 1
#error "MK61_KEY_WAIT_BENCHMARK must be 0 or 1"
#endif
namespace key_wait_benchmark {
// Diagnostic only: time from an APP's accepted key to its next blocking wait.
// Clock reads occur at those two boundaries, never in the VM dispatch loop.
struct Sample {
  uint32_t sequence=0,microseconds=0;
  int32_t key=-1;
  bool screen_begin=false,screen_end=false;
};
class Timer {
  Sample sample_{};
  uint32_t returned_at_=0;
  int32_t returned_key_=-1;
  bool armed_=false,returned_screen_=false;
public:
  void enter(uint32_t now,bool screen) {
    if(armed_) {
      ++sample_.sequence;sample_.microseconds=now-returned_at_;
      sample_.key=returned_key_;sample_.screen_begin=returned_screen_;sample_.screen_end=screen;
      armed_=false;
    }
  }
  void returned(uint32_t now,int32_t key,bool screen) {
    returned_at_=now;returned_key_=key;returned_screen_=screen;armed_=true;
  }
  Sample sample()const{return sample_;}
};
#if MK61_KEY_WAIT_BENCHMARK
void enter(uint32_t now,bool screen);
void returned(uint32_t now,int32_t key,bool screen);
Sample sample();
// Diagnostic PING arms one detach after the next accepted key, before timing.
void arm_detach();
bool take_detach();
#endif
}
#endif
