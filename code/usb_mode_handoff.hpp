#ifndef MK61_USB_MODE_HANDOFF_HPP
#define MK61_USB_MODE_HANDOFF_HPP

namespace usb_mode_handoff {

// Tracks ownership of the single USB device shared by CDC and MSC.
// CDC needs one start during normal boot and one restart after it has actually
// been stopped for MSC.  A failure while MSC is only being prepared leaves CDC
// alive, so restarting it in that path is both unnecessary and unsafe.
class TerminalLifecycle {
 public:
  constexpr TerminalLifecycle() : start_required_(true), generation_(0) {}

  void cdc_stopped() {
    start_required_ = true;
    ++generation_;
  }

  bool consume_start_required() {
    const bool result = start_required_;
    start_required_ = false;
    return result;
  }

  unsigned generation() const { return generation_; }

 private:
  bool start_required_;
  unsigned generation_;
};

} // namespace usb_mode_handoff

#endif
