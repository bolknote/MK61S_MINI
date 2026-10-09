#include "vm_cache_lzss.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <random>
#include <vector>
static void check(const std::vector<uint8_t>& raw) {
  vm_cache_lzss::Workspace workspace;
  std::vector<uint8_t> packed(raw.size()*2+32,0xA5), decoded(raw.size()+16,0xA5);
  size_t predicted=0, written=0;
  assert(vm_cache_lzss::encode(raw.data(),raw.size(),workspace,nullptr,0,predicted));
  assert(vm_cache_lzss::encode(raw.data(),raw.size(),workspace,packed.data(),packed.size(),written));
  assert(predicted==written);
  assert(vm_cache_lzss::decode(packed.data(),written,decoded.data(),raw.size(),raw.size()));
  assert(std::equal(raw.begin(),raw.end(),decoded.begin()));
  assert(std::all_of(decoded.begin()+raw.size(),decoded.end(),[](uint8_t c){return c==0xA5;}));
  if(written) {
    assert(!vm_cache_lzss::decode(packed.data(),written-1,decoded.data(),raw.size(),raw.size()));
    packed[written]=0;
    assert(!vm_cache_lzss::decode(packed.data(),written+1,decoded.data(),raw.size(),raw.size()));
    assert(!vm_cache_lzss::encode(raw.data(),raw.size(),workspace,packed.data(),written-1,predicted));
  }
}
int main() {
  std::mt19937 rng(0x61CA);
  check({});
  for(size_t size=1;size<=9728;size=size<100?size+1:size*2) {
    std::vector<uint8_t> raw(size);
    check(raw);
    for(auto& c:raw)c=uint8_t(rng()); check(raw);
    for(size_t i=0;i<size;++i)raw[i]=uint8_t(i%256); check(raw);
    for(size_t i=0;i<size;++i)raw[i]=uint8_t(i%3); check(raw);
  }
  std::vector<uint8_t> raw(9728);
  for(auto& c:raw)c=uint8_t(rng());check(raw);
  uint8_t output[32]={}, bad_offset[]={1,0,0}, bad_length[]={2,'A',0,16};
  assert(!vm_cache_lzss::decode(bad_offset,3,output,32,3));
  assert(!vm_cache_lzss::decode(bad_length,4,output,32,4));
  assert(!vm_cache_lzss::decode(bad_offset,3,output,1,3));
  vm_cache_lzss::Workspace w;size_t n=0;
  auto* dictionary=reinterpret_cast<uint8_t*>(&w);
  assert(!vm_cache_lzss::encode(output,16,w,output,32,n));
  assert(!vm_cache_lzss::encode(dictionary,sizeof(w),w,output,32,n));
  assert(!vm_cache_lzss::encode(output,16,w,dictionary,sizeof(w),n));
  assert(!vm_cache_lzss::decode(output,16,output,32,16));
  std::puts("VM cache LZSS research: roundtrip, overlap, boundaries, corruption and output guards PASS");
}
