// Fixed active profile: HSE8MHz -> PLLx9, AHB72/APB1 36/APB2 72MHz.
// Timer prescalers are patched together with this function by build.py.
#include "hal_interface.h"
void SystemClock_Config(void){
 LL_FLASH_SetLatency(LL_FLASH_LATENCY_2);
 while(LL_FLASH_GetLatency()!=LL_FLASH_LATENCY_2){}
 LL_FLASH_EnablePrefetch();
 LL_RCC_HSE_Enable();while(!LL_RCC_HSE_IsReady()){}
 // Also safe on wake/re-entry: do not reconfigure an active PLL.
 LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_HSE);
 while(LL_RCC_GetSysClkSource()!=LL_RCC_SYS_CLKSOURCE_STATUS_HSE){}
 LL_RCC_PLL_Disable();while(LL_RCC_PLL_IsReady()){}
 LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSE_DIV_1,LL_RCC_PLL_MUL_9);
 LL_RCC_SetAHBPrescaler(LL_RCC_SYSCLK_DIV_1);
 LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_2);
 LL_RCC_SetAPB2Prescaler(LL_RCC_APB2_DIV_1);
 LL_RCC_PLL_Enable();while(!LL_RCC_PLL_IsReady()){}
 LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);
 while(LL_RCC_GetSysClkSource()!=LL_RCC_SYS_CLKSOURCE_STATUS_PLL){}
 LL_SetSystemCoreClock(72000000u);
 LL_RCC_LSI_Enable();while(!LL_RCC_LSI_IsReady()){}
 LL_PWR_EnableBkUpAccess();
 if(LL_RCC_GetRTCClockSource()!=LL_RCC_RTC_CLKSOURCE_LSE){
  LL_RCC_ForceBackupDomainReset();LL_RCC_ReleaseBackupDomainReset();
 }
 LL_RCC_LSE_Enable();while(!LL_RCC_LSE_IsReady()){}
 if(LL_RCC_GetRTCClockSource()!=LL_RCC_RTC_CLKSOURCE_LSE)
  LL_RCC_SetRTCClockSource(LL_RCC_RTC_CLKSOURCE_LSE);
 LL_RCC_EnableRTC();
 if(HAL_InitTick(TICK_INT_PRIORITY)!=HAL_OK)Error_Handler();
}
