#include "memory_word_ops.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#if defined(__unix__) || defined(__APPLE__)
#include <sys/mman.h>
#include <unistd.h>
#endif
extern "C" void* mk61_test_memcpy(void*,const void*,size_t);
extern "C" int mk61_test_memcmp(const void*,const void*,size_t);
#if defined(MK61_TEST_SDK_MEMORY)
extern "C" void* mk61_test_memmove(void*,const void*,size_t);
#endif
static int sign(int n) { return (n>0)-(n<0); }
static void compare(const unsigned char* a,const unsigned char* b,size_t n) {
  assert(sign(mk61_test_memcmp(a,b,n))==sign(std::memcmp(a,b,n)));
}
int main() {
  assert(mk61_test_memcpy(nullptr,nullptr,0)==nullptr);
  assert(mk61_test_memcmp(nullptr,nullptr,0)==0);
  uint32_t random=0x61F411;
  for(unsigned aa=0;aa<4;++aa) for(unsigned ba=0;ba<4;++ba) {
    for(size_t n=0;n<=513;++n) {
      std::vector<unsigned char> a(n+aa+!n),b(n+ba+!n),out(n+ba+!n);
      unsigned char* p=a.data()+aa;unsigned char* q=b.data()+ba;unsigned char* dest=out.data()+ba;
      for(size_t i=0;i<n;++i) {random^=random<<13;random^=random>>17;random^=random<<5;p[i]=q[i]=(unsigned char)random;}
      compare(p,q,n);
      for(size_t at=0;at<n;++at) {q[at]^=0x81;compare(p,q,n);compare(q,p,n);q[at]^=0x81;}
      assert(mk61_test_memcpy(dest,p,n)==dest);
      assert(std::memcmp(dest,p,n)==0);
    }
  }
  for(size_t n:{size_t(1024),size_t(4096),size_t(8192),size_t(32769)}) {
    std::vector<unsigned char> a(n+3),b(n+1),out(n+2);
    for(size_t i=0;i<n;++i) a[i+3]=b[i+1]=(unsigned char)(i*43);
    compare(a.data()+3,b.data()+1,n);
    for(size_t at:{size_t(0),size_t(1),size_t(3),size_t(4),size_t(15),size_t(16),n/2,n-1}) {
      b[at+1]^=0xFF;compare(a.data()+3,b.data()+1,n);compare(b.data()+1,a.data()+3,n);b[at+1]^=0xFF;
    }
    assert(mk61_test_memcpy(out.data()+2,a.data()+3,n)==out.data()+2);
    assert(std::memcmp(out.data()+2,a.data()+3,n)==0);
  }
#if defined(MK61_TEST_SDK_MEMORY)
  // SDK memmove uses memcpy for safe forward copies, including overlap.
  for(unsigned n=0;n<=65;++n) for(int shift=-16;shift<=16;++shift) {
    unsigned char actual[128],expected[128];
    for(unsigned i=0;i<128;++i) actual[i]=expected[i]=(unsigned char)(i*37);
    assert(mk61_test_memmove(actual+32+shift,actual+32,n)==actual+32+shift);
    std::memmove(expected+32+shift,expected+32,n);
    assert(std::memcmp(actual,expected,sizeof(actual))==0);
  }
#endif
#if defined(__unix__) || defined(__APPLE__)
  // Hardware-style exact page boundaries catch a load/store that reaches
  // outside the requested range, independently of allocator padding.
  const size_t page=(size_t)sysconf(_SC_PAGESIZE);
  auto guarded=[&]() {
    auto* p=(unsigned char*)mmap(nullptr,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    assert(p!=MAP_FAILED && mprotect(p+page,page,PROT_NONE)==0);return p;
  };
  unsigned char* a=guarded();unsigned char* b=guarded();
  for(size_t n=0;n<=513;++n) {
    unsigned char* p=a+page-n;unsigned char* q=b+page-n;
    for(size_t i=0;i<n;++i) p[i]=(unsigned char)(i*37);
    assert(mk61_test_memcpy(q,p,n)==q);compare(p,q,n);
    if(n) {q[n-1]^=1;compare(p,q,n);}
  }
  assert(munmap(a,page*2)==0 && munmap(b,page*2)==0);
#endif
  std::puts("System memcpy/memcmp: ISO C order/return, all alignments, short/large/exact guard-page tails PASS");
}
