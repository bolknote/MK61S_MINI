MK61_M0_TRIG_SECTION("tan_small")
__attribute__((optimize("Os"),noinline)) static CheckedTrigValue checked_trig_tan_small(CheckedTrigArgument a) {
  const U z=checked_trig_small_square(a.q,a.e),one=U(1)<<62;
  if(!z) return {a.q,a.e,2+a.error};
  if(a.e<=-18) {
    const U third=wide32(uint32_t(z)+1,0xAAAAAAABU)>>33;
    return {a.q+mk61_m0_mul_q62(a.q,third),a.e,3+2*a.error};
  }
  const U z2=math62_product(z,z);
  const uint32_t c=0x22222222U+
    uint32_t(wide32(uint32_t(z>>22),231791886U)>>32)+
    uint32_t(wide32(uint32_t(z2>>22),93928738U)>>32);
  const U factor=one+math62_third(z)+math62_scale40(z2,c,34);
  return {math62_product(a.q,factor),a.e,8+2*a.error};
}
// Q70 Taylor evaluation keeps additional guard bits for small tangent
// magnitudes. Only the table value needs a third limb; all corrections
// fit in 64 bits because |h| < 2^-11 + 2^-63.
// If reciprocal rounding is undecided, compare the unshortened Q70 value
// with the candidate binary64 midpoint. This keeps the bits discarded by
// normalization and avoids reevaluating sin/cos in the middle pass.
__attribute__((optimize("Os"),noinline,cold)) static U checked_trig_tan_midpoint(Refine96 value,unsigned error,U q,int e,U sign) {
  if(q<(U(1)<<62)) {q<<=1;--e;}
  const unsigned high=unsigned(q>>63),shift=10+high;
  const U retained=q>>shift,midpoint=(retained<<1)|1;
  // midpoint * 2^(e+high-54) is the positive binary64 rounding midpoint.
  // Compare value*midpoint with 2^(124-e-high), all in exact integers.
  const Product p=multiply(value.low,midpoint);
  const U upper=p.high+low_product(value.high,midpoint);
  U low=U(0)-p.low,hi=(U(1)<<unsigned(60-e-int(high)))-upper-U(p.low!=0);
  const bool negative=bool(hi>>63);
  if(negative) {low=U(0)-low;hi=~hi+U(!low);}
  const U tolerance=low_product(error,midpoint);
  if(!hi && low<=tolerance) return 0;
  return sign+(U(e+1021+int(high))<<52)+retained+U(!negative);
}
// Sixth Taylor term in Q70, error <4 units. Q8 Horner is sufficient here:
// the entire correction is <96 units and is needed only after ambiguity.
__attribute__((optimize("Os"),noinline,cold)) static uint32_t checked_trig_tan_sixth(const TrigTanRow &row,U h) {
  const uint32_t t=uint32_t(row.first>>57)*4U+uint32_t(row.value>>62)+unsigned((row.value>>61)&1);
  const uint32_t u=(t*t+128U)>>8;
  const uint32_t p1=105U*256U+45U*u;
  const uint32_t p2=77U*256U+((p1*u+128U)>>8);
  const uint32_t p3=17U*256U+((p2*u+128U)>>8);
  const uint32_t coefficient=(p3*t+5760U)/11520U;
  const U delta=h>>63?U(0)-h:h;
  const uint32_t g=uint32_t((delta+(U(1)<<50))>>51);
  const uint32_t g2=(g*g+128U)>>8,g3=(g2*g+128U)>>8,g6=(g3*g3+128U)>>8;
  return (coefficient*g6+2048U)>>12;
}
// For q <=2^30, two native products approximate q*q/2^34 to <=3/4.
// The missing low square and the truncated cross fraction contribute <2
// high-word units. Bias3 followed by >>2 encloses all four residue classes.
__attribute__((always_inline)) inline uint32_t checked_trig_tan_fourth(uint32_t q) {
  const uint32_t high=q>>16,low=q&0xFFFFU;
  return (high*high+((high*low)>>15)+3U)>>2;
}
MK61_M0_TRIG_SECTION("tan_table")
__attribute__((optimize("Os"),noinline)) static U checked_trig_tan_table(CheckedTrigArgument a,U sign) {
  const unsigned j=unsigned((a.q+(U(1)<<51))>>52);
  const TrigTanRow &row=trig_tan_table[j];
  const U h=((a.q-(U(j)<<52))<<8)+U(int64_t(a.tail));Refine96 value={row.value,uint32_t(row.first>>57)};
  unsigned error=1+3*a.error;
  if(h) {
    const bool negative=bool(h>>63);const U delta=negative?U(0)-h:h,magnitude=delta>>8;
    const uint32_t t=uint32_t(magnitude>>20);
    const U square=wide32(t,t),cross=wide32(t,uint32_t(magnitude)&0xFFFFFU);
    const uint32_t fraction=((uint32_t(square)&0x3FFFU)<<10)+(uint32_t(cross>>9)&0xFFFFFFU);
    const U z=(square>>14)+(cross>>33)+((fraction+(1U<<23))>>24);
    U cube=0,second=0;
    if(z) {
      // Retain h's Q70 tail in the cube. The shared six-product kernel
      // accepts a full-width first operand and z <2^48; the one possible
      // endpoint z=2^48 reduces to a rounded shift. B50 fits 52 bits.
      cube=z<(U(1)<<48)?mk61_m0_log_cube70(delta,z):(delta+(1U<<21))>>22;
      second=mk61_m0_log_product54(z,(row.second<<12)>>8);
    }
    const U linear=mk61_m0_product62(row.first<<7,delta);
    const U c=wide32(uint32_t(cube),uint32_t(row.third));
    const unsigned high=unsigned(row.second>>62);
    U third=(c>>32)+wide32(uint32_t(cube>>32)&0xFFFFU,uint32_t(row.third))+
      (high==2?cube<<1:high?cube:0);
    third+=uint32_t(c)>0x80000000U || (uint32_t(c)==0x80000000U && (third&1));
    const uint32_t zr=uint32_t((z+(1U<<17))>>18);
    const uint32_t fourth=checked_trig_tan_fourth(zr);
    const uint32_t fifth=uint32_t((wide32(fourth,t)+(U(1)<<41))>>42);
    const uint32_t fifth_coefficient=(row.polynomial>>25)|(uint32_t(row.second>>45)&0x1FF80U);
    const U even=second+((wide32(fourth,row.polynomial&0x1FFFFFFU)+(1U<<22))>>23);
    const U odd=linear+third+U((fifth*fifth_coefficient+(1U<<13))>>14);
    value=r96_add_low(value,even);
    value=negative?r96_sub_low(value,odd):r96_add_low(value,odd);
    // Preserve the Q70 argument tail in the linear term. The omitted
    // eight bits in the square add <1/4 Q70 unit. The bounded products,
    // packed coefficient errors and remainder fit in 143 units.
    // |tan'| <3 throughout this reduced domain.
    error=(!z?9U:delta<(U(1)<<58)?25U:143U)+3*a.error;
  }
  for(;;) {
    unsigned shift=2;uint32_t high=value.high;
    if(high>=16) {high>>=4;shift+=4;}
    if(high>=4) {high>>=2;shift+=2;}
    if(high>=2) ++shift;
    const uint32_t lo=uint32_t(value.low),hi=uint32_t(value.low>>32);
    if(a.n&1) {
      const U q=(U((hi>>shift)|(value.high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
      const U inverse=checked_trig_inverse(q);const int e=8-int(shift);
      const unsigned relative_error=((error+((1U<<shift)-1))>>shift)+1;
      U result;
      if(atan_pack(inverse,e,sign,2*relative_error+6,result)) return result;
      result=checked_trig_tan_midpoint(value,error,inverse,e,sign);
      if(result) return result;
    } else {
      // Round the full Q70 value, retaining the extra guard bits.
      shift+=10;
      const uint32_t half=1U<<(shift-1),tail=lo&((half<<1)-1);
      if(!(tail>=half?tail-half<=error:half-tail<=error)) {
        const U retained=(U((hi>>shift)|(value.high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
        return sign+(U(shift+1004)<<52)+retained+U(tail>half || (tail==half && (retained&1)));
      }
    }
    if(error<=51+3*a.error) return 0;
    value=r96_add_low(value,checked_trig_tan_sixth(row,h));
    error=51+3*a.error;
  }
}
