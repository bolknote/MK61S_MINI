#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
using W=unsigned;
using U=unsigned long long;
static_assert(sizeof(W)==4 && sizeof(U)==8);
struct P128 {W h0,h1,l0,l1;int exponent;W radius;};
static_assert(sizeof(P128)==24);
extern "C" void pow_integer128_square(P128*);
extern "C" void pow_integer128_multiply(P128*,const P128*);
extern "C" int mk61_m0_boundary128_compare(const P128*,const P128*);
extern "C" __attribute__((noinline,section(".m0_pow_boundary128_code")))
int mk61_m0_boundary128(const P128 *power,W denominator,bool inverse,U cell) {
  if(cell<0x0010000000000000ULL || cell>=0x7fefffffffffffffULL) return 0;
  const W lo=W(cell),hi=W(cell>>32);
  P128 mid;
  mid.h0=(lo<<11)|1024U;
  mid.h1=(((hi&0xfffffU)|0x100000U)<<11)|(lo>>21);
  mid.exponent=int(hi>>20)-1023;
  static_cast<volatile W&>(mid.l0)=0;
  static_cast<volatile W&>(mid.l1)=0;
  static_cast<volatile W&>(mid.radius)=0;
  for(W n=denominator;n>1;n>>=1) pow_integer128_square(&mid);
  if(!inverse) return mk61_m0_boundary128_compare(power,&mid);
  pow_integer128_multiply(&mid,power);
  if(mid.exponent>0) return -1;
  if(mid.exponent < -1) return 1;
  if(!mid.exponent) {
    if(mid.h1>0x80000000U || (mid.h1==0x80000000U && mid.h0) || mid.l1 || mid.l0>mid.radius) return -1;
    return 0;
  }
  if(mid.h1!=0xffffffffU || mid.h0!=0xffffffffU) return 1;
  const U low=(U(mid.l1)<<32)|mid.l0;
  return low<U(0)-U(mid.radius)?1:0;
}
#endif
