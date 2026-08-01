#if defined(ARDUINO_ARCH_STM32)
  #include "config.h"
#endif

#include "spi1_dma.hpp"

#if MK61_SPI1_DMA_SUPPORTED
  #include <Arduino.h>
  #include <SPI.h>
  #include <stm32f4xx.h>
  #include "stm32f4_platform_resources.hpp"
#endif

namespace spi1_dma {
namespace {

static Snapshot counters = {
    MK61_SPI1_DMA_SUPPORTED != 0, (u16) MK61_SPI1_DMA_THRESHOLD,
    0, 0, 0, 0, 0, 0, 0};

static u32 saturated_increment(u32 value) {
  return value == 0xFFFFFFFFUL ? value : value + 1U;
}

#if MK61_SPI1_DMA_SUPPORTED

static u32 saturated_add(u32 left, u32 right) {
  return left > 0xFFFFFFFFUL - right ? 0xFFFFFFFFUL : left + right;
}

static DMA_HandleTypeDef rx_dma = {};
static DMA_HandleTypeDef tx_dma = {};
static SPI_HandleTypeDef* active_spi;
static u8 dummy_tx = 0xFF;
static u8 sink_rx;
static bool initialized;

static void configure_handle(DMA_HandleTypeDef& handle,
                             DMA_Stream_TypeDef* instance,
                             u32 direction) {
  handle.Instance = instance;
  handle.Init.Channel = DMA_CHANNEL_3;
  handle.Init.Direction = direction;
  handle.Init.PeriphInc = DMA_PINC_DISABLE;
  handle.Init.MemInc = DMA_MINC_DISABLE;
  handle.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
  handle.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
  handle.Init.Mode = DMA_NORMAL;
  handle.Init.Priority = DMA_PRIORITY_HIGH;
  handle.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
  handle.Init.FIFOThreshold = DMA_FIFO_THRESHOLD_FULL;
  handle.Init.MemBurst = DMA_MBURST_SINGLE;
  handle.Init.PeriphBurst = DMA_PBURST_SINGLE;
}

static bool initialize(SPI_HandleTypeDef* spi) {
  if(initialized) return active_spi == spi;

  static_assert(stm32f4_platform_resources::SPI1_DMA_CONTROLLER == 2,
                "SPI1 DMA backend expects DMA2");
  static_assert(stm32f4_platform_resources::SPI1_RX_DMA_STREAM == 2 &&
                stm32f4_platform_resources::SPI1_TX_DMA_STREAM == 3 &&
                stm32f4_platform_resources::SPI1_RX_DMA_CHANNEL == 3 &&
                stm32f4_platform_resources::SPI1_TX_DMA_CHANNEL == 3,
                "SPI1 DMA backend and platform resource map disagree");

  __HAL_RCC_DMA2_CLK_ENABLE();
  configure_handle(rx_dma, MK61_SPI1_RX_DMA_INSTANCE,
                   DMA_PERIPH_TO_MEMORY);
  configure_handle(tx_dma, MK61_SPI1_TX_DMA_INSTANCE,
                   DMA_MEMORY_TO_PERIPH);
  if(HAL_DMA_Init(&rx_dma) != HAL_OK) return false;
  if(HAL_DMA_Init(&tx_dma) != HAL_OK) {
    (void) HAL_DMA_DeInit(&rx_dma);
    return false;
  }

  __HAL_LINKDMA(spi, hdmarx, rx_dma);
  __HAL_LINKDMA(spi, hdmatx, tx_dma);
  HAL_NVIC_SetPriority(MK61_SPI1_RX_DMA_IRQ, 2, 0);
  HAL_NVIC_SetPriority(MK61_SPI1_TX_DMA_IRQ, 2, 0);
  HAL_NVIC_EnableIRQ(MK61_SPI1_RX_DMA_IRQ);
  HAL_NVIC_EnableIRQ(MK61_SPI1_TX_DMA_IRQ);
  active_spi = spi;
  initialized = true;
  return true;
}

static void set_memory_increment(DMA_HandleTypeDef& handle, bool enabled) {
  handle.Init.MemInc = enabled ? DMA_MINC_ENABLE : DMA_MINC_DISABLE;
  MODIFY_REG(handle.Instance->CR, DMA_SxCR_MINC, handle.Init.MemInc);
}

static void wait_for_interrupt(void) {
  const u32 saved_scr = SCB->SCR;
  SCB->SCR = saved_scr & ~SCB_SCR_SLEEPDEEP_Msk;
  __DSB();
  __WFI();
  __ISB();
  SCB->SCR = saved_scr;
  __DSB();
}

static void stop_failed_transfer(SPI_HandleTypeDef* spi) {
  (void) HAL_SPI_DMAStop(spi);
  __HAL_SPI_DISABLE_IT(spi, SPI_IT_ERR);
  spi->State = HAL_SPI_STATE_READY;
}

#endif

} // namespace

Result transfer(SPIClass* interface, const void* tx_buffer, void* rx_buffer,
                usize count) {
#if MK61_SPI1_DMA_SUPPORTED
  if(interface == nullptr || count < MK61_SPI1_DMA_THRESHOLD ||
     count > 0xFFFFU || (tx_buffer == nullptr && rx_buffer == nullptr) ||
     __get_PRIMASK() != 0 || __get_IPSR() != 0) {
    counters.polling_fallbacks =
        saturated_increment(counters.polling_fallbacks);
    return Result::NOT_USED;
  }

  SPI_HandleTypeDef* const spi = interface->getHandle();
  if(spi == nullptr || spi->Instance != SPI1 ||
     HAL_SPI_GetState(spi) != HAL_SPI_STATE_READY) {
    counters.polling_fallbacks =
        saturated_increment(counters.polling_fallbacks);
    return Result::NOT_USED;
  }
  if(!initialize(spi)) {
    counters.initialization_failures =
        saturated_increment(counters.initialization_failures);
    return Result::NOT_USED;
  }

  set_memory_increment(tx_dma, tx_buffer != nullptr);
  set_memory_increment(rx_dma, rx_buffer != nullptr);
  u8* const tx = tx_buffer != nullptr
      ? const_cast<u8*>(static_cast<const u8*>(tx_buffer)) : &dummy_tx;
  u8* const rx = rx_buffer != nullptr
      ? static_cast<u8*>(rx_buffer) : &sink_rx;

  if(HAL_SPI_TransmitReceive_DMA(spi, tx, rx, (u16) count) != HAL_OK) {
    stop_failed_transfer(spi);
    counters.transfer_failures =
        saturated_increment(counters.transfer_failures);
    return Result::FAILED;
  }

  const u32 started_ms = millis();
  while(HAL_SPI_GetState(spi) != HAL_SPI_STATE_READY) {
    if((u32) (millis() - started_ms) >= 100U) {
      stop_failed_transfer(spi);
      counters.timeouts = saturated_increment(counters.timeouts);
      counters.transfer_failures =
          saturated_increment(counters.transfer_failures);
      return Result::FAILED;
    }
    counters.wfi_entries = saturated_increment(counters.wfi_entries);
    wait_for_interrupt();
  }

  if(HAL_SPI_GetError(spi) != HAL_SPI_ERROR_NONE ||
     HAL_DMA_GetError(&rx_dma) != HAL_DMA_ERROR_NONE ||
     HAL_DMA_GetError(&tx_dma) != HAL_DMA_ERROR_NONE) {
    counters.transfer_failures =
        saturated_increment(counters.transfer_failures);
    return Result::FAILED;
  }

  counters.transfers = saturated_increment(counters.transfers);
  counters.bytes = saturated_add(counters.bytes, (u32) count);
  return Result::COMPLETE;
#else
  (void) interface;
  (void) tx_buffer;
  (void) rx_buffer;
  (void) count;
  counters.polling_fallbacks =
      saturated_increment(counters.polling_fallbacks);
  return Result::NOT_USED;
#endif
}

Snapshot statistics(void) { return counters; }

void reset_statistics(void) {
  counters.transfers = 0;
  counters.bytes = 0;
  counters.wfi_entries = 0;
  counters.polling_fallbacks = 0;
  counters.initialization_failures = 0;
  counters.transfer_failures = 0;
  counters.timeouts = 0;
}

const char* backend_name(void) {
#if MK61_SPI1_DMA_SUPPORTED
  return "DMA2-S2/S3-C3";
#else
  return "disabled";
#endif
}

} // namespace spi1_dma

#if MK61_SPI1_DMA_SUPPORTED
extern "C" void DMA2_Stream2_IRQHandler(void) {
  HAL_DMA_IRQHandler(&spi1_dma::rx_dma);
}

extern "C" void DMA2_Stream3_IRQHandler(void) {
  HAL_DMA_IRQHandler(&spi1_dma::tx_dma);
}
#endif
