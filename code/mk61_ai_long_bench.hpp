#ifndef MK61_AI_LONG_BENCH_HPP
#define MK61_AI_LONG_BENCH_HPP
#include <cstdint>
namespace mk61ai::long_bench {
constexpr unsigned contexts[]={64,128,256};
constexpr unsigned cases=3,decode=2,reference_bytes=20+cases*32;
constexpr std::uint32_t magic=0x31474e4c;
constexpr const char *prompt="Задача: вычисли выражение в регистрах. Проверь результат и заверши программу.";
inline std::uint16_t input(const std::uint16_t *ids,unsigned count,unsigned position) {
  return ids[position?1+(position-1)%(count-1):0];
}
inline std::uint32_t word(const std::uint8_t *data,unsigned offset) {
  return std::uint32_t(data[offset]) | std::uint32_t(data[offset+1])<<8 |
      std::uint32_t(data[offset+2])<<16 | std::uint32_t(data[offset+3])<<24;
}
inline void put(std::uint8_t *data,unsigned offset,std::uint32_t value) {
  for(unsigned i=0;i<4;++i) data[offset+i]=std::uint8_t(value>>(8*i));
}
inline std::uint32_t hash(std::uint32_t value,const std::uint8_t *data,unsigned bytes) {
  for(unsigned i=0;i<bytes;++i) value=(value^data[i])*16777619U;
  return value;
}
}
#endif
