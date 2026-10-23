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
__attribute__((always_inline)) inline unsigned pow_bit5(unsigned n) {
  unsigned bit=0;
  if(n>=8) {n>>=3;bit=3;}
  if(n>=2) {n>>=1;++bit;}
  if(n>=2) ++bit;
  return bit;
}

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
__attribute__((noinline,section(".m0_pow_root_prefix"))) extern "C" U pow_integer128_approx_high64(U a,U b) {
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
__attribute__((always_inline)) inline static void pow_midpoint_square(PowInteger128 &a) {
  const U high=a.high,low=a.low;
  Product product=pow_integer128_square64(high);
  if(low) {
    const U cross=pow_integer128_approx_high64(low,high);
    const U previous=product.low;
    product.low+=cross<<1;
    product.high+=(cross>>63)+U(product.low<previous);
  }
  unsigned error=2*a.error+(low?16:(a.error?1:0));
  a.exponent*=2;
  if(product.high>>63) ++a.exponent;
  else {
    product.high=(product.high<<1)|(product.low>>63);product.low<<=1;error<<=1;
  }
  a.high=product.high;a.low=product.low;a.error=error;
}
__attribute__((noinline,section(".m0_pow_boundary_exact")))
static int root128_boundary(const PowInteger128 &power,unsigned denominator,bool inverse,U cell) {
  if(cell<UINT64_C(0x0010000000000000) || cell>=UINT64_C(0x7FEFFFFFFFFFFFFF)) return 0;
  const U coefficient=(((cell&D::Fraction)|D::Hidden)<<1)+1;
  PowInteger128 midpoint={coefficient<<10,0,int(cell>>52)-1023,0};
  // The decoder supplies1,2,4,...,128. This is the identical square
  // chain, without a base copy, CLZ or generic numerator bit tests.
  for(unsigned n=denominator;n>1;n>>=1) pow_midpoint_square(midpoint);
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
__attribute__((always_inline))
inline static void root64_sqrt(Root64 &a) {
  const unsigned odd=unsigned(a.exponent)&1U;
  if(!a.error && a.high==(U(1)<<63) && !odd) {a.exponent>>=1;return;}
  U center=pow_sqrt64_raw(a.high,odd);
  a.exponent>>=1;
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
__attribute__((noinline,section(".m0_pow_tail_extra")))
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
  const int scale=-(e>>1);
  if(q>>63) return {q,scale,24};
  return {q<<1,scale-1,48};
}

__attribute__((noinline,section(".m0_pow_near_one_refine")))
extern "C" void pow_integer128_multiply(PowInteger128 &a,const PowInteger128 &b) {
  const U ah=a.high,al=a.low,bh=b.high,bl=b.low;
  const int exponent=a.exponent+b.exponent;
  unsigned error=a.error+b.error;
  Product product=multiply(ah,bh);
  if(al) {
    const U previous=product.low;
    product.low+=pow_integer128_approx_high64(al,bh);product.high+=U(product.low<previous);
  }
  if(bl) {
    const U previous=product.low;
    product.low+=pow_integer128_approx_high64(ah,bl);product.high+=U(product.low<previous);
  }
  // If both low words vanish, the mantissa product is exact. Otherwise
  // omitted cross-high parts and low-low product lose <15units; operand errors and
  // their product give the indicated conservative integer error radius.
  error+=al&&bl?16:(al||bl?8:(error?1:0));
  a.exponent=exponent;
  if(product.high>>63) ++a.exponent;
  else {
    product.high=(product.high<<1)|(product.low>>63);product.low<<=1;
    error<<=1;
  }
  a.high=product.high;a.low=product.low;a.error=error;
}
__attribute__((noinline,section(".m0_pow_square_fixed")))
extern "C" void pow_integer128_square(PowInteger128 &a) {
  const U high=a.high,low=a.low;
  Product product=pow_integer128_square64(high);
  if(low) {
    const U cross=pow_integer128_approx_high64(low,high);
    const U previous=product.low;
    product.low+=cross<<1;
    product.high+=(cross>>63)+U(product.low<previous);
  }
  unsigned error=2*a.error+(low?16:(a.error?1:0));
  a.exponent*=2;
  if(product.high>>63) ++a.exponent;
  else {
    product.high=(product.high<<1)|(product.low>>63);product.low<<=1;error<<=1;
  }
  a.high=product.high;a.low=product.low;a.error=error;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" void factor64_multiply(Root64 &a,const Root64 &b) {
  U center=exp_high_product(a.high,b.high);
  const unsigned ua=unsigned(a.high>>56)+1,ub=unsigned(b.high>>56)+1;
  unsigned error=((a.error*ub+b.error*ua+255)>>8)+4;
  a.exponent+=b.exponent;
  if(center>>63) ++a.exponent;
  else {center<<=1;error<<=1;}
  a.high=center;a.error=error;
}

__attribute__((noinline,section(".m0_pow_tail_extra")))
static U factor_decide(U xb,unsigned numerator,unsigned denominator,bool inverse,U cell,bool first) {
  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};
  if(numerator!=1) {
    const PowInteger128 base=power;
    unsigned bit=pow_bit5(numerator);
    while(bit) {
      --bit;pow_integer128_square(power);
      if(numerator&(1U<<bit)) pow_integer128_base(power,base);
    }
  }
  return pow_root128_decide(power,denominator,inverse,cell,first);
}

__attribute__((always_inline)) inline static void factor_base_inline(Root64 &a,const Root64 &base) {
  U product=exp_high_product(a.high,base.high);
  const unsigned upper=unsigned(base.high>>56)+1;
  unsigned error=((a.error*upper+255U)>>8)+3;
  a.exponent+=base.exponent;
  if(product>>63) ++a.exponent;
  else {product<<=1;error<<=1;}
  a.high=product;a.error=error;
}
__attribute__((noinline,section(".m0_pow_root_prefix")))
static U factor_pow(U xb,unsigned numerator,unsigned depth,bool inverse) {
  const U undecided=D::Infinity|D::Quiet;
  const unsigned denominator=1U<<depth;
  Root64 total;
  if(!inverse) {
    // The caller supplies an odd p<2*q. Starting at bit0=1, each
    // step halves the current exponent, then adds the next binary bit.
    // After d steps the exponent is exactly p/2^d. Only exact-base
    // products are needed; each intervening root contracts the radius.
    const Root64 base={((xb&D::Fraction)|D::Hidden)<<11,int(xb>>52)-1023,0};
    total=base;
    for(unsigned bit=2;bit<=denominator;bit<<=1) {
      root64_sqrt(total);
      if(numerator&bit) factor_base_inline(total,base);
    }
  } else {
    // The caller admits only proper negative fractions here. The
    // reciprocal-root seed already represents the first binary term.
    Root64 partial=factor_inverse(xb);
    bool accumulated=false;
    for(unsigned bit=denominator>>1;bit;bit>>=1) {
      if(numerator&bit) {
        if(!accumulated) {total=partial;accumulated=true;}
        else factor64_multiply(total,partial);
      }
      if(bit>1) root64_sqrt(partial);
    }
    if(!accumulated) return undecided;
  }
  if(total.exponent < -1021 || total.exponent>1022 || total.error>=1024) return undecided;
  const U retained=total.high>>11;
  const unsigned tail=unsigned(total.high)&2047U,error=total.error;
  const U cell=(U(total.exponent+1022)<<52)+retained;
  if(!(cell&D::Fraction) && tail+512U<=error) return undecided;
  if(!error) return cell+U(tail>1024U || (tail==1024U && (retained&1)));
  if(tail+error<1024U) return cell;
  if(tail>1024U+error) return cell+1;
  return factor_decide(xb,numerator,denominator,inverse,cell,true);
}

__attribute__((noinline,section(".m0_pow_root_prefix")))
extern "C" U pow_root128(U xb,U yb) {
  const U undecided=D::Infinity|D::Quiet;
  if(uint32_t(yb) || uint32_t(xb>>52)-1U>=2046U) return undecided;
  const uint32_t yh=uint32_t(yb>>32),ym=yh&0x7FFFFFFFU;
  const int ey=int(ym>>20)-1023;
  if(unsigned(ey+7)>12U) return undecided;
  if(ym&65535U) return undecided;
  unsigned numerator=((ym>>16)&15U)|16U;
  int shift=ey-4;
  if(!(numerator&3U)) {numerator>>=2;shift+=2;}
  if(!(numerator&1U)) {numerator>>=1;++shift;}
  if(!(numerator&1U)) {numerator>>=1;++shift;}
  if(shift < -7 || shift>5) return undecided;
  unsigned denominator=1;
  if(shift>=0) {numerator<<=unsigned(shift);if(numerator>32) return undecided;}
  else denominator<<=unsigned(-shift);
  const bool inverse=bool(yh>>31);
  const int exponent=int(xb>>52)-1023,scaled=exponent*int(numerator);
  if(scaled < -1021*int(denominator) || scaled+int(numerator)>1022*int(denominator)) return undecided;
  if(denominator!=1 && (inverse?numerator<denominator:(numerator>3 && numerator<2*denominator))) return factor_pow(xb,numerator,unsigned(-shift),inverse);
  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};
  if(numerator!=1) {
    const PowInteger128 base=power;
    unsigned bit=pow_bit5(numerator);
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
