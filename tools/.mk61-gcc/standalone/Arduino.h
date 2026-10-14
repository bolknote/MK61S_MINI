#ifndef MK61_NATIVE_PLATFORM_COMPAT_H
#define MK61_NATIVE_PLATFORM_COMPAT_H
// Source compatibility with existing calculator code, without Arduino runtime.
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "stm32_def.h"
#include "PinNames.h"
#include <stm32f4xx_ll_tim.h>
#include <stm32f4xx_ll_rtc.h>
#ifndef F_CPU
#if defined(STM32F411xE)
#define F_CPU 96000000UL
#else
#define F_CPU 84000000UL
#endif
#endif
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define INPUT_PULLDOWN 3
#define INPUT_ANALOG 4
#define OUTPUT_OPEN_DRAIN 5
#define DEC 10
#define HEX 16
#define OCT 8
#define BIN 2
#define LED_BUILTIN PC13
#define PROGMEM
#define pgm_read_byte(address) (*(const uint8_t*)(address))
#define pgm_read_word(address) (*(const uint16_t*)(address))
#define pgm_read_dword(address) (*(const uint32_t*)(address))
#define bitRead(value,bit) (((value)>>(bit))&1U)
#define bitSet(value,bit) ((value)|=(1UL<<(bit)))
#define bitClear(value,bit) ((value)&=~(1UL<<(bit)))
#define noInterrupts() __disable_irq()
#define interrupts() __enable_irq()
#ifdef __cplusplus
#include <algorithm>
using std::min;
using std::max;
using byte=uint8_t;
using boolean=bool;
enum {PA0=0,PA1=1,PA2=2,PA3=3,PA4=4,PA5=5,PA6=6,PA7=7,PA8=8,PA9=9,PA10=10,PA11=11,PA12=12,PA13=13,PA14=14,PA15=15,PB0=16,PB1=17,PB2=18,PB3=19,PB4=20,PB5=21,PB6=22,PB7=23,PB8=24,PB9=25,PB10=26,PB12=27,PB13=28,PB14=29,PB15=30,PC13=31,PC14=32,PC15=33,PH0=34,PH1=35,NUM_DIGITAL_PINS=36};
constexpr PinName digitalPinToPinName(uint32_t pin) {
  return pin<27 ? static_cast<PinName>(pin) : pin<31 ? static_cast<PinName>(pin+1) :
    pin<34 ? static_cast<PinName>(0x2D+pin-31) : pin<36 ? static_cast<PinName>(0x50+pin-34) : NC;
}
inline void enableBackupDomain() { RCC->APB1ENR|=RCC_APB1ENR_PWREN;(void)RCC->APB1ENR;PWR->CR|=PWR_CR_DBP; }
inline GPIO_TypeDef* get_GPIO_Port(uint32_t index) {
  return index==PortH ? GPIOH : index<PortH ? reinterpret_cast<GPIO_TypeDef*>(GPIOA_BASE+index*0x400U) : nullptr;
}
extern "C" {
#endif
void setup(void);
void loop(void);
void yield(void);
uint32_t millis(void);
uint32_t micros(void);
void delay(uint32_t ms);
void delayMicroseconds(uint32_t us);
void pinMode(uint32_t pin,uint32_t mode);
void digitalWrite(uint32_t pin,uint32_t value);
int digitalRead(uint32_t pin);
void _Error_Handler(const char* file,int line);
#define Error_Handler() _Error_Handler(__FILE__,__LINE__)
#ifdef __cplusplus
}
#endif
#endif
