// Radix-2^16 estimates use four interrupt-safe 32-bit divisions in total.
// The final radix-2^32 corrections give the exact 64-bit quotient.
__attribute__((always_inline)) inline uint32_t atan_div64_32(U n,uint32_t d) {
  const uint32_t high=d>>16,low=d&65535U,a=uint32_t(n>>32),b=uint32_t(n);
  uint32_t q1=mk61_m0_math_udiv32(a,high),r=a-q1*high;
  while(q1>=65536U || q1*low>(r<<16)+(b>>16)) {
    --q1;r+=high;if(r>=65536U) break;
  }
  const uint32_t rest=(a<<16)+(b>>16)-q1*d;
  uint32_t q0=mk61_m0_math_udiv32(rest,high);r=rest-q0*high;
  while(q0>=65536U || q0*low>(r<<16)+(b&65535U)) {
    --q0;r+=high;if(r>=65536U) break;
  }
  return (q1<<16)|q0;
}
__attribute__((always_inline)) inline uint32_t atan_digit(U n,uint32_t next,uint32_t d,uint32_t low) {
  uint32_t q=uint32_t(n>>32)==d?UINT32_MAX:atan_div64_32(n,d);
  U r=n-wide32(q,d);
  while(!(r>>32) && wide32(q,low)>((r<<32)|next)) {--q;r+=d;}
  return q;
}
__attribute__((optimize("Os"),noinline)) static U atan_ratio_words(U numerator,U lower,U denominator) {
  const unsigned shift=clz64(denominator);
  const U d=denominator<<shift,n=shift?(numerator<<shift)|(lower>>(64-shift)):numerator;
  const U low_n=lower<<shift;
  const uint32_t high=uint32_t(d>>32),low=uint32_t(d);
  const uint32_t q1=atan_digit(n,uint32_t(low_n>>32),high,low);
  const U rest=((n<<32)|(low_n>>32))-low_product(q1,d);
  const uint32_t q0=atan_digit(rest,uint32_t(low_n),high,low);
  return (U(q1)<<32)|q0;
}
__attribute__((always_inline)) inline U atan_ratio(U numerator,U denominator) {return atan_ratio_words(numerator,0,denominator);}
__attribute__((optimize("Os"),noinline,cold)) static double atan_refine(double original,unsigned index) {
  const U b=bits(original),m=b&D::Magnitude,sign=b&D::Sign;
  if(m<UINT64_C(0x3F90000000000000)) return mk61_m0_cr_atan(original);
  const bool invert=m>UINT64_C(0x3FF0000000000000);
  const int e=int(m>>52)-1023;
  const U s=(m&D::Fraction)|D::Hidden;
  U numerator,denominator;bool negative=false;
  if(invert && !index) {
    numerator=U(1)<<unsigned(58-e);denominator=s;
  } else if(invert) {
    const U a=U(1)<<unsigned(58-e),c=low_product(s,index);
    negative=a<c;numerator=(negative?c-a:a-c)<<6;
    denominator=(s<<6)+(U(index)<<unsigned(52-e));
  } else {
    const U a=s<<6,c=U(index)<<unsigned(52-e);
    negative=a<c;const U n=negative?c-a:a-c;
    const U product=low_product(s,index);
    if(e==-6) {numerator=n<<5;denominator=(U(1)<<63)|(product>>1);}
    else {numerator=n<<6;denominator=(U(1)<<unsigned(58-e))+product;}
  }
  const U h=numerator?atan_ratio(numerator,denominator):0;
  // Leave room for the inline product's compensation before narrowing.
  if(h>(U(1)<<63)-8) return mk61_m0_cr_atan(original);
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
  if(invert) q=r96_sub({(U(refine_atan_half_pi[1])<<32)|refine_atan_half_pi[0],refine_atan_half_pi[2]},q);
  U result;
  // Ratio truncation (including the optional 65-bit denominator), series
  // products, reciprocal coefficients and the omitted r^11/11 fit 16 Q70.
  // The exact rational certificate is in certify_m0_atan_fast.py.
  if(r96_pack(q,24,sign,16,result)) return real(result);
  return mk61_m0_cr_atan(original);
}
