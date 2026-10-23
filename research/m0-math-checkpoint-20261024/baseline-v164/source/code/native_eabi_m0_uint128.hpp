#ifndef MK61_M0_UINT128_HPP
#define MK61_M0_UINT128_HPP
#include <stdint.h>
#include <type_traits>

// Unsigned modulo-2^128 arithmetic for ARMv6-M, whose compiler has no native
// __int128 type. Trivial layout also permits the upstream little-endian unions.
struct mk61_m0_uint128 {
  uint64_t low,high;
  mk61_m0_uint128() = default;
  template<class T> static constexpr uint64_t extension(T n) {
    if constexpr(std::is_signed<T>::value) return n<0?UINT64_MAX:0;
    return 0;
  }
  template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type = 0>
  constexpr mk61_m0_uint128(T n):low(uint64_t(n)),high(extension(n)) {}
  static constexpr mk61_m0_uint128 words(uint64_t low,uint64_t high) {
    return mk61_m0_uint128(low,high);
  }
  explicit constexpr operator bool() const {return (low|high)!=0;}
  constexpr operator uint64_t() const {return low;}
  template<class T,typename std::enable_if<std::is_integral<T>::value && !std::is_same<T,bool>::value && !std::is_same<T,uint64_t>::value,int>::type = 0>
  explicit constexpr operator T() const {return T(low);}
private:
  constexpr mk61_m0_uint128(uint64_t lo,uint64_t hi):low(lo),high(hi) {}
};
using mk61_u128=mk61_m0_uint128;
static_assert(sizeof(mk61_u128)==16 && std::is_trivially_copyable<mk61_u128>::value,
              "128-bit union representation");
inline constexpr mk61_u128 operator+(mk61_u128 a,mk61_u128 b) {
  return mk61_u128::words(a.low+b.low,a.high+b.high+uint64_t(a.low+b.low<a.low));
}
inline constexpr mk61_u128 operator-(mk61_u128 a,mk61_u128 b) {
  return mk61_u128::words(a.low-b.low,a.high-b.high-uint64_t(a.low<b.low));
}
inline constexpr mk61_u128 operator-(mk61_u128 a) {return mk61_u128(0)-a;}
inline constexpr mk61_u128 operator~(mk61_u128 a) {return mk61_u128::words(~a.low,~a.high);}
inline constexpr mk61_u128 operator&(mk61_u128 a,mk61_u128 b) {return mk61_u128::words(a.low&b.low,a.high&b.high);}
inline constexpr mk61_u128 operator|(mk61_u128 a,mk61_u128 b) {return mk61_u128::words(a.low|b.low,a.high|b.high);}
inline constexpr mk61_u128 operator^(mk61_u128 a,mk61_u128 b) {return mk61_u128::words(a.low^b.low,a.high^b.high);}
template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type = 0>
inline constexpr mk61_u128 operator<<(mk61_u128 a,T n) {
  return !n?a:n>=128?mk61_u128(0):n>=64?mk61_u128::words(0,a.low<<(n-64)):
    mk61_u128::words(a.low<<n,(a.high<<n)|(a.low>>(64-n)));
}
template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type = 0>
inline constexpr mk61_u128 operator>>(mk61_u128 a,T n) {
  return !n?a:n>=128?mk61_u128(0):n>=64?mk61_u128::words(a.high>>(n-64),0):
    mk61_u128::words((a.low>>n)|(a.high<<(64-n)),a.high>>n);
}
inline constexpr uint64_t mk61_m0_wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&65535U,ah=a>>16,bl=b&65535U,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&65535U);
  return (uint64_t(ah*bh+(t>>16)+(v>>16))<<32)|uint32_t(v<<16)|(p&65535U);
}
inline constexpr mk61_u128 operator*(mk61_u128 a,mk61_u128 b) {
  const uint64_t p=mk61_m0_wide32(uint32_t(a.low),uint32_t(b.low));
  const uint64_t t=mk61_m0_wide32(uint32_t(a.low>>32),uint32_t(b.low))+(p>>32);
  const uint64_t v=mk61_m0_wide32(uint32_t(a.low),uint32_t(b.low>>32))+uint32_t(t);
  const uint64_t high=mk61_m0_wide32(uint32_t(a.low>>32),uint32_t(b.low>>32))+(t>>32)+(v>>32);
  return mk61_u128::words((v<<32)|uint32_t(p),high+a.low*b.high+a.high*b.low);
}
inline constexpr bool operator==(mk61_u128 a,mk61_u128 b) {return a.low==b.low && a.high==b.high;}
inline constexpr bool operator!=(mk61_u128 a,mk61_u128 b) {return !(a==b);}
inline constexpr bool operator<(mk61_u128 a,mk61_u128 b) {return a.high!=b.high?a.high<b.high:a.low<b.low;}
inline constexpr bool operator>(mk61_u128 a,mk61_u128 b) {return b<a;}
inline constexpr bool operator<=(mk61_u128 a,mk61_u128 b) {return !(b<a);}
inline constexpr bool operator>=(mk61_u128 a,mk61_u128 b) {return !(a<b);}
#define MK61_U128_MIXED(op) \
template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type = 0> \
inline constexpr auto operator op(mk61_u128 a,T b) -> decltype(a op mk61_u128(b)) {return a op mk61_u128(b);} \
template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type = 0> \
inline constexpr auto operator op(T a,mk61_u128 b) -> decltype(mk61_u128(a) op b) {return mk61_u128(a) op b;}
MK61_U128_MIXED(+)
MK61_U128_MIXED(-)
MK61_U128_MIXED(*)
MK61_U128_MIXED(&)
MK61_U128_MIXED(|)
MK61_U128_MIXED(^)
MK61_U128_MIXED(==)
MK61_U128_MIXED(!=)
MK61_U128_MIXED(<)
MK61_U128_MIXED(>)
MK61_U128_MIXED(<=)
MK61_U128_MIXED(>=)
#undef MK61_U128_MIXED
#define MK61_U128_COMPOUND(op) inline mk61_u128& operator op##=(mk61_u128& a,mk61_u128 b) {return a=a op b;}
MK61_U128_COMPOUND(+)
MK61_U128_COMPOUND(-)
MK61_U128_COMPOUND(*)
MK61_U128_COMPOUND(&)
MK61_U128_COMPOUND(|)
MK61_U128_COMPOUND(^)
#undef MK61_U128_COMPOUND
inline mk61_u128& operator<<=(mk61_u128& a,unsigned n) {return a=a<<n;}
inline mk61_u128& operator>>=(mk61_u128& a,unsigned n) {return a=a>>n;}
inline mk61_u128& operator++(mk61_u128& a) {return a+=1;}
inline mk61_u128& operator--(mk61_u128& a) {return a-=1;}
inline mk61_u128 operator++(mk61_u128& a,int) {const mk61_u128 old=a;++a;return old;}
inline mk61_u128 operator--(mk61_u128& a,int) {const mk61_u128 old=a;--a;return old;}
#endif
