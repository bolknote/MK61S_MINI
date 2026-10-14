#include "mk_math.hpp"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <fstream>
#include <string>

using Unary = double(*)(double);
struct Function {
  const char* name;
  Unary actual;
  Unary reference;
  uint64_t limit;
  uint64_t cases = 0, worst = 0, failures = 0;
};
static Function functions[] = {
  {"sin",mk_math::sin,static_cast<Unary>(std::sin),4},
  {"cos",mk_math::cos,static_cast<Unary>(std::cos),4},
  {"tan",mk_math::tan,static_cast<Unary>(std::tan),4},
  {"asin",mk_math::asin,static_cast<Unary>(std::asin),4},
  {"acos",mk_math::acos,static_cast<Unary>(std::acos),4},
  {"atan",mk_math::atan,static_cast<Unary>(std::atan),4},
  {"ln",mk_math::ln,static_cast<Unary>(std::log),4},
  {"log10",mk_math::log10,static_cast<Unary>(std::log10),4},
  {"exp",mk_math::exp,static_cast<Unary>(std::exp),4},
  {"sqrt",mk_math::sqrt,static_cast<Unary>(std::sqrt),0},
};
static Function power = {"pow",nullptr,nullptr,4};
static uint64_t state = UINT64_C(0x05bb37c4e943016d);
static uint64_t next() {
  state ^= state << 13; state ^= state >> 7; state ^= state << 17;
  return state;
}
static uint64_t bits(double x) { uint64_t b; std::memcpy(&b,&x,8); return b; }
static double value(uint64_t b) { double x; std::memcpy(&x,&b,8); return x; }
static uint64_t ordered(double x) {
  const uint64_t b = bits(x);
  return (b >> 63) ? ~b : b | (UINT64_C(1) << 63);
}
static void compare(Function& f, double x, double y, double actual, double expected) {
  ++f.cases;
  bool ok;
  uint64_t distance = 0;
  if (std::isnan(expected)) {
    ok = std::isnan(actual); // NaN payload/signaling encodings are not the API contract.
  } else if (expected == 0.0 || std::isinf(expected)) {
    ok = bits(actual) == bits(expected);
  } else {
    const uint64_t a = ordered(actual), b = ordered(expected);
    distance = a >= b ? a-b : b-a;
    ok = std::isfinite(actual) && distance <= f.limit;
  }
  f.worst = std::max(f.worst,distance);
  if (!ok) {
    if (++f.failures <= 10) {
      std::fprintf(stderr,"%s x=%a y=%a got=%a expected=%a ulp=%llu\n",
          f.name,x,y,actual,expected,(unsigned long long)distance);
    }
  }
}
static void all(double x) {
  for (Function& f: functions) compare(f,x,0,f.actual(x),f.reference(x));
}
static void pow_case(double x, double y) {
  compare(power,x,y,mk_math::pow(x,y),std::pow(x,y));
}
static double unit() { return double(next() >> 11)*0x1p-53; }
static double any_finite() {
  uint64_t b = next();
  if ((b & UINT64_C(0x7FF0000000000000)) == UINT64_C(0x7FF0000000000000))
    b ^= UINT64_C(1) << 52;
  return value(b);
}
int main(int argc,char** argv) {
  const unsigned count = argc > 1 ? unsigned(std::strtoul(argv[1],nullptr,10)) : 100000;
  const double infinity = std::numeric_limits<double>::infinity();
  const double denorm = std::numeric_limits<double>::denorm_min();
  const double minimum = std::numeric_limits<double>::min();
  const double maximum = std::numeric_limits<double>::max();
  const double pi = 0x1.921fb54442d18p1;
  const double fixtures[] = {
    0,-0.0,denorm,-denorm,minimum,-minimum,
    std::nextafter(minimum,0.0),-std::nextafter(minimum,0.0),
    maximum,-maximum,infinity,-infinity,
    value(UINT64_C(0x7FF80000DEADBEEF)),value(UINT64_C(0x7FF0000000000001)),
    1,-1,std::nextafter(1.0,0.0),std::nextafter(1.0,infinity),
    -std::nextafter(1.0,0.0),-std::nextafter(1.0,infinity),
    0.5,-0.5,2,-2,3,-3,4,-4,53,-53,1074,-1074,
    0x1p53,-0x1p53,0x1p64,-0x1p64,pi,-pi,pi/2,-pi/2,
    std::nextafter(pi/2,0.0),std::nextafter(pi/2,infinity),
    std::nextafter(-pi/2,0.0),std::nextafter(-pi/2,-infinity),
    709.782712893384, std::nextafter(709.782712893384,infinity),
    -745.1332191019411,std::nextafter(-745.1332191019411,-infinity)
  };
  for (double x: fixtures) {
    all(x);
    for (double y: fixtures) pow_case(x,y);
  }
  for (int e=-1074;e<=1023;++e) {
    const double x=std::ldexp(1.0,e);
    for (double a: {x,-x,std::nextafter(x,0.0),std::nextafter(x,infinity)}) all(a);
    const double angle=std::ldexp(pi/2,e);
    for (double a: {angle,std::nextafter(angle,0.0),std::nextafter(angle,infinity),
                    -angle,std::nextafter(-angle,0.0),std::nextafter(-angle,-infinity)}) {
      for (unsigned i=0;i<3;++i)
        compare(functions[i],a,0,functions[i].actual(a),functions[i].reference(a));
    }
    for (double y: {0.5,-0.5,1.0,2.0,3.0,-3.0,4.0,1.5})
      pow_case(x,y);
  }
  for (unsigned i=0;i<count;++i) {
    const double a=any_finite();
    all(a);
    const double small=(unit()*2-1)*16;
    for (unsigned j=0;j<6;++j)
      compare(functions[j],small,0,functions[j].actual(small),functions[j].reference(small));
    const double inside=unit()*2-1;
    for (unsigned j=3;j<=4;++j)
      compare(functions[j],inside,0,functions[j].actual(inside),functions[j].reference(inside));
    const double exponent=unit()*1480-760;
    compare(functions[8],exponent,0,functions[8].actual(exponent),std::exp(exponent));
    pow_case(std::fabs(a),unit()*16-8);
    const int64_t offset=int64_t(next()%UINT64_C(0x200000001))-INT64_C(0x100000000);
    const double near_one=value(uint64_t(INT64_C(0x3FF0000000000000)+offset));
    const double big_power=std::ldexp(unit()*2-1,int(next()%65));
    pow_case(near_one,big_power);
    pow_case(unit()*1.5+0.5,unit()*4096-2048);
    pow_case(-std::fabs(a),double(int(next()%129)-64));
  }
  if (argc > 2) {
    std::ifstream input(argv[2]);
    assert(input.is_open());
    std::string line;
    unsigned vectors=0;
    while (std::getline(input,line)) {
      if (line.empty() || line[0]=='#') continue;
      char name[16],extra;
      unsigned long long a,b,result;
      assert(std::sscanf(line.c_str(),"%15s %llx %llx %llx %c",name,&a,&b,&result,&extra)==4);
      Function* f=nullptr;
      if (std::strcmp(name,"pow")==0) f=&power;
      else for (Function& candidate: functions)
        if (std::strcmp(name,candidate.name)==0) f=&candidate;
      assert(f);
      const double x=value(a), y=value(b), expected=value(result);
      compare(*f,x,y,f==&power ? mk_math::pow(x,y) : f->actual(x),expected);
      ++vectors;
    }
    assert(vectors >= 1800);
    std::printf("high-precision independent vectors=%u\n",vectors);
  }
  uint64_t total=0, failures=0;
  for (const Function& f: functions) {
    std::printf("%s cases=%llu worst_ulp=%llu failures=%llu\n",f.name,
        (unsigned long long)f.cases,(unsigned long long)f.worst,(unsigned long long)f.failures);
    total+=f.cases; failures+=f.failures;
  }
  std::printf("pow cases=%llu worst_ulp=%llu failures=%llu\n",
      (unsigned long long)power.cases,(unsigned long long)power.worst,(unsigned long long)power.failures);
  total+=power.cases; failures+=power.failures;
  std::printf("compact math differential: %llu cases, %llu failures\n",
      (unsigned long long)total,(unsigned long long)failures);
  return failures ? 1 : 0;
}
