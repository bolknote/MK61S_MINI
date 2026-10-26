// Private entry contract: positive normal E<=1023 and E&(E+1)==0.
// The unchanged source router proves it for every call. Thus k=0 or
// |k|>=512. Uniform polynomial error<16 and Q70 ln2 error<-472/1000
// make the nonzero-exponent magnitude error strictly negative. Points
// strictly above the midpoint therefore round upward without refinement.
constexpr bool ln_isolated_nonzero_exponents_are_large() {
  for(unsigned e=1;e<=1023;++e)
    if(!(e&(e+1)) && e!=1023 && 1023-e<512) return false;
  return true;
}
static_assert(ln_isolated_nonzero_exponents_are_large(),"isolated ln2 bias requires |k|>=512");
// Source-derived isolated RP ln callers. Existing tables and near kernel are shared.

__attribute__((optimize("Os"),noinline,cold)) static int ln_main_square_direction(
    uint32_t t,uint32_t h_low,int32_t above_margin,int32_t below_margin,uint32_t den,
    uint32_t cube,uint32_t fourth) {
  const U cross=wide32(t,h_low&0x7FFFFFFU);
  const uint32_t product=t*t;
  const uint32_t fraction=uint32_t(cross>>34)&255U;
  const int32_t parity=-int32_t(((product>>16)+uint32_t(cross>>42)+1U)&1U);
  const int32_t factor=15*int32_t(den);
  const int32_t upper_gain=128-int32_t((fraction+2U)>>1)-128*parity;
  const int32_t refined_above=above_margin+factor*upper_gain;
  if(refined_above>=0) return 1;
  const int32_t lower_gain=int32_t((product&65535U)>>9)+int32_t(fraction>>1)+128+128*parity;
  if(below_margin+factor*lower_gain>=0) return -1;
  if(fourth<65536U) {
    const uint32_t fourth_fraction=uint32_t(wide32(cube>>6,t)>>29)&255U;
    const uint32_t fifth_fraction=uint32_t(wide32(uint16_t(fourth),t)>>35)&255U;
    const int32_t gain=1005-int32_t((15U*(fourth_fraction+4U)+3U)>>2)+3*(int32_t(fifth_fraction)-1);
    if(refined_above+int32_t(den)*gain>=0) return 1;
  }
  return 0;
}

// The private entry keeps the old argument layout and falls straight into
// the general gate for a negative offset. The postbuild check binds that
// fallthrough to the actual compiled general body, not source order alone.
static int ln_main_point_direction_general(U,int32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
int ln_main_point_direction(U,int32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);

__attribute__((optimize("Os"),noinline,cold,no_reorder,used,section(".m0_ln_point_bundle"))) static int ln_small_positive_point_direction(U b,
    int32_t midpoint,uint32_t h_low,uint32_t fourth,uint32_t fifth,
    uint32_t t,uint32_t cube,uint32_t third) {
  const uint32_t index=uint32_t(b>>42)&1023U,den=2049U+2U*index;
  const int32_t residue=int32_t((uint32_t(b)<<29)-h_low*den);
  const int32_t r3=int32_t(cube-3U*third);
  const int32_t r4=int32_t((fourth+2U)&3U)-2;
  int32_t bias=960*r4-1280*r3;
  if(fifth) bias-=768*(int32_t(fifth)-5*int32_t(((fifth+2U)*52429U)>>18));
  const int32_t center=-int32_t(int32_t(refine_log_table[index][3]<<8)>>24);
  const uint32_t square=(((t*t)&65535U)+511U)>>9;
  // Private small-domain bounds prove both middle sums fit uint32_t.
  const uint32_t al=uint16_t(cube>>6),ah=cube>>22,tl=uint16_t(t),th=t>>16;
  const uint32_t middle=((al*tl)>>16)+ah*tl+al*th;
  const uint32_t fourth_fraction=((middle>>13)+((ah*th)<<3))&255U;
  const uint32_t fifth_fraction=((uint16_t(fourth)*th+((uint16_t(fourth)*tl)>>16))>>19)&255U;
  const int32_t upper=bias+15*(center+2+int32_t(square)+47)
    +int32_t((15U*(fourth_fraction+4U)+3U)>>2)-3*(int32_t(fifth_fraction)-1)+3;
  if((3840*midpoint-upper)*int32_t(den)+3840*residue>=0) return 1;
  return ln_main_point_direction_general(b,midpoint,h_low,fourth,fifth,t,cube,third);
}

asm(
 ".pushsection .m0_ln_point_bundle,\"ax\",%progbits\n"
 ".syntax unified\n.thumb\n.p2align 1\n"
 ".Lln_small_positive_dispatch:\n"
 "cmp r2,#0\nble .Lln_point_general_jump\n"
 "ldr r0,[sp,#0]\nlsrs r0,r0,#16\nbne .Lln_point_general_jump\n"
 "mov r0,ip\nb ln_small_positive_point_direction\n"
 ".Lln_point_general_jump:\nmov r0,ip\nb ln_main_point_direction_general\n"
 ".global ln_main_point_direction\n.type ln_main_point_direction,%function\n.thumb_func\n"
 "ln_main_point_direction:\n"
 "mov ip,r0\nlsls r0,r1,#23\nbcs .Lln_small_positive_dispatch\nmov r0,ip\n"
 ".size ln_main_point_direction,.-ln_main_point_direction\n"
 ".syntax divided\n.popsection\n");

__attribute__((optimize("Os"),noinline,cold,no_reorder,used,section(".m0_ln_point_bundle"))) static int ln_main_point_direction_general(U b,
    int32_t midpoint,uint32_t h_low,uint32_t fourth,uint32_t fifth,
    uint32_t t,uint32_t cube,uint32_t third) {
  const uint32_t index=uint32_t(b>>42)&1023U,den=2049U+2U*index;
  const bool negative=(uint32_t(b>>32)&512U)==0;
  uint32_t delta_low=uint32_t(b)<<29;
  if(negative) delta_low=0U-delta_low;
  const int32_t residue=int32_t(delta_low-h_low*den);
  const int32_t oriented=negative?-residue:residue;
  const int32_t r3=int32_t(cube-3U*third);
  const int32_t r4=int32_t((fourth+2U)&3U)-2;
  const int32_t r5=int32_t(fifth)-5*int32_t(((fifth+2U)*52429U)>>18);
  const int32_t odd=768*r5+1280*r3;
  const int32_t bias=960*r4+(negative?odd:-odd);
  const int32_t center=-int32_t(int32_t(refine_log_table[index][3]<<8)>>24);
  const uint32_t square=(((t*t)&65535U)+511U)>>9;
  const uint32_t sixth=((fifth+2U)*((t>>16)+1U)+524287U)>>19;
  const uint32_t remainder=(((sixth+5U)*10923U)>>16)+1U;
  const int32_t lower=bias+15*(center-2-(negative?304:355));
  const int32_t upper=bias+15*(center+2+int32_t((negative?166U:115U)+square+remainder));
  const int32_t linear=3840*oriented;
  const int32_t above_margin=(3840*midpoint-upper)*int32_t(den)+linear;
  if(above_margin>=0) return 1;
  const int32_t below_margin=(lower-3840*midpoint)*int32_t(den)-linear;
  if(below_margin>=0) return -1;
  return ln_main_square_direction(t,h_low,above_margin,below_margin,den,cube,negative?UINT32_MAX:fourth);
}

__attribute__((always_inline)) inline double ln_main_point_pack70(U low,uint32_t high,
    U sign,unsigned shift,int bias,bool upward) {
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  return real(sign+(U(bias-8)<<52)+retained+U(upward));
}

__attribute__((always_inline)) inline double ln_isolated_pack70(U low,uint32_t high,U sign,uint32_t error,double x
    ,uint32_t h_low=0,uint32_t fourth=0,uint32_t fifth=0,
    uint32_t t=0,uint32_t cube=0,uint32_t third=0
    ) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t guard=error-1;
  if(uint32_t(tail-(half-guard))<=2*guard) {
    bool safe=error>ln_main_radius && tail>half;
    if(!safe && error==ln_main_radius) {
      const uint32_t bh=uint32_t(bits(x)>>32);
      if((bh>>20)==1023U) {
        const uint32_t distance=tail>half?tail-half:half-tail;
        if(tail<half) {
          safe=distance>=4U || ((bh&0xFFFFFU)<32768U && (bh&1023U)>=1022U);
        } else safe=distance>=((bh&512U)?7U:6U);
      }
    }
    if(!safe && error==ln_main_radius && uint32_t(bits(x)>>52)==1023U) {
      const int direction=ln_main_point_direction(bits(x),int32_t(tail)-int32_t(half),h_low,fourth,fifth,t,cube,third);
      if(direction) return ln_main_point_pack70(low,high,sign,shift,bias,direction>0);
    }
    if(!safe && error>=ln_main_radius) {
      const uint32_t distance=tail>half?tail-half:half-tail;
      if(distance) {
        const U b=bits(x);
        const uint32_t den=2049U+2U*unsigned((b&D::Fraction)>>42);
        const bool negative=(b&(U(1)<<41))==0;
        uint32_t delta_low=uint32_t(b)<<29;
        if(negative) delta_low=0U-delta_low;
        const int32_t residue=int32_t(delta_low-h_low*den);
        const int32_t oriented=(negative!=(sign!=0))?-residue:residue;
        const uint32_t n=2U*(error-ln_main_radius)-((uint32_t(b>>52)^1U)&1U);
        safe=ln_main_coefficient_accept(distance,tail>half,sign,n,den,oriented,negative,fourth,fifth);
      }
    }
    if(!safe) return ln_refine(x);
  }
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}

__attribute__((always_inline)) inline double ln_isolated_main_pack70(U low,uint32_t high,U sign,
    uint32_t exponent_error,uint32_t h_low,double x,uint32_t fourth,uint32_t fifth,
    uint32_t t,uint32_t cube,uint32_t third) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t guard=15U+exponent_error;
  if(uint32_t(tail-(half-guard))<=2U*guard) {
    if(!exponent_error || tail<=half) {
      const uint32_t distance=tail>half?tail-half:half-tail;
      if(!distance) {
        if(!exponent_error) {
          const int direction=ln_main_point_direction(bits(x),0,h_low,fourth,fifth,t,cube,third);
          if(direction) return ln_main_point_pack70(low,high,sign,shift,bias,direction>0);
        }
        return ln_refine(x);
      }
      const U b=bits(x);
      const uint32_t den=2049U+2U*unsigned((b&D::Fraction)>>42);
      const bool negative=(b&(U(1)<<41))==0;
      uint32_t delta_low=uint32_t(b)<<29;
      if(negative) delta_low=0U-delta_low;
      const int32_t residue=int32_t(delta_low-h_low*den);
      const int32_t oriented=(negative!=(sign!=0))?-residue:residue;
      const int32_t directed=tail>half?oriented:-oriented;
      uint32_t radius=7U+exponent_error;
      if(!exponent_error) {
        radius=tail>half?6U:(negative?3U:4U);
        if(!negative && tail<half && den<=2111U && (uint32_t(b>>32)&1023U)>=1022U)
          radius=1U;
      }
      if((int32_t(distance)-int32_t(radius))*int32_t(den)+directed<0) {
        if(!exponent_error) {
          const int direction=ln_main_point_direction(b,int32_t(tail)-int32_t(half),h_low,fourth,fifth,t,cube,third);
          if(direction) return ln_main_point_pack70(low,high,sign,shift,bias,direction>0);
        }
        const uint32_t n=2U*exponent_error-((uint32_t(b>>52)^1U)&1U);
        if(!ln_main_coefficient_accept(distance,tail>half,sign,n,den,oriented,negative,fourth,fifth))
          return ln_refine(x);
      }
    }
  }
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}

__attribute__((optimize("Os"),noinline)) static double ln_isolated_raw(U b) {
  const double x=real(b);
  const int k=int((b>>52)&0x7FFU)-1023;
  const unsigned index=unsigned((b&D::Fraction)>>42);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
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
  if(!k) return ln_isolated_main_pack70(low,high,0,0,uint32_t(h),x,fourth,fifth,t,uint32_t(cube),uint32_t(third));
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(log70_two_low),n),p1=wide32(uint32_t(log70_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log70_two_high*n;
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
  return ln_isolated_main_pack70(result,upper,k<0?D::Sign:0,(n+1)/2,uint32_t(h),x,fourth,fifth,t,uint32_t(cube),uint32_t(third));
}

__attribute__((optimize("Os"),noinline)) MK61_SOFT_PCS double mk61_m0_ln_positive_isolated(double x) {
  const U b=bits(x);
  if(b>=ln_near_lower && b<=UINT64_C(0x3FF0400000000000))
    return ln_near_interval77(x,b);
  if(uint32_t(uint32_t(b)+64U)>128U &&
      (*reinterpret_cast<volatile uint32_t*>(UINT32_C(0xD0000078))&2U)) return ln_isolated_raw(b);
  const int k=int((b>>52)&0x7FFU)-1023;
  const unsigned index=unsigned((b&D::Fraction)>>42);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
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
  if(!k) return ln_isolated_pack70(low,high,0,ln_main_radius,x,uint32_t(h),fourth,fifth,t,uint32_t(cube),uint32_t(third));
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(log70_two_low),n),p1=wide32(uint32_t(log70_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log70_two_high*n;
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
  return ln_isolated_pack70(result,upper,k<0?D::Sign:0,ln_main_radius+(n+1)/2,x,uint32_t(h),fourth,fifth,t,uint32_t(cube),uint32_t(third));
}
