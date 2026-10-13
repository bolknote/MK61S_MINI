#include <Arduino.h>
#include "stm32f4_adc.hpp"
#include "stm32f4_rtc.hpp"
#include "spi1_transport.hpp"
#include "spi1_dma.hpp"
#include "stm32f4_buzzer.hpp"
#include "stm32f4_keyboard_exti.hpp"
#include <iostream>
#include <array>
RCC_TypeDef model_rcc;
GPIO_TypeDef model_gpio, model_gpio_b;
TIM_TypeDef model_tim2, model_tim4;
SYSCFG_TypeDef model_syscfg;
PWR_TypeDef model_pwr;
ADC_TypeDef model_adc;
ADC_Common_TypeDef model_common;
SPI_TypeDef model_spi;
RTC_TypeDef model_rtc;
EXTI_TypeDef model_exti;
DMA_Stream_TypeDef model_rx, model_tx;
DMA_TypeDef model_dma;
SCB_TypeDef model_scb;
extern "C" void DMA2_Stream2_IRQHandler();
extern "C" void DMA2_Stream3_IRQHandler();
static uint32_t elapsed;
static unsigned conversions, channel_samples[19];
static bool fail_adc, raw_noise, unlocked, inject_alarm_a, rollover;
static unsigned ssr_reads, init_exits, synchronizations;
static int dma_mode;
static bool primask, in_irq, inject_keyboard, dma_pending;
static bool nvic_enabled[64];
static unsigned nvic_priority[64];

uint32_t model_read(const void *address, uint32_t value) {
  if (address == &model_common.CCR)
    assert((model_rcc.APB2ENR.value & RCC_APB2ENR_ADC1EN) != 0);
  if (address == &model_rtc.SSR && rollover) {
    if (ssr_reads++ == 0)
      return 2;
    model_rtc.TR.value = 0;
    model_rtc.DR.value = 0x0027A101;
    return 254;
  }
  return value;
}
void model_write(void *address, uint32_t value) {
  auto *reg = static_cast<Register *>(address);
  if (address == &model_adc.CR2 && (value & ADC_CR2_SWSTART)) {
    assert((model_rcc.APB2ENR.value & RCC_APB2ENR_ADC1EN) != 0);
    ++conversions;
    const unsigned channel = model_adc.SQR3.value;
    assert(channel >= 16 && channel <= 18);
    const unsigned sample = channel_samples[channel]++ % 6;
    constexpr unsigned values[3][6] = {{0, 700, 900, 800, 750, 850},
                                       {0, 1600, 1700, 1500, 1800, 1650},
                                       {0, 900, 1100, 1000, 950, 1050}};
    model_adc.DR.value = raw_noise ? 42 : values[channel - 16][sample];
    if (!fail_adc)
      model_adc.SR.value |= ADC_SR_EOC;
    value &= ~ADC_CR2_SWSTART;
  }
  if (address == &model_rtc.WPR) {
    if (value == 0x53 && reg->value == 0xCA)
      unlocked = true;
    if (value == 0xFF)
      unlocked = false;
  }
  if (address == &model_rtc.ISR) {
    constexpr uint32_t flags =
        RTC_ISR_ALRAF | RTC_ISR_ALRBF | RTC_ISR_WUTF | RTC_ISR_RSF;
    uint32_t old = reg->value;
    if (inject_alarm_a && (old & RTC_ISR_ALRBF) && !(value & RTC_ISR_ALRBF)) {
      old |= RTC_ISR_ALRAF;
      inject_alarm_a = false;
    }
    if ((old ^ value) & RTC_ISR_INIT)
      assert(unlocked);
    reg->value =
        (old & ~flags & ~RTC_ISR_INIT) | (old & value & flags) | (value & RTC_ISR_INIT);
    if ((old & RTC_ISR_INIT) && !(value & RTC_ISR_INIT))
      ++init_exits;
    return;
  }
  if (address == &model_rtc.CR || address == &model_rtc.CALR ||
      address == &model_rtc.PRER || address == &model_rtc.TR ||
      address == &model_rtc.DR) {
    assert(unlocked);
    if (address == &model_rtc.PRER || address == &model_rtc.TR ||
        address == &model_rtc.DR)
      assert(model_rtc.ISR.value & RTC_ISR_INITF);
  }
  if (address == &model_rcc.BDCR) {
    if (value & RCC_BDCR_BDRST)
      model_rtc = RTC_TypeDef{};
    if (value & RCC_BDCR_LSEON)
      value |= RCC_BDCR_LSERDY;
  }
  if (address == &model_rcc.CSR && (value & RCC_CSR_LSION))
    value |= RCC_CSR_LSIRDY;
  if (address == &model_rcc.APB2RSTR && (value & RCC_APB2RSTR_SPI1RST))
    model_spi = SPI_TypeDef{};
  if (address == &model_dma.LIFCR)
    model_dma.LISR.value &= ~value;
  if (address == &model_exti.PR) {
    if(inject_keyboard) { reg->value |= 1U << 6; inject_keyboard = false; }
    reg->value &= ~value;
    return;
  }
  reg->value = value;
}
uint32_t millis() {
  return elapsed++ / 1000;
}
uint32_t micros() {
  return elapsed++;
}
void delayMicroseconds(uint32_t amount) {
  elapsed += amount;
}
void yield() {
  elapsed += 1000;
  if (model_rtc.ISR.value & RTC_ISR_INIT)
    model_rtc.ISR.value |= RTC_ISR_INITF;
  else {
    model_rtc.ISR.value &= ~RTC_ISR_INITF;
    if ((model_rtc.CR.value & RTC_CR_BYPSHAD) == 0) {
      if (!(model_rtc.ISR.value & RTC_ISR_RSF))
        ++synchronizations;
      model_rtc.ISR.value |= RTC_ISR_RSF;
    }
  }
  if (!(model_rtc.CR.value & RTC_CR_ALRAE))
    model_rtc.ISR.value |= RTC_ISR_ALRAWF;
  if (!(model_rtc.CR.value & RTC_CR_ALRBE))
    model_rtc.ISR.value |= RTC_ISR_ALRBWF;
  if (!(model_rtc.CR.value & RTC_CR_WUTE))
    model_rtc.ISR.value |= RTC_ISR_WUTWF;
}
void __DMB() {
}
void __DSB() {
}
void __ISB() {
}
static void dma_complete() {
  model_dma.LISR.value |=
      dma_mode == 1 ? DMA_LISR_TEIF3 : DMA_LISR_TCIF2 | DMA_LISR_TCIF3 | DMA_LISR_FEIF3;
  model_rx.CR.value &= ~DMA_SxCR_EN;
  model_tx.CR.value &= ~DMA_SxCR_EN;
  DMA2_Stream2_IRQHandler();
  DMA2_Stream3_IRQHandler();
}
void __WFI() {
  assert(primask); // No gap for an IRQ to be consumed before the sleep.
  elapsed += 1000;
  if (dma_mode == 2)
    return; // Lost IRQ: bounded timeout must stop both streams.
  dma_pending = true; // PRIMASK delays the handler, but the IRQ wakes WFI.
}
uint32_t __get_PRIMASK() { return primask; }
void __disable_irq() {
  if(dma_mode == 3 && (model_rx.CR.value & DMA_SxCR_EN))
    dma_complete(); // Completion in the original check-to-WFI race window.
  primask = true;
}
void __set_PRIMASK(uint32_t value) {
  primask = value != 0;
  if(!primask && dma_pending) { dma_pending = false; dma_complete(); }
}
uint32_t __get_IPSR() {
  return in_irq;
}
void NVIC_ClearPendingIRQ(int) {
}
void NVIC_SetPendingIRQ(int) {
}
void NVIC_SetPriority(int irq, unsigned value) { nvic_priority[irq] = value;
}
void NVIC_EnableIRQ(int irq) { nvic_enabled[irq] = true;
}
void NVIC_DisableIRQ(int irq) { nvic_enabled[irq] = false;
}
static void reset_model() {
  elapsed = 0;
  conversions = 0;
  fail_adc = false;
  raw_noise = false;
  for (auto &n : channel_samples)
    n = 0;
  model_rcc = {};
  model_gpio = {};
  model_pwr = {};
  model_adc = {};
  model_common = {};
  model_rtc = {};
  model_exti = {};
  model_rx = {};
  model_tx = {};
  model_dma = {};
  unlocked = false;
  inject_alarm_a = false;
  rollover = false;
  ssr_reads = 0;
  init_exits = 0;
  synchronizations = 0;
  dma_mode = 0;
  primask = false;
  in_irq = false;
}
static void adc_tests() {
  reset_model();
  uint16_t v = 99, t = 99, b = 99;
  assert(stm32f4_adc::read_internal(v, t, b));
  assert(v == 1650 && t == 800 && b == 1000 && conversions == 18);
  assert(!(model_rcc.APB2ENR.value & RCC_APB2ENR_ADC1EN));
  assert(model_adc.CR2.value == 0 && model_common.CCR.value == 0);
  fail_adc = true;
  v = t = b = 99;
  assert(!stm32f4_adc::read_internal(v, t, b));
  assert(v == 99 && t == 99 && b == 99 && model_adc.CR2.value == 0);
  assert(elapsed >= 1000);
  fail_adc = false;
  raw_noise = true;
  const unsigned before = conversions;
  assert(stm32f4_adc::read_vbat(b) && b == 42 && conversions == before + 1);
}
static void rtc_tests() {
  reset_model();
  RTC_TimeTypeDef time = {}, result = {};
  RTC_DateTypeDef date = {}, result_date = {};
  time.Hours = 23;
  time.Minutes = 59;
  time.Seconds = 59;
  date.Year = 26;
  date.Month = 12;
  date.Date = 31;
  date.WeekDay = 4;
  model_rtc.CR.value = RTC_CR_BYPSHAD;
  assert(stm32f4_rtc::set_calendar(time, date));
  assert(init_exits == 1 && synchronizations == 1 && !unlocked);
  model_rtc.SSR.value = 2;
  rollover = true;
  assert(stm32f4_rtc::snapshot(result, result_date));
  assert(result.Hours == 0 && result.Seconds == 0 && result_date.Year == 27 &&
         result_date.Month == 1 && result_date.Date == 1 && result.SubSeconds == 254);
  rollover = false;
  model_rtc.CR.value = RTC_CR_ALRAIE | RTC_CR_ALRBIE;
  model_rtc.ISR.value |= RTC_ISR_ALRBF;
  inject_alarm_a = true;
  assert(stm32f4_rtc::alarm_irq() == 3);
  assert(!(model_rtc.ISR.value & (RTC_ISR_ALRAF | RTC_ISR_ALRBF)));
  model_rtc.ISR.value |= RTC_ISR_ALRAF | RTC_ISR_ALRBF;
  assert(stm32f4_rtc::deactivate_alarm(RTC_ALARM_A));
  assert(!(model_rtc.ISR.value & RTC_ISR_ALRAF) &&
         (model_rtc.ISR.value & RTC_ISR_ALRBF));
  model_rtc.ISR.value |= RTC_ISR_WUTWF;
  assert(stm32f4_rtc::arm_wakeup(123));
  assert(!stm32f4_rtc::arm_wakeup(123)); // Active lease cannot be stolen.
  model_rtc.ISR.value |= RTC_ISR_WUTF;
  stm32f4_rtc::wakeup_irq();
  assert(stm32f4_rtc::wakeup_pending()); // Pending survives clearing hardware flag.
  assert(stm32f4_rtc::disarm_wakeup() && !stm32f4_rtc::wakeup_pending());
  reset_model();
  model_rtc.ISR.value = RTC_ISR_INITS;
  model_rtc.TR.value = 0x00123456;
  model_rtc.DR.value = 0x00265013;
  model_rtc.SSR.value = 12;
  model_rcc.BDCR.value = RCC_BDCR_RTCSEL_0 | RCC_BDCR_LSEON;
  (&model_rtc.BKP0R)[0] = 0x1234;
  for (unsigned i = 0; i < 19; ++i)
    model_rtc.other_backup[i] = i + 1;
  assert(stm32f4_rtc::begin(rtc_clock::ClockSource::LSI, nullptr));
  assert(model_rtc.TR.value == 0x00123456 && model_rtc.DR.value == 0x00265013);
  assert(model_rtc.BKP0R == 0x1234);
  for (unsigned i = 0; i < 19; ++i)
    assert(model_rtc.other_backup[i] == i + 1);
}
static void spi_tests() {
  reset_model();
  model_spi.SR.value = SPI_SR_TXE | SPI_SR_RXNE;
  model_gpio.MODER.value = 0xAAAAAAAA;
  assert(spi1_transport::begin_transaction(24000000));
  assert(spi1_transport::br_code() == 1);
  constexpr uint32_t mask = (3U << 10) | (3U << 12) | (3U << 14);
  assert((model_gpio.MODER.value & ~mask) == (0xAAAAAAAAU & ~mask));
  assert(spi1_transport::transfer(0x5A) == 0x5A);
  assert(spi1_transport::begin_transaction(8000000) && spi1_transport::br_code() == 3);
  std::array<uint8_t, 65> bytes{};
  spi1_dma::reset_statistics();
  assert(spi1_dma::transfer(bytes.data(), bytes.data(), bytes.size()) ==
         spi1_dma::Result::COMPLETE);
  assert(spi1_dma::statistics().transfer_failures ==
         0); // Direct-mode FEIF is not a transfer error.
  dma_mode = 1;
  assert(spi1_dma::transfer(bytes.data(), bytes.data(), bytes.size()) ==
         spi1_dma::Result::FAILED);
  assert((model_rx.CR.value & DMA_SxCR_EN) == 0 &&
         (model_tx.CR.value & DMA_SxCR_EN) == 0);
  dma_mode = 2;
  assert(spi1_dma::transfer(bytes.data(), bytes.data(), bytes.size()) ==
         spi1_dma::Result::FAILED);
  assert(spi1_dma::statistics().timeouts == 1);
  primask = true;
  assert(spi1_dma::transfer(bytes.data(), bytes.data(), bytes.size()) ==
         spi1_dma::Result::NOT_USED);
  primask = false;
  dma_mode = 3;
  spi1_dma::reset_statistics();
  model_scb.SCR.value = SCB_SCR_SLEEPDEEP_Msk;
  assert(spi1_dma::transfer(bytes.data(),bytes.data(),bytes.size()) == spi1_dma::Result::COMPLETE);
  assert(!primask && spi1_dma::statistics().wfi_entries == 0);
  assert(model_scb.SCR.value == SCB_SCR_SLEEPDEEP_Msk);
  dma_mode = 0;
  assert(spi1_dma::transfer(bytes.data(),bytes.data(),bytes.size()) == spi1_dma::Result::COMPLETE);
  assert(!primask && spi1_dma::statistics().wfi_entries == 1);
  assert(model_scb.SCR.value == SCB_SCR_SLEEPDEEP_Msk);
  model_spi.SR.value = SPI_SR_BSY;
  assert(!spi1_transport::begin_transaction(24000000));
  assert(model_spi.CR1.value == 0);
  model_spi.SR.value = SPI_SR_TXE | SPI_SR_RXNE;
  assert(spi1_transport::begin_transaction(24000000));
  assert(spi1_transport::transfer(0xAA) == 0xAA);
  spi1_transport::end();
}
static void fixed_pin_checks() {
  reset_model();
  GPIO_TypeDef& gpio = PIN_BUZZER == PA0 ? model_gpio : model_gpio_b;
  gpio.MODER.value = 0x55555555; gpio.AFR[0].value = 0x12345678;
  gpio.AFR[1].value = 0x87654321; gpio.PUPDR.value = 0xAAAAAAAA;
  gpio.OTYPER.value = 0xFFFF; gpio.OSPEEDR.value = 0x55555555;
  const auto before = gpio;
  stm32f4_buzzer::enable_timer_clock();
  assert(model_rcc.APB1ENR.value & (PIN_BUZZER == PB9 ? RCC_APB1ENR_TIM4EN : RCC_APB1ENR_TIM2EN));
  assert(stm32f4_buzzer::timer() == (PIN_BUZZER == PB9 ? TIM4 : TIM2));
  assert(stm32f4_buzzer::CHANNEL == (PIN_BUZZER == PB9 ? 4 : (PIN_BUZZER == PB10 ? 3 : 1)));
  stm32f4_buzzer::alternate_function();
  constexpr uint32_t pair = 3UL << (stm32f4_buzzer::BIT * 2U);
  constexpr uint32_t af_mask = 15UL << ((stm32f4_buzzer::BIT & 7U) * 4U);
  assert((gpio.MODER.value & pair) == (2UL << (stm32f4_buzzer::BIT * 2U)));
  assert((gpio.MODER.value & ~pair) == (before.MODER.value & ~pair));
  assert((gpio.PUPDR.value & pair) == 0 && (gpio.PUPDR.value & ~pair) == (before.PUPDR.value & ~pair));
  assert((gpio.OTYPER.value & (1UL << stm32f4_buzzer::BIT)) == 0);
  assert((gpio.AFR[stm32f4_buzzer::BIT >> 3].value & ~af_mask) == (before.AFR[stm32f4_buzzer::BIT >> 3].value & ~af_mask));
  assert(((gpio.AFR[stm32f4_buzzer::BIT >> 3].value & af_mask) >> ((stm32f4_buzzer::BIT & 7U) * 4U)) == stm32f4_buzzer::AF);
  model_exti.IMR.value = 1U << 17; model_exti.RTSR.value = 1U << 17;
  model_exti.FTSR.value = 0xFFFF;
  model_syscfg.EXTICR[1].value = 0xABCD0000; model_syscfg.EXTICR[2].value = 0x76543210;
  model_exti.PR.value = stm32f4_keyboard_exti::MASK | (1U << 17);
  stm32f4_keyboard_exti::arm();
  assert(model_exti.PR.value == (1U << 17));
  assert(model_exti.IMR.value == (stm32f4_keyboard_exti::MASK | (1U << 17)));
  assert(model_syscfg.EXTICR[1].value == 0xABCD1111 && model_syscfg.EXTICR[2].value == 0x76543211);
  assert((model_exti.FTSR.value & stm32f4_keyboard_exti::MASK) == 0);
  assert(nvic_enabled[EXTI4_IRQn] && nvic_enabled[EXTI9_5_IRQn]);
  assert(nvic_priority[EXTI4_IRQn] == 6 && nvic_priority[EXTI9_5_IRQn] == 6);
  model_exti.PR.value |= (1U << 4) | (1U << 8); inject_keyboard = true;
  assert(stm32f4_keyboard_exti::take_pending() == ((1U << 4) | (1U << 8)));
  assert(model_exti.PR.value == ((1U << 6) | (1U << 17)));
  assert(stm32f4_keyboard_exti::take_pending() == (1U << 6));
  stm32f4_keyboard_exti::disarm();
  assert(model_exti.IMR.value == (1U << 17) && model_exti.PR.value == (1U << 17));
  assert(!nvic_enabled[EXTI4_IRQn] && !nvic_enabled[EXTI9_5_IRQn]);
}

int main() {
  fixed_pin_checks();
  adc_tests();
  rtc_tests();
  spi_tests();
  std::cout << "STM32 owned driver hardware-state model: OK\n";
}
