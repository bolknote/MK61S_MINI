#include "dwt_profiler.hpp"

#if MK61_DWT_PROFILER_SUPPORTED

namespace dwt_profiler {
namespace {

Statistics point_statistics[POINT_COUNT];
bool dwt_available = false;
u32 core_clock_hz = 0;
u32 read_overhead_cycles = 0;

static usize point_index(Point point) {
  const usize index = (usize) point;
  return index < POINT_COUNT ? index : POINT_COUNT;
}

static u32 measure_read_overhead(void) {
  u32 best = 0xFFFFFFFFUL;
  for(u8 sample = 0; sample < 32; sample++) {
    __asm__ __volatile__("" ::: "memory");
    const u32 started_at = DWT->CYCCNT;
    __asm__ __volatile__("" ::: "memory");
    const u32 finished_at = DWT->CYCCNT;
    __asm__ __volatile__("" ::: "memory");
    const u32 elapsed = finished_at - started_at;
    if(elapsed < best) best = elapsed;
  }
  return best == 0xFFFFFFFFUL ? 0 : best;
}

} // namespace

bool collection_active = false;

void initialize(void) {
  collection_active = false;
  reset();

  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  __DSB();
  __ISB();

  const u32 before = DWT->CYCCNT;
  for(u8 index = 0; index < 8; index++) __NOP();
  const u32 after = DWT->CYCCNT;
  dwt_available = after != before;
  core_clock_hz = dwt_available ? SystemCoreClock : 0;
  read_overhead_cycles = dwt_available ? measure_read_overhead() : 0;
}

bool available(void) { return dwt_available; }
bool running(void) { return collection_active; }

bool start(void) {
  if(!dwt_available) return false;
  reset();
  collection_active = true;
  return true;
}

void stop(void) { collection_active = false; }

void reset(void) {
  for(usize index = 0; index < POINT_COUNT; index++) {
    point_statistics[index].reset();
  }
}

u32 clock_hz(void) { return core_clock_hz; }
u32 overhead_cycles(void) { return read_overhead_cycles; }

const char* point_name(Point point) {
  switch(point) {
    case Point::CORE_STEP:          return "core.step";
    case Point::CORE_FETCH:         return "core.fetch";
    case Point::CORE_TICKS_00_26:   return "core.ticks.00-26";
    case Point::CORE_TICKS_27_35:   return "core.ticks.27-35";
    case Point::CORE_TICKS_36_41:   return "core.ticks.36-41";
    case Point::CORE_STEP_FINISH:   return "core.finish";
    case Point::CORE_IK1302:        return "core.ik1302";
    case Point::CORE_IK1303:        return "core.ik1303";
    case Point::CORE_IK1306:        return "core.ik1306";
    case Point::IDLE_MAIN:          return "idle.main";
    case Point::DISPLAY_UPDATE:     return "display.update";
    case Point::USB_SCREEN_SERVICE: return "usb.service";
    case Point::FLASH_READ:         return "flash.read";
    case Point::FLASH_WRITE:        return "flash.write";
    case Point::FLASH_VERIFY:       return "flash.verify";
    case Point::FLASH_ERASE:        return "flash.erase";
    case Point::ZX0_DECODE:         return "zx0.decode";
    case Point::COUNT:              break;
  }
  return "unknown";
}

const Statistics& statistics(Point point) {
  static const Statistics empty;
  const usize index = point_index(point);
  return index < POINT_COUNT ? point_statistics[index] : empty;
}

void record_sample(Point point, u32 elapsed_cycles) {
  if(!collection_active) return;
  const usize index = point_index(point);
  if(index < POINT_COUNT) point_statistics[index].add(elapsed_cycles);
}

} // namespace dwt_profiler

#endif
