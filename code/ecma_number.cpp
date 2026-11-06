// Number conversion is a cold service, including compatibility builds whose
// sketch otherwise uses -O3. Keep the exact algorithm optimized for size.
#if defined(__GNUC__) && !defined(__clang__) && defined(__arm__)
#pragma GCC optimize ("Oz")
#endif
// Ryu provides shortest round-tripping digits; this adapter applies the
// ECMAScript decimal/scientific notation thresholds used by UrqW.
#define RYU_OPTIMIZE_SIZE
#define RYU_ONLY_64_BIT_OPS
#ifndef NDEBUG
#define NDEBUG
#endif
#include "ecma_number.hpp"
#if defined(MK61_APP_SHARED_RUNTIME)
#define MK61_USE_COMPACT_LIBM 1
#endif
#include "mk_math.hpp"
#include <string.h>
#include <stdlib.h>
#include <assert.h>
#include <inttypes.h>
#if defined(MK61_APP_SHARED_RUNTIME) && defined(MK61_TARGET_PICOCALC)
// The SDK's freestanding stdlib omits allocation. Only d2d is used; the
// upstream allocating wrapper is discarded by function-section GC.
extern "C" void* malloc(size_t);
#endif
namespace mk61_ryu {
#if defined(MK61_TEST_COMPACT_DECIMAL) || \
    (defined(MK61_APP_SHARED_RUNTIME) && !defined(MK61_TARGET_PICOCALC))
#include "ecma_decimal_compact.hpp"
#else
#include "../third_party/ryu/ryu/d2s.c"
#include "../third_party/ryu/ryu/s2d.c"
#endif
}

namespace ecma_number {
namespace {
// Shared by shortest digits, fixed substitutions and scientific exponents.
// The returned span is forward-readable and needs no second reverse buffer.
__attribute__((noinline)) char* decimal_digits(uint64_t value,char* end) {
  do {*--end=char('0'+value%10);value/=10;}while(value);
  return end;
}
}

__attribute__((noinline)) bool fractional(double value,char* out,size_t capacity) {
  if(!out || capacity<32) return false;
  uint64_t bits;memcpy(&bits,&value,8);const unsigned raw=unsigned((bits>>52)&2047);
  if(raw==2047 || value==0) return format(value,out,capacity);
  const uint64_t mantissa=(bits&UINT64_C(0xfffffffffffff))|(raw?UINT64_C(1)<<52:0);
  const int exponent=raw?int(raw)-1023-52:-1074;
  if(exponent>=0 || (-exponent<64 && !(mantissa&((UINT64_C(1)<<unsigned(-exponent))-1))))
    return format(value,out,capacity);
  const uint64_t scaled=mantissa*25;const int shift=exponent+2;
  uint64_t rounded;
  if(shift>=0) rounded=scaled<<unsigned(shift);
  else if(shift<=-64) rounded=0;
  else {
    const unsigned right=unsigned(-shift);rounded=scaled>>right;
    if((scaled&((UINT64_C(1)<<right)-1))>=(UINT64_C(1)<<(right-1))) ++rounded;
  }
  unsigned n=0;if(bits>>63) out[n++]='-';
  char buffer[24];const char* end=buffer+sizeof(buffer);
  for(const char* digit=decimal_digits(rounded/100,buffer+sizeof(buffer));digit!=end;++digit)out[n++]=*digit;
  out[n++]='.';out[n++]=char('0'+(rounded%100)/10);out[n++]=char('0'+rounded%10);out[n]=0;
  return true;
}
bool format(double value,char* out,size_t capacity) {
  if(!out || capacity<32) return false;
  if(value==0) { out[0]='0';out[1]=0;return true; }
  uint64_t bits;memcpy(&bits,&value,sizeof(bits));
  const bool negative=bool(bits>>63);
  const uint32_t raw=uint32_t((bits>>52)&2047);
  const uint64_t mantissa=bits&UINT64_C(0xfffffffffffff);
  if(raw==2047) {
    const char* source=mantissa?"NaN":negative?"-Infinity":"Infinity";
    for(char* write=out;(*write++=*source++)!=0;) {}
    return true;
  }
  // Use Ryu's exact decimal result directly. Formatting scientific text and
  // parsing it back duplicates a decimal formatter in the resident image.
  const auto decimal=mk61_ryu::d2d(mantissa,raw);
  char buffer[20];char* digits=decimal_digits(decimal.mantissa,buffer+sizeof(buffer));
  const unsigned count=unsigned(buffer+sizeof(buffer)-digits);
  const int exponent=decimal.exponent+int(count)-1;
  unsigned n=0;if(negative) out[n++]='-';
  if(exponent>=-6 && exponent<21) {
    const int point=exponent+1;
    if(point<=0) {
      out[n++]='0';out[n++]='.';for(int i=0;i<-point;++i) out[n++]='0';
      for(unsigned i=0;i<count;++i) out[n++]=digits[i];
    } else {
      for(int i=0;i<point || unsigned(i)<count;++i) {
        if(i==point) out[n++]='.';
        out[n++]=unsigned(i)<count?digits[i]:'0';
      }
    }
  } else {
    out[n++]=digits[0];if(count>1) out[n++]='.';
    for(unsigned i=1;i<count;++i) out[n++]=digits[i];
    out[n++]='e';out[n++]=exponent<0?'-':'+';
    const unsigned magnitude=unsigned(exponent<0?-exponent:exponent);
    for(const char* digit=decimal_digits(magnitude,buffer+sizeof(buffer));digit!=buffer+sizeof(buffer);++digit)out[n++]=*digit;
  }
  out[n]=0;return true;
}
__attribute__((noinline)) bool parse(const char* text,double& value,ParseFallback fallback) {
  while(*text==' ' || *text=='\t' || *text=='\r' || *text=='\n') ++text;
  unsigned size=unsigned(strlen(text));
  while(size && (text[size-1]==' ' || text[size-1]=='\t' || text[size-1]=='\r' || text[size-1]=='\n')) --size;
  if(!size) { value=0;return true; }
  const char* number=text;if(*number=='+') { ++number;--size; }
  if(size==8 && !strncmp(number,"Infinity",8)) { value=__builtin_inf();return true; }
  if(size==9 && !strncmp(number,"-Infinity",9)) { value=-__builtin_inf();return true; }
  if(size>2 && number[0]=='0') {
    unsigned base=number[1]=='x'||number[1]=='X'?16:number[1]=='b'||number[1]=='B'?2:number[1]=='o'||number[1]=='O'?8:0;
    if(base) {
      if(number!=text) return false;
      value=0;
      for(unsigned i=2;i<size;++i) {
        const char ch=number[i];const unsigned digit=ch>='0'&&ch<='9'?unsigned(ch-'0'):
            ch>='a'&&ch<='f'?unsigned(ch-'a'+10):ch>='A'&&ch<='F'?unsigned(ch-'A'+10):99;
        if(digit>=base) return false;
        value=value*base+digit;
      }
      return true;
    }
  }
  if(mk61_ryu::s2d_n(number,int(size),&value)==mk61_ryu::SUCCESS) return true;
  if(fallback) return fallback(number,size,value);
#if defined(MK61_APP_SHARED_RUNTIME)
  return false;
#else
  // Retain the existing bounded parser for host and direct-library clients.
  const char* end=nullptr;value=mk_math::strtod(number,&end);
  return end!=number && unsigned(end-number)==size;
#endif
}
}
