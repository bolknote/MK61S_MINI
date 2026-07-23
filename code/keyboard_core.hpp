#ifndef KEYBOARD_CORE_HPP
#define KEYBOARD_CORE_HPP

#include "rust_types.h"

namespace keyboard_core {

static constexpr usize ROW_COUNT = 5;
static constexpr usize COLUMN_COUNT = 8;
static constexpr usize KEY_COUNT = ROW_COUNT * COLUMN_COUNT;
static constexpr u8 RELEASE_MASK = 0x40;
static constexpr t_time_ms DEBOUNCE_MS = 30;

inline bool time_reached(t_time_ms now, t_time_ms target) {
  return (i32) (now - target) >= 0;
}

inline bool valid_scan_code(i32 scan_code) {
  if(scan_code < 0 || scan_code > 0x7F) return false;
  return (scan_code & ~((i32) RELEASE_MASK)) < (i32) KEY_COUNT;
}

template<usize CapacityValue>
class FixedFifo {
  public:
    static constexpr usize CAPACITY = CapacityValue;
    static_assert(CAPACITY > 0, "keyboard FIFO must not be empty");

    constexpr FixedFifo(void) : head_(0), size_(0), data_{} {}

    void clear(void) {
      head_ = 0;
      size_ = 0;
    }

    bool empty(void) const { return size_ == 0; }
    bool full(void) const { return size_ == CAPACITY; }
    usize size(void) const { return size_; }

    bool push(i32 scan_code) {
      if(!valid_scan_code(scan_code) || full()) return false;
      data_[(head_ + size_) % CAPACITY] = (u8) scan_code;
      size_++;
      return true;
    }

    i32 peek(usize index = 0) const {
      if(index >= size_) return -1;
      return data_[(head_ + index) % CAPACITY];
    }

    i32 pop(void) {
      if(empty()) return -1;
      const u8 value = data_[head_];
      head_ = (head_ + 1) % CAPACITY;
      size_--;
      return value;
    }

  private:
    usize head_;
    usize size_;
    u8 data_[CAPACITY];
};

using Fifo = FixedFifo<8>;

class PressEdgeLatch {
  public:
    constexpr PressEdgeLatch(void) : pending_(0) {
      static_assert(KEY_COUNT <= 64, "keyboard press latch exceeds u64");
    }

    void reset(void) { pending_ = 0; }

    void noteRow(usize row, u8 columns) {
      if(row >= ROW_COUNT) return;
      for(usize column = 0; column < COLUMN_COUNT; column++) {
        const u8 bit = (u8) (1u << column);
        if((columns & bit) == 0) continue;
        const usize key_code = column * ROW_COUNT + row;
        pending_ |= (u64) 1U << key_code;
      }
    }

    bool take(i32 key_code) {
      if(key_code < 0 || key_code >= (i32) KEY_COUNT) return false;
      const u64 bit = (u64) 1U << (u8) key_code;
      if((pending_ & bit) == 0) return false;
      pending_ &= ~bit;
      return true;
    }

  private:
    u64 pending_;
};

class ExternalKeyState {
  public:
    constexpr ExternalKeyState(void)
      : pressed_(0), held_key_(-1), hold_quant_(-1), next_hold_ms_(0) {
      static_assert(KEY_COUNT <= 64, "external key mask exceeds u64");
    }

    void reset(void) {
      pressed_ = 0;
      clearHold();
      next_hold_ms_ = 0;
    }

    bool press(i32 key_code, t_time_ms now, t_time_ms hold_period_ms) {
      if(!validKey(key_code)) return false;
      const u64 bit = bitFor(key_code);
      if((pressed_ & bit) != 0) return false;
      pressed_ |= bit;
      held_key_ = key_code;
      hold_quant_ = -1;
      next_hold_ms_ = now + hold_period_ms;
      return true;
    }

    bool release(i32 key_code, i32& unhold_quant) {
      unhold_quant = -1;
      if(!validKey(key_code)) return false;
      const u64 bit = bitFor(key_code);
      if((pressed_ & bit) == 0) return false;
      pressed_ &= ~bit;
      if(held_key_ == key_code) {
        unhold_quant = hold_quant_;
        clearHold();
      }
      return true;
    }

    bool pollHold(t_time_ms now, t_time_ms hold_period_ms,
                  i32& held_key, i32& hold_quant) {
      if(held_key_ < 0 || !time_reached(now, next_hold_ms_)) return false;
      hold_quant_++;
      next_hold_ms_ = now + hold_period_ms;
      held_key = held_key_;
      hold_quant = hold_quant_;
      return true;
    }

    void clearHold(void) {
      held_key_ = -1;
      hold_quant_ = -1;
    }

    bool anyPressed(void) const { return pressed_ != 0; }

    bool pressed(i32 key_code) const {
      return validKey(key_code) && (pressed_ & bitFor(key_code)) != 0;
    }

  private:
    static bool validKey(i32 key_code) {
      return key_code >= 0 && key_code < (i32) KEY_COUNT;
    }

    static u64 bitFor(i32 key_code) {
      return (u64) 1U << (u8) key_code;
    }

    u64 pressed_;
    i32 held_key_;
    i32 hold_quant_;
    t_time_ms next_hold_ms_;
};

class DebouncedRow {
  public:
    constexpr DebouncedRow(void) : stable_(0), candidate_(0), changed_at_{} {}

    void reset(t_time_ms now) {
      stable_ = 0;
      candidate_ = 0;
      for(usize column = 0; column < COLUMN_COUNT; column++) changed_at_[column] = now;
    }

  // Возвращает не более одного стабилизированного бита столбца. Остальные
  // одновременные переходы возвращаются последующими вызовами, поэтому ни одно
  // событие не теряется.
    u8 update(u8 sample, t_time_ms now) {
      for(usize column = 0; column < COLUMN_COUNT; column++) {
        const u8 bit = (u8) (1u << column);

        if((candidate_ & bit) != (sample & bit)) {
          if((sample & bit) != 0) candidate_ |= bit;
          else candidate_ &= (u8) ~bit;
          changed_at_[column] = now;
          continue;
        }

        if((stable_ & bit) != (candidate_ & bit) &&
           (t_time_ms) (now - changed_at_[column]) >= DEBOUNCE_MS) {
          if((candidate_ & bit) != 0) stable_ |= bit;
          else stable_ &= (u8) ~bit;
          return bit;
        }
      }

      return 0;
    }

    bool pressed_or_pending(void) const { return (stable_ | candidate_) != 0; }
    u8 candidate_mask(void) const { return candidate_; }

    bool pressed(usize column) const {
      return column < COLUMN_COUNT && (stable_ & (u8) (1u << column)) != 0;
    }

    u8 state_mask(usize column) const {
      if(column >= COLUMN_COUNT) return RELEASE_MASK;
      return pressed(column) ? 0 : RELEASE_MASK;
    }

  private:
    u8 stable_;
    u8 candidate_;
    t_time_ms changed_at_[COLUMN_COUNT];
};

inline isize first_set_bit(u8 value) {
  for(usize bit = 0; bit < COLUMN_COUNT; bit++) {
    if((value & (u8) (1u << bit)) != 0) return (isize) bit;
  }
  return -1;
}

} // пространство имён keyboard_core

#endif
