#ifndef MK61_PICOCALC_SD_CRC_HPP
#define MK61_PICOCALC_SD_CRC_HPP
#include "rust_types.h"
#include <array>
namespace picocalc { namespace sd {
constexpr std::array<u16, 256> make_crc16_table() {
    std::array<u16, 256> table{};
    for(unsigned i = 0; i < table.size(); ++i) {
        u16 crc = (u16)(i << 8);
        for(unsigned bit = 0; bit < 8; ++bit) crc = (u16)((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
        table[i] = crc;
    }
    return table;
}
inline u16 crc16(const u8* data, unsigned size) {
    static constexpr auto table = make_crc16_table();
    u16 crc = 0;
    for(unsigned i = 0; i < size; ++i) crc = (u16)((crc << 8) ^ table[(crc >> 8) ^ data[i]]);
    return crc;
}
} }
#endif
