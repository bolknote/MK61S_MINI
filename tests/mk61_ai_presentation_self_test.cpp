#include "ai_presentation.hpp"
#include "mk61_ai_model.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
using namespace mk61ai;
namespace {
bool read(void*p,std::uint32_t at,void*out,unsigned n){
  const auto&v=*static_cast<std::vector<std::uint8_t>*>(p);
  if(at>v.size()||n>v.size()-at)return false;
  std::memcpy(out,v.data()+at,n);return true;
}
bool write(void*p,std::uint32_t at,const void*in,unsigned n){
  auto&v=*static_cast<std::vector<std::uint8_t>*>(p);
  if(at>v.size()||n>v.size()-at)return false;
  std::memcpy(v.data()+at,in,n);return true;
}
struct Timer {
  std::uint32_t now=0,calls=0;bool cancel=false;
  static std::uint32_t micros(void*p){return static_cast<Timer*>(p)->now;}
  static void busy(void*p,bool on){static_cast<Timer*>(p)->now+=on?120000u:2000u;}
  static bool service(void*p){auto&t=*static_cast<Timer*>(p);t.now+=5;++t.calls;return !t.cancel;}
};
}
int main(int argc,char**argv){
  using namespace picocalc::ai;
  PresentationGate gate;
  assert(gate.needs_wait(1));gate.frozen(1);
  assert(!gate.needs_wait(1)&&gate.needs_wait(2));
  gate.color_presented();assert(!gate.needs_wait(2)&&!gate.needs_wait(3));
  gate.color_ended();assert(gate.needs_wait(3));
  PresentationCadence cadence;
  unsigned frames=0;
  for(unsigned now=0;now<20000;now+=20)
    if(cadence.due(now,1)){cadence.presented(now,1);++frames;}
  assert(frames==10); // 1000 completed ticks produce ten progress frames.
  cadence.invalidate();assert(cadence.due(19999,1));cadence.presented(19999,1);
  assert(cadence.due(19999,2)); // Phase transitions bypass the interval.
  cadence.presented(0xfffffff0u,2);
  assert(!cadence.due(1000,2)&&cadence.due(2000,2));
  assert(argc==2);std::ifstream file(argv[1],std::ios::binary);
  std::vector<std::uint8_t> package((std::istreambuf_iterator<char>(file)),{});
  Model model;assert(model.open({&package,unsigned(package.size()),read,nullptr})==ModelStatus::OK);
  std::vector<std::uint64_t> work((model.workspace_bytes()+7)/8);
  std::vector<std::uint8_t> cache(model.cache_bytes());
  assert(model.bind(work.data(),work.size()*8,{&cache,unsigned(cache.size()),read,write})==ModelStatus::OK);
  const auto token=std::uint16_t(model.config().bos);
  std::vector<float> reference(model.config().vocab),profiled(reference.size());
  ComputeExecution execution{};execution.kernel=LinearKernel::SRAM;
  model.execution(execution);std::uint16_t a=0,b=0;
  assert(model.forward(token,true,a,nullptr,nullptr,Arithmetic::INT8,reference.data())==ModelStatus::OK);
  const auto reference_cache=cache;const auto checksum=model.compute_metrics().checksum;
  model.reset();Timer timer;execution.context=&timer;execution.micros=Timer::micros;
  execution.busy=Timer::busy;model.execution(execution);
  assert(model.forward(token,true,b,Timer::service,&timer,Arithmetic::INT8,profiled.data())==ModelStatus::OK);
  const auto metrics=model.compute_metrics();
  assert(a==b&&reference==profiled&&cache==reference_cache&&checksum==metrics.checksum);
  assert(metrics.presentation_us==122000&&metrics.service_calls==timer.calls&&metrics.service_us==5*timer.calls);
  assert(metrics.layers_us+metrics.classifier_us==metrics.service_us);
  assert(timer.now==metrics.presentation_us+metrics.layers_us+metrics.classifier_us);
  model.reset();timer={};timer.cancel=true;
  assert(model.forward(token,true,b,Timer::service,&timer,Arithmetic::INT8)==ModelStatus::CANCELLED);
  assert(model.compute_metrics().presentation_us==122000&&model.position()==0);
  std::puts("AI presentation PASS: frame reuse, color DMA handoff, progress cadence/input/phase/wrap; full logits/KV/checksum exact; timers/cancel balanced");
}
