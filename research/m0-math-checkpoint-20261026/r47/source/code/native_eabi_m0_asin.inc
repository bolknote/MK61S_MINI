// Checked binary64 asin/acos for ARMv6-M. Exact dyadic unit-vector
// geometry avoids composing rounded double arithmetic. Taylor and table
// paths return only if their complete interval rounds to one binary64.
// tools/certify_m0_asin_fast.py proves the arithmetic/rounding bounds.
// Unresolved or guarded cases use the existing CORE-MATH functions.
// Exact normalized geometry primitive, X=x*2^63 in[2^57,2^63).
__attribute__((optimize("Os"),noinline,cold,section(".m0_asin_refine_extension"))) static U asin_root_normalized(U X,unsigned &scale) {
  const Product square=multiply(X,X);
  Product N={(U(1)<<62)-square.high-U(square.low!=0),U(0)-square.low};
  const unsigned width=128-clz64(N.high),shift=(126-width)&~1U;
  scale=shift/2;
  if(shift) N={(N.high<<shift)|(N.low>>(64-shift)),N.low<<shift};
  const unsigned normalized_width=width+shift;
  const unsigned reduction=normalized_width-117;
  const U top=N.high>>reduction;
  const uint32_t half=1U<<(reduction-1),tail=uint32_t(N.high)&((half<<1)-1);
  const U rounded=top+U(tail>half || (tail==half && (N.low || (top&1))));
  const U argument=(U(normalized_width+895)<<52)+rounded;
  const U seed=bits(mk61_m0_sqrt(real(argument)));
  const U g=seed==UINT64_C(0x3FF0000000000000)?U(1)<<63:((seed&D::Fraction)|D::Hidden)<<10;
  const Product seed_square=multiply(g,g);
  const bool below=seed_square.high<N.high || (seed_square.high==N.high && seed_square.low<N.low);
  const Product a=below?N:seed_square,sub=below?seed_square:N;
  const Product residual={a.high-sub.high-U(a.low<sub.low),a.low-sub.low};
  const uint32_t denominator=uint32_t(g>>47);
  const uint32_t numerator=uint32_t((residual.low>>48)|(residual.high<<16));
  const uint32_t correction=mk61_m0_math_udiv32(numerator,denominator);
  if(correction>=65536) return 0;
  U q=below?g+correction:g-correction;
  // q=g+-c. One 64x16 product and c*c replace the full second square.
  const uint32_t g0=uint32_t(g)&65535U,g1=uint32_t(g)>>16;
  const uint32_t g2=uint32_t(g>>32)&65535U,g3=uint32_t(g>>48);
  const uint32_t p0=g0*correction,p1=g1*correction+(p0>>16);
  const uint32_t p2=g2*correction+(p1>>16),p3=g3*correction+(p2>>16);
  const U gl=(U((p3<<16)|(p2&65535U))<<32)|uint32_t((p1<<16)|(p0&65535U));
  const U delta_low=gl<<1,delta_high=(U(p3>>16)<<1)|(gl>>63);
  Product square_q;
  if(below) {
    const U low=seed_square.low+delta_low;
    square_q={seed_square.high+delta_high+U(low<seed_square.low),low};
  } else square_q={seed_square.high-delta_high-U(seed_square.low<delta_low),seed_square.low-delta_low};
  const uint32_t c2=correction*correction;const U before=square_q.low;
  square_q.low+=c2;square_q.high+=square_q.low<before;
  for(unsigned tries=0;tries<3;++tries) {
    if(square_q.high>N.high || (square_q.high==N.high && square_q.low>N.low)) {
      const U step=(q<<1)-1,old=square_q.low;
      square_q.low-=step;square_q.high-=old<step;--q;
      continue;
    }
    const U step=(q<<1)+1,low=square_q.low+step;
    const Product next={square_q.high+U(low<square_q.low),low};
    if(next.high<N.high || (next.high==N.high && next.low<=N.low)) {
      square_q=next;++q;continue;
    }
    return q;
  }
  return 0;
}

// The first tier needs only a certified two-unit Q63 root enclosure.
// Exact floor-root correction remains in the rare independent refinement.
__attribute__((optimize("Os"),noinline,section(".m0_asin_extension"))) static U asin_root_estimate(U X,unsigned &scale) {
  const Product square=multiply(X,X);
  Product N={(U(1)<<62)-square.high-U(square.low!=0),U(0)-square.low};
  const unsigned width=128-clz64(N.high),shift=(126-width)&~1U;
  scale=shift/2;
  if(shift) N={(N.high<<shift)|(N.low>>(64-shift)),N.low<<shift};
  const unsigned normalized_width=width+shift;
  const unsigned reduction=normalized_width-117;
  const U top=N.high>>reduction;
  const uint32_t half=1U<<(reduction-1),tail=uint32_t(N.high)&((half<<1)-1);
  const U rounded=top+U(tail>half || (tail==half && (N.low || (top&1))));
  const U argument=(U(normalized_width+895)<<52)+rounded;
  const U seed=bits(mk61_m0_sqrt(real(argument)));
  const U g=seed==UINT64_C(0x3FF0000000000000)?U(1)<<63:((seed&D::Fraction)|D::Hidden)<<10;
  const Product seed_square=multiply(g,g);
  const bool below=seed_square.high<N.high || (seed_square.high==N.high && seed_square.low<N.low);
  const Product a=below?N:seed_square,sub=below?seed_square:N;
  const Product residual={a.high-sub.high-U(a.low<sub.low),a.low-sub.low};
  const uint32_t denominator=uint32_t(g>>47);
  const uint32_t numerator=uint32_t((residual.low>>48)|(residual.high<<16));
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Nearest integer quotient reduces the normalized root error below one.
  const uint32_t correction=mk61_m0_math_udiv32(numerator+(denominator>>1),denominator);
#else
  const uint32_t correction=mk61_m0_math_udiv32(numerator,denominator);
#endif
  if(correction>=65536) return 0;
  U q=below?g+correction:g-correction;
  return q;
}

#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Geometry has0<=scale<=26. Half-up is sufficient for this enclosure;
// the final binary64 packer still performs nearest-even rounding.
__attribute__((always_inline)) inline U asin_root_shift(U root,unsigned scale) {
  if(!scale) return root;
  const uint32_t lo=uint32_t(root),hi=uint32_t(root>>32);
  const U q=(U(hi>>scale)<<32)|((lo>>scale)|(hi<<(32-scale)));
  return q+((lo>>(scale-1))&1U);
}
#endif

// All unresolved cells retain the CORE-MATH fallback.
__attribute__((always_inline)) inline Refine96 asin_half_pi() {
  return {(U(refine_atan_half_pi[1])<<32)|refine_atan_half_pi[0],refine_atan_half_pi[2]};
}
__attribute__((always_inline)) inline Refine96 asin_q70(U q,int e) {
  const int shift=e+7;
  if(shift>0) return {q<<unsigned(shift),uint32_t(q>>unsigned(64-shift))};
  if(!shift) return {q,0};
  return {math62_right(q,unsigned(-shift)),0};
}
// Final absolute angles are in[2^-7,pi]; the low-only case has width64.
__attribute__((always_inline)) inline bool asin_pack_q70(Refine96 a,U sign,unsigned error,U &result) {
  unsigned shift,bias;
  if(a.high) {const unsigned width=32-clz32(a.high);shift=width+11;bias=width+1015;}
  else {if(a.low<(U(1)<<63)) return false;shift=11;bias=1015;}
  const uint32_t lo=uint32_t(a.low),hi=uint32_t(a.low>>32);
  const uint32_t half=1U<<(shift-1),tail=lo&((half<<1)-1);
  if(uint32_t(tail-(half-error))<=2*error) return false;
  const U retained=(U((hi>>shift)|(a.high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U rounded=retained+U(tail>half || (tail==half && (retained&1)));
  result=sign+(U(bias)<<52)+rounded;return true;
}
__attribute__((optimize("Os"),noinline,section(".m0_asin_extension"))) static U asin_small(U m,int &e) {
  e=int(m>>52)-1022;
  const U q=((m&D::Fraction)|D::Hidden)<<10,z=math62_square(q,e);
  const U z2=math62_product(z,z),z3=math62_product(z2,z),z4=math62_product(z3,z);
  const U factor=(U(1)<<62)+math62_product(z,UINT64_C(768614336404564651))+
    math62_product(z2,UINT64_C(345876451382054093))+
    math62_product(z3,UINT64_C(205878840108365531))+
    math62_product(z4,UINT64_C(140111988407082098));
  return math62_product(q,factor);
}
__attribute__((optimize("Os"),noinline,section(".m0_asin_extension"))) static U asin_atan_small(U root,U X,unsigned scale,int &e) {
  U q=atan_ratio(root>>1,X);e=-int(scale);
  if(q>=(U(1)<<63)) {q>>=1;++e;}
  if(e>-6) return 0;
  const U z=math62_square(q,e),z2=math62_product(z,z),z3=math62_product(z2,z),z4=math62_product(z3,z);
  const uint32_t a=uint32_t(z3),b=uint32_t(z4);
  uint32_t seventh=uint32_t(wide32(a,2454267027U)>>34);
  seventh+=a-7*seventh>=4;
  uint32_t ninth=uint32_t(wide32(b,954437177U)>>33);
  ninth+=b-9*ninth>=5;
  const U factor=(U(1)<<62)-math62_third(z)+math62_product(z2,UINT64_C(922337203685477581))-seventh+ninth;
  return math62_product(q,factor);
}
__attribute__((optimize("Os"),noinline,section(".m0_asin_extension"))) static bool asin_geometry(U X,U Y,Refine96 &angle) {
  const bool invert=X>Y;
  const U n=invert?Y:X,d=invert?X:Y;
  const uint32_t seed=mk61_m0_math_udiv32(uint32_t(n>>31),uint32_t(d>>47));
  const unsigned index=(seed+512)>>10;
  if(index>64) return false;
  // The top-word index differs from round(64*n/d) by at most one;
  // |64*n-index*d|<2^63, so its sign and magnitude survive modulo 2^64.
  const uint32_t dlo=uint32_t(d),dhi=uint32_t(d>>32);
  const uint32_t d0=(dlo&65535U)*index,d1=(dlo>>16)*index+(d0>>16);
  const U product=(U(dhi*index+(d1>>16))<<32)|uint32_t((d1<<16)|(d0&65535U));
  const U difference=(n<<6)-product;
  const bool negative=bool(difference>>63);
  const U residual=negative?U(0)-difference:difference;
  const uint32_t nlo=uint32_t(n),nhi=uint32_t(n>>32);
  const uint32_t n0=(nlo&65535U)*index,n1=(nlo>>16)*index+(n0>>16);
  const uint32_t n2=(nhi&65535U)*index+(n1>>16),n3=(nhi>>16)*index+(n2>>16);
  const U term=(U((n3<<16)|(n2&65535U))<<32)|uint32_t((n1<<16)|(n0&65535U));
  const U dd=d>>1;
  const U denominator=dd+((U(n3>>16)<<57)|(term>>7))+U((d&1) && ((term&127)>=64));
  const U nn=residual>>1;
  if(nn>=(denominator>>1)) return false;
  const U h=nn?atan_fast_ratio(nn,denominator):0;
  if(h>(U(1)<<63)-(U(1)<<48)) return false;
  const U z=math62_right(exp_high_square(h),6);
  const U c3=math62_right(exp_high_product(h,z),6);
  const U c5=(wide32(uint32_t(c3>>17),uint32_t(z>>24))+(U(1)<<28))>>29;
  const uint32_t c7=uint32_t((wide32(uint32_t(c5>>3),uint32_t(z>>24))+(U(1)<<42))>>43);
  const U third=math62_third(c3);
  const U fifth=(wide32(uint32_t(c5>>3),0xCCCCCCCDU)+(U(1)<<30))>>31;
  const U seventh=wide32(c7+3,2454267027U)>>34;
  const U reduction=third-fifth+seventh;
  if(reduction>h) return false;
  const U correction=h-reduction;
  const uint32_t* row=refine_atan_table[index];
  Refine96 q={(U(row[1])<<32)|row[0],row[2]};
  q=negative?r96_sub_low(q,correction):r96_add_low(q,correction);
  angle=invert?r96_sub(asin_half_pi(),q):q;
  return true;
}
__attribute__((optimize("Os"),noinline,cold,section(".m0_asin_refine_extension"))) static bool asin_geometry_refined(U X,U Y,Refine96 &angle) {
  const bool invert=X>Y;
  const U n=invert?Y:X,d=invert?X:Y;
  const uint32_t seed=mk61_m0_math_udiv32(uint32_t(n>>31),uint32_t(d>>47));
  const unsigned index=(seed+512)>>10;
  if(index>64) return false;
  // The top-word index differs from round(64*n/d) by at most one;
  // |64*n-index*d|<2^63, so its sign and magnitude survive modulo 2^64.
  const uint32_t dlo=uint32_t(d),dhi=uint32_t(d>>32);
  const uint32_t d0=(dlo&65535U)*index,d1=(dlo>>16)*index+(d0>>16);
  const U product=(U(dhi*index+(d1>>16))<<32)|uint32_t((d1<<16)|(d0&65535U));
  const U difference=(n<<6)-product;
  const bool negative=bool(difference>>63);
  const U residual=negative?U(0)-difference:difference;
  const uint32_t nlo=uint32_t(n),nhi=uint32_t(n>>32);
  const uint32_t n0=(nlo&65535U)*index,n1=(nlo>>16)*index+(n0>>16);
  const uint32_t n2=(nhi&65535U)*index+(n1>>16),n3=(nhi>>16)*index+(n2>>16);
  const U term=(U((n3<<16)|(n2&65535U))<<32)|uint32_t((n1<<16)|(n0&65535U));
  const U dd=d>>1;
  const U denominator=dd+((U(n3>>16)<<57)|(term>>7))+U((d&1) && ((term&127)>=64));
  const U nn=residual>>1;
  if(nn>=(denominator>>1)) return false;
  const U h=nn?atan_ratio(nn,denominator):0;
  if(h>(U(1)<<63)-8) return false;
  const U z=math62_right(math62_product(h,h),8);
  const U c3=math62_right(math62_product(h,z),8),c5=math62_right(math62_product(c3,z),8);
  const U c7=math62_right(math62_product(c5,z),8),c9=math62_right(math62_product(c7,z),8);
  const U reduction=exp_high_product(c3,UINT64_C(6148914691236517206))-
    exp_high_product(c5,UINT64_C(3689348814741910324))+
    U(uint32_t(wide32(uint32_t(c7)+3,2454267027U)>>34))-
    U(((uint32_t(c9)+4)*7282U)>>16);
  const U correction=h-reduction;
  const uint32_t* row=refine_atan_table[index];
  Refine96 q={(U(row[1])<<32)|row[0],row[2]};
  q=negative?r96_sub_low(q,correction):r96_add_low(q,correction);
  const U root_residual=U(0)-low_product(X,X)-low_product(Y,Y);
  const unsigned root_shift=48-clz64(Y);
  const uint32_t root_denominator=uint32_t(Y>>root_shift);
  const uint32_t root_numerator=uint32_t(root_residual>>(root_shift-15));
  const uint32_t fraction15=mk61_m0_math_udiv32(root_numerator,root_denominator);
  const U root_correction=math62_right(wide32(uint32_t(X>>47),fraction15),25);
  angle=r96_sub_low(invert?r96_sub(asin_half_pi(),q):q,root_correction);
  return true;
}
__attribute__((optimize("Os"),noinline,cold,section(".m0_asin_refine_extension"))) static double asin_refine(double original,bool cosine) {
  const U b=bits(original),m=b&D::Magnitude,sign=b&D::Sign;
  if(m<UINT64_C(0x3F90000000000000) || m>=UINT64_C(0x3FF0000000000000))
    return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
  const int e=int(m>>52)-1023;
  const U X=((m&D::Fraction)|D::Hidden)<<unsigned(e+11);
  unsigned scale;const U root=asin_root_normalized(X,scale),Y=root>>scale;
  if(!root || Y<X>>6) return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
  Refine96 angle;
  if(!asin_geometry_refined(X,Y,angle)) return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
  if(cosine) angle=sign?r96_add(asin_half_pi(),angle):r96_sub(asin_half_pi(),angle);
  U result;if(asin_pack_q70(angle,cosine?0:sign,32,result)) return real(result);
  return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
}
__attribute__((optimize("Os"),noinline,section(".m0_asin_extension"))) static double asin_checked(double original,bool cosine) {
  const U b=bits(original),m=b&D::Magnitude,sign=b&D::Sign;
  if(m==UINT64_C(0x3FF0000000000000)) return real(cosine?(sign?UINT64_C(0x400921FB54442D18):0):(sign|UINT64_C(0x3FF921FB54442D18)));
  if(m>UINT64_C(0x3FF0000000000000)) return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
  if(!cosine && m<UINT64_C(0x3E40000000000000)) return original;
  if(cosine && m<UINT64_C(0x3C70000000000000)) return real(UINT64_C(0x3FF921FB54442D18));
  U result;Refine96 angle;unsigned error=128;
  if(m<UINT64_C(0x3F90000000000000)) {
    int e;const U q=asin_small(m,e);
    if(!cosine) {
      if(atan_pack(q,e,sign,32,result)) return real(result);
      return mk61_m0_cr_asin(original);
    }
    angle=asin_q70(q,e);error=128;
  } else {
    const int e=int(m>>52)-1023;
    const U X=((m&D::Fraction)|D::Hidden)<<unsigned(e+11);
    unsigned scale;const U root=asin_root_estimate(X,scale);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    const U Y=asin_root_shift(root,scale);
#else
    const U Y=root>>scale;
#endif
    if(Y<X>>6) {
      int exponent;const U small=asin_atan_small(root,X,scale,exponent);
      if(!small) return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
      if(cosine && !sign) {
        if(atan_pack(small,exponent,0,24,result)) return real(result);
        return mk61_m0_cr_acos(original);
      }
      angle=r96_sub(asin_half_pi(),asin_q70(small,exponent));
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      // The relative error is <24 Q63 units. At exponent<=-13,
      // converting to Q70 and folding at most two half-pi constants
      // costs <24/64+1/2+1=1.875 units, so radius2 is sufficient.
      error=exponent<=-13?2U:128U;
#else
      error=128;
#endif
    } else {
      if(!asin_geometry(X,Y,angle)) return cosine?mk61_m0_cr_acos(original):mk61_m0_cr_asin(original);
      const unsigned bias=unsigned(X>>57)+1;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      error=63+2*bias;
#else
      error=63+4*bias;
#endif
    }
  }
  if(cosine) angle=sign?r96_add(asin_half_pi(),angle):r96_sub(asin_half_pi(),angle);
  if(asin_pack_q70(angle,cosine?0:sign,error,result)) return real(result);
  return asin_refine(original,cosine);
}
__attribute__((optimize("Os"),section(".m0_asin_extension"))) MK61_SOFT_PCS double mk61_m0_asin(double x) {return asin_checked(x,false);}
__attribute__((optimize("Os"),section(".m0_asin_extension"))) MK61_SOFT_PCS double mk61_m0_acos(double x) {return asin_checked(x,true);}
