// Private APP; does not replace the resident EABI or write firmware/settings.
#include "mk61_app.h"
#include "karatsuba-inputs.hpp"
#include <cstdint>
using U=std::uint32_t;
using Wide=std::uint64_t;
using Fn=Wide(*)(Wide,Wide);
extern "C" {
Wide m0_kara_baseline(Wide,Wide);
Wide m0_kara_difference(Wide,Wide);
Wide m0_kara_sum_guarded(Wide,Wide);
void m0_product_baseline(Wide,Wide);
void m0_product_difference(Wide,Wide);
void m0_product_sum_guarded(Wide,Wide);
extern U m0_kara_product_words[4];
}
static volatile Wide sink;
static U micros(){asm volatile("":::"memory");return *(volatile U*)0x40054028;}
static __attribute__((noipa)) Wide identity(Wide a,Wide){return a;}
static const Fn functions[]={reinterpret_cast<Fn>(resident_dmul),m0_kara_baseline,
                            m0_kara_difference,m0_kara_sum_guarded};
static void(*const products[])(Wide,Wide)={m0_product_baseline,m0_product_difference,m0_product_sum_guarded};
static constexpr unsigned Rounds=8,Calls=2048;
struct Row {U failures,first;Wide expected,actual;U times[Rounds],controls[Rounds];};
struct Report {
 U magic,version,hz_before,hz_measure,hz_after,restored,cases,calls,rounds,product_failures;
 Row rows[4];
};
static Report report;
static bool nan(Wide x){return (x&0x7fffffffffffffffULL)>0x7ff0000000000000ULL;}
static bool same(Wide a,Wide b){return a==b || (nan(a)&&nan(b));}
static U measure(Fn f) {
 U elapsed=0;
 for(unsigned start=0;start<Calls;start+=128) {
  mk61_api->service();const U before=micros();
  for(unsigned j=0;j<128;++j){const auto& p=kara_pairs[(start+j)&(KaraTimeCases-1)];sink=f(p.a,p.b);}
  elapsed+=micros()-before;
 }
 return elapsed;
}
struct ClockState {U sys=0,peri=0,peri_ctrl=0,peri_div=0,spi0_hz=0,spi1_hz=0;bool changed=false,restore_attempted=false;};
static_assert(sizeof(ClockState)==28,"Resident clock-state ABI");
extern "C" U mk61_app_flow_step(mk61_app_flow* flow) {
 if(!mk61_app_flow_compatible(flow))return 0;
 const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
 if(!services)return 0;
 // Keep the fixed Flash pointer independent of the relocated APP table;
 // an affine pointer-difference literal would not be an APP relocation.
 uintptr_t footer=footer_address;asm volatile("":"+r"(footer));
 for(unsigned i=0;i<10;++i)if(((volatile const U*)footer)[i]!=footer_words[i])return 0;
 mk61_service_file app{};
 if(!services->call(MK61_SERVICE_FILE_ENTRY,0,flow->current.file_id,0,&app))return 0;
 using Hz=U(*)();using Begin=bool(*)(unsigned,ClockState*);using End=bool(*)(ClockState*);
 const auto hz=(Hz)(uintptr_t)clock_hz_function;
 const auto begin=(Begin)(uintptr_t)clock_begin_function;
 const auto end=(End)(uintptr_t)clock_end_function;
 report.magic=0x4b415231;report.version=1;report.hz_before=hz();report.cases=KaraCases;
 report.calls=Calls;report.rounds=Rounds;
 ClockState clock;bool ok=report.hz_before==125000000 && begin(270,&clock);
 report.hz_measure=hz();ok=ok&&report.hz_measure==270000000;
 if(ok) {
  for(unsigned v=0;v<4;++v) {
   auto& row=report.rows[v];row.first=~0U;
   for(unsigned i=0;i<KaraCases;++i) {
    const auto& p=kara_pairs[i];const Wide actual=functions[v](p.a,p.b);
    if(!same(actual,p.expected)) {
     if(!row.failures){row.first=i;row.expected=p.expected;row.actual=actual;}
     ++row.failures;ok=false;
    }
    if(!(i&31))mk61_api->service();
   }
  }
  // Check all106 integer product bits too, without floating-point rounding.
  for(unsigned i=0;i<KaraTimeCases;++i) {
   const Wide a=(kara_pairs[i].a&0xfffffffffffffULL)|0x10000000000000ULL;
   const Wide b=(kara_pairs[i].b&0xfffffffffffffULL)|0x10000000000000ULL;
   U expected[4];products[0](a,b);
   for(unsigned k=0;k<4;++k)expected[k]=m0_kara_product_words[k];
   for(unsigned v=1;v<3;++v) {
    products[v](a,b);
    for(unsigned k=0;k<4;++k)if(expected[k]!=m0_kara_product_words[k]){++report.product_failures;ok=false;}
   }
   if(!(i&31))mk61_api->service();
  }
  // Incorrect variants never enter the timing stage.
  if(ok) {
   const U warm=micros();unsigned i=0;
   while(micros()-warm<100000) {
    const auto& p=kara_pairs[(i++)&(KaraTimeCases-1)];for(const auto f:functions)sink=f(p.a,p.b);
    mk61_api->service();
   }
   for(unsigned r=0;r<Rounds;++r)for(unsigned k=0;k<4;++k) {
    const unsigned v=(r+k)%4;
    report.rows[v].controls[r]=measure(identity);report.rows[v].times[r]=measure(functions[v]);
   }
  }
 }
 report.restored=end(&clock);report.hz_after=hz();ok=ok&&report.restored&&report.hz_after==report.hz_before;
 mk61_service_write write{"KARAOUT.BIN",(const unsigned char*)&report,sizeof(report),MK61_SERVICE_INVALID_ID};
 ok=services->call(MK61_SERVICE_FILE_WRITE,app.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&write)&&ok;
 mk61_app_flow_exit(flow,ok?MK61_APP_OK:MK61_APP_RUNTIME_ERROR,MK61_FLOW_OK);return 1;
}
