#include "../code/ecma_number.hpp"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <initializer_list>

// Independent reference: use the upstream public scientific formatter, whose
// small-integer path and digit writer the resident adapter no longer retains.
#define RYU_OPTIMIZE_SIZE
#define RYU_ONLY_64_BIT_OPS
#define d2s reference_d2s
#define d2s_buffered reference_d2s_buffered
#define d2s_buffered_n reference_d2s_buffered_n
namespace reference_ryu {
#include "../third_party/ryu/ryu/d2s.c"
}
#undef d2s
#undef d2s_buffered
#undef d2s_buffered_n

static void check(uint64_t bits) {
  double value;
  memcpy(&value, &bits, sizeof(value));
  char actual[40];
  memset(actual, '!', sizeof(actual));
  assert(ecma_number::format(value, actual, 32));
  assert(actual[32] == '!');
  char scientific[32];
  scientific[reference_ryu::reference_d2s_buffered_n(value, scientific)] = 0;
  char expected[40] = {};
  char* exponent_at = strchr(scientific, 'E');
  if(value == 0) strcpy(expected, "0");
  else if(!exponent_at) strcpy(expected, scientific);
  else {
    // Convert the reference's decimal point/exponent to ECMAScript notation
    // without any integer-to-decimal machinery from the production adapter.
    const int exponent = atoi(exponent_at + 1);
    char* write = expected;
    const char* read = scientific;
    if(*read == '-') { *write++ = *read++; }
    char digits[20] = {};
    unsigned count = 0;
    while(read < exponent_at) {
      if(*read != '.') digits[count++] = *read;
      ++read;
    }
    if(exponent < -6 || exponent >= 21) {
      *write++ = digits[0];
      if(count > 1) {
        *write++ = '.';
        memcpy(write, digits + 1, count - 1); write += count - 1;
      }
      snprintf(write, 10, "e%+d", exponent);
    } else {
      const int point = exponent + 1;
      if(point <= 0) {
        *write++ = '0'; *write++ = '.';
        for(int i = point; i < 0; ++i) *write++ = '0';
        memcpy(write, digits, count);
      } else {
        const unsigned length = count > unsigned(point) ? count : unsigned(point);
        for(unsigned i = 0; i < length; ++i) {
          if(i == unsigned(point)) *write++ = '.';
          *write++ = i < count ? digits[i] : '0';
        }
      }
    }
  }
  if(strcmp(actual, expected)) {
    fprintf(stderr, "%016" PRIx64 ": %s != %s\n", bits, actual, expected);
    abort();
  }
  if((bits & UINT64_C(0x7fffffffffffffff)) < UINT64_C(0x7ff0000000000000) && value != 0) {
    const double roundtrip = strtod(actual, nullptr);
    uint64_t restored; memcpy(&restored, &roundtrip, sizeof(restored));
    assert(restored == bits);
    double parsed=0;
    assert(ecma_number::parse(scientific,parsed));
    memcpy(&restored,&parsed,sizeof(restored));
    if(restored!=bits){fprintf(stderr,"parse roundtrip %016" PRIx64 " %s -> %016" PRIx64 "\n",bits,scientific,restored);abort();}
  }
}

int main() {
  for(unsigned exponent = 0; exponent < 2048; ++exponent) {
    const uint64_t base = uint64_t(exponent) << 52;
    for(uint64_t fraction : {UINT64_C(0), UINT64_C(1), UINT64_C(0x7ffffffffffff),
                            UINT64_C(0xffffffffffffe), UINT64_C(0xfffffffffffff)}) {
      check(base | fraction); check(base | fraction | (UINT64_C(1) << 63));
    }
  }
  uint64_t random = UINT64_C(0x71e3a9c586f02d4b);
  for(unsigned i = 0; i < 100000; ++i) {
    random ^= random << 13; random ^= random >> 7; random ^= random << 17;
    check(random);
  }
  // Independent native decimal parser, including all binary64 exponent
  // ranges and signed underflow/overflow. Use at most 17 significant digits,
  // the exact input range advertised by the resident conversion service.
  for(unsigned i=0;i<100000;++i) {
    random ^= random<<13;random ^= random>>7;random ^= random<<17;
    char input[64];
    snprintf(input,sizeof(input),"%s%" PRIu64 "e%d",i&1?"-":"",
             random%UINT64_C(100000000000000000),int((random>>32)%661)-340);
    double parsed=0;assert(ecma_number::parse(input,parsed));
    const double reference=strtod(input,nullptr);
    uint64_t a,b;memcpy(&a,&parsed,8);memcpy(&b,&reference,8);
    if(a!=b){fprintf(stderr,"parse %s -> %016" PRIx64 " != %016" PRIx64 "\n",input,a,b);abort();}
  }
  char buffer[32];
  assert(!ecma_number::format(1, nullptr, 32));
  assert(!ecma_number::format(1, buffer, 31));
  puts("ECMAScript formatting: upstream equivalence and exact round trips passed");
}
