#ifndef MK61_READ_BENCHMARK_HPP
#define MK61_READ_BENCHMARK_HPP

#include "rust_types.h"

namespace read_benchmark {

// Небольшой чистый аккумулятор для HIL-замеров. CRC первого прохода становится
// эталоном; несовпадение следующих проходов превращает тест скорости в ошибку
// данных, а не маскируется красивым средним временем.
struct Summary {
  u64 total_us;
  u32 minimum_us;
  u32 maximum_us;
  u32 reference_crc;
  u8 samples;
  bool crc_consistent;

  constexpr Summary(void)
      : total_us(0), minimum_us(0), maximum_us(0), reference_crc(0),
        samples(0), crc_consistent(true) {}

  bool add(u32 elapsed_us, u32 crc) {
    if(samples == 0xFF) return false;
    if(samples == 0) {
      minimum_us = elapsed_us;
      maximum_us = elapsed_us;
      reference_crc = crc;
    } else {
      if(elapsed_us < minimum_us) minimum_us = elapsed_us;
      if(elapsed_us > maximum_us) maximum_us = elapsed_us;
      if(crc != reference_crc) crc_consistent = false;
    }
    total_us += elapsed_us;
    samples++;
    return crc_consistent;
  }

  u32 average_us(void) const {
    return samples == 0 ? 0 : (u32) (total_us / samples);
  }

  u32 bytes_per_second(u32 bytes_per_sample) const {
    const u32 average = average_us();
    if(average == 0) return 0;
    const u64 rate = (u64) bytes_per_sample * 1000000ULL / average;
    return rate > 0xFFFFFFFFULL ? 0xFFFFFFFFUL : (u32) rate;
  }
};

} // namespace read_benchmark

#endif
