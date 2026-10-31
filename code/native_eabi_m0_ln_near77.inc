// The near-one table keeps the reciprocal's known high byte implicit and
// uses that byte for seven additional logarithm bits, without table growth.
__attribute__((optimize("Os"),noinline)) static U ln_near_ratio77(U delta,uint32_t denominator) {
  uint32_t a=(uint32_t(delta>>36)<<16)|(uint32_t(delta>>20)&65535U);
  const uint32_t q1=mk61_m0_math_udiv32(a,denominator);
  uint32_t r=a-q1*denominator;
  a=(r<<16)|(uint32_t(delta>>4)&65535U);
  const uint32_t q2=mk61_m0_math_udiv32(a,denominator);r=a-q2*denominator;
  a=(r<<16)|((uint32_t(delta)&15U)<<12);
  const uint32_t q3=mk61_m0_math_udiv32(a,denominator);r=a-q3*denominator;
  a=r<<16;
  const uint32_t q4=mk61_m0_math_udiv32(a,denominator);r=a-q4*denominator;
  const U q=(U(q1)<<48)|(U(q2)<<32)|(q3<<16)|q4;
  return q+U(2*r>denominator || (2*r==denominator && (q&1)));
}
__attribute__((always_inline)) inline U ln_near_third77(U cube) {
  const uint32_t hi=uint32_t(cube>>32),lo=uint32_t(cube);
  const uint32_t qh=hi*171U>>9;
  const uint32_t ql=uint32_t(wide32(lo,0xAAAAAAABU)>>33);
  const uint32_t rh=hi-3*qh,tail=rh+lo-3*ql,carry=tail>=3;
  const U q=(U(qh)<<32)|uint32_t(ql+rh*0x55555555U+carry);
  return q+U(tail-3*carry>=2);
}
__attribute__((always_inline)) inline U ln_near_pack77(Refine96 q,U sign) {
  unsigned shift;uint32_t high=q.high;
  if(!high) shift=10+unsigned(q.low>>63);
  else {
    shift=12;
    if(high>=16) {high>>=4;shift+=4;}
    if(high>=4) {high>>=2;shift+=2;}
    if(high>=2) ++shift;
  }
  const uint32_t half=1U<<(shift-1),lo=uint32_t(q.low),hi=uint32_t(q.low>>32),tail=lo&((half<<1)-1);
  // The complete error is strictly below5 Q77 units. An integer
  // midpoint distance>=5 excludes it, hence reject only0..4.
  if(tail>=half?tail-half<=4:half-tail<=4) return 0;
  const U retained=(U((hi>>shift)|(q.high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  return sign+(U(shift+997)<<52)+retained+U(tail>half || (tail==half && (retained&1)));
}
__attribute__((optimize("Os"),noinline)) static double ln_near_interval(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  const unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return ln_near_one(x,b);
  if(negative && n==128) return ln_refine(x);
  const unsigned index=(negative?128-n:128+n)-1;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  const U* row=log_near_table[index];
  Refine96 value={row[1],uint32_t(row[0]>>56)};
  if(delta) {
    const U rounded=ln_near_ratio77(delta,8065+index);
    const U z=(exp_high_square(rounded)+(1U<<12))>>13;
    const uint32_t hr=uint32_t((rounded+(U(1)<<31))>>32);
    const uint32_t zr=uint32_t((z+(1U<<17))>>18);
    const U coarse=(wide32(hr,zr)+(1U<<26))>>27;
    const int32_t dh=int32_t(uint32_t(rounded)),dz=int32_t(uint32_t(z)-(zr<<18));
    const int32_t change1=((dh>>16)*int32_t(zr>>16)+(1<<26))>>27;
    const int32_t change2=((dz>>2)*int32_t(hr>>16)+(1<<26))>>27;
    const int64_t corrected=int64_t(coarse)+change1+change2;
    const U cube=corrected>0?U(corrected):0;
    const U third=ln_near_third77(cube);
    const uint32_t z16=uint32_t((z+(U(1)<<33))>>34);
    const uint32_t fourth=uint32_t((wide32(zr,zr)+(U(1)<<40))>>41);
    const uint32_t c16=uint32_t((cube+(1U<<19))>>20);
    const uint32_t fifth=(c16*z16+(1U<<22))>>23;
    const U odd=rounded+third+((fifth+2U)*205U>>10);
    const U even=((z+1)>>1)+((fourth+2)>>2);
    const U correction=subtract?odd+even:odd-even;
    value=subtract==negative?r96_add_low(value,correction):r96_sub_low(value,correction);
  }
  const U result=ln_near_pack77(value,negative?D::Sign:0);
  if(result) return real(result);
  return ln_refine(x);
}
