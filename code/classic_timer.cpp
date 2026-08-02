#include <Arduino.h>
#include "classic_timer.hpp"
#include "config.h"
#include "stm32f4_platform_resources.hpp"
#include "stm32f4_timer_math.hpp"

#if defined(ARDUINO_ARCH_STM32) && defined(HAL_TIM_MODULE_ENABLED) && \
    !defined(HAL_TIM_MODULE_ONLY) && MK61_STM32F4_RESOURCE_MAP_SUPPORTED
  #define MK61_CLASSIC_TIMER_USES_TIM9 1
#else
  #define MK61_CLASSIC_TIMER_USES_TIM9 0
#endif

namespace classic_timer {
namespace {

static classic_scheduler::Scheduler scheduler;
static u32 actual_period_us = cfg::CLASSIC_MK61_PERIOD_US;

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

#if MK61_CLASSIC_TIMER_USES_TIM9

// TIM9 работает свободным 16-битным счётчиком на 10 кГц. SysTick читает его
// раз в миллисекунду, а дробный аккумулятор выдаёт ровно 13 шагов за 15 секунд.
// Так средняя скорость задаётся аппаратной временной базой без тяжёлого
// HardwareTimer и без дополнительного IRQ-вектора.
static volatile u16 previous_counter = 0;
static volatile u32 phase = 0;
static bool timer_initialized = false;

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

static void stop_timer_locked(void) {
  LL_TIM_DisableCounter(MK61_CLASSIC_TIMER_INSTANCE);
  LL_TIM_DisableIT_UPDATE(MK61_CLASSIC_TIMER_INSTANCE);
  LL_TIM_ClearFlag_UPDATE(MK61_CLASSIC_TIMER_INSTANCE);
  scheduler.set_active(false);
  previous_counter = 0;
  phase = 0;
}

static void start_timer_locked(void) {
  LL_TIM_DisableCounter(MK61_CLASSIC_TIMER_INSTANCE);
  LL_TIM_SetCounter(MK61_CLASSIC_TIMER_INSTANCE, 0);
  LL_TIM_ClearFlag_UPDATE(MK61_CLASSIC_TIMER_INSTANCE);
  previous_counter = 0;
  phase = 0;
  scheduler.set_active(true);
  LL_TIM_EnableCounter(MK61_CLASSIC_TIMER_INSTANCE);
}

static void configure_timer(void) {
  __HAL_RCC_TIM9_CLK_ENABLE();

  const u32 timer_hz = stm32f4_platform_resources::apb2_timer_clock_hz();
  u32 prescaler = timer_hz / stm32f4_timer_math::CLASSIC_COUNTER_HZ;
  if(prescaler == 0) prescaler = 1;
  if(prescaler > stm32f4_timer_math::TIMER_FACTOR_LIMIT) {
    prescaler = stm32f4_timer_math::TIMER_FACTOR_LIMIT;
  }

  TIM_TypeDef* const timer = MK61_CLASSIC_TIMER_INSTANCE;
  timer->CR1 = 0;
  timer->CR2 = 0;
  timer->SMCR = 0;
  timer->DIER = 0;
  LL_TIM_SetPrescaler(timer, prescaler - 1UL);
  LL_TIM_SetAutoReload(timer, 0xFFFFUL);
  LL_TIM_SetCounter(timer, 0);
  LL_TIM_GenerateEvent_UPDATE(timer);
  LL_TIM_ClearFlag_UPDATE(timer);

  const u32 counter_hz = timer_hz / prescaler;
  actual_period_us = (u32) (((u64) 1000000UL *
    stm32f4_timer_math::CLASSIC_PERIOD_NUMERATOR +
    stm32f4_timer_math::CLASSIC_PERIOD_DENOMINATOR / 2UL) /
    stm32f4_timer_math::CLASSIC_PERIOD_DENOMINATOR);

  // Все штатные F401/F411-профили дают ровно 10 кГц. При пользовательской
  // частоте тактирования безопаснее перейти на micros(), чем незаметно менять
  // скорость классического режима.
  timer_initialized = counter_hz == stm32f4_timer_math::CLASSIC_COUNTER_HZ;
  if(!timer_initialized) {
    __HAL_RCC_TIM9_CLK_DISABLE();
  }
}

#endif

} // namespace

void construct(void) {}

void initialize(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  const InterruptState irq = disable_interrupts();
  configure_timer();
  scheduler.set_active(false);
  restore_interrupts(irq);
#else
  scheduler.set_active(false);
  actual_period_us = cfg::CLASSIC_MK61_PERIOD_US;
#endif
}

void synchronize(bool active) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  if(!timer_initialized) {
    if(scheduler.active() != active) {
      scheduler.set_active(active);
      if(active) next_tick_us = micros() + cfg::CLASSIC_MK61_PERIOD_US;
    }
    if(active) poll_fallback();
    return;
  }
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
  if(!timer_initialized) {
    poll_fallback();
    return scheduler.take_step();
  }
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
  if(!timer_initialized) poll_fallback();
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
  return timer_initialized ? "TIM9/SysTick" : "micros";
#else
  return "micros";
#endif
}

u32 configured_period_us(void) {
  return actual_period_us;
}

void on_systick_isr(void) {
#if MK61_CLASSIC_TIMER_USES_TIM9
  if(!timer_initialized || !scheduler.active()) return;

  const u16 current = (u16) LL_TIM_GetCounter(MK61_CLASSIC_TIMER_INSTANCE);
  const u16 elapsed = stm32f4_timer_math::elapsed_counter_ticks(
    previous_counter, current);
  previous_counter = current;

  u32 next_phase = phase;
  const u32 due = stm32f4_timer_math::advance_classic_phase(elapsed, next_phase);
  phase = next_phase;
  scheduler.on_ticks(due);
#endif
}

} // namespace classic_timer
