// A Q70 correction of the discarded exp bits. This pass is reached only
// when the Q62 rounding test was inconclusive; it changes no accepted cell.
// It reuses both exp tables. certify_m0_exp_fine.py bounds the final error
// by less than 3136 / 65536 of one Q62 unit, before binary64 rounding.
__attribute__((always_inline)) inline U exp_fine_nonlinear(U a,bool negative) {
  const uint32_t lo=uint32_t(a),hi=uint32_t(a>>32);
  const U bottom=wide32(lo,lo),cross=wide32(lo,hi);
  const U middle=(bottom>>32)+(U(uint32_t(cross))<<1);
  const U top=wide32(hi,hi)+((cross>>32)<<1)+(middle>>32);
  const U square=(top<<5)|(uint32_t(middle)>>27); // floor(r*r/2 * 2^70)

  // The bounded 41/40-bit operands need three wide products and one
  // ordinary product. The cross sum is <2^43, so cannot overflow U.
  const U b=square>>8,t=a>>14;
  const uint32_t bl=uint32_t(b),bh=uint32_t(b>>32),tl=uint32_t(t),th=uint32_t(t>>32);
  const U low=wide32(bl,tl);
  const U sum=wide32(bh,tl)+wide32(bl,th)+(low>>32);
  const U cube=(sum>>10)+(U(bh*th)<<22);
  // ceil(2^40/3)=0x5555555556. Its excess is 2/(3*2^40).
  const uint32_t ch=uint32_t(cube>>32);
  const U upper=(U(ch*0x5555U)<<16)+ch*0x5556U;
  const U third_sum=upper+wide32(uint32_t(cube),0x55U)+
    (wide32(uint32_t(cube),0x55555556U)>>32);
  const U third=(third_sum>>8)+(U(ch*0x55U)<<24);

  const uint32_t v=uint32_t(square>>18);
  const uint32_t fourth_numerator=uint32_t(wide32(v,v)>>34);
  const uint32_t fourth=uint32_t(wide32(fourth_numerator,0xAAAAAAABU)>>34);
  const uint32_t fifth_numerator=uint32_t(wide32(fourth,uint32_t(a>>33))>>31);
  const uint32_t fifth=(fifth_numerator*0xCCCDU)>>18;
  return negative?square+fourth-third-fifth:square+fourth+third+fifth;
}

MK61_M0_EXP_CORE __attribute__((optimize("Os","no-tree-ter","no-reorder-blocks","no-if-conversion"),noinline,cold))
static unsigned exp_round_fine(double x,uint32_t n,U delta,unsigned cell) {
  // Normalized cells need a doubled enclosure. Tiny inputs with n=0
  // also retain the existing independent refinement.
  if(!n || (cell&1024U)) return 0;
  const U xb=bits(x),m=xb&D::Magnitude,significand=(m&D::Fraction)|D::Hidden;
  const unsigned shift=unsigned(int(m>>52)-1011); // 1..21 when n!=0
  const uint32_t sl=uint32_t(significand),sh=uint32_t(significand>>32);
  const U scaled=(U((sh<<shift)|(sl>>(32-shift)))<<32)|(sl<<shift);
  const U reduction=wide32(uint32_t(exp_step_high),n)+
    (U(uint32_t(exp_step_high>>32)*n)<<32)+(wide32(n,exp_step_low)>>32);
  const U raw=scaled-reduction,a=raw>>63?U(0)-raw:raw;
  const bool below=(cell&2048U)!=0;
  const U nonlinear=exp_fine_nonlinear(a,below);
  const U previous=below?a-delta:delta-a;
  const int32_t polynomial=int32_t(int64_t(nonlinear)-int64_t(previous<<6));
  const uint32_t fraction=n*exp_step_low;
  const int32_t residual=(xb&D::Sign)?int32_t(fraction>>16):-int32_t(fraction>>16);
  const int32_t correction=polynomial*1024+residual; // Q16 units of Q64

  const int signed_n=xb&D::Sign?-int(n):int(n);
  const unsigned index=unsigned(signed_n)&511U;
  const U base=exp_table[index];
  const uint32_t al=uint32_t(base),ah=uint32_t(base>>32);
  const uint32_t bl=uint32_t(delta),bh=uint32_t(delta>>32);
  const U sum=U(uint32_t(al*bh))+uint32_t(ah*bl)+(al>>16)*(bl>>16);
  int adjustment=int(sum>>32)-1+int(uint32_t(sum)>=0x80000000U);
  int32_t product_fraction=int32_t(uint32_t(sum))>>16;
  if(below) {adjustment=-adjustment;product_fraction=-product_fraction;}
  const int distance=int(cell&1023U)+adjustment-512;
  const uint32_t magnitude=correction<0?uint32_t(-correction):uint32_t(correction);
  const int32_t product=int32_t(wide32(ah,magnitude)>>32);
  const int32_t table_fraction=int32_t(refine_exp_table[index][0])>>16;
  const int32_t refined=distance*65536+table_fraction+product_fraction+
    (correction<0?-product:product);
  return (refined<0?-refined:refined)>3136?2-(unsigned(refined)>>31):0;
}
