__attribute__((noinline,section(".m0_pow_root_prefix")))
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
