// Independent differential oracle: host IEEE hardware and native integer division.
#include "native_eabi.hpp"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
extern "C" double mk61_eabi_ddiv_scale(double,double);
using U = uint64_t;
static U state=UINT64_C(0xB5763AE84019CDEF), cases=0;
static U random64() {state^=state<<13;state^=state>>7;state^=state<<17;return state;}
static double real(U b) {double x;std::memcpy(&x,&b,8);return x;}
static U bits(double x) {U b;std::memcpy(&b,&x,8);return b;}
[[noreturn]] static void fail(const char* op,U a,U b,U got,U expected) {
  std::fprintf(stderr,"%s a=%016llX b=%016llX got=%016llX expected=%016llX\n",op,
    (unsigned long long)a,(unsigned long long)b,(unsigned long long)got,(unsigned long long)expected);
  std::exit(1);
}
static bool nan(U a) {return (a&UINT64_C(0x7FFFFFFFFFFFFFFF))>UINT64_C(0x7FF0000000000000);}
static void equal(const char* op,U a,U b,double got,double reference) {
  ++cases;U g=bits(got),e=bits(reference);
  if((nan(e) && !nan(g)) || (!nan(e) && g!=e))fail(op,a,b,g,e);
}
static void integers(U n,U d) {
  mk61_eabi_divmod r;mk61_eabi_divmod64(n,d,&r);
  const U q=d?n/d:n?UINT64_MAX:0,rem=d?n%d:0;
  cases+=2;
  if(r.quotient!=q)fail("udiv",n,d,r.quotient,q);
  if(r.remainder!=rem)fail("umod",n,d,r.remainder,rem);
}
static void pair(U a,U b) {
  volatile double x=real(a),y=real(b); // Force genuine host arithmetic.
  equal("div",a,b,__aeabi_ddiv(x,y),x/y);
  const int got[]={__aeabi_dcmpeq(x,y),__aeabi_dcmplt(x,y),__aeabi_dcmple(x,y),__aeabi_dcmpge(x,y),__aeabi_dcmpgt(x,y)};
  const int expected[]={x==y,x<y,x<=y,x>=y,x>y};
  for(unsigned i=0;i<5;++i) {++cases;if(got[i]!=expected[i])fail("compare",a,b,got[i],expected[i]);}
  if(x>=-0x1p63 && x<0x1p63) {++cases;const int64_t g=__aeabi_d2lz(x),e=static_cast<int64_t>(x);if(g!=e)fail("d2lz",a,b,U(g),U(e));}
  if(x>=0 && x<0x1p64) {++cases;const U g=__aeabi_d2ulz(x),e=static_cast<U>(x);if(g!=e)fail("d2ulz",a,b,g,e);}
  integers(a,b);
}
int main(int argc,char**argv) {
  const U edge[]={0,UINT64_C(0x8000000000000000),1,2,3,0x7FFFFFU,0x800000U,0xFFFFFFFFU,
    UINT64_C(0xFFFFFFFFFFFFF),UINT64_C(0x10000000000000),UINT64_C(0x10000000000001),
    UINT64_C(0x3FF0000000000000),UINT64_C(0x3FEFFFFFFFFFFFFF),UINT64_C(0x3FF0000000000001),
    UINT64_C(0x4000000000000000),UINT64_C(0x3FE0000000000000),UINT64_C(0x7FEFFFFFFFFFFFFF),
    UINT64_C(0x7FF0000000000000),UINT64_C(0xFFF0000000000000),UINT64_C(0x7FF0000000000001),
    UINT64_C(0x7FF8123456789ABC),UINT64_C(0xFFF8123456789ABC),UINT64_MAX};
  for(U a:edge)for(U b:edge) {pair(a,b);pair(a^UINT64_C(0x8000000000000000),b);}
  // Boundary cancellation, halfway rounding, underflow, overflow and conversions.
  for(unsigned exponent=0;exponent<2047;++exponent) for(unsigned i=0;i<32;++i) {
    U a=(U(exponent)<<52)|(random64()&UINT64_C(0xFFFFFFFFFFFFF));
    U b=a+(i%5)-2;
    pair(a,b);pair(a,b^UINT64_C(0x8000000000000000));
    pair(a,bits(0x1p-53));pair(a,bits(0.5));
  }
  const unsigned count=argc>1?unsigned(std::strtoul(argv[1],nullptr,10)):1000000;
  for(unsigned i=0;i<count;++i) {
    pair(random64(),random64());
    const U a=random64(),b=(U(1+random64()%2046)<<52)|(random64()&UINT64_C(0x8000000000000000));
    volatile double x=real(a),y=real(b);
    equal("scale",a,b,mk61_eabi_ddiv_scale(x,y),x/y);
    // Exercise both branches of normalized multiword division frequently.
    integers(random64(),uint32_t(random64()));
    integers(random64(),random64()&UINT64_C(0xFFFFFFFFFF));
  }
  std::printf("PASS %llu independent arithmetic/conversion/divmod checks\n",(unsigned long long)cases);
}
