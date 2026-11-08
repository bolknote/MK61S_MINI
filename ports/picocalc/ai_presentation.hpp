#ifndef MK61_PICOCALC_AI_PRESENTATION_HPP
#define MK61_PICOCALC_AI_PRESENTATION_HPP
#include <cstdint>
namespace picocalc::ai {
// Token completion is not a request to repaint the entire 320x320 surface.
// Keys invalidate this cadence; phase changes and the final answer bypass it.
class PresentationCadence {
public:
  bool due(std::uint32_t now, std::uint32_t phase,
           std::uint32_t interval_ms = 2000) const {
    return !valid_ || phase != phase_ || std::uint32_t(now - drawn_) >= interval_ms;
  }
  void presented(std::uint32_t now, std::uint32_t phase) {
    drawn_ = now; phase_ = phase; valid_ = true;
  }
  void invalidate() { valid_ = false; }
private:
  std::uint32_t drawn_ = 0, phase_ = 0;
  bool valid_ = false;
};
// Color rectangles are submitted directly to Panel. The final DMA is drained
// by suspend_frames; asking service_pump to submit another frame would wait
// for an event that does not need to happen.
class PresentationGate {
public:
  void color_presented() { color_ = true; }
  void color_ended() { color_ = false; valid_ = false; }
  bool needs_wait(std::uint32_t revision) const {
    return !color_ && (!valid_ || revision != revision_);
  }
  void frozen(std::uint32_t revision) { revision_ = revision; valid_ = true; }
private:
  std::uint32_t revision_ = 0;
  bool color_ = false, valid_ = false;
};
}
#endif
