#if defined(MK61_NATIVE_RUNTIME)
#include <Arduino.h>
#include "stm32f4_gpio.hpp"
extern "C" void osSystickHandler(void);
extern "C" {
uint32_t SystemCoreClock=16000000;
volatile uint32_t uwTick;
}
namespace {
bool ready(volatile uint32_t& reg,uint32_t mask,uint32_t wanted) {
  for(uint32_t count=0;count<4000000;++count) if((reg&mask)==wanted) return true;
  return false;
}
void fail() { __disable_irq();for(;;) __NOP(); }
void tick_configure() {
  SysTick->CTRL=0;
  SysTick->LOAD=SystemCoreClock/1000U-1U;
  SysTick->VAL=0;
  SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk;
  NVIC_SetPriority(SysTick_IRQn,15);
  SysTick->CTRL=SysTick_CTRL_CLKSOURCE_Msk|SysTick_CTRL_TICKINT_Msk|SysTick_CTRL_ENABLE_Msk;
}
uint32_t apb_clock(uint32_t shift) {
  const uint32_t divider=(RCC->CFGR>>shift)&7U;
  return SystemCoreClock>>(divider<4 ? 0 : divider-3);
}
}
extern "C" void SystemInit(void) {
  // ROM DFU can jump here without a peripheral reset. No old interrupt may
  // observe the resident's .data/.bss before Reset_Handler initializes them.
  __disable_irq();
  SysTick->CTRL=0;
  for(uint32_t bank=0;bank<8;++bank) {
    NVIC->ICER[bank]=0xFFFFFFFFU;
    NVIC->ICPR[bank]=0xFFFFFFFFU;
  }
  SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk|SCB_ICSR_PENDSVCLR_Msk;
  RCC->CR|=RCC_CR_HSION;
  if(!ready(RCC->CR,RCC_CR_HSIRDY,RCC_CR_HSIRDY)) fail();
  RCC->CFGR=(RCC->CFGR&~RCC_CFGR_SW)|RCC_CFGR_SW_HSI;
  if(!ready(RCC->CFGR,RCC_CFGR_SWS,RCC_CFGR_SWS_HSI)) fail();
  RCC->CR&=~RCC_CR_PLLON;
  if(!ready(RCC->CR,RCC_CR_PLLRDY,0)) fail();
  RCC->CFGR=0;
  SCB->CPACR|=0x00F00000U;
  __DSB(); __ISB();
  SCB->VTOR=FLASH_BASE;
}
extern "C" void SystemClock_Config(void) {
  // The USB wake IRQ also calls this when STOP was aborted before WFI, or
  // after foreground STOP recovery already restored the PLL. Keep SysTick's
  // fractional phase in those cases, so micros() cannot move backwards.
  if((RCC->CFGR & RCC_CFGR_SWS) == RCC_CFGR_SWS_PLL &&
     SystemCoreClock == F_CPU) return;
  SysTick->CTRL=0;
  RCC->CR|=RCC_CR_HSION;
  if(!ready(RCC->CR,RCC_CR_HSIRDY,RCC_CR_HSIRDY)) fail();
  RCC->CFGR=(RCC->CFGR&~RCC_CFGR_SW)|RCC_CFGR_SW_HSI;
  if(!ready(RCC->CFGR,RCC_CFGR_SWS,RCC_CFGR_SWS_HSI)) fail();
  RCC->CR&=~RCC_CR_PLLON;
  if(!ready(RCC->CR,RCC_CR_PLLRDY,0)) fail();
  RCC->APB1ENR|=RCC_APB1ENR_PWREN;
  (void)RCC->APB1ENR;
  #if defined(STM32F411xE)
  PWR->CR=(PWR->CR&~PWR_CR_VOS)|PWR_REGULATOR_VOLTAGE_SCALE1;
#else
  PWR->CR=(PWR->CR&~PWR_CR_VOS)|PWR_REGULATOR_VOLTAGE_SCALE2;
#endif
  RCC->CR|=RCC_CR_HSEON;
  if(!ready(RCC->CR,RCC_CR_HSERDY,RCC_CR_HSERDY)) fail();
#if defined(STM32F411xE)
  RCC->PLLCFGR=25U|(192U<<6)|RCC_PLLCFGR_PLLSRC_HSE|(4U<<24);
  FLASH->ACR=FLASH_ACR_LATENCY_3WS|FLASH_ACR_PRFTEN|FLASH_ACR_ICEN|FLASH_ACR_DCEN;
#else
  RCC->PLLCFGR=25U|(336U<<6)|(1U<<16)|RCC_PLLCFGR_PLLSRC_HSE|(7U<<24);
  FLASH->ACR=FLASH_ACR_LATENCY_2WS|FLASH_ACR_PRFTEN|FLASH_ACR_ICEN|FLASH_ACR_DCEN;
#endif
  (void)FLASH->ACR;
  __DSB(); __ISB();
  RCC->CFGR=(RCC->CFGR&~(RCC_CFGR_HPRE|RCC_CFGR_PPRE1|RCC_CFGR_PPRE2))|RCC_CFGR_PPRE1_DIV2;
  RCC->CR|=RCC_CR_PLLON;
  if(!ready(RCC->CR,RCC_CR_PLLRDY,RCC_CR_PLLRDY)) fail();
  // F401/F411 assert VOSRDY only with the main PLL running. Waiting for it
  // before PLLON deadlocks cold start even though the chosen voltage is valid.
  if(!ready(PWR->CSR,PWR_CSR_VOSRDY,PWR_CSR_VOSRDY)) fail();
  RCC->CFGR=(RCC->CFGR&~RCC_CFGR_SW)|RCC_CFGR_SW_PLL;
  if(!ready(RCC->CFGR,RCC_CFGR_SWS,RCC_CFGR_SWS_PLL)) fail();
  SystemCoreClock=F_CPU;
  tick_configure();
}
extern "C" void SystemCoreClockUpdate(void) {
  const uint32_t source=RCC->CFGR&RCC_CFGR_SWS;
  SystemCoreClock=source==RCC_CFGR_SWS_PLL ? F_CPU : source==RCC_CFGR_SWS_HSE ? HSE_VALUE : HSI_VALUE;
}
__attribute__((constructor(101))) static void platform_initialize() {
  NVIC_SetPriorityGrouping(3);
  SystemClock_Config();
  CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;DWT->CYCCNT=0;DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
  __enable_irq();
}
extern "C" void SysTick_Handler(void) { ++uwTick;osSystickHandler(); }
extern "C" uint32_t millis(void) { return uwTick; }
extern "C" __attribute__((noinline)) uint32_t micros(void) {
  const uint32_t mask=__get_PRIMASK(); __disable_irq();
  uint32_t ms=uwTick;
  const uint32_t pending_before=SCB->ICSR&SCB_ICSR_PENDSTSET_Msk;
  uint32_t counter=SysTick->VAL;
  const uint32_t pending_after=SCB->ICSR&SCB_ICSR_PENDSTSET_Msk;
  if(pending_after) {
    ++ms;
    if(!pending_before) counter=SysTick->VAL;
  }
  const uint32_t reload=SysTick->LOAD;
  __set_PRIMASK(mask);
  // VAL=0 is the reload boundary (also the initial write-to-clear value).
  // Counting it as a whole extra millisecond duplicates a pending SysTick.
  const uint32_t fraction=counter ? (reload-counter)*1000U/(reload+1U) : 0;
  return ms*1000U+fraction;
}
extern "C" void delayMicroseconds(uint32_t us) {
  const uint32_t per_us=SystemCoreClock/1000000U;
  while(us) {
    const uint32_t portion=us>1000000U ? 1000000U:us;
    const uint32_t begin=DWT->CYCCNT,cycles=portion*per_us;
    while((uint32_t)(DWT->CYCCNT-begin)<cycles) {}
    us-=portion;
  }
}
extern "C" void delay(uint32_t ms) {
  if(__get_PRIMASK()) { while(ms--) delayMicroseconds(1000);return; }
  const uint32_t begin=millis();while((uint32_t)(millis()-begin)<ms) {}
}
extern "C" void yield(void) {}
extern "C" void pinMode(uint32_t pin,uint32_t mode) { stm32f4_gpio::configure(pin,mode); }
extern "C" void digitalWrite(uint32_t pin,uint32_t value) { stm32f4_gpio::write(pin,value); }
extern "C" int digitalRead(uint32_t pin) { return stm32f4_gpio::read(pin); }
extern "C" uint32_t HAL_GetTick(void) { return millis(); }
extern "C" void HAL_Delay(uint32_t ms) { delay(ms); }
extern "C" void HAL_SuspendTick(void) { SysTick->CTRL&=~SysTick_CTRL_TICKINT_Msk; }
extern "C" void HAL_ResumeTick(void) { SysTick->CTRL|=SysTick_CTRL_TICKINT_Msk; }
extern "C" uint32_t HAL_RCC_GetHCLKFreq(void) { return SystemCoreClock; }
extern "C" uint32_t HAL_RCC_GetPCLK1Freq(void) { return apb_clock(10); }
extern "C" uint32_t HAL_RCC_GetPCLK2Freq(void) { return apb_clock(13); }
extern "C" void HAL_NVIC_SetPriority(IRQn_Type irq,uint32_t preempt,uint32_t sub) {
  NVIC_SetPriority(irq,NVIC_EncodePriority(NVIC_GetPriorityGrouping(),preempt,sub));
}
extern "C" void HAL_NVIC_EnableIRQ(IRQn_Type irq) { NVIC_EnableIRQ(irq); }
extern "C" void HAL_NVIC_DisableIRQ(IRQn_Type irq) { NVIC_DisableIRQ(irq); }
extern "C" void HAL_PWR_EnablePVD(void) { PWR->CR|=PWR_CR_PVDE; }
extern "C" void HAL_PWR_DisablePVD(void) { PWR->CR&=~PWR_CR_PVDE; }
extern "C" void HAL_PWR_ConfigPVD(PWR_PVDTypeDef* config) {
  PWR->CR=(PWR->CR&~PWR_CR_PLS)|config->PVDLevel;
  const uint32_t bit=1U<<16;
  EXTI->IMR=(EXTI->IMR&~bit)|((config->Mode&0x00010000U) ? bit:0);
  EXTI->EMR=(EXTI->EMR&~bit)|((config->Mode&0x00020000U) ? bit:0);
  EXTI->RTSR=(EXTI->RTSR&~bit)|((config->Mode&0x1U) ? bit:0);
  EXTI->FTSR=(EXTI->FTSR&~bit)|((config->Mode&0x2U) ? bit:0);
}
extern "C" __attribute__((noinline)) void HAL_PWR_EnterSTOPMode(uint32_t regulator,uint8_t entry) {
  if(entry!=PWR_STOPENTRY_WFI) fail();
  PWR->CR=(PWR->CR&~(PWR_CR_PDDS|PWR_CR_LPDS))|regulator;
  SCB->SCR|=SCB_SCR_SLEEPDEEP_Msk;__DSB();__WFI();__ISB();SCB->SCR&=~SCB_SCR_SLEEPDEEP_Msk;
}
extern "C" void USBD_SystemClockConfigFromResume(void) { SystemClock_Config(); }
extern "C" void _Error_Handler(const char*,int) { fail(); }
extern "C" void __cxa_pure_virtual(void) { fail(); }
extern "C" void _init(void) {}
extern "C" void _fini(void) {}
int main() { setup();for(;;) loop(); }
#endif
