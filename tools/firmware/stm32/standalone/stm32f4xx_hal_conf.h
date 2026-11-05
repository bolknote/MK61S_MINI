#ifndef MK61_NATIVE_HAL_TYPES_H
#define MK61_NATIVE_HAL_TYPES_H
// Type/macro declarations for ST LL and compatibility calls; no HAL objects are linked.
#define HSE_VALUE 25000000U
#define HSI_VALUE 16000000U
#define LSE_VALUE 32768U
#define LSI_VALUE 32000U
#define HSE_STARTUP_TIMEOUT 100U
#define LSE_STARTUP_TIMEOUT 5000U
#define VDD_VALUE 3300U
#define TICK_INT_PRIORITY 15U
#define USE_RTOS 0U
#define PREFETCH_ENABLE 1U
#define INSTRUCTION_CACHE_ENABLE 1U
#define DATA_CACHE_ENABLE 1U
#define assert_param(value) ((void)0)
#define HAL_TIM_MODULE_ENABLED
#define HAL_RTC_MODULE_ENABLED
#include <stm32f4xx_hal_dma.h>
#include <stm32f4xx_hal_tim.h>
#include <stm32f4xx_hal_rtc.h>
#include <stm32f4xx_hal_rcc.h>
#include <stm32f4xx_hal_gpio.h>
#include <stm32f4xx_hal_cortex.h>
#include <stm32f4xx_hal_pwr.h>
#include <stm32f4xx_hal_flash.h>
#include <stm32f4xx_hal_pcd.h>
#endif
