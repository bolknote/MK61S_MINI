#include "compute_gap_probe.hpp"
#include <Arduino.h>
namespace compute_gap_probe {
namespace {
struct Gap {uint32_t last, maximum, samples; bool seen;};
Gap gaps[8]{};
bool collecting;
void at(Service service, uint32_t now) {
  auto& gap = gaps[unsigned(service)];
  if(gap.seen) {
    const uint32_t elapsed = now - gap.last;
    if(elapsed > gap.maximum) gap.maximum = elapsed;
    ++gap.samples;
  }
  gap.last = now;
  gap.seen = true;
}
}
void note(Service service) {if(collecting) at(service, micros());}
void row(uint8_t index) {
  if(!collecting || index >= 5) return;
  const uint32_t now = micros();
  at(Service::KEYBOARD_SAMPLE, now);
  at(Service(unsigned(Service::KEYBOARD_ROW0) + index), now);
}
uint32_t service(uint32_t operation, uint32_t index) {
  switch(operation) {
    case 0xC001: return 0x47415031;
    case 0xC002:
      for(auto& gap : gaps) gap = {};
      collecting = true; return 1;
    case 0xC003: collecting = false; return 1;
    case 0xC004: return index < 8 ? gaps[index].maximum : 0;
    case 0xC005: return index < 8 ? gaps[index].samples : 0;
    default: return 0;
  }
}
}
