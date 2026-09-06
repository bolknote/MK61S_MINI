#include "mk61_app.h"
static uint32_t data = 7;
static uint32_t bss[4];
static uint32_t increment(uint32_t value) { return value + data; }
static uint32_t* volatile pointer = &data;
static uint32_t (*volatile function)(uint32_t) = increment;
static struct __attribute__((packed)) { uint8_t pad; uint32_t* pointer; } volatile unaligned = {0x55, bss};
static uint32_t* volatile end = bss + 4;
static volatile uint32_t integer = 0x20000008;
int main(void) {
  if(pointer != &data || function != increment || unaligned.pointer != bss || end != bss + 4) return 10;
  if(integer != 0x20000008 || unaligned.pad != 0x55 || bss[0] != 0 || data != 7) return 11;
  *pointer = 9;
  bss[0] = function(4);
  return bss[0] == 13 ? 0 : 12;
}
