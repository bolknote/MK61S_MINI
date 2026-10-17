#include "language_flash.hpp"
#include "language_flash_cache.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using namespace language_vm::flash;
struct Source {
  uint8_t bytes[8192];
  uint32_t visible=sizeof(bytes);
  unsigned reads=0;
  uint16_t maximum=0;
  bool failed=false;
  static bool read(void* raw,uint32_t at,uint8_t* out,uint16_t n) {
    auto& s=*(Source*)raw;++s.reads;if(n>s.maximum)s.maximum=n;
    assert(at<=s.visible && n<=s.visible-at);
    if(s.failed)return false;
    memcpy(out,s.bytes+at,n);return true;
  }
};
static void page_cache() {
  PageCache<8192> cache;
  static_assert(sizeof(cache)<=8192 && decltype(cache)::pages>=3,"metadata is included in page budget");
  assert(cache.payload()==decltype(cache)::pages*WRITE_BYTES && cache.used()==0);
  assert(cache.statistics().lookups==0 && cache.statistics().invalidations==0);
  uint8_t a[WRITE_BYTES],b[WRITE_BYTES],out[WRITE_BYTES];
  memset(a,0x51,sizeof(a));memset(b,0x83,sizeof(b));
  cache.put(1,4,1,a);cache.put(1,4,65537,b);
  assert(cache.get(1,4,1,out) && !memcmp(a,out,sizeof(out)));
  assert(cache.get(1,4,65537,out) && !memcmp(b,out,sizeof(out)));
  assert(!cache.get(1,5,1,out)); // Identical page numbers in different files.
  const auto& stats=cache.statistics();
  assert(stats.lookups==3 && stats.hits==2 && stats.misses==1 &&
      stats.publications==2 && stats.evictions==0 && stats.invalidations==1);
  assert(cache.used()==2*WRITE_BYTES);
  cache.put(1,5,1,b);
  for(unsigned i=3;i<decltype(cache)::pages;++i)cache.put(1,uint16_t(10+i),0,b);
  assert(cache.get(1,4,1,out)); // Most recent frame must survive eviction.
  cache.put(1,6,2,b);
  assert(cache.get(1,4,1,out) && !cache.get(1,4,65537,out));
  assert(cache.used()==cache.payload() && stats.evictions==1);
  assert(!cache.get(2,4,1,out)); // C9 changes invalidate every previous frame.
  assert(cache.used()==0 && stats.invalidations==2);
  cache.put(2,4,1,b);
  assert(cache.get(2,4,1,out) && !memcmp(b,out,sizeof(out)));
  uint32_t stamp=0;
  assert(!cache.fingerprint(2,language_vm::Language::BASIC,stamp));
  cache.remember_fingerprint(2,language_vm::Language::BASIC,123);
  assert(cache.fingerprint(2,language_vm::Language::BASIC,stamp) && stamp==123);
  assert(!cache.fingerprint(2,language_vm::Language::FOCAL,stamp));
  assert(!cache.fingerprint(3,language_vm::Language::BASIC,stamp));
  ReadCache::Image image={};image.source=42;image.fingerprint=123;image.stamp=456;
  image.root=3;image.directory=4;image.validated.size=75000;
  cache.remember_image(3,image);
  ReadCache::Image found={};
  assert(cache.image(3,42,123,found) && found.stamp==456 && found.validated.size==75000);
  assert(!cache.image(3,42,124,found) && !cache.image(3,UINT16_MAX,123,found));
  assert(!cache.image(4,42,123,found));
  puts("Flash page cache: bounded LRU, complete 32-bit keys and C9 epoch invalidation PASS");
}
int main() {
  page_cache();
  Source s;for(unsigned i=0;i<sizeof(s.bytes);++i)s.bytes[i]=uint8_t(i*37U);
  Reader reader({&s,Source::read,sizeof(s.bytes)});
  // Ordinary instruction/operand fetches reuse bounded APP-local windows.
  // The backing resident page may be displaced by line-map/DATA lookups.
  for(unsigned pass=0;pass<2000;++pass)
    for(unsigned i=0;i<96;++i)
      assert(reader.at(4096+i)==s.bytes[4096+i]);
  uint8_t operands[12];
  for(unsigned i=0;i<1000;++i)
    assert(reader.read(4111,operands,sizeof(operands)) &&
        !memcmp(operands,s.bytes+4111,sizeof(operands)));
  fprintf(stderr,"Flash instruction window: %u backing reads for 192000 byte fetches + 1000 operand reads\n",s.reads);
  assert(s.reads<=2 && s.maximum<=READ_BYTES);
  uint8_t result[37];
  for(uint32_t at:{255U,1021U,4093U,8155U}) {
    assert(reader.read(at,result,sizeof(result)));
    assert(!memcmp(result,s.bytes+at,sizeof(result)));
  }
  // No unbounded allocation, over-read, or stale cache after invalidation.
  static_assert(sizeof(Reader)<=576,"instruction windows must remain bounded");
  assert(!reader.read(sizeof(s.bytes)-1,result,2));
  reader.invalidate();s.failed=true;
  assert(!reader.read(4096,result,1) && !reader.good());
  s.failed=false;assert(!reader.read(4096,result,1)); // I/O failure is sticky.
  const unsigned reads=s.reads;assert(reader.at(4096)==0 && s.reads==reads);
  Source tail;tail.visible=8159;
  for(unsigned i=0;i<sizeof(tail.bytes);++i)tail.bytes[i]=uint8_t(i*37U);
  Reader last({&tail,Source::read,tail.visible});
  assert(last.at(8158)==tail.bytes[8158] && tail.maximum<=READ_BYTES && tail.reads==1);
  assert(last.read(8155,result,4) && !memcmp(result,tail.bytes+8155,4));
  assert(!last.read(8155,result,5) && last.good());
  const unsigned tail_reads=tail.reads;
  assert(last.at(tail.visible)==0 && last.read(tail.visible,nullptr,0) && tail.reads==tail_reads);
  Reader absent({nullptr,nullptr,32});assert(!absent.good() && absent.at(0)==0);
  puts("Flash reader: bounded hot fetches, boundaries, invalidation and sticky I/O PASS");
}
