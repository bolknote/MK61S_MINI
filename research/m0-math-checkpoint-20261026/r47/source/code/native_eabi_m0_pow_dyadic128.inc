// Compare the same normalized enclosures through references and scalar locals.
__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_near_one_refine")))
static int pow_dyadic128_compare(const PowInteger128 &a,const PowInteger128 &b) {
  const int distance=a.exponent-b.exponent;
  if(distance>=2) return 1;
  if(distance<=-2) return -1;
  U ah=a.high,al=a.low,bh=b.high,bl=b.low;
  unsigned ae=a.error,be=b.error;
  if(distance<0) {
    al=(al>>1)|(ah<<63);ah>>=1;ae=(ae>>1)+1;
  } else if(distance>0) {
    bl=(bl>>1)|(bh<<63);bh>>=1;be=(be>>1)+1;
  }
  if(ah==bh && uint32_t(al>>32)==uint32_t(bl>>32)) {
    const uint32_t left=uint32_t(al),right=uint32_t(bl),error=ae+be;
    if(left>=right) return left-right>error?1:0;
    return right-left>error?-1:0;
  }
  if(ah==bh && al==bl) return 0;
  const bool smaller=ah<bh || (ah==bh && al<bl);
  const U hi=smaller?bh:ah,lo=smaller?bl:al;
  const U other_hi=smaller?ah:bh,other_lo=smaller?al:bl;
  const U low=lo-other_lo,high=hi-other_hi-U(lo<other_lo);
  if(high || low>U(ae+be)) return smaller?-1:1;
  return 0;
}

__attribute__((always_inline)) inline void pow_dyadic128_raise(PowInteger128 &q,unsigned n) {
  if(n==1) return;
  const PowInteger128 base=q;
  unsigned bit=31-clz32(n);
  while(bit) {
    --bit;
    pow_integer128_square(q);
    if(n&(1U<<bit)) pow_integer128_multiply(q,base);
  }
}

// Sign of x^(+/-p/q)-midpoint. Every result is certified by integer
// power enclosures; the seed has no authority over rounding acceptance.
__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_near_one_refine")))
static int pow_dyadic128_boundary(const PowInteger128 &power,unsigned denominator,bool inverse,U cell) {
  if(cell<UINT64_C(0x0010000000000000) || cell>=UINT64_C(0x7FEFFFFFFFFFFFFF)) return 0;
  const U coefficient=(((cell&D::Fraction)|D::Hidden)<<1)+1;
  PowInteger128 midpoint={coefficient<<10,0,int(cell>>52)-1023,0};
  // The decoder supplies1,2,4,...,128. This is the identical square
  // chain, without a base copy, CLZ or generic numerator bit tests.
  for(unsigned n=denominator;n>1;n>>=1) pow_integer128_square(midpoint);
  if(!inverse) return pow_dyadic128_compare(power,midpoint);
  pow_integer128_multiply(midpoint,power);
  if(midpoint.exponent>0) return -1;
  if(midpoint.exponent < -1) return 1;
  if(!midpoint.exponent) {
    if(midpoint.high>(U(1)<<63) || midpoint.low>midpoint.error) return -1;
    return 0;
  }
  if(midpoint.high!=UINT64_MAX || midpoint.low<U(0)-U(midpoint.error)) return 1;
  return 0;
}

__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_near_one_refine")))
static U pow_dyadic128_checked(U xb,U yb,U hint,bool first_cell) {
  const U undecided=D::Infinity|D::Quiet,ym=yb&D::Magnitude;
  if(uint32_t(yb) || !ym || ym>=D::Infinity || xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity ||
     hint<=UINT64_C(0x0010000000000001) || hint>=UINT64_C(0x7FEFFFFFFFFFFFFE)) return undecided;
  U coefficient=(ym&D::Fraction)|D::Hidden;
  const unsigned zeros=63-clz64(coefficient&(U(0)-coefficient));
  coefficient>>=zeros;
  const int shift=int(ym>>52)-1075+int(zeros);
  if(coefficient>32 || shift < -7 || shift>5) return undecided;
  unsigned numerator=unsigned(coefficient),denominator=1;
  if(shift>=0) {
    numerator<<=unsigned(shift);
    if(numerator>32) return undecided;
  } else denominator=1U<<unsigned(-shift);
  if(numerator==3 && denominator==2 && !(yb&D::Sign)) {
    // When sqrt(x) is exactly dyadic, x*sqrt(x) needs only one final
    // binary64 rounding, including an exact midpoint tie. Certify the
    // proposed root by its exact106-bit square, not a rounded double test.
    const U root=bits(mk61_m0_sqrt(real(xb)));
    if(root>=UINT64_C(0x0010000000000000) && root<D::Infinity) {
      PowInteger128 square={((root&D::Fraction)|D::Hidden)<<11,0,int(root>>52)-1023,0};
      pow_integer128_square(square);
      if(!square.error && !square.low && square.high==(((xb&D::Fraction)|D::Hidden)<<11) &&
         square.exponent==int(xb>>52)-1023) return bits(real(xb)*real(root));
    }
  }
  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};
  pow_dyadic128_raise(power,numerator);
  const bool inverse=bool(yb&D::Sign);
  const int side=pow_dyadic128_boundary(power,denominator,inverse,hint);
  if(!side) return undecided;
  if(first_cell) return side>0?hint+1:hint;
  if(side>0) {
    return pow_dyadic128_boundary(power,denominator,inverse,hint+1)<0?hint+1:undecided;
  }
  const int previous=pow_dyadic128_boundary(power,denominator,inverse,hint-1);
  if(previous>0) return hint;
  if(previous<0 && pow_dyadic128_boundary(power,denominator,inverse,hint-2)>0) return hint-1;
  return undecided;
}

// This entry retains its original untrusted-hint contract. Only the separate
// first-cell caller may use the first-tier two-cell enclosure.
__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_near_one_refine")))
static U pow_dyadic128(U xb,U yb,U hint) {
  return pow_dyadic128_checked(xb,yb,hint,false);
}
