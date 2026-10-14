#include <cassert>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <algorithm>
#include <sys/mman.h>
#include <unistd.h>
extern "C" {
void* mk61_test_memchr(const void*,int,size_t);
size_t mk61_test_strlen(const char*);
size_t mk61_test_strnlen(const char*,size_t);
char* mk61_test_strchr(const char*,int);
int mk61_test_strcmp(const char*,const char*);
int mk61_test_strncmp(const char*,const char*,size_t);
char* mk61_test_strcpy(char*,const char*);
char* mk61_test_strncpy(char*,const char*,size_t);
char* mk61_test_strncat(char*,const char*,size_t);
}
static int sign(int n) {return (n>0)-(n<0);}
static uint32_t random_state=0xF411;
static unsigned next() {random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static void exercise(const char* a,const char* b,size_t length,size_t n) {
  assert(mk61_test_strlen(a)==length);
  assert(mk61_test_strnlen(a,n)==std::min(length,n));
  assert(sign(mk61_test_strcmp(a,b))==sign(std::strcmp(a,b)));
  assert(sign(mk61_test_strncmp(a,b,n))==sign(std::strncmp(a,b,n)));
  for(int c:{0,1,65,127,128,255,-1,0x1234}) {
    assert(mk61_test_strchr(a,c)==std::strchr(a,c));
    assert(mk61_test_memchr(a,c,length+1)==std::memchr(a,c,length+1));
  }
  char actual[1100],expected[1100];
  std::memset(actual,0xA7,sizeof(actual));std::memcpy(expected,actual,sizeof(actual));
  assert(mk61_test_strcpy(actual,a)==actual);std::strcpy(expected,a);assert(!std::memcmp(actual,expected,sizeof(actual)));
  std::memset(actual,0xA7,sizeof(actual));std::memcpy(expected,actual,sizeof(actual));
  assert(mk61_test_strncpy(actual,a,n)==actual);std::strncpy(expected,a,n);assert(!std::memcmp(actual,expected,sizeof(actual)));
  std::memset(actual,0xA7,sizeof(actual));std::memcpy(expected,actual,sizeof(actual));
  std::memcpy(actual,"ABC",4);std::memcpy(expected,"ABC",4);
  assert(mk61_test_strncat(actual,a,n)==actual);std::strncat(expected,a,n);assert(!std::memcmp(actual,expected,sizeof(actual)));
}
int main() {
  for(unsigned test=0;test<20000;++test) {
    char aa[530],bb[530];const unsigned n=next()%514,align=next()%4,other=next()%514;
    char* a=aa+align;char* b=bb+(next()%4);
    for(unsigned i=0;i<n;++i)a[i]=char(1+next()%255);a[n]=0;
    for(unsigned i=0;i<other;++i)b[i]=char(1+next()%255);b[other]=0;
    if(test%3==0)std::memcpy(b,a,n+1);
    exercise(a,b,n,next()%514);
  }
  const size_t page=size_t(sysconf(_SC_PAGESIZE));
  char* storage=(char*)mmap(nullptr,2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
  assert(storage!=MAP_FAILED && mprotect(storage+page,page,PROT_NONE)==0);
  for(size_t n=0;n<514;++n) {
    char* s=storage+page-n-1;std::memset(s,0xFE,n);s[n]=0;
    exercise(s,s,n,n+1);
    assert(mk61_test_strnlen(storage+page-n,n)==n-!!n);
    if(n)assert(mk61_test_strncmp(s,s,n)==0);
  }
  assert(munmap(storage,2*page)==0);
  std::puts("ISO strings: unsigned bytes, return values, bounds/padding/terminators, alignments and exact guard-page tails PASS");
}
