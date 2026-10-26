// Additional bounded Q70 pow pass. The existing first-tier point is only
// a hint: this pass recomputes an independent full Q70 argument enclosure.
// All tables and rounded-high64 products are reused. An undecided cell
// retains the original Q94 refinement.
__attribute__((always_inline)) inline Refine96 pow_middle_row(unsigned index) {
  const uint32_t* row=refine_exp_table[index];
  const U raw=(U(row[1])<<32)|row[0];
  U low=(raw>>24)|(U(row[2])<<40);
  uint32_t high=row[2]>>24;
  const uint32_t tail=uint32_t(raw)&0xFFFFFFU;
  const bool up=tail>0x800000U || (tail==0x800000U && (low&1));
  const U old=low;low+=U(up);high+=low<old;
  return {low,high};
}
__attribute__((always_inline)) inline U pow_middle_correction(Refine96 a,U delta) {
  const U d=delta>>6;
  const U low=mk61_m0_pow_exp_product_flash(a.low>>1,d)<<1;
  const uint32_t c0=(uint32_t(d)&65535U)*a.high;
  const uint32_t c1=(uint32_t(d)>>16)*a.high+(c0>>16);
  const uint32_t c2=uint32_t(d>>32)*a.high+(c1>>16);
  const U high=(U(c2)<<32)|uint32_t((c1<<16)|(c0&65535U));
  return low+high+((a.high*uint32_t(delta&63U))>>6);
}
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_pow_middle")))
bool mk61_m0_pow_middle_interval(U xb,U yb,U* out) {
  const U ym=yb&D::Magnitude;
  const int ey=int(ym>>52)-1023;
  if(xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity || ym>=D::Infinity || ey<-12 || ey>10)
    return false;
  const PowFastLog logarithm=pow_fast_log(ey,xb);
  if(logarithm.scale!=70 || logarithm.high>=65536U || logarithm.error>65535U) return false;
  const unsigned shift=unsigned(52-ey);
  const U sy=(ym&D::Fraction)|D::Hidden;
  const Product argument=mk61_m0_pow_argument(logarithm.low,logarithm.high,sy,shift);
  // The omitted three terms total<2^50. Include their whole effect and
  // the final floor at every shift42..64, instead of assuming one unit.
  unsigned input_error;
  if(ey>=-1) input_error=logarithm.error<<unsigned(ey+1);
  else {
    const unsigned s=unsigned(-ey-1);
    input_error=(logarithm.error+((1U<<s)-1))>>s;
  }
  input_error+=shift>=50?2U:1U+(1U<<(50-shift));
  if(input_error>=65536U || argument.high>=U(747*64)) return false;
  const U a64=(argument.low>>6)|(argument.high<<58),integer=argument.high>>6;
  const U estimate0=wide32(uint32_t(a64>>32),0xB8AA3B29U);
  const U estimate1=wide32(uint32_t(integer),0xB8AA3B29U)+(estimate0>>32);
  const uint32_t n=uint32_t((estimate1+(1U<<21))>>22);
  if(n>552000U) return false;
  // Multiply the complete existing nearest Q96 step before dropping26
  // bits. Its reduction error is<1+n/2^27<2 Q70 units.
  const U p0=wide32(exp_step_low,n);
  const U p1=wide32(uint32_t(exp_step_high),n)+(p0>>32);
  const U p2=wide32(uint32_t(exp_step_high>>32),n)+(p1>>32);
  const U sl=(p1<<32)|uint32_t(p0);
  const Product step={p2>>26,(sl>>26)|(p2<<38)};
  U low=argument.low-step.low,high=argument.high-step.high-U(argument.low<step.low);
  bool negative=bool(high>>63);
  if(negative) {low=U(0)-low;high=~high+U(!low);}
  if(high || low>UINT64_C(826414134502187912)) return false; // |r|<=0.0007
  const U z=mk61_m0_pow_exp_product_flash(low,low>>6);
  const U cube=mk61_m0_pow_exp_product_flash(z,low>>6);
  const U fourth_power=mk61_m0_pow_exp_product_flash(z,z>>6);
  const U fifth_power=mk61_m0_pow_exp_product_flash(fourth_power,low>>6);
  const U third=(math62_third(cube)+1)>>1;
  const U fourth=(math62_third(fourth_power)+4)>>3;
  const U fifth=(wide32(uint32_t(fifth_power),35791394U)+(U(1)<<31))>>32;
  const U even=((z+1)>>1)+fourth,odd=low+third+fifth;
  const bool negative_argument=logarithm.negative^bool(yb&D::Sign);
  negative^=negative_argument;
  const U delta=negative?odd-even:odd+even;
  const int signed_n=negative_argument?-int(n):int(n);
  const unsigned index=unsigned(signed_n)&511U;
  const int k=(signed_n-int(index))/512;
  Refine96 q=pow_middle_row(index);
  const U correction=pow_middle_correction(q,delta);
  q=negative?r96_sub_low(q,correction):r96_add_low(q,correction);
  const unsigned error=16+2*input_error;
  return r128_pack({q.high,q.low},24+k,0,error,*out);
}
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_pow_middle")))
MK61_SOFT_PCS double mk61_m0_pow_midpoint(double x,double y) {
  // At large |y| the old Q70 log error dominates both exp enclosures.
  // Avoid a second evaluation with the same information; keep Q94 there.
  if((bits(y)&D::Magnitude)>=UINT64_C(0x4020000000000000)) return pow_refine_checked(x,y);
  U out;
  if(mk61_m0_pow_middle_interval(bits(x),bits(y),&out)) return real(out);
  return pow_refine_checked(x,y);
}
