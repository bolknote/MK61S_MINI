// Finite APP-only comparison, bound by the builder to one resident firmware.
#include "mk61_app.h"
#include "mk61_ai_exact_fp32.hpp"
#include "math-benchmark-inputs.hpp"
extern "C" {float expf(float);float sqrtf(float);float roundf(float);}
#include <cstdint>
#include <cstring>
using U=std::uint32_t;
union F { U u;float f; };
using Fn=U(*)(U,U);
using FloatBinary=float(*)(float,float);
using FloatUnary=float(*)(float);
using DoubleBinary=double(*)(double,double);
using DoubleUnary=double(*)(double);
#define NOINLINE __attribute__((noipa))
extern "C" float mk61_m0_sqrtf(float);
extern "C" int* __errno() {static int value;return &value;}
static volatile U sink;
static const mk61_app_services* services;
static U micros(){asm volatile("":::"memory");return *(volatile U*)0x40054028;}
static U raw(float x){F f;f.f=x;return f.u;}
static float value(U x){F f;f.u=x;return f.f;}
static NOINLINE U identity(U a,U){return a;}
template<unsigned Op> static NOINLINE U resident(U a,U b) {
 if constexpr(Op<4)return raw(((FloatBinary)(uintptr_t)resident_functions[Op])(value(a),value(b)));
 return raw(((FloatUnary)(uintptr_t)resident_functions[Op])(value(a)));
}
template<unsigned Op> static NOINLINE U local(U a,U b) {
 volatile float x=value(a),y=value(b);
 if constexpr(Op==0)return raw(x+y);
 if constexpr(Op==1)return raw(x-y);
 if constexpr(Op==2)return raw(x*y);
 if constexpr(Op==3)return raw(x/y);
 if constexpr(Op==4)return raw(sqrtf(x));
 if constexpr(Op==5)return raw(expf(x));
 if constexpr(Op==6)return raw(roundf(x));
}
template<unsigned Op> static NOINLINE U rom32(U a,U b) {
 if constexpr(Op<4)return raw(((FloatBinary)(uintptr_t)rom_float_functions[Op])(value(a),value(b)));
 return raw(((FloatUnary)(uintptr_t)rom_float_functions[Op])(value(a)));
}
template<unsigned Op> static NOINLINE U rom64(U a,U b) {
 if constexpr(Op<4)return raw(float(((DoubleBinary)(uintptr_t)rom_double_functions[Op])(double(value(a)),double(value(b)))));
 return raw(float(((DoubleUnary)(uintptr_t)rom_double_functions[Op])(double(value(a)))));
}
static NOINLINE U own_round(U a,U) {
 const U sign=a&0x80000000U,mag=a&0x7fffffffU,e=mag>>23;
 if(e>=150)return a; // Includes NaNs/infinities, matching finite round behavior.
 if(e<126)return sign;
 if(e==126)return sign|0x3f800000U;
 const unsigned shift=150-e;const U mask=(1U<<shift)-1;
 return sign|((mag+(1U<<(shift-1)))&~mask);
}
template<unsigned Op> static NOINLINE U own(U a,U b) {
 if constexpr(Op==0)return raw(mk61ai::exact_fp32::sum(value(a),value(b)));
 if constexpr(Op==1)return raw(mk61ai::exact_fp32::sum(value(a),value(b^0x80000000U)));
 if constexpr(Op==2)return raw(mk61ai::exact_fp32::product(value(a),value(b)));
 if constexpr(Op==3)return resident<3>(a,b);
 if constexpr(Op==4)return raw(mk61_m0_sqrtf(value(a)));
 if constexpr(Op==5)return raw(float(((DoubleUnary)(uintptr_t)own_exp_function)(double(value(a)))));
 if constexpr(Op==6)return own_round(a,b);
}
template<unsigned Op> static NOINLINE U guarded(U a,U b) {
 if constexpr(Op<4) {
  const U ea=(a>>23)&255,eb=(b>>23)&255;
  if(ea && ea<255 && eb && eb<255) {
   const U r=rom32<Op>(a,b),er=(r>>23)&255;
   if(er && er<255)return r;
  }
  return resident<Op>(a,b);
 }
 if constexpr(Op==4) {
  if(!(a&0x80000000U) && (a&0x7f800000U) && (a&0x7f800000U)!=0x7f800000U)return rom32<4>(a,b);
  return own<4>(a,b);
 }
 if constexpr(Op==5) {
  if((a&0x7fffffffU)<0x42a00000U)return rom32<5>(a,b); // |x|<80, no FTZ range.
  return resident<5>(a,b);
 }
 return own_round(a,b);
}
#define ROW(op) {resident<op>,own<op>,rom32<op>,guarded<op>,local<op>,rom64<op>}
static const Fn functions[7][6]={ROW(0),ROW(1),ROW(2),ROW(3),ROW(4),ROW(5),
 {resident<6>,own<6>,nullptr,guarded<6>,local<6>,nullptr}};
static constexpr unsigned Rounds=6,Calls=2048;
struct Row {U available,failures,first,want,got,max_ulp,baseline_differences;U times[Rounds],controls[Rounds];};
struct Report {U magic,version,hz_before,hz_measure,hz_after,restored,cases,calls,rounds,rom_version;Row rows[7][6];};
static Report result;
static bool nan(U x){return (x&0x7fffffffU)>0x7f800000U;}
static bool same(U a,U b){return a==b || (nan(a)&&nan(b));}
static U ordered(U x){return x&0x80000000U?~x:x|0x80000000U;}
static U measure(Fn f,unsigned op) {
 U total=0;
 for(unsigned start=0;start<Calls;start+=128) {
  mk61_api->service();const U before=micros();
  for(unsigned i=0;i<128;++i) {const auto& v=math_inputs[op][(start+i)&127];sink=f(v.a,v.b);}
  total+=micros()-before;
 }
 return total;
}
struct ClockState {U sys=0,peri=0,peri_ctrl=0,peri_div=0,spi0_hz=0,spi1_hz=0;bool changed=false,restore_attempted=false;};
static_assert(sizeof(ClockState)==28,"Resident clock-state ABI");
extern "C" U mk61_app_flow_step(mk61_app_flow* flow) {
 if(!mk61_app_flow_compatible(flow))return 0;
 services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
 if(!services)return 0;
 mk61_service_file app{};
 if(!services->call(MK61_SERVICE_FILE_ENTRY,0,flow->current.file_id,0,&app))return 0;
 if(*(volatile unsigned char*)0x13!=3)return 0;
 for(unsigned op=0;op<6;++op) {
  if(*(volatile const U*)(rom_sf_table+rom_offsets[op])!=rom_float_functions[op] ||
     *(volatile const U*)(rom_sd_table+rom_offsets[op])!=rom_double_functions[op])return 0;
 }
 using Hz=U(*)();using Begin=bool(*)(unsigned,ClockState*);using End=bool(*)(ClockState*);
 auto hz=(Hz)(uintptr_t)clock_hz_function;auto begin=(Begin)(uintptr_t)clock_begin_function;auto end=(End)(uintptr_t)clock_end_function;
 result.magic=0x414d5431;result.version=1;result.hz_before=hz();result.cases=MathCases;result.calls=Calls;result.rounds=Rounds;result.rom_version=3;
 ClockState clock;bool ok=begin(270,&clock);result.hz_measure=hz();ok=ok&&result.hz_measure==270000000;
 if(ok) {
  // Accuracy is untimed, with boundary values kept separate from normal timing.
  for(unsigned op=0;op<7;++op)for(unsigned v=0;v<6;++v) {
   auto& row=result.rows[op][v];row.first=~0U;if(!functions[op][v])continue;row.available=1;
   for(unsigned i=0;i<MathCases;++i) {
    const auto& x=math_inputs[op][i];U got=functions[op][v](x.a,x.b),base=functions[op][0](x.a,x.b);
    row.baseline_differences+=!same(got,base);
    if(!same(got,x.expected)) {if(!row.failures){row.first=i;row.want=x.expected;row.got=got;}++row.failures;}
    if(!nan(got)&&!nan(x.expected)) {U a=ordered(got),b=ordered(x.expected),d=a>b?a-b:b-a;if(d>row.max_ulp)row.max_ulp=d;}
    if(!(i&31))mk61_api->service();
   }
  }
  // Untimed warmup, then balanced order across six rounds.
  const U warm=micros();unsigned spin=0;
  while(micros()-warm<200000) {for(unsigned op=0;op<7;++op)for(unsigned v=0;v<6;++v)if(functions[op][v]){const auto& x=math_inputs[op][spin&127];sink=functions[op][v](x.a,x.b);}++spin;mk61_api->service();}
  for(unsigned r=0;r<Rounds;++r)for(unsigned op=0;op<7;++op)for(unsigned k=0;k<6;++k) {
   unsigned v=(k+r)%6;if(!functions[op][v])continue;
   result.rows[op][v].controls[r]=measure(identity,op);result.rows[op][v].times[r]=measure(functions[op][v],op);
  }
 }
 result.restored=end(&clock);result.hz_after=hz();ok=ok&&result.restored&&result.hz_after==125000000;
 mk61_service_write out{"MATHOUT.BIN",(const unsigned char*)&result,sizeof(result),MK61_SERVICE_INVALID_ID};
 ok=services->call(MK61_SERVICE_FILE_WRITE,app.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&out)&&ok;
 mk61_app_flow_exit(flow,ok?MK61_APP_OK:MK61_APP_RUNTIME_ERROR,MK61_FLOW_OK);return 1;
}
