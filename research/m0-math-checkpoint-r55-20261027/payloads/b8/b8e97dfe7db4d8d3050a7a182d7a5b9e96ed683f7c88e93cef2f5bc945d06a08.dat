#ifndef MK61_USB_SCREEN_HPP
#define MK61_USB_SCREEN_HPP

#include "config.h"
#include "rust_types.h"

namespace usb_screen {

enum class State : u8 {
  IDLE,
  WAITING_FOR_HOST,
  ATTACHED,
};

enum class Event : u8 {
  NONE,
  ATTACHED,
  CONNECTION_LOST,
  EXITED,
};

#if MK61_ENABLE_USB_SCREEN
bool start(void);
void cancel(void);
void service(void);
// CDC control/key transport only: no display, allocation or filesystem I/O.
void service_during_storage(void);
State state(void);
bool active(void);
bool attached(void);
#if defined(MK61_KEY_WAIT_BENCHMARK) && MK61_KEY_WAIT_BENCHMARK
void benchmarkDetachAfterKey(void);
#endif
bool wireBusy(void);
bool idleWorkPending(void);
bool takeTerminalByte(u8& value);
Event takeEvent(void);
#else
inline bool start(void) { return false; }
inline void cancel(void) {}
inline void service(void) {}
inline void service_during_storage(void) {}
inline State state(void) { return State::IDLE; }
inline bool active(void) { return false; }
inline bool attached(void) { return false; }
#if defined(MK61_KEY_WAIT_BENCHMARK) && MK61_KEY_WAIT_BENCHMARK
inline void benchmarkDetachAfterKey(void) {}
#endif
inline bool wireBusy(void) { return false; }
inline bool idleWorkPending(void) { return false; }
inline bool takeTerminalByte(u8&) { return false; }
inline Event takeEvent(void) { return Event::NONE; }
#endif

} // пространство имён usb_screen

#endif
