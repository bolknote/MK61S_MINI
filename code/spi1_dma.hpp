#ifndef MK61_SPI1_DMA_HPP
#define MK61_SPI1_DMA_HPP

#include "rust_types.h"

#ifndef MK61_ENABLE_SPI1_ARBITER
  #define MK61_ENABLE_SPI1_ARBITER 0
#endif
#ifndef MK61_ENABLE_SPI1_DMA
  #define MK61_ENABLE_SPI1_DMA MK61_ENABLE_SPI1_ARBITER
#endif
#ifndef MK61_SPI1_DMA_THRESHOLD
  #define MK61_SPI1_DMA_THRESHOLD 64
#endif

#if defined(MK61_BUILD_FOCAL_MODULE) || \
    defined(MK61_BUILD_TINYBASIC_MODULE) || \
    defined(MK61_BUILD_WBMP_MODULE) || \
    defined(MK61_BUILD_MARKDOWN_MODULE) || \
    defined(MK61_BUILD_CHIP8_MODULE)
  #define MK61_SPI1_DMA_MODULE_BUILD 1
#else
  #define MK61_SPI1_DMA_MODULE_BUILD 0
#endif

#if MK61_ENABLE_SPI1_DMA && MK61_ENABLE_SPI1_ARBITER && \
    defined(ARDUINO_ARCH_STM32) && defined(__ARM_ARCH_7EM__) && \
    !MK61_SPI1_DMA_MODULE_BUILD && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_SPI1_DMA_SUPPORTED 1
#else
  #define MK61_SPI1_DMA_SUPPORTED 0
#endif

class SPIClass;

namespace spi1_dma {

enum class Result : u8 {
  NOT_USED,
  COMPLETE,
  FAILED,
};

struct Snapshot {
  bool supported;
  u16 threshold;
  u32 transfers;
  u32 bytes;
  u32 wfi_entries;
  u32 polling_fallbacks;
  u32 initialization_failures;
  u32 transfer_failures;
  u32 timeouts;
};

Result transfer(SPIClass* interface, const void* tx_buffer, void* rx_buffer,
                usize count);
Snapshot statistics(void);
void reset_statistics(void);
const char* backend_name(void);

} // namespace spi1_dma

#endif
