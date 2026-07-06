#include <Arduino.h>
#include "config.h"
#include "sound_driver.hpp"

#if defined(ARDUINO_ARCH_STM32) && defined(HAL_TIM_MODULE_ENABLED) && !defined(HAL_TIM_MODULE_ONLY)

#include <HardwareTimer.h>
#include "PeripheralPins.h"
#include "pinmap.h"

#ifndef MK61_SOUND_CUTOFF_TIMER
  #ifdef TIMER_TONE
    #define MK61_SOUND_CUTOFF_TIMER TIMER_TONE
  #else
    #define MK61_SOUND_CUTOFF_TIMER TIM10
  #endif
#endif

namespace {

static constexpr usize SOUND_VOLUME_MAX = 10;
static constexpr u32   SOUND_DUTY_MAX   = 128; // 50% in 8-bit PWM terms, same loudness range as the old analogWrite code.

static HardwareTimer pwm_timer;
static HardwareTimer cutoff_timer(MK61_SOUND_CUTOFF_TIMER);

static bool pwm_ready = false;
static usize pwm_pin = PIN_BUZZER;
static PinName pwm_pin_name = NC;
static uint32_t pwm_channel = 0;
static volatile bool sound_active = false;

static usize clamp_volume(usize volume) {
  return (volume > SOUND_VOLUME_MAX) ? SOUND_VOLUME_MAX : volume;
}

static u32 volume_to_duty(usize volume) {
  return (u32) ((clamp_volume(volume) * SOUND_DUTY_MAX + (SOUND_VOLUME_MAX / 2)) / SOUND_VOLUME_MAX);
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

static void stop_from_timer(void) {
  pause_cutoff_timer();

  if(pwm_ready) {
    pwm_timer.pauseChannel(pwm_channel);
    pwm_timer.pause();
  }

  force_buzzer_low();
  sound_active = false;
}

static bool configure_pwm_mapping(usize pin) {
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

  // The mapping is resolved here once, explicitly: PIN_BUZZER -> PinName ->
  // TIMx_CHy from the active STM32duino variant's PinMap_TIM table.
  pwm_timer.setup(timer_instance);
  pwm_timer.pause();
  pwm_ready = true;

  force_buzzer_low();
  return true;
}

} // namespace

void sound_driver_init(usize pin) {
  sound_driver_stop();

  pwm_ready = configure_pwm_mapping(pin);

  pause_cutoff_timer();
  cutoff_timer.detachInterrupt();
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms, usize volume) {
  const u32 duty = volume_to_duty(volume);
  if(frequency_Hz <= 0 || duration_ms == 0 || duty == 0) {
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

  pause_cutoff_timer();
  cutoff_timer.detachInterrupt();
  pwm_timer.pauseChannel(pwm_channel);
  pwm_timer.pause();

  // Configure PWM output every time before starting: stop() returns the pin to
  // GPIO LOW, so setMode() restores the alternate-function PWM routing.
  pwm_timer.setMode(pwm_channel, TIMER_OUTPUT_COMPARE_PWM1, pwm_pin_name);
  pwm_timer.setOverflow((u32) frequency_Hz, HERTZ_FORMAT);
  pwm_timer.setCaptureCompare(pwm_channel, duty, RESOLUTION_8B_COMPARE_FORMAT);
  pwm_timer.resume();

  sound_active = true;

  // HardwareTimer has no one-shot mode in this API. The cutoff timer therefore
  // runs as a normal base timer and its first update interrupt stops both
  // itself and the PWM timer.
  cutoff_timer.setOverflow(duration_ms_to_us(duration_ms), MICROSEC_FORMAT);
  cutoff_timer.setCount(0);
  clear_cutoff_interrupt();
  cutoff_timer.attachInterrupt(stop_from_timer);
  clear_cutoff_interrupt();
  cutoff_timer.resume();
}

void sound_driver_stop(void) {
  pause_cutoff_timer();
  cutoff_timer.detachInterrupt();
  clear_cutoff_interrupt();

  if(pwm_ready) {
    pwm_timer.pauseChannel(pwm_channel);
    pwm_timer.pause();
  }

  force_buzzer_low();
  sound_active = false;
}

void sound_driver_poll(void) {
  // Duration cutoff is handled by cutoff_timer interrupt. The polling hook is
  // intentionally kept so existing firmware loops do not depend on driver type.
  (void) sound_active;
}

#else

void sound_driver_init(usize pin) {
  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
}

void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms, usize volume) {
  if(frequency_Hz <= 0 || duration_ms == 0 || volume == 0) {
    sound_driver_stop();
    return;
  }

  tone(pin, (unsigned int) frequency_Hz, (unsigned long) duration_ms);
}

void sound_driver_stop(void) {
  noTone(PIN_BUZZER);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
}

void sound_driver_poll(void) {}

#endif
