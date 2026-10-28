#include "native_eabi_m0_atan_fast.inc"
__attribute__((always_inline)) inline bool atan_pack(U q,int e,U sign,unsigned error,U &result) {
  if(q<(U(1)<<62)) {q<<=1;--e;error*=2;}
  const unsigned high=unsigned(q>>63),shift=10+high;
  const uint32_t half=1U<<(shift-1),tail=uint32_t(q)&((half<<1)-1);
  if(uint32_t(tail-(half-error))<=2*error) return false;
  const uint32_t lo=uint32_t(q),hi=uint32_t(q>>32);
  const U retained=(U(hi>>shift)<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U rounded=retained+U(tail>half || (tail==half && (retained&1)));
  result=sign+(U(e+1021+int(high))<<52)+rounded;return true;
}
__attribute__((optimize("Os"),noinline,cold)) static U atan_inverse_correction(U original,U inverse,U angle,unsigned base,unsigned index,unsigned radius) {
  const U a=(original&D::Fraction)|D::Hidden,b=(inverse&D::Fraction)|D::Hidden;
  const int ea=int((original>>52)&0x7FFU)-1023,eb=int((inverse>>52)&0x7FFU)-1023;
  const Product product=multiply(a,b);
  const U residual=U(0)-product.low;
  const bool negative=bool(residual>>63);
  const Product p=multiply(negative?U(0)-residual:residual,b);
  const unsigned shift=unsigned(94-ea-2*eb);
  uint32_t delta=0;
  if(shift<128) {
    const unsigned n=shift-64;const U half=U(1)<<(n-1),tail=p.high&((half<<1)-1);
    delta=uint32_t(p.high>>n)+uint32_t(tail>half || (tail==half && (p.low||((p.high>>n)&1))));
  }
  if(index) delta=uint32_t((wide32(delta,refine_atan_inverse[index])+(U(1)<<31))>>32);
  angle=negative?angle+delta:angle-delta;
  U result;
  if(atan_pack(angle,1,original&D::Sign,base+2+(radius+63)/64,result)) return result;
  return D::Infinity|D::Quiet;
}
__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_atan(double original) {
  const U b=bits(original),m=b&D::Magnitude,sign=b&D::Sign;
  if(m<UINT64_C(0x3E40000000000000)) return original;
  if(m>D::Infinity) return real(b|D::Quiet);
  // The exact pi/2 is >4.97e-17 above the lower midpoint of its RNE cell.
  // For |x|>=2^55, pi/2-atan(|x|)<2^-55 and cannot leave that cell.
  if(m>=UINT64_C(0x4360000000000000)) return real(sign|UINT64_C(0x3FF921FB54442D18));
  if(m>=UINT64_C(0x3F90000000000000) && m<=UINT64_C(0x4050000000000000))
    return atan_fast(original);
  const bool invert=m>UINT64_C(0x3FF0000000000000);
  double x=real(m);unsigned inverse_error=0;
  if(invert) {
    x=1./x;const int exponent=int((bits(x)>>52)&0x7FFU)-1023;
    inverse_error=exponent>=-9?1U<<unsigned(exponent+9):1;
  }
  U result;
  int e;const U q=mk61_m0_atan_reduced(x,&e);
  if(!invert) {
    if(atan_pack(q,e,sign,8,result)) return real(result);
  } else {
    const U angle=compact_math::tables::half_pi-math62_right(q,unsigned(1-e));
    if(atan_pack(angle,1,sign,3+inverse_error,result)) return real(result);
    const unsigned index=m<=UINT64_C(0x4060000000000000)?1:0;
    result=atan_inverse_correction(m,bits(x),angle,3,index,inverse_error);
    if(result<D::Infinity) return real(result|sign);
  }
  return invert?atan_refine(original,m<=UINT64_C(0x4060000000000000)?1:0):mk61_m0_cr_atan(original);
}
