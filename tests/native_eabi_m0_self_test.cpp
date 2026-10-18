// Independent oracle: host IEEE arithmetic, integer multiply/divide and sqrt.
#include "native_eabi_m0.hpp"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using U=uint64_t;
static U state=UINT64_C(0x3D7C91F061614204),checks=0;
static U random64() {state^=state<<13;state^=state>>7;state^=state<<17;return state;}
template<class T,class V> static T copy(V x) {T y;static_assert(sizeof(T)==sizeof(V));std::memcpy(&y,&x,sizeof(y));return y;}
[[noreturn]] static void fail(const char* op,U a,U b,U got,U expected) {
  std::fprintf(stderr,"%s a=%016llX b=%016llX got=%016llX expected=%016llX\n",op,
    (unsigned long long)a,(unsigned long long)b,(unsigned long long)got,(unsigned long long)expected);std::exit(1);
}
static void exact(const char* op,U a,U b,U got,U expected) {++checks;if(got!=expected)fail(op,a,b,got,expected);}
static void equal(const char* op,U a,U b,double got,double expected) {
  ++checks;if(std::isnan(expected)?!std::isnan(got):copy<U>(got)!=copy<U>(expected))fail(op,a,b,copy<U>(got),copy<U>(expected));
}
static void equal(const char* op,U a,U b,float got,float expected) {
  ++checks;if(std::isnan(expected)?!std::isnan(got):copy<uint32_t>(got)!=copy<uint32_t>(expected))fail(op,a,b,copy<uint32_t>(got),copy<uint32_t>(expected));
}
static void doubles(U a,U b) {
  volatile double x=copy<double>(a),y=copy<double>(b);
  equal("dadd",a,b,__aeabi_dadd(x,y),x+y);equal("dsub",a,b,__aeabi_dsub(x,y),x-y);
  equal("drsub",a,b,__aeabi_drsub(x,y),y-x);equal("dmul",a,b,__aeabi_dmul(x,y),x*y);
  equal("ddiv",a,b,__aeabi_ddiv(x,y),x/y);
  const int got[]={__aeabi_dcmpeq(x,y),__aeabi_dcmplt(x,y),__aeabi_dcmple(x,y),__aeabi_dcmpge(x,y),__aeabi_dcmpgt(x,y),__aeabi_dcmpun(x,y)};
  const int expected[]={x==y,x<y,x<=y,x>=y,x>y,std::isunordered(x,y)};
  for(unsigned i=0;i<6;++i)exact("dcmp",a,b,got[i],expected[i]);
  equal("d2f",a,0,__aeabi_d2f(x),float(x));
  if(x>=-0x1p31 && x<0x1p31)exact("d2i",a,0,uint32_t(__aeabi_d2iz(x)),uint32_t(int32_t(x)));
  if(x>=0 && x<0x1p32)exact("d2ui",a,0,__aeabi_d2uiz(x),uint32_t(x));
  if(x>=-0x1p63 && x<0x1p63)exact("d2l",a,0,U(__aeabi_d2lz(x)),U(int64_t(x)));
  if(x>=0 && x<0x1p64)exact("d2ul",a,0,__aeabi_d2ulz(x),U(x));
}
static void singles(uint32_t a,uint32_t b) {
  volatile float x=copy<float>(a),y=copy<float>(b);
  equal("fadd",a,b,__aeabi_fadd(x,y),x+y);equal("fsub",a,b,__aeabi_fsub(x,y),x-y);
  equal("frsub",a,b,__aeabi_frsub(x,y),y-x);equal("fmul",a,b,__aeabi_fmul(x,y),x*y);
  equal("fdiv",a,b,__aeabi_fdiv(x,y),x/y);equal("sqrtf",a,0,mk61_m0_sqrtf(x),std::sqrt(x));
  equal("f2d",a,0,__aeabi_f2d(x),double(x));
  const int got[]={__aeabi_fcmpeq(x,y),__aeabi_fcmplt(x,y),__aeabi_fcmple(x,y),__aeabi_fcmpge(x,y),__aeabi_fcmpgt(x,y),__aeabi_fcmpun(x,y)};
  const int expected[]={x==y,x<y,x<=y,x>=y,x>y,std::isunordered(x,y)};
  for(unsigned i=0;i<6;++i)exact("fcmp",a,b,got[i],expected[i]);
  if(x>=-0x1p31f && x<0x1p31f)exact("f2i",a,0,uint32_t(__aeabi_f2iz(x)),uint32_t(int32_t(x)));
  if(x>=0 && x<0x1p32f)exact("f2ui",a,0,__aeabi_f2uiz(x),uint32_t(x));
}
static void integers(U a,U b) {
  exact("lmul",a,b,__aeabi_lmul(a,b),a*b);
  equal("ul2d",a,0,__aeabi_ul2d(a),double(a));equal("l2d",a,0,__aeabi_l2d(copy<int64_t>(a)),double(copy<int64_t>(a)));
  const uint32_t u=uint32_t(a);const int32_t i=copy<int32_t>(u);
  equal("ui2d",a,0,__aeabi_ui2d(u),double(u));equal("i2d",a,0,__aeabi_i2d(i),double(i));
  equal("ui2f",a,0,__aeabi_ui2f(u),float(u));equal("i2f",a,0,__aeabi_i2f(i),float(i));
  mk61_eabi_divmod qr;mk61_m0_divmod64(a,b,&qr);
  exact("udiv64",a,b,qr.quotient,b?a/b:a?UINT64_MAX:0);exact("umod64",a,b,qr.remainder,b?a%b:0);
  exact("clz64",a,0,__clzdi2(a),a?unsigned(__builtin_clzll(a)):64);
  exact("clz32",a,0,__clzsi2(u),u?unsigned(__builtin_clz(u)):32);
}
int main(int argc,char**argv) {
  const U edge[]={0,U(1)<<63,1,2,3,0x7FFFFF,0x800000,0xFFFFFFFF,
    UINT64_C(0xFFFFFFFFFFFFF),UINT64_C(0x10000000000000),UINT64_C(0x10000000000001),
    UINT64_C(0x3FE0000000000000),UINT64_C(0x3FF0000000000000),UINT64_C(0x3FF0000000000001),
    UINT64_C(0x7FEFFFFFFFFFFFFF),UINT64_C(0x7FF0000000000000),UINT64_C(0xFFF0000000000000),
    UINT64_C(0x7FF0000000000001),UINT64_C(0x7FF8123456789ABC),UINT64_MAX};
  for(U a:edge)for(U b:edge) {doubles(a,b);doubles(a^(U(1)<<63),b);integers(a,b);}
  const uint32_t fe[]={0,0x80000000,1,2,3,0x7FFFFF,0x800000,0x800001,0x3F000000,
    0x3F800000,0x3F800001,0x7F7FFFFF,0x7F800000,0xFF800000,0x7F800001,0x7FC01234,UINT32_MAX};
  for(uint32_t a:fe)for(uint32_t b:fe) {singles(a,b);singles(a^0x80000000U,b);}
  // Cancellation and the rounding/underflow boundaries of every exponent.
  for(unsigned e=0;e<2047;++e)for(unsigned k=0;k<12;++k) {
    const U a=(U(e)<<52)|(random64()&UINT64_C(0xFFFFFFFFFFFFF));
    doubles(a,(a+int(k%5)-2)^(U(1)<<63));doubles(a,copy<U>(0x1p-53));
    doubles(a,copy<U>(0.5));
  }
  for(unsigned e=0;e<255;++e)for(unsigned k=0;k<12;++k) {
    const uint32_t a=(e<<23)|(uint32_t(random64())&0x7FFFFF);
    singles(a,(a+k%5-2)^0x80000000U);singles(a,0x33800000);singles(a,0x3F000000);
  }
  const unsigned n=argc>1?unsigned(std::strtoul(argv[1],nullptr,10)):100000;
  for(unsigned k=0;k<n;++k) {
    const U a=random64(),b=random64();doubles(a,b);singles(uint32_t(a),uint32_t(b));integers(a,b);
    integers(a,uint32_t(b));
  }
  std::printf("PASS %llu independent M0 IEEE/integer checks\n",(unsigned long long)checks);
}
