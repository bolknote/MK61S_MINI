// ARMv6-M adapter: exact software FMA/sqrt and binary64 integer rounding.
// The runtime contract is round-to-nearest-even without errno/fenv state.
#ifndef MK61_CORE_SHIM_HPP
#define MK61_CORE_SHIM_HPP
inline double core_round(double x,int mode) {
 uint64_t b;__builtin_memcpy(&b,&x,8);
 const uint64_t sign=b&(UINT64_C(1)<<63),m=b&~(UINT64_C(1)<<63);
 const unsigned raw=unsigned(m>>52);
 if(raw>=1075) return x;
 uint64_t result;
 if(raw<1023) {
  bool up=mode==0?bool(sign&&m):mode==1?m>UINT64_C(0x3FE0000000000000):m>=UINT64_C(0x3FE0000000000000);
  result=sign|(up?UINT64_C(0x3FF0000000000000):0);
 } else {
  const unsigned n=1075-raw;const uint64_t one=UINT64_C(1)<<n,tail=m&(one-1);
  const bool up=mode==0?bool(sign&&tail):tail>one/2 || (tail==one/2&&(mode==2 || ((m>>n)&1)));
  result=(b&~(one-1))+(up?one:0);
 }
 double out;__builtin_memcpy(&out,&result,8);return out;
}
inline double core_floor(double x) {return core_round(x,0);}
inline double core_roundeven(double x) {return core_round(x,1);}
inline double core_roundaway(double x) {return core_round(x,2);}
inline int core_ctzll(uint64_t x) {return 63-__clzdi2(x&(~x+1));}
#define __builtin_fma mk61_m0_fma
#define __builtin_sqrt mk61_m0_sqrt
#define __builtin_floor core_floor
#define __builtin_roundeven core_roundeven
#define __builtin_round core_roundaway
#define __builtin_ctzll core_ctzll
#define fegetround() FE_TONEAREST
#define feraiseexcept(x) 0
#define fegetexceptflag(p,x) (*(p)=0,0)
#define fesetexceptflag(p,x) 0
#define printf(...) 0
#define exit(n) __builtin_trap()
#endif
