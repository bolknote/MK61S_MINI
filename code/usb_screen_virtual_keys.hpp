#ifndef MK61_USB_SCREEN_VIRTUAL_KEYS_HPP
#define MK61_USB_SCREEN_VIRTUAL_KEYS_HPP

#include "keyboard_core.hpp"

namespace usb_screen {

// Tracks the host's requested key state separately from events that have
// actually reached the calculator queue. This distinction is essential on a
// session abort: pending presses must be discarded, while delivered presses
// still need matching release events.
class VirtualKeyQueue {
  public:
    enum class EnqueueResult : u8 {
      QUEUED,
      IGNORED,
      FULL,
      INVALID,
    };

    constexpr VirtualKeyQueue(void)
      : requested_pressed_(0), delivered_pressed_(0),
        release_all_pending_(false), events_() {}

    EnqueueResult enqueue(u8 key, bool down) {
      if(key >= keyboard_core::KEY_COUNT) return EnqueueResult::INVALID;
      const u64 bit = (u64) 1 << key;
      const bool already_down = (requested_pressed_ & bit) != 0;
      if(already_down == down) return EnqueueResult::IGNORED;

      const i32 event = down ? key : key | keyboard_core::RELEASE_MASK;
      if(!events_.push(event)) return EnqueueResult::FULL;
      if(down) requested_pressed_ |= bit;
      else requested_pressed_ &= ~bit;
      return EnqueueResult::QUEUED;
    }

    void scheduleReleaseAll(void) {
      release_all_pending_ = requested_pressed_ != 0;
    }

    // Stages one release behind any already queued key events. The caller uses
    // the returned key to update the keyboard's external held-key state.
    bool stageNextRelease(u8& key) {
      if(!release_all_pending_) return false;
      for(u8 candidate = 0; candidate < keyboard_core::KEY_COUNT;
          candidate++) {
        const u64 bit = (u64) 1 << candidate;
        if((requested_pressed_ & bit) == 0) continue;
        if(!events_.push(candidate | keyboard_core::RELEASE_MASK)) {
          return false;
        }
        requested_pressed_ &= ~bit;
        release_all_pending_ = requested_pressed_ != 0;
        key = candidate;
        return true;
      }
      release_all_pending_ = false;
      return false;
    }

    i32 front(void) const { return events_.peek(); }

    // Call only after the front event was accepted by the calculator queue.
    bool markFrontDelivered(void) {
      const i32 event = events_.peek();
      if(event < 0) return false;
      const u8 key = (u8) (event & ~((i32) keyboard_core::RELEASE_MASK));
      const u64 bit = (u64) 1 << key;
      if((event & keyboard_core::RELEASE_MASK) != 0) {
        delivered_pressed_ &= ~bit;
      } else {
        delivered_pressed_ |= bit;
      }
      events_.pop();
      return true;
    }

    // Drops every undelivered event and queues releases only for presses that
    // were already observed by the calculator. Returns the external-state mask
    // that the caller must clear immediately.
    u64 abortPending(void) {
      const u64 external_pressed = requested_pressed_;
      requested_pressed_ = 0;
      release_all_pending_ = false;
      events_.clear();
      for(u8 key = 0; key < keyboard_core::KEY_COUNT; key++) {
        const u64 bit = (u64) 1 << key;
        if((delivered_pressed_ & bit) != 0) {
          (void) events_.push(key | keyboard_core::RELEASE_MASK);
        }
      }
      return external_pressed;
    }

    u64 requestedPressed(void) const { return requested_pressed_; }
    u64 deliveredPressed(void) const { return delivered_pressed_; }
    usize pendingEvents(void) const { return events_.size(); }

  private:
    u64 requested_pressed_;
    u64 delivered_pressed_;
    bool release_all_pending_;
    keyboard_core::FixedFifo<keyboard_core::KEY_COUNT * 2> events_;
};

} // namespace usb_screen

#endif
