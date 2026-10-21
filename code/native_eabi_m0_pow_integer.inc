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
  if(xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity) return D::Infinity|D::Quiet;
  const U base=((xb&D::Fraction)|D::Hidden)<<10;
  const int base_e=int(xb>>52)-1023;
  U q=base;int k=base_e;unsigned error=0;
  if(!pow_integer_product(q,k,error,base,base_e,0)) return D::Infinity|D::Quiet;
  if(n==3) {
    if(!pow_integer_product(q,k,error,base,base_e,0)) return D::Infinity|D::Quiet;
  } else {
    const U square=q;const int square_e=k;const unsigned square_error=error;
    if(!pow_integer_product(q,k,error,square,square_e,square_error)) return D::Infinity|D::Quiet;
    if(n==8) {
      const U fourth=q;const int fourth_e=k;const unsigned fourth_error=error;
      if(!pow_integer_product(q,k,error,fourth,fourth_e,fourth_error)) return D::Infinity|D::Quiet;
    } else if(n>=5) {
      if(n>=6 && !pow_integer_product(q,k,error,square,square_e,square_error)) return D::Infinity|D::Quiet;
      if(n!=6 && !pow_integer_product(q,k,error,base,base_e,0)) return D::Infinity|D::Quiet;
    }
  }
  if(k>1023) {
    if(k>1024 || q-(U(1)<<62)+256>error) return D::Infinity;
    return D::Infinity|D::Quiet;
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
    return D::Infinity|D::Quiet;
  }
  const uint32_t tail=uint32_t(q)&1023U;
  if(uint32_t(tail-(512U-error))<=2*error) return D::Infinity|D::Quiet;
  const U rounded=(q+511+((q>>10)&1))>>10;
  return (U(k+1022)<<52)+rounded;
}
