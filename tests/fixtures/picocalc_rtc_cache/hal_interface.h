#ifndef PICOCALC_RTC_CACHE_TEST_HAL_H
#define PICOCALC_RTC_CACHE_TEST_HAL_H
#include <stdint.h>
typedef enum { HAL_OK, HAL_ERROR } HAL_StatusTypeDef;
typedef struct { uint8_t Hours, Minutes, Seconds; } RTC_TimeTypeDef;
typedef struct { uint8_t WeekDay, Month, Date, Year; } RTC_DateTypeDef;
typedef union { uint32_t raw; RTC_TimeTypeDef _s; } RTC_TimeTypeDef_u;
typedef union { uint32_t raw; RTC_DateTypeDef _s; } RTC_DateTypeDef_u;
typedef struct {
    volatile uint32_t CRH, CRL, PRLH, PRLL, DIVH, DIVL, CNTH, CNTL, ALRH, ALRL;
} RTC_TypeDef;
typedef struct { RTC_TypeDef *Instance; RTC_DateTypeDef DateToUpdate; } RTC_HandleTypeDef;
enum { RTC_CRL_SECF=1, RTC_CRL_ALRF=2, RTC_CRL_OWF=4, RTC_CRL_RSF=8,
       RTC_CRL_CNF=16, RTC_CRL_RTOFF=32, RTC_FORMAT_BIN=0 };
extern volatile RTC_TimeTypeDef_u rtc_time;
extern volatile RTC_DateTypeDef_u rtc_date;
uint32_t __get_PRIMASK(void);
void __disable_irq(void);
void __set_PRIMASK(uint32_t);
void test_rtc_write(volatile uint32_t *, uint32_t);
#define WRITE_REG(reg, value) test_rtc_write(&(reg), (value))
HAL_StatusTypeDef HAL_RTC_GetDate(RTC_HandleTypeDef *, RTC_DateTypeDef *, uint32_t);
HAL_StatusTypeDef HAL_RTC_GetTime(RTC_HandleTypeDef *, RTC_TimeTypeDef *, uint32_t);
#endif
