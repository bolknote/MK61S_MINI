// Private tangent product with a separately certified <=6.5-unit enclosure.
__attribute__((const)) U mk61_m0_product62(U a,U b);
// Logarithm residual products: a <= 2^41 (Q46) or a <= 2^48 (Q54).
// Enclosures are certified by generate_m0_log70_table.py.
__attribute__((const)) U mk61_m0_log_product46(U a,U b);
__attribute__((const)) U mk61_m0_log_product54(U a,U b);
// Direct Q70 product with <35/64-unit error; a <2^59, b <2^48.
__attribute__((const)) U mk61_m0_log_cube70(U a,U b);
// Project-owned relative Q62 kernels. Each inline approximate product below has
// operands below 2^63 and differs from the real Q62 product by <= 2.5 units.
// Normalized results retain nine guard bits before binary64 rounding.
__attribute__((always_inline)) inline U math62_product(U a,U b) {
  if(!a || !b) return 0;
  const U cross=wide32(uint32_t(a),uint32_t(b>>32))+wide32(uint32_t(a>>32),uint32_t(b));
  const U high=wide32(uint32_t(a>>32),uint32_t(b>>32))+(cross>>32);
  return ((high<<2)|(uint32_t(cross)>>30))+2+((uint32_t(cross)>>29)&1);
}
__attribute__((always_inline)) inline U math62_right(U a,unsigned n) {
  if(!n) return a;
  if(n>=64) return n==64 && a>(U(1)<<63);
  const U half=U(1)<<(n-1),tail=a&((half<<1)-1),q=a>>n;
  return q+(tail>half || (tail==half && (q&1)));
}
__attribute__((always_inline)) inline U math62_square(U q,int e) {
  if(e<=-32) return 0;
  return math62_right(exp_high_product(q,q),unsigned(-2*e));
}
__attribute__((always_inline)) inline U math62_third(U a) {
  const uint32_t hi=uint32_t(a>>32),lo=uint32_t(a);
  const uint32_t qh=uint32_t(wide32(hi,0xAAAAAAABU)>>33);
  const uint32_t ql=uint32_t(wide32(lo,0xAAAAAAABU)>>33);
  const uint32_t rh=hi-3*qh,tail=rh+lo-3*ql,carry=tail>=3;
  const U q=(U(qh)<<32)|uint32_t(ql+rh*0x55555555U+carry);
  return q+U(tail-3*carry>=2);
}
__attribute__((always_inline)) inline U math62_scale32(U a,uint32_t b) {
  const U low=wide32(uint32_t(a),b);
  const U high=wide32(uint32_t(a>>32),b)+(low>>32);
  const uint32_t tail=uint32_t(low);
  return high+U(tail>0x80000000U || (tail==0x80000000U && (high&1)));
}
__attribute__((always_inline)) inline U math62_scale40(U a,uint32_t low_coefficient,unsigned high_coefficient) {
  const U low=wide32(uint32_t(a),low_coefficient);
  const U high=wide32(uint32_t(a>>32),low_coefficient)+(low>>32)+
    (high_coefficient==2?(a<<1):high_coefficient==10?(a<<3)+(a<<1):
     high_coefficient==34?(a<<5)+(a<<1):(a<<5)+(a<<4)+(a<<1)+a);
  const U q=high>>8;const unsigned tail=unsigned(high)&255;
  return q+U(tail>128 || (tail==128 && (uint32_t(low)||(q&1))));
}
__attribute__((always_inline)) inline double math62_pack(U q,int e,U sign) {
  if(q<(U(1)<<62)) {q<<=1;--e;}
  const unsigned high=unsigned(q>>63),shift=10+high;
  const uint32_t lo=uint32_t(q),hi=uint32_t(q>>32),half=1U<<(shift-1),tail=lo&((half<<1)-1);
  U m=(U(hi>>shift)<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  m+=tail>half || (tail==half && (m&1));
  return real(sign+(U(e+1021+int(high))<<52)+m);
}
__attribute__((always_inline)) inline U math62_input(double x,double tail,int &e) {
  const U b=bits(x),t=bits(tail);
  e=int((b>>52)&0x7FFU)-1022;
  U q=((b&D::Fraction)|D::Hidden)<<10;
  if(t&D::Magnitude) {
    const unsigned te=unsigned((t>>52)&0x7FFU);
    const U m=(t&D::Fraction)|(te?D::Hidden:0);
    const int shift=(te?int(te)-1023:-1022)-e+11;
    const U correction=shift<0?math62_right(m,unsigned(-shift)):m<<unsigned(shift);
    q=((b^t)&D::Sign)?q-correction:q+correction;
  }
  return q;
}
__attribute__((optimize("Os"))) void math62_sincos_small(U q,int e,U sign,double* out,unsigned mask) {
  const U one=U(1)<<62;
  if(e<=-27) {
    if(mask&1) out[0]=math62_pack(q,e,sign);
    if(mask&2) out[1]=1.0;
    return;
  }
  const U z=math62_square(q,e);
  if(e<=-13) {
    // Below 2^-14 the omitted sine/cosine terms are below 0.54 ULP.
    if(mask&1) out[0]=math62_pack(math62_product(q,one-((math62_third(z)+1)>>1)),e,sign);
    if(mask&2) out[1]=math62_pack(one-((z+1)>>1),1,0);
    return;
  }
  const U z2=math62_product(z,z);
  if(mask&1) {
    // sin(x)/x = 1-z/6+z^2*(1/120-z/5040), |x| <= 1/64.
    const uint32_t c=0x22222222U-uint32_t(wide32(uint32_t(z>>22),852176U)>>32);
    const U factor=one-((math62_third(z)+1)>>1)+math62_scale40(z2,c,2);
    out[0]=math62_pack(math62_product(q,factor),e,sign);
  }
  if(mask&2) {
    const uint32_t c=0xAAAAAAABU-uint32_t(wide32(uint32_t(z>>22),5965232U)>>32);
    const U result=one-((z+1)>>1)+math62_scale40(z2,c,10);
    out[1]=math62_pack(result,1,0);
  }
}
__attribute__((optimize("Os"))) void mk61_m0_sincos_small(double x,double tail,double* out,unsigned mask) {
  if((bits(x)&D::Magnitude)<UINT64_C(0x3E40000000000000)) {
    if(mask&1) out[0]=x+tail;
    if(mask&2) out[1]=1.0;
    return;
  }
  int e;const U q=math62_input(x,tail,e);
  math62_sincos_small(q,e,bits(x)&D::Sign,out,mask);
}
__attribute__((optimize("Os"))) double math62_tan_small(U q,int e,U sign) {
  const U z=math62_square(q,e),one=U(1)<<62;
  if(!z) return math62_pack(q,e,sign);
  U factor=one+math62_third(z);
  if(e>-13) {
    const U z2=math62_product(z,z);
    // tan(x)/x through x^8, |x| <= 1/64. The omitted term is
    // below 2^-66; Q32 coefficients retain the relative guard bits.
    const uint32_t c=572662306U+
      uint32_t(wide32(uint32_t(z>>30),231791886U)>>32)+
      uint32_t(wide32(uint32_t(z2>>30),93928738U)>>32);
    factor+=math62_scale32(z2,c);
  }
  return math62_pack(math62_product(q,factor),e,sign);
}
__attribute__((optimize("Os"))) double mk61_m0_tan_small(double x,double tail) {
  if((bits(x)&D::Magnitude)<UINT64_C(0x3E40000000000000)) return x+tail;
  int e;const U q=math62_input(x,tail,e);
  return math62_tan_small(q,e,bits(x)&D::Sign);
}
__attribute__((optimize("Os"))) U mk61_m0_atan_reduced(double x,int* exponent) {
  int e;const U q=math62_input(x,0.0,e),z=math62_square(q,e),one=U(1)<<62;
  *exponent=e;
  if(!z) return q;
  const U z2=math62_product(z,z);
  const uint32_t seventh=uint32_t(wide32(uint32_t(z>>22)+3,2454267027U)>>34);
  const uint32_t ninth=((uint32_t(z2>>22)+4)*7282U)>>16;
  const uint32_t coefficient=0x33333333U-seventh+ninth;
  return math62_product(q,one-math62_third(z)+math62_scale40(z2,coefficient,51));
}
__attribute__((always_inline)) inline double math62_log_near_one(U b) {
  // Called only for |x-1| <= 2^-14; the first omitted relative term
  // f^4/5 is below 13 Q62 units, with nine guard bits at the output.
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  if(!a) return 0.0;
  const unsigned leading=clz64(a);
  const U q=a<<(leading-1),one=U(1)<<62,half=a>>1;
  if(a<=(U(1)<<35)) {
    const U factor=one+(negative?half:U(0)-half);
    return math62_pack(math62_product(q,factor),2-int(leading),negative?D::Sign:0);
  }
  // a <= 2^56. Two products approximate a*a/2^62 within 1.001
  // units; the omitted low square contributes less than 2^-12.
  const uint32_t t=uint32_t(a>>25);
  const U z=(wide32(t,t)>>12)+(wide32(t,uint32_t(a)&0x1FFFFFFU)>>36)+1;
  if(a<=(U(1)<<42)) {
    const U factor=one+(negative?half:U(0)-half)+math62_third(z);
    return math62_pack(math62_product(q,factor),2-int(leading),negative?D::Sign:0);
  }
  const U cube=math62_product(a,z);
  const U quarter=(cube+2)>>2;
  const U factor=(U(1)<<62)+(negative?half:U(0)-half)+math62_third(z)+
    (negative?quarter:U(0)-quarter);
  return math62_pack(math62_product(q,factor),2-int(leading),negative?D::Sign:0);
}
__attribute__((always_inline)) inline int64_t math62_log_correction(int64_t h) {
  if(!h) return 0;
  const bool negative=h<0;const U a=negative?U(0)-U(h):U(h);
  const uint32_t t=uint32_t(a>>22);
  const U z=(wide32(t,t)>>18)+(wide32(t,uint32_t(a)&0x3FFFFFU)>>39)+1;
  const U cube=math62_product(a,z);
  const uint32_t fifth=uint32_t(wide32(uint32_t(z>>26),0xCCCCCCCDU)>>34);
  const uint32_t sixth=uint32_t(wide32(uint32_t(cube>>26),0xAAAAAAABU)>>34);
  const uint32_t quarter=uint32_t(a>>28);
  const uint32_t c=0x55555555U+(negative?quarter:0U-quarter)+fifth+(negative?sixth:0U-sixth);
  const U low=wide32(uint32_t(cube),c);
  const U high=wide32(uint32_t(cube>>32),c)+(low>>32)+cube+(cube<<2);
  const U q=high>>4;const unsigned tail=unsigned(high)&15;
  const U third=q+U(tail>8 || (tail==8 && (uint32_t(low)||(q&1))));
  const int64_t second=int64_t((z+1)>>1);
  return negative?-int64_t(a)-second-int64_t(third):int64_t(a)-second+int64_t(third);
}
__attribute__((always_inline)) inline double math62_pack96(U low,uint32_t high,U sign) {
  unsigned shift;int bias;
  if(high) {
    const unsigned width=32-clz32(high);
    shift=width+11;bias=int(width)+1023;
  } else {
    const unsigned width=64-clz64(low);
    shift=width-53;bias=int(width)+959;
  }
  // Here 3 <= shift <= 21; only the low 32-bit word contains rounding bits.
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32),half=1U<<(shift-1),tail=lo&((half<<1)-1);
  U q=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  q+=tail>half || (tail==half && (q&1));
  return real(sign+(U(bias)<<52)+q);
}
__attribute__((always_inline)) inline double math62_log_interval(U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return math62_log_near_one(b);
  if(negative && n==128) --n;
  const unsigned index=negative?128-n:128+n;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  if(!delta) return real(bits(math62_pack96(log_near_table[index-1][1],0,negative?D::Sign:0))-(U(8)<<52));
  const Product product=multiply(delta,log_near_table[index-1][0]);
  const U h0=(product.high<<10)|(product.low>>54),tail=product.low&((U(1)<<54)-1),half=U(1)<<53;
  const U h=h0+U(tail>half || (tail==half && (h0&1)));
  // |h| <= 1/8065. In Q70 the square needs two wide products;
  // the cube and fourth power need one each. Total accumulated error
  // stays below four Q70 units, including certified table rounding.
  const uint32_t t=uint32_t(h>>26);
  const U z=(wide32(t,t)>>18)+(wide32(t,uint32_t(h)&0x3FFFFFFU)>>43)+1;
  const uint32_t hr=uint32_t((h+(1U<<25))>>26),zr=uint32_t((z+(1U<<12))>>13);
  const uint32_t cube=uint32_t((wide32(hr,zr)+(U(1)<<30))>>31);
  const uint32_t q=uint32_t(wide32(cube,0xAAAAAAABU)>>33);
  const U third=q+U(cube-3*q>=2);
  const U fourth=(wide32(zr,zr)+(U(1)<<43))>>44;
  const U even=((z+1)>>1)+((fourth+2)>>2),odd=h+third;
  const U correction=subtract?odd+even:odd-even;
  U low=log_near_table[index-1][1];uint32_t high=0;
  if(subtract==negative) {const U before=low;low+=correction;high=low<before;}
  else low-=correction;
  return real(bits(math62_pack96(low,high,negative?D::Sign:0))-(U(8)<<52));
}
__attribute__((optimize("Os"))) double mk61_m0_ln_approx(double x) {
  const U b=bits(x);
  if(b>=UINT64_C(0x3FEF800000000000) && b<=UINT64_C(0x3FF0400000000000))
    return math62_log_interval(b);
  const int k=int((b>>52)&0x7FFU)-1023;
  const U m=((b&D::Fraction)|D::Hidden)<<10;
  const unsigned j=unsigned((b&D::Fraction)>>44);
  const Product product=multiply(m,log_table[j][0]);
  const U q=(product.high<<1)|(product.low>>63),tail=product.low&((U(1)<<63)-1);
  const U ratio=q+U(tail>(U(1)<<62) || (tail==(U(1)<<62) && (q&1)));
  const int64_t lm=int64_t(log_table[j][1])+math62_log_correction(int64_t(ratio-(U(1)<<62)));
  if(!k) return math62_pack96(U(lm),0,0);
  const uint32_t n=uint16_t(k<0?-k:k);
  const U lower=wide32(uint32_t(log_two),n);
  const U upper=wide32(uint32_t(log_two>>32),n)+(lower>>32);
  U low=(upper<<32)|uint32_t(lower);uint32_t high=uint32_t(upper>>32);
  const int64_t correction=k<0?-lm:lm;
  if(correction<0) {const U old=low;low-=U(-correction);high-=old<U(-correction);}
  else {const U old=low;low+=U(correction);high+=low<old;}
  return math62_pack96(low,high,k<0?D::Sign:0);
}
