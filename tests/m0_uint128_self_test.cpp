#include "native_eabi_m0_uint128.hpp"
#include <assert.h>
#include <stdio.h>

using Native=unsigned __int128;
static uint64_t state=UINT64_C(0x128C0FFEE2040);
static uint64_t random64() {
  state^=state<<13;state^=state>>7;state^=state<<17;return state;
}
static void same(mk61_u128 a,Native b) {
  assert(a.low==uint64_t(b) && a.high==uint64_t(b>>64));
}
int main() {
  for(unsigned i=0;i<1000000;++i) {
    const uint64_t al=random64(),ah=random64(),bl=random64(),bh=random64();
    const mk61_u128 a=mk61_u128::words(al,ah),b=mk61_u128::words(bl,bh);
    const Native x=(Native(ah)<<64)|al,y=(Native(bh)<<64)|bl;
    same(a+b,x+y);same(a-b,x-y);same(a*b,x*y);
    same(-a,-x);same(~a,~x);same(a&b,x&y);same(a|b,x|y);same(a^b,x^y);
    assert((a<b)==(x<y) && (a==b)==(x==y));
    const unsigned n=random64()&127;
    same(a<<n,x<<n);same(a>>n,x>>n);
    same(a+bl,x+bl);same(al-b,Native(al)-y);same(a*bl,x*bl);
    assert(bool(a)==bool(x));same(mk61_u128(-1),~Native(0));
  }
  puts("PASS: 1,000,000 portable uint128 vectors");
}
