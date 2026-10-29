// RP2040 reserves four unused KiB immediately below its unchanged stack.
// Other ARMv6-M builds retain the existing flash section.
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#define MK61_M0_POW_HOT_SECTION ".scratch_y.m0_pow_hot"
#else
#define MK61_M0_POW_HOT_SECTION ".m0_pow_extension"
#endif
// On this path shift>=53, q.high<2^16 and sy<2^53. Omit the
// three bottom 16x16 products: their sum is below2^50, so the final
// integer argument differs from the full product by at most one unit.
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
MK61_SOFT_PCS Product mk61_m0_pow_argument(U low,uint32_t high,U sy,unsigned shift);
MK61_SOFT_PCS U mk61_m0_pow_exp_product(U q,U magnitude);
#endif
__attribute__((always_inline)) inline Product pow_general_argument(U low,uint32_t high,U sy,unsigned shift) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  return mk61_m0_pow_argument(low,high,sy,shift);
#else
  const uint32_t a0=uint32_t(low)&65535U,a1=uint32_t(low)>>16;
  const uint32_t a2=uint32_t(low>>32)&65535U,a3=uint32_t(low>>48),a4=high;
  const uint32_t b0=uint32_t(sy)&65535U,b1=uint32_t(sy)>>16;
  const uint32_t b2=uint32_t(sy>>32)&65535U,b3=uint32_t(sy>>48);
  const U c2=U(a0*b2)+U(a1*b1)+U(a2*b0);
  const U c3=U(a0*b3)+U(a1*b2)+U(a2*b1)+U(a3*b0)+(c2>>16);
  const U c4=U(a1*b3)+U(a2*b2)+U(a3*b1)+U(a4*b0)+(c3>>16);
  const U c5=U(a2*b3)+U(a3*b2)+U(a4*b1)+(c4>>16);
  const U c6=U(a3*b3)+U(a4*b2)+(c5>>16);
  const U c7=U(a4*b3)+(c6>>16);
  const U lo=(c2&65535U)|((c3&65535U)<<16)|((c4&65535U)<<32)|((c5&65535U)<<48);
  const U hi=(c6&65535U)|(c7<<16);
  const unsigned s=shift-32;
  return {hi>>s,(lo>>s)|(hi<<(64-s))};
#endif
}

// Exact comparisons and an unrounded Q94 logarithm/exp middle pass.
__attribute__((always_inline)) inline bool pow_scaled_argument(Product q,U sy,unsigned shift,Product &a) {
  if(shift>=128) return false;
  const Product low=multiply(q.low,sy),high=multiply(q.high,sy);
  const U middle=low.high+high.low,upper=high.high+U(middle<low.high);
  if(!shift) {if(upper) return false;a={middle,low.low};}
  else if(shift<64) {
    if(upper>>shift) return false;
    a={(middle>>shift)|(upper<<(64-shift)),(low.low>>shift)|(middle<<(64-shift))};
  } else if(shift==64) a={upper,middle};
  else {const unsigned s=shift-64;a={upper>>s,(middle>>s)|(upper<<(64-s))};}
  return true;
}
__attribute__((always_inline)) inline bool pow_argument_error(unsigned error,unsigned shift,unsigned &out) {
  if(shift>=53) {
    const unsigned s=shift-53;
    out=s>=32?1:(error+((1U<<s)-1))>>s;
    return true;
  }
  const unsigned s=53-shift;
  if(s>=28 || error>((1U<<28)>>s)) return false;
  out=error<<s;return true;
}
// Compare m * midpoint(lower,lower+1)^2 with 1, using exact 161-bit integers.
__attribute__((optimize("Os"),noinline,section(".m0_pow_extension"))) static int pow_rsqrt_boundary(U m,unsigned parity,U lower) {
  const U midpoint=(((lower&D::Fraction)|D::Hidden)<<1)+1;
  const int exponent=int(lower>>52)-1023;
  const Product square=multiply(midpoint,midpoint);
  const Product lo=multiply(square.low,m),hi=multiply(square.high,m);
  const U middle=lo.high+hi.low,upper=hi.high+U(middle<lo.high);
  const unsigned bit=unsigned(158-int(parity)-2*exponent);
  if(bit<128 || bit>=192) return 2;
  const U target=U(1)<<(bit-128);
  if(upper<target) return -1;
  if(upper>target || middle || lo.low) return 1;
  return 0;
}
#include "native_eabi_m0_rsqrt_table.inc"
// One integer Newton step encloses 1/sqrt(M) in q+-24 Q63 units.
// Only an ambiguous binary64 rounding cell needs an exact midpoint test.
__attribute__((optimize("Os"),noinline,section(".m0_pow_dispatch_extension"))) double pow_rsqrt(double x) {
  const U b=bits(x);U m=b&D::Fraction;int e=int(b>>52)-1023;
  if(b>>52) m|=D::Hidden;
  else {const unsigned shift=clz64(m)-11;m<<=shift;e=-1022-int(shift);}
  const unsigned parity=unsigned(e)&1U,index=unsigned((m&D::Fraction)>>44);
  const uint32_t center=513+2*index;
  const U c=U(center)<<43;const bool negative=m<c;
  const U distance=negative?c-m:m-c;
  // Subtracting one before the shift also represents the exact2^43
  // endpoint without overflowing the 32-bit hardware numerator.
  const uint32_t numerator=distance?uint32_t((distance-1)>>11):0;
  const uint32_t t=numerator?mk61_m0_math_udiv32(numerator,center):0;
  const U z=wide32(t,t);const uint32_t z32=uint32_t(z>>32);
  const uint32_t quadratic=(3*z32+4)>>3;
  const uint32_t cube=(z32*(t>>16))>>16,cubic=(5*cube+8)>>4;
  const int32_t delta=(negative?int32_t(t):-int32_t(t))+2*int32_t(quadratic)+
    (negative?2*int32_t(cubic):-2*int32_t(cubic));
  const uint32_t base=pow_rsqrt_seeds[(parity<<8)|index];
  const uint32_t magnitude=uint32_t(delta<0?-delta:delta);
  const uint32_t correction=uint32_t((wide32(base,magnitude)+(U(1)<<32))>>33);
  uint32_t seed=delta<0?base-correction:base+correction;
  if(delta>=0 && seed<base) seed=0xFFFFFFFFU;
  const U argument=m<<(10+parity),square=wide32(seed,seed);
  const U product=exp_high_product(argument,square);
  const U factor=(U(3)<<62)-product;
  const U p0=wide32(uint32_t(factor),seed);
  const U p1=wide32(uint32_t(factor>>32),seed)+(p0>>32);
  const U q=p1;
  const unsigned tail=unsigned(q)&1023U;
  const int scale=-(e-int(parity))/2;
  if(uint32_t(tail-(512U-24U))>48U) {
    const U rounded=(q+511+((q>>10)&1))>>10;
    return real((U(1021+scale)<<52)+rounded);
  }
  U lower=(U(1021)<<52)+(q>>10);
  const int compare=pow_rsqrt_boundary(m,parity,lower);
  if(compare==2) return mk61_m0_cr_pow(x,-0.5);
  lower+=compare<0 || (!compare && (lower&1));
  return real((lower&D::Fraction)|(U(int(lower>>52)+scale)<<52));
}
// For small integer y and |y*(x-1)|<=2^-28, the nonlinear remainder
// has magnitude <2^-55. The exact linear term is on the 2^-53 grid.
// Its only midpoint case is x<1,y<0; convexity makes that tie round up.
__attribute__((optimize("Os"),noinline,section(MK61_M0_POW_HOT_SECTION))) static bool pow_tiny_integer(U xb,U yb,U &out) {
  const U ym=yb&D::Magnitude;const int e=int(ym>>52)-1023;
  if(e<0 || e>16) return false;
  const U significand=(ym&D::Fraction)|D::Hidden;
  const unsigned shift=52-unsigned(e);
  if(significand&((U(1)<<shift)-1)) return false;
  const uint32_t n=uint32_t(significand>>shift);if(n>65536) return false;
  const U one=UINT64_C(0x3FF0000000000000);
  const bool below=xb<one;
  const uint32_t delta=uint32_t(below?one-xb:xb-one);
  const U units=wide32(delta,n);const unsigned fraction=below?53:52;
  if(units>(U(1)<<(fraction-28))) return false;
  const bool negative=below^bool(yb&D::Sign);
  out=negative?one-(units<<(53-fraction)):one+(below?((units+1)>>1):units);
  return true;
}

struct PowRefinedLog {Product q;unsigned scale,error;bool negative;};
__attribute__((optimize("Os"),noinline,cold,section(".m0_pow_refine_extension"))) static PowRefinedLog pow_refined_log(U b) {
  if(b>=UINT64_C(0x3FEFFFE000000000) && b<=UINT64_C(0x3FF0001000000000)) {
    const bool negative=b<UINT64_C(0x3FF0000000000000);
    const U s=(b&D::Fraction)|D::Hidden;
    const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
    const unsigned leading=clz64(a);const U normalized=a<<(leading-1);
    const Refine96 f={a<<32,uint32_t(a>>32)};
    const U f64=a<<2;
    const Refine96 z=r96_square64(f64);
    const U cube=exp_high_product(z.low,f64),fourth=exp_high_product(cube,f64);
    Refine96 factor={0,1U<<30};
    factor=negative?r96_add(factor,r96_half(f)):r96_sub(factor,r96_half(f));
    factor=r96_add_low(factor,exp_high_product(z.low,UINT64_C(6148914691236517206))+
      exp_high_product(fourth,UINT64_C(3689348814741910324)));
    factor=negative?r96_add_low(factor,cube>>2):r96_sub_low(factor,cube>>2);
    const Refine96 q=r96_product({normalized<<32,uint32_t(normalized>>32)},factor);
    const unsigned top=63-leading;
    const int omitted_shift=5*int(top+1)-216;
    const uint32_t error=64+(omitted_shift>0?((1U<<unsigned(omitted_shift))+2)/3:1);
    return {{q.high,q.low},93+leading,error,negative};
  }
  const int k=int((b>>52)&0x7FFU)-1023;
  const U significand=(b&D::Fraction)|D::Hidden;
  const uint32_t* row=refine_log_table[unsigned((b&D::Fraction)>>42)];
  const Refine96 ratio=r96_product({significand<<42,uint32_t(significand>>22)},
    {(U(row[1])<<32)|row[0],row[2]});
  const bool negative=ratio.high<(1U<<30);
  const Refine96 one={0,1U<<30};
  const Refine96 h=negative?r96_sub(one,ratio):r96_sub(ratio,one);
  const U h64=(U(h.high)<<34)|(h.low>>30);
  Refine96 z=r96_square64(h64);
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
  if(!k) return {{q.high,q.low},94,128,false};
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(refine_log_two_low),n),p1=wide32(uint32_t(refine_log_two_low>>32),n)+(p0>>32);
  Product t={U(refine_log_two_high)*n+(p1>>32),(p1<<32)|uint32_t(p0)};
  const U old=t.low;
  if(k<0) {t.low-=q.low;t.high-=q.high+U(old<q.low);}
  else {t.low+=q.low;t.high+=q.high+U(t.low<old);}
  return {t,94,128+(n+1)/2,k<0};
}
__attribute__((optimize("Os"),noinline,cold,section(".m0_pow_refine_extension"))) static double pow_refine_checked(double x,double y) {
  const U xb=bits(x),yb=bits(y),ym=yb&D::Magnitude;
  const int ey=int(ym>>52)-1023;
  if(xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity || ey < -12 || ey>64 || xb==UINT64_C(0x3FF0000000000000))
    return mk61_m0_cr_pow(x,y);
  const PowRefinedLog logarithm=pow_refined_log(xb);
  const int shift=int(logarithm.scale)-44-ey;
  if(shift<0) return mk61_m0_cr_pow(x,y);
  Product argument;unsigned input_error;
  if(!pow_scaled_argument(logarithm.q,(ym&D::Fraction)|D::Hidden,unsigned(shift),argument) ||
     !pow_argument_error(logarithm.error,unsigned(shift),input_error)) return mk61_m0_cr_pow(x,y);
  const bool negative_argument=logarithm.negative^bool(yb&D::Sign);
  if((argument.high>>32)>=(negative_argument?746U:710U)) return real(negative_argument?0:D::Infinity);
  if((argument.high>>32)>=700) return mk61_m0_cr_pow(x,y);
  const U p0=wide32(uint32_t(argument.high),0xB8AA3B29U);
  const U p1=wide32(uint32_t(argument.high>>32),0xB8AA3B29U)+(p0>>32);
  const uint32_t n=uint32_t((p1+(1U<<21))>>22);
  const U s0=wide32(uint32_t(refine_exp_step[0]),n);
  const U s1=wide32(uint32_t(refine_exp_step[0]>>32),n)+(s0>>32);
  const U s2=wide32(uint32_t(refine_exp_step[1]),n)+(s1>>32);
  const uint32_t s3=uint32_t(refine_exp_step[1]>>32)*n+uint32_t(s2>>32);
  const U pl=(s1<<32)|uint32_t(s0),ph=(U(s3)<<32)|uint32_t(s2);
  const U rl=(pl>>16)|(ph<<48),rh=ph>>16;
  U low=argument.low-rl,high=argument.high-rh-U(argument.low<rl);
  bool negative=bool(high>>63);
  if(negative) {low=U(0)-low;high=~high+U(!low);}
  if(high>3006477) return mk61_m0_cr_pow(x,y);
  negative^=negative_argument;
  const Refine96 r={(low>>2)|(high<<62),uint32_t(high>>2)};
  const U h=(high<<32)|(low>>32);
  const U h64=h+U(uint32_t(low)>0x80000000U);
  const Refine96 z=r96_square64(h64);
  const U c3=r96_times64(z,h64),c4=exp_high_product(c3,h64);
  const U c5=exp_high_product(c4,h64),c6=exp_high_product(c5,h64),c7=exp_high_product(c6,h64);
  const U odd=exp_high_product(c3,UINT64_C(3074457345618258603))+
    exp_high_product(c5,UINT64_C(153722867280912931))+
    exp_high_product(c7,UINT64_C(3660068268593166));
  const U even=exp_high_product(c4,UINT64_C(768614336404564651))+
    exp_high_product(c6,UINT64_C(25620477880152156));
  Refine96 q={0,1U<<30};
  q=negative?r96_sub(q,r):r96_add(q,r);
  q=r96_add(q,r96_half(z));q=r96_add_low(q,even);
  q=negative?r96_sub_low(q,odd):r96_add_low(q,odd);
  const int signed_n=negative_argument?-int(n):int(n);
  const unsigned index=unsigned(signed_n)&511;
  const uint32_t* row=refine_exp_table[index];
  q=r96_product(q,{(U(row[1])<<32)|row[0],row[2]});
  U result;
  if(r96_pack(q,(signed_n-int(index))/512,0,(1U<<24)+input_error,result)) return real(result);
  return mk61_m0_cr_pow(x,y);
}

// For |f|=|x-1|<=2^-36 and |y*f|<700, form y*(f-f*f/2)
// without first rounding ln(x). The omitted logarithmic tail is <1 Q64
// unit. Exact 32x32 products and two floors give a full +-4 enclosure.
__attribute__((optimize("Os"),noinline,section(MK61_M0_POW_HOT_SECTION))) static bool pow_near_one_argument(U xb,U yb,Product &argument,unsigned &error,bool &negative) {
  const U one=UINT64_C(0x3FF0000000000000),ym=yb&D::Magnitude;
  const bool below=xb<one;
  const unsigned p=below?53U:52U;
  const U distance=below?one-xb:xb-one;
  const int ey=int(ym>>52)-1023;
  if(!distance || distance>(U(1)<<(p-36)) || ey<20 || ey>64) return false;
  const uint32_t delta=uint32_t(distance);
  const U sy=(ym&D::Fraction)|D::Hidden;
  const U lo=wide32(uint32_t(sy),delta);
  const U mid=wide32(uint32_t(sy>>32),delta)+(lo>>32);
  Product linear={mid>>32,(mid<<32)|uint32_t(lo)};
  const int shift=int(p)-12-ey;
  if(shift>0) {
    linear.low=(linear.low>>unsigned(shift))|(linear.high<<(64-unsigned(shift)));
    linear.high>>=unsigned(shift);
  } else if(shift<0) {
    linear.high=(linear.high<<unsigned(-shift))|(linear.low>>(64-unsigned(-shift)));
    linear.low<<=unsigned(-shift);
  }
  if(linear.high>=700) return false;
  const U q0=wide32(uint32_t(linear.low),delta);
  const U q1=wide32(uint32_t(linear.low>>32),delta)+(q0>>32);
  const U q2=(q1>>32)+linear.high*delta;
  const U qlow=(q1<<32)|uint32_t(q0);
  const U quadratic=(qlow>>(p+1))|(q2<<(63-p));
  argument=linear;
  if(below) {argument.low+=quadratic;argument.high+=argument.low<linear.low;}
  else {argument.low-=quadratic;argument.high-=argument.low>linear.low;}
  error=4;negative=below^bool(yb&D::Sign);return true;
}

#include "native_eabi_m0_pow_third.inc"
#include "native_eabi_m0_pow_tail.inc"
#include "native_eabi_m0_pow_ln2.inc"

// Checked binary64 pow first tier. Every accepted cell contains its full interval.
struct PowFastLog {U low;uint32_t high,error;bool negative;unsigned scale;};
__attribute__((optimize("Os"),noinline,section(".m0_pow_extension"))) static PowFastLog pow_fast_log(U b) {
  if(b>=UINT64_C(0x3FEFFF8000000000) && b<=UINT64_C(0x3FF0004000000000)) {
    const bool negative=b<UINT64_C(0x3FF0000000000000);
    const U s=(b&D::Fraction)|D::Hidden;
    const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
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
    return {math62_product(q,factor),0,error,negative,61+leading};
  }
  const int k=int((b>>52)&0x7FFU)-1023;
  const unsigned index=unsigned((b&D::Fraction)>>42);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
  // The distance from the exact dyadic center is kept unrounded.
  // RP2040 divides it exactly; generic ARMv6-M uses the certified reciprocal.
  const U h=log70_residual(delta,index);
  const uint32_t t=uint32_t(h>>27);
  const U z=(wide32(t,t)>>16)+(wide32(t,uint32_t(h)&0x7FFFFFFU)>>42)+1;
  const U cube=mk61_m0_log_cube70(h,z);
  const U third=pow_log_third70(cube);
  const uint32_t fourth=pow_log_fourth70(cube,t);
  const uint32_t fifth=pow_log_fifth70(fourth,t);
  const U even=((z+1)>>1)+((fourth+2)>>2);
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=negative?U(0)-odd-even:odd-even;
  const Log70Center center=log70_center(index);
  U low=center.low;uint32_t high=center.high;
  if(negative) {const U old=low;low+=correction;high-=low>old;}
  else {const U old=low;low+=correction;high+=low<old;}
  if(!k) return {low,high,16,false,70};
  const uint32_t n=uint16_t(k<0?-k:k);
  const Product scaled=pow_log_two70(n);
  U result=scaled.low;uint32_t upper=uint32_t(scaled.high);
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
  return {result,upper,16+(n+1)/2,k<0,70};
}
__attribute__((optimize("Os"),noinline,section(MK61_M0_POW_HOT_SECTION))) static double pow_positive_checked(double,double);
// For a negative finite base and a finite integer exponent, RNE of
// the magnitude commutes with the exact sign change, including zero/inf.
__attribute__((optimize("Os"),noinline,section(".m0_pow_dispatch_extension"))) static double pow_negative_integer(double x,double y) {
  const U xb=bits(x),yb=bits(y),m=xb&D::Magnitude,ym=yb&D::Magnitude;
  if(!m || m>=D::Infinity || ym>=D::Infinity) return mk61_m0_cr_pow(x,y);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const uint32_t yh=uint32_t(ym>>32),yl=uint32_t(ym);
  const int e=int(yh>>20)-1023;bool odd=false;
  if(e<=52) {
    if(e<0) return mk61_m0_cr_pow(x,y);
    if(e<=20) {
      // 20-e is in [0,20]; exponent bits cannot enter the low-bit mask.
      const unsigned shift=20-unsigned(e);
      if(yl || (yh&((1U<<shift)-1U))) return mk61_m0_cr_pow(x,y);
      odd=bool((yh>>shift)&1U);
    } else {
      // 52-e is in [0,31], so no C++ shift ever equals the word width.
      const unsigned shift=52-unsigned(e);
      if(yl&((1U<<shift)-1U)) return mk61_m0_cr_pow(x,y);
      odd=bool((yl>>shift)&1U);
    }
  }
#else
  const int e=int(ym>>52)-1023;bool odd=false;
  if(e<=52) {
    if(e<0) return mk61_m0_cr_pow(x,y);
    const unsigned shift=52-unsigned(e);
    const U significand=(ym&D::Fraction)|D::Hidden;
    if(significand&((U(1)<<shift)-1)) return mk61_m0_cr_pow(x,y);
    odd=bool((significand>>shift)&1);
  }
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // R64 normal-result certificate: |x| immediately below a power of two,
  // y=-n, 1<=n<=64. The exact normalized magnitude is strictly between
  // 1+n/2^53 and 1+(n+1)/2^53; nearest-even adds ceil(n/2) ulps.
  // The existing finite/integer checks above supply e>=0 and exact odd.
  const unsigned E=unsigned(m>>52);
  if((yb&D::Sign) && unsigned(e)<=6U && E &&
     uint32_t(m)==0xFFFFFFFFU &&
     (uint32_t(m>>32)&0xFFFFFU)==0xFFFFFU) {
    const unsigned n=((uint32_t(ym>>32)&0xFFFFFU)|0x100000U)>>unsigned(20-e);
    if(n<=64U) {
      const int p=(1022-int(E))*int(n);
      if(unsigned(p+1022)<=2045U)
        return real((U(uint32_t(p+1023))<<52)|U((n+1U)>>1)|
                    (odd?D::Sign:U(0)));
    }
  }
#endif
  const U result=m==UINT64_C(0x3FF0000000000000)?m:bits(pow_positive_checked(real(m),y));
  return real(result|(odd?D::Sign:0));
}

#include "native_eabi_m0_pow_integer.inc"

__attribute__((optimize("Os"),noinline,section(MK61_M0_POW_HOT_SECTION))) static double pow_positive_checked(double x,double y) {
  const U xb=bits(x),yb=bits(y),ym=yb&D::Magnitude;
  Product argument;unsigned input_error;bool negative_argument;
  if(xb>=UINT64_C(0x3FF0000000000000)-(U(1)<<21) && xb<=UINT64_C(0x3FF0000000000000)+(U(1)<<20)) {
    U result;if(pow_tiny_integer(xb,yb,result)) return real(result);
    if(pow_near_one_argument(xb,yb,argument,input_error,negative_argument)) goto pow_exp_argument;
  }
  if(!uint32_t(yb) && uint32_t(yb>>32)-0x40080000U<=0x00180000U) {
    const U result=pow_small_integer(xb,uint32_t(yb>>32));
    if(result!=(D::Infinity|D::Quiet)) return real(result);
  }
  {
    const int ey=int(ym>>52)-1023;
    if(xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity || ey < -12 || ey>64)
      return pow_refine_checked(x,y);
    const PowFastLog logarithm=pow_fast_log(xb);
    const U sy=(ym&D::Fraction)|D::Hidden;
    const int signed_shift=int(logarithm.scale)-12-ey;
    if(signed_shift<0) return pow_refine_checked(x,y);
    if(logarithm.scale==70 && ey<=5) {
      argument=pow_general_argument(logarithm.low,logarithm.high,sy,unsigned(signed_shift));
      if(!pow_argument_error(logarithm.error,unsigned(signed_shift),input_error)) return pow_refine_checked(x,y);
      ++input_error;
    } else if(!pow_scaled_argument({logarithm.high,logarithm.low},sy,unsigned(signed_shift),argument) ||
              !pow_argument_error(logarithm.error,unsigned(signed_shift),input_error))
      return pow_refine_checked(x,y);
    negative_argument=logarithm.negative^bool(yb&D::Sign);
  }
pow_exp_argument:
  // The same certified residual polynomial covers finite results up
  // through overflow and gradual underflow. Far endpoints remain exact.
  if(argument.high>=(negative_argument?746U:710U)) return real(negative_argument?0:D::Infinity);
  const U p0=wide32(uint32_t(argument.low>>32),0xB8AA3B29U);
  const U p1=wide32(uint32_t(argument.high),0xB8AA3B29U)+(p0>>32);
  const uint32_t n=uint32_t((p1+(1U<<21))>>22);
  const U reduction=wide32(uint32_t(exp_step_high),n)+(U(uint32_t(exp_step_high>>32)*n)<<32);
  U r=argument.low-reduction-uint32_t(wide32(n,exp_step_low)>>32);
  int k=int(n);
  if(negative_argument) {r=U(0)-r;k=-k;}
  const bool negative=(r>>63)!=0;
  const U magnitude=negative?U(0)-r:r;
  // Protect the polynomial's certified domain independently of the segment
  // estimate. Opposing truncations keep split reduction error below
  // 1.001 Q64 units; certify_m0_exp_fast.py checks the complete interval.
  if(magnitude>UINT64_C(12912720851596686)) return pow_refine_checked(x,y); // 0.0007
  const U z=exp_high_square(magnitude)&((U(1)<<44)-1);
  const uint32_t t=uint32_t((magnitude+(1U<<21))>>22); // |r| in Q42
  // Evaluate r/6+r*r/24+r*r*r/120 in Q44; it still fits int32.
  // The combined coefficient error is <3 Q44 units. Including the fifth
  // term costs fewer wide products than the old Q40 fourth-degree path.
  const uint32_t linear=pow_exp_linear32(t);
  const uint32_t square=uint32_t((z+(1U<<22))>>23);
  const uint32_t quadratic=uint32_t(wide32(square+1,0xAAAAAAABU)>>33);
  const uint32_t cubic=(uint32_t(z>>32)*(t>>16)+(1U<<16))>>17;
  const uint32_t fifth=((cubic+7)*2185U)>>15;
  const int32_t tail=(negative?-int32_t(linear):int32_t(linear))+int32_t(quadratic)+
    (negative?-int32_t(fifth):int32_t(fifth));
  const uint32_t tail_magnitude=tail<0?uint32_t(-tail):uint32_t(tail);
  const U p=wide32(uint32_t(z),tail_magnitude);
  const U c=(wide32(uint32_t(z>>32),tail_magnitude)+(p>>32))>>12;
  const U delta=r+(z>>1)+(tail<0?U(0)-c:c);
  const unsigned index=unsigned(k)&511U;
  k=(k-int(index))/512;
  U q=exp_table[index];
  const bool below=(delta>>63)!=0;
  const U d=below?U(0)-delta:delta;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // The rounded13-product specialization has error<=1/2+2^-15.
  const U correction=mk61_m0_pow_exp_product(q,d);
#else
  const U cross=wide32(uint32_t(q),uint32_t(d>>32))+
    wide32(uint32_t(q>>32),uint32_t(d));
  const U correction=wide32(uint32_t(q>>32),uint32_t(d>>32))+(cross>>32)+1;
#endif
  q=below?q-correction:q+correction;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  unsigned error=(input_error<=129?3U:4U)+(input_error+1)/2;
#else
  unsigned error=4+(input_error+1)/2;
#endif
  if(error>=256) return pow_refine_checked(x,y);
  if(q<(U(1)<<62)) {q<<=1;--k;error*=2;}
  if(k>1023) {
    // At exponent1024 the overflow midpoint is Q62 2^62-256.
    if(k>1024 || q-(U(1)<<62)+256>error) return real(D::Infinity);
    return pow_refine_checked(x,y);
  }
  if(k<-1022) {
    if(k<-1075) {
      const U half=U(1)<<63;
      if(k<-1076 || (q<half && half-q>error)) return 0.0;
    } else {
      const unsigned shift=unsigned(-k-1012);
      const U mask=(U(1)<<shift)-1,half=U(1)<<(shift-1),tail=q&mask;
      const U distance=tail>half?tail-half:half-tail;
      if(distance>error) {
        const U retained=q>>shift;
        return real(retained+U(tail>half || (tail==half && (retained&1))));
      }
    }
    return pow_refine_checked(x,y);
  }
  const uint32_t rounding_tail=uint32_t(q)&1023U;
  if(uint32_t(rounding_tail-(512U-error))<=2*error) return pow_refine_checked(x,y);
  const U rounded=(q+511+((q>>10)&1))>>10;
  return real((U(k+1022)<<52)+rounded);
}

__attribute__((optimize("Os"),noinline,section(".m0_pow_dispatch_extension"))) MK61_SOFT_PCS double mk61_m0_pow_dispatch(double x,double y) {
  const U xb=bits(x),yb=bits(y);
  if(!uint32_t(yb)) {
    switch(uint32_t(yb>>32)) {
    case 0xBFF00000U:return 1.0/x;
    case 0x3FE00000U: {
      const U m=xb&D::Magnitude;
      return !m || m==D::Infinity?real(m):mk61_m0_sqrt(x);
    }
    case 0xBFE00000U: {
      const U m=xb&D::Magnitude;
      if(!m) return real(D::Infinity);
      if(m==D::Infinity) return 0.0;
      return xb<D::Infinity?pow_rsqrt(x):mk61_m0_cr_pow(x,y);
    }
    }
  }
  const U ym=yb&D::Magnitude;
  if(!ym) return real((xb&D::Magnitude)>D::Infinity && !(xb&D::Quiet)?xb|D::Quiet:UINT64_C(0x3FF0000000000000));
  if(xb==UINT64_C(0x3FF0000000000000)) return real(ym>D::Infinity && !(yb&D::Quiet)?yb|D::Quiet:xb);
  if(xb&D::Sign) return pow_negative_integer(x,y);
  return pow_positive_checked(x,y);
}

#undef MK61_M0_POW_HOT_SECTION
