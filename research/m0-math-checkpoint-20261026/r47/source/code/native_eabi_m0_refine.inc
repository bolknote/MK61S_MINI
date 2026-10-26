// Independent fixed-point interval refinement. Coefficients are exact Taylor
// reciprocals. This middle pass avoids software-FMA work for common ambiguous
// Q62 results; only its own undecided rounding cells reach CORE-MATH.
struct Refine96 {U low;uint32_t high;};
__attribute__((always_inline)) inline Refine96 r96_add(Refine96 a,Refine96 b) {
  const U low=a.low+b.low;return {low,a.high+b.high+uint32_t(low<a.low)};
}
__attribute__((always_inline)) inline Refine96 r96_sub(Refine96 a,Refine96 b) {
  return {a.low-b.low,a.high-b.high-uint32_t(a.low<b.low)};
}
__attribute__((always_inline)) inline Refine96 r96_add_low(Refine96 a,U b) {return r96_add(a,{b,0});}
__attribute__((always_inline)) inline Refine96 r96_sub_low(Refine96 a,U b) {return r96_sub(a,{b,0});}
__attribute__((always_inline)) inline Refine96 r96_half(Refine96 a) {return {(a.low>>1)|(U(a.high)<<63),a.high>>1};}
__attribute__((always_inline)) inline Refine96 r96_square64(U a) {
  const Product p=multiply(a,a);
  return {(p.low>>34)|(p.high<<30),uint32_t(p.high>>34)};
}
__attribute__((always_inline)) inline U r96_times64(Refine96 a,U b) {
  return exp_high_product(a.low,b)+low_product(a.high,b);
}
__attribute__((always_inline)) inline Refine96 r96_product(Refine96 a,Refine96 b) {
  const Product p=multiply(a.low,b.low);
  const U v0=wide32(uint32_t(a.low),b.high),v1=wide32(uint32_t(a.low>>32),b.high)+(v0>>32);
  const U w0=wide32(uint32_t(b.low),a.high),w1=wide32(uint32_t(b.low>>32),a.high)+(w0>>32);
  const U v=(v1<<32)|uint32_t(v0),w=(w1<<32)|uint32_t(w0);
  const U s=p.high+v,t=s+w;
  const U h=wide32(a.high,b.high)+(v1>>32)+(w1>>32)+U(s<p.high)+U(t<s);
  return {(t>>30)|(h<<34),uint32_t(h>>30)};
}
__attribute__((always_inline)) inline bool r128_pack(Product a,int scale,U sign,uint32_t error,U &out) {
  if(!a.high) {
    if(!a.low) return false;
    const unsigned width=64-clz64(a.low);
    if(width<=53) return false;
    const unsigned shift=width-53;const U half=U(1)<<(shift-1),tail=a.low&((half<<1)-1);
    if(tail>=half?tail-half<=error:half-tail<=error) return false;
    const int exponent=int(width)-95+scale;
    if(exponent < -1022 || exponent > 1023) return false;
    const U q=(a.low>>shift)+U(tail>half || (tail==half && ((a.low>>shift)&1)));
    out=sign+(U(exponent+1022)<<52)+q;return true;
  }
  const unsigned width=64-clz64(a.high),shift=width+11;
  if(shift>=64) return false;
  const int exponent=int(width)-31+scale;
  if(exponent < -1022 || exponent > 1023) return false;
  const U half=U(1)<<(shift-1),tail=a.low&((half<<1)-1);
  if(tail>=half?tail-half<=error:half-tail<=error) return false;
  U q=(a.low>>shift)|(U(a.high)<<(64-shift));
  q+=tail>half || (tail==half && (q&1));
  out=sign+(U(exponent+1022)<<52)+q;
  return true;
}
__attribute__((always_inline)) inline bool r96_pack(Refine96 a,int scale,U sign,uint32_t error,U &out) {
  return r128_pack({a.high,a.low},scale,sign,error,out);
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
__attribute__((used,noipa))
#endif
MK61_M0_EXP_CORE __attribute__((optimize("Os"),noinline,cold)) static double exp_refine(double x,uint32_t n) {
  const U b=bits(x),m=b&D::Magnitude,s=(m&D::Fraction)|D::Hidden;
  const int e=int(m>>52)-1023,shift=e+60;
  // x*2^112 is exact throughout the caller's finite, non-tiny domain.
  U low=shift>=64?0:s<<unsigned(shift);
  U high=shift>=64?s<<unsigned(shift-64):s>>unsigned(64-shift);
  const U p0=wide32(uint32_t(refine_exp_step[0]),n);
  const U p1=wide32(uint32_t(refine_exp_step[0]>>32),n)+(p0>>32);
  const U p2=wide32(uint32_t(refine_exp_step[1]),n)+(p1>>32);
  const uint32_t p3=uint32_t(refine_exp_step[1]>>32)*n+uint32_t(p2>>32);
  const U pl=(p1<<32)|uint32_t(p0),ph=(U(p3)<<32)|uint32_t(p2);
  const U old=low;low-=pl;high-=ph+U(old<pl);
  bool negative=bool(high>>63);
  if(negative) {low=U(0)-low;high=~high+U(!low);}
  if(high>UINT64_C(197032483697)) return mk61_m0_cr_exp(x); // |r| < 0.0007
  negative^=bool(b&D::Sign);
  const Refine96 r={(low>>18)|(high<<46),uint32_t(high>>18)};
  const U h=(high<<16)|(low>>48);
  const U h64=h+U((low&((U(1)<<48)-1))>(U(1)<<47));
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
  const int signed_n=b&D::Sign?-int(n):int(n);
  const unsigned index=unsigned(signed_n)&511;
  const uint32_t* row=refine_exp_table[index];
  q=r96_product(q,{(U(row[1])<<32)|row[0],row[2]});
  U result;
  // Rounded h64 perturbs the square by <2^20 Q94 units. All subsequent
  // products, Taylor omissions, table/reduction roundings fit below 2^22.
  if(r96_pack(q,(signed_n-int(index))/512,0,1U<<22,result)) return real(result);
  return mk61_m0_cr_exp(x);
}

__attribute__((optimize("Os"),noinline,cold)) static double ln_refine(double x) {
  const U b=bits(x);const int k=int((b>>52)&0x7FFU)-1023;
  // Cancellation at x=1 needs relative precision. x-1 is an exact dyadic,
  // so f64 below is exact even for the adjacent binary64 values to 1.
  if(b>=UINT64_C(0x3FEFFFE000000000) && b<=UINT64_C(0x3FF0001000000000)) {
    const bool negative=b<UINT64_C(0x3FF0000000000000);
    const U s=(b&D::Fraction)|D::Hidden;
    const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
    if(!a) return 0.;
    const unsigned leading=clz64(a);const U normalized=a<<(leading-1);
    int scale=1-int(leading);
    if(a<=(U(1)<<26)) {
      // a has >=9 trailing zeros. The exact quadratic numerator is on a
      // grid of 2^(clz(a)+17), at least 2^54 units. Its positive remaining
      // series is <2^53 units for |f|<=2^-36. Only an exact midpoint can be
      // crossed, and that midpoint always rounds upward in magnitude.
      const Product p=multiply(normalized,a);
      Product n={normalized>>1,normalized<<63};
      if(negative) {const U low=n.low+p.low;n.high+=p.high+U(low<n.low);n.low=low;}
      else {const U low=n.low-p.low;n.high-=p.high+U(n.low<p.low);n.low=low;}
      {
        const unsigned shift=(n.high&(U(1)<<61))?9:8;
        if(shift==8) --scale;
        const unsigned tail=unsigned(n.high)&((1U<<shift)-1),half=1U<<(shift-1);
        const U q=(n.high>>shift)+U(tail>=half);
        return real((negative?D::Sign:0)+(U(scale+1022)<<52)+q);
      }
    }
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
    U result;
    // |f|<=2^-16: the omitted relative f^5/6 term is <5462 Q94
    // units after normalization; all integer truncations fit below 8192.
    const unsigned top=63-leading;
    const int omitted_shift=5*int(top+1)-216;
    const uint32_t error=32+(omitted_shift>0?((1U<<unsigned(omitted_shift))+2)/3:1);
    if(r96_pack(q,scale,negative?D::Sign:0,error,result)) return real(result);
    return mk61_m0_cr_ln(x);
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
    U result;if(r96_pack(q,0,0,128,result)) return real(result);
  } else {
    const uint32_t n=uint16_t(k<0?-k:k);
    const U p0=wide32(uint32_t(refine_log_two_low),n),p1=wide32(uint32_t(refine_log_two_low>>32),n)+(p0>>32);
    Product t={U(refine_log_two_high)*n+(p1>>32),(p1<<32)|uint32_t(p0)};
    const U old=t.low;
    if(k<0) {t.low-=q.low;t.high-=q.high+U(old<q.low);}
    else {t.low+=q.low;t.high+=q.high+U(t.low<old);}
    // certify_m0_ln_refine.py includes every product/series rounding and
    // adds the separately rounded n*ln(2) contribution.
    U result;if(r128_pack(t,0,k<0?D::Sign:0,128+(n+1)/2,result)) return real(result);
  }
  return mk61_m0_cr_ln(x);
}
