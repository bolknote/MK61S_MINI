#include "experimental/compute_gap_probe.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
static uint32_t now;
uint32_t micros() {return now;}
int main() {
  using namespace compute_gap_probe;
  assert(service(0xC001, 0) == 0x47415031);
  service(0xC002, 0);
  now = UINT32_MAX - 5; row(0);
  now = 3; row(0);
  assert(service(0xC004, 1) == 9 && service(0xC004, 2) == 9);
  assert(service(0xC005, 1) == 1 && service(0xC005, 2) == 1);
  service(0xC003, 0); now = 10000; row(0);
  assert(service(0xC004, 2) == 9 && service(0xC005, 2) == 1);
  service(0xC002, 0);
  for(unsigned i = 0; i < 8; ++i) {
    now = 0; note(Service(i)); now = 123; note(Service(i));
    assert(service(0xC004, i) == 123 && service(0xC005, i) == 1);
  }
  assert(service(0xC004, 8) == 0 && service(0xC005, 8) == 0);
  std::puts("Wall-clock keyboard/USB probe: actual collector, wrap, zero timestamp, reset, stop and bounds PASS");
}
