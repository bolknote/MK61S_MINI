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
__attribute__((noinline,section(".m0_pow_exact_extension"))) static U pow_integer128_approx_high64(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+pow_integer128_high32(al,bh)+U(pow_integer128_high32(ah,bl));
}
__attribute__((noinline,section(".m0_pow_exact_extension")))
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
__attribute__((noinline,section(".m0_pow_exact_extension")))
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
__attribute__((noinline,section(".m0_pow_exact_extension")))
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
__attribute__((noinline,section(".m0_pow_exact_extension")))
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
__attribute__((noinline,section(".m0_pow_exact_extension")))
static void root64_sqrt(Root64 &a) {
  const unsigned odd=unsigned(a.exponent)&1U;
  if(!a.error && a.high==(U(1)<<63) && !odd) {a.exponent/=2;return;}
  U center=pow_sqrt64_raw(a.high,odd);
  a.exponent=(a.exponent-int(odd))/2;
  a.error=((3*a.error+3)>>2)+3;
  if(!(center>>63)) {center=(center>>1)|(U(1)<<63);++a.exponent;}
  a.high=center;
}
__attribute__((noinline,section(".m0_pow_exact_extension")))
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

__attribute__((noinline,section(".m0_pow_exact_extension")))
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
__attribute__((noinline,section(".m0_pow_exact_extension")))
extern "C" U pow_root128(U xb,U yb) {
  const U undecided=D::Infinity|D::Quiet;
  if(uint32_t(yb) || uint32_t(xb>>52)-1U>=2046U) return undecided;
  const uint32_t yh=uint32_t(yb>>32),ym=yh&0x7FFFFFFFU;
  const int ey=int(ym>>20)-1023;
  if(unsigned(ey+7)>12U) return undecided;
  unsigned numerator=(ym&0xFFFFFU)|0x100000U;
  const unsigned zeros=31-clz32(numerator&(0U-numerator));
  numerator>>=zeros;
  const int shift=ey-20+int(zeros);
  if(numerator>32 || shift < -7 || shift>5) return undecided;
  unsigned denominator=1;
  if(shift>=0) {numerator<<=unsigned(shift);if(numerator>32) return undecided;}
  else denominator<<=unsigned(-shift);
  const bool inverse=bool(yh>>31);
  const int exponent=int(xb>>52)-1023,scaled=exponent*int(numerator);
  if(scaled < -1021*int(denominator) || scaled+int(numerator)>1022*int(denominator)) return undecided;
  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};
  if(numerator!=1) {
    const PowInteger128 base=power;
    unsigned bit=31-clz32(numerator);
    while(bit) {
      --bit;pow_integer128_square(power);
      if(numerator&(1U<<bit)) pow_integer128_base(power,base);
    }
  }
  if(denominator==1 && !inverse) {
    if(power.exponent < -1022 || power.exponent>1023) return undecided;
    const U retained=power.high>>11,tail=power.high&2047U;
    if(power.error && ((tail==1024U && power.low<=power.error) ||
       (tail==1023U && power.low>=U(0)-U(power.error)))) return undecided;
    return (U(power.exponent+1022)<<52)+retained+
      U(tail>1024U || (tail==1024U && (power.low || (retained&1))));
  }
  Root64 root={power.high,power.exponent,power.error?2U:unsigned(power.low!=0)};
  for(unsigned n=denominator;n>1;n>>=1) root64_sqrt(root);
  if(root.exponent < -1021 || root.exponent>1022 || root.error>=1024) return undecided;
  const U retained=root.high>>11;
  const unsigned tail=unsigned(root.high)&2047U,error=root.error;
  U cell=(U(root.exponent+1022)<<52)+retained;
  if(!(cell&D::Fraction) && tail+512U<=error) return undecided;
  if(!inverse) {
    if(!error) return cell+U(tail>1024U || (tail==1024U && (retained&1)));
    if(tail+error<1024U) return cell;
    if(tail>1024U+error) return cell+1;
    return pow_root128_decide(power,denominator,false,cell,true);
  }
  const U hint=cell+U(tail>1024U || (tail==1024U && (retained&1)));
  const U reciprocal=bits(1.0/real(hint));
  if(reciprocal<=UINT64_C(0x0010000000000001) || reciprocal>=UINT64_C(0x7FEFFFFFFFFFFFFE)) return undecided;
  const U fraction=reciprocal&D::Fraction;
  if(fraction<2 || fraction==D::Fraction) {
  cell=reciprocal;
  int side=root64_boundary(root,cell);
  if(!side) return pow_root128_decide(power,denominator,true,cell,error<=508U && bool(cell&D::Fraction));
  if(side<0) {
    ++cell;side=root64_boundary(root,cell);
    if(side>0) return reciprocal+1;
    if(!side) return pow_root128_decide(power,denominator,true,cell,error<=508U && bool(cell&D::Fraction));
  } else {
    --cell;side=root64_boundary(root,cell);
    if(side<0) return reciprocal;
    if(!side) return pow_root128_decide(power,denominator,true,cell,error<=508U && bool(cell&D::Fraction));
    --cell;side=root64_boundary(root,cell);
    if(side<0) return reciprocal-1;
    if(!side) return pow_root128_decide(power,denominator,true,cell,error<=508U && bool(cell&D::Fraction));
  }
  return pow_root128_decide(power,denominator,true,reciprocal,false);
  }
  const U info=root64_distance(root,reciprocal);
  if(info==UINT64_MAX) return pow_root128_decide(power,denominator,true,reciprocal,false);
  int32_t distance=int32_t(uint32_t(info));
  unsigned radius=unsigned(info>>43),step=unsigned(info>>32)&2047U;
  cell=reciprocal;
  int side=root64_side(distance,radius);
  if(!side) goto ambiguous_cell;
  if(side<0) {
    ++cell;distance+=int32_t(step);++radius;
    side=root64_side(distance,radius);
    if(side>0) return reciprocal+1;
    if(!side) goto ambiguous_cell;
  } else {
    --cell;distance-=int32_t(step);++radius;
    side=root64_side(distance,radius);
    if(side<0) return reciprocal;
    if(!side) goto ambiguous_cell;
    --cell;distance-=int32_t(step);++radius;
    side=root64_side(distance,radius);
    if(side<0) return reciprocal-1;
    if(!side) goto ambiguous_cell;
  }
  return pow_root128_decide(power,denominator,true,reciprocal,false);
ambiguous_cell:
  return pow_root128_decide(power,denominator,true,cell,radius<=511U && bool(cell&D::Fraction));
}
