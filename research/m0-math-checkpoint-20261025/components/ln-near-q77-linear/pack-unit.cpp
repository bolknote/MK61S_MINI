#include <stdint.h>
using U=uint64_t;
static unsigned clz32(uint32_t x) {
  if(!x) return 32;
  unsigned n=0;
  if(!(x&0xFFFF0000U)) {n+=16;x<<=16;}
  if(!(x&0xFF000000U)) {n+=8;x<<=8;}
  if(!(x&0xF0000000U)) {n+=4;x<<=4;}
  if(!(x&0xC0000000U)) {n+=2;x<<=2;}
  return n+unsigned(!(x&0x80000000U));
}
static unsigned clz64(U x) {return uint32_t(x>>32)?clz32(uint32_t(x>>32)):32+clz32(uint32_t(x));}

static double real(U x) {union {U u;double d;} q={x};return q.d;}
static U bits(double x) {union {double d;U u;} q={x};return q.u;}
static double ln_refine(double) {return real(UINT64_C(0x7FF800000000019A));}
__attribute__((always_inline)) inline double ln_near_round_pack77(U low,uint32_t high,U sign,
    int32_t bias60,int32_t residue,uint32_t den,bool add,bool exact_center,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t distance=tail>half?tail-half:half-tail;
  bool safe=distance>=4;
  if(!safe && distance) {
    if(exact_center) safe=true;
    else if(bool(tail>half)==add)
      safe=int32_t(den)*(int32_t(60*distance)-bias60)+60*residue>=90*int32_t(den);
    else safe=int32_t(den)*(int32_t(60*distance)+bias60)-60*residue>=90*int32_t(den);
  }
  if(!safe) return ln_refine(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-15)<<52)+q);
}
extern "C" U audit_near_pack77(U low,U configuration) {
 const uint32_t meta=uint32_t(configuration);
 return bits(ln_near_round_pack77(low,(meta>>11)&255U,U((meta>>10)&1U)<<63,
   int32_t(meta&255U)-128,int32_t(configuration>>32),8065U+((meta>>19)&255U),
   (meta>>8)&1U,(meta>>9)&1U,0.));
}
