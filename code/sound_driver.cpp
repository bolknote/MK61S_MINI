#include <Arduino.h>
#include "config.h"
#include "runtime_safety.hpp"
#include "sound_driver.hpp"
#include "stm32f4_platform_resources.hpp"

#if defined(ARDUINO_ARCH_STM32) && defined(HAL_TIM_MODULE_ENABLED) && \
    !defined(HAL_TIM_MODULE_ONLY)
  #define MK61_SOUND_DRIVER_STM32 1
#else
  #define MK61_SOUND_DRIVER_STM32 0
#endif

#if MK61_SOUND_DRIVER_STM32 && MK61_STM32F4_RESOURCE_MAP_SUPPORTED
  #define MK61_SOUND_DRIVER_DIRECT 1
  #include "PeripheralPins.h"
  #include "pinmap.h"
  #include "stm32f4_timer_math.hpp"
#else
  #define MK61_SOUND_DRIVER_DIRECT 0
#endif

#if MK61_SOUND_DRIVER_STM32 && !MK61_SOUND_DRIVER_DIRECT
  #include <HardwareTimer.h>
  #include "PeripheralPins.h"
  #include "manual_lifetime.hpp"
  #include "pinmap.h"

  #ifndef MK61_SOUND_CUTOFF_TIMER
    #if defined(TIMER_TONE)
      #define MK61_SOUND_CUTOFF_TIMER TIMER_TONE
    #elif defined(TIM10)
      #define MK61_SOUND_CUTOFF_TIMER TIM10
    #else
      #error "No timer available for sound cutoff. Define MK61_SOUND_CUTOFF_TIMER in config.h."
    #endif
  #endif
#endif

#if MK61_SOUND_DRIVER_DIRECT

namespace {

static constexpr usize SOUND_VOLUME_MAX = 10;
static constexpr u32 SOUND_DUTY_MAX = 128;

static volatile bool pwm_ready = false;
static usize pwm_pin = PIN_BUZZER;
static PinName pwm_pin_name = NC;
static u32 pwm_ll_channel = 0;
static TIM_TypeDef* pwm_timer_instance = NULL;
static volatile bool sound_active = false;
static volatile bool stop_cleanup_pending = false;
static volatile u32 cutoff_ticks = 0;

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

static usize clamp_volume(usize volume) {
  return volume > SOUND_VOLUME_MAX ? SOUND_VOLUME_MAX : volume;
}

static u32 volume_to_duty(usize volume) {
  return (u32) ((clamp_volume(volume) * SOUND_DUTY_MAX +
    SOUND_VOLUME_MAX / 2) / SOUND_VOLUME_MAX);
}

static u32 scale_duty(u32 duty, usize volume_percent) {
  if(volume_percent >= 100) return duty;
  const u32 scaled = (u32) ((duty * volume_percent + 50) / 100);
  return scaled == 0 && duty != 0 && volume_percent != 0 ? 1 : scaled;
}

static u32 duration_to_ticks(usize duration_ms) {
  // Дополнительный tick не позволяет тону стать короче заказанной длительности
  // из-за произвольной фазы текущей миллисекунды.
  return duration_ms >= 0xFFFFFFFEUL ? 0xFFFFFFFFUL :
    (u32) duration_ms + 1UL;
}

static void force_buzzer_low(void) {
  pinMode(pwm_pin, OUTPUT);
  digitalWrite(pwm_pin, LOW);
}

static u32 channel_to_ll(u32 channel) {
  switch(channel) {
    case 1: return LL_TIM_CHANNEL_CH1;
    case 2: return LL_TIM_CHANNEL_CH2;
    case 3: return LL_TIM_CHANNEL_CH3;
    case 4: return LL_TIM_CHANNEL_CH4;
    default: return 0;
  }
}

static bool enable_pwm_timer_clock(TIM_TypeDef* timer) {
  if(timer == TIM2) {
    __HAL_RCC_TIM2_CLK_ENABLE();
    return true;
  }
  if(timer == TIM4) {
    __HAL_RCC_TIM4_CLK_ENABLE();
    return true;
  }
  if(timer == TIM5) {
    __HAL_RCC_TIM5_CLK_ENABLE();
    return true;
  }
  return false;
}

static void set_compare(TIM_TypeDef* timer, u32 channel, u32 compare) {
  switch(channel) {
    case LL_TIM_CHANNEL_CH1: LL_TIM_OC_SetCompareCH1(timer, compare); break;
    case LL_TIM_CHANNEL_CH2: LL_TIM_OC_SetCompareCH2(timer, compare); break;
    case LL_TIM_CHANNEL_CH3: LL_TIM_OC_SetCompareCH3(timer, compare); break;
    case LL_TIM_CHANNEL_CH4: LL_TIM_OC_SetCompareCH4(timer, compare); break;
    default: break;
  }
}

static void mute_pwm_from_interrupt(void) {
  if(pwm_ready && pwm_timer_instance != NULL && pwm_ll_channel != 0) {
    LL_TIM_CC_DisableChannel(pwm_timer_instance, pwm_ll_channel);
    LL_TIM_DisableCounter(pwm_timer_instance);
  }
}

static bool configure_pwm_mapping(usize pin) {
  pwm_ready = false;
  pwm_timer_instance = NULL;
  pwm_ll_channel = 0;

  const PinName pin_name = digitalPinToPinName(pin);
  if(pin_name == NC) return false;

  TIM_TypeDef* const timer =
    (TIM_TypeDef*) pinmap_peripheral(pin_name, PinMap_TIM);
  if(timer == NULL || !enable_pwm_timer_clock(timer)) return false;

  const u32 function = pinmap_function(pin_name, PinMap_TIM);
  if(STM_PIN_INVERTED(function)) return false;
  const u32 ll_channel = channel_to_ll(STM_PIN_CHANNEL(function));
  if(ll_channel == 0) return false;

  pwm_pin = pin;
  pwm_pin_name = pin_name;
  pwm_timer_instance = timer;
  pwm_ll_channel = ll_channel;
  pwm_ready = true;

  mute_pwm_from_interrupt();
  force_buzzer_low();
  return true;
}

static void configure_pwm(u32 frequency_hz, u32 duty) {
  TIM_TypeDef* const timer = pwm_timer_instance;
  const stm32f4_timer_math::Divider divider =
    stm32f4_timer_math::frequency_divider(
      stm32f4_platform_resources::apb1_timer_clock_hz(), frequency_hz);
  const u32 period_ticks = divider.period_ticks();
  const u32 compare = stm32f4_timer_math::pwm_compare(period_ticks, duty);

  LL_TIM_DisableCounter(timer);
  timer->CR1 = 0;
  timer->CR2 = 0;
  timer->SMCR = 0;
  timer->DIER = 0;
  timer->CCER = 0;
  timer->CCMR1 = 0;
  timer->CCMR2 = 0;
  LL_TIM_SetPrescaler(timer, divider.prescaler_register);
  LL_TIM_SetAutoReload(timer, divider.auto_reload_register);
  LL_TIM_OC_SetMode(timer, pwm_ll_channel, LL_TIM_OCMODE_PWM1);
  LL_TIM_OC_SetPolarity(timer, pwm_ll_channel, LL_TIM_OCPOLARITY_HIGH);
  LL_TIM_OC_EnablePreload(timer, pwm_ll_channel);
  LL_TIM_EnableARRPreload(timer);
  set_compare(timer, pwm_ll_channel, compare);
  LL_TIM_SetCounter(timer, 0);
  LL_TIM_GenerateEvent_UPDATE(timer);
  LL_TIM_ClearFlag_UPDATE(timer);

  // stop() возвращает вывод в GPIO LOW; альтернативная функция включается
  // лишь после полной настройки таймера, поэтому на буззере нет стартового
  // выброса.
  pinmap_pinout(pwm_pin_name, PinMap_TIM);
  LL_TIM_CC_EnableChannel(timer, pwm_ll_channel);
  LL_TIM_EnableCounter(timer);
}

} // namespace

void sound_driver_construct(void) {}

void sound_driver_init(usize pin) {
  sound_driver_stop();
  configure_pwm_mapping(pin);

  const InterruptState irq = disable_interrupts();
  cutoff_ticks = 0;
  stop_cleanup_pending = false;
  sound_active = false;
  restore_interrupts(irq);
}

void sound_driver_play_scaled(usize pin, isize frequency_Hz,
                              usize duration_ms, usize volume,
                              usize volume_percent) {
  const u32 duty = scale_duty(volume_to_duty(volume), volume_percent);
  if(!runtime_safety::valid_sound_frequency(frequency_Hz) ||
     duration_ms == 0 || duty == 0) {
    sound_driver_stop();
    return;
  }

  if(!pwm_ready || pwm_pin != pin) sound_driver_init(pin);
  if(!pwm_ready) {
    sound_driver_stop();
    return;
  }

  const InterruptState irq = disable_interrupts();
  mute_pwm_from_interrupt();
  cutoff_ticks = 0;
  stop_cleanup_pending = false;
  configure_pwm((u32) frequency_Hz, duty);
  cutoff_ticks = duration_to_ticks(duration_ms);
  sound_active = true;
  restore_interrupts(irq);
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms,
                       usize volume) {
  sound_driver_play_scaled(pin, frequency_Hz, duration_ms, volume, 100);
}

void sound_driver_stop(void) {
  const InterruptState irq = disable_interrupts();
  cutoff_ticks = 0;
  mute_pwm_from_interrupt();
  sound_active = false;
  stop_cleanup_pending = false;
  restore_interrupts(irq);
  force_buzzer_low();
}

void sound_driver_poll(void) {
  if(!stop_cleanup_pending) return;

  const InterruptState irq = disable_interrupts();
  const bool cleanup_needed = stop_cleanup_pending && !sound_active;
  if(cleanup_needed) stop_cleanup_pending = false;
  restore_interrupts(irq);

  if(cleanup_needed) sound_driver_stop();
}

bool sound_driver_busy(void) {
  return sound_active || stop_cleanup_pending;
}

void sound_driver_on_systick_isr(void) {
  if(!sound_active) return;

  const u32 remaining = cutoff_ticks;
  if(remaining > 1) {
    cutoff_ticks = remaining - 1UL;
    return;
  }

  cutoff_ticks = 0;
  mute_pwm_from_interrupt();
  sound_active = false;
  stop_cleanup_pending = true;
}

#elif MK61_SOUND_DRIVER_STM32

namespace {

static constexpr usize SOUND_VOLUME_MAX = 10;
static constexpr u32 SOUND_DUTY_MAX = 128;

static manual_lifetime::Storage<HardwareTimer> pwm_timer_storage;
static manual_lifetime::Storage<HardwareTimer> cutoff_timer_storage;

static HardwareTimer& pwmTimer(void) { return pwm_timer_storage.get(); }
static HardwareTimer& cutoffTimer(void) { return cutoff_timer_storage.get(); }

static volatile bool pwm_ready = false;
static usize pwm_pin = PIN_BUZZER;
static PinName pwm_pin_name = NC;
static u32 pwm_channel = 0;
static u32 pwm_ll_channel = 0;
static TIM_TypeDef* pwm_timer_instance = NULL;
static volatile bool sound_active = false;
static volatile bool stop_cleanup_pending = false;

struct InterruptState { u32 primask; };

static InterruptState disable_interrupts(void) {
  const InterruptState state = {__get_PRIMASK()};
  __disable_irq();
  return state;
}

static void restore_interrupts(InterruptState state) {
  __set_PRIMASK(state.primask);
}

static usize clamp_volume(usize volume) {
  return volume > SOUND_VOLUME_MAX ? SOUND_VOLUME_MAX : volume;
}

static u32 volume_to_duty(usize volume) {
  return (u32) ((clamp_volume(volume) * SOUND_DUTY_MAX +
    SOUND_VOLUME_MAX / 2) / SOUND_VOLUME_MAX);
}

static u32 scale_duty(u32 duty, usize volume_percent) {
  if(volume_percent >= 100) return duty;
  const u32 scaled = (u32) ((duty * volume_percent + 50) / 100);
  return scaled == 0 && duty != 0 && volume_percent != 0 ? 1 : scaled;
}

static u32 duration_ms_to_us(usize duration_ms) {
  const u64 duration_us = (u64) duration_ms * 1000;
  return duration_us > 0xFFFFFFFFu ? 0xFFFFFFFFu : (u32) duration_us;
}

static void force_buzzer_low(void) {
  pinMode(pwm_pin, OUTPUT);
  digitalWrite(pwm_pin, LOW);
}

static void clear_cutoff_interrupt(void) {
  TIM_HandleTypeDef* handle = cutoffTimer().getHandle();
  if(handle != NULL) __HAL_TIM_CLEAR_FLAG(handle, TIM_FLAG_UPDATE);
}

static void pause_cutoff_timer(void) {
  cutoffTimer().pause();
  clear_cutoff_interrupt();
}

static void stop_cutoff_from_interrupt(void) {
  TIM_HandleTypeDef* handle = cutoffTimer().getHandle();
  if(handle != NULL) {
    __HAL_TIM_DISABLE_IT(handle, TIM_IT_UPDATE);
    LL_TIM_DisableCounter(handle->Instance);
    __HAL_TIM_CLEAR_FLAG(handle, TIM_FLAG_UPDATE);
  }
}

static void mute_pwm_from_interrupt(void) {
  if(pwm_ready && pwm_timer_instance != NULL && pwm_ll_channel != 0) {
    LL_TIM_OC_SetMode(pwm_timer_instance, pwm_ll_channel,
                     LL_TIM_OCMODE_FORCED_INACTIVE);
    LL_TIM_DisableCounter(pwm_timer_instance);
  }
}

static void stop_from_timer(void) {
  stop_cutoff_from_interrupt();
  mute_pwm_from_interrupt();
  sound_active = false;
  stop_cleanup_pending = true;
}

static bool configure_pwm_mapping(usize pin) {
  pwm_ready = false;
  pwm_timer_instance = NULL;
  pwm_ll_channel = 0;

  const PinName pin_name = digitalPinToPinName(pin);
  if(pin_name == NC) return false;
  TIM_TypeDef* const timer =
    (TIM_TypeDef*) pinmap_peripheral(pin_name, PinMap_TIM);
  if(timer == NULL) return false;
  const u32 channel = STM_PIN_CHANNEL(pinmap_function(pin_name, PinMap_TIM));
  if(channel == 0) return false;

  pwm_pin = pin;
  pwm_pin_name = pin_name;
  pwm_channel = channel;
  pwmTimer().setup(timer);
  pwm_timer_instance = timer;
  pwmTimer().pause();
  pwm_ready = true;
  force_buzzer_low();
  return true;
}

} // namespace

void sound_driver_construct(void) {
  pwm_timer_storage.construct();
  cutoff_timer_storage.construct(MK61_SOUND_CUTOFF_TIMER);
}

void sound_driver_init(usize pin) {
  sound_driver_stop();
  configure_pwm_mapping(pin);

  const InterruptState irq = disable_interrupts();
  pause_cutoff_timer();
  cutoffTimer().detachInterrupt();
  stop_cleanup_pending = false;
  sound_active = false;
  restore_interrupts(irq);
}

void sound_driver_play_scaled(usize pin, isize frequency_Hz,
                              usize duration_ms, usize volume,
                              usize volume_percent) {
  const u32 duty = scale_duty(volume_to_duty(volume), volume_percent);
  if(!runtime_safety::valid_sound_frequency(frequency_Hz) ||
     duration_ms == 0 || duty == 0) {
    sound_driver_stop();
    return;
  }
  if(!pwm_ready || pwm_pin != pin) sound_driver_init(pin);
  if(!pwm_ready) {
    sound_driver_stop();
    return;
  }

  const InterruptState irq = disable_interrupts();
  stop_cleanup_pending = false;
  pause_cutoff_timer();
  cutoffTimer().detachInterrupt();
  pwmTimer().pauseChannel(pwm_channel);
  pwmTimer().pause();
  pwmTimer().setMode(pwm_channel, TIMER_OUTPUT_COMPARE_PWM1, pwm_pin_name);
  pwm_ll_channel = pwmTimer().getLLChannel(pwm_channel);
  pwmTimer().setOverflow((u32) frequency_Hz, HERTZ_FORMAT);
  pwmTimer().setCaptureCompare(pwm_channel, duty,
                               RESOLUTION_8B_COMPARE_FORMAT);
  pwmTimer().resume();
  sound_active = true;

  cutoffTimer().setOverflow(duration_ms_to_us(duration_ms), MICROSEC_FORMAT);
  cutoffTimer().setCount(0);
  clear_cutoff_interrupt();
  cutoffTimer().attachInterrupt(stop_from_timer);
  clear_cutoff_interrupt();
  cutoffTimer().resume();
  restore_interrupts(irq);
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms,
                       usize volume) {
  sound_driver_play_scaled(pin, frequency_Hz, duration_ms, volume, 100);
}

void sound_driver_stop(void) {
  const InterruptState irq = disable_interrupts();
  pause_cutoff_timer();
  cutoffTimer().detachInterrupt();
  clear_cutoff_interrupt();
  if(pwm_ready) {
    pwmTimer().pauseChannel(pwm_channel);
    pwmTimer().pause();
  }
  sound_active = false;
  stop_cleanup_pending = false;
  restore_interrupts(irq);
  force_buzzer_low();
}

void sound_driver_poll(void) {
  if(!stop_cleanup_pending) return;
  const InterruptState irq = disable_interrupts();
  const bool cleanup_needed = stop_cleanup_pending && !sound_active;
  if(cleanup_needed) stop_cleanup_pending = false;
  restore_interrupts(irq);
  if(cleanup_needed) sound_driver_stop();
}

bool sound_driver_busy(void) {
  return sound_active || stop_cleanup_pending;
}

void sound_driver_on_systick_isr(void) {}

#else

namespace {

static usize fallback_pin = PIN_BUZZER;

} // namespace

void sound_driver_construct(void) {}

void sound_driver_init(usize pin) {
  fallback_pin = pin;
  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
}

void sound_driver_play_scaled(usize pin, isize frequency_Hz,
                              usize duration_ms, usize volume,
                              usize volume_percent) {
  if(!runtime_safety::valid_sound_frequency(frequency_Hz) ||
     duration_ms == 0 || volume == 0 || volume_percent == 0) {
    sound_driver_stop();
    return;
  }
  fallback_pin = pin;
  tone(pin, (unsigned int) frequency_Hz, (unsigned long) duration_ms);
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms,
                       usize volume) {
  sound_driver_play_scaled(pin, frequency_Hz, duration_ms, volume, 100);
}

void sound_driver_stop(void) {
  noTone(fallback_pin);
  pinMode(fallback_pin, OUTPUT);
  digitalWrite(fallback_pin, LOW);
}

void sound_driver_poll(void) {}
bool sound_driver_busy(void) { return false; }
void sound_driver_on_systick_isr(void) {}

#endif
