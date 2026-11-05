#ifndef MK61_SPECTRUM_ROM_CACHE_H
#define MK61_SPECTRUM_ROM_CACHE_H
#include <stdint.h>
#include <stdbool.h>
/* Optional immutable asset pack, outside the sealed firmware and settings.
 * No executable code is installed here. A bad/missing pack uses SD + SRAM. */
#define SPECTRUM_ROM_CACHE_ADDRESS 0x101C0000U
#define SPECTRUM_ROM_CACHE_CAPACITY 131072U
enum { SPECTRUM_ROM_48,SPECTRUM_ROM_128_0,SPECTRUM_ROM_128_1,SPECTRUM_ROM_BETA,SPECTRUM_ROM_DIV,SPECTRUM_ROM_COUNT };
uint32_t spectrum_crc32(uint32_t crc,const uint8_t*,unsigned bytes);
bool spectrum_rom_cache_valid(const uint8_t*,unsigned capacity);
const uint8_t* spectrum_rom_cache_find(unsigned id,uint32_t* crc);
#endif
