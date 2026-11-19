#ifndef TEST_BIOS_SLEEP_HAL_H
#define TEST_BIOS_SLEEP_HAL_H
#include <stdint.h>
typedef struct { volatile uint32_t SCR; } SCB_Type;
extern SCB_Type test_scb;
#define SCB (&test_scb)
#define SCB_SCR_SLEEPDEEP_Msk 4u
#define SCB_SCR_SLEEPONEXIT_Msk 2u
uint32_t __get_PRIMASK(void);
uint32_t __get_IPSR(void);
uint32_t __get_BASEPRI(void);
uint32_t __get_FAULTMASK(void);
void __disable_irq(void);
void __set_PRIMASK(uint32_t value);
void __DSB(void);
void __WFI(void);
void __ISB(void);
uint32_t uptime_ms(void);
uint32_t coproc_time_us(void *context);
#endif
