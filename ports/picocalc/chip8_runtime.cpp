#include "chip8.hpp"
#include "canvas.hpp"
#include "cross_hal.h"
#include "input.hpp"
#include "m61_platform.hpp"
#include "m61_text.hpp"
#include "script.hpp"
#include "services.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
namespace picocalc {
u8 Services::run_chip8(const char *path) {
  if (!pump_ || running_ || files::usb_active())
    return 2;
  auto *vm = new (std::nothrow) chip8::State;
  if (!vm) {
    message("CHIP-8: not enough RAM", ServicePage::BROWSER);
    return 3;
  }
  chip8::reset(*vm);
  unsigned size = 0;
  if (!files::read(path, vm->memory + chip8::ROM_ADDRESS, chip8::MAX_ROM_SIZE,
                   size) ||
      !size) {
    delete vm;
    message("CHIP-8: invalid ROM (1..3584 bytes)", ServicePage::BROWSER);
    return 2;
  }
  std::snprintf(path_, sizeof(path_), "%s", path);
  page_ = ServicePage::CONSOLE;
  running_ = true;
  runtime_ = "CHIP8";
  runtime_graphics_ = true;
  std::snprintf(status_, sizeof(status_),
                "CHIP-8: Esc exit, F3 pause; 1234/QWER/ASDF/ZXCV");
  bool paused = false, dirty = true, sounding = false;
  u8 result = 0;
  u32 tick_at = millis(), step_at = tick_at, frame_at = 0, random = 0x42A61;
  // Fixed-point instruction budget, bounded after every foreground pump.
  u32 credit = 0,timer_credit=0;
  while (running_) {
    u8 key = 0;
    if (pump_(pump_context_, key)) {
      if (key == 0x1B || key == 0xB1)
        break;
      if (key == 0x83) {
        paused = !paused;
        credit = 0;
      }
    }
    const u32 now = millis();
    chip8::update_keys(*vm, controls::chip8_keys(now));
    const u32 elapsed = now - step_at;
    step_at = now;
    credit += elapsed > 35 ? 24500 : elapsed * 700;
    if (paused) {
      credit = 0;
      tick_at = now;
    } else {
      for (unsigned n = 0; credit >= 1000 && n < 24; ++n, credit -= 1000) {
        random = random * 1664525 + 1013904223;
        const auto outcome = chip8::step(*vm, (u8)(random >> 24));
        if (outcome == chip8::StepResult::DRAW)
          dirty = true;
        if (outcome > chip8::StepResult::WAITING_KEY) {
          std::snprintf(status_, sizeof(status_), "CHIP-8 error %u at %03X",
                        (unsigned)outcome, vm->pc);
          result = 2;
          running_ = false;
          break;
        }
      }
      const u32 timer_elapsed=now-tick_at;tick_at=now;
      timer_credit+=(timer_elapsed>100?100:timer_elapsed)*60;
      while(timer_credit>=1000) { chip8::tick_timers(*vm);timer_credit-=1000; }
    }
    const bool sound = !paused && vm->sound_timer != 0;
    if (sound != sounding) {
      script::tone(sound ? 440 : 0, 0);
      sounding = sound;
    }
    if (dirty && (u32)(now - frame_at) >= 16) {
      u8 frame[1536]{};
      for (unsigned y = 0; y < 32; ++y)
        for (unsigned x = 0; x < 64; ++x)
          if (chip8::pixel(*vm, (u8)x, (u8)y))
            for (unsigned dy = 0; dy < 2; ++dy)
              for (unsigned dx = 0; dx < 2; ++dx) {
                const unsigned xx = 32 + x * 2 + dx, yy = y * 2 + dy;
                frame[(yy / 8) * 192 + xx] |= (u8)(1U << (yy % 8));
              }
      script::show_frame(frame);
      canvas::clear();
      // A CHIP-8 pixel is a uniform 5x5 block. This is the VM's own pixel
      // geometry, not a resampled 192x64 display image.
      for(unsigned y=0;y<32;++y) for(unsigned x=0;x<64;++x)
        if(chip8::pixel(*vm,(u8)x,(u8)y)) canvas::rect(canvas::frame(),x*5,80+y*5,5,5,true);
      script::show_native_frame(canvas::frame(),false);
      frame_at = now;
      dirty = false;
    }
  }
  std::printf("CHIP8_RESULT=%u PC=%03X ROM=%u\n", result, vm->pc, size);
  delete vm;
  script::tone(0, 0);
  running_ = false;
  runtime_ = "NONE";
  runtime_graphics_ = false;
  if (result)
    message(status_,
            m61_text::active() ? ServicePage::CLOSED : ServicePage::BROWSER);
  else {
    page_ = m61_text::active() ? ServicePage::CLOSED : ServicePage::BROWSER;
    if (page_ == ServicePage::BROWSER)
      refresh();
  }
  return result;
}
} // namespace picocalc
