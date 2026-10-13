#if defined(ARDUINO_ARCH_STM32)
#include "config.h"
#endif

#include "spi1_dma.hpp"

#if MK61_SPI1_DMA_SUPPORTED
#include <Arduino.h>
#include <stm32f4xx.h>
#include "stm32f4_platform_resources.hpp"
#endif

namespace spi1_dma {
namespace {

static Snapshot counters = {
    MK61_SPI1_DMA_SUPPORTED != 0, (u16)MK61_SPI1_DMA_THRESHOLD, 0, 0, 0, 0, 0, 0, 0};

static u32 saturated_increment(u32 value) {
  return value == 0xFFFFFFFFUL ? value : value + 1U;
}

#if MK61_SPI1_DMA_SUPPORTED

static u32 saturated_add(u32 left, u32 right) {
  return left > 0xFFFFFFFFUL - right ? 0xFFFFFFFFUL : left + right;
}

static volatile u32 completed;
static volatile u32 errors;
static u8 dummy_tx = 0xFF;
static u8 sink_rx;
static constexpr u32 RX_FLAGS = DMA_LIFCR_CFEIF2 | DMA_LIFCR_CDMEIF2 |
                                DMA_LIFCR_CTEIF2 | DMA_LIFCR_CHTIF2 | DMA_LIFCR_CTCIF2;
static constexpr u32 TX_FLAGS = DMA_LIFCR_CFEIF3 | DMA_LIFCR_CDMEIF3 |
                                DMA_LIFCR_CTEIF3 | DMA_LIFCR_CHTIF3 | DMA_LIFCR_CTCIF3;
// AN4031: FEIF is ignored in direct mode; FEIE remains disabled.
static constexpr u32 RX_ERRORS = DMA_LISR_DMEIF2 | DMA_LISR_TEIF2;
static constexpr u32 TX_ERRORS = DMA_LISR_DMEIF3 | DMA_LISR_TEIF3;
static bool stop_streams() {
  SPI1->CR2 &= ~(SPI_CR2_RXDMAEN | SPI_CR2_TXDMAEN);
  MK61_SPI1_RX_DMA_INSTANCE->CR &= ~DMA_SxCR_EN;
  MK61_SPI1_TX_DMA_INSTANCE->CR &= ~DMA_SxCR_EN;
  const u32 started = millis();
  while (((MK61_SPI1_RX_DMA_INSTANCE->CR | MK61_SPI1_TX_DMA_INSTANCE->CR) &
          DMA_SxCR_EN) != 0) {
    if ((u32)(millis() - started) >= 100U)
      return false;
  }
  DMA2->LIFCR = RX_FLAGS | TX_FLAGS;
  return true;
}
static void wait_for_interrupt() {
  const u32 saved = SCB->SCR;
  SCB->SCR = saved & ~SCB_SCR_SLEEPDEEP_Msk;
  __DSB();
  __WFI();
  __ISB();
  SCB->SCR = saved;
  __DSB();
}

#endif

} // namespace

Result transfer(const void *tx_buffer, void *rx_buffer, usize count) {
#if MK61_SPI1_DMA_SUPPORTED
  if (count < MK61_SPI1_DMA_THRESHOLD || count > 0xFFFFU ||
      (tx_buffer == nullptr && rx_buffer == nullptr) || __get_PRIMASK() != 0 ||
      __get_IPSR() != 0) {
    counters.polling_fallbacks = saturated_increment(counters.polling_fallbacks);
    return Result::NOT_USED;
  }
  static_assert(stm32f4_platform_resources::SPI1_RX_DMA_STREAM == 2 &&
                    stm32f4_platform_resources::SPI1_TX_DMA_STREAM == 3 &&
                    stm32f4_platform_resources::SPI1_RX_DMA_CHANNEL == 3 &&
                    stm32f4_platform_resources::SPI1_TX_DMA_CHANNEL == 3,
                "SPI1 DMA backend and resource plan disagree");
  RCC->AHB1ENR |= RCC_AHB1ENR_DMA2EN;
  (void)RCC->AHB1ENR;
  if (!stop_streams()) {
    counters.initialization_failures =
        saturated_increment(counters.initialization_failures);
    return Result::FAILED;
  }
  DMA_Stream_TypeDef *const rx = MK61_SPI1_RX_DMA_INSTANCE;
  DMA_Stream_TypeDef *const tx = MK61_SPI1_TX_DMA_INSTANCE;
  constexpr u32 control = (3UL << DMA_SxCR_CHSEL_Pos) | DMA_SxCR_PL_1 | DMA_SxCR_TCIE |
                          DMA_SxCR_TEIE | DMA_SxCR_DMEIE;
  rx->CR = control | (rx_buffer ? DMA_SxCR_MINC : 0);
  tx->CR = control | DMA_SxCR_DIR_0 | (tx_buffer ? DMA_SxCR_MINC : 0);
  rx->FCR = 0;
  tx->FCR = 0; // Direct mode, byte-wide peripheral and memory.
  rx->PAR = (u32)(uintptr_t)&SPI1->DR;
  tx->PAR = (u32)(uintptr_t)&SPI1->DR;
  rx->M0AR = (u32)(uintptr_t)(rx_buffer ? rx_buffer : &sink_rx);
  tx->M0AR = (u32)(uintptr_t)(tx_buffer ? tx_buffer : &dummy_tx);
  rx->NDTR = count;
  tx->NDTR = count;
  completed = 0;
  errors = 0;
  NVIC_ClearPendingIRQ(MK61_SPI1_RX_DMA_IRQ);
  NVIC_ClearPendingIRQ(MK61_SPI1_TX_DMA_IRQ);
  NVIC_SetPriority(MK61_SPI1_RX_DMA_IRQ, 2);
  NVIC_SetPriority(MK61_SPI1_TX_DMA_IRQ, 2);
  NVIC_EnableIRQ(MK61_SPI1_RX_DMA_IRQ);
  NVIC_EnableIRQ(MK61_SPI1_TX_DMA_IRQ);
  __DMB();
  rx->CR |= DMA_SxCR_EN;
  tx->CR |= DMA_SxCR_EN;
  SPI1->CR2 |= SPI_CR2_RXDMAEN | SPI_CR2_TXDMAEN;
  const u32 started = millis();
  bool timeout = false;
  while (completed != 3 && errors == 0) {
    if ((u32)(millis() - started) >= 100U) {
      timeout = true;
      break;
    }
    counters.wfi_entries = saturated_increment(counters.wfi_entries);
    wait_for_interrupt();
  }
  while (!timeout && errors == 0 && (SPI1->SR & SPI_SR_BSY) != 0) {
    if ((u32)(millis() - started) >= 100U)
      timeout = true;
  }
  const bool stopped = stop_streams();
  __DMB();
  if (timeout || errors != 0 || !stopped ||
      (SPI1->SR & (SPI_SR_OVR | SPI_SR_MODF)) != 0) {
    counters.transfer_failures = saturated_increment(counters.transfer_failures);
    if (timeout)
      counters.timeouts = saturated_increment(counters.timeouts);
    return Result::FAILED;
  }
  counters.transfers = saturated_increment(counters.transfers);
  counters.bytes = saturated_add(counters.bytes, (u32)count);
  return Result::COMPLETE;
#else
  (void)tx_buffer;
  (void)rx_buffer;
  (void)count;
  counters.polling_fallbacks = saturated_increment(counters.polling_fallbacks);
  return Result::NOT_USED;
#endif
}

Snapshot statistics(void) {
  return counters;
}

void reset_statistics(void) {
  counters.transfers = 0;
  counters.bytes = 0;
  counters.wfi_entries = 0;
  counters.polling_fallbacks = 0;
  counters.initialization_failures = 0;
  counters.transfer_failures = 0;
  counters.timeouts = 0;
}

const char *backend_name(void) {
#if MK61_SPI1_DMA_SUPPORTED
  return "DMA2-S2/S3-C3";
#else
  return "disabled";
#endif
}

} // namespace spi1_dma

#if MK61_SPI1_DMA_SUPPORTED
extern "C" void DMA2_Stream2_IRQHandler(void) {
  const u32 flags = DMA2->LISR;
  DMA2->LIFCR = spi1_dma::RX_FLAGS;
  if ((flags & spi1_dma::RX_ERRORS) != 0)
    spi1_dma::errors |= 1;
  if ((flags & DMA_LISR_TCIF2) != 0)
    spi1_dma::completed |= 1;
}

extern "C" void DMA2_Stream3_IRQHandler(void) {
  const u32 flags = DMA2->LISR;
  DMA2->LIFCR = spi1_dma::TX_FLAGS;
  if ((flags & spi1_dma::TX_ERRORS) != 0)
    spi1_dma::errors |= 2;
  if ((flags & DMA_LISR_TCIF3) != 0)
    spi1_dma::completed |= 2;
}
#endif
