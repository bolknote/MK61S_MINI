#ifndef MK61_AI_PSRAM_READ_CLOCK_HPP
#define MK61_AI_PSRAM_READ_CLOCK_HPP
#include <cstdint>
namespace picocalc::ai_psram_read_clock {
// Only the qualified270MHz AI profile changes. Keep SPI and writes at their
// normal divider. Six PIO cycles per SCK; the default bounds reads to25MHz.
// The16-byte autonomous packet and its FIFO/CE# safety remain unchanged.
constexpr std::uint32_t divider256(std::uint32_t sys,std::uint32_t normal) {
  // Experimental late sampling is paired with33.3MHz only by explicit opt-in.
#if MK61_PICOCALC_AI_PSRAM_LATE_READ
  constexpr std::uint32_t selected=346;
#else
  constexpr std::uint32_t selected=461;
#endif
  return sys==270000000 && normal==692 ? selected : normal;
}
}
#endif
