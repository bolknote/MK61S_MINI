// Host-only size/codec probe. Host timings are NOT Cortex cycles or game times.
#include <chrono>
#include <fstream>
#include <iostream>
#include <vector>
#include <cstring>
#include "../tests/experimental/vm_cache_lzss.hpp"
#include "zx0.hpp"
using Clock=std::chrono::steady_clock;
struct Input {const std::vector<uint8_t>* bytes;size_t at=0;};
static bool read(void* p,uint8_t& c) {auto& r=*static_cast<Input*>(p);if(r.at==r.bytes->size())return false;c=(*r.bytes)[r.at++];return true;}
static bool write(void* p,uint8_t c) {static_cast<std::vector<uint8_t>*>(p)->push_back(c);return true;}
int main(int argc,char** argv) {
  if(argc!=2)return 2;
  std::ifstream file(argv[1],std::ios::binary);
  if(!file)return 2;
  std::vector<uint8_t> raw(std::istreambuf_iterator<char>(file),{});
  if(raw.size()<32||raw.size()>9728)return 2;
  vm_cache_lzss::Workspace work;
  std::vector<uint8_t> packed(raw.size()*2+32), decoded(raw.size());
  size_t n=0;
  if(!vm_cache_lzss::encode(raw.data(),raw.size(),work,packed.data(),packed.size(),n))return 3;
  if(!vm_cache_lzss::decode(packed.data(),n,decoded.data(),decoded.size(),raw.size())||decoded!=raw)return 3;
  const unsigned repeats=30;
  auto begin=Clock::now();
  for(unsigned i=0;i<repeats;++i)
    if(!vm_cache_lzss::encode(raw.data(),raw.size(),work,packed.data(),packed.size(),n))return 3;
  const auto encode_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin).count()/repeats;
  begin=Clock::now();
  for(unsigned i=0;i<repeats;++i)
    if(!vm_cache_lzss::decode(packed.data(),n,decoded.data(),decoded.size(),raw.size()))return 3;
  const auto decode_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin).count()/repeats;
  std::cout<<"{\"raw_bytes\":"<<raw.size()<<",\"lzss\":{\"bytes\":"<<n
           <<",\"workspace_bytes\":256,\"group_stack_bytes\":17,\"roundtrip\":true,\"host_encode_ns\":"<<encode_ns
           <<",\"host_decode_ns\":"<<decode_ns<<"},\"zx0\":[";
  bool comma=false;
  for(unsigned size:{1600U,4096U}) {
    std::vector<uint8_t> scratch(size),stream;
    zx0::Prepared plan={};bool ok=zx0::prepare(raw.data(),raw.size(),scratch.data(),scratch.size(),plan);
    if(ok) {
      zx0::Output sink={&stream,write};
      if(!zx0::emit(plan,sink))return 3;
      Input source={&stream};zx0::Input input={&source,read};uint32_t written=0;
      if(!zx0::decode(input,stream.size(),decoded.data(),decoded.size(),written)||written!=raw.size()||decoded!=raw)return 3;
    }
    if(comma)std::cout<<',';comma=true;
    std::cout<<"{\"workspace_bytes\":"<<size<<",\"available\":"<<(ok?"true":"false")
             <<",\"bytes\":"<<(ok?plan.output_size:0)<<",\"roundtrip\":"<<(ok?"true":"false")<<'}';
  }
  std::cout<<"],\"note\":\"Host codec timings only; separate staging output is required; not installed firmware.\"}\n";
}
