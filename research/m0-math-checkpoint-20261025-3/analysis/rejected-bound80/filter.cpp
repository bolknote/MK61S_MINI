#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
using W=unsigned;
using U=unsigned long long;
static_assert(sizeof(W)==4 && sizeof(U)==8);
struct B80 {W h0,h1,low;int exponent;W radius;};
static_assert(sizeof(B80)==20);
struct P128 {W h0,h1,l0,l1;int exponent;W radius;};
extern "C" U mk61_m0_bound80_wide32(W,W);
extern "C" void mk61_m0_bound80_square(B80*);
extern "C" int mk61_m0_bound80_old_boundary(const P128*,W,bool,U);

struct T80 {W p0,p1,p2;};
__attribute__((always_inline)) static inline void add80(T80 &t,W lo,W hi=0) {
  const W old=t.p0;
  t.p0+=lo;
  const W carry=t.p0<old,previous=t.p1;
  t.p1+=hi;
  const W c1=t.p1<previous;
  const W middle=t.p1;
  t.p1+=carry;
  t.p2+=c1+W(t.p1<middle);
}

extern "C" __attribute__((noinline,section(".m0_pow_bound80_multiply")))
void mk61_m0_bound80_multiply(B80 *a,const B80 *b) {
  const U top=mk61_m0_bound80_wide32(a->h1,b->h1);
  T80 t{W(top)<<16,W(top>>16),W(top>>48)};
  U cross=mk61_m0_bound80_wide32(a->h1,b->h0);
  add80(t,W(cross>>16),W(cross>>48));
  cross=mk61_m0_bound80_wide32(a->h0,b->h1);
  add80(t,W(cross>>16),W(cross>>48));
  add80(t,((a->h0>>16)*(b->h0>>16))>>16);
  add80(t,((a->h1>>16)*b->low)>>16);
  add80(t,((b->h1>>16)*a->low)>>16);
  W radius=a->radius+b->radius+16;
  int exponent=a->exponent+b->exponent;
  if(t.p2&0x8000U) ++exponent;
  else {
    t.p2=(t.p2<<1)|(t.p1>>31);
    t.p1=(t.p1<<1)|(t.p0>>31);
    t.p0<<=1;
    radius<<=1;
  }
  a->h0=(t.p1<<16)|(t.p0>>16);
  a->h1=(t.p2<<16)|(t.p1>>16);
  a->low=t.p0&65535U;
  a->exponent=exponent;
  a->radius=radius;
}

__attribute__((always_inline)) static inline void half80(B80 &a) {
  a.low=(a.low>>1)|((a.h0&1U)<<15);
  a.h0=(a.h0>>1)|(a.h1<<31);
  a.h1>>=1;
  a.radius=(a.radius>>1)+1;
}
extern "C" __attribute__((noinline,section(".m0_pow_bound80_compare")))
int mk61_m0_bound80_compare(const B80 *input_a,const B80 *input_b) {
  B80 a=*input_a,b=*input_b;
  const int distance=a.exponent-b.exponent;
  if(distance>=2) return 1;
  if(distance<=-2) return -1;
  if(distance<0) half80(a);
  else if(distance>0) half80(b);
  int side=1;
  if(a.h1<b.h1 || (a.h1==b.h1 && (a.h0<b.h0 || (a.h0==b.h0 && a.low<b.low)))) {
    B80 t=a;a=b;b=t;side=-1;
  }
  const W low=(a.low-b.low)&65535U;
  const W borrow=a.low<b.low;
  const W h0=a.h0-b.h0-borrow;
  const W borrow0=(a.h0<b.h0 || (a.h0==b.h0 && borrow));
  const W h1=a.h1-b.h1-borrow0;
  const W error=a.radius+b.radius;
  if(h1 || h0>(error>>16) || ((h0<<16)|low)>error) return side;
  return 0;
}

extern "C" __attribute__((noinline,section(".m0_pow_bound80_filter")))
int mk61_m0_bound80_filter(const P128 *power,W denominator,bool inverse,U cell) {
  if(cell<0x0010000000000000ULL || cell>=0x7fefffffffffffffULL) return 0;
  if(!denominator || denominator>128 || (denominator&(denominator-1)) || !(power->h1&0x80000000U))
    return mk61_m0_bound80_old_boundary(power,denominator,inverse,cell);
  const W lo=W(cell),hi=W(cell>>32);
  B80 mid;
  mid.h0=(lo<<11)|1024U;
  mid.h1=(((hi&0xfffffU)|0x100000U)<<11)|(lo>>21);
  mid.exponent=int(hi>>20)-1023;
  // Two explicit field stores avoid an out-of-line aggregate memset.
  static_cast<volatile W&>(mid.low)=0;
  static_cast<volatile W&>(mid.radius)=0;
  for(W n=denominator;n>1;n>>=1) mk61_m0_bound80_square(&mid);
  B80 value{power->h0,power->h1,power->l1>>16,power->exponent,2};
  int result;
  if(inverse) {
    mk61_m0_bound80_multiply(&mid,&value);
    B80 one{0,0x80000000U,0,0,0};
    result=-mk61_m0_bound80_compare(&mid,&one);
  } else result=mk61_m0_bound80_compare(&value,&mid);
  return result?result:mk61_m0_bound80_old_boundary(power,denominator,inverse,cell);
}
#endif
