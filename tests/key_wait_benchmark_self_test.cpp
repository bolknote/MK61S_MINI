#include "key_wait_benchmark.hpp"
#include <cassert>
#include <cstdio>
int main() {
  using namespace key_wait_benchmark;
  Timer timer;
  timer.enter(100,true);assert(!timer.sample().sequence);
  timer.returned(200,37,true);timer.enter(200+25000000,true);
  auto first=timer.sample();assert(first.sequence==1 && first.microseconds==25000000 && first.key==37);
  assert(first.screen_begin && first.screen_end);
  // The duration is recorded once at entry, not after the user's long wait.
  timer.enter(90000000,false);assert(timer.sample().microseconds==25000000);
  timer.returned(100000000,37,false);timer.enter(122000000,false);
  auto next=timer.sample();assert(next.sequence==2 && next.microseconds==22000000 && next.key==37);
  assert(!next.screen_begin && !next.screen_end);
  timer.returned(0xFFFFFF00U,0,false);timer.enter(0x100U,true);
  assert(timer.sample().sequence==3 && timer.sample().microseconds==512 && timer.sample().key==0);
  assert(!timer.sample().screen_begin && timer.sample().screen_end);
  enter(1,true);assert(!sample().sequence);
  returned(0,37,false);enter(40000000,false);assert(sample().microseconds==40000000);
  assert(!take_detach());arm_detach();assert(take_detach());assert(!take_detach());
  arm_detach();arm_detach();assert(take_detach());assert(!take_detach());
  puts("KEYWAIT benchmark: accepted-key boundary, next-wait capture, screen state and micros wrap PASS");
}
