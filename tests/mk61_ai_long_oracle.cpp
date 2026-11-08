#include "mk61_ai_long_bench.hpp"
#include "mk61_ai_model.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
using namespace mk61ai;
namespace {
bool read(void *p,std::uint32_t at,void *out,unsigned n) {
  auto &v=*static_cast<std::vector<std::uint8_t>*>(p);
  if(at>v.size() || n>v.size()-at) return false;
  std::memcpy(out,v.data()+at,n);return true;
}
bool write(void *p,std::uint32_t at,const void *in,unsigned n) {
  auto &v=*static_cast<std::vector<std::uint8_t>*>(p);
  if(at>v.size() || n>v.size()-at) return false;
  std::memcpy(v.data()+at,in,n);return true;
}
struct Runtime {
  Model model;
  std::vector<std::uint8_t> cache;
  std::vector<std::uint64_t> workspace;
  Runtime(std::vector<std::uint8_t> &package,bool optimized) {
    assert(model.open({&package,unsigned(package.size()),read})==ModelStatus::OK);
    auto e=model.execution();e.kernel=LinearKernel::SRAM;e.tile_rows=28;
    e.reuse_activations=optimized;e.share_kv=optimized;model.execution(e);
    cache.resize(model.cache_bytes());workspace.resize((model.workspace_bytes()+7)/8);
    assert(model.bind(workspace.data(),model.workspace_bytes(),
        {&cache,unsigned(cache.size()),read,write})==ModelStatus::OK);
  }
};
std::uint32_t kv_hash(const Runtime &r,unsigned positions) {
  const auto &c=r.model.config();const unsigned row=c.kv_heads*c.head_dim*8;
  std::uint32_t hash=2166136261U;
  for(unsigned layer=0;layer<c.layers;++layer)
    hash=long_bench::hash(hash,r.cache.data()+layer*c.context*row,positions*row);
  return hash;
}
}
int main(int argc,char **argv) {
  assert(argc==3);
  std::ifstream input(argv[1],std::ios::binary);
  std::vector<std::uint8_t> package((std::istreambuf_iterator<char>(input)),{});
  assert(package.size()>128);
  Runtime reference(package,false),candidate(package,true);
  std::uint16_t ids[64]{};unsigned count=0;
  assert(reference.model.encode(long_bench::prompt,ids,64,count)==ModelStatus::OK && count>1);
  std::vector<float> a(reference.model.config().vocab),b(a.size());
  std::uint8_t expected[long_bench::reference_bytes]{};
  long_bench::put(expected,0,long_bench::magic);
  long_bench::put(expected,4,reference.model.config().vocab);
  long_bench::put(expected,8,long_bench::cases);
  long_bench::put(expected,12,long_bench::decode);
  long_bench::put(expected,16,long_bench::word(package.data(),124));
  for(unsigned which=0;which<long_bench::cases;++which) {
    const unsigned context=long_bench::contexts[which],base=20+which*32;
    reference.model.reset();candidate.model.reset();
    long_bench::put(expected,base,context);
    std::uint16_t next=0;
    auto step=[&](std::uint16_t token,bool output) {
      std::uint16_t other=0;
      assert(reference.model.forward(token,output,next,nullptr,nullptr,Arithmetic::INT8,output?a.data():nullptr)==ModelStatus::OK);
      if(output) {
        const auto execution=candidate.model.execution();
        const unsigned position=candidate.model.position();
        auto old=execution;old.reuse_activations=false;old.share_kv=false;
        candidate.model.execution(old);
        assert(candidate.model.forward(token,output,other,nullptr,nullptr,Arithmetic::INT8,b.data())==ModelStatus::OK);
        assert(next==other && reference.cache==candidate.cache);
        assert(!std::memcmp(a.data(),b.data(),a.size()*sizeof(float)));
        candidate.model.execution(execution);assert(candidate.model.rewind(position));
      }
      assert(candidate.model.forward(token,output,other,nullptr,nullptr,Arithmetic::INT8,output?b.data():nullptr)==ModelStatus::OK);
      assert(next==other && reference.model.compute_metrics().checksum==candidate.model.compute_metrics().checksum);
      assert(reference.cache==candidate.cache);
      if(output) assert(!std::memcmp(a.data(),b.data(),a.size()*sizeof(float)));
    };
    for(unsigned pos=0;pos<context;++pos) step(long_bench::input(ids,count,pos),pos+1==context);
    long_bench::put(expected,base+4,next);
    long_bench::put(expected,base+8,candidate.model.compute_metrics().checksum);
    for(unsigned i=0;i<long_bench::decode;++i) {
      step(next,true);long_bench::put(expected,base+12+i*8,next);
      long_bench::put(expected,base+16+i*8,candidate.model.compute_metrics().checksum);
    }
    const auto hash=kv_hash(candidate,context+long_bench::decode);
    assert(hash==kv_hash(reference,context+long_bench::decode));
    long_bench::put(expected,base+28,hash);
    std::printf("Long oracle context=%u: full logits, trajectory, used KV and checksums exact PASS\n",context);
    std::fflush(stdout);
  }
  std::ofstream output(argv[2],std::ios::binary);output.write(reinterpret_cast<char*>(expected),sizeof(expected));
  assert(output.good());
}
