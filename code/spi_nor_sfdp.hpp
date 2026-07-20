#ifndef MK61_SPI_NOR_SFDP_HPP
#define MK61_SPI_NOR_SFDP_HPP

#include "rust_types.h"

namespace spi_nor_sfdp {

enum AddressModeMethod : u8 {
  EN4B_EX4B = 0,
  WREN_EN4B_EX4B = 1,
  UNSUPPORTED = 2
};

struct BasicParameters {
  u32 capacity_bytes;
  u16 page_size;
  u8 erase_opcode;
  u8 erase_type_4k;
  AddressModeMethod address_mode;
};

inline u32 read_le32(const u8* data) {
  return (u32) data[0] | ((u32) data[1] << 8) |
         ((u32) data[2] << 16) | ((u32) data[3] << 24);
}

inline bool power_of_two(u32 value) {
  return value != 0 && (value & (value - 1)) == 0;
}

inline bool parse_basic(const u8* table, u8 dwords,
                        u32 minimum_capacity, u32 maximum_capacity,
                        BasicParameters& output) {
  if(table == 0 || dwords < 2) return false;

  const u32 density = read_le32(table + 4);
  u64 bits = 0;
  if((density & 0x80000000UL) == 0) {
    bits = (u64) density + 1;
  } else {
    const u32 exponent = density & 0x7FFFFFFFUL;
    if(exponent >= 63) return false;
    bits = (u64) 1 << exponent;
  }
  const u64 bytes = (bits + 7) / 8;
  if(bytes < minimum_capacity || bytes > maximum_capacity ||
     !power_of_two((u32) bytes)) return false;

  output.capacity_bytes = (u32) bytes;
  output.page_size = 256;
  output.erase_opcode = 0x20;
  output.erase_type_4k = 0xFF;
  output.address_mode = EN4B_EX4B;

  if(dwords >= 9) {
    for(u8 erase_type = 0; erase_type < 4; erase_type++) {
      const u8 pair = (u8) (28 + erase_type * 2);
      const u8 exponent = table[pair];
      const u8 opcode = table[pair + 1];
      if(exponent == 12 && opcode != 0 && opcode != 0xFF) {
        output.erase_opcode = opcode;
        output.erase_type_4k = erase_type;
        break;
      }
    }
  }

  if(dwords >= 11) {
    const u8 page_exponent = (u8) ((read_le32(table + 40) >> 4) & 0x0F);
    // Фрагменты меньше физической страницы всегда безопасны. C5 намеренно
    // ограничивает фрагмент 256 байтами, даже если устройство сообщает
    // о странице большего размера.
    if(page_exponent < 8) output.page_size = (u16) 1U << page_exponent;
  }

  if(dwords >= 16) {
    const u32 methods = read_le32(table + 60);
    const u32 wren_method = (1UL << 25) | (1UL << 15);
    const u32 plain_method = (1UL << 24) | (1UL << 14);
    if((methods & wren_method) == wren_method) {
      output.address_mode = WREN_EN4B_EX4B;
    } else if((methods & plain_method) == plain_method) {
      output.address_mode = EN4B_EX4B;
    } else {
      output.address_mode = UNSUPPORTED;
    }
  }
  return true;
}

inline bool parse_4bait(const u8* table, u8 erase_type_4k,
                        u8& erase_opcode_4b) {
  if(table == 0 || erase_type_4k >= 4) return false;
  const u32 supported = read_le32(table);
  const u8 erase_opcode = table[4 + erase_type_4k];
  if((supported & (1UL << 0)) == 0 ||
     (supported & (1UL << 6)) == 0 ||
     (supported & (1UL << (9 + erase_type_4k))) == 0 ||
     erase_opcode == 0 || erase_opcode == 0xFF) return false;
  erase_opcode_4b = erase_opcode;
  return true;
}

} // пространство имён spi_nor_sfdp

#endif
