#include "api.h"
#include "integer.inc"
#include "native_eabi_m0_log_table.inc"
__attribute__((always_inline)) inline U math62_product(U a,U b) {
  if(!a || !b) return 0;
  const U cross=wide32(uint32_t(a),uint32_t(b>>32))+wide32(uint32_t(a>>32),uint32_t(b));
  const U high=wide32(uint32_t(a>>32),uint32_t(b>>32))+(cross>>32);
  return ((high<<2)|(uint32_t(cross)>>30))+2+((uint32_t(cross)>>29)&1);
}
__attribute__((always_inline)) inline U math62_right(U a,unsigned n) {
  if(!n) return a;
  if(n>=64) return n==64 && a>(U(1)<<63);
  const U half=U(1)<<(n-1),tail=a&((half<<1)-1),q=a>>n;
  return q+(tail>half || (tail==half && (q&1)));
}
__attribute__((always_inline)) inline U math62_third(U a) {
  const uint32_t hi=uint32_t(a>>32),lo=uint32_t(a);
  const uint32_t qh=uint32_t(wide32(hi,0xAAAAAAABU)>>33);
  const uint32_t ql=uint32_t(wide32(lo,0xAAAAAAABU)>>33);
  const uint32_t rh=hi-3*qh,tail=rh+lo-3*ql,carry=tail>=3;
  const U q=(U(qh)<<32)|uint32_t(ql+rh*0x55555555U+carry);
  return q+U(tail-3*carry>=2);
}
__attribute__((always_inline)) inline double math62_pack(U q,int e,U sign) {
  if(q<(U(1)<<62)) {q<<=1;--e;}
  const unsigned high=unsigned(q>>63),shift=10+high;
  const uint32_t lo=uint32_t(q),hi=uint32_t(q>>32),half=1U<<(shift-1),tail=lo&((half<<1)-1);
  U m=(U(hi>>shift)<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  m+=tail>half || (tail==half && (m&1));
  return real(sign+(U(e+1021+int(high))<<52)+m);
}
__attribute__((always_inline)) inline double math62_log_near_one(U b) {
  // Called only for |x-1| <= 2^-14; the first omitted relative term
  // f^4/5 is below 13 Q62 units, with nine guard bits at the output.
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  if(!a) return 0.0;
  const unsigned leading=clz64(a);
  const U q=a<<(leading-1),one=U(1)<<62,half=a>>1;
  if(a<=(U(1)<<35)) {
    const U factor=one+(negative?half:U(0)-half);
    return math62_pack(math62_product(q,factor),2-int(leading),negative?D::Sign:0);
  }
  // a <= 2^56. Two products approximate a*a/2^62 within 1.001
  // units; the omitted low square contributes less than 2^-12.
  const uint32_t t=uint32_t(a>>25);
  const U z=(wide32(t,t)>>12)+(wide32(t,uint32_t(a)&0x1FFFFFFU)>>36)+1;
  if(a<=(U(1)<<42)) {
    const U factor=one+(negative?half:U(0)-half)+math62_third(z);
    return math62_pack(math62_product(q,factor),2-int(leading),negative?D::Sign:0);
  }
  const U cube=math62_product(a,z);
  const U quarter=(cube+2)>>2;
  const U factor=(U(1)<<62)+(negative?half:U(0)-half)+math62_third(z)+
    (negative?quarter:U(0)-quarter);
  return math62_pack(math62_product(q,factor),2-int(leading),negative?D::Sign:0);
}
__attribute__((always_inline)) inline int64_t math62_log_correction(int64_t h) {
  if(!h) return 0;
  const bool negative=h<0;const U a=negative?U(0)-U(h):U(h);
  const uint32_t t=uint32_t(a>>22);
  const U z=(wide32(t,t)>>18)+(wide32(t,uint32_t(a)&0x3FFFFFU)>>39)+1;
  const U cube=math62_product(a,z);
  const uint32_t fifth=uint32_t(wide32(uint32_t(z>>26),0xCCCCCCCDU)>>34);
  const uint32_t sixth=uint32_t(wide32(uint32_t(cube>>26),0xAAAAAAABU)>>34);
  const uint32_t quarter=uint32_t(a>>28);
  const uint32_t c=0x55555555U+(negative?quarter:0U-quarter)+fifth+(negative?sixth:0U-sixth);
  const U low=wide32(uint32_t(cube),c);
  const U high=wide32(uint32_t(cube>>32),c)+(low>>32)+cube+(cube<<2);
  const U q=high>>4;const unsigned tail=unsigned(high)&15;
  const U third=q+U(tail>8 || (tail==8 && (uint32_t(low)||(q&1))));
  const int64_t second=int64_t((z+1)>>1);
  return negative?-int64_t(a)-second-int64_t(third):int64_t(a)-second+int64_t(third);
}
__attribute__((always_inline)) inline double math62_pack96(U low,uint32_t high,U sign) {
  unsigned shift;int bias;
  if(high) {
    const unsigned width=32-clz32(high);
    shift=width+11;bias=int(width)+1023;
  } else {
    const unsigned width=64-clz64(low);
    shift=width-53;bias=int(width)+959;
  }
  // Here 3 <= shift <= 21; only the low 32-bit word contains rounding bits.
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32),half=1U<<(shift-1),tail=lo&((half<<1)-1);
  U q=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  q+=tail>half || (tail==half && (q&1));
  return real(sign+(U(bias)<<52)+q);
}
__attribute__((always_inline)) inline double math62_log_interval(U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return math62_log_near_one(b);
  if(negative && n==128) --n;
  const unsigned index=negative?128-n:128+n;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  if(!delta) return real(bits(math62_pack96(log_near_table[index-1][1],0,negative?D::Sign:0))-(U(8)<<52));
  const Product product=multiply(delta,log_near_table[index-1][0]);
  const U h0=(product.high<<10)|(product.low>>54),tail=product.low&((U(1)<<54)-1),half=U(1)<<53;
  const U h=h0+U(tail>half || (tail==half && (h0&1)));
  // |h| <= 1/8065. In Q70 the square needs two wide products;
  // the cube and fourth power need one each. Total accumulated error
  // stays below four Q70 units, including certified table rounding.
  const uint32_t t=uint32_t(h>>26);
  const U z=(wide32(t,t)>>18)+(wide32(t,uint32_t(h)&0x3FFFFFFU)>>43)+1;
  const uint32_t hr=uint32_t((h+(1U<<25))>>26),zr=uint32_t((z+(1U<<12))>>13);
  const uint32_t cube=uint32_t((wide32(hr,zr)+(U(1)<<30))>>31);
  const uint32_t q=uint32_t(wide32(cube,0xAAAAAAABU)>>33);
  const U third=q+U(cube-3*q>=2);
  const U fourth=(wide32(zr,zr)+(U(1)<<43))>>44;
  const U even=((z+1)>>1)+((fourth+2)>>2),odd=h+third;
  const U correction=subtract?odd+even:odd-even;
  U low=log_near_table[index-1][1];uint32_t high=0;
  if(subtract==negative) {const U before=low;low+=correction;high=low<before;}
  else low-=correction;
  return real(bits(math62_pack96(low,high,negative?D::Sign:0))-(U(8)<<52));
}
extern "C" void fo_lookup_setup(void) {auto p=(volatile uint32_t*)0xd00000c0;p[11]=8U|(4U<<5)|(11U<<10);p[2]=(uint32_t)(uintptr_t)log_table;}
template<bool HW> __attribute__((always_inline)) inline double ln_core(double x) {
  U b=bits(x);int adjustment=0;
  if(!(b&D::Magnitude))return real(D::Sign|D::Infinity);
  if((b&D::Magnitude)>D::Infinity)return real(b|D::Quiet);
  if(b&D::Sign)return real(D::Infinity|D::Quiet);
  if(b==D::Infinity)return x;
  if(!(b>>52)){const unsigned shift=clz64(b)-11;b=((b<<shift)&D::Fraction)|D::Hidden;adjustment=-int(shift);}
  if(b>=UINT64_C(0x3FEF800000000000) && b<=UINT64_C(0x3FF0400000000000))
    return math62_log_interval(b);
  const int k=int((b>>52)&0x7FFU)-1023+adjustment;
  const U m=((b&D::Fraction)|D::Hidden)<<10;
  const unsigned j=unsigned((b&D::Fraction)>>44);
  const U* row;
  if constexpr(HW){auto p=(volatile uint32_t*)0xd00000c0;p[0]=uint32_t(b>>32);row=(const U*)(uintptr_t)p[8];}
  else row=log_table[j];
  const Product product=multiply(m,row[0]);
  const U q=(product.high<<1)|(product.low>>63),tail=product.low&((U(1)<<63)-1);
  const U ratio=q+U(tail>(U(1)<<62) || (tail==(U(1)<<62) && (q&1)));
  const int64_t lm=int64_t(row[1])+math62_log_correction(int64_t(ratio-(U(1)<<62)));
  if(!k) return math62_pack96(U(lm),0,0);
  const uint32_t n=uint16_t(k<0?-k:k);
  const U lower=wide32(uint32_t(log_two),n);
  const U upper=wide32(uint32_t(log_two>>32),n)+(lower>>32);
  U low=(upper<<32)|uint32_t(lower);uint32_t high=uint32_t(upper>>32);
  const int64_t correction=k<0?-lm:lm;
  if(correction<0) {const U old=low;low-=U(-correction);high-=old<U(-correction);}
  else {const U old=low;low+=U(correction);high+=low<old;}
  return math62_pack96(low,high,k<0?D::Sign:0);
}
extern "C" __attribute__((noipa)) U fo_ln_cpu(U x,U){return bits(ln_core<false>(real(x)));}
extern "C" __attribute__((noipa)) U fo_ln_interp(U x,U){return bits(ln_core<true>(real(x)));}
