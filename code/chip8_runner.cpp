#include "config.h"

#if MK61_CHIP8_IS_BUILTIN || defined(MK61_BUILD_CHIP8_MODULE)

#include "chip8_runner.hpp"

#include "Arduino.h"
#include "chip8.hpp"
#include "cross_hal.h"
#include "display.hpp"
#include "entropy_pool.hpp"
#include "keyboard.h"
#include "keyboard_layout.hpp"
#include "language_workspace.hpp"
#include "menu.hpp"
#include "tools.hpp"

#include <string.h>

extern void idle_main_process(void);

namespace chip8_runner {
namespace {

static constexpr u16 DISPLAY_WIDTH = 192;
static constexpr u16 DISPLAY_HEIGHT = 64;
static constexpr usize DISPLAY_BYTES =
    (usize) DISPLAY_WIDTH * DISPLAY_HEIGHT / 8U;
static constexpr u8 SCALE = 2;
static constexpr u8 VIEW_X = (DISPLAY_WIDTH - chip8::SCREEN_WIDTH * SCALE) / 2;
static constexpr u32 CPU_PERIOD_US = 1429;  // примерно 700 инструкций/с
static constexpr u32 TIMER_PERIOD_US = 16667;
static constexpr u8 MAX_STEPS_PER_POLL = 24;
static constexpr u16 BEEP_FREQUENCY_HZ = 800;
static constexpr u16 BEEP_DURATION_MS = 20;
static constexpr u8 BEEP_VOLUME_PERCENT = 20;

struct Workspace {
  chip8::State machine;
  u8 display[DISPLAY_BYTES];
};

static_assert(sizeof(Workspace) <= language_workspace::SIZE,
              "CHIP-8 runtime does not fit the shared language workspace");
static_assert(VIEW_X == 32, "CHIP-8 2x viewport must be horizontally centred");

static void set_display_pixel(u8* bitmap, u16 x, u8 y) {
  const usize offset = (usize) (y / 8U) * DISPLAY_WIDTH + x;
  bitmap[offset] |= (u8) (1U << (y & 7U));
}

static bool render(MK61Display& display, const chip8::State& machine,
                   u8 bitmap[DISPLAY_BYTES]) {
  memset(bitmap, 0, DISPLAY_BYTES);
  for(u8 y = 0; y < chip8::SCREEN_HEIGHT; y++) {
    for(u8 x = 0; x < chip8::SCREEN_WIDTH; x++) {
      if(!chip8::pixel(machine, x, y)) continue;
      const u16 left = (u16) VIEW_X + (u16) x * SCALE;
      const u8 top = (u8) (y * SCALE);
      set_display_pixel(bitmap, left, top);
      set_display_pixel(bitmap, left + 1U, top);
      set_display_pixel(bitmap, left, (u8) (top + 1U));
      set_display_pixel(bitmap, left + 1U, (u8) (top + 1U));
    }
  }
  return display.showFullscreenBitmap(bitmap, DISPLAY_BYTES);
}

static bool pressed(i32 key) {
  return key >= 0 && kbd::is_key_pressed(key);
}

static bool chip_key_pressed(u8 key) {
  const keyboard_layout::Mapping& mapping = keyboard_layout::ACTIVE;
  if(key <= 9 && pressed(mapping.digit[key])) return true;
  switch(key) {
    case 0xA: return pressed(mapping.dot);
    case 0xB: return pressed(mapping.div);
    case 0xC: return pressed(mapping.power);
    case 0xD: return pressed(mapping.cx);
    case 0xE: return pressed(mapping.bx);
    case 0xF: return pressed(mapping.alpha);
  }

  // Одновременные игровые алиасы не заменяют прямую hex-клавиатуру:
  // стрелки дают привычный крест, OK — основное действие.
  if(key == 4 && pressed(mapping.left)) return true;
  if(key == 6 && pressed(mapping.right)) return true;
  if(key == 2 && pressed(mapping.shg_left)) return true;
  if(key == 8 && pressed(mapping.shg_right)) return true;
  return key == 5 && pressed(mapping.ok);
}

static u16 key_mask(void) {
  u16 result = 0;
  for(u8 key = 0; key < chip8::KEY_COUNT; key++) {
    if(chip_key_pressed(key)) result |= (u16) 1U << key;
  }
  return result;
}

static bool service_display_change(MK61Display& display,
                                   u32& display_mode_revision,
                                   const chip8::State& machine,
                                   u8 bitmap[DISPLAY_BYTES]) {
  if(display.displayModeRevision() == display_mode_revision) return true;
  display.endFullscreenBitmap();
  display_mode_revision = display.displayModeRevision();
  if(!display.graphicsMode() || !display.beginFullscreenBitmap()) return false;
  return render(display, machine, bitmap);
}

static bool wait_launch_key_release(MK61Display& display,
                                    u32& display_mode_revision,
                                    const chip8::State& machine,
                                    u8 bitmap[DISPLAY_BYTES]) {
  while(kbd::any_key_pressed()) {
    idle_main_process();
    (void) kbd::scan();
    if(!service_display_change(display, display_mode_revision,
                               machine, bitmap)) return false;
    delay(1);
  }
  kbd::debounce_init();
  kbd::clear_immediate_presses();
  return true;
}

static loadable_module::FileOpenResult run(
    const program_store::Entry& entry, Workspace& workspace) {
  using loadable_module::FileOpenResult;
  MK61Display& display = main_lcd();
  if(!display.graphicsMode()) return FileOpenResult::UNSUPPORTED_DISPLAY;

  chip8::reset(workspace.machine);
  u16 read_len = 0;
  if(!program_store::read_range_id(
         entry.id, 0, workspace.machine.memory + chip8::ROM_ADDRESS,
         entry.data_len, &read_len) ||
     read_len != entry.data_len) {
    return FileOpenResult::IO_ERROR;
  }

  if(!display.beginFullscreenBitmap()) {
    return FileOpenResult::UNSUPPORTED_DISPLAY;
  }
  bool fullscreen = true;
  if(!render(display, workspace.machine, workspace.display)) {
    display.endFullscreenBitmap();
    return FileOpenResult::UNSUPPORTED_DISPLAY;
  }

  u32 display_mode_revision = display.displayModeRevision();
  if(!wait_launch_key_release(display, display_mode_revision,
                              workspace.machine, workspace.display)) {
    display.endFullscreenBitmap();
    return FileOpenResult::UNSUPPORTED_DISPLAY;
  }

  u32 last_us = micros();
  u32 cpu_accumulator = 0;
  u32 timer_accumulator = 0;
  bool paused = false;
  bool previous_run = false;
  FileOpenResult result = FileOpenResult::OK;

  while(true) {
    idle_main_process();
    (void) kbd::scan();
    if(!service_display_change(display, display_mode_revision,
                               workspace.machine, workspace.display)) {
      result = FileOpenResult::UNSUPPORTED_DISPLAY;
      fullscreen = false;
      break;
    }

    const keyboard_layout::Mapping& mapping = keyboard_layout::ACTIVE;
    if(pressed(mapping.esc)) break;
    const bool run_pressed = pressed(mapping.run);
    if(run_pressed && !previous_run) {
      paused = !paused;
      if(paused) sound_stop();
    }
    previous_run = run_pressed;
    chip8::update_keys(workspace.machine, key_mask());

    const u32 now = micros();
    u32 elapsed = (u32) (now - last_us);
    last_us = now;
    if(elapsed > 100000U) elapsed = 100000U;
    if(!paused) {
      cpu_accumulator += elapsed;
      timer_accumulator += elapsed;
    }

    bool dirty = false;
    u8 steps = 0;
    while(!paused && cpu_accumulator >= CPU_PERIOD_US &&
          steps++ < MAX_STEPS_PER_POLL) {
      cpu_accumulator -= CPU_PERIOD_US;
      const u8 random_byte = (u8) entropy_pool::next_u32(
          entropy_pool::Domain::CHIP8);
      const chip8::StepResult step =
          chip8::step(workspace.machine, random_byte);
      if(step == chip8::StepResult::DRAW) {
        dirty = true;
      } else if(step == chip8::StepResult::WAITING_KEY) {
        cpu_accumulator = 0;
        break;
      } else if(step != chip8::StepResult::OK) {
        result = FileOpenResult::RUNTIME_ERROR;
        goto finished;
      }
    }

    while(!paused && timer_accumulator >= TIMER_PERIOD_US) {
      timer_accumulator -= TIMER_PERIOD_US;
      const bool sounding = workspace.machine.sound_timer != 0;
      chip8::tick_timers(workspace.machine);
      if(sounding) {
        sound_scaled(PIN_BUZZER, BEEP_FREQUENCY_HZ, BEEP_DURATION_MS,
                     library_mk61::sound_volume(), BEEP_VOLUME_PERCENT);
      } else {
        sound_stop();
      }
    }

    if(dirty &&
       !render(display, workspace.machine, workspace.display)) {
      result = FileOpenResult::UNSUPPORTED_DISPLAY;
      break;
    }
    delay(1);
  }

finished:
  sound_stop();
  if(fullscreen) display.endFullscreenBitmap();
  kbd::clear_hold_key();
  kbd::clear_immediate_presses();
  return result;
}

} // namespace

loadable_module::FileOpenResult run_entry(
    const program_store::Entry& entry) {
  using loadable_module::FileOpenResult;
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::CHIP8 ||
     entry.data_len == 0 ||
     entry.data_len > program_store::MAX_CHIP8_SIZE) {
    return FileOpenResult::INVALID_FILE;
  }
  language_workspace::Lease lease(language_workspace::Owner::CHIP8,
                                   sizeof(Workspace));
  if(!lease.ok()) return FileOpenResult::BUSY;
  return run(entry, *(Workspace*) lease.data());
}

} // namespace chip8_runner

#endif
