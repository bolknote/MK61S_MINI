#ifndef MK61_CHIP8_HPP
#define MK61_CHIP8_HPP

#include "rust_types.h"

namespace chip8 {

static constexpr u16 MEMORY_SIZE = 4096;
static constexpr u16 ROM_ADDRESS = 0x200;
static constexpr u16 MAX_ROM_SIZE = MEMORY_SIZE - ROM_ADDRESS;
static constexpr u8 SCREEN_WIDTH = 64;
static constexpr u8 SCREEN_HEIGHT = 32;
static constexpr u16 FRAME_BYTES =
    (u16) SCREEN_WIDTH * SCREEN_HEIGHT / 8U;
static constexpr u8 STACK_DEPTH = 16;
static constexpr u8 KEY_COUNT = 16;

enum Quirk : u8 {
  QUIRK_SHIFT_USES_VY = 1U << 0,
  QUIRK_LOAD_STORE_INCREMENT_I = 1U << 1,
  QUIRK_JUMP_USES_VX = 1U << 2,
  QUIRK_CLIP_SPRITES = 1U << 3
};

enum class StepResult : u8 {
  OK = 0,
  DRAW,
  WAITING_KEY,
  INVALID_OPCODE,
  MEMORY_ERROR,
  STACK_ERROR
};

struct State {
  u8 memory[MEMORY_SIZE];
  u8 framebuffer[FRAME_BYTES];
  u16 stack[STACK_DEPTH];
  u8 v[16];
  u16 i;
  u16 pc;
  u16 keys;
  u16 key_edges;
  u8 sp;
  u8 delay_timer;
  u8 sound_timer;
  u8 waiting_register;
  u8 quirks;
};

void reset(State& state, u8 quirks = 0);
bool load_rom(State& state, const u8* rom, u16 size, u8 quirks = 0);
void update_keys(State& state, u16 pressed_mask);
StepResult step(State& state, u8 random_byte);
void tick_timers(State& state);

inline bool pixel(const State& state, u8 x, u8 y) {
  if(x >= SCREEN_WIDTH || y >= SCREEN_HEIGHT) return false;
  const u16 offset = (u16) y * (SCREEN_WIDTH / 8U) + x / 8U;
  return (state.framebuffer[offset] & (u8) (0x80U >> (x & 7U))) != 0;
}

} // namespace chip8

#endif
