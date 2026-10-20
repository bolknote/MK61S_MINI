#include "language_vm_image_cache.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
using namespace language_vm;
namespace language_vm {
struct ImageCacheTestAccess {
  template<class C> static bool pack(C& c,typename C::Handle h,typename C::Scratch scratch) {
    auto* e=c.entry(h);return e && c.pack(*e,c.checked(scratch));
  }
};
}
struct Result {Value variables[26]={};Value array[385]={};Value stack[MAX_STACK]={};std::string output;};
bool event(void* raw,Event kind,const char* text,uint16_t length,double&) {
  if(kind==Event::TEXT)static_cast<Result*>(raw)->output.append(text,length);
  assert(kind!=Event::RESOURCE_TEXT && kind!=Event::RESOURCE_INPUT);
  return true;
}
void execute(const uint8_t* image,unsigned bytes,Result& result) {
  View view;assert(inspect(image,(uint16_t)bytes,view)==Error::NONE);
  Continuation control={};
  Bindings bindings={result.variables,result.array,385,result.stack,MAX_STACK};
  Services services={};services.context=&result;services.event=event;
  assert(run(view,control,bindings,services).error==Error::NONE);
}
int main() {
  using Cache=ImageCache<24576,16,CachePolicy::REUSE_DENSITY,true>;
  Cache cache;alignas(8) uint8_t scratch[COMPILER_WORKSPACE_SIZE];
  std::string sources[]={"10 A=.1\n20 FOR I=1 TO 25;A=A+.1;NEXT I\n",
                          "1.10 SET A=.1\n1.20 FOR I=1,25;SET A=A+.1\n"};
  for(unsigned n=0;n<20;++n) {
    sources[0]+=std::to_string(100+n*10)+" A=A+.1\n";
    sources[1]+="2."+std::to_string(10+n)+" SET A=A+.1\n";
  }
  sources[0]+="1000 PRINT 'BASIC PACKED';A\n1010 END\n";
  sources[1]+="3.10 PRINT \"FOCAL PACKED\",A\n3.20 EXIT\n";
  for(unsigned l=0;l<2;++l) {
    const auto lang=l?Language::FOCAL:Language::BASIC;
    std::vector<uint8_t> raw(MAX_MODULE);
    const ResourceSource resources={42,1,ResourceMode::EMBEDDED};
    const auto compiled=compile(lang,sources[l].data(),sources[l].size(),raw.data(),raw.size(),true,&resources);
    assert(compiled.error==Error::NONE);raw.resize(compiled.size);
    View v;assert(inspect(raw.data(),raw.size(),v)==Error::NONE);
    Result baseline;execute(raw.data(),raw.size(),baseline);
    const Cache::Key key={1,42,lang,0};
    auto h=cache.reserve(key,raw.size());assert(h);
    memcpy(cache.building(h),raw.data(),raw.size());
    ValidatedImage cert={VALIDATED_MAGIC,v.size,v.code,v.source_size,v.end,(uint8_t)v.lines,v.stack,raw[7],lang,false};
    assert(cache.publish(h,cert) && cache.release(h));
    assert(ImageCacheTestAccess::pack(cache,h,{scratch,sizeof(scratch)}));
    for(unsigned repeat=0;repeat<4;++repeat) {
      h=cache.find(key,{scratch,sizeof(scratch)});assert(h);
      assert(!memcmp(cache.image(h),raw.data(),raw.size()));
      Result restored;execute(cache.image(h),raw.size(),restored);
      assert(restored.output==baseline.output && !memcmp(restored.variables,baseline.variables,sizeof(baseline.variables)));
      assert(!memcmp(restored.array,baseline.array,sizeof(baseline.array)));
      assert(cache.release(h));
      assert(ImageCacheTestAccess::pack(cache,h,{scratch,sizeof(scratch)}));
    }
  }
  assert(cache.packing_statistics().thaws==8);
  puts("VM mixed execution: BASIC/FOCAL decimal arithmetic, loops, embedded resources and repeated packed roundtrips exact PASS");
}
