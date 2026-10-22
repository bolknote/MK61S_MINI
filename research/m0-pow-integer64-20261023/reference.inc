// Experimental checked negative integer powers. Normalized Q63 centers
// carry explicit radii; ambiguous midpoint decisions retain the existing
// arbitrary-hint128-bit backend. No hint has rounding authority.
struct PowInteger64 {U high;int exponent;unsigned error;};

__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_exact_extension")))
static void pow_integer64_square(PowInteger64 &a) {
  const U high=a.high;
  U product=exp_high_product(high,high);
  const unsigned upper=unsigned(high>>56)+1;
  unsigned error=((2*a.error*upper+255U)>>8)+4;
  a.exponent*=2;
  if(product>>63) ++a.exponent;
  else {product<<=1;error<<=1;}
  a.high=product;a.error=error;
}

__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_exact_extension")))
static void pow_integer64_base(PowInteger64 &a,const PowInteger64 &base) {
  U product=exp_high_product(a.high,base.high);
  const unsigned upper=unsigned(base.high>>56)+1;
  unsigned error=((a.error*upper+255U)>>8)+3;
  a.exponent+=base.exponent;
  if(product>>63) ++a.exponent;
  else {product<<=1;error<<=1;}
  a.high=product;a.error=error;
}

// Sign of the complete power interval times an exact normal midpoint -1.
__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_exact_extension")))
static U pow_integer64_distance(const PowInteger64 &a,U cell) {
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

__attribute__((always_inline)) inline int pow_integer64_side(int32_t distance,unsigned error) {
  if(distance>int32_t(error)) return 1;
  if(distance < -int32_t(error)) return -1;
  return 0;
}

__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_exact_extension")))
static int pow_integer64_boundary(const PowInteger64 &a,U cell) {
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

__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_exact_extension")))
static U pow_integer64_negative(U xb,uint32_t yh) {
  const U undecided=D::Infinity|D::Quiet;
  if(yh-0xC0080000U>0x00380000U || xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity)
    return undecided;
  const unsigned ey=((yh&0x7FFFFFFFU)>>20)-1023;
  const uint32_t significand=(yh&0xFFFFFU)|0x100000U;
  const unsigned shift=20-ey;
  if(significand&((1U<<shift)-1)) return undecided;
  const unsigned n=significand>>shift;
  const int exponent=int(xb>>52)-1023,scaled=exponent*int(n);
  if(scaled < -1022 || scaled+int(n)>1021) return undecided;
  const PowInteger64 base={((xb&D::Fraction)|D::Hidden)<<11,exponent,0};
  const Product square=pow_integer128_square64(base.high);
  PowInteger64 q={square.high,2*exponent,unsigned(square.low!=0)};
  if(q.high>>63) ++q.exponent;
  else {q.high=(q.high<<1)|(square.low>>63);q.error=unsigned((square.low<<1)!=0);}
  unsigned bit=30-clz32(n);
  if(n&(1U<<bit)) pow_integer64_base(q,base);
  while(bit) {
    --bit;pow_integer64_square(q);
    if(n&(1U<<bit)) pow_integer64_base(q,base);
  }
  if(q.exponent < -1022 || q.exponent>1023) return undecided;
  const U retained=q.high>>11,tail=q.high&2047U;
  const U hint=(U(q.exponent+1022)<<52)+retained+U(tail>1024U || (tail==1024U && (retained&1)));
  if(hint<UINT64_C(0x0010000000000000) || hint>=D::Infinity) return undecided;
  const U reciprocal=bits(1.0/real(hint));
  if(reciprocal<=UINT64_C(0x0010000000000001) || reciprocal>=UINT64_C(0x7FEFFFFFFFFFFFFE)) return undecided;
  const U fraction=reciprocal&D::Fraction;
  if(fraction<2 || fraction==D::Fraction) {
    U cell=reciprocal;
    int side=pow_integer64_boundary(q,cell);
    if(!side) return pow_dyadic128_checked(xb,U(yh)<<32,cell,q.error<=508U && bool(cell&D::Fraction));
    if(side<0) {
      ++cell;side=pow_integer64_boundary(q,cell);
      if(side>0) return reciprocal+1;
      if(!side) return pow_dyadic128_checked(xb,U(yh)<<32,cell,q.error<=508U && bool(cell&D::Fraction));
    } else {
      --cell;side=pow_integer64_boundary(q,cell);
      if(side<0) return reciprocal;
      if(!side) return pow_dyadic128_checked(xb,U(yh)<<32,cell,q.error<=508U && bool(cell&D::Fraction));
      --cell;side=pow_integer64_boundary(q,cell);
      if(side<0) return reciprocal-1;
      if(!side) return pow_dyadic128_checked(xb,U(yh)<<32,cell,q.error<=508U && bool(cell&D::Fraction));
    }
    return pow_dyadic128(xb,U(yh)<<32,reciprocal);
  }
  const U info=pow_integer64_distance(q,reciprocal);
  if(info==UINT64_MAX) return pow_dyadic128(xb,U(yh)<<32,reciprocal);
  int32_t distance=int32_t(uint32_t(info));
  unsigned error=unsigned(info>>43),step=unsigned(info>>32)&2047U;
  U cell=reciprocal;
  int side=pow_integer64_side(distance,error);
  if(!side) goto ambiguous_cell;
  if(side<0) {
    ++cell;distance+=int32_t(step);++error;
    side=pow_integer64_side(distance,error);
    if(side>0) return reciprocal+1;
    if(!side) goto ambiguous_cell;
  } else {
    --cell;distance-=int32_t(step);++error;
    side=pow_integer64_side(distance,error);
    if(side<0) return reciprocal;
    if(!side) goto ambiguous_cell;
    --cell;distance-=int32_t(step);++error;
    side=pow_integer64_side(distance,error);
    if(side<0) return reciprocal-1;
    if(!side) goto ambiguous_cell;
  }
  return pow_dyadic128(xb,U(yh)<<32,reciprocal);
ambiguous_cell:
  // The true product is within2*error<=1022 units of1. The outer
  // midpoint separation is>1023 units for a non-binade-start cell.
  // Hence RNE can only be cell or cell+1. Exact overlap still declines.
  return pow_dyadic128_checked(xb,U(yh)<<32,cell,error<=511U && bool(cell&D::Fraction));

}
