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

class Fifo {
  public:
    static constexpr usize CAPACITY = 8;

    Fifo(void) : head_(0), size_(0), data_{} {}

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

class DebouncedRow {
  public:
    DebouncedRow(void) : stable_(0), candidate_(0), changed_at_{} {}

    void reset(t_time_ms now) {
      stable_ = 0;
      candidate_ = 0;
      for(usize column = 0; column < COLUMN_COUNT; column++) changed_at_[column] = now;
    }

    // Returns at most one stabilized column bit. Remaining simultaneous
    // transitions are returned by subsequent calls so no event is lost.
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

} // namespace keyboard_core

#endif
