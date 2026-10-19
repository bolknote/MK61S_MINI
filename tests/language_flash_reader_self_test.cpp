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
struct LoanSource {
  uint8_t bytes[9*WRITE_BYTES];unsigned reads=0,polls=0,fail_read=0,fail_poll=0;
  ReadCache* mutate=nullptr;uint32_t revision=0;
  LoanSource(){for(unsigned i=0;i<sizeof(bytes);++i)bytes[i]=uint8_t(i*37U+i/WRITE_BYTES);}
  IO io() {return {this,[](void* raw,Space space,uint32_t at,uint8_t* out,uint16_t n) {
    auto& s=*static_cast<LoanSource*>(raw);assert(space==IMAGE && at<=sizeof(s.bytes) && n<=sizeof(s.bytes)-at);
    if(++s.reads==s.fail_read)return false;
    memcpy(out,s.bytes+at,n);return true;
  },nullptr,nullptr,[](void* raw) {
    auto& s=*static_cast<LoanSource*>(raw);
    if(s.mutate){s.mutate->put(s.revision,99,123,s.bytes);s.mutate=nullptr;}
    return ++s.polls!=s.fail_poll;
  }};}
};
static void image_loans() {
  PageCache<8192> cache;LoanSource source;
  static_assert(sizeof(cache)<=8192,"loans must fit the original cache budget");
  const uint8_t* image=nullptr;const auto io=source.io();
  assert(cache.borrow(1,42,WRITE_BYTES+13,io,image) && image);
  assert(source.reads==2 && source.polls==2 && !memcmp(image,source.bytes,2*WRITE_BYTES));
  assert(cache.statistics().loan_hits==0 && cache.statistics().loan_misses==1);
  assert(cache.statistics().lookups==0 && cache.statistics().hits==0 && cache.statistics().misses==0);
  const auto* original=image;const uint8_t* second=nullptr;
  assert(cache.borrow(1,43,1,io,second) && !second && source.reads==2);
  assert(cache.statistics().loan_hits==0 && cache.statistics().loan_misses==1);
  cache.release(original);
  assert(cache.borrow(1,42,WRITE_BYTES+13,io,image) && image==original && source.reads==2);
  assert(cache.statistics().loan_hits==1 && cache.statistics().loan_misses==1);
  uint8_t page[WRITE_BYTES],out[WRITE_BYTES];memset(page,0xB7,sizeof(page));
  assert(cache.get(1,42,1,out) && !memcmp(out,source.bytes+WRITE_BYTES,sizeof(out)));
  for(unsigned i=0;i<20;++i)cache.put(1,uint16_t(i+100),i,page);
  assert(!memcmp(image,source.bytes,2*WRITE_BYTES));
  // A C9 epoch invalidates all keys, but cannot overwrite an active RUN's
  // code/map/prompts, even if callbacks fill every other page during INPUT.
  assert(!cache.get(2,42,0,out));
  for(unsigned i=0;i<20;++i)cache.put(2,uint16_t(i+100),i,page);
  assert(!memcmp(image,source.bytes,2*WRITE_BYTES));
  cache.release(image);image=nullptr;
  assert(cache.borrow(2,42,WRITE_BYTES+13,io,image) && image && source.reads==4);
  cache.release(image);
  // Partial reads and cancelled background service never publish a loan.
  source.fail_read=source.reads+2;
  assert(!cache.borrow(3,42,WRITE_BYTES+13,io,image) && !image);
  source.fail_read=0;source.fail_poll=source.polls+1;
  assert(!cache.borrow(3,42,WRITE_BYTES+13,io,image) && !image);
  source.fail_poll=0;
  assert(cache.borrow(3,42,WRITE_BYTES+13,io,image) && image && !memcmp(image,source.bytes,2*WRITE_BYTES));
  cache.release(image);
  const auto reads=source.reads;
  for(uint32_t size:{0U,8193U,UINT32_MAX})assert(cache.borrow(3,42,size,io,image) && !image);
  assert(cache.borrow(3,UINT16_MAX,1,io,image) && !image && source.reads==reads);
  // No spare frame is required: a full-pool pin simply rejects publications.
  assert(cache.borrow(4,42,cache.payload(),io,image) && image);
  for(unsigned i=0;i<20;++i)cache.put(4,100,100+i,page);
  assert(!memcmp(image,source.bytes,cache.payload()));
  cache.put(5,100,100,page);assert(!memcmp(image,source.bytes,cache.payload()));
  cache.release(image);cache.put(5,100,100,page);
  assert(cache.get(5,100,100,out) && !memcmp(out,page,sizeof(out)));
  source.mutate=&cache;source.revision=7;
  assert(!cache.borrow(6,42,WRITE_BYTES+13,io,image) && !image);
  assert(cache.borrow(7,42,WRITE_BYTES+13,io,image) && image && !memcmp(image,source.bytes,2*WRITE_BYTES));
  cache.release(image);
  puts("Flash image loans: original budget, whole-page padding, hot reuse, pins/epoch/INPUT safety, I/O/cancel/full-pool fallbacks PASS");
}
int main() {
  page_cache();
  image_loans();
  Source s;for(unsigned i=0;i<sizeof(s.bytes);++i)s.bytes[i]=uint8_t(i*37U);
  Reader reader({&s,Source::read,sizeof(s.bytes)});
  assert(!reader.cached(4096,12) && s.reads==0);
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
  const unsigned borrowed_reads=s.reads;
  assert(reader.cached(4111,12) && !memcmp(reader.cached(4111,12),s.bytes+4111,12));
  assert(!reader.cached(4096+READ_BYTES-4,8));
  assert(!reader.cached(UINT32_MAX,16) && !reader.cached(sizeof(s.bytes)-1,2));
  assert(s.reads==borrowed_reads);
  uint8_t result[37];
  for(uint32_t at:{255U,1021U,4093U,8155U}) {
    assert(reader.read(at,result,sizeof(result)));
    assert(!memcmp(result,s.bytes+at,sizeof(result)));
  }
  // No unbounded allocation, over-read, or stale cache after invalidation.
  static_assert(sizeof(Reader)<=576,"instruction windows must remain bounded");
  assert(!reader.read(sizeof(s.bytes)-1,result,2));
  reader.invalidate();s.failed=true;
  assert(!reader.cached(4096,1));
  assert(!reader.read(4096,result,1) && !reader.good());
  assert(!reader.cached(4096,1));
  s.failed=false;assert(!reader.read(4096,result,1)); // I/O failure is sticky.
  const unsigned reads=s.reads;assert(reader.at(4096)==0 && s.reads==reads);
  Source tail;tail.visible=8159;
  for(unsigned i=0;i<sizeof(tail.bytes);++i)tail.bytes[i]=uint8_t(i*37U);
  Reader last({&tail,Source::read,tail.visible});
  assert(last.at(8158)==tail.bytes[8158] && tail.maximum<=READ_BYTES && tail.reads==1);
  assert(last.read(8155,result,4) && !memcmp(result,tail.bytes+8155,4));
  assert(last.cached(8155,4) && !memcmp(last.cached(8155,4),tail.bytes+8155,4));
  assert(!last.cached(8155,5) && !last.cached(UINT32_MAX,4));
  assert(!last.read(8155,result,5) && last.good());
  const unsigned tail_reads=tail.reads;
  assert(last.at(tail.visible)==0 && last.read(tail.visible,nullptr,0) && tail.reads==tail_reads);
  Reader absent({nullptr,nullptr,32});assert(!absent.good() && absent.at(0)==0);
  puts("Flash reader: bounded hot fetches, boundaries, invalidation and sticky I/O PASS");
}
