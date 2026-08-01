#include <Arduino.h>
#include "classic_timer.hpp"
#include "config.h"
#include "stm32f4_platform_resources.hpp"

#if defined(ARDUINO_ARCH_STM32) && defined(HAL_TIM_MODULE_ENABLED) && \
    !defined(HAL_TIM_MODULE_ONLY) && MK61_STM32F4_RESOURCE_MAP_SUPPORTED
  #define MK61_CLASSIC_TIMER_USES_TIM9 1
#else
  #define MK61_CLASSIC_TIMER_USES_TIM9 0
#endif

#if MK61_CLASSIC_TIMER_USES_TIM9
  #include <HardwareTimer.h>
  #include "manual_lifetime.hpp"
#endif

namespace classic_timer {
namespace {

static classic_scheduler::Scheduler scheduler;
static u32 actual_period_us = cfg::CLASSIC_MK61_PERIOD_US;

#if MK61_CLASSIC_TIMER_USES_TIM9

// Карта ресурсов F401/F411: TIM10 обслуживает отсечку звука, TIM11 зарезервирован
// STM32duino под Servo, а PWM буззера занимает TIM2/TIM4/TIM5 в зависимости от
// профиля платы. TIM9 не пересекается ни с одним из этих потребителей.
static manual_lifetime::Storage<HardwareTimer> timer_storage;
static bool timer_constructed = false;
static bool timer_initialized = false;

static HardwareTimer& timer(void) {
  return timer_storage.get();
}

struct InterruptState {
  u32 primask;
};

static InterruptState disable_interrupts(void) {
  const InterruptState state = {__get_PRIMASK()};
  __disable_irq();
  return state;
}

static void restore_interrupts(InterruptState state) {
  __set_PRIMASK(state.primask);
}

static void clear_update_interrupt(void) {
  TIM_HandleTypeDef* handle = timer().getHandle();
  if(handle != NULL) __HAL_TIM_CLEAR_FLAG(handle, TIM_FLAG_UPDATE);
}

static void on_timer_tick(void) {
  scheduler.on_tick();
}

static void configure_period(void) {
  // HardwareTimer::setOverflow(MICROSEC_FORMAT) выбирает первый допустимый
  // 16-битный делитель и на F401 ошибается примерно на 15 мкс за шаг. Для
  // штатных частот BlackPill используем лучшие целочисленные пары PSC/ARR для
  // измеренного рационального периода 15/13 с (ошибка не больше 0,023 мкс).
  const u32 timer_hz = timer().getTimerClkFreq();
  if(timer_hz == 84000000UL) {
    timer().setPrescaleFactor(3109);
    timer().setOverflow(31175, TICK_FORMAT);
  } else if(timer_hz == 96000000UL) {
    timer().setPrescaleFactor(3441);
    timer().setOverflow(32191, TICK_FORMAT);
  } else if(timer_hz == 100000000UL) {
    timer().setPrescaleFactor(1986);
    timer().setOverflow(58099, TICK_FORMAT);
  } else {
    timer().setOverflow(cfg::CLASSIC_MK61_PERIOD_US, MICROSEC_FORMAT);
  }
}

static void stop_timer_locked(void) {
  timer().pause();
  timer().detachInterrupt();
  clear_update_interrupt();
  scheduler.set_active(false);
}

static void start_timer_locked(void) {
  timer().pause();
  timer().detachInterrupt();
  clear_update_interrupt();
  timer().setCount(0);
  scheduler.set_active(true);
  timer().attachInterrupt(on_timer_tick);
  clear_update_interrupt();
  timer().resume();
}

#else

static u32 next_tick_us = 0;

static void poll_fallback(void) {
  if(!scheduler.active()) return;
  const u32 now = micros();
  if((i32) (now - next_tick_us) < 0) return;

  const u32 due = (u32) ((now - next_tick_us) /
                         cfg::CLASSIC_MK61_PERIOD_US) + 1U;
  scheduler.on_ticks(due);
  next_tick_us += due * cfg::CLASSIC_MK61_PERIOD_US;
}

#endif

} // namespace

void construct(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  if(timer_constructed) return;
  timer_storage.construct(MK61_CLASSIC_TIMER_INSTANCE);
  timer_constructed = true;
#endif
}

void initialize(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  if(!timer_constructed) construct();
  const InterruptState irq = disable_interrupts();
  timer().pause();
  timer().detachInterrupt();
  configure_period();
  timer().setCount(0);
  clear_update_interrupt();
  scheduler.set_active(false);
  actual_period_us = timer().getOverflow(MICROSEC_FORMAT);
  timer_initialized = true;
  restore_interrupts(irq);
#else
  scheduler.set_active(false);
  actual_period_us = cfg::CLASSIC_MK61_PERIOD_US;
#endif
}

void synchronize(bool active) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  if(!timer_initialized) return;
  if(scheduler.active() == active) return;
  const InterruptState irq = disable_interrupts();
  if(active) start_timer_locked();
  else stop_timer_locked();
  restore_interrupts(irq);
#else
  if(scheduler.active() != active) {
    scheduler.set_active(active);
    if(active) next_tick_us = micros() + cfg::CLASSIC_MK61_PERIOD_US;
  }
  if(active) poll_fallback();
#endif
}

bool take_step(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  const InterruptState irq = disable_interrupts();
  const bool ready = scheduler.take_step();
  restore_interrupts(irq);
  return ready;
#else
  poll_fallback();
  return scheduler.take_step();
#endif
}

void reset_statistics(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  const InterruptState irq = disable_interrupts();
  scheduler.reset_statistics();
  restore_interrupts(irq);
#else
  scheduler.reset_statistics();
#endif
}

classic_scheduler::Snapshot statistics(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  const InterruptState irq = disable_interrupts();
  const classic_scheduler::Snapshot snapshot = scheduler.snapshot();
  restore_interrupts(irq);
  return snapshot;
#else
  poll_fallback();
  return scheduler.snapshot();
#endif
}

const char* backend_name(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  return "TIM9";
#else
  return "micros";
#endif
}

u32 configured_period_us(void) {
  return actual_period_us;
}

} // namespace classic_timer
