#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../code/chip8.hpp"
#include "../code/chip8_frame_pacer.hpp"

namespace {

using chip8::State;
using chip8::StepResult;

static void opcode(State& state, u16 value) {
  state.memory[chip8::ROM_ADDRESS] = (u8) (value >> 8);
  state.memory[chip8::ROM_ADDRESS + 1] = (u8) value;
  state.pc = chip8::ROM_ADDRESS;
}

static void test_reset_and_rom(void) {
  State state;
  memset(&state, 0xA5, sizeof(state));
  chip8::reset(state);
  assert(state.pc == chip8::ROM_ADDRESS);
  assert(state.waiting_register == 0xFF);
  assert(state.memory[0x50] == 0xF0);
  assert(state.memory[0x50 + 79] == 0x80);

  const u8 rom[] = {0x60, 0x2A, 0x61, 0x03};
  assert(chip8::load_rom(state, rom, sizeof(rom)));
  assert(memcmp(state.memory + chip8::ROM_ADDRESS, rom, sizeof(rom)) == 0);
  assert(!chip8::load_rom(state, nullptr, sizeof(rom)));
  assert(!chip8::load_rom(state, rom, 0));

  static u8 maximum[chip8::MAX_ROM_SIZE];
  static u8 too_large[chip8::MAX_ROM_SIZE + 1];
  assert(chip8::load_rom(state, maximum, sizeof(maximum)));
  assert(!chip8::load_rom(state, too_large, sizeof(too_large)));
}

static void test_arithmetic_and_skips(void) {
  State state;
  chip8::reset(state);

  opcode(state, 0x60FE);
  assert(chip8::step(state, 0) == StepResult::OK && state.v[0] == 0xFE);
  opcode(state, 0x7003);
  assert(chip8::step(state, 0) == StepResult::OK && state.v[0] == 1);

  state.v[1] = 250;
  state.v[2] = 10;
  opcode(state, 0x8124);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[1] == 4 && state.v[0xF] == 1);

  state.v[1] = 3;
  state.v[2] = 5;
  opcode(state, 0x8125);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[1] == 254 && state.v[0xF] == 0);
  state.v[1] = 3;
  state.v[2] = 5;
  opcode(state, 0x8127);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[1] == 2 && state.v[0xF] == 1);

  state.v[3] = 0x55;
  opcode(state, 0x3355);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == chip8::ROM_ADDRESS + 4);
  opcode(state, 0x4355);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == chip8::ROM_ADDRESS + 2);

  state.v[4] = 9;
  state.v[5] = 9;
  opcode(state, 0x5450);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == chip8::ROM_ADDRESS + 4);
  opcode(state, 0x9450);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == chip8::ROM_ADDRESS + 2);

  opcode(state, 0x5121);
  assert(chip8::step(state, 0) == StepResult::INVALID_OPCODE);
  opcode(state, 0x9121);
  assert(chip8::step(state, 0) == StepResult::INVALID_OPCODE);
}

static void test_control_flow_and_stack(void) {
  State state;
  chip8::reset(state);

  opcode(state, 0x1204);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == 0x204);

  opcode(state, 0x2300);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.sp == 1 && state.stack[0] == 0x202 && state.pc == 0x300);
  state.memory[0x300] = 0x00;
  state.memory[0x301] = 0xEE;
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.sp == 0 && state.pc == 0x202);

  opcode(state, 0x00EE);
  assert(chip8::step(state, 0) == StepResult::STACK_ERROR);

  opcode(state, 0x2200);
  for(u8 depth = 0; depth < chip8::STACK_DEPTH; depth++) {
    assert(chip8::step(state, 0) == StepResult::OK);
  }
  assert(chip8::step(state, 0) == StepResult::STACK_ERROR);

  chip8::reset(state);
  state.v[0] = 1;
  state.v[1] = 3;
  opcode(state, 0xB123);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == 0x124);
  chip8::reset(state, chip8::QUIRK_JUMP_USES_VX);
  state.v[0] = 1;
  state.v[1] = 3;
  opcode(state, 0xB123);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == 0x126);

  chip8::reset(state);
  opcode(state, 0x1205);
  state.memory[0x205] = 0x60;
  state.memory[0x206] = 0x2A;
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == 0x205);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[0] == 0x2A && state.pc == 0x207);
}

static void test_memory_font_and_quirks(void) {
  State state;
  chip8::reset(state);
  state.v[2] = 0x0A;
  opcode(state, 0xF229);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.i == 0x50 + 10 * 5);

  state.i = 0x300;
  state.v[3] = 234;
  opcode(state, 0xF333);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.memory[0x300] == 2);
  assert(state.memory[0x301] == 3);
  assert(state.memory[0x302] == 4);

  state.i = 0x320;
  state.v[0] = 1;
  state.v[1] = 2;
  state.v[2] = 3;
  opcode(state, 0xF255);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.i == 0x320);
  memset(state.v, 0, sizeof(state.v));
  opcode(state, 0xF265);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[0] == 1 && state.v[1] == 2 && state.v[2] == 3);

  chip8::reset(state, chip8::QUIRK_LOAD_STORE_INCREMENT_I);
  state.i = 0x320;
  opcode(state, 0xF255);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.i == 0x323);

  chip8::reset(state);
  state.v[1] = 8;
  state.v[2] = 3;
  opcode(state, 0x8126);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[1] == 4 && state.v[0xF] == 0);
  chip8::reset(state, chip8::QUIRK_SHIFT_USES_VY);
  state.v[1] = 8;
  state.v[2] = 3;
  opcode(state, 0x8126);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[1] == 1 && state.v[0xF] == 1);

  chip8::reset(state);
  state.i = chip8::MEMORY_SIZE - 1;
  state.v[0] = 2;
  opcode(state, 0xF01E);
  assert(chip8::step(state, 0) == StepResult::MEMORY_ERROR);
}

static void test_draw_collision_and_clear(void) {
  State state;
  chip8::reset(state);
  state.i = 0x300;
  state.memory[state.i] = 0xC0;
  state.v[0] = 63;
  state.v[1] = 31;
  opcode(state, 0xD011);
  assert(chip8::step(state, 0) == StepResult::DRAW);
  assert(chip8::pixel(state, 63, 31));
  assert(chip8::pixel(state, 0, 31));
  assert(state.v[0xF] == 0);

  opcode(state, 0xD011);
  assert(chip8::step(state, 0) == StepResult::DRAW);
  assert(!chip8::pixel(state, 63, 31));
  assert(!chip8::pixel(state, 0, 31));
  assert(state.v[0xF] == 1);

  chip8::reset(state, chip8::QUIRK_CLIP_SPRITES);
  state.i = 0x300;
  state.memory[state.i] = 0xC0;
  state.v[0] = 63;
  state.v[1] = 31;
  opcode(state, 0xD011);
  assert(chip8::step(state, 0) == StepResult::DRAW);
  assert(chip8::pixel(state, 63, 31));
  assert(!chip8::pixel(state, 0, 31));

  opcode(state, 0x00E0);
  assert(chip8::step(state, 0) == StepResult::DRAW);
  for(u16 index = 0; index < chip8::FRAME_BYTES; index++) {
    assert(state.framebuffer[index] == 0);
  }
}

static void test_keys_random_and_timers(void) {
  State state;
  chip8::reset(state);
  state.v[2] = 5;
  chip8::update_keys(state, (u16) 1U << 5);
  opcode(state, 0xE29E);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == chip8::ROM_ADDRESS + 4);
  opcode(state, 0xE2A1);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.pc == chip8::ROM_ADDRESS + 2);

  // Удерживаемая до FX0A клавиша не принимается: нужен новый фронт.
  opcode(state, 0xF10A);
  assert(chip8::step(state, 0) == StepResult::WAITING_KEY);
  assert(state.waiting_register == 1);
  assert(chip8::step(state, 0) == StepResult::WAITING_KEY);
  chip8::update_keys(state, (u16) 1U << 5);
  assert(chip8::step(state, 0) == StepResult::WAITING_KEY);
  chip8::update_keys(state, 0);
  assert(chip8::step(state, 0) == StepResult::WAITING_KEY);
  chip8::update_keys(state, (u16) 1U << 7);
  assert(chip8::step(state, 0) == StepResult::OK);
  assert(state.v[1] == 7 && state.waiting_register == 0xFF);

  opcode(state, 0xC30F);
  assert(chip8::step(state, 0xA5) == StepResult::OK);
  assert(state.v[3] == 5);

  state.delay_timer = 2;
  state.sound_timer = 1;
  chip8::tick_timers(state);
  assert(state.delay_timer == 1 && state.sound_timer == 0);
  chip8::tick_timers(state);
  assert(state.delay_timer == 0 && state.sound_timer == 0);
}

static void test_invalid_and_bounds(void) {
  State state;
  chip8::reset(state);
  opcode(state, 0x8018);
  assert(chip8::step(state, 0) == StepResult::INVALID_OPCODE);
  opcode(state, 0xD010);
  assert(chip8::step(state, 0) == StepResult::INVALID_OPCODE);
  state.pc = chip8::MEMORY_SIZE - 1;
  assert(chip8::step(state, 0) == StepResult::MEMORY_ERROR);
}

static void test_frame_pacer(void) {
  chip8_runner::FramePacer pacer;

  // Несколько операций рисования внутри кадра объединяются.
  pacer.markDirty();
  pacer.markDirty();
  assert(!pacer.advance(chip8_runner::FramePacer::PERIOD_US - 1U));
  assert(pacer.advance(1));

  // Без изменения framebuffer пустой тик не публикуется.
  assert(!pacer.advance(chip8_runner::FramePacer::PERIOD_US));

  // Новое изменение ждёт ближайшую границу кадра.
  pacer.markDirty();
  assert(!pacer.advance(chip8_runner::FramePacer::PERIOD_US / 2U));
  assert(pacer.advance(
      chip8_runner::FramePacer::PERIOD_US -
      chip8_runner::FramePacer::PERIOD_US / 2U));

  // После долгой задержки также публикуется только один итоговый кадр.
  pacer.markDirty();
  assert(pacer.advance(chip8_runner::FramePacer::PERIOD_US * 3U));
  assert(!pacer.advance(0));
}

static u16 read_rom(const char* path, u8 output[chip8::MAX_ROM_SIZE]) {
  FILE* input = fopen(path, "rb");
  assert(input != nullptr);
  assert(fseek(input, 0, SEEK_END) == 0);
  const long size = ftell(input);
  assert(size > 0 && size <= chip8::MAX_ROM_SIZE);
  assert(fseek(input, 0, SEEK_SET) == 0);
  assert(fread(output, 1, (usize) size, input) == (usize) size);
  assert(fclose(input) == 0);
  return (u16) size;
}

static void smoke_rom(const char* path, bool expects_key_wait) {
  static const u8 TEST_KEYS[] = {5, 7, 8, 9, 6};
  u8 rom[chip8::MAX_ROM_SIZE];
  State state;
  assert(chip8::load_rom(state, rom, read_rom(path, rom)));

  u32 draws = 0;
  u32 waits = 0;
  u8 next_key = 0;
  for(u32 iteration = 0; iteration < 100000U; iteration++) {
    if(state.waiting_register < chip8::KEY_COUNT) {
      chip8::update_keys(state, 0);
      chip8::update_keys(
          state, (u16) 1U << TEST_KEYS[next_key++ % sizeof(TEST_KEYS)]);
    } else {
      chip8::update_keys(state, 0);
    }

    const u16 pc = state.pc;
    const u16 current_opcode =
        pc <= chip8::MEMORY_SIZE - 2U
            ? ((u16) state.memory[pc] << 8) | state.memory[pc + 1U]
            : 0;
    const StepResult result =
        chip8::step(state, (u8) (iteration * 73U + 19U));
    if(result == StepResult::DRAW) {
      draws++;
    } else if(result == StepResult::WAITING_KEY) {
      waits++;
    } else if(result != StepResult::OK) {
      fprintf(stderr,
              "CHIP-8 ROM failed: %s pc=%03X opcode=%04X result=%u\n",
              path, (unsigned) pc, (unsigned) current_opcode,
              (unsigned) result);
      assert(false);
    }
    if(iteration % 12U == 0) chip8::tick_timers(state);
  }
  assert(draws != 0);
  assert((waits != 0) == expects_key_wait);
}

static void run_until_key_wait(State& state) {
  for(u32 iteration = 0; iteration < 20000U; iteration++) {
    const StepResult result =
        chip8::step(state, (u8) (iteration * 37U + 11U));
    if(result == StepResult::WAITING_KEY) return;
    assert(result == StepResult::OK || result == StepResult::DRAW);
    if(iteration % 12U == 0) chip8::tick_timers(state);
  }
  assert(!"CHIP-8 ROM did not reach its next input point");
}

static void press_waiting_key(State& state, u8 key) {
  assert(state.waiting_register < chip8::KEY_COUNT);
  chip8::update_keys(state, 0);
  chip8::update_keys(state, (u16) 1U << key);
  assert(chip8::step(state, 0x5A) == StepResult::OK);
  chip8::update_keys(state, 0);
  run_until_key_wait(state);
}

static void echo8_acknowledge_messages(State& state) {
  // ECHO-8 deliberately uses V0 for story pages, V5 for exploration and V6
  // for the final choice. This lets the traversal test distinguish them.
  while(state.waiting_register == 0) press_waiting_key(state, 5);
  assert(state.waiting_register == 5 || state.waiting_register == 6);
}

static void echo8_command(State& state, u8 key) {
  assert(state.waiting_register == 5);
  press_waiting_key(state, key);
  echo8_acknowledge_messages(state);
}

static void echo8_start_game(const char* path, State& state) {
  u8 rom[chip8::MAX_ROM_SIZE];
  assert(chip8::load_rom(state, rom, read_rom(path, rom)));

  run_until_key_wait(state);
  assert(state.waiting_register == 0);  // title
  press_waiting_key(state, 5);
  assert(state.waiting_register == 0);  // introduction
  press_waiting_key(state, 5);
  assert(state.waiting_register == 5);
  assert(state.v[8] == 0 && state.v[9] == 0);
  assert(state.v[0xA] == 0 && state.v[0xB] == 0 && state.v[0xD] == 99);
}

static void test_echo8_complete_route(const char* path) {
  State state;
  echo8_start_game(path, state);

  // Entry body.
  echo8_command(state, 6);  // face east
  echo8_command(state, 5);
  assert(state.v[0xB] == 0x01);
  echo8_command(state, 4);  // face north

  // Mirror 1 in room 2 and body 04 in room 5.
  echo8_command(state, 2);
  echo8_command(state, 2);
  assert(state.v[8] == 2);
  echo8_command(state, 6);
  echo8_command(state, 5);
  assert(state.v[0xA] == 0x01);
  echo8_command(state, 4);
  echo8_command(state, 2);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0x09);

  // Mirror 3, bodies 07, 03 and 08 around the western loop.
  echo8_command(state, 4);
  echo8_command(state, 2);
  assert(state.v[8] == 8 && state.v[9] == 3);
  echo8_command(state, 5);
  assert(state.v[0xA] == 0x05);
  echo8_command(state, 6);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0x49);
  echo8_command(state, 8);
  assert(state.v[8] == 4 && state.v[9] == 0);
  echo8_command(state, 4);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0x4D);
  echo8_command(state, 4);
  echo8_command(state, 2);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0xCD);

  // Eastern archive: body 02, mirror 2 and body 06.
  echo8_command(state, 4);
  echo8_command(state, 2);
  echo8_command(state, 4);
  echo8_command(state, 2);
  echo8_command(state, 6);
  echo8_command(state, 2);
  assert(state.v[8] == 3 && state.v[9] == 1);
  echo8_command(state, 6);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0xCF);
  echo8_command(state, 4);
  echo8_command(state, 2);
  assert(state.v[8] == 7 && state.v[9] == 1);
  echo8_command(state, 5);
  assert(state.v[0xA] == 0x07);
  echo8_command(state, 4);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0xEF);

  // Last body in room 6, then the now-open core.
  echo8_command(state, 4);
  echo8_command(state, 2);
  echo8_command(state, 6);
  echo8_command(state, 2);
  assert(state.v[8] == 6 && state.v[9] == 0);
  echo8_command(state, 6);
  echo8_command(state, 5);
  assert(state.v[0xB] == 0xFF);
  echo8_command(state, 4);
  echo8_command(state, 2);
  assert(state.v[8] == 10);
  echo8_command(state, 2);
  assert(state.v[8] == 11);
  assert(state.waiting_register == 6);

  // Choose ECHO. Stop on the ending page before the automatic new game.
  press_waiting_key(state, 6);
  assert(state.waiting_register == 0);
  assert(state.v[0xC] == 0xE3);
}

static void test_echo8_other_endings_and_limits(const char* path) {
  State state;

  // The unopened core gate reports the lock and does not move the player.
  echo8_start_game(path, state);
  state.v[8] = 10;
  state.v[9] = 0;
  press_waiting_key(state, 5);
  assert(state.waiting_register == 0);
  press_waiting_key(state, 5);
  assert(state.waiting_register == 5 && state.v[8] == 10);
  echo8_command(state, 2);
  assert(state.v[8] == 10 && state.v[0xA] == 0);

  // Enter a prepared core and select ESCAPE.
  state.v[0xA] = 7;
  echo8_command(state, 2);
  assert(state.v[8] == 11 && state.waiting_register == 6);
  press_waiting_key(state, 2);
  assert(state.waiting_register == 0 && state.v[0xC] == 0xE1);

  // SILENCE is independent of the memory fragments.
  echo8_start_game(path, state);
  state.v[8] = 10;
  state.v[9] = 0;
  state.v[0xA] = 7;
  echo8_command(state, 2);
  press_waiting_key(state, 4);
  assert(state.waiting_register == 0 && state.v[0xC] == 0xE2);

  // ECHO remains unavailable without all eight fragments; 8 leaves the menu.
  echo8_start_game(path, state);
  state.v[8] = 10;
  state.v[9] = 0;
  state.v[0xA] = 7;
  echo8_command(state, 2);
  press_waiting_key(state, 6);
  assert(state.waiting_register == 0 && state.v[0xC] == 1);
  press_waiting_key(state, 5);
  assert(state.waiting_register == 6);
  press_waiting_key(state, 8);
  assert(state.waiting_register == 5 && state.v[8] == 11 &&
         state.v[0xC] == 0);
  echo8_command(state, 8);
  assert(state.v[8] == 10);
  echo8_command(state, 2);
  assert(state.v[8] == 11 && state.waiting_register == 6);
  press_waiting_key(state, 8);
  assert(state.waiting_register == 5);

  // Exhausting the last signal unit shows SIGNAL LOST and starts a clean run.
  state.v[0xD] = 1;
  echo8_command(state, 4);
  assert(state.v[8] == 0 && state.v[9] == 0);
  assert(state.v[0xA] == 0 && state.v[0xB] == 0 && state.v[0xD] == 99);
}

} // namespace

int main(int argc, char** argv) {
  test_reset_and_rom();
  test_arithmetic_and_skips();
  test_control_flow_and_stack();
  test_memory_font_and_quirks();
  test_draw_collision_and_clear();
  test_keys_random_and_timers();
  test_invalid_and_bounds();
  test_frame_pacer();
  assert(argc == 1 || argc == 5);
  if(argc == 5) {
    smoke_rom(argv[1], false);
    smoke_rom(argv[2], true);
    smoke_rom(argv[3], false);
    smoke_rom(argv[4], true);
    test_echo8_complete_route(argv[4]);
    test_echo8_other_endings_and_limits(argv[4]);
  }
  printf("chip8_self_test: ok\n");
  return 0;
}
