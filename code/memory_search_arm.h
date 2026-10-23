/* M4 backend measured on ClassicF411; naturally aligned paired loads stop
 * safely at protection boundaries. Other targets retain the byte fallback
 * until their hardware selection is complete. */
#ifndef MK61_MEMORY_SEARCH_ARM_H
#define MK61_MEMORY_SEARCH_ARM_H
#include <stddef.h>
#ifndef MK61_MEMCHR_NAME
#define MK61_MEMCHR_NAME memchr
#endif
#ifndef MK61_MEMCHR_ATTRIBUTES
#define MK61_MEMCHR_ATTRIBUTES
#endif
#ifndef MK61_MEMCHR_WORDS
#if defined(MK61_MEMCHR_M4_FLASH) && (defined(STM32F401xC) || defined(STM32F401xE))
#define MK61_MEMCHR_WORDS 4
#else
#define MK61_MEMCHR_WORDS 16
#endif
#endif
#if defined(__GNUC__) && !defined(__clang__) && defined(__ARM_ARCH_7EM__)
#define MK61_MEMCHR_STRINGIFY_(value) #value
#define MK61_MEMCHR_STRINGIFY(value) MK61_MEMCHR_STRINGIFY_(value)
__attribute__((naked, noipa, aligned(4))) MK61_MEMCHR_ATTRIBUTES
void* MK61_MEMCHR_NAME(const void* data __attribute__((unused)),
    int value __attribute__((unused)),size_t size __attribute__((unused))) {
  __asm__(
#include "memchr_arm.inc"
  );
}
#undef MK61_MEMCHR_STRINGIFY
#undef MK61_MEMCHR_STRINGIFY_
#else
MK61_MEMCHR_ATTRIBUTES
void* MK61_MEMCHR_NAME(const void* data,int value,size_t size) {
  const unsigned char* bytes=(const unsigned char*)data;
  const unsigned char wanted=(unsigned char)value;
  for(size_t i=0;i<size;++i) if(bytes[i]==wanted) return (void*)(bytes+i);
  return NULL;
}
#endif
#endif
