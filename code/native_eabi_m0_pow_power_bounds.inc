// Compare a positive binary64 power with one known adjacent RNE boundary.
// Use normalized lower bounds on integer powers and add a proved error
// bound only to the smaller side. No floating-point math is performed.
#pragma once
#include "native_eabi_m0_pow_exact.inc"
#include "native_eabi_m0_uint128.hpp"

#if defined(__arm__) || defined(__thumb__)
#define M0_POW_BOUNDS __attribute__((noinline,cold,section(".m0_pow_exact_extension")))
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" void mk61_m0_pow_progress() __attribute__((weak));
#endif
#else
#define M0_POW_BOUNDS
#endif

namespace m0_pow_power_bounds {
namespace {
using U = uint64_t;
using Scale = mk61_u128;
using Word = uint16_t;
constexpr unsigned SquareLeafWords=16;

// The caller leaves the outgoing carry word beyond the earlier rows.
static __attribute__((always_inline)) inline void multiply_row(Word* product,const Word* first,
                                                               const Word* end,uint32_t digit) {
  uint32_t carry=0;
  while(first!=end) {
    const uint32_t sum=uint32_t(*first++)*digit+*product+carry;
    *product++=Word(sum);
    carry=sum>>16;
  }
  *product=Word(carry);
}

static M0_POW_BOUNDS void square_leaf(const Word* input,Word* product,unsigned words) {
  for(unsigned i=0;i<2*words;++i) product[i]=0;
  unsigned first=0;
  while(first<words && !input[first]) ++first;
  // First accumulate one copy of each off-diagonal term. Double that
  // integer and insert the diagonal squares in a single carry pass.
  for(unsigned j=first+1;j<words;++j)
    multiply_row(product+j+first,input+first,input+j,input[j]);
  uint32_t carry=0;
  for(unsigned i=first;i<words;++i) {
    const uint32_t diagonal=uint32_t(input[i])*input[i];
    const uint32_t low=2U*product[2*i]+Word(diagonal)+carry;
    product[2*i]=Word(low);
    const uint32_t high=2U*product[2*i+1]+(diagonal>>16)+(low>>16);
    product[2*i+1]=Word(high);
    carry=high>>16;
  }
}

// Square the halves and their absolute difference. The cross term is
// low^2+high^2-(high-low)^2. Scratch needs fewer than 3*words limbs
// because the three recursive calls reuse the same suffix in sequence.
static M0_POW_BOUNDS void square_words(const Word* input,Word* product,Word* scratch,unsigned words) {
  if(words<=SquareLeafWords || (words&1U)) {
    square_leaf(input,product,words);
    return;
  }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(words>=128 && mk61_m0_pow_progress) mk61_m0_pow_progress();
#endif
  const unsigned half=words/2;
  Word* difference=scratch;
  Word* middle=difference+half;
  Word* remaining=middle+words;
  uint32_t borrow=0;
  for(unsigned i=0;i<half;++i) {
    const uint32_t digit=uint32_t(input[i+half])-input[i]-borrow;
    difference[i]=Word(digit);
    borrow=digit>>31;
  }
  if(borrow) {
    uint32_t carry=1;
    for(unsigned i=0;i<half;++i) {
      const uint32_t digit=Word(~difference[i])+carry;
      difference[i]=Word(digit);
      carry=digit>>16;
    }
  }

  square_words(input,product,remaining,half);
  square_words(input+half,product+words,remaining,half);
  square_words(difference,middle,remaining,half);

  // Bias the signed carry by one to represent a borrow without signed
  // shifts. The nonnegative cross term has at most one extra limb.
  uint32_t biased_carry=1;
  for(unsigned i=0;i<words;++i) {
    const uint32_t sum=uint32_t(product[i])+product[i+words]+0xFFFFU-middle[i]+biased_carry;
    middle[i]=Word(sum);
    biased_carry=sum>>16;
  }
  uint32_t carry=0;
  for(unsigned i=0;i<words;++i) {
    const uint32_t sum=uint32_t(product[i+half])+middle[i]+carry;
    product[i+half]=Word(sum);
    carry=sum>>16;
  }
  carry+=biased_carry-1;
  for(unsigned i=words+half;carry && i<2*words;++i) {
    const uint32_t sum=uint32_t(product[i])+carry;
    product[i]=Word(sum);
    carry=sum>>16;
  }
}

template<unsigned Words> struct PowerBounds {
  static_assert(Words >= 8, "The comparison guard requires 128 significand bits");
  struct Number {
    Word word[Words];
    Scale scale;
    bool exact;
  };

  static M0_POW_BOUNDS void from_dyadic(Number& value,U coefficient,int exponent) {
    unsigned width=0;
    for(U bits=coefficient;bits>>=1;) ++width;
    const U high=coefficient<<(63-width);
    for(unsigned i=0;i<Words-4;++i) value.word[i]=0;
    for(unsigned i=0;i<4;++i) value.word[Words-4+i]=uint16_t(high>>(16*i));
    value.scale=Scale(exponent+int(width));
    value.exact=true;
  }

  static M0_POW_BOUNDS void normalize_product(Number& a,const Number& b,const Word* product) {
    bool lost=false;
    for(unsigned i=0;i<Words-1;++i) lost|=product[i]!=0;
    const bool upper_binade=bool(product[2*Words-1]&0x8000U);
    a.scale+=b.scale+unsigned(upper_binade);
    if(upper_binade) {
      lost|=product[Words-1]!=0;
      for(unsigned i=0;i<Words;++i) a.word[i]=product[Words+i];
    } else {
      lost|=(product[Words-1]&0x7FFFU)!=0;
      for(unsigned i=0;i<Words;++i)
        a.word[i]=uint16_t((product[Words-1+i]>>15)|(uint32_t(product[Words+i])<<1));
    }
    a.exact=a.exact && b.exact && !lost;
  }

  // a and b are normalized positive lower bounds. The product can alias
  // either input. b_start skips known zero low words.
  static M0_POW_BOUNDS void multiply(Number& a,const Number& b,unsigned b_start) {
    Word product[2*Words]{};
    for(unsigned j=b_start;j<Words;++j) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      if constexpr(Words>256)
        if(!(j&15U) && mk61_m0_pow_progress) mk61_m0_pow_progress();
#endif
      multiply_row(product+j,a.word,a.word+Words,b.word[j]);
    }
    normalize_product(a,b,product);
  }

  static M0_POW_BOUNDS void square(Number& a) {
    Word product[2*Words];
    if constexpr(Words<=SquareLeafWords) {
      square_leaf(a.word,product,Words);
    } else {
      unsigned first=0;
      while(!a.word[first]) ++first; // The most significant word is nonzero.
      unsigned words=Words;
      while(words>SquareLeafWords && !(words&1U) && first>=Words-words/2)
        words/=2;
      const unsigned skip=Words-words;
      for(unsigned i=0;i<2*skip;++i) product[i]=0;
      Word scratch[3*Words];
      square_words(a.word+skip,product+2*skip,scratch,words);
    }
    normalize_product(a,a,product);
  }

  static inline void power(Number& result,const Number& base,U exponent) {
    result=base;
    U bit=UINT64_C(1)<<62;
    while(!(exponent&bit)) bit>>=1;
    while(bit>>=1) {
      square(result);
      if(exponent&bit) multiply(result,base,Words-4);
    }
  }

  static M0_POW_BOUNDS int compare(const Number& a,const Number& b) {
    // Compare the two's-complement scales without a signed overflow.
    const Scale sign=Scale(1)<<127;
    const Scale ae=a.scale^sign,be=b.scale^sign;
    if(ae!=be) return ae<be?-1:1;
    for(unsigned i=Words;i--;) if(a.word[i]!=b.word[i]) return a.word[i]<b.word[i]?-1:1;
    return 0;
  }

  static M0_POW_BOUNDS bool add_units(Number& value,Scale amount) {
    uint32_t carry=0;
    for(unsigned i=0;i<Words;++i) {
      const uint32_t sum=uint32_t(value.word[i])+uint16_t(amount.low)+carry;
      value.word[i]=uint16_t(sum);
      carry=sum>>16;
      amount>>=16;
      if(!carry && !amount) return false;
    }
    return carry!=0;
  }

  // Each downward product loses at most 2^(1-P) relative for P=16*Words.
  // The expression tree has at most terms-1 rounded products after reuse
  // is expanded. The exact value is strictly below the lower significand
  // plus 4*(terms-1) units when any result was inexact.
  static M0_POW_BOUNDS void raise_bound(Number& value,Scale terms) {
    if(!add_units(value,(terms-1)<<2)) return;
    const bool lost=value.word[0]&1;
    for(unsigned i=0;i<Words-1;++i)
      value.word[i]=uint16_t((value.word[i]>>1)|(uint32_t(value.word[i+1])<<15));
    value.word[Words-1]=uint16_t((value.word[Words-1]>>1)|0x8000U);
    value.scale+=1;
    if(lost) add_units(value,1);
  }

  // -1 and +1 denote the rounded side of the boundary. Zero is undecided.
  static M0_POW_BOUNDS int side(U x,U y,U lower) {
    constexpr U mask=UINT64_C(0x7FFFFFFFFFFFFFFF);
    constexpr U infinity=UINT64_C(0x7FF0000000000000);
    constexpr U one=UINT64_C(0x3FF0000000000000);
    const U ym=y&mask;
    if(!x || x>=infinity || ym>=infinity || lower>=infinity) return 0;
    // The existing interval certificate bounds these magnitudes.
    if(x==one || ym<UINT64_C(0x3BF0000000000000)) return one<=lower?-1:1;
    if(ym>=UINT64_C(0x43E0000000000000))
      return (x<one)^bool(y>>63)?-1:1;

    U numerator;
    int y_scale;
    m0_pow_exact::decode(ym,numerator,y_scale);
    while(!(numerator&1)) {numerator>>=1;++y_scale;}
    unsigned squarings=0;
    if(y_scale>=0) numerator<<=unsigned(y_scale);
    else squarings=unsigned(-y_scale);

    U a,m;
    int ae,me;
    m0_pow_exact::decode(x,a,ae);
    if(!m0_pow_exact::midpoint(lower,lower+1,m,me)) return 0;
    Number left,right;
    {
      Number factor;
      from_dyadic(factor,a,ae);
      power(left,factor,numerator);
    }
    from_dyadic(right,m,me);
    for(unsigned i=0;i<squarings;++i) square(right);
    Scale left_terms=numerator,right_terms=Scale(1)<<squarings;
    const bool inverse=bool(y>>63);
    if(inverse) {
      multiply(left,right,0);
      left_terms+=right_terms;
      from_dyadic(right,1,0);
      right_terms=1;
    }

    const int order=compare(left,right);
    if(!order) {
      const int exactness=int(left.exact)-int(right.exact);
      // An inexact lower bound is strictly below its value.
      if(exactness) return inverse?exactness:-exactness;
      return left.exact?(lower&1?1:-1):0;
    }
    Number& smaller=order<0?left:right;
    const Number& larger=order<0?right:left;
    if(!smaller.exact) {
      raise_bound(smaller,order<0?left_terms:right_terms);
      if(compare(smaller,larger)>0) return 0;
    }
    return inverse?-order:order;
  }
};

static M0_POW_BOUNDS bool resolve(U x,U y,U& lower) {
  const int side=PowerBounds<256>::side(x,y,lower);
  if(!side) return false;
  lower+=unsigned(side>0);
  return true;
}
}
}
#undef M0_POW_BOUNDS
