#include "spi1_transport.hpp"
#if MK61_SPI1_DIRECT_SUPPORTED
#include "spi1_dma.hpp"
#include "stm32_spi_clock.hpp"
namespace spi1_transport {
namespace {
static bool initialized;
static bool healthy = true;
static __attribute__((always_inline)) inline bool wait_flag(u32 mask, bool set, u32 started) {
  // Resolve the ordinary wire wait with a tight, bounded burst before
  // adding the deadline bookkeeping to a peripheral that is still stalled.
  for (unsigned probe = 0; probe < 4; ++probe) {
    if (((SPI1->SR & mask) != 0) == set)
      return true;
  }
  u32 polls = 0;
  while (((SPI1->SR & mask) != 0) != set) {
    // The wire takes tens of CPU cycles per byte. Keep its ordinary flag
    // loop short; recheck the deadline at most every 32 unsuccessful polls.
    if ((++polls & 31U) == 0 && (u32)(HAL_GetTick() - started) >= 100U) {
      healthy = false;
      return false;
    }
  }
  return true;
}
static bool polling(const void *tx_buffer, void *rx_buffer, usize count) {
  const u8 *tx = static_cast<const u8 *>(tx_buffer);
  u8 *rx = static_cast<u8 *>(rx_buffer);
  const u32 started = HAL_GetTick();
  for (usize i = 0; i < count; ++i) {
    if (!wait_flag(SPI_SR_TXE, true, started))
      return false;
    *reinterpret_cast<volatile u8 *>(&SPI1->DR) = tx ? tx[i] : 0xFF;
    if (!wait_flag(SPI_SR_RXNE, true, started))
      return false;
    const u8 value = *reinterpret_cast<volatile u8 *>(&SPI1->DR);
    if (rx)
      rx[i] = value;
  }
  return wait_flag(SPI_SR_BSY, false, started);
}
static __attribute__((always_inline)) inline bool wait_flag(u32 mask, bool set) {
  if (((SPI1->SR & mask) != 0) == set)
    return true;
  return wait_flag(mask, set, HAL_GetTick());
}
} // namespace
bool begin() {
  if (initialized)
    return true;
#if defined(PIN_SPI_MOSI) && defined(PIN_SPI_MISO) && defined(PIN_SPI_SCK)
  static_assert(PIN_SPI_MOSI == PA7 && PIN_SPI_MISO == PA6 && PIN_SPI_SCK == PA5,
                "owned SPI1 transport requires the qualified PA5/PA6/PA7 bus");
#endif
  RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
  (void)RCC->AHB1ENR;
  // Alternate function 5, push-pull, very high speed, no pulls. Other pins
  // share GPIOA with display controls and must remain untouched.
  constexpr u32 pairs = (3UL << 10) | (3UL << 12) | (3UL << 14);
  GPIOA->OTYPER &= ~((1U << 5) | (1U << 6) | (1U << 7));
  GPIOA->OSPEEDR |= pairs;
  GPIOA->PUPDR &= ~pairs;
  GPIOA->AFR[0] = (GPIOA->AFR[0] & ~((15UL << 20) | (15UL << 24) | (15UL << 28))) |
                  (5UL << 20) | (5UL << 24) | (5UL << 28);
  GPIOA->MODER = (GPIOA->MODER & ~pairs) | (2UL << 10) | (2UL << 12) | (2UL << 14);
  RCC->APB2ENR |= RCC_APB2ENR_SPI1EN;
  (void)RCC->APB2ENR;
  SPI1->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI | SPI_CR1_BR;
  SPI1->CR2 = 0;
  SPI1->CR1 |= SPI_CR1_SPE;
  initialized = true;
  healthy = true;
  return true;
}
void end() {
  if (!initialized)
    return;
  (void)end_transaction();
  SPI1->CR1 &= ~SPI_CR1_SPE;
  RCC->APB2ENR &= ~RCC_APB2ENR_SPI1EN;
  initialized = false;
}
bool begin_transaction(u32 requested_hz) {
  if (requested_hz == 0 || !begin())
    return false;
  if (!wait_flag(SPI_SR_BSY, false)) {
    (void)end_transaction();
    return false;
  }
  const u32 pclk = peripheral_clock_hz();
  u8 code = 0;
  while (code < 7 && stm32_spi_clock::actual_hz(pclk, code) > requested_hz)
    ++code;
  const u32 desired = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI |
      ((u32)code << SPI_CR1_BR_Pos) | SPI_CR1_SPE;
  if(SPI1->CR1 != desired || SPI1->CR2 != 0) {
    SPI1->CR1 &= ~SPI_CR1_SPE;
    SPI1->CR1 = desired & ~SPI_CR1_SPE;
    SPI1->CR2 = 0;
    SPI1->CR1 |= SPI_CR1_SPE;
  }
  healthy = true;
  return true;
}
bool end_transaction() {
  if (!initialized)
    return false;
  const bool ok = healthy && wait_flag(SPI_SR_BSY, false);
  if (!ok) {
    // A timed-out peripheral must not contaminate the next client's bus.
    RCC->APB2RSTR |= RCC_APB2RSTR_SPI1RST;
    RCC->APB2RSTR &= ~RCC_APB2RSTR_SPI1RST;
    initialized = false;
  }
  return ok;
}
u8 transfer(u8 value) {
  if(!healthy) return 0xFF;
  if(!wait_flag(SPI_SR_TXE,true)) return 0xFF;
  *reinterpret_cast<volatile u8*>(&SPI1->DR) = value;
  if(!wait_flag(SPI_SR_RXNE,true)) return 0xFF;
  const u8 result = *reinterpret_cast<volatile u8*>(&SPI1->DR);
  if(!wait_flag(SPI_SR_BSY,false)) return 0xFF;
  return result;
}
bool transfer_buffer(const void *tx, void *rx, usize count, bool allow_dma) {
  if (!healthy)
    return false;
  if (count == 0)
    return true;
  const spi1_dma::Result result =
      allow_dma ? spi1_dma::transfer(tx, rx, count) : spi1_dma::Result::NOT_USED;
  if (result == spi1_dma::Result::COMPLETE)
    return true;
  if (result == spi1_dma::Result::FAILED) {
    healthy = false;
    return false;
  }
  return polling(tx, rx, count);
}
u32 peripheral_clock_hz() {
  return HAL_RCC_GetPCLK2Freq();
}
u8 br_code() {
  return (u8)((SPI1->CR1 & SPI_CR1_BR) >> SPI_CR1_BR_Pos);
}
} // namespace spi1_transport
#endif
