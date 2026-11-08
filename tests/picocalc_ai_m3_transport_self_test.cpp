// Real AI backend + real SDK framing + resident loader. Only UART registers,
// clocks and SD are replaced; fault injection never opens a physical device.
#include "ai_m3.hpp"
#include "stm3_client.h"
#include "pico_uart1.h"
#include "stm3_runtime.h"
#include "storage.hpp"
#include "hardware/structs/clocks.h"
#include "hardware/irq.h"
#include "hardware/uart.h"
#include "mk61_ai_worker_fixture.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>
extern "C" uint32_t module_entry(uint32_t,const stm3_api*,stm3_job*);
extern "C" uint32_t module_int8_entry(uint32_t,const stm3_api*,stm3_job*);
namespace {
stm3_runtime server;
std::vector<uint8_t> package;
uint32_t ticks=0,init_calls=0,unloads=0,begins=0,ends=0;
bool audio=false,reserved=false,lose_start=false,fault_step=false;
bool integer_module=false;
irq_handler_t uart_irq=nullptr;
bool irq_enabled=false,rx_irq_enabled=false;
bool inside_uart_irq=false;
unsigned irq_priority=128;
const char*expected_path="/AI/M3LINE.S3M";
clocks_hw_t clock_regs{};
uint32_t now(void*) { return ++ticks; }
uint32_t address(void*,const void*) { return 0x20002000; }
uint32_t invoke(void*,uint32_t,uint32_t op,const stm3_api *api,stm3_job *job) {
  if(op==STM3_INIT) ++init_calls;
  if(op==STM3_STEP && fault_step) { fault_step=false;return STM3_INVALID; }
  return integer_module?module_int8_entry(op,api,job):module_entry(op,api,job);
}
}
bool irq_is_enabled(unsigned n) { assert(n==UART1_IRQ);return irq_enabled; }
irq_handler_t irq_get_exclusive_handler(unsigned n) { assert(n==UART1_IRQ);return uart_irq; }
unsigned irq_get_priority(unsigned n) { assert(n==UART1_IRQ);return irq_priority; }
void irq_set_exclusive_handler(unsigned n,irq_handler_t h) { assert(n==UART1_IRQ&&!uart_irq);uart_irq=h; }
void irq_set_priority(unsigned n,unsigned p) { assert(n==UART1_IRQ);irq_priority=p; }
void irq_set_enabled(unsigned n,bool enabled) { assert(n==UART1_IRQ);irq_enabled=enabled; }
void irq_remove_handler(unsigned n,irq_handler_t h) { assert(n==UART1_IRQ&&h==uart_irq);uart_irq=nullptr; }
bool uart_is_readable(int u) { assert(u==uart1);return server.tx_at<server.tx_bytes; }
void uart_set_irq_enables(int u,bool rx,bool tx) { assert(u==uart1&&!tx);rx_irq_enabled=rx; }
clocks_hw_t *clocks_hw=&clock_regs;
uint32_t time_us_32() {
  ++ticks;
  // The resident progresses independently while Pico runs local rows. Its
  // deferred reply is delivered by UART IRQ before the foreground join.
  if(!inside_uart_irq) {
    stm3_tick(&server);
    if(irq_enabled&&rx_irq_enabled&&uart_irq&&server.tx_at<server.tx_bytes) {
      inside_uart_irq=true;uart_irq();inside_uart_irq=false;
    }
  }
  return ticks;
}
void sleep_us(uint64_t n) { ticks+=uint32_t(n);stm3_tick(&server); }
namespace picocalc::io_worker { void invoke(void *p,void(*fn)(void*)) { fn(p); } }
namespace picocalc::m3_audio { bool transport_active() { return audio; } }
namespace picocalc::files {
bool stat(const char *path,Entry &e) {
  assert(!std::strcmp(path,expected_path));e.directory=false;e.size=package.size();return true;
}
bool read_range(const char *path,u32 at,u8 *out,unsigned n,unsigned &used) {
  assert(!std::strcmp(path,expected_path));
  if(at>package.size() || n>package.size()-at) return false;
  std::memcpy(out,package.data()+at,n);used=n;return true;
}
}
extern "C" {
int stm3_pico_uart1_begin(stm3_pico_uart1 *u,uint32_t(*clock)(void*),void *p,uint32_t peri,uint32_t baud) {
  assert(peri==48000000 && baud==2250000);++begins;
  if(reserved) return 0;
  u->micros=clock;u->context=p;u->ready=1;return 1;
}
void stm3_pico_uart1_end(stm3_pico_uart1 *u) { assert(u->ready);u->ready=0;++ends; }
uint32_t stm3_pico_uart1_micros(void *p) {
  auto *u=static_cast<stm3_pico_uart1*>(p);return u->micros(u->context);
}
int stm3_pico_uart1_send(void*,const uint8_t *p,unsigned n,uint32_t) {
  for(unsigned i=0;i<n;++i) stm3_feed(&server,p[i]);
  if(server.last_cmd==S3_UNLOAD) ++unloads;
  if((server.last_cmd==S3_START||server.last_cmd==S3_START_RESULT) && lose_start) {
    lose_start=false;uint8_t discard[272];(void)stm3_transmit(&server,discard,sizeof(discard));
  }
  if(irq_enabled&&rx_irq_enabled) { assert(uart_irq);uart_irq(); }
  return 1;
}
int stm3_pico_uart1_read(void*,uint32_t) {
  uint8_t b;stm3_tick(&server);
  return stm3_transmit(&server,&b,1)==1?b:-1;
}
}
int main(int argc,char **argv) {
  using namespace picocalc;
  assert(argc==4);std::ifstream f(argv[1],std::ios::binary);
  package.assign(std::istreambuf_iterator<char>(f),{});assert(package.size()>64);
  const stm3_backend backend{nullptr,now,address,invoke,2250000,3};stm3_init(&server,&backend);
  audio=true;assert(!ai_m3::open() && !begins && !unloads);audio=false;
  reserved=true;assert(!ai_m3::open() && begins==1 && !ends);reserved=false;
  server.state=STM3_READY;server.module_id=42;
  assert(!ai_m3::open() && server.state==STM3_READY && server.module_id==42 && !unloads);
  assert(begins==ends+1);server.state=STM3_EMPTY;
  // The resident's IDs can have advanced arbitrarily in another APP session.
  server.job_id=9001;assert(ai_m3::open() && server.state==STM3_READY);
  assert(clock_regs.sleep_en1!=0);
  float x[384],out[2];std::fill(x,x+384,1.0f);
  uint8_t weights[384],scales[48];
  mk61ai::LinearBatch b{};b.columns=384;b.rows=2;b.input=x;b.weights=weights;b.scales=scales;b.output=out;
  for(unsigned row=0;row<2;++row) for(unsigned g=0;g<12;++g) {
    for(unsigned bit=0;bit<4;++bit) for(unsigned i=0;i<4;++i)
      weights[row*192+g*16+bit*4+i]=((row?7U:9U)&(1U<<bit))?255:0;
    scales[row*24+g*2]=0;scales[row*24+g*2+1]=0x3c;
  }
  const auto before=init_calls;lose_start=true;
  assert(ai_m3::prepare(&b)==2);
  // PREPARE + three vector chunks. Lost START reply did not rerun INIT.
  assert(init_calls==before+4 && server.job_id==9005);
  assert(ai_m3::submit(&b) && ai_m3::join());
  assert(out[0]==384 && out[1]==-384);
  auto stats=ai_m3::statistics();assert(stats.jobs==1 && stats.rows==2 && !stats.error && !stats.uart_errors);
  fault_step=true;assert(ai_m3::submit(&b));
  assert(!ai_m3::join() && server.state==STM3_EMPTY);
  assert(!ai_m3::submit(&b) && !ai_m3::prepare(&b));
  ai_m3::close();assert(server.state==STM3_EMPTY && clock_regs.sleep_en1==0);
  stats=ai_m3::statistics();assert(!stats.active && stats.error && !stats.unload_failures);
  server.backend.transport_flags=7; // New opt-in completion capability, old protocol remains valid.
  assert(ai_m3::open() && ai_m3::prepare(&b)==2 && ai_m3::submit(&b) && ai_m3::join());
  ai_m3::close();assert(server.state==STM3_EMPTY && !ai_m3::statistics().unload_failures);
  // Real SDK/resident/native INT8 path: exact vector chunking, one remote row,
  // two-worker-compatible arithmetic, and no stale FP32 module assumptions.
  integer_module=true;expected_path="/AI/M3INT8.S3M";
  std::ifstream integer_file(argv[2],std::ios::binary);
  package.assign(std::istreambuf_iterator<char>(integer_file),{});assert(package.size()>64);
  assert(ai_m3::open(expected_path));
  int8_t quant[512];std::fill(quant,quant+512,3);
  float activation_scales[16];std::fill(activation_scales,activation_scales+16,1.0f);
  std::fill(weights,weights+sizeof(weights),0x99);
  for(unsigned i=0;i<sizeof(scales);i+=2){scales[i]=0;scales[i+1]=0x3c;}
  b.arithmetic=mk61ai::Arithmetic::INT8;b.grid=0;b.rows=1;b.quant=quant;b.activation_scales=activation_scales;
  for(unsigned columns:{128U,384U,512U}){
    b.columns=columns;assert(ai_m3::prepare(&b)==1);
    assert(ai_m3::submit(&b)&&ai_m3::join()&&out[0]==float(3*columns));
  }
  std::ifstream model_file(argv[3],std::ios::binary);
  std::vector<uint8_t> model_bytes(std::istreambuf_iterator<char>(model_file),{});
  auto memory=[](std::vector<uint8_t>&bytes){
    return mk61ai::Memory{&bytes,unsigned(bytes.size()),[](void*p,uint32_t at,void*out,unsigned n){
      const auto&v=*static_cast<std::vector<uint8_t>*>(p);
      if(at>v.size()||n>v.size()-at)return false;
      std::memcpy(out,v.data()+at,n);return true;
    },[](void*p,uint32_t at,const void*in,unsigned n){
      auto&v=*static_cast<std::vector<uint8_t>*>(p);
      if(at>v.size()||n>v.size()-at)return false;
      std::memcpy(v.data()+at,in,n);return true;
    }};
  };
  mk61ai::Model baseline,target;
  assert(baseline.open(memory(model_bytes))==mk61ai::ModelStatus::OK);
  assert(target.open(memory(model_bytes))==mk61ai::ModelStatus::OK);
  auto plan=target.execution();plan.tile_rows=64;target.execution(plan);
  std::vector<uint64_t> wa((baseline.workspace_bytes()+7)/8),wb((target.workspace_bytes()+7)/8);
  assert(wb.size()>wa.size());
  std::vector<uint8_t> ka(baseline.cache_bytes()),kb(ka.size());
  assert(baseline.bind(wa.data(),wa.size()*8,memory(ka))==mk61ai::ModelStatus::OK);
  assert(target.bind(wb.data(),wb.size()*8,memory(kb))==mk61ai::ModelStatus::OK);
  TestAiWorker worker;
  mk61ai::ComputeExecution execution{};execution.context=&worker;execution.kernel=mk61ai::LinearKernel::SRAM;
  execution.submit=[](void*p,void(*fn)(void*),void*arg){return static_cast<TestAiWorker*>(p)->submit(fn,arg);};
  execution.join=[](void*p){static_cast<TestAiWorker*>(p)->join();};
  baseline.execution(execution);
  execution.tile_rows=64;
  execution.remote_prepare=[](void*,const mk61ai::LinearBatch*b){return ai_m3::prepare(b);};
  execution.remote_submit=[](void*,mk61ai::LinearBatch*b){return ai_m3::submit(b);};
  execution.remote_join=[](void*){return ai_m3::join();};target.execution(execution);
  std::vector<float> la(baseline.config().vocab),lb(la.size());uint16_t ids[64];unsigned count=0;
  assert(baseline.encode("Вычисли синус 22 градусов и проверь программу.",ids,64,count)==mk61ai::ModelStatus::OK&&count>4);
  for(unsigned i=0;i<4;++i){uint16_t left=0,right=0;
    assert(baseline.forward(ids[i],true,left,nullptr,nullptr,mk61ai::Arithmetic::INT8,la.data())==mk61ai::ModelStatus::OK);
    assert(target.forward(ids[i],true,right,nullptr,nullptr,mk61ai::Arithmetic::INT8,lb.data())==mk61ai::ModelStatus::OK);
    assert(left==right&&la==lb&&ka==kb);
    const auto&metrics=target.compute_metrics();
    assert(metrics.remote_jobs&&metrics.remote_rows==metrics.remote_jobs&&!metrics.remote_fallbacks);
    assert(metrics.worker_rows&&metrics.checksum==baseline.compute_metrics().checksum);
  }
  ai_m3::close();assert(server.state==STM3_EMPTY&&!ai_m3::statistics().error&&!ai_m3::statistics().unload_failures);
  assert(begins==ends+1);
  assert(!irq_enabled&&!uart_irq&&!rx_irq_enabled&&irq_priority==128);
  std::puts("AI M3 transport HOST PASS: real SDK/resident/backend; FP32+INT8 chunking/one-row; foreign/audio/pin refusal; lost START idempotent; native fault/drain/reopen; UART/clocks released");
  std::puts("INT8 RP2 vs RP2+M3 full-model HOST PASS: four full logits, complete KV and all-row checksums exact; real worker+SDK+resident; no fallback");
}
