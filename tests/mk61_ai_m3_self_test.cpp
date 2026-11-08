#include "mk61_ai_model.hpp"
#include "mk61_ai_linear.hpp"
#include "mk61_ai_perf.hpp"
#include "mk61_ai_worker_fixture.hpp"
#include "stm3_module.h"
#include "m3_linear_protocol.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <random>
#include <vector>
extern "C" uint32_t module_entry(uint32_t, const stm3_api *, stm3_job *);
namespace {
using namespace mk61ai;
void put(uint8_t *p, uint32_t x) { std::memcpy(p, &x, 4); }
struct Remote {
  alignas(4) uint8_t input[512]{}, output[512]{};
  stm3_api api{STM3_ABI, sizeof(stm3_api), nullptr, nullptr};
  stm3_job job{input, 0, output, sizeof(output), 0, 0};
  LinearBatch *batch = nullptr;
  bool refuse = false, fail_join = false;
  unsigned submitted = 0, joined = 0;
  uint32_t begin(unsigned n) {
    job.input_bytes = n; job.output_bytes = job.progress = 0;
    return module_entry(STM3_INIT, &api, &job);
  }
  void header(unsigned op, unsigned columns, unsigned rows) {
    put(input, AI_M3_MAGIC); put(input+4, op); put(input+8, columns); put(input+12, rows);
  }
  unsigned prepare(const LinearBatch &b) {
    assert(!batch);
    if (b.arithmetic != Arithmetic::LUT_FLOAT32 || b.bits != 4 || b.grid != 256 ||
        !b.columns || b.columns > 512 || b.columns%32) return 0;
    header(AI_M3_PREPARE, b.columns, 0);
    assert(begin(16) == STM3_DONE && job.output_bytes == 12);
    for (unsigned at = 0; at < b.columns*4;) {
      unsigned n = std::min(512U, b.columns*4-at);
      std::memcpy(input, reinterpret_cast<const uint8_t*>(b.input)+at, n);
      assert(begin(n) == STM3_DONE); at += n;
    }
    return std::min(2U, (512U-16)/(b.columns/2+b.columns/16));
  }
  bool submit(LinearBatch &b) {
    assert(!batch);
    if (refuse) return false;
    const unsigned w=b.columns/2, s=b.columns/16;
    header(AI_M3_RUN,b.columns,b.rows);
    for (unsigned r=0;r<b.rows;++r) {
      std::memcpy(input+16+r*(w+s),b.weights+r*w,w);
      std::memcpy(input+16+r*(w+s)+w,b.scales+r*s,s);
    }
    assert(begin(16+b.rows*(w+s))==STM3_MORE);
    batch=&b; ++submitted; return true;
  }
  bool join() {
    assert(batch); auto *b=batch;
    for (unsigned g=0;g<b->columns/32;++g) {
      const auto status=module_entry(STM3_STEP,&api,&job);
      assert(status==(g+1==b->columns/32?STM3_DONE:STM3_MORE));
      assert(job.progress==g+1 && job.output_bytes==b->rows*4);
    }
    batch=nullptr; ++joined;
    if (fail_join) return false;
    std::memcpy(b->output,output,b->rows*4); return true;
  }
  void reset() { assert(module_entry(STM3_FINI,nullptr,nullptr)==STM3_DONE); }
};
using namespace mk61ai;
void tables(const float *x,unsigned columns,float *lut,float *sums) {
  for (unsigned g=0;g<columns/32;++g) {
    float sum=0;
    for (unsigned q=0;q<8;++q) {
      float *t=lut+g*128+q*16;t[0]=0;
      for (unsigned lane=0;lane<4;++lane)
        for (unsigned mask=0;mask<(1U<<lane);++mask)
          t[mask+(1U<<lane)]=t[mask]+x[g*32+q*4+lane];
      sum+=t[15];
    }
    sums[g]=sum;
  }
}
struct Runtime {
  Model model;
  const std::vector<uint8_t>& package;
  std::vector<uint64_t> workspace;
  std::vector<uint8_t> kv;
  TestAiWorker worker;
  TestAiWorker dma;
  Remote remote;
  int cancel_after=-1;
  bool pending=false;
  block_io::ReadSpan spans[16]{};
  unsigned span_count=0,begun=0,finished=0,overlapped=0;
  static bool read(void *p,uint32_t at,void *out,unsigned n) {
    auto &r=*static_cast<Runtime*>(p);
    assert(!r.pending);
    if(at>r.package.size() || n>r.package.size()-at) return false;
    std::memcpy(out,r.package.data()+at,n);return true;
  }
  static bool kv_read(void *p,uint32_t at,void *out,unsigned n) {
    auto &r=*static_cast<Runtime*>(p);
    assert(!r.pending);
    if(at>r.kv.size() || n>r.kv.size()-at)return false;
    std::memcpy(out,r.kv.data()+at,n);return true;
  }
  static bool kv_write(void *p,uint32_t at,const void *in,unsigned n) {
    auto &r=*static_cast<Runtime*>(p);
    assert(!r.pending);
    if(at>r.kv.size() || n>r.kv.size()-at)return false;
    std::memcpy(r.kv.data()+at,in,n);return true;
  }
  explicit Runtime(const std::vector<uint8_t>& p):package(p) {
    assert(model.open({this,unsigned(p.size()),read,nullptr,
      [](void *p,const block_io::ReadSpan *spans,unsigned count) {
        auto &r=*static_cast<Runtime*>(p);
        assert(!r.pending && count && count<=16);
        r.span_count=count;std::copy(spans,spans+count,r.spans);
        r.pending=true;++r.begun;
        return r.dma.submit([](void *p) {
          auto &r=*static_cast<Runtime*>(p);
          for(unsigned i=0;i<r.span_count;++i) {
            const auto &s=r.spans[i];assert(s.offset+s.bytes<=r.package.size());
            std::memcpy(s.destination,r.package.data()+s.offset,s.bytes);
          }
        },&r);
      },[](void *p) {
        auto &r=*static_cast<Runtime*>(p);
        assert(r.pending);r.dma.join();r.pending=false;++r.finished;return true;
      }})==ModelStatus::OK);
    workspace.resize((model.workspace_bytes()+7)/8);
    kv.resize(model.cache_bytes());
    assert(model.bind(workspace.data(),workspace.size()*8,
        {this,unsigned(kv.size()),kv_read,kv_write})==ModelStatus::OK);
  }
  void configure(bool third) {
    ComputeExecution e{};e.context=this;e.kernel=LinearKernel::SRAM;e.prefetch=third;
    e.submit=[](void *p,void(*fn)(void*),void *job) {
      return static_cast<Runtime*>(p)->worker.submit(fn,job);
    };
    e.join=[](void *p){static_cast<Runtime*>(p)->worker.join();};
    if(third) {
      e.remote_prepare=[](void *p,const LinearBatch *b) {
        auto &r=*static_cast<Runtime*>(p);assert(!r.pending);
        return r.remote.prepare(*b);
      };
      e.remote_submit=[](void *p,LinearBatch *b) {
        auto &r=*static_cast<Runtime*>(p);if(r.pending)++r.overlapped;
        return r.remote.submit(*b);
      };
      e.remote_join=[](void *p){return static_cast<Runtime*>(p)->remote.join();};
    }
    model.execution(e);
  }
  ModelStatus forward(uint16_t token,uint16_t &next,float *logits) {
    const auto status=model.forward(token,true,next,[](void *p) {
      auto &r=*static_cast<Runtime*>(p);
      assert(!r.pending);
      return r.cancel_after<0 || r.cancel_after-->0;
    },this,Arithmetic::LUT_FLOAT32,logits);
    assert(!pending && begun==finished && !remote.batch && remote.submitted==remote.joined && worker.submitted==worker.joined);
    return status;
  }
};
}
int main(int argc,char **argv) {
  using namespace mk61ai;
  const std::string valid="AIPERF2\nkernel=2\narithmetic=3\ncores=3\nfreeze=1\nfilter=0\nmhz=125\nprefill=1\ndecode=1\nrepeat=1\nstress_ms=0\ncontrol=1\nconstrained=0\nprefetch=1\n";
  PerfConfig cfg;
  assert(parse_perf_config(valid.data(),unsigned(valid.size()),cfg) && cfg.cores==3);
  for(const auto &bad: {std::string(valid).replace(6,1,"1"),
      std::string(valid).replace(valid.find("mhz=125"),7,"mhz=269"),
      std::string(valid).replace(valid.find("arithmetic=3"),12,"arithmetic=2"),
      std::string(valid).replace(valid.find("control=1"),9,"control=0")})
    assert(!parse_perf_config(bad.data(),unsigned(bad.size()),cfg));
  auto int8_config=valid;int8_config.replace(int8_config.find("arithmetic=3"),12,"arithmetic=1");
  assert(parse_perf_config(int8_config.data(),unsigned(int8_config.size()),cfg)&&cfg.arithmetic==1&&cfg.cores==3);
  auto archived=int8_config;archived.replace(archived.find("mhz=125"),7,"mhz=270");
  archived.replace(archived.find("control=1"),9,"control=2");
  assert(parse_perf_config(archived.data(),unsigned(archived.size()),cfg)&&cfg.mhz==270&&cfg.control==2);
  Remote remote;
  std::mt19937 rng(0x4d334149);
  unsigned rows_checked=0;
  for(unsigned columns: {32U,128U,384U,512U}) {
    float x[512],lut[2048],sums[16],a[2]{},b[2]{};
    uint8_t weights[512],scales[64];
    for(unsigned test=0;test<40;++test) {
      for(unsigned j=0;j<columns;++j) x[j]=float(int(rng()%65537)-32768)*0x1p-12f;
      if(test==0) std::fill(x,x+columns,-0.0f);
      tables(x,columns,lut,sums);
      for(auto &w:weights) w=uint8_t(rng());
      for(unsigned i=0;i<sizeof(scales);i+=2) {
        const uint16_t edges[]={0,0x8000,1,0x83ff,0x0400,0xbc00,0x3c00,0x7bff};
        const auto h=test<8?edges[test]:uint16_t((rng()%0x7800)^((rng()&1)<<15));
        std::memcpy(scales+i,&h,2);
      }
      LinearBatch batch{};batch.columns=columns;batch.input=x;batch.lookup=lut;
      batch.input_sums=sums;batch.weights=weights;batch.scales=scales;batch.output=a;
      batch.rows=std::min(2U,(512U-16)/(columns/2+columns/16));
      linear_batch_flash(&batch);assert(batch.status==ModelStatus::OK);
      assert(remote.prepare(batch)==batch.rows);batch.output=b;
      assert(remote.submit(batch) && remote.join());
      assert(!std::memcmp(a,b,batch.rows*4));rows_checked+=batch.rows;
    }
  }
  // Chunk boundaries, invalid input, NaN/Inf, cancellation and zeroed FINI.
  remote.reset();remote.header(AI_M3_PREPARE,33,0);assert(remote.begin(16)==STM3_INVALID);
  remote.header(AI_M3_PREPARE,128,0);assert(remote.begin(16)==STM3_DONE);
  assert(remote.begin(3)==STM3_INVALID);
  put(remote.input,0x7f800000);assert(remote.begin(4)==STM3_INVALID);
  assert(module_entry(STM3_CANCEL,nullptr,nullptr)==STM3_DONE);
  remote.header(AI_M3_RUN,128,1);assert(remote.begin(88)==STM3_INVALID);
  remote.reset();
  assert(argc==2);
  std::ifstream stream(argv[1],std::ios::binary);
  std::vector<uint8_t> package((std::istreambuf_iterator<char>(stream)),{});
  Runtime reference(package),candidate(package);
  reference.configure(false);candidate.configure(true);
  const auto vocab=reference.model.config().vocab;
  std::vector<float> a(vocab),b(vocab);
  uint16_t tokens[64];unsigned n=0;
  assert(reference.model.encode("Задача: вычисли синус 22 градусов.",tokens,64,n)==ModelStatus::OK && n>4);
  unsigned forwards=0;
  for(unsigned scenario=0;scenario<3;++scenario) {
    reference.model.reset();candidate.model.reset();
    candidate.remote.refuse=scenario==1;candidate.remote.fail_join=scenario==2;
    for(unsigned i=0;i<4;++i) {
      uint16_t na=0,nb=0;
      assert(reference.forward(tokens[i],na,a.data())==ModelStatus::OK);
      assert(candidate.forward(tokens[i],nb,b.data())==ModelStatus::OK);
      const auto &m=candidate.model.compute_metrics();
      assert(na==nb && !std::memcmp(a.data(),b.data(),vocab*4));
      assert(reference.kv==candidate.kv);
      assert(reference.model.compute_metrics().checksum==m.checksum && m.worker_jobs);
      if(scenario==1) assert(!m.remote_jobs && !m.remote_fallbacks);
      else assert(m.remote_jobs && m.remote_rows && (scenario==2?m.remote_jobs==m.remote_fallbacks:!m.remote_fallbacks));
      ++forwards;
    }
  }
  candidate.remote.fail_join=false;candidate.remote.refuse=false;
  candidate.model.reset();candidate.cancel_after=8;uint16_t next=0;
  assert(candidate.forward(tokens[0],next,b.data())==ModelStatus::CANCELLED);
  assert(candidate.model.position()==0 && candidate.remote.submitted==candidate.remote.joined);
  candidate.cancel_after=-1;reference.model.reset();
  assert(reference.forward(tokens[0],next,a.data())==ModelStatus::OK);
  assert(candidate.forward(tokens[0],next,b.data())==ModelStatus::OK);
  assert(!std::memcmp(a.data(),b.data(),vocab*4) && reference.kv==candidate.kv);
  assert(candidate.overlapped && candidate.begun && candidate.begun==candidate.finished);
  std::printf("M3 HOST PASS: %u kernel rows; %u full forwards; FP32 logits/KV/row hashes exact; refusal/fallback/cancel/prefetch drained\n",rows_checked,forwards+1);
}
