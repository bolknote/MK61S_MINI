__attribute__((always_inline)) inline Trig192 checked_trig_input191(U m) {
  const U s=(m&D::Fraction)|D::Hidden;const int shift=int(m>>52)-1023+139;
  if(shift>=128) return {0,0,s<<unsigned(shift-128)};
  return {0,s<<unsigned(shift-64),s>>unsigned(128-shift)};
}
__attribute__((always_inline)) inline Refine96 checked_trig_relative94(Trig192 r,int &e) {
  U first,second,third;unsigned leading;
  if(r.high) {first=r.high;second=r.middle;third=r.low;leading=0;}
  else if(r.middle) {first=r.middle;second=r.low;third=0;leading=64;}
  else {first=r.low;second=third=0;leading=128;}
  if(!first) {e=-192;return {0,0};}
  const unsigned shift=clz64(first);leading+=shift;e=1-int(leading);
  const U high=shift?(first<<shift)|(second>>(64-shift)):first;
  const U low=shift?(second<<shift)|(third>>(64-shift)):second;
  return {(high<<30)|(low>>34),uint32_t(high>>34)};
}
__attribute__((always_inline)) inline Refine96 checked_trig_coefficient(unsigned op,unsigned i) {
  const uint32_t* p=trig94_coefficients[op][i];return {(U(p[1])<<32)|p[0],p[2]};
}
__attribute__((optimize("Os"),noinline,cold)) static void checked_trig_refine_values(Trig192 r,unsigned mask,Refine96* output,int* scales,uint32_t &error) {
  const Refine96 one={0,1U<<30};
  if(r.high<(U(1)<<57)) { // |r| < 1/64
    int e;const Refine96 relative=checked_trig_relative94(r,e);
    const U h64=(r.high<<1)|(r.middle>>63);
    const Refine96 z=r96_square64(h64);
    for(unsigned op=0;op<2;++op) {
      if(!(mask&(1U<<op))) continue;
      Refine96 factor;
      if(e<=-16) {
        if(op) factor=r96_sub(one,r96_half(z));
        else factor=r96_sub_low(one,exp_high_product(z.low,UINT64_C(3074457345618258603)));
      } else {
        // Below 2^-10 the omitted cosine term is <2^34/720 Q94;
        // the existing 2^26 enclosure also covers square truncation.
        const unsigned degree=e<=-10?1:3;
        Refine96 p=checked_trig_coefficient(op,degree);
        for(unsigned i=degree;i--;) p=r96_sub(checked_trig_coefficient(op,i),r96_product(z,p));
        factor=r96_sub(one,r96_product(z,p));
      }
      output[op]=op?factor:r96_product(relative,factor);scales[op]=op?0:e;
    }
    // Exact linear input; the rounded Q64 square contributes <2^25 Q94.
    // Polynomial omissions, pi/2 truncation and all integer roundings fit.
    error=1U<<26;return;
  }
  const Refine96 q={(r.middle>>33)|(r.high<<31),uint32_t(r.high>>33)};
  const unsigned j=unsigned((r.high+(U(1)<<52))>>53);
  const Refine96 center={0,j<<20};
  const bool negative=q.high<center.high;
  const Refine96 h=negative?r96_sub(center,q):r96_sub(q,center);
  const U h64=(U(h.high)<<34)|(h.low>>30);
  const Refine96 z=r96_square64(h64);
  const U c3=r96_times64(z,h64),c4=exp_high_product(c3,h64);
  const U c5=exp_high_product(c4,h64),c6=exp_high_product(c5,h64),c7=exp_high_product(c6,h64);
  const U odd=exp_high_product(c3,UINT64_C(3074457345618258603))-
    exp_high_product(c5,UINT64_C(153722867280912931))+
    exp_high_product(c7,UINT64_C(3660068268593166));
  const U even=exp_high_product(c4,UINT64_C(768614336404564651))-
    exp_high_product(c6,UINT64_C(25620477880152156));
  const Refine96 sh=r96_sub_low(h,odd),ch=r96_sub_low(r96_half(z),even);
  const uint32_t* row=trig94_table[j];
  const Refine96 s={(U(row[1])<<32)|row[0],row[2]},c={(U(row[4])<<32)|row[3],row[5]};
  if(mask&1) {
    const Refine96 base=r96_sub(s,r96_product(s,ch)),change=r96_product(c,sh);
    output[0]=negative?r96_sub(base,change):r96_add(base,change);scales[0]=0;
  }
  if(mask&2) {
    const Refine96 base=r96_sub(c,r96_product(c,ch)),change=r96_product(s,sh);
    output[1]=negative?r96_add(base,change):r96_sub(base,change);scales[1]=0;
  }
  error=1U<<22;
}
struct CheckedTrigNormalized {U q;int e;};
// Compare the unshortened Q94 ratio with its nearest binary64 midpoint.
// Keeping the discarded numerator/denominator limbs avoids a second
// rounding ambiguity in the 63-bit division, especially close to poles.
__attribute__((optimize("Os"),noinline,cold)) static bool checked_trig_ratio_midpoint(
    Refine96 numerator,Refine96 denominator,unsigned shift,U midpoint,
    uint32_t error,bool &above) {
  const Product p=multiply(denominator.low,midpoint);
  const Product c=multiply(denominator.high,midpoint);
  const U middle=p.high+c.low;
  const Trig192 product={p.low,middle,c.high+U(middle<p.high)};
  const Trig192 scaled={numerator.low<<shift,
    (numerator.low>>(64-shift))|(U(numerator.high)<<shift),U(numerator.high)>>(64-shift)};
  Trig192 residual=trig_difference(scaled,product);
  const bool negative=bool(residual.high>>63);
  if(negative) residual=trig_negate(residual);
  const Product tolerance=multiply(midpoint,error);
  const U extra=U(error)<<shift,low=tolerance.low+extra;
  const U high=tolerance.high+(U(error)>>(64-shift))+U(low<tolerance.low);
  if(!residual.high && (residual.middle<high || (residual.middle==high && residual.low<=low))) return false;
  above=!negative;return true;
}
__attribute__((always_inline)) inline CheckedTrigNormalized checked_trig_normalize94(Refine96 q,int scale) {
  const unsigned width=q.high?96-clz32(q.high):64-clz64(q.low),shift=width-63;
  const U significand=shift?(q.low>>shift)|(U(q.high)<<(64-shift)):q.low;
  return {significand,int(width)-94+scale};
}
__attribute__((optimize("Os"),noinline,cold)) static double checked_trig_backend(double x,unsigned op) {
  return op==0?mk61_m0_cr_sin(x):op==1?mk61_m0_cr_cos(x):mk61_m0_cr_tan(x);
}
__attribute__((optimize("Os"),noinline,cold)) static double checked_trig_refine(double x,unsigned op) {
  const U b=bits(x),m=b&D::Magnitude;uint32_t n=0;bool negative=false;
  Trig192 r;
  if(m<=UINT64_C(0x3FE921FB54442D18)) r=checked_trig_input191(m);
  else {r=trig_remainder(m,n,negative);if(!n) r=checked_trig_input191(m);}
  const unsigned selected=op==0?(n&1):op==1?((n&1)^1):0;
  Refine96 values[2];int scales[2];uint32_t error;
  checked_trig_refine_values(r,op==2?3:1U<<selected,values,scales,error);
  if(op!=2) {
    const unsigned flip=(op==0?((n>>1)&1)^unsigned(b>>63):((n+1)>>1)&1)^(selected?0:unsigned(negative));
    U result;
    if(r96_pack(values[selected],scales[selected],U(flip)<<63,error,result)) return real(result);
  } else {
    CheckedTrigNormalized numerator=checked_trig_normalize94(values[n&1],scales[n&1]);
    CheckedTrigNormalized denominator=checked_trig_normalize94(values[(n&1)^1],scales[(n&1)^1]);
    const bool upper=numerator.q>=denominator.q;
    const unsigned shift=upper?62:63;
    const U q=atan_ratio_words(numerator.q>>(64-shift),numerator.q<<shift,denominator.q);
    const int e=numerator.e-denominator.e+int(upper);
    const U sign=(b&D::Sign)^(negative?D::Sign:0)^((n&1)?D::Sign:0);
    U result;
    if(atan_pack(q,e,sign,12,result)) return real(result);
    const int width_n=numerator.e-scales[n&1]+94,width_d=denominator.e-scales[(n&1)^1]+94;
    const U retained=q>>10,midpoint=(retained<<1)|1;
    bool above;
    if(checked_trig_ratio_midpoint(values[n&1],values[(n&1)^1],
        unsigned(54-width_n+width_d-int(upper)),midpoint,error,above))
      return real(sign+(U(e+1021)<<52)+retained+U(above));
  }
  return checked_trig_backend(x,op);
}
