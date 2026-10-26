#ifndef MK61_CHIP8_FRAME_PACER_HPP
#define MK61_CHIP8_FRAME_PACER_HPP

#include "rust_types.h"

namespace chip8_runner {

class FramePacer {
  public:
    static constexpr u32 PERIOD_US = 16667;

    FramePacer(void) : accumulator_us_(0), dirty_(false) {}

    void markDirty(void) { dirty_ = true; }

    bool advance(u32 elapsed_us) {
      accumulator_us_ += elapsed_us;
      if(accumulator_us_ < PERIOD_US) return false;
      accumulator_us_ %= PERIOD_US;
      if(!dirty_) return false;
      dirty_ = false;
      return true;
    }

  private:
    u32 accumulator_us_;
    bool dirty_;
};

} // namespace chip8_runner

#endif
