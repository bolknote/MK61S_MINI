/* Physical startup check: the host recognizes the complete bitmap. A dirty
 * .data or .bss produces a different image, even if main's result is ignored. */
#include "mk61_app.h"

static unsigned initialized = 40;
static unsigned launches;
static uint8_t frame[192 * 64 / 8];

#ifdef MK61_HIL_RELOCATION_CHECK
extern uint8_t __module_image_start[], __module_memory_end[];
static unsigned add(unsigned value) { return initialized + value; }
static unsigned* volatile data_pointer = &initialized;
static unsigned (*volatile function_pointer)(unsigned) = add;
static struct __attribute__((packed)) {
  uint8_t marker;
  uint8_t* pointer;
} volatile packed_pointer = {0x55, frame};
static uint8_t* volatile one_past_end = frame + sizeof(frame);
static volatile uint32_t address_like_integer = 0x20000008;

static unsigned relocations_valid(void) {
  uintptr_t pc;
  __asm__ volatile("mov %0, pc" : "=r" (pc));
  return (uintptr_t) __module_image_start > 0x20000000 &&
      pc >= (uintptr_t) __module_image_start && pc < (uintptr_t) __module_memory_end &&
      data_pointer == &initialized && *data_pointer == 40 &&
      function_pointer == add && function_pointer(2) == 42 &&
      packed_pointer.marker == 0x55 && packed_pointer.pointer == frame &&
      one_past_end == frame + sizeof(frame) && address_like_integer == 0x20000008;
}
#endif

int main(void) {
  unsigned ok = initialized == 40 && launches == 0;
  for(unsigned i = 0; i < sizeof(frame); ++i)
    if(frame[i] != 0) ok = 0;
#ifdef MK61_HIL_RELOCATION_CHECK
  if(!relocations_valid()) ok = 0;
#endif
  initialized += 2;
  ++launches;
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
      MK61_APP_CAP_TIME | MK61_APP_CAP_GRAPHICS | MK61_APP_CAP_KEYBOARD)) return 2;
  if(!mk61_api->graphics_begin()) return 3;
  for(unsigned i = 0; i < sizeof(frame); ++i)
    frame[i] = ok ? (uint8_t) ((i * 17U + i / 16U) ^ 0xA5U) : 0xFF;
#ifdef MK61_HIL_RELOCATION_CHECK
  // Report the relocated linker symbol in the frame; the host independently
  // derives the expected allocation from the installed container's header.
  if(ok) for(unsigned i = 0; i < 4; ++i)
    frame[i] = (uint8_t) ((uintptr_t) __module_image_start >> (8 * i));
#endif
  if(!mk61_api->graphics_present(frame, sizeof(frame))) {
    mk61_api->graphics_end();
    return 4;
  }
  while(mk61_api->key_poll() != MK61_APP_KEY_ESC) mk61_api->delay_ms(10);
  mk61_api->graphics_end();
  return ok ? 0 : 1;
}
