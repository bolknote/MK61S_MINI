#ifndef MK61_DISPLAY_BUFFER_LOAN_HPP
#define MK61_DISPLAY_BUFFER_LOAN_HPP

#include "rust_types.h"
class MK61Display;

// Foreground-only loan of inactive USB framebuffer bytes, or the UC1609
// page buffer when USB is not compiled (physical redraw is then deferred).
// The display must outlive this guard; ATTACH waits until reset/destruction.
class [[nodiscard]] DisplayBufferLoan {
  public:
    constexpr DisplayBufferLoan() : display_(nullptr), memory_(nullptr) {}
    ~DisplayBufferLoan();
    DisplayBufferLoan(const DisplayBufferLoan&) = delete;
    DisplayBufferLoan& operator=(const DisplayBufferLoan&) = delete;
    bool acquire(usize required);
    bool acquire(MK61Display& display, usize required);
    void reset();
    u8* data() const { return memory_; }
    bool ok() const { return memory_ != nullptr; }
  private:
    MK61Display* display_;
    u8* memory_;
};
#endif
