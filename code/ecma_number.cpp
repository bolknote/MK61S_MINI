// Ryu provides shortest round-tripping digits; this adapter applies the
// ECMAScript decimal/scientific notation thresholds used by UrqW.
#define RYU_OPTIMIZE_SIZE
#define RYU_ONLY_64_BIT_OPS
#ifndef NDEBUG
#define NDEBUG
#endif
#include "ecma_number.hpp"
#include "mk_math.hpp"
#include <string.h>
#include <stdlib.h>
#include <assert.h>
#include <inttypes.h>
namespace mk61_ryu {
#include "../third_party/ryu/ryu/d2s.c"
#include "../third_party/ryu/ryu/s2d.c"
}

namespace ecma_number {
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
  uint64_t integer=rounded/100;char reverse[24];unsigned used=0;
  do { reverse[used++]=char('0'+integer%10);integer/=10; } while(integer);
  while(used) out[n++]=reverse[--used];
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
    strcpy(out,mantissa?"NaN":negative?"-Infinity":"Infinity");
    return true;
  }
  // Use Ryu's exact decimal result directly. Formatting scientific text and
  // parsing it back duplicates a decimal formatter in the resident image.
  const auto decimal=mk61_ryu::d2d(mantissa,raw);
  uint64_t integer=decimal.mantissa;
  char reverse[20];unsigned count=0;
  do { reverse[count++]=char('0'+integer%10);integer/=10; } while(integer);
  char digits[20];for(unsigned i=0;i<count;++i) digits[i]=reverse[count-i-1];
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
    unsigned magnitude=unsigned(exponent<0?-exponent:exponent),used=0;char reverse[4];
    do { reverse[used++]=char('0'+magnitude%10);magnitude/=10; } while(magnitude);
    while(used) out[n++]=reverse[--used];
  }
  out[n]=0;return true;
}
__attribute__((noinline)) bool parse(const char* text,double& value) {
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
  // Retain the existing bounded resident parser for long decimal inputs.
  const char* end=nullptr;value=mk_math::strtod(number,&end);
  return end!=number && unsigned(end-number)==size;
}
}
