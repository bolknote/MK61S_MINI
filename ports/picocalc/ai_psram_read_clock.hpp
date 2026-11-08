#ifndef MK61_AI_PSRAM_READ_CLOCK_HPP
#define MK61_AI_PSRAM_READ_CLOCK_HPP
#include <cstdint>
namespace picocalc::ai_psram_read_clock {
// Only the qualified270MHz AI profile changes. Keep SPI and writes at their
// normal divider. Six PIO cycles per SCK, so this bounds QPI reads to25MHz.
// The16-byte autonomous packet and its FIFO/CE# safety remain unchanged.
constexpr std::uint32_t divider256(std::uint32_t sys,std::uint32_t normal) {
  return sys==270000000 && normal==692 ? 461 : normal;
}
}
#endif
