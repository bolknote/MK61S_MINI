#include "read_benchmark.hpp"

#include <cassert>

int main(void) {
  read_benchmark::Summary summary;
  assert(summary.samples == 0);
  assert(summary.average_us() == 0);
  assert(summary.bytes_per_second(512) == 0);

  assert(summary.add(100, 0x12345678UL));
  assert(summary.add(300, 0x12345678UL));
  assert(summary.add(200, 0x12345678UL));
  assert(summary.samples == 3);
  assert(summary.minimum_us == 100);
  assert(summary.maximum_us == 300);
  assert(summary.average_us() == 200);
  assert(summary.bytes_per_second(1000) == 5000000UL);

  assert(!summary.add(250, 0x87654321UL));
  assert(!summary.crc_consistent);
  return 0;
}
