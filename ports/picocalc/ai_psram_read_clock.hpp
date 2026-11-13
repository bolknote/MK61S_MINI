#ifndef MK61_AI_PSRAM_READ_CLOCK_HPP
#define MK61_AI_PSRAM_READ_CLOCK_HPP
#include <cstdint>
namespace picocalc::ai_psram_read_clock {
constexpr std::uint32_t burst_dividers[]={461,419,384,346};
constexpr std::uint32_t control_burst_divider=burst_dividers[0];
constexpr std::uint32_t default_burst_divider=burst_dividers[3];
constexpr bool sweep_divider(std::uint32_t div) {
  for(auto allowed:burst_dividers) if(div==allowed) return true;
  return false;
}
constexpr bool late_burst_sample(std::uint32_t div) {
  return div!=control_burst_divider && sweep_divider(div);
}
constexpr bool ai_profile(std::uint32_t sys,std::uint32_t normal) {
  return sys==270000000 && normal==692;
}
// The long-packet reader uses default_burst_divider (33.3 MHz at 270 MHz).
// Keep the short reader at 25 MHz in that profile for overflow recovery.
constexpr std::uint32_t divider256(std::uint32_t sys,std::uint32_t normal) {
  // Preserve the opt-in 16-byte late-sampling experiment.
#if MK61_PICOCALC_AI_PSRAM_LATE_READ
  constexpr std::uint32_t selected=346;
#else
  constexpr std::uint32_t selected=control_burst_divider;
#endif
  return ai_profile(sys,normal) ? selected : normal;
}
}
#endif
