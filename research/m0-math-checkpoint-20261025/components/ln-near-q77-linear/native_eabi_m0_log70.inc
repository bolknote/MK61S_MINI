#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
enum : uint32_t {ln_main_radius=8U,ln_near_radius=4U};
// The first negative near-center has65 log bits and is deliberately
// excluded. Its entire half-cell uses the certified general kernel.
enum : U {ln_near_lower=UINT64_C(0x3FEF808000000001)};
#else
enum : uint32_t {ln_main_radius=16U,ln_near_radius=8U};
enum : U {ln_near_lower=UINT64_C(0x3FEF800000000000)};
#endif
// A ten-bit segment index keeps |h| < 1/2048. All fast paths certify a
// complete error interval before returning a binary64 rounding.
__attribute__((always_inline)) inline double ln_pack70(U low,uint32_t high,U sign,uint32_t error,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Actual error is strictly below the integer radius. The discrete
  // midpoint distance may equal that radius and still be accepted.
  const uint32_t guard=error-1;
#else
  const uint32_t guard=error;
#endif
  if(uint32_t(tail-(half-guard))<=2*guard) return ln_refine(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// The polynomial division remainders give an exact integer bias. The
// known h residual removes its symmetric quotient error from the gate.
__attribute__((always_inline)) inline double ln_near_round_pack(U low,uint32_t high,U sign,
    int32_t bias12,int32_t residue,uint32_t den,bool add,bool exact_center,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t distance=tail>half?tail-half:half-tail;
  bool safe=distance>=4;
  if(!safe && distance) {
    if(exact_center) safe=true;
    else if(bool(tail>half)==add)
      safe=int32_t(den)*(int32_t(12*distance)-bias12)+12*residue>=18*int32_t(den);
    else safe=int32_t(den)*(int32_t(12*distance)+bias12)-12*residue>=21*int32_t(den);
  }
  if(!safe) return ln_refine(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
#endif
__attribute__((always_inline)) inline double ln_pack_relative(U q,int e,U sign,unsigned error,double x) {
  if(q<(U(1)<<62)) {q<<=1;--e;error*=2;}
  const unsigned high=unsigned(q>>63),shift=10+high;
  const uint32_t half=1U<<(shift-1),tail=uint32_t(q)&((half<<1)-1);
  if(uint32_t(tail-(half-error))<=2*error) return ln_refine(x);
  const U rounded=(q>>shift)+U(tail>half || (tail==half && ((q>>shift)&1)));
  return real(sign+(U(e+1021+int(high))<<52)+rounded);
}
__attribute__((optimize("Os"),noinline)) static double ln_near_one(double x,U b) {
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
  return ln_pack_relative(math62_product(q,factor),2-int(leading),negative?D::Sign:0,error,x);
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
static constexpr int8_t ln_near_q77_delta[256]={
  -15,-39,-55,19,13,-4,-51,5,-7,-57,11,-33,18,42,32,-30,
  19,15,47,-52,8,-45,52,-46,62,-5,-49,-54,22,3,-41,-39,
  36,55,63,46,11,-4,34,33,-11,5,-14,41,54,-47,54,47,
  -25,-1,-44,23,26,-36,-38,25,-9,52,63,64,-33,-45,35,51,
  6,-61,-3,46,0,-54,-51,53,-45,23,-50,18,6,-54,42,21,
  -58,55,-55,49,28,25,58,-8,-47,36,-45,18,8,28,10,51,
  41,-8,52,54,38,54,34,-22,-55,-23,-40,49,14,46,-38,6,
  55,21,-51,31,54,50,-11,44,15,-26,-63,-8,-42,22,9,0,
  8,12,-35,-51,21,6,-9,1,-8,39,-39,30,-41,8,-19,-44,
  60,57,26,-42,64,-8,47,29,-50,38,54,-52,-52,-46,20,8,
  -39,19,33,11,-8,-9,18,30,-39,-59,-44,-50,6,-50,53,11,
  43,5,-8,-21,46,34,38,-50,-42,-18,52,11,46,4,-56,-17,
  -45,44,-54,25,-25,-7,-35,11,-51,-28,-1,-7,-45,1,-6,13,
  3,0,52,-51,53,23,37,49,2,-6,-2,41,-61,6,34,20,
  59,58,32,-33,-5,23,54,-49,45,9,-5,43,-50,-25,-37,62,
  -8,39,-47,-37,-51,-44,31,-14,14,-31,-12,54,-6,-47,28,-5,
};
__attribute__((always_inline)) inline U ln_near_argument77(U delta,U reciprocal,uint32_t den,int32_t& residue) {
  U h=mk61_m0_log_product54(delta,reciprocal)<<7;
  const int32_t r=int32_t((uint32_t(delta)<<28)-uint32_t(h)*den);
  const bool negative=r<0;
  const uint32_t magnitude=negative?0U-uint32_t(r):uint32_t(r);
  // 4096-floor(den/4) approximates2^24/den within3/4 throughout
  // den8065..8320. The final captured residue certifies its rounding.
  const uint32_t correction=(magnitude*(4096U-(den>>2))+(1U<<23))>>24;
  const int32_t signed_correction=negative?-int32_t(correction):int32_t(correction);
  h+=U(int64_t(signed_correction));
  residue=int32_t((uint32_t(delta)<<28)-uint32_t(h)*den);
  return h;
}
__attribute__((always_inline)) inline U ln_near_third77(U a) {
  const uint32_t hi=uint32_t(a>>32),lo=uint32_t(a);
  const uint32_t qh=(hi*171U)>>9;
  const uint32_t ql=uint32_t(wide32(lo,0xAAAAAAABU)>>33);
  const uint32_t rh=hi-3*qh,tail=rh+lo-3*ql,carry=tail>=3;
  const U q=(U(qh)<<32)|uint32_t(ql+rh*0x55555555U+carry);
  return q+U(tail-3*carry>=2);
}
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
__attribute__((optimize("Os"),noinline)) static double ln_near_interval77(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return ln_near_one(x,b);
  // The outer negative center has a 65-bit log value. Clamping to the
  // preceding center would need a 49-bit distance and invalidate the
  // short product and quartic remainder bounds below.
  if(negative && n==128) return ln_refine(x);
  const unsigned index=negative?128-n:128+n;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  const U base=log_near_table[index-1][1];
  U low=(base<<7)+U(int64_t(ln_near_q77_delta[index-1]));
  uint32_t high=uint32_t(base>>57);
  int32_t bias60=0,residue=0;
  const uint32_t den=8064U+index;
  if(delta) {
    const U h=ln_near_argument77(delta,log_near_table[index-1][0],den,residue);
    U correction=h;
    if(h>(U(1)<<38)) {
      const uint32_t t=uint32_t(h>>32);
      const U z=(wide32(t,t)>>13)+(wide32(t,uint32_t(h))>>44)+1;
      const uint32_t zc=uint32_t(z>>18);
      U cp=wide32(t,zc);
      cp+=uint32_t((uint32_t(h)>>16)*(zc>>16));
      cp+=uint32_t((t>>16)*((uint32_t(z)>>2)&65535U));
      const U cube=(cp+(U(1)<<26))>>27;
      const U third=ln_near_third77(cube);
      const uint32_t zr=uint32_t(z>>19);
      const uint32_t fourth=uint32_t((wide32(zr,zr)+(U(1)<<38))>>39);
      const uint32_t fifth=(((t>>16)*(fourth>>6))+(1U<<22))>>23;
      const uint32_t fifth_term=((fifth+2U)*205U)>>10;
      const U even=((z+1)>>1)+((fourth+2)>>2),odd=h+third+fifth_term;
      correction=subtract?odd+even:odd-even;
      const int32_t r2=-int32_t(z&1U);
      const int32_t r3=int32_t(uint32_t(cube)-3U*uint32_t(third));
      const int32_t r4=int32_t((fourth+2)&3U)-2;
      const int32_t r5=int32_t(fifth)-5*int32_t(fifth_term);
      const int32_t even_bias=6*r2+3*r4;
      bias60=5*(-4*r3+(subtract?-even_bias:even_bias))-12*r5;
    }
    if(subtract==negative) {const U before=low;low+=correction;high+=uint32_t(low<before);}
    else {const U before=low;low-=correction;high-=uint32_t(before<correction);}
  }
  return ln_near_round_pack77(low,high,negative?D::Sign:0,bias60,residue,den,subtract==negative,!delta,x);
}
#endif
__attribute__((optimize("Os"),noinline)) static double ln_near_interval(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return ln_near_one(x,b);
  // The outer negative center has a 65-bit log value. Clamping to the
  // preceding center would need a 49-bit distance and invalidate the
  // short product and quartic remainder bounds below.
  if(negative && n==128) return ln_refine(x);
  const unsigned index=negative?128-n:128+n;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  U low=log_near_table[index-1][1];uint32_t high=0;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  int32_t bias12=0,residue=0;
  const uint32_t den=8064U+index;
#endif
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
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    const int32_t r2=-int32_t(z&1U);
    const int32_t r3=int32_t(cube)-3*int32_t(third);
    const int32_t r4=int32_t((fourth+2)&3U)-2;
    const int32_t even_bias=6*r2+3*r4;
    bias12=-4*r3+(subtract?-even_bias:even_bias);
    residue=int32_t((uint32_t(delta)<<21)-uint32_t(h)*den);
#endif
    if(subtract==negative) {const U before=low;low+=correction;high=low<before;}
    else low-=correction;
  }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  return ln_near_round_pack(low,high,negative?D::Sign:0,bias12,residue,den,subtract==negative,!delta,x);
#else
  return ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x);
#endif
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// The exact signed h residual removes the quotient error from the cold
// pack test. Its remaining strict base is6.900060<7Q70 units.
__attribute__((always_inline)) inline double ln_main_pack70(U low,uint32_t high,U sign,
    uint32_t exponent_error,uint32_t h_low,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t guard=15U+exponent_error;
  if(uint32_t(tail-(half-guard))<=2U*guard) {
    const uint32_t distance=tail>half?tail-half:half-tail;
    if(!distance) return ln_refine(x);
    const U b=bits(x);
    const uint32_t den=2049U+2U*unsigned((b&D::Fraction)>>42);
    const bool negative=(b&(U(1)<<41))==0;
    uint32_t delta_low=uint32_t(b)<<29;
    if(negative) delta_low=0U-delta_low;
    const int32_t residue=int32_t(delta_low-h_low*den);
    const int32_t oriented=(negative!=(sign!=0))?-residue:residue;
    const int32_t directed=tail>half?oriented:-oriented;
    if((int32_t(distance)-int32_t(7U+exponent_error))*int32_t(den)+directed<0)
      return ln_refine(x);
  }
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
__attribute__((optimize("Os"),noinline)) static double ln_main_raw(U b) {
  const double x=real(b);
  const int k=int((b>>52)&0x7FFU)-1023;
  const unsigned index=unsigned((b&D::Fraction)>>42);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
  // The distance from the exact dyadic center is kept unrounded.
  // RP2040 divides it exactly; generic ARMv6-M uses the certified reciprocal.
  const uint32_t* row=log10_table[index];
  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);
  const U h=mk61_m0_log_product46(delta,reciprocal);
  const uint32_t t=uint32_t(h>>27);
  const U z=(wide32(t,t)>>16)+(wide32(t,uint32_t(h)&0x7FFFFFFU)>>42)+1;
  const U cube=mk61_m0_log_cube70(h,z);
  const U third=math62_third(cube);
  const uint32_t fourth=uint32_t(wide32(uint32_t(cube>>6),t)>>37);
  const uint32_t fifth=uint32_t(wide32(fourth,t)>>43);
  const U even=((z+1)>>1)+((fourth+2)>>2);
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=negative?U(0)-odd-even:odd-even;
  const Log70Center center=log70_center(index);
  U low=center.low;uint32_t high=center.high;
  if(negative) {const U old=low;low+=correction;high-=low>old;}
  else {const U old=low;low+=correction;high+=low<old;}
  if(!k) return ln_main_pack70(low,high,0,0,uint32_t(h),x);
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(log70_two_low),n),p1=wide32(uint32_t(log70_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log70_two_high*n;
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
  return ln_main_pack70(result,upper,k<0?D::Sign:0,(n+1)/2,uint32_t(h),x);
}

#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Avoid a C++ frame for IEEE zero and positive infinity. Every other
// non-normal input still reaches the existing cold implementation.
__attribute__((naked,noinline,optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double) {
  asm volatile(
    ".syntax unified\n"
    "cmp r0,#0\nbne .Lln_classify\n"
    "lsls r2,r1,#1\nbeq .Lln_zero\n"
    "ldr r2,=0x7ff00000\ncmp r1,r2\nbeq .Lln_return\n"
    ".Lln_classify:\nlsrs r2,r1,#20\nadds r3,r2,#1\nlsrs r3,r3,#11\n"
    "bne .Lln_cold\ncmp r2,#0\nbeq .Lln_cold\nb mk61_m0_ln_positive\n"
    ".Lln_zero:\nldr r1,=0xfff00000\n"
    ".Lln_return:\nbx lr\n"
    ".Lln_cold:\nldr r3,=mk61_m0_ln_special\nbx r3\n"
    ".p2align 2\n.ltorg\n.syntax divided\n");
}
__attribute__((optimize("Os"),noinline)) MK61_SOFT_PCS double mk61_m0_ln_positive(double x) {
  const U b=bits(x);
#else
__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {
  const U b=bits(x);
  if(b<UINT64_C(0x0010000000000000) || b>=D::Infinity)
    return mk61_m0_cr_ln(x);
#endif
  if(b>=ln_near_lower && b<=UINT64_C(0x3FF0400000000000))
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    return ln_near_interval77(x,b);
#else
    return ln_near_interval(x,b);
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(uint32_t(uint32_t(b)+64U)>128U &&
      (*reinterpret_cast<volatile uint32_t*>(UINT32_C(0xD0000078))&2U)) return ln_main_raw(b);
#endif
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
  const U third=math62_third(cube);
  const uint32_t fourth=uint32_t(wide32(uint32_t(cube>>6),t)>>37);
  const uint32_t fifth=uint32_t(wide32(fourth,t)>>43);
  const U even=((z+1)>>1)+((fourth+2)>>2);
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=negative?U(0)-odd-even:odd-even;
  const Log70Center center=log70_center(index);
  U low=center.low;uint32_t high=center.high;
  if(negative) {const U old=low;low+=correction;high-=low>old;}
  else {const U old=low;low+=correction;high+=low<old;}
  if(!k) return ln_pack70(low,high,0,ln_main_radius,x);
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(log70_two_low),n),p1=wide32(uint32_t(log70_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log70_two_high*n;
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
  return ln_pack70(result,upper,k<0?D::Sign:0,ln_main_radius+(n+1)/2,x);
}
