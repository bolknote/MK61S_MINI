#include "independent_watchdog.hpp"

#include "crash_dump.hpp"

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>
#endif

namespace independent_watchdog {
namespace {

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED

static constexpr u32 RETAINED_MAGIC = 0x57443631UL; // "16DW" / watchdog v1.
static constexpr u32 KEY_START = 0x0000CCCCUL;
static constexpr u32 KEY_WRITE = 0x00005555UL;
static constexpr u32 KEY_RELOAD = 0x0000AAAAUL;
static constexpr u32 PRESCALER_REGISTER_VALUE = 6;
static constexpr u32 UPDATE_FLAGS = IWDG_SR_PVU | IWDG_SR_RVU;

extern "C" {
__attribute__((used, aligned(8), section(".noinit.mk61_watchdog")))
volatile Breadcrumb mk61_watchdog_breadcrumb;
}

static watchdog_gate::Gate gate;
static Breadcrumb previous_breadcrumb;
static bool previous_valid;
static bool watchdog_reset;
static bool hardware_running;

static bool breadcrumb_valid(const volatile Breadcrumb& value) {
  return value.magic == RETAINED_MAGIC &&
         value.inverse_magic == ~RETAINED_MAGIC &&
         value.state >= RETAINED_RUNNING &&
         value.state <= RETAINED_HANG_TEST;
}

static void copy_breadcrumb(Breadcrumb& output,
                            const volatile Breadcrumb& input) {
  const volatile u32* source =
      reinterpret_cast<const volatile u32*>(&input);
  u32* destination = reinterpret_cast<u32*>(&output);
  for(usize index = 0; index < sizeof(output) / sizeof(u32); index++) {
    destination[index] = source[index];
  }
}

static void publish_breadcrumb(u32 state) {
  const watchdog_gate::Snapshot snapshot = gate.snapshot();
  // A reset between any two payload stores leaves magic cleared. Readers
  // therefore reject a torn snapshot instead of combining two generations.
  mk61_watchdog_breadcrumb.magic = 0;
  __DMB();
  mk61_watchdog_breadcrumb.state = state;
  mk61_watchdog_breadcrumb.epochs = snapshot.epochs;
  mk61_watchdog_breadcrumb.reloads = snapshot.reloads;
  mk61_watchdog_breadcrumb.last_epoch_ms = snapshot.last_epoch_ms;
  mk61_watchdog_breadcrumb.last_reload_ms = snapshot.last_reload_ms;
  mk61_watchdog_breadcrumb.maximum_reload_gap_ms =
      snapshot.maximum_reload_gap_ms;
  __DMB();
  mk61_watchdog_breadcrumb.inverse_magic = ~RETAINED_MAGIC;
  __DMB();
  mk61_watchdog_breadcrumb.magic = RETAINED_MAGIC;
  __DMB();
}

static bool start_hardware(void) {
  // Последовательность HAL_IWDG_Init без handle и глобального конструктора.
  // После KEY_START IWDG уже нельзя остановить до reset, поэтому вызов
  // разрешён только в конце setup().
  IWDG->KR = KEY_START;
  IWDG->KR = KEY_WRITE;
  IWDG->PR = PRESCALER_REGISTER_VALUE;
  IWDG->RLR = RELOAD;

  const u32 started_at = millis();
  while((IWDG->SR & UPDATE_FLAGS) != 0) {
    if((u32) (millis() - started_at) > 100U) return false;
  }
  IWDG->KR = KEY_RELOAD;
  return true;
}

#else

static watchdog_gate::Gate gate;

#endif

} // namespace

bool initialize(u32 now_ms) {
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  watchdog_reset =
      (crash_dump::boot_reset_flags() & RCC_CSR_IWDGRSTF) != 0;
  previous_valid = breadcrumb_valid(mk61_watchdog_breadcrumb);
  if(previous_valid) copy_breadcrumb(
      previous_breadcrumb, mk61_watchdog_breadcrumb);
  else previous_breadcrumb = {};

  const u32 generation = previous_valid
      ? previous_breadcrumb.generation + 1U : 1U;
  mk61_watchdog_breadcrumb.magic = 0;
  __DMB();
  mk61_watchdog_breadcrumb.inverse_magic = ~RETAINED_MAGIC;
  mk61_watchdog_breadcrumb.generation = generation;

  if(!start_hardware()) return false;
  gate.start(now_ms);
  hardware_running = true;
  publish_breadcrumb(RETAINED_RUNNING);
  return true;
#else
  (void) now_ms;
  return false;
#endif
}

void foreground_epoch(u32 now_ms) {
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  if(!hardware_running) return;
  gate.note_epoch(now_ms);
  if(!gate.take_reload(now_ms)) return;
  IWDG->KR = KEY_RELOAD;
  publish_breadcrumb(RETAINED_RUNNING);
#else
  (void) now_ms;
#endif
}

bool running(void) {
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
  return hardware_running;
#else
  return false;
#endif
}

Snapshot statistics(void) {
  const Snapshot snapshot = {
    gate.snapshot(),
#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED
    watchdog_reset, previous_valid,
    hardware_running ? mk61_watchdog_breadcrumb.generation : 0,
    previous_breadcrumb
#else
    false, false, 0, {}
#endif
  };
  return snapshot;
}

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED && MK61_ENABLE_WATCHDOG_TEST
void inhibit_for_test(void) {
  gate.inhibit();
  publish_breadcrumb(RETAINED_INHIBITED);
}

[[noreturn]] void hang_for_test(void) {
  gate.inhibit();
  publish_breadcrumb(RETAINED_HANG_TEST);
  __enable_irq();
  while(true) __asm__ volatile("" ::: "memory");
}
#endif

} // namespace independent_watchdog
