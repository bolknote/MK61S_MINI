#ifndef MK61_PICOCALC_FIRMWARE_HPP
#define MK61_PICOCALC_FIRMWARE_HPP
#include "resident_firmware_format.hpp"
namespace picocalc::firmware {
constexpr u32 IMAGE_START=0x10000000, FLASH_CAPACITY=2*1024*1024-8192;
constexpr u32 PROFILE_ID=0x50434831; // PicoCalc / Pico H, revision 1.
struct Result {
  resident_firmware_format::Status status=resident_firmware_format::Status::BAD_RANGE;
  u32 expected=0,actual=0,image_size=0,footer_offset=0,elapsed_us=0;
};
Result verify_image(const u8* image,u32 size,u32 footer_offset);
#if defined(PICO_ON_DEVICE)
Result verify();
void enforce();
unsigned report(char* out,unsigned capacity,bool recheck=false);
#endif
}
#endif
