#include "api.h"
#include "integer.inc"
#include "seed-inline.inc"
extern "C" void fo_root_setup(void){interp_blend_setup();}
extern "C" U fo_sqrt_seed_cpu(U m,U parity){return cpu_sqrt_seeds(m,parity);}
extern "C" U fo_sqrt_seed_interp(U m,U parity){return interp_sqrt_seeds(m,parity);}
template<U(*F)(U,U)> static U sqrt_slow(U a){const U m=a&D::Magnitude;if(!m)return a;if(m>=D::Infinity)return m==D::Infinity && !(a&D::Sign)?a:a|D::Infinity|D::Quiet;if(a&D::Sign)return D::Infinity|D::Quiet;const unsigned shift=clz64(m)-11;const int e=-1022-int(shift);const unsigned odd=unsigned(e)&1U;const U s=m<<shift;const U result=F((s&D::Fraction)|(U(1023+odd)<<52),0);return result-(U(-(e-int(odd))/2)<<52);}
extern "C" U fo_sqrt_base_slow(U a){return sqrt_slow<fo_sqrt_base>(a);}
extern "C" U fo_sqrt_new_cpu_slow(U a){return sqrt_slow<fo_sqrt_new_cpu>(a);}
extern "C" U fo_sqrt_new_interp_slow(U a){return sqrt_slow<fo_sqrt_new_interp>(a);}
extern "C" U fo_sqrt_skip_refine_slow(U a){return sqrt_slow<fo_sqrt_skip_refine>(a);}
__attribute__((optimize("Os"),noinline)) static int pow_rsqrt_boundary(U m,unsigned parity,U lower) {
  const U midpoint=(((lower&D::Fraction)|D::Hidden)<<1)+1;
  const int exponent=int(lower>>52)-1023;
  const Product square=multiply(midpoint,midpoint);
  const Product lo=multiply(square.low,m),hi=multiply(square.high,m);
  const U middle=lo.high+hi.low,upper=hi.high+U(middle<lo.high);
  const unsigned bit=unsigned(158-int(parity)-2*exponent);
  if(bit<128 || bit>=192) return 2;
  const U target=U(1)<<(bit-128);
  if(upper<target) return -1;
  if(upper>target || middle || lo.low) return 1;
  return 0;
}
template<unsigned SEED> __attribute__((always_inline)) inline double rsqrt_core(double x) {
  const U b=bits(x);
  if(!(b&D::Magnitude))return real((b&D::Sign)|D::Infinity);
  if((b&D::Magnitude)>D::Infinity)return real(b|D::Quiet);
  if(b&D::Sign)return real(D::Infinity|D::Quiet);
  if(b==D::Infinity)return 0.0;
  U m=b&D::Fraction;int e=int(b>>52)-1023;
  if(b>>52) m|=D::Hidden;
  else {const unsigned shift=clz64(m)-11;m<<=shift;e=-1022-int(shift);}
  const unsigned parity=unsigned(e)&1U;
  const uint32_t seed=SEED==0?uint32_t(current_rsqrt_seed(m,parity)):
    SEED==1?uint32_t(cpu_rsqrt_seed(m,parity)):
    SEED==2?uint32_t(interp_rsqrt_seed(m,parity)):
    uint32_t(linear_seed<false>(m,parity,linear_rsqrt_seeds))<<1;
  const U argument=m<<(10+parity),square=wide32(seed,seed);
  const U product=exp_high_product(argument,square);
  const U factor=(U(3)<<62)-product;
  const U p0=wide32(uint32_t(factor),seed);
  const U p1=wide32(uint32_t(factor>>32),seed)+(p0>>32);
  const U q=p1;
  const unsigned tail=unsigned(q)&1023U;
  const int scale=-(e-int(parity))/2;
  if(uint32_t(tail-(512U-24U))>48U) {
    const U rounded=(q+511+((q>>10)&1))>>10;
    return real((U(1021+scale)<<52)+rounded);
  }
  U lower=(U(1021)<<52)+(q>>10);
  const int compare=pow_rsqrt_boundary(m,parity,lower);
  if(compare==2) return real(D::Infinity|D::Quiet); // Outside the proved normalized boundary range.
  lower+=compare<0 || (!compare && (lower&1));
  return real((lower&D::Fraction)|(U(int(lower>>52)+scale)<<52));
}
extern "C" __attribute__((noipa)) U fo_rsqrt_base(U x,U){return bits(rsqrt_core<0>(real(x)));}
extern "C" __attribute__((noipa)) U fo_rsqrt_new_cpu(U x,U){return bits(rsqrt_core<1>(real(x)));}
extern "C" __attribute__((noipa)) U fo_rsqrt_new_interp(U x,U){return bits(rsqrt_core<2>(real(x)));}
extern "C" __attribute__((noipa)) U fo_rsqrt_skip_refine(U x,U){return bits(rsqrt_core<3>(real(x)));}
