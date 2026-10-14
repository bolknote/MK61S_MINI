// Ordinary APP, no private firmware callbacks and no product instrumentation.
// Actual compiler calls are replayed from SRAM; reports use USB Screen CRCs.
#include "mk61_app.h"
#include "vm_scan_candidates.hpp"
#include "vm_scan_fixture.hpp"

namespace c = vm_scan_candidates;
#define KERNEL __attribute__((noipa, flatten, aligned(16)))
static uint8_t report[1536];
static volatile uint32_t checksum;
static uint32_t failures;

template<unsigned Family,unsigned Variant>
__attribute__((always_inline)) static inline uint32_t replay(unsigned dataset,const uint8_t* blob) {
  const ScanGroup& group=fixture_groups[dataset][Family];
  uint32_t total=0;
  for(unsigned at=0;at<group.count;++at) {
    const ScanRecord& r=fixture_records[group.start+at];
    const uint8_t* left=blob+r.left;
    const uint8_t* right=blob+r.right;
    for(unsigned repeat=0;repeat<r.weight;++repeat) {
      // Keep repeated actual calls inside the timed loop, rather than letting
      // LTO hoist a pure scan and multiply its answer by the call weight.
      __asm__ __volatile__("" : : "r"(left),"r"(right) : "memory");
      uint32_t value;
      if constexpr(Family==0) {
        value=Variant==0 ? c::line_scalar(left,r.length) : Variant==1 ?
          c::line_word(left,r.length) : c::line_dsp(left,r.length);
      } else if constexpr(Family==1) {
        value=Variant==0 ? c::spaces_scalar(left,r.length) : Variant==1 ?
          c::spaces_word(left,r.length) : c::spaces_dsp(left,r.length);
      } else if constexpr(Family==2) {
        const unsigned n=Variant==0 ? c::alpha_scalar(left,r.length) : Variant==1 ?
          c::alpha_word(left,r.length) : c::alpha_dsp(left,r.length);
        const bool dotted=n<r.length && left[n]=='.';
        bool same=n!=0 && (dotted ? n>=r.minimum && n<=r.right_length : n==r.right_length);
        if(same) same=Variant==0 ? c::upper_equal_scalar(left,right,n) : Variant==1 ?
          c::upper_equal_word(left,right,n) : c::upper_equal_dsp(left,right,n);
        value=n | ((uint32_t)dotted<<16) | ((uint32_t)same<<17);
      } else {
        value=r.length==r.right_length && (Variant==0 ? c::equal_scalar(left,right,r.length) :
          Variant==1 ? c::equal_word(left,right,r.length) : c::equal_dsp(left,right,r.length));
      }
      total+=value;
    }
  }
  return total;
}
#define BENCH(NAME,FAMILY,VARIANT) extern "C" KERNEL uint32_t NAME(unsigned dataset,const uint8_t* blob) { return replay<FAMILY,VARIANT>(dataset,blob); }
BENCH(vm_line_scalar,0,0)
BENCH(vm_line_word,0,1)
BENCH(vm_line_dsp,0,2)
BENCH(vm_spaces_scalar,1,0)
BENCH(vm_spaces_word,1,1)
BENCH(vm_spaces_dsp,1,2)
BENCH(vm_keyword_scalar,2,0)
BENCH(vm_keyword_word,2,1)
BENCH(vm_keyword_dsp,2,2)
BENCH(vm_equal_scalar,3,0)
BENCH(vm_equal_word,3,1)
BENCH(vm_equal_dsp,3,2)
#undef BENCH
using Function=uint32_t(*)(unsigned,const uint8_t*);
static const Function kernels[]={vm_line_scalar,vm_line_word,vm_line_dsp,
  vm_spaces_scalar,vm_spaces_word,vm_spaces_dsp,vm_keyword_scalar,vm_keyword_word,
  vm_keyword_dsp,vm_equal_scalar,vm_equal_word,vm_equal_dsp};

static volatile uint32_t& reg(uint32_t address) { return *(volatile uint32_t*)(uintptr_t)address; }
static uint32_t cycles() {
  __asm__ __volatile__("" ::: "memory");
  const uint32_t result=reg(0xE0001004U);
  __asm__ __volatile__("" ::: "memory");
  return result;
}
static void put8(unsigned at,uint8_t value) {
  report[at+(at>=176 ? 16 : 0)+(at>=352 ? 16 : 0)]=value;
}
static void put32(unsigned at,uint32_t value) {
  for(unsigned i=0;i<4;++i) put8(at+i,(uint8_t)(value>>(i*8)));
}
static void validate_native(uint8_t* storage) {
  for(unsigned alignment=0;alignment<4;++alignment) for(unsigned n=0;n<=64;++n) {
    uint8_t* p=storage+alignment;
    uint8_t* q=storage+256+3-alignment;
    for(unsigned mode=0;mode<6;++mode) {
      for(unsigned i=0;i<n;++i) {
        p[i]=mode==0 ? ' ' : mode==1 ? '\t' : mode==2 ? 'a' :
          mode==3 ? 'Z' : mode==4 ? '\r' : (uint8_t)(i*37+n);
        q[i]=c::upper(p[i]);
      }
      __asm__ __volatile__("" ::: "memory");
      for(unsigned at=0;at<=n;++at) {
        const uint8_t old=at<n ? p[at] : 0;
        if(at<n) p[at]^=1;
        if(c::line_scalar(p,n)!=c::line_word(p,n) || c::line_scalar(p,n)!=c::line_dsp(p,n) ||
           c::spaces_scalar(p,n)!=c::spaces_word(p,n) || c::spaces_scalar(p,n)!=c::spaces_dsp(p,n) ||
           c::alpha_scalar(p,n)!=c::alpha_word(p,n) || c::alpha_scalar(p,n)!=c::alpha_dsp(p,n) ||
           c::equal_scalar(p,q,n)!=c::equal_word(p,q,n) || c::equal_scalar(p,q,n)!=c::equal_dsp(p,q,n) ||
           c::upper_equal_scalar(p,q,n)!=c::upper_equal_word(p,q,n) ||
           c::upper_equal_scalar(p,q,n)!=c::upper_equal_dsp(p,q,n)) ++failures;
        if(at<n) p[at]=old;
      }
    }
    mk61_api->service();
  }
}
static void benchmark(unsigned dataset,uint8_t* storage) {
  __builtin_memset(report,0,sizeof(report));
  unsigned rows=0;
  constexpr unsigned samples=7;
  for(unsigned alignment=0;alignment<4;++alignment) {
    uint8_t* blob=storage+alignment;
    __builtin_memcpy(blob,fixture_blob,sizeof(fixture_blob));
    for(unsigned family=0;family<4;++family) {
      const auto& group=fixture_groups[dataset][family];
      if(!group.calls) continue;
      const unsigned first=family*3;
      const uint32_t expected=kernels[first](dataset,blob);
      for(unsigned k=0;k<3;++k) {
        if(kernels[first+k](dataset,blob)!=expected) ++failures;
        for(unsigned warmup=0;warmup<4;++warmup) checksum+=kernels[first+k](dataset,blob);
      }
      uint32_t times[3][samples];
      // Roughly similar batch length across source indexing and tiny token
      // predicates. Each sample remains well below a DWT counter wrap.
      const unsigned iterations=group.calls<256 ? 32 : group.calls<2048 ? 8 : 2;
      for(unsigned sample=0;sample<samples;++sample) {
        for(unsigned order=0;order<3;++order) {
          const unsigned k=(sample+order)%3;
          const Function function=kernels[first+k];
          const uint32_t started=cycles();
          for(unsigned iteration=0;iteration<iterations;++iteration)
            checksum+=function(dataset,blob);
          times[k][sample]=cycles()-started;
          mk61_api->service();
        }
      }
      for(unsigned k=0;k<3;++k) {
        for(unsigned i=1;i<samples;++i) {
          const uint32_t value=times[k][i];unsigned j=i;
          while(j && times[k][j-1]>value) {times[k][j]=times[k][j-1];--j;}
          times[k][j]=value;
        }
        const unsigned at=40+rows*20;
        put8(at,(uint8_t)(first+k));put8(at+1,(uint8_t)alignment);
        put32(at+4,iterations);put32(at+8,times[k][0]);
        put32(at+12,times[k][samples/2]);put32(at+16,times[k][samples-1]);
        ++rows;
      }
    }
  }
  report[0]='V';report[1]='S';report[2]='C';report[3]='1';
  put32(4,1);put32(8,dataset);put32(12,rows);put32(16,failures);
  put32(20,(uint32_t)(uintptr_t)vm_line_scalar);put32(24,checksum);
  put32(28,sizeof(fixture_blob));put32(32,sizeof(fixture_records)/sizeof(fixture_records[0]));
}

extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),
      MK61_APP_CAP_TIME|MK61_APP_CAP_GRAPHICS|MK61_APP_CAP_KEYBOARD)) return MK61_APP_RUNTIME_ERROR;
  const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_MEMORY);
  mk61_service_lease lease={};
  if(!services || !services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_WORKSPACE,
       mk61_app_current_kind,sizeof(fixture_blob)+4,&lease)) return MK61_APP_BUSY;
  const uint32_t demcr=reg(0xE000EDFCU),control=reg(0xE0001000U);
  reg(0xE000EDFCU)=demcr|(1U<<24);reg(0xE0001000U)=control|1U;
  failures=0;checksum=0;
  const uint32_t before=cycles();
  for(volatile unsigned i=0;i<32;++i) {}
  if(cycles()==before) ++failures;
  validate_native(lease.data);
  unsigned dataset=0;
  int result=MK61_APP_OK;
  if(!mk61_api->graphics_begin()) result=MK61_APP_RUNTIME_ERROR;
  else {
    benchmark(dataset,lease.data);
    (void)mk61_api->graphics_present(report,sizeof(report));
    for(;;) {
      const int key=mk61_api->key_poll();
      if(key==MK61_APP_KEY_ESC) break;
      if(key==MK61_APP_KEY_DIGIT_1 && dataset+1<fixture_case_count) {
        benchmark(++dataset,lease.data);
        (void)mk61_api->graphics_present(report,sizeof(report));
      }
      mk61_api->delay_ms(1);
    }
    mk61_api->graphics_end();
    if(failures) result=MK61_APP_RUNTIME_ERROR;
  }
  reg(0xE0001000U)=control;reg(0xE000EDFCU)=demcr;
  services->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_WORKSPACE,0,0,&lease);
  return result;
}
