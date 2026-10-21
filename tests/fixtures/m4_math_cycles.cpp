// Temporary SRAM diagnostic. Build one operation at a time to fit the
// unchanged 20-KiB APP arena. All arithmetic helpers are local, without LTO.
#include "mk61_app.h"
#include "compact_math.hpp"
#include <stdint.h>

union Binary64 {uint64_t bits;double number;};
struct Case {uint64_t a,b;};
static const Case cases[]={M4_BENCH_CASES};
static constexpr unsigned Samples=256,Rounds=9;
struct Header {uint32_t magic,version,operation,cases,samples,rounds;};
struct Row {uint64_t a,b,result;uint32_t cycles,control;};
struct Output {Header header;Row rows[sizeof(cases)/sizeof(*cases)];};
static Output output;
static volatile uint64_t input_a,input_b,sink;
using Function=double(*)(double,double);

__attribute__((noipa)) static double evaluate(double x,double y) {
  (void)y;
  switch (M4_BENCH_OPERATION) {
    case 0:return compact_math::sin(x);
    case 1:return compact_math::cos(x);
    case 2:return compact_math::tan(x);
    case 3:return compact_math::asin(x);
    case 4:return compact_math::acos(x);
    case 5:return compact_math::atan(x);
    case 6:return compact_math::ln(x);
    case 7:return compact_math::log10(x);
    case 8:return compact_math::exp(x);
    case 9:return compact_math::sqrt(x);
    case 10:return compact_math::pow(x,y);
    default:return x;
  }
}
__attribute__((noipa)) static double identity(double x,double) {return x;}
static uint32_t cycles() {
  __asm__ volatile ("":::"memory");
  return *reinterpret_cast<volatile uint32_t*>(0xE0001004);
}
static uint32_t median_time(Function function) {
  uint32_t times[Rounds];
  for (unsigned r=0;r<Rounds;++r) {
    mk61_api->service();
    const uint32_t begin=cycles();
    for (unsigned i=0;i<Samples;++i) {
      Binary64 a,b,result;a.bits=input_a;b.bits=input_b;
      result.number=function(a.number,b.number);sink=result.bits;
    }
    times[r]=cycles()-begin;
  }
  for (unsigned i=1;i<Rounds;++i)
    for (unsigned j=i;j && times[j]<times[j-1];--j) {
      const uint32_t t=times[j];times[j]=times[j-1];times[j-1]=t;
    }
  return times[Rounds/2];
}
int main() {
  const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
  if (!services || !(*reinterpret_cast<volatile uint32_t*>(0xE0001000)&1))
    return MK61_APP_RUNTIME_ERROR;
  output.header={0x3448544D,1,M4_BENCH_OPERATION,
                 unsigned(sizeof(cases)/sizeof(*cases)),Samples,Rounds};
  for (unsigned i=0;i<sizeof(cases)/sizeof(*cases);++i) {
    Row& row=output.rows[i];const Case& c=cases[i];
    input_a=row.a=c.a;input_b=row.b=c.b;
    Binary64 a,b,result;a.bits=c.a;b.bits=c.b;
    result.number=evaluate(a.number,b.number);row.result=result.bits;
    row.control=median_time(identity);row.cycles=median_time(evaluate);
  }
  mk61_service_write file={"M4MATH",reinterpret_cast<const uint8_t*>(&output),
                           sizeof(output),MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,
      MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&file)?
      MK61_APP_OK:MK61_APP_IO_ERROR;
}
