/* Naturally aligned word comparison shared by both opt-in M0 functions.
 * Read only a containing word after prior words are equal and nonzero.
 * For strncmp each word is additionally within the remaining count. */
#ifndef MK61_LIBC_M0_COMPARE_H
#define MK61_LIBC_M0_COMPARE_H
typedef uint32_t mk61_m0_compare_word __attribute__((__may_alias__));
#define M0_INLINE static inline __attribute__((always_inline))
M0_INLINE int mk61_m0_compare_byte(const unsigned char* a,const unsigned char* b,size_t n,int bounded) {
  for(;;) {if(bounded && !n--)return 0;unsigned x=*a++,y=*b++;if(x!=y||!x)return (int)x-(int)y;}
}
#define M0_BYTE_STEP(i) do {unsigned x=a[i],y=b[i];if(x!=y||!x)return (int)x-(int)y;}while(0)
M0_INLINE int mk61_m0_compare_words(const char* left,const char* right,size_t n,int bounded,int words) {
  const unsigned char* a=(const unsigned char*)left;const unsigned char* b=(const unsigned char*)right;
  if(((uintptr_t)a^(uintptr_t)b)&3) {
    while(!bounded||n>=4) {M0_BYTE_STEP(0);M0_BYTE_STEP(1);M0_BYTE_STEP(2);M0_BYTE_STEP(3);a+=4;b+=4;if(bounded)n-=4;}
    return mk61_m0_compare_byte(a,b,n,bounded);
  }
  while(((uintptr_t)a&3)&&(!bounded||n)) {M0_BYTE_STEP(0);++a;++b;if(bounded)--n;}
#define M0_WORD_STEP() do {uint32_t x=*(const mk61_m0_compare_word*)a,y=*(const mk61_m0_compare_word*)b; \
  if(x!=y||((x-0x01010101u)&~x&0x80808080u))return mk61_m0_compare_byte(a,b,n,bounded); \
  a+=4;b+=4;if(bounded)n-=4;}while(0)
  if(words==2)while(!bounded||n>=8) {M0_WORD_STEP();M0_WORD_STEP();}
  while(!bounded||n>=4) {M0_WORD_STEP();}
  return mk61_m0_compare_byte(a,b,n,bounded);
#undef M0_WORD_STEP
}
#undef M0_BYTE_STEP
#undef M0_INLINE
#endif
