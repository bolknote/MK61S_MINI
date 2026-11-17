// The fast atan domain yields 2^58 <= denominator < 2^64. Only residual
// bits40..71 are needed for its short correction, as in Qfplib's narrow
// residual division. Recover those bits modulo2^32 instead of forming
// the full128-bit product. The signed head is ceil(residual/2^40).
// Its quotient error stays below1+35/2^18; no iterative correction.
__attribute__((optimize("Os"),noinline,cold))
static int32_t atan_ratio_adjust(U numerator,U denominator,U estimate) {
  const uint32_t al=uint32_t(estimate),ah=uint32_t(estimate>>32);
  const uint32_t bl=uint32_t(denominator),bh=uint32_t(denominator>>32);
  const U low=wide32(al,bl);
  const U middle=wide32(ah,bl)+(low>>32)+wide32(al,bh)+(U(ah*bh)<<32);
  const int32_t residual=int32_t((uint32_t(numerator)<<24)-uint32_t(middle>>8));
  return mk61_m0_math_sdiv32(residual,int32_t(denominator>>40));
}

__attribute__((optimize("Os"),noinline,cold))
static int32_t atan_round_correct(U numerator,U denominator,U estimate,U z,uint32_t seventh) {
  const int32_t change=atan_ratio_adjust(numerator,denominator,estimate);
  // Reuse the seventh-degree polynomial; changing its linear term
  // perturbs the nonlinear part by <35/16384 Q70 units.
  const uint32_t ninth=uint32_t((wide32(seventh,uint32_t(z>>24))+(U(1)<<45))>>46);
  const uint32_t term=((ninth+4U)*7282U)>>16;
  return change+int32_t(term);
}

// atan's Q70 magnitude is in [atan(1/64),atan(64)]. Its binary64
// right shift is 11..17. The full enclosure is <54 Q70.
__attribute__((always_inline)) inline U atan_pack70(Refine96 q,U sign,U numerator,U denominator,
                                                  U estimate,U z,uint32_t seventh,bool subtract) {
  unsigned shift=q.high?12:11;uint32_t high=q.high;
  if(high>=16) {high>>=4;shift+=4;}
  if(high>=4) {high>>=2;shift+=2;}
  if(high>=2) ++shift;
  const uint32_t half=1U<<(shift-1),lo=uint32_t(q.low),hi=uint32_t(q.low>>32),tail=lo&((half<<1)-1);
  int32_t distance=int32_t(tail)-int32_t(half);
  if(uint32_t(distance+53)<=106) {
    const int32_t delta=atan_round_correct(numerator,denominator,estimate,z,seventh);
    distance+=subtract?-delta:delta;
    // The corrected value can reuse the lower endpoint while it stays
    // in this cell. Its certified error is <11 Q70.
    if(uint32_t(distance+int32_t(half))>=(half<<1) || uint32_t(distance+10)<=20)
      return 0;
  }
  const U retained=(U((hi>>shift)|(q.high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  return sign+(U(shift+1004)<<52)+retained+U(distance>0);
}
