// Private implementation, included inside the adapter's backend namespace.
// Exact binary64 intervals and nearest-even decimal parsing use bounded
// stack integers instead of cached-power tables.

// Exact bounded integer arithmetic: binary64's decimal conversion needs at
// most 36 limbs for subnormals and 17 significant decimal input digits.
struct Big {
  uint32_t word[36]; unsigned size;
  explicit Big(uint64_t v=0):size(v>>32?2:1) {word[0]=uint32_t(v);if(size==2)word[1]=uint32_t(v>>32);}
  Big(const Big& b):size(b.size) {memcpy(word,b.word,size*4);}
  __attribute__((noinline)) int compare(const Big& b) const {
    if(size!=b.size)return size>b.size?1:-1;
    for(unsigned i=size;i--;)if(word[i]!=b.word[i])return word[i]>b.word[i]?1:-1;
    return 0;
  }
  __attribute__((noinline)) void multiply(unsigned m) {
    uint64_t carry=0;
    for(unsigned i=0;i<size;++i){carry+=uint64_t(word[i])*m;word[i]=uint32_t(carry);carry>>=32;}
    if(carry){assert(size<36);word[size++]=uint32_t(carry);}
  }
  __attribute__((noinline)) void shift(unsigned shift) {
    const unsigned whole=shift/32,bits=shift%32,old=size;
    assert(this->bits()+shift<=36*32);
    uint32_t carry=0;
    for(unsigned i=0;i<old;++i){const uint32_t v=word[i];word[i]=bits?(v<<bits)|carry:v;carry=bits?v>>(32-bits):0;}
    if(carry){assert(size<36);word[size++]=carry;}
    for(unsigned i=size;i--;)word[i+whole]=word[i];
    for(unsigned i=0;i<whole;++i)word[i]=0;
    size+=whole;
  }
  __attribute__((noinline)) void halve() {
    uint32_t carry=0;
    for(unsigned i=size;i--;){const uint32_t v=word[i];word[i]=(v>>1)|carry;carry=v<<31;}
    if(size>1&&!word[size-1])--size;
  }
  __attribute__((noinline)) void subtract(const Big& b) {
    uint64_t borrow=0;
    for(unsigned i=0;i<size;++i){const uint64_t v=uint64_t(i<b.size?b.word[i]:0)+borrow;const uint32_t a=word[i];word[i]=a-uint32_t(v);borrow=(v>>32)+(a<uint32_t(v));}
    assert(!borrow);while(size>1&&!word[size-1])--size;
  }
  unsigned bits() const {return word[size-1]?(size-1)*32+32-unsigned(__builtin_clz(word[size-1])):0;}
  __attribute__((noinline)) int sum_compare(const Big& b,const Big& limit) const {
    unsigned n=size>b.size?size:b.size;if(n<limit.size)n=limit.size;
    uint64_t carry=0;int result=0;
    for(unsigned i=0;i<n;++i){carry+=uint64_t(i<size?word[i]:0)+(i<b.size?b.word[i]:0);const uint32_t sum=uint32_t(carry),other=i<limit.size?limit.word[i]:0;if(sum!=other)result=sum>other?1:-1;carry>>=32;}
    return carry?1:result;
  }
};
struct floating_decimal_64 {uint64_t mantissa;int exponent;};
static floating_decimal_64 d2d(uint64_t fraction,uint32_t raw) {
  const uint64_t m=fraction|(raw?UINT64_C(1)<<52:0);
  const int e=(raw?int(raw)-1023-52:-1074)-2;
  Big remainder(m*4),denominator(1),lower(!fraction&&raw>1?1:2),upper(2);
  if(e>=0){remainder.shift(unsigned(e));lower.shift(unsigned(e));upper.shift(unsigned(e));}
  else denominator.shift(unsigned(-e));
  // Conservative base-10 exponent estimate; normalize exactly below.
  const int binary=int(remainder.bits())-int(denominator.bits());
  int exponent=1+(binary>=0?binary*1233/4096:-((-binary*1233+4095)/4096));
  if(exponent>=0)for(int i=0;i<exponent;++i)denominator.multiply(10);
  else for(int i=0;i<-exponent;++i){remainder.multiply(10);lower.multiply(10);upper.multiply(10);}
  while(remainder.compare(denominator)<0){remainder.multiply(10);lower.multiply(10);upper.multiply(10);--exponent;}
  const bool inclusive=!(m&1);uint64_t digits=0;unsigned count=0;
  for(;;){
    unsigned digit=0;while(remainder.compare(denominator)>=0){remainder.subtract(denominator);++digit;}
    assert(digit<10);
    const int low=remainder.compare(lower),high=remainder.sum_compare(upper,denominator);
    const bool down=low<0||(low==0&&inclusive),up=high>0||(high==0&&inclusive);
    digits=digits*10+digit;++count;
    if(down||up){
      if(up){remainder.multiply(2);const int middle=remainder.compare(denominator);if(!down||middle>0||(middle==0&&(digit&1)))++digits;}
      break;
    }
    remainder.multiply(10);lower.multiply(10);upper.multiply(10);
    assert(count<18);
  }
  exponent-=int(count)-1;
  while(digits%10==0){digits/=10;++exponent;}
  return {digits,exponent};
}
static uint64_t rounded_quotient(Big& numerator,const Big& denominator) {
  int shift=int(numerator.bits())-int(denominator.bits());
  Big divisor(denominator);if(shift>=0)divisor.shift(unsigned(shift));
  uint64_t quotient=0;
  for(int bit=shift;bit>=0;--bit){if(numerator.compare(divisor)>=0){numerator.subtract(divisor);quotient|=UINT64_C(1)<<unsigned(bit);}divisor.halve();}
  numerator.multiply(2);const int halfway=numerator.compare(denominator);
  return quotient+(halfway>0||(halfway==0&&(quotient&1)));
}
static double decimal_to_double(uint64_t coefficient,int exponent,bool negative,int digits) {
  uint64_t bits=uint64_t(negative)<<63;
  if(!coefficient||digits+exponent<=-324){}
  else if(digits+exponent>=310)bits|=UINT64_C(0x7ff0000000000000);
  else {
    Big numerator(coefficient),denominator(1);
    if(exponent>=0)for(int i=0;i<exponent;++i)numerator.multiply(10);
    else for(int i=0;i<-exponent;++i)denominator.multiply(10);
    int binary=int(numerator.bits())-int(denominator.bits());
    {Big scaled(binary>=0?denominator:numerator);scaled.shift(unsigned(binary>=0?binary:-binary));if(binary>=0?numerator.compare(scaled)<0:scaled.compare(denominator)<0)--binary;}
    if(binary>1023)bits|=UINT64_C(0x7ff0000000000000);
    else {
      if(binary<-1022)binary=-1022;
      const int shift=52-binary;
      if(shift>=0)numerator.shift(unsigned(shift));else denominator.shift(unsigned(-shift));
      uint64_t significand=rounded_quotient(numerator,denominator);
      if(significand==(UINT64_C(1)<<53)){significand>>=1;++binary;}
      bits|=binary>1023?UINT64_C(0x7ff0000000000000):(uint64_t(binary+1022)<<52)+significand;
    }
  }
  double value;memcpy(&value,&bits,sizeof(value));return value;
}
enum Status {SUCCESS,FAIL};
static Status s2d_n(const char* text,int length,double* out) {
  if(!length)return FAIL;
  bool negative=text[0]=='-';int i=negative?1:0;uint64_t coefficient=0;int digits=0,point=length,end=length,exponent=0;
  for(;i<length;++i){const char ch=text[i];if(ch=='.'){if(point!=length)return FAIL;point=i;continue;}if(ch<'0'||ch>'9')break;if(digits>=17)return FAIL;coefficient=coefficient*10+unsigned(ch-'0');if(coefficient)++digits;}
  if(i<length&&(text[i]=='e'||text[i]=='E')){
    end=i++;bool minus=false;if(i<length&&(text[i]=='-'||text[i]=='+'))minus=text[i++]=='-';int significant=0;
    for(;i<length;++i){const char ch=text[i];if(ch<'0'||ch>'9'||significant>3)return FAIL;exponent=exponent*10+ch-'0';if(exponent)++significant;}
    if(minus)exponent=-exponent;
  }
  if(i<length)return FAIL;
  if(point<end)exponent-=end-point-1;
  *out=decimal_to_double(coefficient,exponent,negative,digits);return SUCCESS;
}
