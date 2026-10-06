#include "config.h"
#if MK61_SCREEN_BUFFER_LOAN
#include "display_buffer_loan.hpp"
#include "display.hpp"

namespace {
bool interrupt_context() {
#if defined(__arm__) || defined(__thumb__)
  u32 ipsr = 0;
  __asm__ volatile ("mrs %0, ipsr" : "=r" (ipsr));
  return ipsr != 0;
#else
  return false;
#endif
}
}

bool DisplayBufferLoan::acquire(usize required) {
  return acquire(main_lcd(),required);
}
bool DisplayBufferLoan::acquire(MK61Display& display, usize required) {
  if(interrupt_context() || ok() || !required || display.screen_buffer_loan_active)
    return false;
#if MK61_ENABLE_USB_SCREEN
  if(display.usb_screen_active) return false;
#if defined(MK61_DISPLAY_UC1609)
  constexpr usize prefix = lcd_display::PIXEL_WIDTH;
  if(required > usb_screen::FRAME_BYTES-prefix) return false;
  memory_ = display.render_buffer+prefix;
#else
  if(required > usb_screen::FRAME_BYTES) return false;
  memory_ = display.usb_framebuffer;
#endif
#else
  if(required > lcd_display::PIXEL_WIDTH || display.update_depth==(usize)-1) return false;
  display.beginUpdate();
  memory_ = display.render_buffer;
#endif
  display_ = &display;
  display.screen_buffer_loan_active = true;
  return true;
}
void DisplayBufferLoan::reset() {
  if(display_ && interrupt_context()) __builtin_trap();
  if(display_) {
    display_->screen_buffer_loan_active = false;
#if !MK61_ENABLE_USB_SCREEN
    display_->endUpdate();
#endif
  }
  display_ = nullptr; memory_ = nullptr;
}
DisplayBufferLoan::~DisplayBufferLoan() { reset(); }
#endif
