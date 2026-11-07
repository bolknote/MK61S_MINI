#define MK61_PICOCALC_AI_OVERCLOCK 1
#include "ai_clock_transition.hpp"
#include "mk61_ai_perf.hpp"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace picocalc;
struct Bus {
  std::vector<std::string> calls;
  std::string failure;
  bool reset_held=false;
  bool call(const char* name){calls.push_back(name);return failure!=name;}
  bool allowed(){return call("allowed");}
  void prepare(){call("drain");}
  void mark(unsigned,unsigned){}
  bool pio(unsigned){return call("pio");}
  void disconnect(){call("disconnect");}
  bool deinit(){return call("deinit");}
  void reset(){call("reset");reset_held=true;}
  void detach_delay(){assert(reset_held);call("detach-delay");}
  bool pll(const cosmic_clock::Plan&){assert(reset_held);return call("pll");}
  void retune_i2c(){assert(reset_held);call("i2c10k");}
  bool verify(const cosmic_clock::Plan&){assert(reset_held);return call("verify");}
  void unreset(){assert(reset_held);reset_held=false;call("unreset");}
  bool init(){assert(!reset_held);return call("init");}
  void connect(){assert(!reset_held);call("connect");}
};
int main(){
  const auto& base=*cosmic_clock::find(125);
  assert(!cosmic_clock::find(290));
  for(unsigned mhz : {250U,260U,270U,280U,288U,292U,300U}) {
    const auto* p=cosmic_clock::find(mhz);assert(p && cosmic_clock::valid(*p));
    Bus up;assert(ai_clock::change(up,base,*p));
    assert(up.calls[2]=="pio");
    Bus down;assert(ai_clock::change(down,*p,base));
    assert(down.calls[2]=="disconnect");
    for(auto fail : {"allowed","pio","deinit","pll","verify","init"}) {
      Bus bad;bad.failure=fail;assert(!ai_clock::change(bad,base,*p));
      if(bad.failure=="allowed")assert(bad.calls.size()==1);
    }
    char text[300];int n=std::snprintf(text,sizeof(text),"AIPERF2\nkernel=2\narithmetic=1\ncores=2\nfreeze=1\nfilter=0\nmhz=%u\nprefill=2\ndecode=2\nrepeat=2\nstress_ms=120000\ncontrol=1\nconstrained=0\nprefetch=1\n",mhz);
    mk61ai::PerfConfig config;assert(mk61ai::parse_perf_config(text,unsigned(n),config) && config.mhz==mhz);
  }
  std::puts("Clock sweep plans/USB reset ordering/up-down PIO/I2C retune/fault paths/strict configs PASS");
}
