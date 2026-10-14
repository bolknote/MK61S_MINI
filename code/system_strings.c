// The resident needs byte-exact ISO strings, not locale, streams or allocation.
#include "native_libc.h"
#if MK61_USE_NATIVE_LIBC || defined(MK61_STRING_TEST_BUILD)
#include <stddef.h>
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("no-tree-loop-distribute-patterns")
#endif
void* memchr(const void* memory,int c,size_t n) {
  const unsigned char* p=(const unsigned char*)memory;
  const unsigned char target=(unsigned char)c;
  for(size_t i=0;i<n;++i)if(p[i]==target)return (void*)(p+i);
  return NULL;
}
size_t strlen(const char* s) {
  const char* p=s;while(*p)++p;return (size_t)(p-s);
}
size_t strnlen(const char* s,size_t n) {
  size_t i=0;while(i<n && s[i])++i;return i;
}
char* strchr(const char* s,int c) {
  const unsigned char target=(unsigned char)c;
  for(;;++s) {
    const unsigned char value=(unsigned char)*s;
    if(value==target)return (char*)s;
    if(!value)return NULL;
  }
}
int strcmp(const char* a,const char* b) {
  while((unsigned char)*a==(unsigned char)*b && *a) {++a;++b;}
  return (int)(unsigned char)*a-(int)(unsigned char)*b;
}
int strncmp(const char* a,const char* b,size_t n) {
  while(n--) {
    const unsigned char x=(unsigned char)*a++,y=(unsigned char)*b++;
    if(x!=y)return (int)x-(int)y;
    if(!x)break;
  }
  return 0;
}
char* strcpy(char* destination,const char* source) {
  char* d=destination;
  do { *d=*source++; } while(*d++);
  return destination;
}
char* strncpy(char* destination,const char* source,size_t n) {
  char* d=destination;
  while(n && *source) {*d++=*source++;--n;}
  while(n--) *d++=0;
  return destination;
}
char* strncat(char* destination,const char* source,size_t n) {
  char* d=destination;
  while(*d)++d;
  while(n-- && *source) *d++=*source++;
  *d=0;return destination;
}
#endif
