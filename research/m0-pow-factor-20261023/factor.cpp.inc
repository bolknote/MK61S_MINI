
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

__attribute__((noinline,section(".m0_pow_root_prefix")))
static U factor_decide(U xb,unsigned numerator,unsigned denominator,bool inverse,U cell,bool first) {
  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};
  if(numerator!=1) {
    const PowInteger128 base=power;
    unsigned bit=31-clz32(numerator);
    while(bit) {
      --bit;pow_integer128_square(power);
      if(numerator&(1U<<bit)) pow_integer128_base(power,base);
    }
  }
  return pow_root128_decide(power,denominator,inverse,cell,first);
}

__attribute__((noinline,section(".m0_pow_root_prefix")))
static U factor_pow(U xb,unsigned numerator,unsigned denominator,bool inverse) {
  const U undecided=D::Infinity|D::Quiet;
  unsigned depth=0;
  for(unsigned n=denominator;n>1;n>>=1) ++depth;
  const unsigned integral=numerator>>depth,remainder=numerator&(denominator-1);
  const Root64 base={((xb&D::Fraction)|D::Hidden)<<11,int(xb>>52)-1023,0};
  Root64 total={U(1)<<63,0,0};
  bool accumulated=false;
  if(integral) {
    total=base;accumulated=true;
    if(integral>1) {
      const Product square=pow_integer128_square64(base.high);
      total={square.high,2*base.exponent,unsigned(square.low!=0)};
      if(total.high>>63) ++total.exponent;
      else {total.high=(total.high<<1)|(square.low>>63);total.error=unsigned((square.low<<1)!=0);}
      unsigned bit=30-clz32(integral);
      if(integral&(1U<<bit)) factor64_base(total,base);
      while(bit) {
        --bit;factor64_square(total);
        if(integral&(1U<<bit)) factor64_base(total,base);
      }
    }
  }
  const bool inverse_estimate=inverse && !integral;
  if(remainder) {
    Root64 partial=base;
    unsigned bit=denominator>>1;
    if(inverse_estimate) partial=factor_inverse(xb);
    else root64_sqrt(partial);
    while(bit) {
      if(remainder&bit) {
        if(!accumulated) {total=partial;accumulated=true;}
        else factor64_multiply(total,partial);
      }
      bit>>=1;
      if(bit) root64_sqrt(partial);
    }
  }
  if(!accumulated || total.exponent < -1021 || total.exponent>1022 || total.error>=1024) return undecided;
  const U retained=total.high>>11;
  const unsigned tail=unsigned(total.high)&2047U,error=total.error;
  U cell=(U(total.exponent+1022)<<52)+retained;
  if(!(cell&D::Fraction) && tail+512U<=error) return undecided;
  if(!inverse || inverse_estimate) {
    if(!error) return cell+U(tail>1024U || (tail==1024U && (retained&1)));
    if(tail+error<1024U) return cell;
    if(tail>1024U+error) return cell+1;
    return factor_decide(xb,numerator,denominator,inverse,cell,true);
  }
  const U hint=cell+U(tail>1024U || (tail==1024U && (retained&1)));
  const U reciprocal=bits(1.0/real(hint));
  if(reciprocal<=UINT64_C(0x0010000000000001) || reciprocal>=UINT64_C(0x7FEFFFFFFFFFFFFE)) return undecided;
  const U fraction=reciprocal&D::Fraction;
  if(fraction<2 || fraction==D::Fraction)
    return factor_decide(xb,numerator,denominator,true,reciprocal,false);
  const U info=root64_distance(total,reciprocal);
  if(info==UINT64_MAX) return factor_decide(xb,numerator,denominator,true,reciprocal,false);
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
  return factor_decide(xb,numerator,denominator,true,reciprocal,false);
ambiguous_cell:
  return factor_decide(xb,numerator,denominator,true,cell,radius<=511U && bool(cell&D::Fraction));
}
