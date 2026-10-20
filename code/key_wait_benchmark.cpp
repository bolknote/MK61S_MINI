#include "key_wait_benchmark.hpp"
#if MK61_KEY_WAIT_BENCHMARK
namespace key_wait_benchmark {
namespace {Timer timer;bool detach_pending=false;}
void enter(uint32_t now,bool screen){timer.enter(now,screen);}
void returned(uint32_t now,int32_t key,bool screen){timer.returned(now,key,screen);}
Sample sample(){return timer.sample();}
void arm_detach(){detach_pending=true;}
bool take_detach(){const bool pending=detach_pending;detach_pending=false;return pending;}
}
#endif
