#ifndef MK61_LANGUAGE_VALUE_HPP
#define MK61_LANGUAGE_VALUE_HPP
#include "mk_math.hpp"
#include <limits.h>
#include <stdint.h>
#include <string.h>
#include <type_traits>
namespace language_vm {
// Eight-byte, pointer-free number. Only this positive quiet-NaN family is
// reserved for int32; external NaNs in that family become a genuine NaN,
// never an integer. Negative zero, infinities and all finite doubles survive.
class Value {
 public:
  static constexpr uint32_t INTEGER_TAG = 0x7FFC0001UL;
  constexpr Value():bits_((uint64_t)INTEGER_TAG << 32) {}
  constexpr Value(int32_t n):bits_(((uint64_t)INTEGER_TAG << 32) | (uint32_t)n) {}
  Value(uint32_t n) {
    if(n <= INT32_MAX) bits_=((uint64_t)INTEGER_TAG << 32) | n;
    else set_number((double)n);
  }
  template<typename T, typename std::enable_if<std::is_integral<T>::value && sizeof(T) <= 4,int>::type = 0>
  Value(T n) {
    if(std::is_signed<T>::value || (uint64_t)n <= INT32_MAX)
      bits_=((uint64_t)INTEGER_TAG << 32) | (uint32_t)n;
    else set_number((double)n);
  }
  Value(double n) { set_number(n); }
  static Value floating_bits(uint64_t bits) {
    Value v;
    v.bits_ = (uint32_t)(bits >> 32) == INTEGER_TAG ? UINT64_C(0x7FF8000000000000) : bits;
    return v;
  }
  bool integer() const { return (uint32_t)(bits_ >> 32) == INTEGER_TAG; }
  int32_t integer_value() const {
    const uint32_t low = (uint32_t)bits_; int32_t n; memcpy(&n, &low, sizeof(n)); return n;
  }
  double number() const {
    if(integer()) return (double)integer_value();
    double n; memcpy(&n, &bits_, sizeof(n)); return n;
  }
  explicit operator double() const { return number(); }
  explicit operator bool() const { return !zero(); }
  bool finite() const {
    return integer() || (bits_ & UINT64_C(0x7FF0000000000000)) != UINT64_C(0x7FF0000000000000);
  }
  bool zero() const { return integer() ? (uint32_t)bits_ == 0 : (bits_ << 1) == 0; }
  uint64_t representation() const { return bits_; }
  Value floor() const { return integer() ? *this : Value(mk_math::floor(number())); }
  Value absolute() const {
    if(integer() && integer_value() >= 0) return *this;
    return integer() ? -*this : Value(mk_math::fabs(number()));
  }
  Value fraction() const { return integer() ? Value(0) : Value(mk_math::frac(number())); }
  Value rounded() const { return integer() ? *this : Value(mk_math::round_half(number())); }
  friend Value operator-(Value a) {
    if(a.integer()) {
      const int32_t n=a.integer_value(); int32_t out;
      if(n == 0) return floating_bits(UINT64_C(0x8000000000000000));
      if(!__builtin_sub_overflow(0,n,&out)) return Value(out);
    }
    return Value(-a.number());
  }
  friend Value operator+(Value a, Value b) {
    int32_t out;
    if(a.integer() && b.integer() &&
       !__builtin_add_overflow(a.integer_value(),b.integer_value(),&out)) return Value(out);
    return Value(a.number()+b.number());
  }
  friend Value operator-(Value a, Value b) {
    int32_t out;
    if(a.integer() && b.integer() &&
       !__builtin_sub_overflow(a.integer_value(),b.integer_value(),&out)) return Value(out);
    return Value(a.number()-b.number());
  }
  friend Value operator*(Value a, Value b) {
    int32_t out;
    if(a.integer() && b.integer()) {
      const int32_t x=a.integer_value(), y=b.integer_value();
      if((x == 0 && y < 0) || (y == 0 && x < 0))
        return floating_bits(UINT64_C(0x8000000000000000));
      if(!__builtin_mul_overflow(x,y,&out)) return Value(out);
    }
    return Value(a.number()*b.number());
  }
  friend Value operator/(Value a, Value b) {
    if(a.integer() && b.integer()) {
      const int32_t x=a.integer_value(), y=b.integer_value();
      if(y && !(x == INT32_MIN && y == -1)) {
        if(x == 0 && y < 0) return floating_bits(UINT64_C(0x8000000000000000));
        if(x % y == 0) return Value(x / y);
      }
    }
    return Value(a.number()/b.number());
  }
  static Value modulo(Value a, Value b) {
    if(a.integer() && b.integer()) {
      const int32_t x=a.integer_value(), y=b.integer_value();
      if(y) {
        if(x == INT32_MIN && y == -1) return Value(0);
        const uint32_t magnitude = y < 0 ? 0U-(uint32_t)y : (uint32_t)y;
        if((magnitude & (magnitude-1)) == 0) {
          const uint32_t remainder=(uint32_t)x & (magnitude-1);
          const uint32_t low=y < 0 && remainder ? remainder-magnitude : remainder;
          int32_t n; memcpy(&n,&low,sizeof(n)); return Value(n);
        }
        int32_t r=x % y;
        if((r < 0 && y > 0) || (r > 0 && y < 0)) r += y;
        return Value(r);
      }
    }
    const double x=a.number(), y=b.number();
    return Value(x-mk_math::floor(x/y)*y);
  }
  static Value floor_divide(Value a, Value b) {
    if(a.integer() && b.integer()) {
      const int32_t x=a.integer_value(), y=b.integer_value();
      if(y && !(x == INT32_MIN && y == -1)) {
        if(y > 0 && ((uint32_t)y & ((uint32_t)y-1)) == 0) {
          const unsigned shift=(unsigned)__builtin_ctz((uint32_t)y);
          static_assert((int32_t(-1) >> 1) == -1, "arithmetic right shift required");
          return Value(x >> shift);
        }
        int32_t q=x / y, r=x % y;
        if(r && ((r < 0) != (y < 0))) --q;
        return Value(q);
      }
    }
    return Value(mk_math::floor(a.number()/b.number()));
  }
#define MK61_VALUE_COMPARE(op) \
  friend bool operator op(Value a, Value b) { \
    return a.integer() && b.integer() ? a.integer_value() op b.integer_value() : a.number() op b.number(); \
  }
  MK61_VALUE_COMPARE(==)
  MK61_VALUE_COMPARE(!=)
  MK61_VALUE_COMPARE(<)
  MK61_VALUE_COMPARE(<=)
  MK61_VALUE_COMPARE(>)
  MK61_VALUE_COMPARE(>=)
#undef MK61_VALUE_COMPARE
 private:
  uint64_t bits_;
  __attribute__((noinline)) void set_number(double n) {
    uint64_t bits; memcpy(&bits,&n,sizeof(bits));
    const uint64_t magnitude=bits & UINT64_C(0x7FFFFFFFFFFFFFFF);
    if(magnitude == 0) {
      bits_ = bits ? bits : (uint64_t)INTEGER_TAG << 32; return;
    }
    const unsigned exponent=(unsigned)(magnitude >> 52);
    if(exponent >= 1023 && exponent <= 1054) {
      const unsigned shift=1075-exponent;
      const uint64_t mantissa=(magnitude & UINT64_C(0x000FFFFFFFFFFFFF)) | (UINT64_C(1)<<52);
      const uint64_t whole=mantissa >> shift;
      if((mantissa & ((UINT64_C(1)<<shift)-1)) == 0 &&
         whole <= ((bits >> 63) ? UINT64_C(2147483648) : UINT64_C(2147483647))) {
        const uint32_t low=(bits >> 63) ? 0U-(uint32_t)whole : (uint32_t)whole;
        bits_=((uint64_t)INTEGER_TAG << 32) | low; return;
      }
    }
    bits_=(uint32_t)(bits >> 32) == INTEGER_TAG ? UINT64_C(0x7FF8000000000000) : bits;
  }
};
static_assert(sizeof(Value) == sizeof(double), "number cell must remain eight bytes");
static_assert(std::is_trivially_copyable<Value>::value, "number must survive raw snapshots");
static_assert(alignof(Value) == alignof(double), "number cell alignment changed");
} // namespace language_vm
#endif
