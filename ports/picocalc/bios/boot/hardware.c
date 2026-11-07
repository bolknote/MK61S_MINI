/* STM32F103R8, polling recovery loader. No HAL, interrupts, dynamic memory,
 * EEPROM, RTC or option-byte writes. The application owns PMU policy. */
#include "stm32f1xx.h"
#include "wire.h"
#include <string.h>
static m3b_link link;
extern void boot_jump(uint32_t base) __attribute__((noreturn));
void *memcpy(void *d, const void *s, size_t n) {
  uint8_t *a = d;
  const uint8_t *b = s;
  while (n--)
    *a++ = *b++;
  return d;
}
void *memset(void *d, int c, size_t n) {
  uint8_t *a = d;
  while (n--)
    *a++ = (uint8_t)c;
  return d;
}
int memcmp(const void *a, const void *b, size_t n) {
  const uint8_t *x = a, *y = b;
  while (n--) {
    if (*x != *y)
      return *x - *y;
    ++x;
    ++y;
  }
  return 0;
}
static void watchdog(void) { IWDG->KR = 0xaaaa; }
static int wait_flash(void) {
  for (unsigned i = 0; i < 2000000; ++i) {
    watchdog();
    if (!(FLASH->SR & FLASH_SR_BSY))
      return !(FLASH->SR & (FLASH_SR_PGERR | FLASH_SR_WRPRTERR));
  }
  return 0;
}
static int unlock(void) {
  if (FLASH->CR & FLASH_CR_LOCK) {
    FLASH->KEYR = 0x45670123;
    FLASH->KEYR = 0xcdef89ab;
  }
  FLASH->SR = FLASH_SR_PGERR | FLASH_SR_WRPRTERR | FLASH_SR_EOP;
  return wait_flash();
}
static const uint8_t *read_flash(void *p, uint32_t at, uint32_t n) {
  (void)p;
  if (at < M3B_FLASH || at > M3B_SETTINGS || n > M3B_SETTINGS - at)
    return 0;
  return (const uint8_t *)(uintptr_t)at;
}
static int erase_page(void *p, uint32_t at) {
  (void)p;
  if ((at & (M3B_PAGE - 1)) || at < M3B_APP || at > M3B_META || !unlock())
    return 0;
  FLASH->CR |= FLASH_CR_PER;
  FLASH->AR = at;
  FLASH->CR |= FLASH_CR_STRT;
  const int ok = wait_flash();
  FLASH->CR &= ~FLASH_CR_PER;
  FLASH->CR |= FLASH_CR_LOCK;
  if (!ok)
    return 0;
  for (unsigned i = 0; i < M3B_PAGE; i += 4)
    if (*(volatile uint32_t *)(uintptr_t)(at + i) != ~0u)
      return 0;
  return 1;
}
static int program(void *p, uint32_t at, const uint8_t *data, uint32_t n) {
  (void)p;
  if ((at & 1) || (n & 1) || at < M3B_APP || at > M3B_META + M3B_PAGE ||
      n > M3B_META + M3B_PAGE - at || !unlock())
    return 0;
  int ok = 1;
  for (unsigned i = 0; i < n; i += 2) {
    volatile uint16_t *dst = (volatile uint16_t *)(uintptr_t)(at + i);
    const uint16_t v =
        (uint16_t)((unsigned)data[i] | (unsigned)data[i + 1] << 8);
    if (*dst == v)
      continue;
    if (*dst != 0xffff) {
      ok = 0;
      break;
    }
    FLASH->CR |= FLASH_CR_PG;
    *dst = v;
    ok = wait_flash() && *dst == v;
    FLASH->CR &= ~FLASH_CR_PG;
    if (!ok)
      break;
  }
  FLASH->CR |= FLASH_CR_LOCK;
  return ok;
}
static void quiet(void) {
  __disable_irq();
  SysTick->CTRL = 0;
  for (unsigned i = 0; i < 3; ++i) {
    NVIC->ICER[i] = ~0u;
    NVIC->ICPR[i] = ~0u;
  }
  RCC->AHBENR |= RCC_AHBENR_DMA1EN;
  DMA1_Channel1->CCR = 0;
  DMA1_Channel2->CCR = 0;
  DMA1_Channel3->CCR = 0;
  DMA1_Channel4->CCR = 0;
  DMA1_Channel5->CCR = 0;
  DMA1_Channel6->CCR = 0;
  DMA1_Channel7->CCR = 0;
  /* Stop app timers/I2C without touching GPIO outputs, especially Pico EN. */
  const uint32_t reset = RCC_APB1RSTR_TIM2RST | RCC_APB1RSTR_TIM3RST |
                         RCC_APB1RSTR_TIM4RST | RCC_APB1RSTR_I2C1RST |
                         RCC_APB1RSTR_I2C2RST | RCC_APB1RSTR_USART3RST;
  RCC->APB1RSTR |= reset;
  RCC->APB1RSTR &= ~reset;
  RCC->APB2RSTR = RCC_APB2RSTR_TIM1RST;
  RCC->APB2RSTR = 0;
  RCC->CR |= RCC_CR_HSION;
  while (!(RCC->CR & RCC_CR_HSIRDY))
    watchdog();
  RCC->CFGR &= ~RCC_CFGR_SW;
  while (RCC->CFGR & RCC_CFGR_SWS)
    watchdog();
  RCC->CFGR = 0;
  RCC->CR &= ~RCC_CR_PLLON;
}
static void recovery_uart(void) {
  RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_IOPCEN;
  AFIO->MAPR = (AFIO->MAPR & ~(AFIO_MAPR_USART3_REMAP | AFIO_MAPR_SWJ_CFG)) |
               AFIO_MAPR_USART3_REMAP_PARTIALREMAP | AFIO_MAPR_SWJ_CFG_DISABLE;
  /* PA13 holds the power switch on. Preload ODR before changing its mode. */
  GPIOA->BSRR = 1u << 13;
  GPIOA->BRR = 1u << 14;
  GPIOA->CRH = (GPIOA->CRH & ~0x0ff00000u) | 0x02200000u;
  GPIOC->BSRR = 1u << 11;
  GPIOC->CRH = (GPIOC->CRH & ~0x0000ff00u) | 0x00008b00u;
  RCC->APB1ENR |= RCC_APB1ENR_USART3EN;
  USART3->CR1 = 0;
  USART3->CR2 = 0;
  USART3->CR3 = 0;
  USART3->BRR = 69;
  USART3->CR1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE;
}
static void run_app(int keep) {
  volatile uint32_t *box = (volatile uint32_t *)M3B_MAILBOX;
  box[0] = 0;
  box[1] = 0;
  box[2] = keep ? M3B_KEEP : 0;
  box[3] = ~box[2];
  USART3->CR1 = 0;
  RCC->APB1ENR &= ~RCC_APB1ENR_USART3EN;
  __DSB();
  boot_jump(M3B_APP);
}
void boot_main(void) {
  volatile uint32_t *box = (volatile uint32_t *)M3B_MAILBOX;
  const int force = box[0] == M3B_FORCE && box[1] == ~M3B_FORCE;
  box[0] = box[1] = 0;
  quiet();
  const m3b_flash f = {0, read_flash, erase_page, program};
  m3b_link_init(&link, &f);
  if (!force && m3b_valid(&link.update))
    run_app(0);
  recovery_uart();
  for (;;) {
    watchdog();
    const uint32_t sr = USART3->SR;
    if (sr & (USART_SR_ORE | USART_SR_FE | USART_SR_NE | USART_SR_PE)) {
      (void)USART3->DR;
      link.received = 0;
      link.overflow = 1;
      continue;
    }
    if (!(sr & USART_SR_RXNE))
      continue;
    const unsigned bytes = m3b_feed(&link, (uint8_t)USART3->DR);
    for (unsigned i = 0; i < bytes; ++i) {
      while (!(USART3->SR & USART_SR_TXE))
        watchdog();
      USART3->DR = link.tx[i];
    }
    if (bytes) {
      while (!(USART3->SR & USART_SR_TC))
        watchdog();
      if (link.update.run)
        run_app(1);
    }
  }
}
