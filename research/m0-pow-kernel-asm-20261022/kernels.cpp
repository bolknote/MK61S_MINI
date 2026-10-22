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
__attribute__((always_inline)) inline U pow_integer128_approx_high64(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+(wide32(al,bh)>>32)+(wide32(ah,bl)>>32);
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
  // omitted cross-high parts and low-low product lose <7units; operand errors and
  // their product give the indicated conservative integer error radius.
  error+=al&&bl?8:(al||bl?4:(error?1:0));
  a.exponent=exponent;
  if(product.high>>63) ++a.exponent;
  else {
    product.high=(product.high<<1)|(product.low>>63);product.low<<=1;
    error<<=1;
  }
  a.high=product.high;a.low=product.low;a.error=error;
}
__attribute__((noinline,section(".m0_pow_near_one_refine")))
extern "C" void pow_integer128_square(PowInteger128 &a) {
  const U high=a.high,low=a.low;
  Product product=pow_integer128_square64(high);
  if(low) {
    const U cross=pow_integer128_approx_high64(low,high);
    U previous=product.low;
    product.low+=cross;product.high+=U(product.low<previous);
    previous=product.low;
    product.low+=cross;product.high+=U(product.low<previous);
  }
  unsigned error=2*a.error+(low?8:(a.error?1:0));
  a.exponent*=2;
  if(product.high>>63) ++a.exponent;
  else {
    product.high=(product.high<<1)|(product.low>>63);product.low<<=1;error<<=1;
  }
  a.high=product.high;a.low=product.low;a.error=error;
}
