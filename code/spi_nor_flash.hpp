#ifndef MK61_SPI_NOR_FLASH_HPP
#define MK61_SPI_NOR_FLASH_HPP

#include "rust_types.h"

#if defined(PROGRAM_STORE_HOST_TEST)

#include <SPIFlash.h>
using SpiNorFlash = SPIFlash;

#else

#include <Arduino.h>
#include <SPI.h>

// Small SFDP-driven SPI NOR driver used by C5. It deliberately avoids trusting
// a part-number table and exposes raw aliasing access only for the one-time
// destructive capacity probe on an unformatted chip.
class SpiNorFlash {
  public:
    static constexpr u32 MIN_CAPACITY = 128U * 1024U;
    static constexpr u32 MAX_CAPACITY = 128U * 1024U * 1024U;
    static constexpr u32 SECTOR_SIZE = 4096;

    explicit SpiNorFlash(u8 chip_select, SPIClass* interface = &SPI);

    bool begin(u32 fallback_capacity = 0);
    u32 getCapacity(void) const { return capacity_; }
    u32 getJEDECID(void) const { return jedec_id_; }
    bool sfdpPresent(void) const { return sfdp_present_; }
    u32 capacityProbeUpper(void) const { return probe_upper_; }
    bool setCapacity(u32 capacity);

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
    static constexpr u32 CLOCK_HZ = 20000000UL;

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

    void select(void);
    void deselect(void);
    u8 transfer(u8 value);
    void sendAddress(u32 address);
    u8 readStatus(void);
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

#endif // PROGRAM_STORE_HOST_TEST

#endif
