// RP2040 full-range argument stage. No new table: CORE-MATH's existing
// downward1280-bit1/(2*pi) table is shared through a read-only accessor.
extern "C" const uint64_t* mk61_m0_trig_inverse_table();
__attribute__((always_inline)) inline uint32_t trig_large_digit(const uint64_t* table,unsigned i) {
  const U value=table[i>>1];
  return i&1U?uint32_t(value):uint32_t(value>>32);
}
extern "C" void mk61_m0_trig_product(uint32_t*,const uint32_t*,U);
extern "C" void mk61_m0_trig_pi2_product(uint32_t*,const uint32_t*,const uint32_t*);
// sh<=2^51, so sh<<2 fits the existing a63*b54 contract.
// Its1/2+2^-15 product error keeps the exact first-pass bound below6.
extern "C" MK61_SOFT_PCS U mk61_m0_pow_exp_product_flash(U,U);
__attribute__((section(".m0_trig_large")))
__attribute__((optimize("Os"),noinline)) static U trig_large_fast_table(CheckedTrigArgument a,unsigned op,U sign) {
  const unsigned j=unsigned((a.q+(U(1)<<51))>>52);
  const uint32_t* row=trig94_table[j];
  const U s=(U(row[2])<<32)|row[1],c=(U(row[5])<<32)|row[4];
  U value=op?c:s;unsigned error=1+a.error;
  const U h=a.q-(U(j)<<52);
  if(h) {
    const bool negative=bool(h>>63);const U magnitude=negative?U(0)-h:h;
    const uint32_t t=uint32_t(magnitude>>20);
    const U square=wide32(t,t),cross=wide32(t,uint32_t(magnitude)&0xFFFFFU);
    const U z=(square>>22)+(cross>>41)+1;
    const U p=wide32(uint32_t(square),t);
    const uint32_t cube=uint32_t((wide32(uint32_t(square>>32),t)+(p>>32))>>32);
    const uint32_t third=uint32_t(wide32(cube+3,0xAAAAAAABU)>>34);
    const uint32_t fourth=uint32_t(wide32(uint32_t(wide32(cube,t)>>42)+12,0xAAAAAAABU)>>36);
    const U sh=magnitude-third,ch=((z+1)>>1)-fourth;
    const U odd=mk61_m0_pow_exp_product_flash(op?s:c,sh<<2);
    value-=trig_small_product(value,ch);
    value+=negative!=bool(op)?U(0)-odd:odd;
    error=6+a.error;
  }
  unsigned shift=9;uint32_t high=uint32_t(value>>32);
  if(high<(1U<<26)) {high<<=4;shift-=4;}
  if(high<(1U<<28)) {high<<=2;shift-=2;}
  if(high<(1U<<29)) --shift;
  const uint32_t half=1U<<(shift-1),lo=uint32_t(value),hi=uint32_t(value>>32),tail=lo&((half<<1)-1);
  if(tail>=half?tail-half<=error:half-tail<=error) return 0;
  const U retained=(U(hi>>shift)<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  return sign+(U(shift+1012)<<52)+retained+U(tail>half || (tail==half && (retained&1)));
}
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_trig_large")))
bool mk61_m0_trig_large_argument(U m,CheckedTrigArgument* a,Refine96* fine) {
  const uint32_t input_high=uint32_t(m>>32);
  if(input_high<0x41300000U || input_high>=0x7FF00000U) return false;
  const int e=int(m>>52)-1023;
  const unsigned index=e<52?0U:unsigned(e-52)>>5;
  const int r=e-52-32*int(index);
  const U significand=(m&D::Fraction)|D::Hidden;
  const uint64_t* table=mk61_m0_trig_inverse_table();
  uint32_t digits[6],product[7];
  const unsigned block=index>>1;
  if(index&1U) {
    digits[0]=uint32_t(table[block+3]>>32);
    const U a=table[block+2],b=table[block+1];
    digits[1]=uint32_t(a);digits[2]=uint32_t(a>>32);
    digits[3]=uint32_t(b);digits[4]=uint32_t(b>>32);
    digits[5]=uint32_t(table[block]);
  } else {
    const U a=table[block+2],b=table[block+1],c=table[block];
    digits[0]=uint32_t(a);digits[1]=uint32_t(a>>32);
    digits[2]=uint32_t(b);digits[3]=uint32_t(b>>32);
    digits[4]=uint32_t(c);digits[5]=uint32_t(c>>32);
  }
  mk61_m0_trig_product(product,digits,significand);
  // The omitted low three16-bit columns add<1.5 Q96 units; the
  // table tail adds<2^-12 and flooring<1, for a total strictly<3.
  const unsigned shift=unsigned(96-r),word=shift>>5,s=shift&31;
  uint32_t f[3];const uint32_t* p=product+word;
  if(s) {
    const unsigned left=32-s;
    f[0]=(p[0]>>s)|(p[1]<<left);
    f[1]=(p[1]>>s)|(p[2]<<left);
    f[2]=(p[2]>>s)|(p[3]<<left);
  } else {f[0]=p[0];f[1]=p[1];f[2]=p[2];}
  unsigned n=f[2]>>30;
  f[2]=(f[2]<<2)|(f[1]>>30);f[1]=(f[1]<<2)|(f[0]>>30);f[0]<<=2;
  const bool negative=bool(f[2]>>31);
  if(negative) {f[0]=0U-f[0];f[1]=~f[1]+unsigned(!f[0]);f[2]=~f[2]+unsigned(!f[0]&&!f[1]);++n;}
  // Certify the nearest quadrant independently of the later rounding cell.
  if(f[2]>=0x80000000U ||
     (f[2]==0x7FFFFFFFU && f[1]==0xFFFFFFFFU && f[0]>=0xFFFFFFF0U)) return false;
  uint32_t remainder[3];
  mk61_m0_trig_pi2_product(remainder,f,trig_pi2+3);
  const uint32_t r0=remainder[0],r1=remainder[1],r2=remainder[2];
  const U top=(U(r2)<<32)|r1;
  // Phase error<12 Q96; the omitted pi/2 columns contribute<5
  // Q95, pi/2 truncation<1/2 and the final floor<1: total<16.
  if(r2<8) return false;
  if(fine) *fine={(U(r1)<<32)|r0,r2};
  U q;int exponent=1;int16_t tail=0;
  if(r2>=(1U<<25)) {
    const bool up=(r1&1) && (r0||(r1&2));
    q=(top>>1)+U(up);
    const unsigned t=(r1&1)*128U+(r0>>25);
    const uint32_t fine=r0&0x1FFFFFFU;
    tail=int16_t(int(t)+int(fine>0x1000000U || (fine==0x1000000U && (t&1)))-int(up)*256);
  } else {
    const unsigned leading=clz64(top);exponent=1-int(leading);
    const uint32_t th=(r2<<leading)|(r1>>(32-leading));
    const uint32_t tl=(r1<<leading)|(r0>>(32-leading));
    const uint32_t sticky=r0<<leading;
    q=(U(th>>1)<<32)|((tl>>1)|(th<<31));
    q+=U((tl&1) && (sticky||(tl&2)));
  }
  a->q=q;a->e=exponent;a->n=n&3U;a->error=1;a->negative=negative;a->tail=tail;
  return true;
}
// Reuse the existing Q94 evaluator on the retained Q95 remainder.
// Its16-unit input radius contributes at most8*2^-scale Q94 units.
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_trig_large")))
MK61_SOFT_PCS double mk61_m0_trig_large_refine(double x,unsigned op) {
  const U b=bits(x),m=b&D::Magnitude;
  CheckedTrigArgument a;Refine96 fine;
  if(!mk61_m0_trig_large_argument(m,&a,&fine)) return checked_trig_backend(x,op);
  const Trig192 r={0,fine.low<<32,(fine.low>>32)|(U(fine.high)<<32)};
  const unsigned selected=op==0?(a.n&1):((a.n&1)^1);
  Refine96 values[2];int scales[2];uint32_t error;
  checked_trig_refine_values(r,1U<<selected,values,scales,error);
  const int scale=scales[selected];
  if(scale>0 || scale<-27) return checked_trig_backend(x,op);
  error+=(8U<<unsigned(-scale))+1U;
  const unsigned flip=(op==0?((a.n>>1)&1)^unsigned(b>>63):((a.n+1)>>1)&1)^
    (selected?0:unsigned(a.negative));
  U result;
  if(r96_pack(values[selected],scale,U(flip)<<63,error,result)) return real(result);
  return checked_trig_backend(x,op);
}
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_trig_large")))
MK61_SOFT_PCS double mk61_m0_trig_large(double x,unsigned op) {
  const U b=bits(x),m=b&D::Magnitude;
  CheckedTrigArgument a;
  if(!mk61_m0_trig_large_argument(m,&a,nullptr)) return checked_trig_backend(x,op);
  const unsigned selected=op==0?(a.n&1):op==1?((a.n&1)^1):2;
  U result;
  if(op==2) {
    const unsigned flip=unsigned(b>>63)^unsigned(a.negative)^(a.n&1);
    if(a.e==1) {
      result=checked_trig_tan_table(a,U(flip)<<63);
      if(result) return real(result);
    } else {
      CheckedTrigValue f=checked_trig_tan_small(a);
      if(a.n&1) {
        if(f.q>>63) {f.q>>=1;++f.e;f.error=(f.error+1)/2+1;}
        f={checked_trig_inverse(f.q),1-f.e,2*f.error+6};
      }
      if(atan_pack(f.q,f.e,U(flip)<<63,f.error,result)) return real(result);
    }
  } else {
    const unsigned flip=(op==0?((a.n>>1)&1)^unsigned(b>>63):((a.n+1)>>1)&1)^(selected?0:unsigned(a.negative));
    if(a.e==1) {
      // Very small sine values have narrow Q62 rounding cells; go
      // directly to Q70 there instead of paying for a rejected pass.
      result=selected || a.q>=(U(1)<<59)?trig_large_fast_table(a,selected,U(flip)<<63):0;
      if(!result) result=checked_trig_table(a,selected,U(flip)<<63);
      if(result) return real(result);
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    } else {
      result=checked_trig_small_packed(a,selected,U(flip)<<63);
      if(result) return real(result);
    }
#else
    } else if(checked_trig_pack(checked_trig_small(a,selected),U(flip)<<63,result)) return real(result);
#endif
  }
  return op==2?checked_trig_backend(x,op):mk61_m0_trig_large_refine(x,op);
}
