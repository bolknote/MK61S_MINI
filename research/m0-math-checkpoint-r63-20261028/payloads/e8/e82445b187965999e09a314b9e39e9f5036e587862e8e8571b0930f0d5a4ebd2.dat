// Checked small integer powers. No rounded intermediate doubles are used
// for the positive power. Reciprocal candidates are independently checked
// by multiplying both adjacent exact midpoints against the same enclosure.
struct PowInteger128 {U high,low;int exponent;unsigned error;};

extern "C" void pow_integer128_multiply(PowInteger128 &a,const PowInteger128 &b);

// Exact64-bit square with three32x32 products. Keeping the cross term
// once avoids the duplicated carry calculation in a generic64x64 product.
__attribute__((always_inline)) inline Product pow_integer128_square64(U a) {
  const uint32_t low=uint32_t(a),high=uint32_t(a>>32);
  const U bottom=wide32(low,low),cross=wide32(low,high),top=wide32(high,high);
  const U middle=(bottom>>32)+(U(uint32_t(cross))<<1);
  return {top+((cross>>32)<<1)+(middle>>32),(middle<<32)|uint32_t(bottom)};
}

extern "C" void pow_integer128_square(PowInteger128 &a);

__attribute__((always_inline)) inline U pow_integer128_hint(const PowInteger128 &a) {
  const U retained=a.high>>11,tail=a.high&2047U;
  const bool up=tail>1024U || (tail==1024U && (a.low || (retained&1)));
  return (U(a.exponent+1022)<<52)+retained+U(up);
}

// The sign of x^n*midpoint-1. Zero means that the enclosure is
// inconclusive, including an exact boundary. All midpoints here are normal.
__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_near_one_refine")))
static int pow_integer128_boundary(const PowInteger128 &power,U cell) {
  if(cell<UINT64_C(0x0010000000000000) || cell>=UINT64_C(0x7FEFFFFFFFFFFFFF)) return 0;
  const U coefficient=(((cell&D::Fraction)|D::Hidden)<<1)+1;
  const PowInteger128 midpoint={coefficient<<10,0,int(cell>>52)-1023,0};
  PowInteger128 q=power;
  pow_integer128_multiply(q,midpoint);
  if(q.exponent>0) return 1;
  if(q.exponent < -1) return -1;
  if(!q.exponent) {
    if(q.high>(U(1)<<63) || q.low>q.error) return 1;
    return 0;
  }
  if(q.high!=UINT64_MAX || q.low<U(0)-U(q.error)) return -1;
  return 0;
}

__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_integer_fixed")))
static U pow_integer128(U xb,U yb) {
  const U undecided=D::Infinity|D::Quiet,ym=yb&D::Magnitude;
  const int ey=int(ym>>52)-1023;
  if(uint32_t(yb) || unsigned(ey)>5 || xb<UINT64_C(0x0010000000000000) || xb>=D::Infinity)
    return undecided;
  const U sy=(ym&D::Fraction)|D::Hidden;
  const unsigned shift=52-unsigned(ey);
  if(sy&((U(1)<<shift)-1)) return undecided;
  const unsigned n=unsigned(sy>>shift);
  if(n>32) return undecided;
  const PowInteger128 base={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};
  PowInteger128 q=base;
  unsigned bit=31-clz32(n);
  while(bit) {
    --bit;
    pow_integer128_square(q);
    if(n&(1U<<bit)) pow_integer128_multiply(q,base);
  }
  if(q.exponent < -1022 || q.exponent>1023) return undecided;
  const U hint=pow_integer128_hint(q);
  if(!(yb&D::Sign)) {
    if(q.error) {
      const U tail=q.high&2047U;
      if((tail==1024U && q.low<=q.error) ||
         (tail==1023U && q.low>=U(0)-U(q.error))) return undecided;
    }
    return hint;
  }
  if(hint<UINT64_C(0x0010000000000000) || hint>=D::Infinity) return undecided;
  const U reciprocal=bits(1.0/real(hint));
  if(reciprocal<=UINT64_C(0x0010000000000001) || reciprocal>=UINT64_C(0x7FEFFFFFFFFFFFFE)) return undecided;
  const int side=pow_integer128_boundary(q,reciprocal);
  if(!side) return undecided;
  if(side<0) {
    // The reciprocal exceeds the midpoint above the hint.
    return pow_integer128_boundary(q,reciprocal+1)>0?reciprocal+1:undecided;
  }
  const int previous=pow_integer128_boundary(q,reciprocal-1);
  if(previous<0) return reciprocal;
  if(previous>0 && pow_integer128_boundary(q,reciprocal-2)<0) return reciprocal-1;
  return undecided;
}
