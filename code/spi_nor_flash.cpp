#include "spi_nor_flash.hpp"
#include "flash_capacity_probe.hpp"
#include "spi_nor_sfdp.hpp"

#if !defined(PROGRAM_STORE_HOST_TEST)

#include <string.h>

namespace {

static constexpr u8 CMD_READ = 0x03;
static constexpr u8 CMD_READ_4B = 0x13;
static constexpr u8 CMD_PAGE_PROGRAM = 0x02;
static constexpr u8 CMD_PAGE_PROGRAM_4B = 0x12;
static constexpr u8 CMD_WRITE_ENABLE = 0x06;
static constexpr u8 CMD_READ_STATUS = 0x05;
static constexpr u8 CMD_ERASE_4K = 0x20;
static constexpr u8 CMD_JEDEC_ID = 0x9F;
static constexpr u8 CMD_READ_SFDP = 0x5A;
static constexpr u8 CMD_RELEASE_POWER_DOWN = 0xAB;
static constexpr u8 CMD_ENTER_4BYTE = 0xB7;
static constexpr u8 CMD_EXIT_4BYTE = 0xE9;
static constexpr u8 STATUS_BUSY = 0x01;
static constexpr u8 STATUS_WRITE_ENABLE = 0x02;
static bool power_of_two(u32 value) {
  return value != 0 && (value & (value - 1)) == 0;
}

} // namespace

SpiNorFlash::SpiNorFlash(u8 chip_select, SPIClass* interface)
    : chip_select_(chip_select), spi_(interface),
      settings_(CLOCK_HZ, MSBFIRST, SPI_MODE0), capacity_(0),
      probe_upper_(0), jedec_id_(0), erase_opcode_(CMD_ERASE_4K),
      erase_opcode_4b_(0x21),
      address_mode_method_(spi_nor_sfdp::EN4B_EX4B),
      page_size_(MAX_PROGRAM_CHUNK), four_byte_address_(false),
      four_byte_opcodes_(false),
      sfdp_present_(false) {}

void SpiNorFlash::select(void) {
  spi_->beginTransaction(settings_);
  digitalWrite(chip_select_, LOW);
}

void SpiNorFlash::deselect(void) {
  digitalWrite(chip_select_, HIGH);
  spi_->endTransaction();
}

u8 SpiNorFlash::transfer(u8 value) { return spi_->transfer(value); }

void SpiNorFlash::sendAddress(u32 address) {
  if(four_byte_address_) transfer((u8) (address >> 24));
  transfer((u8) (address >> 16));
  transfer((u8) (address >> 8));
  transfer((u8) address);
}

u8 SpiNorFlash::readStatus(void) {
  select();
  transfer(CMD_READ_STATUS);
  const u8 status = transfer(0xFF);
  deselect();
  return status;
}

bool SpiNorFlash::waitReady(u32 timeout_ms) {
  const u32 started = millis();
  while((readStatus() & STATUS_BUSY) != 0) {
    if((u32) (millis() - started) >= timeout_ms) return false;
    delayMicroseconds(50);
  }
  return true;
}

bool SpiNorFlash::writeEnable(void) {
  if(!waitReady(5000)) return false;
  select();
  transfer(CMD_WRITE_ENABLE);
  deselect();
  return (readStatus() & STATUS_WRITE_ENABLE) != 0;
}

bool SpiNorFlash::sendAddressModeCommand(bool four_byte) {
  if(address_mode_method_ == spi_nor_sfdp::UNSUPPORTED) return false;
  if(!waitReady(5000)) return false;
  if(address_mode_method_ == spi_nor_sfdp::WREN_EN4B_EX4B && !writeEnable()) {
    return false;
  }
  select();
  transfer(four_byte ? CMD_ENTER_4BYTE : CMD_EXIT_4BYTE);
  deselect();
  delayMicroseconds(2);
  return waitReady(5000);
}

bool SpiNorFlash::setAddressWidth(bool four_byte) {
  if(four_byte_address_ == four_byte) return true;
  if(!four_byte_opcodes_) {
    if(!sendAddressModeCommand(four_byte)) return false;
  } else if(!four_byte &&
            address_mode_method_ != spi_nor_sfdp::UNSUPPORTED) {
    // Dedicated 4-byte opcodes are stateless. Still leave a chip inherited
    // from older firmware in ordinary 3-byte mode before using legacy opcodes.
    if(!sendAddressModeCommand(false)) return false;
  }
  four_byte_address_ = four_byte;
  return true;
}

bool SpiNorFlash::readJedec(void) {
  select();
  transfer(CMD_JEDEC_ID);
  const u8 manufacturer = transfer(0xFF);
  const u8 memory_type = transfer(0xFF);
  const u8 capacity_code = transfer(0xFF);
  deselect();
  if(manufacturer == 0 || manufacturer == 0xFF ||
     (memory_type == 0 && capacity_code == 0)) return false;
  jedec_id_ = ((u32) manufacturer << 16) |
              ((u32) memory_type << 8) | capacity_code;
  return true;
}

bool SpiNorFlash::readSfdp(u32 address, u8* output, usize len) {
  if(output == NULL) return false;
  select();
  transfer(CMD_READ_SFDP);
  transfer((u8) (address >> 16));
  transfer((u8) (address >> 8));
  transfer((u8) address);
  transfer(0xFF);
  for(usize i = 0; i < len; i++) output[i] = transfer(0xFF);
  deselect();
  return true;
}

bool SpiNorFlash::discoverSfdp(u32& capacity) {
  capacity = 0;
  u8 header[8];
  if(!readSfdp(0, header, sizeof(header)) || memcmp(header, "SFDP", 4) != 0 ||
     header[5] != 1 || header[7] != 0xFF) {
    return false;
  }
  sfdp_present_ = true;
  const u8 parameter_count = header[6] < 31 ? (u8) (header[6] + 1) : 32;
  u32 bfpt_address = 0;
  u32 four_bait_address = 0;
  u8 bfpt_dwords = 0;
  u8 bfpt_minor = 0;
  u8 four_bait_dwords = 0;
  u8 four_bait_minor = 0;
  for(u8 parameter = 0; parameter < parameter_count; parameter++) {
    u8 descriptor[8];
    if(!readSfdp(8 + (u32) parameter * 8, descriptor,
                 sizeof(descriptor))) return false;
    if(descriptor[2] != 1) continue;
    const u32 table_address = (u32) descriptor[4] |
                              ((u32) descriptor[5] << 8) |
                              ((u32) descriptor[6] << 16);
    const u16 parameter_id = ((u16) descriptor[7] << 8) | descriptor[0];
    if(parameter_id == 0xFF00 && descriptor[3] >= 2 &&
       (bfpt_dwords == 0 || descriptor[1] >= bfpt_minor)) {
      bfpt_address = table_address;
      bfpt_dwords = descriptor[3];
      bfpt_minor = descriptor[1];
    } else if(parameter_id == 0xFF84 && descriptor[3] >= 2 &&
              (four_bait_dwords == 0 || descriptor[1] >= four_bait_minor)) {
      four_bait_address = table_address;
      four_bait_dwords = descriptor[3];
      four_bait_minor = descriptor[1];
    }
  }
  if(bfpt_dwords == 0) return false;

  const u8 dwords = bfpt_dwords > 16 ? 16 : bfpt_dwords;
  u8 table[64];
  if(!readSfdp(bfpt_address, table, (usize) dwords * 4)) return false;
  spi_nor_sfdp::BasicParameters parameters;
  if(!spi_nor_sfdp::parse_basic(table, dwords, MIN_CAPACITY, MAX_CAPACITY,
                                parameters)) return false;
  capacity = parameters.capacity_bytes;
  page_size_ = parameters.page_size;
  erase_opcode_ = parameters.erase_opcode;
  address_mode_method_ = (u8) parameters.address_mode;

  if(four_bait_dwords >= 2 && parameters.erase_type_4k < 4) {
    u8 four_bait[8];
    if(!readSfdp(four_bait_address, four_bait, sizeof(four_bait))) {
      return false;
    }
    u8 erase4 = 0;
    if(spi_nor_sfdp::parse_4bait(four_bait, parameters.erase_type_4k,
                                 erase4)) {
      erase_opcode_4b_ = erase4;
      four_byte_opcodes_ = true;
    }
  }
  return true;
}

u32 SpiNorFlash::jedecCapacity(u8 capacity_code) {
  return flash_capacity_probe::jedec_capacity_bytes(capacity_code);
}

bool SpiNorFlash::validCapacity(u32 capacity) {
  return capacity >= MIN_CAPACITY && capacity <= MAX_CAPACITY &&
         power_of_two(capacity) && capacity % SECTOR_SIZE == 0;
}

bool SpiNorFlash::begin(u32 fallback_capacity) {
  pinMode(chip_select_, OUTPUT);
  digitalWrite(chip_select_, HIGH);
  spi_->begin();
  select();
  transfer(CMD_RELEASE_POWER_DOWN);
  deselect();
  // Covers the longer tRES1 values found in low-power serial NOR families.
  delayMicroseconds(50);
  if(!readJedec()) return false;

  u32 sfdp_capacity = 0;
  const bool has_sfdp_capacity = discoverSfdp(sfdp_capacity);
  const u32 jedec_capacity = jedecCapacity((u8) jedec_id_);
  const bool has_jedec_capacity = validCapacity(jedec_capacity);
  const bool has_fallback = validCapacity(fallback_capacity);

  if(has_sfdp_capacity && has_jedec_capacity) {
    probe_upper_ = sfdp_capacity > jedec_capacity
        ? sfdp_capacity : jedec_capacity;
  } else if(has_sfdp_capacity) {
    probe_upper_ = sfdp_capacity;
  } else if(has_jedec_capacity) {
    probe_upper_ = jedec_capacity;
  } else if(has_fallback) {
    probe_upper_ = fallback_capacity;
  } else {
    probe_upper_ = MAX_CAPACITY;
  }
  // Force a known three-byte baseline after SFDP has told us whether EX4B
  // needs WREN. RDSFDP itself always uses three address bytes.
  four_byte_address_ = true;
  if(address_mode_method_ == spi_nor_sfdp::UNSUPPORTED) {
    // A device with only dedicated 4-byte opcodes has no state to exit. For an
    // unknown strategy, stay conservatively below the 3-byte boundary.
    four_byte_address_ = false;
  } else if(!setAddressWidth(false)) {
    return false;
  }
  // Locator reads need only sector zero. The physical probe or a valid C5
  // locator will select the authoritative capacity afterwards.
  capacity_ = MIN_CAPACITY;
  return rawPrepare(MIN_CAPACITY);
}

bool SpiNorFlash::setCapacity(u32 capacity) {
  // JEDEC/SFDP may be counterfeit or simply mangled. The destructive probe,
  // not the reported density, is authoritative for an unformatted device.
  if(!validCapacity(capacity) || !rawPrepare(capacity)) return false;
  capacity_ = capacity;
  return true;
}

bool SpiNorFlash::rawPrepare(u32 candidate_capacity) {
  return validCapacity(candidate_capacity) &&
         setAddressWidth(candidate_capacity > 16U * 1024U * 1024U);
}

bool SpiNorFlash::rawRead(u32 address, u8* output, usize len) {
  if(output == NULL) return false;
  if(!waitReady(5000)) return false;
  select();
  transfer(four_byte_address_ && four_byte_opcodes_ ? CMD_READ_4B : CMD_READ);
  sendAddress(address);
  // SPIClass::transfer(byte) enters the STM32 HAL once per byte.  A virtual
  // FAT sector would therefore cross that relatively expensive boundary 512
  // times.  The buffer overload performs the same clocking in one HAL call
  // and supplies the standard 0xFF dummy transmit bytes when tx_buf is NULL.
  if(len != 0) spi_->transfer((const void*) NULL, output, len);
  deselect();
  return true;
}

bool SpiNorFlash::readByteArray(u32 address, u8* output, usize len,
                                bool fast_read) {
  (void) fast_read;
  if(output == NULL || address > capacity_ || len > capacity_ - address) {
    return false;
  }
  return rawRead(address, output, len);
}

u8 SpiNorFlash::readByte(u32 address, bool fast_read) {
  u8 value = 0xFF;
  (void) readByteArray(address, &value, 1, fast_read);
  return value;
}

bool SpiNorFlash::rawWrite(u32 address, const u8* data, usize len) {
  if(data == NULL) return false;
  while(len != 0) {
    const u16 page_room = (u16) (page_size_ - address % page_size_);
    const u16 count = (u16) (len < page_room ? len : page_room);
    if(!writeEnable()) return false;
    select();
    transfer(four_byte_address_ && four_byte_opcodes_
        ? CMD_PAGE_PROGRAM_4B : CMD_PAGE_PROGRAM);
    sendAddress(address);
    // Program one complete NOR page fragment per HAL transaction.  Besides
    // being much faster than byte-at-a-time transfer, this preserves the page
    // boundary required by every SPI NOR page-program command.
    spi_->transfer((const void*) data, (void*) NULL, count);
    deselect();
    if(!waitReady(5000)) return false;
    address += count;
    data += count;
    len -= count;
  }
  return true;
}

bool SpiNorFlash::verifyBytes(u32 address, const u8* expected, usize len) {
  if(expected == NULL || !waitReady(5000)) return false;

  // Keep chip select asserted for the entire comparison.  A sector-sized
  // stack buffer verifies the common 512-byte write with one HAL transfer;
  // larger writes remain bounded and are compared sector by sector.
  u8 recovered[512];
  select();
  transfer(four_byte_address_ && four_byte_opcodes_ ? CMD_READ_4B : CMD_READ);
  sendAddress(address);
  usize offset = 0;
  while(offset < len) {
    const u16 count = (u16) (len - offset < sizeof(recovered)
        ? len - offset : sizeof(recovered));
    spi_->transfer((const void*) NULL, recovered, count);
    if(memcmp(recovered, expected + offset, count) != 0) {
      deselect();
      return false;
    }
    offset += count;
  }
  deselect();
  return true;
}

bool SpiNorFlash::writeByteArray(u32 address, u8* data, usize len,
                                 bool verify) {
  if(data == NULL || address > capacity_ || len > capacity_ - address ||
     !rawWrite(address, data, len)) return false;
  return !verify || verifyBytes(address, data, len);
}

bool SpiNorFlash::writeByte(u32 address, u8 value, bool verify) {
  return writeByteArray(address, &value, 1, verify);
}

bool SpiNorFlash::rawEraseSector(u32 address) {
  if(!writeEnable()) return false;
  select();
  transfer(four_byte_address_ && four_byte_opcodes_
      ? erase_opcode_4b_ : erase_opcode_);
  sendAddress(address & ~(SECTOR_SIZE - 1));
  deselect();
  return waitReady(5000);
}

bool SpiNorFlash::eraseSector(u32 address) {
  return address < capacity_ && rawEraseSector(address);
}

#endif // !PROGRAM_STORE_HOST_TEST
