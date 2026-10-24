// The resident needs byte-exact ISO strings, not locale, streams or allocation.
#include "native_libc.h"
#if MK61_USE_NATIVE_LIBC || defined(MK61_STRING_TEST_BUILD)
#include <stddef.h>
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("no-tree-loop-distribute-patterns")
#endif
#define MK61_MEMCHR_M4_FLASH 1
#include "memory_search_arm.h"
#include "memory_string_compare_arm.h"
/* The 256-KiB F401 graphics profiles keep measured DSP8 (76 bytes)
 * within their Flash reserve. LCD/OLED mini, F411 and APPs use DSP32. */
#if defined(STM32F401xC) && \
    (defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_CLASSIC_V3) || \
     defined(MK61_BOARD_40TH) || defined(MK61_DISPLAY_UC1609) || \
     defined(DISPLAY_UC1609))
#define MK61_STRLEN_M4_COMPACT 1
#endif
#include "memory_length_arm.h"
#ifndef MK61_ARM_STRLEN
size_t strlen(const char* s) {
  const char* p=s;while(*p)++p;return (size_t)(p-s);
}
#endif
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
#ifndef MK61_ARM_STRCMP
int strcmp(const char* a,const char* b) {
  while((unsigned char)*a==(unsigned char)*b && *a) {++a;++b;}
  return (int)(unsigned char)*a-(int)(unsigned char)*b;
}
#endif
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
