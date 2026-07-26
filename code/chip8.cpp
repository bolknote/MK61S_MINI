#include "chip8.hpp"

#if defined(ARDUINO)
  #include "config.h"
#endif

#if !defined(ARDUINO) || MK61_CHIP8_IS_BUILTIN || \
    defined(MK61_BUILD_CHIP8_MODULE)

#include <string.h>

namespace chip8 {
namespace {

static constexpr u16 FONT_ADDRESS = 0x50;
static constexpr u8 FONT_BYTES[] = {
  0xF0, 0x90, 0x90, 0x90, 0xF0, // 0
  0x20, 0x60, 0x20, 0x20, 0x70, // 1
  0xF0, 0x10, 0xF0, 0x80, 0xF0, // 2
  0xF0, 0x10, 0xF0, 0x10, 0xF0, // 3
  0x90, 0x90, 0xF0, 0x10, 0x10, // 4
  0xF0, 0x80, 0xF0, 0x10, 0xF0, // 5
  0xF0, 0x80, 0xF0, 0x90, 0xF0, // 6
  0xF0, 0x10, 0x20, 0x40, 0x40, // 7
  0xF0, 0x90, 0xF0, 0x90, 0xF0, // 8
  0xF0, 0x90, 0xF0, 0x10, 0xF0, // 9
  0xF0, 0x90, 0xF0, 0x90, 0x90, // A
  0xE0, 0x90, 0xE0, 0x90, 0xE0, // B
  0xF0, 0x80, 0x80, 0x80, 0xF0, // C
  0xE0, 0x90, 0x90, 0x90, 0xE0, // D
  0xF0, 0x80, 0xF0, 0x80, 0xF0, // E
  0xF0, 0x80, 0xF0, 0x80, 0x80  // F
};

static bool memory_range(u16 offset, u16 size) {
  return offset <= MEMORY_SIZE && size <= MEMORY_SIZE - offset;
}

static int first_key(u16 mask) {
  for(u8 key = 0; key < KEY_COUNT; key++) {
    if((mask & ((u16) 1U << key)) != 0) return key;
  }
  return -1;
}

static bool valid_pc(u16 pc) {
  // CHIP-8 addresses byte-addressed memory. Most ROMs keep instructions
  // aligned, but alignment is not part of the VM contract: for example,
  // Br8kout deliberately starts its main routine at 0x29F.
  return pc <= MEMORY_SIZE - 2U;
}

static void set_pixel(State& state, u8 x, u8 y, bool& collision) {
  const u16 offset = (u16) y * (SCREEN_WIDTH / 8U) + x / 8U;
  const u8 mask = (u8) (0x80U >> (x & 7U));
  if((state.framebuffer[offset] & mask) != 0) collision = true;
  state.framebuffer[offset] ^= mask;
}

} // namespace

void reset(State& state, u8 quirks) {
  memset(&state, 0, sizeof(state));
  memcpy(state.memory + FONT_ADDRESS, FONT_BYTES, sizeof(FONT_BYTES));
  state.pc = ROM_ADDRESS;
  state.waiting_register = 0xFF;
  state.quirks = quirks;
}

bool load_rom(State& state, const u8* rom, u16 size, u8 quirks) {
  if(rom == nullptr || size == 0 || size > MAX_ROM_SIZE) return false;
  reset(state, quirks);
  memcpy(state.memory + ROM_ADDRESS, rom, size);
  return true;
}

void update_keys(State& state, u16 pressed_mask) {
  state.key_edges |= (u16) (pressed_mask & ~state.keys);
  state.keys = pressed_mask;
}

StepResult step(State& state, u8 random_byte) {
  if(state.waiting_register < 16) {
    const int key = first_key(state.key_edges);
    if(key < 0) return StepResult::WAITING_KEY;
    state.v[state.waiting_register] = (u8) key;
    state.key_edges &= (u16) ~((u16) 1U << key);
    state.waiting_register = 0xFF;
    return StepResult::OK;
  }
  if(!valid_pc(state.pc)) return StepResult::MEMORY_ERROR;

  const u16 opcode =
      ((u16) state.memory[state.pc] << 8) | state.memory[state.pc + 1U];
  state.pc = (u16) (state.pc + 2U);
  const u8 x = (u8) ((opcode >> 8) & 0x0F);
  const u8 y = (u8) ((opcode >> 4) & 0x0F);
  const u8 n = (u8) (opcode & 0x0F);
  const u8 nn = (u8) opcode;
  const u16 nnn = opcode & 0x0FFF;

  switch(opcode >> 12) {
    case 0x0:
      if(opcode == 0x00E0) {
        memset(state.framebuffer, 0, sizeof(state.framebuffer));
        return StepResult::DRAW;
      }
      if(opcode == 0x00EE) {
        if(state.sp == 0) return StepResult::STACK_ERROR;
        state.pc = state.stack[--state.sp];
        return valid_pc(state.pc) ? StepResult::OK
                                  : StepResult::MEMORY_ERROR;
      }
      // 0NNN (SYS) не используется современными ROM и безопасно игнорируется.
      return StepResult::OK;

    case 0x1:
      if(!valid_pc(nnn)) return StepResult::MEMORY_ERROR;
      state.pc = nnn;
      return StepResult::OK;

    case 0x2:
      if(state.sp >= STACK_DEPTH || !valid_pc(nnn)) {
        return state.sp >= STACK_DEPTH ? StepResult::STACK_ERROR
                                       : StepResult::MEMORY_ERROR;
      }
      state.stack[state.sp++] = state.pc;
      state.pc = nnn;
      return StepResult::OK;

    case 0x3:
      if(state.v[x] == nn) state.pc = (u16) (state.pc + 2U);
      break;
    case 0x4:
      if(state.v[x] != nn) state.pc = (u16) (state.pc + 2U);
      break;
    case 0x5:
      if(n != 0) return StepResult::INVALID_OPCODE;
      if(state.v[x] == state.v[y]) state.pc = (u16) (state.pc + 2U);
      break;
    case 0x6:
      state.v[x] = nn;
      break;
    case 0x7:
      state.v[x] = (u8) (state.v[x] + nn);
      break;

    case 0x8:
      switch(n) {
        case 0x0: state.v[x] = state.v[y]; break;
        case 0x1: state.v[x] |= state.v[y]; break;
        case 0x2: state.v[x] &= state.v[y]; break;
        case 0x3: state.v[x] ^= state.v[y]; break;
        case 0x4: {
          const u16 sum = (u16) state.v[x] + state.v[y];
          state.v[x] = (u8) sum;
          state.v[0xF] = sum > 0xFFU;
          break;
        }
        case 0x5: {
          const u8 left = state.v[x];
          const u8 right = state.v[y];
          state.v[x] = (u8) (left - right);
          state.v[0xF] = left >= right;
          break;
        }
        case 0x6: {
          const u8 value = (state.quirks & QUIRK_SHIFT_USES_VY)
              ? state.v[y] : state.v[x];
          state.v[x] = (u8) (value >> 1);
          state.v[0xF] = value & 1U;
          break;
        }
        case 0x7: {
          const u8 left = state.v[y];
          const u8 right = state.v[x];
          state.v[x] = (u8) (left - right);
          state.v[0xF] = left >= right;
          break;
        }
        case 0xE: {
          const u8 value = (state.quirks & QUIRK_SHIFT_USES_VY)
              ? state.v[y] : state.v[x];
          state.v[x] = (u8) (value << 1);
          state.v[0xF] = (value >> 7) & 1U;
          break;
        }
        default:
          return StepResult::INVALID_OPCODE;
      }
      break;

    case 0x9:
      if(n != 0) return StepResult::INVALID_OPCODE;
      if(state.v[x] != state.v[y]) state.pc = (u16) (state.pc + 2U);
      break;
    case 0xA:
      state.i = nnn;
      break;
    case 0xB: {
      const u8 base = (state.quirks & QUIRK_JUMP_USES_VX)
          ? state.v[x] : state.v[0];
      const u16 target = (u16) (nnn + base);
      if(!valid_pc(target)) return StepResult::MEMORY_ERROR;
      state.pc = target;
      break;
    }
    case 0xC:
      state.v[x] = random_byte & nn;
      break;
    case 0xD: {
      if(n == 0 || !memory_range(state.i, n)) {
        return n == 0 ? StepResult::INVALID_OPCODE
                      : StepResult::MEMORY_ERROR;
      }
      bool collision = false;
      for(u8 row = 0; row < n; row++) {
        const u8 source = state.memory[state.i + row];
        for(u8 bit = 0; bit < 8; bit++) {
          if((source & (u8) (0x80U >> bit)) == 0) continue;
          const u16 raw_x = (u16) state.v[x] + bit;
          const u16 raw_y = (u16) state.v[y] + row;
          if((state.quirks & QUIRK_CLIP_SPRITES) &&
             (raw_x >= SCREEN_WIDTH || raw_y >= SCREEN_HEIGHT)) continue;
          set_pixel(state, (u8) (raw_x % SCREEN_WIDTH),
                    (u8) (raw_y % SCREEN_HEIGHT), collision);
        }
      }
      state.v[0xF] = collision;
      return StepResult::DRAW;
    }
    case 0xE:
      if(nn == 0x9E) {
        if(state.v[x] < KEY_COUNT &&
           (state.keys & ((u16) 1U << state.v[x])) != 0) {
          state.pc = (u16) (state.pc + 2U);
        }
      } else if(nn == 0xA1) {
        if(state.v[x] >= KEY_COUNT ||
           (state.keys & ((u16) 1U << state.v[x])) == 0) {
          state.pc = (u16) (state.pc + 2U);
        }
      } else {
        return StepResult::INVALID_OPCODE;
      }
      break;

    case 0xF:
      switch(nn) {
        case 0x07:
          state.v[x] = state.delay_timer;
          break;
        case 0x0A: {
          // C1 ждёт новое нажатие после FX0A. Накопленные ранее фронты и
          // уже удерживаемая клавиша не должны немедленно завершить ожидание.
          state.key_edges = 0;
          state.waiting_register = x;
          return StepResult::WAITING_KEY;
        }
        case 0x15:
          state.delay_timer = state.v[x];
          break;
        case 0x18:
          state.sound_timer = state.v[x];
          break;
        case 0x1E:
          state.i = (u16) (state.i + state.v[x]);
          if(state.i >= MEMORY_SIZE) return StepResult::MEMORY_ERROR;
          break;
        case 0x29:
          state.i = (u16) (FONT_ADDRESS + (state.v[x] & 0x0F) * 5U);
          break;
        case 0x33:
          if(!memory_range(state.i, 3)) return StepResult::MEMORY_ERROR;
          state.memory[state.i] = (u8) (state.v[x] / 100U);
          state.memory[state.i + 1U] = (u8) ((state.v[x] / 10U) % 10U);
          state.memory[state.i + 2U] = (u8) (state.v[x] % 10U);
          break;
        case 0x55: {
          const u16 count = (u16) x + 1U;
          if(!memory_range(state.i, count)) return StepResult::MEMORY_ERROR;
          memcpy(state.memory + state.i, state.v, count);
          if(state.quirks & QUIRK_LOAD_STORE_INCREMENT_I) {
            state.i = (u16) (state.i + count);
          }
          break;
        }
        case 0x65: {
          const u16 count = (u16) x + 1U;
          if(!memory_range(state.i, count)) return StepResult::MEMORY_ERROR;
          memcpy(state.v, state.memory + state.i, count);
          if(state.quirks & QUIRK_LOAD_STORE_INCREMENT_I) {
            state.i = (u16) (state.i + count);
          }
          break;
        }
        default:
          return StepResult::INVALID_OPCODE;
      }
      break;

    default:
      return StepResult::INVALID_OPCODE;
  }

  return valid_pc(state.pc) ? StepResult::OK : StepResult::MEMORY_ERROR;
}

void tick_timers(State& state) {
  if(state.delay_timer != 0) state.delay_timer--;
  if(state.sound_timer != 0) state.sound_timer--;
}

} // namespace chip8

#endif
