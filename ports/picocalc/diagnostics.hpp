#ifndef MK61_PICOCALC_DIAGNOSTICS_HPP
#define MK61_PICOCALC_DIAGNOSTICS_HPP
#include "rust_types.h"
#include "crash_dump_format.hpp"

namespace picocalc { namespace diagnostics {
enum class Point : u8 { CORE, USB, DISPLAY, STORAGE, LANGUAGE, APP, PUMP, LCD, KEYBOARD, M61, COUNT };
enum class State : u32 { BOOT, CALCULATOR, MENU, M61, USB_DISK, SLEEP, APP, LANGUAGE };
struct Sample { u64 total_us=0;u32 calls=0,maximum_us=0; };
struct Watchdog {
  bool running=false,boot_was_watchdog=false,previous_valid=false;
  u32 timeout_ms=0,reloads=0,maximum_gap_ms=0,previous_reloads=0,previous_gap_ms=0;
};
void initialize(u32 reset_flags=0,bool watchdog_reset=false,u64 (*clock)()=nullptr);
void watchdog_started(u32 timeout_ms);
void feed_watchdog();
Watchdog watchdog_status();
void context(State state,u32 detail=0);
void profile_start();
void profile_stop();
void profile_reset();
bool profiling();
Sample sample(Point point);
void add_sample(Point point,u64 elapsed);
class Scope {
public:
  explicit Scope(Point point);
  ~Scope();
private:
  Point point_;u64 start_;u32 generation_;
};
// Fault capture itself performs only bounded RAM writes and CRC calculation.
// Pointers are validated by the ARM trampoline before this shared writer.
void capture_fault(const u32* frame,const u32* callee,u32 exc_return,
                   u32 msp,u32 psp,u32 control,u32 primask);
bool crash_available();
bool crash_copy(crash_dump_format::Record& out);
void clear_crash();
unsigned crash_report(char* out,unsigned capacity);
unsigned profile_report(char* out,unsigned capacity,bool core_only=false);
unsigned status_report(char* out,unsigned capacity);
bool persist_crash();
using Writer=void(*)(void*,const char*,unsigned);
bool command(u8 id,const char* args,const char* cwd,Writer write,void* context);
} }
#endif
