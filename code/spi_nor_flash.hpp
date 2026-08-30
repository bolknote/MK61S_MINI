#ifndef MK61_SPI_NOR_FLASH_HPP
#define MK61_SPI_NOR_FLASH_HPP

#include "rust_types.h"

#if defined(PROGRAM_STORE_HOST_TEST)

#include <SPIFlash.h>
using SpiNorFlash = SPIFlash;

#else

#include <Arduino.h>
#include <SPI.h>

#ifndef MK61_SPI_NOR_CLOCK_HZ
  // На F411 запрос 20 МГц округлялся вниз до PCLK2/8 = 12 МГц. Ступень
  // 24 МГц (PCLK2/4) выбрана после HIL-сравнения с верхней 48-МГц ступенью;
  // на F401 тот же запрос даёт безопасные 21 МГц от PCLK2=84 МГц.
  #define MK61_SPI_NOR_CLOCK_HZ 24000000UL
#endif
#if MK61_SPI_NOR_CLOCK_HZ < 100000UL
  #error "MK61_SPI_NOR_CLOCK_HZ is implausibly low"
#endif
#if MK61_SPI_NOR_CLOCK_HZ > 48000000UL
  #error "MK61_SPI_NOR_CLOCK_HZ exceeds the qualified STM32F4 range"
#endif

// Компактный драйвер SPI NOR на основе SFDP, используемый C5. Он намеренно
// не доверяет таблице моделей и открывает низкоуровневый доступ с возможными
// адресами-псевдонимами только для однократной разрушающей проверки ёмкости
// неформатированной микросхемы.
class SpiNorFlash {
  public:
    static constexpr u32 MIN_CAPACITY = 128U * 1024U;
    static constexpr u32 MAX_CAPACITY = 128U * 1024U * 1024U;
    static constexpr u32 SECTOR_SIZE = 4096;

    struct Diagnostics {
      u32 jedec_id;
      u32 capacity_bytes;
      u32 probe_upper_bytes;
      u32 requested_clock_hz;
      u32 peripheral_clock_hz;
      u32 actual_clock_hz;
      u16 page_size;
      u16 prescaler;
      u8 status[3];
      u8 status_count;
      u8 erase_opcode;
      bool sfdp_present;
      bool four_byte_address;
      bool four_byte_opcodes;
    };

    explicit SpiNorFlash(u8 chip_select, SPIClass* interface = &SPI);

    bool begin(u32 fallback_capacity = 0);
    u32 getCapacity(void) const { return capacity_; }
    u32 getJEDECID(void) const { return jedec_id_; }
    bool sfdpPresent(void) const { return sfdp_present_; }
    u32 capacityProbeUpper(void) const { return probe_upper_; }
    bool setCapacity(u32 capacity);
    bool diagnostics(Diagnostics& out);

    u8 readByte(u32 address, bool fast_read = false);
    bool readByteArray(u32 address, u8* output, usize len,
                       bool fast_read = false);
    bool writeByte(u32 address, u8 value, bool verify = true);
    bool writeByteArray(u32 address, u8* data, usize len,
                        bool verify = true);
    bool eraseSector(u32 address);

    bool rawPrepare(u32 candidate_capacity);
    bool rawRead(u32 address, u8* output, usize len);
    bool rawWrite(u32 address, const u8* data, usize len);
    bool rawEraseSector(u32 address);

  private:
    static constexpr u16 MAX_PROGRAM_CHUNK = 256;
    static constexpr u32 CLOCK_HZ = MK61_SPI_NOR_CLOCK_HZ;

    u8 chip_select_;
    SPIClass* spi_;
    SPISettings settings_;
    u32 capacity_;
    u32 probe_upper_;
    u32 jedec_id_;
    u8 erase_opcode_;
    u8 erase_opcode_4b_;
    u8 address_mode_method_;
    u16 page_size_;
    bool four_byte_address_;
    bool four_byte_opcodes_;
    bool sfdp_present_;

    bool select(void);
    bool deselect(void);
    u8 transfer(u8 value);
    bool transferBuffer(const void* tx_buffer, void* rx_buffer, usize len);
    void sendAddress(u32 address);
    bool readRegister(u8 opcode, u8& value);
    bool readStatus(u8& status);
    bool waitReady(u32 timeout_ms);
    bool writeEnable(void);
    bool sendAddressModeCommand(bool four_byte);
    bool setAddressWidth(bool four_byte);
    bool readJedec(void);
    bool readSfdp(u32 address, u8* output, usize len);
    bool verifyBytes(u32 address, const u8* expected, usize len);
    bool discoverSfdp(u32& capacity);
    static u32 jedecCapacity(u8 capacity_code);
    static bool validCapacity(u32 capacity);
};

extern SpiNorFlash* external_flash_pointer;
static inline SpiNorFlash& external_flash(void) {
  return *external_flash_pointer;
}

#endif // PROGRAM_STORE_HOST_TEST

#endif
