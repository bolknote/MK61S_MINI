#ifndef MK61_FS_SECTOR_CANDIDATES_HPP
#define MK61_FS_SECTOR_CANDIDATES_HPP
#include <stddef.h>
#include <stdint.h>
#if defined(__ARM_FEATURE_SIMD32)
#include <arm_acle.h>
#endif

// Experimental bounded RAM kernels. These do not change filesystem code.
namespace fs_sector_candidates {
using u8=uint8_t;
using u32=uint32_t;
#define SECTOR_INLINE inline __attribute__((always_inline))
SECTOR_INLINE u32 load(const u8* p) { u32 word;__builtin_memcpy(&word,p,4);return word; }
SECTOR_INLINE void store(u8* p,u32 word) { __builtin_memcpy(p,&word,4); }
SECTOR_INLINE bool equal_scalar(const u8* a,const u8* b,size_t n) {
  for(size_t i=0;i<n;++i) if(a[i]!=b[i]) return false;
  return true;
}
SECTOR_INLINE bool equal_word_early(const u8* a,const u8* b,size_t n) {
  size_t i=0;
  for(;n-i>=4;i+=4) if(load(a+i)!=load(b+i)) return false;
  return equal_scalar(a+i,b+i,n-i);
}
SECTOR_INLINE int compare_scalar(const u8* a,const u8* b,size_t n) {
  for(size_t i=0;i<n;++i) if(a[i]!=b[i]) return (int)a[i]-b[i];
  return 0;
}
SECTOR_INLINE int compare_word(const u8* a,const u8* b,size_t n) {
  size_t i=0;
  for(;n-i>=4;i+=4) {
    const u32 difference=load(a+i)^load(b+i);
    if(difference) {
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__
      const size_t lane=(size_t)__builtin_ctz(difference)/8;
      return (int)a[i+lane]-b[i+lane];
#else
      return compare_scalar(a+i,b+i,4);
#endif
    }
  }
  return compare_scalar(a+i,b+i,n-i);
}
SECTOR_INLINE bool equal_word_full(const u8* a,const u8* b,size_t n) {
  size_t i=0;u32 difference=0;
  for(;n-i>=4;i+=4) difference|=load(a+i)^load(b+i);
  for(;i<n;++i) difference|=a[i]^b[i];
  return difference==0;
}
SECTOR_INLINE u32 sad4(const u8* a,const u8* b) {
#if defined(__ARM_FEATURE_SIMD32)
  return __usad8((uint8x4_t)load(a),(uint8x4_t)load(b));
#else
  u32 sum=0;
  for(unsigned i=0;i<4;++i) {const int d=(int)a[i]-b[i];sum+=(u32)(d<0 ? -d : d);}
  return sum;
#endif
}
SECTOR_INLINE bool equal_dsp_early(const u8* a,const u8* b,size_t n) {
  size_t i=0;
  for(;n-i>=4;i+=4) if(sad4(a+i,b+i)) return false;
  return equal_scalar(a+i,b+i,n-i);
}
SECTOR_INLINE int compare_dsp(const u8* a,const u8* b,size_t n) {
  size_t i=0;
  for(;n-i>=4;i+=4) if(sad4(a+i,b+i)) return compare_scalar(a+i,b+i,4);
  return compare_scalar(a+i,b+i,n-i);
}
SECTOR_INLINE bool equal_dsp_full(const u8* a,const u8* b,size_t n) {
  // Maximum sum for one sector: 512*255=130560, well below uint32 overflow.
  // Preserve a general bounded contract if a caller passes a larger span.
  if(n>512) return equal_word_full(a,b,n);
  size_t i=0;u32 sum=0;
  for(;n-i>=4;i+=4) {
#if defined(__ARM_FEATURE_SIMD32)
    sum=__usada8((uint8x4_t)load(a+i),(uint8x4_t)load(b+i),sum);
#else
    sum+=sad4(a+i,b+i);
#endif
  }
  for(;i<n;++i) {const int d=(int)a[i]-b[i];sum+=(u32)(d<0 ? -d : d);}
  return sum==0;
}
SECTOR_INLINE void copy_scalar(u8* output,const u8* input,size_t n) {
  for(size_t i=0;i<n;++i) output[i]=input[i];
}
SECTOR_INLINE void copy_word(u8* output,const u8* input,size_t n) {
  size_t i=0;
  for(;n-i>=4;i+=4) store(output+i,load(input+i));
  copy_scalar(output+i,input+i,n-i);
}
SECTOR_INLINE void copy_word_unrolled(u8* output,const u8* input,size_t n) {
  size_t i=0;
  for(;n-i>=16;i+=16) {
    store(output+i,load(input+i));store(output+i+4,load(input+i+4));
    store(output+i+8,load(input+i+8));store(output+i+12,load(input+i+12));
  }
  copy_word(output+i,input+i,n-i);
}
#undef SECTOR_INLINE
} // namespace fs_sector_candidates
#endif
