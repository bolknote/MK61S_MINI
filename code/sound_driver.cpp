#include <Arduino.h>
#include "config.h"
#include "runtime_safety.hpp"
#include "sound_driver.hpp"

#if defined(ARDUINO_ARCH_STM32) && defined(HAL_TIM_MODULE_ENABLED) && !defined(HAL_TIM_MODULE_ONLY)

#include <HardwareTimer.h>
#include "PeripheralPins.h"
#include "pinmap.h"

#ifndef MK61_SOUND_CUTOFF_TIMER
  #ifdef TIMER_TONE
    #define MK61_SOUND_CUTOFF_TIMER TIMER_TONE
  #elif defined(TIM10)
    #define MK61_SOUND_CUTOFF_TIMER TIM10
  #else
    #error "No timer available for sound cutoff. Define MK61_SOUND_CUTOFF_TIMER in config.h."
  #endif
#endif

namespace {

static constexpr usize SOUND_VOLUME_MAX = 10;
static constexpr u32   SOUND_DUTY_MAX   = 128; // 50% в 8-битном ШИМ, тот же диапазон громкости, что у прежнего кода analogWrite.

static HardwareTimer pwm_timer;
static HardwareTimer cutoff_timer(MK61_SOUND_CUTOFF_TIMER);

static volatile bool pwm_ready = false;
static usize pwm_pin = PIN_BUZZER;
static PinName pwm_pin_name = NC;
static uint32_t pwm_channel = 0;
static uint32_t pwm_ll_channel = 0;
static TIM_TypeDef* pwm_timer_instance = NULL;
static volatile bool sound_active = false;
static volatile bool stop_cleanup_pending = false;

struct InterruptState {
  uint32_t primask;
};

static InterruptState disable_interrupts(void) {
  const InterruptState state = { __get_PRIMASK() };
  __disable_irq();
  return state;
}

static void restore_interrupts(InterruptState state) {
  __set_PRIMASK(state.primask);
}

static usize clamp_volume(usize volume) {
  return (volume > SOUND_VOLUME_MAX) ? SOUND_VOLUME_MAX : volume;
}

static u32 volume_to_duty(usize volume) {
  return (u32) ((clamp_volume(volume) * SOUND_DUTY_MAX + (SOUND_VOLUME_MAX / 2)) / SOUND_VOLUME_MAX);
}

static u32 scale_duty(u32 duty, usize volume_percent) {
  if(volume_percent >= 100) return duty;
  const u32 scaled = (u32) ((duty * volume_percent + 50) / 100);
  return (scaled == 0 && duty != 0 && volume_percent != 0) ? 1 : scaled;
}

static u32 duration_ms_to_us(usize duration_ms) {
  const u64 duration_us = (u64) duration_ms * 1000;
  return (duration_us > 0xFFFFFFFFu) ? 0xFFFFFFFFu : (u32) duration_us;
}

static void force_buzzer_low(void) {
  pinMode(pwm_pin, OUTPUT);
  digitalWrite(pwm_pin, LOW);
}

static void clear_cutoff_interrupt(void) {
  TIM_HandleTypeDef* handle = cutoff_timer.getHandle();
  if(handle != NULL) {
    __HAL_TIM_CLEAR_FLAG(handle, TIM_FLAG_UPDATE);
  }
}

static void pause_cutoff_timer(void) {
  cutoff_timer.pause();
  clear_cutoff_interrupt();
}

static void stop_cutoff_from_interrupt(void) {
  TIM_HandleTypeDef* handle = cutoff_timer.getHandle();
  if(handle != NULL) {
    __HAL_TIM_DISABLE_IT(handle, TIM_IT_UPDATE);
    LL_TIM_DisableCounter(handle->Instance);
    __HAL_TIM_CLEAR_FLAG(handle, TIM_FLAG_UPDATE);
  }
}

static void mute_pwm_from_interrupt(void) {
  if(pwm_ready && pwm_timer_instance != NULL && pwm_ll_channel != 0) {
    LL_TIM_OC_SetMode(pwm_timer_instance, pwm_ll_channel, LL_TIM_OCMODE_FORCED_INACTIVE);
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

  TIM_TypeDef* const timer_instance = (TIM_TypeDef*) pinmap_peripheral(pin_name, PinMap_TIM);
  if(timer_instance == NULL) return false;

  const uint32_t timer_function = pinmap_function(pin_name, PinMap_TIM);
  const uint32_t channel = STM_PIN_CHANNEL(timer_function);
  if(channel == 0) return false;

  pwm_pin = pin;
  pwm_pin_name = pin_name;
  pwm_channel = channel;

  // Здесь однократно и явно определяется соответствие: PIN_BUZZER -> PinName ->
  // TIMx_CHy из таблицы PinMap_TIM активного варианта STM32duino.
  // pwm_ll_channel здесь НЕ определяется: HardwareTimer::getLLChannel()
  // возвращает корректную маску лишь после того, как setMode() пометит канал
  // используемым, поэтому значение определяется в sound_driver_play() сразу
  // после setMode().
  pwm_timer.setup(timer_instance);
  pwm_timer_instance = timer_instance;
  pwm_timer.pause();
  pwm_ready = true;

  force_buzzer_low();
  return true;
}

} // анонимное пространство имён

void sound_driver_init(usize pin) {
  sound_driver_stop();

  configure_pwm_mapping(pin);

  const InterruptState irq = disable_interrupts();
  pause_cutoff_timer();
  cutoff_timer.detachInterrupt();
  stop_cleanup_pending = false;
  sound_active = false;
  restore_interrupts(irq);
}

void sound_driver_play_scaled(usize pin, isize frequency_Hz, usize duration_ms, usize volume, usize volume_percent) {
  const u32 duty = scale_duty(volume_to_duty(volume), volume_percent);
  if(!runtime_safety::valid_sound_frequency(frequency_Hz) || duration_ms == 0 || duty == 0) {
    sound_driver_stop();
    return;
  }

  if(!pwm_ready || pwm_pin != pin) {
    sound_driver_init(pin);
  }

  if(!pwm_ready) {
    sound_driver_stop();
    return;
  }

  const InterruptState irq = disable_interrupts();
  stop_cleanup_pending = false;
  pause_cutoff_timer();
  cutoff_timer.detachInterrupt();
  pwm_timer.pauseChannel(pwm_channel);
  pwm_timer.pause();

  // Настраиваем выход ШИМ перед каждым запуском: stop() возвращает вывод в
  // состояние GPIO LOW, поэтому setMode() восстанавливает альтернативную
  // функцию ШИМ.
  pwm_timer.setMode(pwm_channel, TIMER_OUTPUT_COMPARE_PWM1, pwm_pin_name);
  // getLLChannel() возвращает 0, пока setMode() не пометит канал используемым,
  // поэтому LL-маску для mute_pwm_from_interrupt() нужно определять после
  // setMode().
  pwm_ll_channel = pwm_timer.getLLChannel(pwm_channel);
  pwm_timer.setOverflow((u32) frequency_Hz, HERTZ_FORMAT);
  pwm_timer.setCaptureCompare(pwm_channel, duty, RESOLUTION_8B_COMPARE_FORMAT);
  pwm_timer.resume();

  sound_active = true;

  // В этом API у HardwareTimer нет однократного режима. Поэтому таймер отсечки
  // работает как обычный базовый таймер, а первое прерывание обновления
  // останавливает и его самого, и таймер ШИМ.
  cutoff_timer.setOverflow(duration_ms_to_us(duration_ms), MICROSEC_FORMAT);
  cutoff_timer.setCount(0);
  clear_cutoff_interrupt();
  cutoff_timer.attachInterrupt(stop_from_timer);
  clear_cutoff_interrupt();
  cutoff_timer.resume();
  restore_interrupts(irq);
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms, usize volume) {
  sound_driver_play_scaled(pin, frequency_Hz, duration_ms, volume, 100);
}

void sound_driver_stop(void) {
  const InterruptState irq = disable_interrupts();
  pause_cutoff_timer();
  cutoff_timer.detachInterrupt();
  clear_cutoff_interrupt();

  if(pwm_ready) {
    pwm_timer.pauseChannel(pwm_channel);
    pwm_timer.pause();
  }

  sound_active = false;
  stop_cleanup_pending = false;
  restore_interrupts(irq);

  force_buzzer_low();
}

void sound_driver_poll(void) {
  if(!stop_cleanup_pending) {
    return;
  }

  const InterruptState irq = disable_interrupts();
  const bool cleanup_needed = stop_cleanup_pending && !sound_active;
  if(cleanup_needed) {
    stop_cleanup_pending = false;
  }
  restore_interrupts(irq);

  if(cleanup_needed) {
    sound_driver_stop();
  }
}

#else

namespace {

static usize fallback_pin = PIN_BUZZER;

} // анонимное пространство имён

void sound_driver_init(usize pin) {
  fallback_pin = pin;
  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
}

void sound_driver_play_scaled(usize pin, isize frequency_Hz, usize duration_ms, usize volume, usize volume_percent) {
  if(!runtime_safety::valid_sound_frequency(frequency_Hz) || duration_ms == 0 ||
     volume == 0 || volume_percent == 0) {
    sound_driver_stop();
    return;
  }

  fallback_pin = pin;
  tone(pin, (unsigned int) frequency_Hz, (unsigned long) duration_ms);
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms, usize volume) {
  sound_driver_play_scaled(pin, frequency_Hz, duration_ms, volume, 100);
}

void sound_driver_stop(void) {
  noTone(fallback_pin);
  pinMode(fallback_pin, OUTPUT);
  digitalWrite(fallback_pin, LOW);
}

void sound_driver_poll(void) {}

#endif
