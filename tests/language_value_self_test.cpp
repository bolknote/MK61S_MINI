#include "language_value.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
using language_vm::Value;
uint64_t bits(double x){uint64_t b;memcpy(&b,&x,8);return b;}
void same(Value value,double expected){assert(bits(value.number())==bits(expected));}
int main(){
  const double special[]={0.,-0.,.1,-.1,2147483647.,2147483648.,-2147483648.,-2147483649.,
    281474976710655.,std::numeric_limits<double>::denorm_min(),1e300,-1e300,
    std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()};
  for(double d:special)same(Value(d),d);
  assert(Value(0).integer() && !Value(-0.).integer());
  assert(Value(2147483647.).integer() && Value(-2147483648.).integer());
  assert(!Value(2147483648.).integer());
  const uint64_t collision=((uint64_t)Value::INTEGER_TAG<<32)|42;
  double nan;memcpy(&nan,&collision,8);
  Value n(nan);assert(!n.integer() && !n.finite() && std::isnan(n.number()));
  same(-Value(0),-0.);same(Value(0)*Value(-3),-0.);same(Value(0)/Value(-3),-0.);
  same(Value(INT32_MAX)+Value(1),(double)INT32_MAX+1);
  same(Value(INT32_MIN)-Value(1),(double)INT32_MIN-1);
  same(Value(INT32_MIN)/Value(-1),2147483648.);
  same(-Value(INT32_MIN),2147483648.);
  same(Value(-0.).absolute(),mk_math::fabs(-0.));
  same(Value(-0.).fraction(),mk_math::frac(-0.));
  uint32_t random=0x61F411;
  for(unsigned i=0;i<100000;++i){
    random=random*1664525U+1013904223U;int32_t a;memcpy(&a,&random,4);
    random=random*1664525U+1013904223U;int32_t b;memcpy(&b,&random,4);
    const Value x(a),y(b);const double p=a,q=b;
    same(x+y,p+q);same(x-y,p-q);same(x*y,p*q);
    assert((x<y)==(p<q) && (x==y)==(p==q));
    if(b){same(x/y,p/q);same(Value::modulo(x,y),p-mk_math::floor(p/q)*q);
          same(Value::floor_divide(x,y),mk_math::floor(p/q));}
  }
  const int32_t edge[]={INT32_MIN,INT32_MIN+1,-7,-3,-1,0,1,2,3,7,INT32_MAX-1,INT32_MAX};
  for(int32_t a:edge)for(int32_t b:edge){
    Value x(a),y(b);double p=a,q=b;same(x+y,p+q);same(x-y,p-q);same(x*y,p*q);
    if(b){same(x/y,p/q);same(Value::modulo(x,y),p-mk_math::floor(p/q)*q);
          same(Value::floor_divide(x,y),mk_math::floor(p/q));}
  }
  std::puts("language value: eight bytes, int32/float, overflow promotion, signed zero, NaN, 100000 arithmetic pairs PASS");
}
