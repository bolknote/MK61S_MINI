/* Opt-in strcmp/strncmp candidates. Defaults preserve the current resident
 * and SDK baselines until a hardware campaign chooses a variant.
 *
 * Byte candidates read through the first mismatch/NUL only. Word candidates
 * use aligned 32-bit loads on both inputs: the containing word may extend up
 * to three bytes past NUL, never before the input or past strncmp's n bytes.
 * They are for ordinary SRAM/Flash strings, not volatile device registers.
 * No word is loaded until the previous word is known equal and nonzero.
 */
#ifndef MK61_STRING_COMPARE_ARM_H
#define MK61_STRING_COMPARE_ARM_H
#include <stddef.h>
#include <stdint.h>

#ifndef MK61_STRCMP_VARIANT
#define MK61_STRCMP_VARIANT 0
#endif
#ifndef MK61_STRNCMP_VARIANT
#define MK61_STRNCMP_VARIANT 0
#endif
#ifndef MK61_STRCMP_ATTRIBUTES
#define MK61_STRCMP_ATTRIBUTES
#endif
#ifndef MK61_STRNCMP_ATTRIBUTES
#define MK61_STRNCMP_ATTRIBUTES
#endif

typedef uint32_t mk61_sc_alias_word __attribute__((__may_alias__));
#define MK61_SC_INLINE static inline __attribute__((always_inline))
#define MK61_SC_STEP(offset) do { \
  const unsigned x=a[offset],y=b[offset]; \
  if(x!=y || !x)return (int)x-(int)y; \
} while(0)

MK61_SC_INLINE int mk61_sc_byte(const unsigned char* a,const unsigned char* b,
                                size_t n,int bounded) {
  for(;;) {
    if(bounded && !n--)return 0;
    const unsigned x=*a++,y=*b++;
    if(x!=y || !x)return (int)x-(int)y;
  }
}

MK61_SC_INLINE int mk61_sc_byte4(const unsigned char* a,const unsigned char* b,
                                 size_t n,int bounded) {
  while(!bounded || n>=4) {
    MK61_SC_STEP(0);MK61_SC_STEP(1);MK61_SC_STEP(2);MK61_SC_STEP(3);
    a+=4;b+=4;if(bounded)n-=4;
  }
  return mk61_sc_byte(a,b,n,bounded);
}

MK61_SC_INLINE int mk61_sc_has_zero(uint32_t word,int dsp) {
#if defined(__ARM_ARCH_7EM__)
  if(dsp) {
    uint32_t zeros;
    /* Saturated per-byte (1 - byte) is nonzero precisely for a zero byte. */
    __asm__("uqsub8 %0, %1, %2" : "=r"(zeros)
            : "r"(UINT32_C(0x01010101)),"r"(word));
    return zeros!=0;
  }
#else
  (void)dsp;
#endif
  return ((word-UINT32_C(0x01010101)) & ~word & UINT32_C(0x80808080))!=0;
}

#define MK61_SC_WORD_STEP() do { \
  const uint32_t x=*(const mk61_sc_alias_word*)a; \
  const uint32_t y=*(const mk61_sc_alias_word*)b; \
  if(x!=y || mk61_sc_has_zero(x,dsp))return mk61_sc_byte(a,b,n,bounded); \
  a+=4;b+=4;if(bounded)n-=4; \
} while(0)

MK61_SC_INLINE int mk61_sc_word(const unsigned char* a,const unsigned char* b,
                               size_t n,int bounded,int words,int dsp) {
  /* Different alignment classes cannot both reach a word boundary together. */
  if(((uintptr_t)a^(uintptr_t)b)&3)return mk61_sc_byte4(a,b,n,bounded);
  while(((uintptr_t)a&3) && (!bounded || n)) {
    MK61_SC_STEP(0);++a;++b;if(bounded)--n;
  }
  if(words==2) {
    while(!bounded || n>=8) {MK61_SC_WORD_STEP();MK61_SC_WORD_STEP();}
  }
  while(!bounded || n>=4) {MK61_SC_WORD_STEP();}
  return mk61_sc_byte(a,b,n,bounded);
}

MK61_SC_INLINE int mk61_sc_compare(const char* left,const char* right,size_t n,
                                  int bounded,int variant) {
  const unsigned char* a=(const unsigned char*)left;
  const unsigned char* b=(const unsigned char*)right;
  if(variant==1)return mk61_sc_byte(a,b,n,bounded);
  if(variant==2)return mk61_sc_byte4(a,b,n,bounded);
  return mk61_sc_word(a,b,n,bounded,(variant==4 || variant==6)?2:1,variant>=5);
}
#undef MK61_SC_WORD_STEP
#undef MK61_SC_STEP
#undef MK61_SC_INLINE

#if MK61_STRCMP_VARIANT < 0 || MK61_STRCMP_VARIANT > 6 || \
    MK61_STRNCMP_VARIANT < 0 || MK61_STRNCMP_VARIANT > 6
#error "Unknown string comparison candidate"
#endif
#if !defined(__ARM_ARCH_7EM__) && \
    (MK61_STRCMP_VARIANT > 4 || MK61_STRNCMP_VARIANT > 4)
#error "DSP string comparison candidates require Cortex-M4"
#endif
#if MK61_STRCMP_VARIANT
#define MK61_ARM_STRCMP 1
__attribute__((noipa,aligned(4))) MK61_STRCMP_ATTRIBUTES
int strcmp(const char* left,const char* right) {
  return mk61_sc_compare(left,right,0,0,MK61_STRCMP_VARIANT);
}
#endif
#if MK61_STRNCMP_VARIANT && !defined(MK61_APP_SHARED_RUNTIME)
#define MK61_ARM_STRNCMP 1
__attribute__((noipa,aligned(4))) MK61_STRNCMP_ATTRIBUTES
int strncmp(const char* left,const char* right,size_t n) {
  return mk61_sc_compare(left,right,n,1,MK61_STRNCMP_VARIANT);
}
#endif
#endif
