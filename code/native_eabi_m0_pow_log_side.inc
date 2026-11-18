// A fixed-work sign test for y*ln(x)-ln(m), with m a dyadic midpoint.
#pragma once
#include "native_eabi_m0_pow_power_bounds.inc"

namespace m0_pow_log_side {
namespace {
using U = uint64_t;
using Word = uint16_t;
using m0_pow_power_bounds::multiply_row;
constexpr unsigned Precision = 16384;
constexpr unsigned Words = Precision/16;
constexpr unsigned TableLast = 16;
constexpr unsigned LastSingleBit = 256;
constexpr unsigned ResidualBits = Precision/2;
constexpr unsigned FirstBlockShift = LastSingleBit+7;
constexpr unsigned BlockCount = (Precision-LastSingleBit-ResidualBits)/7+1;
constexpr unsigned GroupCount = Precision/(TableLast+1);
constexpr unsigned PowerWords = (8*(Precision/(FirstBlockShift-8))+15)/16+1;
constexpr unsigned Guard = 83;
constexpr U One = UINT64_C(0x3ff0000000000000);
constexpr U Infinity = UINT64_C(0x7ff0000000000000);
constexpr U Magnitude = UINT64_C(0x7fffffffffffffff);

#if defined(__arm__) || defined(__thumb__)
#define M0_LOG_SIDE __attribute__((noinline,cold,section(".m0_pow_refine_extension")))
#else
#define M0_LOG_SIDE
#endif

#include "native_eabi_m0_pow_log_side_table.inc"

struct Big {
  Word word[Words+5]{};
};
struct Factor {
  Word shift;
  uint8_t digit;
};

static void progress() {
#if defined(__arm__) || defined(__thumb__)
  if(mk61_m0_pow_progress) mk61_m0_pow_progress();
#endif
}

static unsigned top_bit(U n) {
  unsigned bit = 0;
  while(n >>= 1) ++bit;
  return bit;
}

// Add or subtract a short prefix and propagate its outgoing carry.
static void accumulate(Big& sum, const Word* data, unsigned count, bool subtract) {
  uint32_t carry = 0;
  for(unsigned i=0; i<count; ++i) {
    const uint32_t v = uint32_t(sum.word[i])+(subtract ? Word(~data[i]) : data[i])+(carry^subtract);
    sum.word[i] = Word(v);
    carry = (v>>16)^subtract;
  }
  for(unsigned i=count; carry && i<Words+5; ++i) {
    const uint32_t v = subtract ? uint32_t(sum.word[i])-1 : uint32_t(sum.word[i])+1;
    sum.word[i] = Word(v);
    carry = subtract ? v>>31 : v>>16;
  }
}

static void add_column(Big& sum, unsigned at, uint32_t value) {
  while(value) {
    value += sum.word[at];
    sum.word[at++] = Word(value);
    value >>= 16;
  }
}

// floor(c^n * 2^shift), with the unscaled power in a short array.
M0_LOG_SIDE static void add_power(Big& sum, unsigned c, unsigned n, int shift) {
  Word small[PowerWords];
  unsigned length = 1;
  small[0] = 1;
  for(unsigned k=0; k<n; ++k) {
    uint32_t carry = 0;
    for(unsigned i=0; i<length; ++i) {
      const uint32_t v = uint32_t(small[i])*c+carry;
      small[i] = Word(v);
      carry = v>>16;
    }
    if(carry) small[length++] = Word(carry);
  }
  if(shift >= 0) {
    unsigned at = unsigned(shift)/16;
    const unsigned bits = unsigned(shift)%16;
    uint32_t carry = 0;
    for(unsigned i=0; i<length; ++i,++at) {
      const uint32_t v = (uint32_t(small[i])<<bits)+sum.word[at]+carry;
      sum.word[at] = Word(v);
      carry = v>>16;
    }
    add_column(sum, at, carry);
  } else {
    const unsigned skip = unsigned(-shift)/16, bits = unsigned(-shift)%16;
    small[length] = 0;
    uint32_t carry = 0;
    unsigned at = 0;
    for(unsigned i=skip; i<length; ++i,++at) {
      const Word digit = Word((small[i] | (uint32_t(small[i+1])<<16))>>bits);
      const uint32_t v = uint32_t(sum.word[at])+digit+carry;
      sum.word[at] = Word(v);
      carry = v>>16;
    }
    add_column(sum, at, carry);
  }
}

// Store the lower reduced mantissa as 1 + residual/2^Precision.
// The fixed integer word at Words is read by the shifted multiplicand.
static void reduce(Big& residual, unsigned used, unsigned shift, unsigned digit) {
  const unsigned skip = shift/16, bits = shift%16;
  uint32_t carry = digit;
  for(unsigned i=0; i<used; ++i) {
    const uint32_t shifted = residual.word[i+skip] | (uint32_t(residual.word[i+skip+1])<<16);
    const uint32_t v = uint32_t(Word(shifted>>bits))*digit+carry;
    const uint32_t difference = uint32_t(residual.word[i])-Word(v);
    residual.word[i] = Word(difference);
    carry = (v>>16)+(difference>>31);
  }
}

static unsigned choices(Big& residual, uint8_t* singles, Factor* blocks) {
  unsigned used = Words, count = 0, steps = 0;
  for(;;) {
    while(used && !residual.word[used-1]) --used;
    if(used <= ResidualBits/16) return count;
    const unsigned highest = (used-1)*16+top_bit(residual.word[used-1]);
    unsigned shift, digit;
    if(highest > Precision-LastSingleBit) {
      shift = Precision-highest+1;
      digit = 1;
      ++singles[shift];
    } else {
      const unsigned low = highest-7, at = low/16;
      const uint32_t source = residual.word[at] | (uint32_t(residual.word[at+1])<<16);
      digit = ((source>>(low%16))&255)-1;
      shift = Precision-low;
      blocks[count++] = {Word(shift), uint8_t(digit)};
    }
    reduce(residual, used, shift, digit);
    if((++steps&31)==0) progress();
  }
}

// Group the log series by common divisor: sum_j (sum_i digit_i^j/2^(i*j))/j.
M0_LOG_SIDE static void add_series(Big& result, const uint8_t* singles, const Factor* blocks,
                                  unsigned count, bool subtract) {
  for(unsigned n=1; n<=GroupCount; ++n) {
    const unsigned limit = Precision/n;
    Big group;
    for(unsigned i=TableLast+1; i<=LastSingleBit && i<=limit; ++i) {
      if(singles[i]) {
        const unsigned bit = Precision-i*n;
        add_column(group, bit/16, unsigned(singles[i])<<(bit%16));
      }
    }
    for(unsigned i=0; i<count && unsigned(blocks[i].shift)-8<=limit; ++i)
      add_power(group, blocks[i].digit, n, int(Precision)-int(blocks[i].shift)*int(n));
    // The group lies below 8 * 2^(-n*(TableLast+1)). Include its
    // entire possible leading word.
    const unsigned words = (Precision-n*(TableLast+1)+2)/16+1;
    uint32_t remainder = 0;
    if(n>1) {
      for(unsigned i=words; i--;) {
        const uint32_t value = (remainder<<16)|group.word[i];
        const uint32_t quotient = value/n;
        group.word[i] = Word(quotient);
        remainder = value-quotient*n;
      }
    }
    accumulate(result, group.word, words, subtract);
    if((n&15)==0) progress();
  }
}

M0_LOG_SIDE static void absolute_log(Big& result, U coefficient, int exponent) {
  const unsigned lead = top_bit(coefficient);
  exponent += int(lead);
  const bool negative = exponent<0;
  multiply_row(result.word, LogFactors[0], LogFactors[0]+Words,
               unsigned(negative ? -exponent : exponent));
  const U fraction = coefficient-(U(1)<<lead);
  if(!fraction) return;

  Big residual;
  const unsigned place = Precision-lead, at = place/16, bits = place%16;
  const U shifted = fraction<<bits;
  for(unsigned i=0; i+at<Words; ++i)
    residual.word[at+i] = Word(shifted>>(i*16));
  residual.word[Words] = 1;
  uint8_t singles[LastSingleBit+1]{};
  Factor blocks[BlockCount];
  const unsigned count = choices(residual, singles, blocks);

  for(unsigned i=2; i<=TableLast; ++i)
    for(unsigned copies=0; copies<singles[i]; ++copies)
      accumulate(result, LogFactors[i-1], Words, negative);
  add_series(result, singles, blocks, count, negative);
  // log(1+r) differs from r by <1 Q16384 unit at the remaining scale.
  accumulate(result, residual.word, ResidualBits/16, negative);
}

static void scale_by_exponent(Big& out, const Big& log, U multiplier, int shift) {
  for(unsigned i=0; i<4; ++i)
    multiply_row(out.word+i, log.word, log.word+Words+1, Word(multiplier>>(16*i)));
  if(shift>0) {
    // Active exponents have shift <= 10.
    for(unsigned i=Words+5; i--;) {
      const uint32_t lower = i ? uint32_t(out.word[i-1])>>(16-shift) : 0;
      out.word[i] = Word((uint32_t(out.word[i])<<shift)|lower);
    }
  } else if(shift<0) {
    const unsigned skip = unsigned(-shift)/16, bits = unsigned(-shift)%16;
    for(unsigned i=0; i<Words+5; ++i) {
      const unsigned at = i+skip;
      const uint32_t a = at<Words+5 ? out.word[at] : 0;
      const uint32_t b = at+1<Words+5 ? out.word[at+1] : 0;
      out.word[i] = Word((a | (b<<16))>>bits);
    }
  }
}

// Both logarithm errors plus the scaling floor cost <2^83 units.
// After taking the exact difference, inspect only bits at and above 83.
M0_LOG_SIDE static int side(U x, U y, U lower) {
  const U y_magnitude = y&Magnitude;
  if(!x || x>=Infinity || lower>=Infinity || y_magnitude>=UINT64_C(0x43e0000000000000))
    return 0;
  const bool midpoint_negative = lower<One;
  if(x==One || y_magnitude<UINT64_C(0x3bf0000000000000)) return midpoint_negative ? 1 : -1;
  const bool power_negative = (x<One) != bool(y>>63);
  if(power_negative != midpoint_negative) return power_negative ? -1 : 1;
  U a, sy, midpoint;
  int e, shift, me;
  m0_pow_exact::decode(x, a, e);
  m0_pow_exact::decode(y_magnitude, sy, shift);
  if(!m0_pow_exact::midpoint(lower, lower+1, midpoint, me)) return 0;

  Big log, threshold, product;
  absolute_log(log, a, e);
  absolute_log(threshold, midpoint, me);
  scale_by_exponent(product, log, sy, shift);
  int order = 0;
  for(unsigned i=Words+5; i--;) {
    if(product.word[i]!=threshold.word[i]) {
      order = product.word[i]<threshold.word[i] ? -1 : 1;
      break;
    }
  }
  Big& larger = order<0 ? threshold : product;
  const Big& smaller = order<0 ? product : threshold;
  accumulate(larger, smaller.word, Words+5, true);
  unsigned far = larger.word[Guard/16]>>(Guard%16);
  for(unsigned i=Guard/16+1; i<Words+5; ++i) far |= larger.word[i];
  return far ? (power_negative ? -order : order) : 0;
}

#undef M0_LOG_SIDE
}
}
