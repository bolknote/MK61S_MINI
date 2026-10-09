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
extern "C" void* mk61_test_memmove(void*,const void*,size_t);
extern "C" void* mk61_test_memset(void*,int,size_t);
static int sign(int n) { return (n>0)-(n<0); }
static void compare(const unsigned char* a,const unsigned char* b,size_t n) {
  assert(sign(mk61_test_memcmp(a,b,n))==sign(std::memcmp(a,b,n)));
}
int main() {
  assert(mk61_test_memcpy(nullptr,nullptr,0)==nullptr);
  assert(mk61_test_memcmp(nullptr,nullptr,0)==0);
  assert(mk61_test_memmove(nullptr,nullptr,0)==nullptr);
  assert(mk61_test_memset(nullptr,-1,0)==nullptr);
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
  for(unsigned n=0;n<=513;++n) for(unsigned align=0;align<4;++align) for(int shift=-32;shift<=32;++shift) {
    unsigned char actual[640],expected[640];
    for(unsigned i=0;i<640;++i) actual[i]=expected[i]=(unsigned char)(i*37);
    assert(mk61_test_memmove(actual+48+align+shift,actual+48+align,n)==actual+48+align+shift);
    std::memmove(expected+48+align+shift,expected+48+align,n);
    assert(std::memcmp(actual,expected,sizeof(actual))==0);
  }
  for(unsigned n=0;n<=513;++n) for(unsigned align=0;align<4;++align) for(int value:{0,-1,0x1234}) {
    unsigned char actual[520],expected[520];
    std::memset(actual,0xA7,sizeof(actual));std::memset(expected,0xA7,sizeof(expected));
    assert(mk61_test_memset(actual+align,value,n)==actual+align);
    std::memset(expected+align,value,n);
    assert(std::memcmp(actual,expected,sizeof(actual))==0);
  }
  for(size_t n:{size_t(1024),size_t(4096),size_t(8192),size_t(32769)}) for(int shift:{-513,-17,-1,0,1,17,513}) {
    std::vector<unsigned char> actual(n+1100),expected(n+1100);
    for(size_t i=0;i<actual.size();++i)actual[i]=expected[i]=(unsigned char)(i*13);
    assert(mk61_test_memmove(actual.data()+550+shift,actual.data()+550,n)==actual.data()+550+shift);
    std::memmove(expected.data()+550+shift,expected.data()+550,n);
    assert(actual==expected);
    assert(mk61_test_memset(actual.data()+550,0x1234,n)==actual.data()+550);
    std::memset(expected.data()+550,0x1234,n);assert(actual==expected);
  }
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
    assert(mk61_test_memset(q,0x1234,n)==q);
    for(size_t i=0;i<n;++i)assert(q[i]==0x34);
    for(unsigned gap:{1U,2U,3U,4U,15U,16U,17U}) {
      unsigned char* begin=a+page-n-gap;
      for(size_t i=0;i<n+gap;++i)begin[i]=(unsigned char)(i*31);
      assert(mk61_test_memmove(p,begin,n)==p);
      for(size_t i=0;i<n;++i)assert(p[i]==(unsigned char)(i*31));
      for(size_t i=0;i<n+gap;++i)begin[i]=(unsigned char)(i*31);
      assert(mk61_test_memmove(begin,p,n)==begin);
      for(size_t i=0;i<n;++i)assert(begin[i]==(unsigned char)((i+gap)*31));
    }
  }
  assert(munmap(a,page*2)==0 && munmap(b,page*2)==0);
#endif
  std::puts("System memcpy/memcmp/memset/memmove: ISO C order/return, alignments, overlap, short/large/exact guard-page tails PASS");
}
