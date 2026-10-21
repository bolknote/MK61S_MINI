#include "diagnostics.hpp"
#include "version.hpp"
#include "storage.hpp"
#include "script.hpp"
#include "mk8_codec.hpp"
#include "terminal_command_ids.hpp"
#include "terminal_core.hpp"
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cstdint>
#if defined(PICO_ON_DEVICE)
#include <malloc.h>
#include "pico/stdlib.h"
#include "pico/unique_id.h"
#include "hardware/watchdog.h"
#include "hardware/structs/watchdog.h"
#include "hardware/structs/vreg_and_chip_reset.h"
extern "C" { extern char __end__,__HeapLimit; }
#if defined(MK61_PICOCALC_SAMPLE_PROFILE) && MK61_PICOCALC_SAMPLE_PROFILE
#include "hardware/clocks.h"
#include "hardware/exception.h"
#include "hardware/structs/systick.h"
#include "hardware/sync.h"
#endif
#else
#include <chrono>
#endif
#ifndef MK61_PICOCALC_BUILD_ID
#define MK61_PICOCALC_BUILD_ID 0x00060000U
#endif

namespace picocalc { namespace diagnostics {
namespace {
constexpr u32 MAGIC=0x50444336U;
struct Retained {
  u32 magic,inverse,boots,reloads,maximum_gap_ms;
  crash_dump_format::Record crash;
};
#if defined(PICO_ON_DEVICE)
Retained retained __attribute__((section(".uninitialized_data.picocalc_diagnostics")));
#else
Retained retained{};
#endif
Watchdog watchdog;
u64 (*clock_source)()=nullptr;
u64 last_feed=0,profile_since=0,profile_elapsed=0;
u32 reset_reason=0,profile_generation=1;
bool enabled=false;
Sample samples[(unsigned)Point::COUNT];
volatile u32 current_state=0,current_detail=0,current_uptime=0;
#if defined(PICO_ON_DEVICE) && defined(MK61_PICOCALC_SAMPLE_PROFILE) && MK61_PICOCALC_SAMPLE_PROFILE
struct PcBucket { u32 address,count; };
PcBucket pc_buckets[1024]{};
volatile u32 pc_samples=0,pc_dropped=0;
exception_handler_t previous_systick=nullptr;
bool sampling=false;
extern "C" __attribute__((used,noinline)) void mk61_picocalc_sample_pc(const u32* frame) {
  const u32 address=frame[6]&~63U;
  ++pc_samples;
  const unsigned start=(address>>6)*2654435761U>>22;
  for(unsigned i=0;i<32;++i) {
    auto& bucket=pc_buckets[(start+i)&1023];
    if(!bucket.address || bucket.address==address) { bucket.address=address;++bucket.count;return; }
  }
  ++pc_dropped;
}
__attribute__((naked)) void sample_interrupt() {
  __asm__ volatile("mov r0, lr\nmovs r1, #4\ntst r0, r1\nbeq 1f\nmrs r0, psp\nb 2f\n1: mrs r0, msp\n2: b mk61_picocalc_sample_pc");
}
void sample_start() {
  if(sampling) return;
  previous_systick=exception_set_exclusive_handler(SYSTICK_EXCEPTION,sample_interrupt);
  systick_hw->rvr=clock_get_hz(clk_sys)/1000-1;systick_hw->cvr=0;
  sampling=true;systick_hw->csr=7;
}
void sample_stop() {
  if(!sampling) return;
  systick_hw->csr=0;sampling=false;
  exception_restore_handler(SYSTICK_EXCEPTION,previous_systick);
}
void sample_reset() {
  const u32 irq=save_and_disable_interrupts();
  std::memset(pc_buckets,0,sizeof(pc_buckets));pc_samples=pc_dropped=0;
  restore_interrupts(irq);
}
#else
void sample_start() {}
void sample_stop() {}
void sample_reset() {}
#endif
u64 now() {
  if(clock_source) return clock_source();
#if defined(PICO_ON_DEVICE)
  return time_us_64();
#else
  return (u64)std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
#endif
}
struct Text {
  char* out;unsigned capacity,used=0;bool valid=true;
  void print(const char* format,...) {
    if(!valid || !out || used>=capacity) { valid=false;return; }
    va_list args;va_start(args,format);
    const int n=std::vsnprintf(out+used,capacity-used,format,args);va_end(args);
    if(n<0 || (unsigned)n>=capacity-used) { valid=false;return; }
    used+=(unsigned)n;
  }
  unsigned size() const { return valid?used:0; }
};
bool save_path(const char* args,const char* cwd,char out[files::PATH_SIZE]) {
  args=terminal_core::skip_spaces(args);
  usize length=std::strlen(args);
  if(length>=2 && (args[0]=='"' || args[0]=='\'')) {
    if(args[length-1]!=args[0]) return false;
    ++args;length-=2;
  }
  if(!length || length>=files::PATH_SIZE) return false;
  u8 utf8[files::PATH_SIZE];usize used=0;
  if(!mk8::to_utf8((const u8*)args,length,utf8,sizeof(utf8)-1,used)) return false;
  utf8[used]=0;
  return script::normalize_path(cwd,(const char*)utf8,out);
}
}
void initialize(u32 flags,bool from_watchdog,u64 (*clock)()) {
  clock_source=clock;
#if defined(PICO_ON_DEVICE)
  flags=watchdog_hw->reason | (vreg_and_chip_reset_hw->chip_reset<<8);
  from_watchdog=watchdog_enable_caused_reboot();
#endif
  const bool retained_valid=retained.magic==MAGIC && retained.inverse==~MAGIC;
  watchdog={};watchdog.boot_was_watchdog=from_watchdog;
  watchdog.previous_valid=retained_valid;
  if(retained_valid) {
    watchdog.previous_reloads=retained.reloads;
    watchdog.previous_gap_ms=retained.maximum_gap_ms;
    ++retained.boots;
  } else {
    retained={};retained.magic=MAGIC;retained.inverse=~MAGIC;retained.boots=1;
  }
  if(!crash_dump_format::valid(retained.crash)) retained.crash.magic=0;
  else retained.crash.rcc_csr_after_reboot=flags;
  if(retained.crash.magic) retained.crash.crc32=crash_dump_format::calculate_crc(retained.crash);
  retained.reloads=retained.maximum_gap_ms=0;
  reset_reason=flags;last_feed=now();enabled=false;profile_reset();context(State::BOOT);
}
void watchdog_started(u32 timeout_ms) {
  watchdog.running=true;watchdog.timeout_ms=timeout_ms;last_feed=now();
}
void feed_watchdog() {
  const u64 time=now();
  if(!watchdog.running || time-last_feed<10000) return;
  const u32 gap=(u32)((time-last_feed)/1000);
  if(gap>watchdog.maximum_gap_ms) watchdog.maximum_gap_ms=gap;
  ++watchdog.reloads;last_feed=time;
  retained.reloads=watchdog.reloads;retained.maximum_gap_ms=watchdog.maximum_gap_ms;
#if defined(PICO_ON_DEVICE)
  watchdog_update();
#endif
}
Watchdog watchdog_status() { return watchdog; }
void context(State state,u32 detail) {
  current_state=(u32)state;current_detail=detail;current_uptime=(u32)(now()/1000);
}
void profile_start() { if(!enabled) { profile_since=now();enabled=true;++profile_generation;sample_start(); } }
void profile_stop() { if(enabled) { sample_stop();profile_elapsed+=now()-profile_since;enabled=false;++profile_generation; } }
void profile_reset() {
  sample_reset();
  for(auto& item:samples) item={};
  profile_elapsed=0;profile_since=now();++profile_generation;
}
bool profiling() { return enabled; }
Sample sample(Point point) { return (unsigned)point<(unsigned)Point::COUNT?samples[(unsigned)point]:Sample{}; }
void add_sample(Point point,u64 elapsed) {
  if(!enabled || (unsigned)point>=(unsigned)Point::COUNT) return;
  auto& out=samples[(unsigned)point];++out.calls;out.total_us+=elapsed;
  const u32 maximum=elapsed>UINT32_MAX?UINT32_MAX:(u32)elapsed;
  if(maximum>out.maximum_us) out.maximum_us=maximum;
}
Scope::Scope(Point point):point_(point),start_(enabled?now():0),generation_(profile_generation) {}
Scope::~Scope() { if(enabled && generation_==profile_generation) add_sample(point_,now()-start_); }
void capture_fault(const u32* frame,const u32* callee,u32 exc_return,u32 msp,u32 psp,u32 control,u32 primask) {
  const u32 sequence=crash_available()?retained.crash.sequence+1:1;
  auto& out=retained.crash;
  volatile u32* words=(volatile u32*)&out;
  for(unsigned i=0;i<sizeof(out)/sizeof(u32);++i) words[i]=0;
  out.version=crash_dump_format::VERSION;out.size=sizeof(out);out.sequence=sequence;
  out.exception_number=3;out.exc_return=exc_return;out.msp=msp;out.psp=psp;
  u32* stacked=&out.stacked_r0;
  for(unsigned i=0;i<8;++i) stacked[i]=frame?frame[i]:crash_dump_format::INVALID_STACK_WORD;
  if(frame) out.capture_flags|=crash_dump_format::FRAME_VALID;
  if(exc_return&4) out.capture_flags|=crash_dump_format::STACK_USED_PSP;
  u32* saved=&out.r4;
  for(unsigned i=0;i<8;++i) saved[i]=callee?callee[i]:crash_dump_format::INVALID_STACK_WORD;
  if(callee) out.capture_flags|=crash_dump_format::CALLEE_SAVED_VALID;
  out.control=control;out.primask=primask;out.rcc_csr_at_fault=reset_reason;
  out.build_id=MK61_PICOCALC_BUILD_ID;
  out.runtime_uptime_ms=current_uptime;out.runtime_state=current_state;out.runtime_detail=current_detail;
  out.crc32=crash_dump_format::calculate_crc(out);out.magic=crash_dump_format::MAGIC;
}
bool crash_available() { return crash_dump_format::valid(retained.crash); }
bool crash_copy(crash_dump_format::Record& out) {
  if(!crash_available()) return false;
  out=retained.crash;return true;
}
void clear_crash() { retained.crash.magic=0; }
unsigned crash_report(char* out,unsigned capacity) {
  Text text{out,capacity};crash_dump_format::Record record{};
  if(!crash_copy(record)) { text.print("CRASH=NONE\r\n");return text.size(); }
  text.print("MK61S PicoCalc crash / RP2040 Cortex-M0+\r\n"
      "BUILD=%08lX CURRENT_BUILD=%08lX VERSION=%s SEQUENCE=%lu CRC=OK\r\n"
      "EXCEPTION=HardFault EXC_RETURN=%08lX FLAGS=%08lX\r\n"
      "PC=%08lX LR=%08lX XPSR=%08lX MSP=%08lX PSP=%08lX\r\n",
      (unsigned long)record.build_id,(unsigned long)MK61_PICOCALC_BUILD_ID,VERSION,
      (unsigned long)record.sequence,(unsigned long)record.exc_return,(unsigned long)record.capture_flags,
      (unsigned long)record.stacked_pc,(unsigned long)record.stacked_lr,(unsigned long)record.stacked_xpsr,
      (unsigned long)record.msp,(unsigned long)record.psp);
  text.print("R0=%08lX R1=%08lX R2=%08lX R3=%08lX R12=%08lX\r\n",
      (unsigned long)record.stacked_r0,(unsigned long)record.stacked_r1,(unsigned long)record.stacked_r2,
      (unsigned long)record.stacked_r3,(unsigned long)record.stacked_r12);
  text.print("R4=%08lX R5=%08lX R6=%08lX R7=%08lX R8=%08lX R9=%08lX R10=%08lX R11=%08lX\r\n",
      (unsigned long)record.r4,(unsigned long)record.r5,(unsigned long)record.r6,(unsigned long)record.r7,
      (unsigned long)record.r8,(unsigned long)record.r9,(unsigned long)record.r10,(unsigned long)record.r11);
  text.print("CONTROL=%08lX PRIMASK=%08lX RESET_AT_FAULT=%08lX RESET_AFTER_REBOOT=%08lX\r\n"
      "UPTIME_MS=%lu STATE=%lu DETAIL=%lu\r\n",
      (unsigned long)record.control,(unsigned long)record.primask,(unsigned long)record.rcc_csr_at_fault,
      (unsigned long)record.rcc_csr_after_reboot,(unsigned long)record.runtime_uptime_ms,
      (unsigned long)record.runtime_state,(unsigned long)record.runtime_detail);
  return text.size();
}
unsigned profile_report(char* out,unsigned capacity,bool core_only) {
  Text text{out,capacity};
  text.print("PROFILE=%s TIMER=US ELAPSED_US=%llu (inclusive)\r\n",enabled?"RUNNING":"STOPPED",
      (unsigned long long)(profile_elapsed+(enabled?now()-profile_since:0)));
  const char* names[]={"core","usb","display","storage","language","app","pump","lcd","keyboard","m61"};
  for(unsigned i=0;i<(unsigned)Point::COUNT;++i) {
    if(core_only && i!=(unsigned)Point::CORE) continue;
    const auto value=samples[i];
    text.print("%-8s calls=%lu total_us=%llu max_us=%lu mean_us=%llu\r\n",names[i],
        (unsigned long)value.calls,(unsigned long long)value.total_us,(unsigned long)value.maximum_us,
        (unsigned long long)(value.calls?value.total_us/value.calls:0));
  }
  return text.size();
}
unsigned status_report(char* out,unsigned capacity) {
  Text text{out,capacity};
  text.print("RESET_REASON=%08lX BOOTS=%lu CRASH=%s BUILD=%08lX\r\n"
      "WATCHDOG=%s TIMEOUT_MS=%lu RELOADS=%lu MAX_GAP_MS=%lu BOOT_WATCHDOG=%u PREVIOUS_VALID=%u PREVIOUS_RELOADS=%lu PREVIOUS_GAP_MS=%lu\r\n",
      (unsigned long)reset_reason,(unsigned long)retained.boots,crash_available()?"AVAILABLE":"NONE",
      (unsigned long)MK61_PICOCALC_BUILD_ID,watchdog.running?"ON":"OFF",(unsigned long)watchdog.timeout_ms,
      (unsigned long)watchdog.reloads,(unsigned long)watchdog.maximum_gap_ms,watchdog.boot_was_watchdog,
      watchdog.previous_valid,(unsigned long)watchdog.previous_reloads,(unsigned long)watchdog.previous_gap_ms);
  return text.size();
}
bool persist_crash() {
  if(!crash_available() || (retained.crash.capture_flags & crash_dump_format::PERSISTED_TO_C5) || !files::ready()) return false;
  char report[1536];const unsigned size=crash_report(report,sizeof(report));
  if(!size) return false;
  for(unsigned suffix=0;suffix<100;++suffix) {
    char path[100];
    std::snprintf(path,sizeof(path),"/crash-picocalc-%08lX-%lu-%u.txt",
        (unsigned long)retained.crash.build_id,(unsigned long)retained.crash.sequence,suffix);
    if(files::exists(path)) continue;
    if(!files::write_text(path,report,size)) return false;
    retained.crash.capture_flags|=crash_dump_format::PERSISTED_TO_C5;
    retained.crash.crc32=crash_dump_format::calculate_crc(retained.crash);return true;
  }
  return false;
}
bool command(u8 id,const char* arguments,const char* cwd,Writer write,void* raw) {
  const char* args=terminal_core::skip_spaces(arguments);
  char report[2048];unsigned size=0;
  bool save=false;
  if(id==CMD_WATCHDOG) {
    if(*args && std::strcmp(args,"status")) return false;
    size=status_report(report,sizeof(report));
  } else if(id==CMD_CRASH) {
    if(!std::strcmp(args,"clear")) { clear_crash();args="show"; }
    if(!*args || !std::strcmp(args,"show")) size=crash_report(report,sizeof(report));
    else if(!std::strncmp(args,"save",4) && (!args[4] || terminal_core::is_space(args[4]))) {
      args=terminal_core::skip_spaces(args+4);save=true;
      if(!*args) args="crash-picocalc.txt";
      if(!crash_available()) return false;
      size=crash_report(report,sizeof(report));
    } else return false;
  } else if(id==CMD_PROFILE) {
#if defined(PICO_ON_DEVICE)
    if(!std::strcmp(args,"heap")) {
      const auto heap=mallinfo();
      const auto capacity=(uintptr_t)&__HeapLimit-(uintptr_t)&__end__;
      size=std::snprintf(report,sizeof(report),
          "HEAP_BYTES=%lu HEAP_USED=%lu HEAP_FREE=%lu HEAP_ARENA=%lu HEAP_FREE_BLOCKS=%lu HEAP_TOP=%lu\r\n",
          (unsigned long)capacity,(unsigned long)heap.uordblks,
          (unsigned long)(capacity-heap.uordblks),(unsigned long)heap.arena,
          (unsigned long)heap.ordblks,(unsigned long)heap.keepcost);
      if(write) write(raw,report,size);
      return write!=nullptr;
    }
#endif
#if defined(PICO_ON_DEVICE) && defined(MK61_PICOCALC_SAMPLE_PROFILE) && MK61_PICOCALC_SAMPLE_PROFILE
    if(!std::strcmp(args,"samples")) {
      if(enabled || !write) return false;
      size=std::snprintf(report,sizeof(report),"PC_SAMPLES=%lu DROPPED=%lu HZ=1000 BUCKET_BYTES=64\r\n",
          (unsigned long)pc_samples,(unsigned long)pc_dropped);write(raw,report,size);
      for(const auto& bucket:pc_buckets) if(bucket.count) {
        size=std::snprintf(report,sizeof(report),"PC=%08lX COUNT=%lu\r\n",(unsigned long)bucket.address,(unsigned long)bucket.count);
        write(raw,report,size);
      }
      return true;
    }
#endif
    if(!std::strcmp(args,"start")) profile_start();
    else if(!std::strcmp(args,"stop")) profile_stop();
    else if(!std::strcmp(args,"reset")) profile_reset();
    else if(!std::strncmp(args,"save",4) && (!args[4] || terminal_core::is_space(args[4]))) {
      args=terminal_core::skip_spaces(args+4);save=true;
      if(!*args) args="profile-picocalc.txt";
    } else if(*args && std::strcmp(args,"core")) return false;
    size=profile_report(report,sizeof(report),!std::strcmp(args,"core"));
  } else return false;
  if(!size) return false;
  if(save) {
    char path[files::PATH_SIZE];
    if(!save_path(args,cwd,path) || !files::write_text(path,report,size)) return false;
    std::snprintf(report,sizeof(report),"Saved diagnostic report\r\n");size=std::strlen(report);
  }
  if(write) write(raw,report,size);
  return true;
}
} }

#if defined(PICO_ON_DEVICE)
extern "C" {
// Independent stack: even an overflowing application stack can be reported.
alignas(8) u32 picocalc_fault_stack[256]
    __attribute__((section(".uninitialized_data.picocalc_fault_stack")));
u32 picocalc_fault_primask;
[[noreturn]] void picocalc_hardfault_capture(const u32* frame,const u32* callee,u32 exc_return,u32 original_msp) {
  const uintptr_t address=(uintptr_t)frame;
  if((address&3U) || address<0x20000000U || address>0x20042000U-8*sizeof(u32)) frame=nullptr;
  u32 control,psp;
  __asm volatile("mrs %0, control" : "=r"(control));
  __asm volatile("mrs %0, psp" : "=r"(psp));
  picocalc::diagnostics::capture_fault(frame,callee,exc_return,original_msp,psp,control,picocalc_fault_primask);
  watchdog_reboot(0,0,1);
  for(;;) __asm volatile("wfi");
}
__attribute__((naked)) void isr_hardfault() {
  __asm volatile(
      "mrs r0, msp\nmov r12, r0\nmov r2, lr\nmovs r3, #4\ntst r2, r3\nbeq 1f\nmrs r0, psp\n1:\n"
      "ldr r3, =picocalc_fault_stack + 992\nmov r1, r3\n"
      "stmia r3!, {r4-r7}\nmov r4, r8\nmov r5, r9\nmov r6, r10\nmov r7, r11\n"
      "stmia r3!, {r4-r7}\nmov sp, r1\nmov r3, r12\n"
      "mrs r4, primask\nldr r5, =picocalc_fault_primask\nstr r4, [r5]\ncpsid i\n"
      "bl picocalc_hardfault_capture\n");
}
}
#endif
