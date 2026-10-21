#include "native_eabi_m0_log10_table.inc"
#include "native_eabi_m0_log10_constants.inc"
__attribute__((optimize("Os"),noinline,cold,section(".m0_math_extension"))) static double log10_refine(double x);
// Use a direct base10 Q70 table for ordinary inputs; near-one paths scale
// the certified logarithm enclosure before binary64 rounding.
// Quantization, omitted products and Q94 refinements are bounded by
// tools/certify_m0_log10_fast.py. An undecided enclosure uses CORE-MATH.
// Separate flash sections preserve the addresses and bytes of earlier math.
__attribute__((always_inline)) inline double log10_pack70(U low,uint32_t high,U sign,uint32_t error,double x) {
  const U p0=wide32(high,uint32_t(log10_inverse));
  const U p1=wide32(high,uint32_t(log10_inverse>>32))+(p0>>32);
  const U c=(p1<<32)|uint32_t(p0),p=exp_high_product(low,log10_inverse);
  const U q=c+p;
  U result;
  // C<1/2; flooring C costs <high+1 units and the product loses <3.
  const uint32_t enclosure=(error+1)/2+high+4;
  if(r128_pack({(p1>>32)+U(q<c),q},24,sign,enclosure,result)) return real(result);
  return log10_refine(x);
}
__attribute__((always_inline)) inline double log10_pack_relative(U q,int e,U sign,unsigned error,double x) {
  const U value=exp_high_product(q,log10_inverse);U result;
  if(r128_pack({0,value},31+e,sign,(error+1)/2+4,result)) return real(result);
  return log10_refine(x);
}
__attribute__((optimize("Os"),noinline,section(".m0_math_extension"))) static double log10_near_one(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  if(!a) return 0.;
  const unsigned leading=clz64(a);
  const U q=a<<(leading-1),one=U(1)<<62,half=a>>1;
  U factor=one+(negative?half:U(0)-half);unsigned error=4;
  if(a>(U(1)<<27)) {
    const uint32_t t=uint32_t(a>>25);
    const U z=(wide32(t,t)>>12)+(wide32(t,uint32_t(a)&0x1FFFFFFU)>>36)+1;
    factor+=math62_third(z);error=8;
    if(a>(U(1)<<42)) {
      const U quarter=(math62_product(a,z)+2)>>2;
      factor+=negative?quarter:U(0)-quarter;error=32;
    }
  }
  return log10_pack_relative(math62_product(q,factor),2-int(leading),negative?D::Sign:0,error,x);
}
__attribute__((optimize("Os"),noinline,section(".m0_math_extension"))) static double log10_near_interval(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return log10_near_one(x,b);
  // The outer negative center has a 65-bit log value. Clamping to the
  // preceding center would need a 49-bit distance and invalidate the
  // short product and quartic remainder bounds below.
  if(negative && n==128) return log10_refine(x);
  const unsigned index=negative?128-n:128+n;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  U low=log_near_table[index-1][1];uint32_t high=0;
  if(delta) {
    const U h=mk61_m0_log_product54(delta,log_near_table[index-1][0]);
    const uint32_t t=uint32_t(h>>26);
    const U z=(wide32(t,t)>>18)+(wide32(t,uint32_t(h)&0x3FFFFFFU)>>43)+1;
    const uint32_t hr=uint32_t((h+(1U<<25))>>26),zr=uint32_t((z+(1U<<12))>>13);
    const uint32_t cube=uint32_t((wide32(hr,zr)+(U(1)<<30))>>31);
    const uint32_t q=uint32_t(wide32(cube,0xAAAAAAABU)>>33);
    const U third=q+U(cube-3*q>=2);
    const U fourth=(wide32(zr,zr)+(U(1)<<43))>>44;
    const U even=((z+1)>>1)+((fourth+2)>>2),odd=h+third;
    const U correction=subtract?odd+even:odd-even;
    if(subtract==negative) {const U before=low;low+=correction;high=low<before;}
    else low-=correction;
  }
  return log10_pack70(low,high,negative?D::Sign:0,8,x);
}
__attribute__((always_inline)) inline double log10_direct_pack70(U low,uint32_t high,U sign,uint32_t error,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  if(uint32_t(tail-(half-error))<=2*error) return log10_refine(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
__attribute__((optimize("Os"),section(".m0_math_extension"))) MK61_SOFT_PCS double mk61_m0_log10(double x) {
  const U b=bits(x);
  if(b<UINT64_C(0x0010000000000000) || b>=D::Infinity) return mk61_m0_cr_log10(x);
  if(b>=UINT64_C(0x3FEF800000000000) && b<=UINT64_C(0x3FF0400000000000))
    return log10_near_interval(x,b);
  const int k=int((b>>52)&0x7FFU)-1023;
  const uint32_t* row=log10_table[unsigned((b&D::Fraction)>>42)];
  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
  // Multiply the distance from the exact dyadic center, not the complete
  // mantissa. Clearing six reciprocal bits costs <2 Q70 residual units
  // and leaves room for the high log bits in a 16-byte table row.
  const U h=mk61_m0_log_product46(delta,reciprocal);
  const uint32_t t=uint32_t(h>>27);
  const U z=(wide32(t,t)>>16)+(wide32(t,uint32_t(h)&0x7FFFFFFU)>>42)+1;
  const U cube=mk61_m0_log_cube70(h,z);
  const U third=math62_third(cube);
  const uint32_t fourth=uint32_t(wide32(uint32_t(cube>>6),t)>>37);
  const uint32_t fifth=uint32_t(wide32(fourth,t)>>43);
  const U even=((z+1)>>1)+((fourth+2)>>2);
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=math62_product(negative?odd+even:odd-even,log10_inverse>>2);
  U low=(U(row[3])<<32)|row[2];uint32_t high=row[0]&63U;
  if(negative) {const U old=low;low-=correction;high-=low>old;}
  else {const U old=low;low+=correction;high+=low<old;}
  if(!k) return log10_direct_pack70(low,high,0,12,x);
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(log10_two_low),n),p1=wide32(uint32_t(log10_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log10_two_high*n;
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
  return log10_direct_pack70(result,upper,k<0?D::Sign:0,12+(n+1)/2,x);
}


__attribute__((always_inline)) inline bool log10_pack94(Product a,U sign,uint32_t error,U &out) {
  // Normal-input |ln(x)|<710. Dividing by1024 keeps the Q94 result
  // in96 bits; the complete scaling enclosure is at most4 units.
  const Refine96 normalized={(a.low>>10)|(a.high<<54),uint32_t(a.high>>10)};
  const Refine96 q=r96_product(normalized,log10_inverse94);
  return r96_pack(q,10,sign,(error+2047)/2048+3,out);
}
__attribute__((optimize("Os"),noinline,cold,section(".m0_math_extension"))) static double log10_refine(double x) {
  const U b=bits(x);const int k=int((b>>52)&0x7FFU)-1023;
  if(b>=UINT64_C(0x3FEFFFE000000000) && b<=UINT64_C(0x3FF0001000000000)) {
    const bool negative=b<UINT64_C(0x3FF0000000000000);
    const U s=(b&D::Fraction)|D::Hidden;
    const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
    if(!a) return 0.;
    const unsigned leading=clz64(a);const U normalized=a<<(leading-1);
    const int scale=1-int(leading);
    const Refine96 f={a<<32,uint32_t(a>>32)};
    const U f64=a<<2;
    const Refine96 z=r96_square64(f64);
    const U cube=r96_times64(z,f64),fourth=exp_high_product(cube,f64);
    Refine96 factor={0,1U<<30};
    factor=negative?r96_add(factor,r96_half(f)):r96_sub(factor,r96_half(f));
    factor=r96_add_low(factor,r96_times64(z,UINT64_C(6148914691236517206))+
      exp_high_product(fourth,UINT64_C(3689348814741910324)));
    factor=negative?r96_add_low(factor,cube>>2):r96_sub_low(factor,cube>>2);
    Refine96 q=r96_product({normalized<<32,uint32_t(normalized>>32)},factor);
    q=r96_product(q,log10_inverse94);
    const int tail_shift=5*int(64-leading)-216;
    const uint32_t tail=tail_shift>0?((1U<<unsigned(tail_shift))+2)/3:1;
    // The geometric correction covers the negative log-series tail.
    const uint32_t error=32+tail+((tail+8191)>>13);
    U result;
    if(r96_pack(q,scale,negative?D::Sign:0,error,result)) return real(result);
    return mk61_m0_cr_log10(x);
  }
  const U significand=(b&D::Fraction)|D::Hidden;
  const uint32_t* row=refine_log_table[unsigned((b&D::Fraction)>>42)];
  const Refine96 ratio=r96_product({significand<<42,uint32_t(significand>>22)},
    {(U(row[1])<<32)|row[0],row[2]});
  const bool negative=ratio.high<(1U<<30);
  const Refine96 one={0,1U<<30};
  const Refine96 h=negative?r96_sub(one,ratio):r96_sub(ratio,one);
  const U h64=(U(h.high)<<34)|(h.low>>30);
  Refine96 z=r96_square64(h64);
  // Restore the cross term from the 30 bits discarded by h64. Its
  // rounded high product corrects the square to <2+2^-34 Q94 units.
  const uint32_t tail=uint32_t(h.low)&0x3FFFFFFFU;
  z=r96_add_low(z,(wide32(uint32_t(h64>>32),tail)+(U(1)<<30))>>31);
  const U c3=r96_times64(z,h64),c4=exp_high_product(c3,h64);
  const U c5=exp_high_product(c4,h64),c6=exp_high_product(c5,h64),c7=exp_high_product(c6,h64);
  const U odd=exp_high_product(c3,UINT64_C(6148914691236517206))+
    exp_high_product(c5,UINT64_C(3689348814741910324))+
    exp_high_product(c7,UINT64_C(2635249153387078803));
  const U even=(c4>>2)+exp_high_product(c6,UINT64_C(3074457345618258603));
  Refine96 q={(U(row[4])<<32)|row[3],row[5]};
  q=negative?r96_sub(q,h):r96_add(q,h);
  q=r96_sub(q,r96_half(z));q=r96_sub_low(q,even);
  q=negative?r96_sub_low(q,odd):r96_add_low(q,odd);
  if(!k) {
    U result;if(log10_pack94({q.high,q.low},0,128,result)) return real(result);
  } else {
    const uint32_t n=uint16_t(k<0?-k:k);
    const U p0=wide32(uint32_t(refine_log_two_low),n),p1=wide32(uint32_t(refine_log_two_low>>32),n)+(p0>>32);
    Product t={U(refine_log_two_high)*n+(p1>>32),(p1<<32)|uint32_t(p0)};
    const U old=t.low;
    if(k<0) {t.low-=q.low;t.high-=q.high+U(old<q.low);}
    else {t.low+=q.low;t.high+=q.high+U(t.low<old);}
    // certify_m0_ln_refine.py includes every product/series rounding and
    // adds the separately rounded n*ln(2) contribution.
    U result;if(log10_pack94(t,k<0?D::Sign:0,128+(n+1)/2,result)) return real(result);
  }
  return mk61_m0_cr_log10(x);
}
