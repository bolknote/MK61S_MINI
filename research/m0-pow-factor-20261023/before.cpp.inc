typedef int int32_t;
#define UINT64_MAX 0xFFFFFFFFFFFFFFFFULL
typedef unsigned long long U; typedef unsigned int uint32_t;
static_assert(sizeof(U)==8 && sizeof(uint32_t)==4);
struct Product {U high,low;};
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
__attribute__((always_inline)) inline Product multiply(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  const U p=wide32(al,bl),t=wide32(ah,bl)+(p>>32),v=wide32(al,bh)+uint32_t(t);
  return {wide32(ah,bh)+(t>>32)+(v>>32),(v<<32)|uint32_t(p)};
}
struct PowInteger128 {U high,low;int exponent;unsigned error;};
__attribute__((always_inline)) inline Product pow_integer128_square64(U a) {
  const uint32_t low=uint32_t(a),high=uint32_t(a>>32);
  const U bottom=wide32(low,low),cross=wide32(low,high),top=wide32(high,high);
  const U middle=(bottom>>32)+(U(uint32_t(cross))<<1);
  return {top+((cross>>32)<<1)+(middle>>32),(middle<<32)|uint32_t(bottom)};
}
__attribute__((always_inline)) inline uint32_t pow_integer128_high32(uint32_t a,uint32_t b) {
  const uint32_t al=a&65535U,ah=a>>16,bl=b&65535U,bh=b>>16;
  return ah*bh+((al*bh)>>16)+((ah*bl)>>16);
}
__attribute__((noinline,section(".m0_pow_root_prefix"))) static U pow_integer128_approx_high64(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+pow_integer128_high32(al,bh)+U(pow_integer128_high32(ah,bl));
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" void pow_integer128_base(PowInteger128 &a,const PowInteger128 &b) {
  const U ah=a.high,al=a.low,bh=b.high;
  const int exponent=a.exponent+b.exponent;
  Product product=multiply(ah,bh);
  if(al) {
    const U previous=product.low;
    product.low+=pow_integer128_approx_high64(al,bh);
    product.high+=U(product.low<previous);
  }
  unsigned error=a.error+(al?8U:(a.error?1U:0U));
  a.exponent=exponent;
  if(product.high>>63) ++a.exponent;
  else {
    product.high=(product.high<<1)|(product.low>>63);
    product.low<<=1;error<<=1;
  }
  a.high=product.high;a.low=product.low;a.error=error;
}

struct Root64 {U high;int exponent;unsigned error;};
#define UINT64_C(x) x##ULL
struct D {static constexpr U Fraction=0xFFFFFFFFFFFFFULL,Hidden=1ULL<<52,Infinity=0x7FF0000000000000ULL,Quiet=0x8000000000000ULL,Sign=1ULL<<63;};
extern "C" unsigned clz32(unsigned long) asm("_ZN7m0_eabi5clz32Em");
extern "C" void pow_integer128_square(PowInteger128 &);
extern "C" void pow_integer128_multiply(PowInteger128 &,const PowInteger128 &);
extern "C" U pow_sqrt64_raw(U,unsigned);
__attribute__((always_inline)) inline U bits(double x) {U a;__builtin_memcpy(&a,&x,8);return a;}
__attribute__((always_inline)) inline double real(U x) {double a;__builtin_memcpy(&a,&x,8);return a;}
__attribute__((always_inline)) inline U exp_high_product(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+(wide32(al,bh)>>32)+(wide32(ah,bl)>>32);
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" int root64_boundary(const Root64 &a,U cell) {
  if(cell<UINT64_C(0x0010000000000000) || cell>=UINT64_C(0x7FEFFFFFFFFFFFFF)) return 0;
  if(a.error>1048576U) return 0;
  const int scale=a.exponent+int(cell>>52)-1023;
  if(scale>0) return 1;
  if(scale < -2) return -1;
  const U midpoint=((((cell&D::Fraction)|D::Hidden)<<1)+1)<<10;
  const U product=exp_high_product(a.high,midpoint);
  const unsigned error=a.error+3;
  if(scale==-2) return product<U(0)-U(error)?-1:0;
  const U target=scale?(U(1)<<63):(U(1)<<62);
  if(product>=target) return product-target>error?1:0;
  return target-product>error?-1:0;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
static int root128_compare(const PowInteger128 &a,const PowInteger128 &b) {
  const int distance=a.exponent-b.exponent;
  if(distance>=2) return 1;
  if(distance<=-2) return -1;
  U ah=a.high,al=a.low,bh=b.high,bl=b.low;
  unsigned ae=a.error,be=b.error;
  if(distance<0) {
    al=(al>>1)|(ah<<63);ah>>=1;ae=(ae>>1)+1;
  } else if(distance>0) {
    bl=(bl>>1)|(bh<<63);bh>>=1;be=(be>>1)+1;
  }
  if(ah==bh && uint32_t(al>>32)==uint32_t(bl>>32)) {
    const uint32_t left=uint32_t(al),right=uint32_t(bl),error=ae+be;
    if(left>=right) return left-right>error?1:0;
    return right-left>error?-1:0;
  }
  if(ah==bh && al==bl) return 0;
  const bool smaller=ah<bh || (ah==bh && al<bl);
  const U hi=smaller?bh:ah,lo=smaller?bl:al;
  const U other_hi=smaller?ah:bh,other_lo=smaller?al:bl;
  const U low=lo-other_lo,high=hi-other_hi-U(lo<other_lo);
  if(high || low>U(ae+be)) return smaller?-1:1;
  return 0;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
static int root128_boundary(const PowInteger128 &power,unsigned denominator,bool inverse,U cell) {
  if(cell<UINT64_C(0x0010000000000000) || cell>=UINT64_C(0x7FEFFFFFFFFFFFFF)) return 0;
  const U coefficient=(((cell&D::Fraction)|D::Hidden)<<1)+1;
  PowInteger128 midpoint={coefficient<<10,0,int(cell>>52)-1023,0};
  // The decoder supplies1,2,4,...,128. This is the identical square
  // chain, without a base copy, CLZ or generic numerator bit tests.
  for(unsigned n=denominator;n>1;n>>=1) pow_integer128_square(midpoint);
  if(!inverse) return root128_compare(power,midpoint);
  pow_integer128_multiply(midpoint,power);
  if(midpoint.exponent>0) return -1;
  if(midpoint.exponent < -1) return 1;
  if(!midpoint.exponent) {
    if(midpoint.high>(U(1)<<63) || midpoint.low>midpoint.error) return -1;
    return 0;
  }
  if(midpoint.high!=~U(0) || midpoint.low<U(0)-U(midpoint.error)) return 1;
  return 0;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
static void root64_sqrt(Root64 &a) {
  const unsigned odd=unsigned(a.exponent)&1U;
  if(!a.error && a.high==(U(1)<<63) && !odd) {a.exponent/=2;return;}
  U center=pow_sqrt64_raw(a.high,odd);
  a.exponent=(a.exponent-int(odd))/2;
  a.error=((3*a.error+3)>>2)+3;
  if(!(center>>63)) {center=(center>>1)|(U(1)<<63);++a.exponent;}
  a.high=center;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" U pow_root128_decide(const PowInteger128 &power,unsigned denominator,bool inverse,U hint,bool first_cell) {
  const U undecided=D::Infinity|D::Quiet;
  const int side=root128_boundary(power,denominator,inverse,hint);
  if(!side) return undecided;
  if(first_cell) return side>0?hint+1:hint;
  if(side>0) return root128_boundary(power,denominator,inverse,hint+1)<0?hint+1:undecided;
  const int previous=root128_boundary(power,denominator,inverse,hint-1);
  if(previous>0) return hint;
  if(previous<0 && root128_boundary(power,denominator,inverse,hint-2)>0) return hint-1;
  return undecided;
}

__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" U root64_distance(const Root64 &a,U cell) {
  if(cell<UINT64_C(0x0010000000000000) || cell>=UINT64_C(0x7FEFFFFFFFFFFFFF) || a.error>65532U)
    return UINT64_MAX;
  const int scale=a.exponent+int(cell>>52)-1023;
  if(scale>0 || scale < -2) return UINT64_MAX;
  const U midpoint=((((cell&D::Fraction)|D::Hidden)<<1)+1)<<10;
  const U product=exp_high_product(a.high,midpoint);
  U magnitude;int32_t difference;
  if(scale==-2) {
    magnitude=U(0)-product;
    if(magnitude>0x3FFFFFFFU) return UINT64_MAX;
    difference=-int32_t(magnitude);
  } else {
    const U target=scale?(U(1)<<63):(U(1)<<62);
    const bool negative=product<target;
    magnitude=negative?target-product:product-target;
    if(magnitude>0x3FFFFFFFU) return UINT64_MAX;
    difference=negative?-int32_t(magnitude):int32_t(magnitude);
  }
  const unsigned info=((a.error+3)<<11)|unsigned(a.high>>53);
  return (U(info)<<32)|uint32_t(difference);
}
__attribute__((always_inline)) inline int root64_side(int32_t distance,unsigned error) {
  if(distance>int32_t(error)) return 1;
  if(distance < -int32_t(error)) return -1;
  return 0;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" void factor64_square(Root64 &a) {
  const U high=a.high;
  U product=exp_high_product(high,high);
  const unsigned upper=unsigned(high>>56)+1;
  unsigned error=((2*a.error*upper+255U)>>8)+4;
  a.exponent*=2;
  if(product>>63) ++a.exponent;
  else {product<<=1;error<<=1;}
  a.high=product;a.error=error;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" void factor64_base(Root64 &a,const Root64 &base) {
  U product=exp_high_product(a.high,base.high);
  const unsigned upper=unsigned(base.high>>56)+1;
  unsigned error=((a.error*upper+255U)>>8)+3;
  a.exponent+=base.exponent;
  if(product>>63) ++a.exponent;
  else {product<<=1;error<<=1;}
  a.high=product;a.error=error;
}
extern "C" unsigned mk61_m0_math_udiv32(unsigned,unsigned);
extern "C" const uint32_t factor_rsqrt_seeds[];
__attribute__((noinline,section(".m0_pow_root_prefix")))
static Root64 factor_inverse(U xb) {
  const U b=xb;U m=b&D::Fraction;int e=int(b>>52)-1023;
  m|=D::Hidden;
  const unsigned parity=unsigned(e)&1U,index=unsigned((m&D::Fraction)>>44);
  const uint32_t center=513+2*index;
  const U c=U(center)<<43;const bool negative=m<c;
  const U distance=negative?c-m:m-c;
  // Subtracting one before the shift also represents the exact2^43
  // endpoint without overflowing the 32-bit hardware numerator.
  const uint32_t numerator=distance?uint32_t((distance-1)>>11):0;
  const uint32_t t=numerator?mk61_m0_math_udiv32(numerator,center):0;
  const U z=wide32(t,t);const uint32_t z32=uint32_t(z>>32);
  const uint32_t quadratic=(3*z32+4)>>3;
  const uint32_t cube=(z32*(t>>16))>>16,cubic=(5*cube+8)>>4;
  const int32_t delta=(negative?int32_t(t):-int32_t(t))+2*int32_t(quadratic)+
    (negative?2*int32_t(cubic):-2*int32_t(cubic));
  const uint32_t base=factor_rsqrt_seeds[(parity<<8)|index];
  const uint32_t magnitude=uint32_t(delta<0?-delta:delta);
  const uint32_t correction=uint32_t((wide32(base,magnitude)+(U(1)<<32))>>33);
  uint32_t seed=delta<0?base-correction:base+correction;
  if(delta>=0 && seed<base) seed=0xFFFFFFFFU;
  const U argument=m<<(10+parity),square=wide32(seed,seed);
  const U product=exp_high_product(argument,square);
  const U factor=(U(3)<<62)-product;
  const U p0=wide32(uint32_t(factor),seed);
  const U p1=wide32(uint32_t(factor>>32),seed)+(p0>>32);
  const U q=p1;
  const int scale=-(e-int(parity))/2;
  if(q>>63) return {q,scale,24};
  return {q<<1,scale-1,48};
}
