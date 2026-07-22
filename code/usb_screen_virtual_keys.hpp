#ifndef MK61_USB_SCREEN_VIRTUAL_KEYS_HPP
#define MK61_USB_SCREEN_VIRTUAL_KEYS_HPP

#include "keyboard_core.hpp"

namespace usb_screen {

// Отслеживает запрошенное хостом состояние клавиш отдельно от событий,
// фактически достигших очереди калькулятора. Это различие важно при прерывании
// сеанса: ожидающие нажатия нужно отбросить, а доставленным всё ещё требуются
// соответствующие события отпускания.
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

    // Ставит одно отпускание после уже находящихся в очереди событий клавиш.
    // Вызывающий код использует возвращённую клавишу для обновления внешнего
    // состояния удерживаемых клавиш.
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

    // Вызывать только после принятия первого события очередью калькулятора.
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

    // Отбрасывает все недоставленные события и ставит в очередь отпускания лишь
    // для нажатий, уже увиденных калькулятором. Возвращает маску внешнего
    // состояния, которую вызывающий код должен немедленно очистить.
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

} // пространство имён usb_screen

#endif
