// Exact RNE acceptance for positive integer powers3..8. A bounded
// Q62 product keeps guard bits instead of rounding intermediate doubles.
__attribute__((always_inline)) inline bool pow_integer_product(U &a,int &ea,unsigned &error,U b,int eb,unsigned other_error) {
  const U q=mk61_m0_product62(a,b);
  // Inputs are normalized. A wrapped near-four product is below2^62.
  if(q<(U(1)<<62)) return false;
  a=q;ea+=eb;error=2*error+2*other_error+7;
  if(a&(U(1)<<63)) {a>>=1;++ea;error=(error>>1)+1;}
  return true;
}
// A short odd significand can be raised exactly in one uint64_t.
// Enter only for powers3..8; its bit-length bound proves every product fits.
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
__attribute__((optimize("Os"),noinline,section(".m0_pow_exact_extension"))) static U pow_short_integer(U xb,unsigned n) {
  const U undecided=D::Infinity|D::Quiet;
  if(n<3 || n>8 || xb>=D::Infinity) return undecided;
  if(xb<UINT64_C(0x0010000000000000)) return 0;
  const U full=(xb&D::Fraction)|D::Hidden;
  const unsigned zeros=63-clz64(full&(U(0)-full));
  if((53-zeros)*n>64) return undecided;
  const uint32_t a=uint32_t(full>>zeros);
  U power=a;
  if(a!=1) for(unsigned i=1;i<n;++i) {
    const U low=wide32(uint32_t(power),a);
    const uint32_t high=uint32_t(power>>32)*a+uint32_t(low>>32);
    power=(U(high)<<32)|uint32_t(low);
  }
  const unsigned top=63-clz64(power);
  const int scale=(int(xb>>52)-1075+int(zeros))*int(n);
  const U significand=top>55?jam(power,top-55):power<<(55-top);
  return D::pack(0,scale+int(top),significand);
}
#endif

__attribute__((optimize("Os"),noinline,section(".m0_pow_extension"))) static U pow_small_integer(U xb,uint32_t yh) {
  unsigned n;
  switch(yh) {
  case 0x40080000U:n=3;break;
  case 0x40100000U:n=4;break;
  case 0x40140000U:n=5;break;
  case 0x40180000U:n=6;break;
  case 0x401C0000U:n=7;break;
  case 0x40200000U:n=8;break;
  default:return D::Infinity|D::Quiet;
  }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // A supported odd coefficient has <=21bits, hence >=32 trailing zeros
  // in the normal binary64 significand. Full mantissas skip this branch.
  if(!uint32_t(xb)) {
    const U exact=pow_short_integer(xb,n);
    if(exact!=(D::Infinity|D::Quiet)) return exact;
  }
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#define M0_POW_INTEGER_REJECT() return pow_integer128(xb,U(yh)<<32)
#else
#define M0_POW_INTEGER_REJECT() return D::Infinity|D::Quiet
#endif
  if(xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity) M0_POW_INTEGER_REJECT();
  const U base=((xb&D::Fraction)|D::Hidden)<<10;
  const int base_e=int(xb>>52)-1023;
  U q=base;int k=base_e;unsigned error=0;
  if(!pow_integer_product(q,k,error,base,base_e,0)) M0_POW_INTEGER_REJECT();
  if(n==3) {
    if(!pow_integer_product(q,k,error,base,base_e,0)) M0_POW_INTEGER_REJECT();
  } else {
    const U square=q;const int square_e=k;const unsigned square_error=error;
    if(!pow_integer_product(q,k,error,square,square_e,square_error)) M0_POW_INTEGER_REJECT();
    if(n==8) {
      const U fourth=q;const int fourth_e=k;const unsigned fourth_error=error;
      if(!pow_integer_product(q,k,error,fourth,fourth_e,fourth_error)) M0_POW_INTEGER_REJECT();
    } else if(n>=5) {
      if(n>=6 && !pow_integer_product(q,k,error,square,square_e,square_error)) M0_POW_INTEGER_REJECT();
      if(n!=6 && !pow_integer_product(q,k,error,base,base_e,0)) M0_POW_INTEGER_REJECT();
    }
  }
  if(k>1023) {
    if(k>1024 || q-(U(1)<<62)+256>error) return D::Infinity;
    M0_POW_INTEGER_REJECT();
  }
  if(k<-1022) {
    if(k<-1075) {
      const U half=U(1)<<63;
      if(k<-1076 || (q<half && half-q>error)) return 0;
    } else {
      const unsigned shift=unsigned(-k-1012);
      const U mask=(U(1)<<shift)-1,half=U(1)<<(shift-1),tail=q&mask;
      const U distance=tail>half?tail-half:half-tail;
      if(distance>error) {
        const U retained=q>>shift;
        return retained+U(tail>half || (tail==half && (retained&1)));
      }
    }
    M0_POW_INTEGER_REJECT();
  }
  const uint32_t tail=uint32_t(q)&1023U;
  if(uint32_t(tail-(512U-error))<=2*error) M0_POW_INTEGER_REJECT();
  const U rounded=(q+511+((q>>10)&1))>>10;
  return (U(k+1022)<<52)+rounded;
}

#undef M0_POW_INTEGER_REJECT
