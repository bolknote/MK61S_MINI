#ifndef MK61_DISK_ACTIVITY_HPP
#define MK61_DISK_ACTIVITY_HPP

#include "config.h"
#include "rust_types.h"
class MK61Display;

#if defined(MK61_DISPLAY_UC1609) || MK61_ENABLE_USB_SCREEN
#define MK61_DISK_ACTIVITY_SUPPORTED 1
#else
#define MK61_DISK_ACTIVITY_SUPPORTED 0
#endif

namespace disk_activity {

#if MK61_DISK_ACTIVITY_SUPPORTED
// Called only between SPI transactions. Never runs the foreground loop or
// feeds the watchdog; a failed storage operation must remain observable.
// note() is an explicit USB request (including cached sectors). Raw NOR I/O
// uses storageIO(): catalog/settings reads outside a file operation stay quiet.
void note(void);
void poll(void);
void setFileOperation(bool active);
void storageIO(void);

struct Activity {
  u32 last = 0;
  bool seen = false;
  u8 pause_depth = 0; // Fits the existing alignment padding; no backing buffer.
  void note(u32 now) {
    if(!pause_depth) { last = now; seen = true; }
  }
  void pause() {
    if(pause_depth == 255) __builtin_trap();
    ++pause_depth;
    seen = false;
  }
  void resume() {
    if(!pause_depth) __builtin_trap();
    --pause_depth;
  }
  u8 indicator(u32 now) {
    if(pause_depth) return 0;
    // Keep a brief read visible, but do not turn idle time into disk activity.
    if(seen && (u32) (now - last) >= 160U) seen = false;
    return seen ? (u8) (1U + ((now / 160U) & 1U)) : 0U;
  }
};

// Foreground artwork owns the complete screen during startup. Drop activity
// there (including a pending icon) instead of replaying it after the splash.
class Pause {
 public:
  explicit Pause(MK61Display& display);
  ~Pause();
  Pause(const Pause&) = delete;
  Pause& operator=(const Pause&) = delete;
 private:
  MK61Display& display_;
};

// Independent of the clock/text/bitmap owner. Only the covered 16x16 pixels
// are retained; new frames replace that backing even while the icon is on.
class Overlay {
 public:
  static constexpr u8 LEFT = 176, WIDTH = 16, PAGES = 2;
  bool set(u8 value) {
    if(value == state_) return false;
    state_ = value;
    return true;
  }
  u8 state(void) const { return state_; }
  void compose(u8 p, u8 first, u8 count, u8* pixels) {
    if(p >= PAGES || first + (u16) count <= LEFT) return;
    for(u16 i = first < LEFT ? LEFT - first : 0; i < count; ++i) {
      const u16 x = first + i - LEFT;
      if(x >= WIDTH) break;
      background_[p * WIDTH + x] = pixels[i];
      if(state_) pixels[i] = iconColumn(p, (u8) x, state_);
    }
  }
  void page(u8 p, u8* pixels) const {
    if(p >= PAGES) return;
    for(u8 x = 0; x < WIDTH; ++x)
      pixels[x] = state_ ? iconColumn(p, x, state_) : background_[p * WIDTH + x];
  }
  void restore(u8* frame) const {
    if(!state_) return;
    for(u8 p = 0; p < PAGES; ++p)
      for(u8 x = 0; x < WIDTH; ++x)
        frame[p * 192U + LEFT + x] = background_[p * WIDTH + x];
  }
  void composeFrame(u8* frame) {
    for(u8 p = 0; p < PAGES; ++p) compose(p, LEFT, WIDTH, frame + p * 192U + LEFT);
  }
 private:
  static u8 iconColumn(u8 page, u8 x, u8 state) {
    static constexpr u16 rows[] = {
      0, 0, 0x07FC, 0x0DF4, 0x0C44, 0x0C44, 0x0DF4, 0x0804,
      0x09F4, 0x0904, 0x0904, 0x0904, 0x0FFC, 0, 0, 0
    };
    u8 value = 0;
    for(u8 bit = 0; bit < 8; ++bit) {
      const u8 y = page * 8U + bit;
      if((rows[y] & (1U << x)) ||
         (state == 2 && x >= 14 && y >= 10 && y <= 11)) value |= 1U << bit;
    }
    return value;
  }
  u8 background_[WIDTH * PAGES] = {};
  u8 state_ = 0;
};

#if defined(MK61_DISPLAY_UC1609)
void savingPage(u8 page, u8 step, bool russian, u8* pixels);
#endif
#else
inline void note(void) {}
inline void poll(void) {}
inline void setFileOperation(bool) {}
inline void storageIO(void) {}
class Pause {
 public:
  explicit Pause(MK61Display&) {}
  Pause(const Pause&) = delete;
  Pause& operator=(const Pause&) = delete;
};
#endif

} // namespace disk_activity
#endif
