// Execute the real native cache/codec over verified, actual bytecode images.
// Host times are not a Cortex/device performance benchmark.
#include "language_vm_image_cache.hpp"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <map>
#include <vector>
#include <cstring>
using namespace language_vm;
struct Module {Language language;std::vector<uint8_t> bytes;ValidatedImage certificate;};
template<bool Mixed>
int replay(const std::map<unsigned,Module>& modules,const std::vector<unsigned>& order,
           unsigned repeats,unsigned start,unsigned end) {
  using Cache=ImageCache<24576,16,CachePolicy::REUSE_DENSITY,Mixed>;
  struct GuardedCache {uint64_t before=0x61CAFE;Cache value;uint64_t after=0xCAFEB0;};
  GuardedCache guarded;auto& cache=guarded.value;
  struct Loan {uint64_t before=0x123456;alignas(8) uint8_t prefix[COMPILER_WORKSPACE_SIZE];
    uint8_t values[VALUES_SIZE];uint64_t after=0x654321;} loan;
  memset(loan.values,0xB7,sizeof(loan.values));
  std::cout<<"{\"mixed\":"<<(Mixed?"true":"false")<<",\"budget\":24576,\"object_bytes\":"<<sizeof(Cache)
           <<",\"payload\":"<<Cache::PAYLOAD_CAPACITY<<",\"metadata\":"<<Cache::metadata_bytes()<<",\"passes\":[";
  for(unsigned pass=0;pass<repeats;++pass) {
    typename Cache::Statistics before={};typename Cache::PackingStatistics packed_before={};
    unsigned failures=0;std::map<unsigned,unsigned> misses;
    for(unsigned n=0;n<order.size();++n) {
      if(n==start) {before=cache.statistics();packed_before=cache.packing_statistics();}
      const unsigned id=order[n];const auto& m=modules.at(id);
      const typename Cache::Key key={1,(uint16_t)id,m.language,0};
      auto h=cache.find(key,{loan.prefix,sizeof(loan.prefix)});
      if(!h) {
        if(n>=start && n<end)++misses[id];
        h=cache.reserve(key,(uint16_t)m.bytes.size());
        if(!h) {if(n>=start && n<end)++failures;continue;}
        memcpy(cache.building(h),m.bytes.data(),m.bytes.size());
        if(!cache.publish(h,m.certificate))return 3;
      }
      if(!cache.image(h) || !cache.certificate(h) ||
          memcmp(cache.image(h),m.bytes.data(),m.bytes.size()) || !cache.release(h))return 4;
      for(auto b:loan.values)if(b!=0xB7)return 5;
      if(guarded.before!=0x61CAFE || guarded.after!=0xCAFEB0 || loan.before!=0x123456 || loan.after!=0x654321)return 6;
      if(n+1==end) {
        const auto after=cache.statistics();const auto p=cache.packing_statistics();
        if(pass)std::cout<<',';
        std::cout<<"{\"hits\":"<<after.hits-before.hits<<",\"misses\":"<<after.misses-before.misses
                 <<",\"evictions\":"<<after.evictions-before.evictions<<",\"fallback\":"<<failures
                 <<",\"used\":"<<cache.used()<<",\"packs\":"<<p.packs-packed_before.packs
                 <<",\"thaws\":"<<p.thaws-packed_before.thaws<<",\"packed\":"<<p.packed<<",\"miss_modules\":{";
        bool comma=false;
        for(const auto& item:misses) {if(comma)std::cout<<',';comma=true;std::cout<<'"'<<item.first<<"\":"<<item.second;}
        std::cout<<"}}";
      }
    }
  }
  std::cout<<"]}";
  return 0;
}
int main() {
  unsigned repeats,start,end,count,requests;
  if(!(std::cin>>repeats>>start>>end>>count>>requests) || repeats<1 || repeats>10 ||
      count>1024 || requests>1000000 || start>=end || end>requests)return 2;
  std::map<unsigned,Module> modules;
  for(unsigned i=0;i<count;++i) {
    unsigned id,language;std::string path;
    if(!(std::cin>>id>>language>>std::quoted(path)) || id>=0xFFFF || language<1 || language>2 || modules.count(id))return 2;
    std::ifstream file(path,std::ios::binary);if(!file)return 2;
    Module m={(Language)language,{std::istreambuf_iterator<char>(file),{}},{}};
    View v;
    if(m.bytes.size()>0xFFFF || inspect(m.bytes.data(),(uint16_t)m.bytes.size(),v)!=Error::NONE || v.language!=m.language)return 3;
    m.certificate={VALIDATED_MAGIC,v.size,v.code,v.source_size,v.end,(uint8_t)v.lines,v.stack,m.bytes[7],v.language};
    modules[id]=std::move(m);
  }
  std::vector<unsigned> order;
  for(unsigned i=0;i<requests;++i) {unsigned id;if(!(std::cin>>id) || !modules.count(id))return 2;order.push_back(id);}
  std::cout<<"{\"status\":\"PASS\",\"variants\":[";
  int status=replay<false>(modules,order,repeats,start,end);if(status)return status;
  std::cout<<',';status=replay<true>(modules,order,repeats,start,end);if(status)return status;
  std::cout<<"]}\n";
}
