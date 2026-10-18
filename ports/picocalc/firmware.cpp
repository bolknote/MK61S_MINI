#include "firmware.hpp"
#include "crc32.hpp"
#include <cstdio>
#if defined(PICO_ON_DEVICE)
#include "pico/bootrom.h"
#include "pico/stdlib.h"
#endif
namespace picocalc::firmware {
using resident_firmware_format::Footer;
using resident_firmware_format::Status;
Result verify_image(const u8* image,u32 size,u32 offset) {
  Result result;result.image_size=size;result.footer_offset=offset;
  if(!image || size>FLASH_CAPACITY || offset>size || sizeof(Footer)>size-offset) return result;
  Footer footer{};
  const volatile u8* source=image+offset;
  for(unsigned i=0;i<sizeof(footer);++i) ((u8*)&footer)[i]=source[i];
  result.expected=footer.expected_crc32;
  result.status=resident_firmware_format::validate_metadata(footer,size,offset,PROFILE_ID,FLASH_CAPACITY,IMAGE_START);
  if(result.status!=Status::VALID) return result;
  if(!resident_firmware_format::required(footer)) { result.status=Status::BAD_FLAGS;return result; }
  mk61_crc32::Context crc;
  const u32 first=offset+resident_firmware_format::CRC32_OFFSET;
  const u8 zeros[8]{};
  crc.update(image,first);crc.update(zeros,sizeof(zeros));
  crc.update(image+first+sizeof(zeros),size-first-sizeof(zeros));
  result.actual=crc.finish();
  if(result.expected!=result.actual) result.status=Status::CRC_MISMATCH;
  return result;
}
#if defined(PICO_ON_DEVICE)
namespace {
struct Failure { u32 magic,inverse,status,expected,actual; };
constexpr u32 FAILURE_MAGIC=0x50434657;
__attribute__((section(".uninitialized_data.picocalc_fw"))) Failure failure;
Result boot;
}
extern "C" {
extern const u8 __flash_binary_end[];
__attribute__((used,aligned(4),section(".mk61_fw_footer")))
extern const volatile Footer mk61_picocalc_firmware_footer={
  {'M','K','6','1','F','W','C',0},resident_firmware_format::VERSION,sizeof(Footer),
  IMAGE_START,0,0,0,PROFILE_ID,resident_firmware_format::FLAG_CRC_REQUIRED,0
};
}
Result verify() {
  const u32 start=time_us_32();
  const u32 size=(u32)((uintptr_t)__flash_binary_end-IMAGE_START);
  const u32 offset=(u32)((uintptr_t)&mk61_picocalc_firmware_footer-IMAGE_START);
  Result out=verify_image((const u8*)IMAGE_START,size,offset);
  out.elapsed_us=time_us_32()-start;return out;
}
void enforce() {
  boot=verify();
  if(boot.status==Status::VALID) return;
  failure.magic=0;failure.inverse=~FAILURE_MAGIC;failure.status=(u32)boot.status;
  failure.expected=boot.expected;failure.actual=boot.actual;
  __asm volatile("dmb" ::: "memory");failure.magic=FAILURE_MAGIC;
  // The ROM USB loader is independent of the installed firmware and card.
  reset_usb_boot(0,0);
  for(;;) tight_loop_contents();
}
unsigned report(char* out,unsigned capacity,bool recheck) {
  const Result value=recheck?verify():boot;
  int used=std::snprintf(out,capacity,"FIRMWARE_CRC=%s REQUIRED=1 IMAGE=%lu FOOTER=%lu EXPECTED=%08lX ACTUAL=%08lX CHECK_US=%lu\r\n",
    resident_firmware_format::status_name(value.status),(unsigned long)value.image_size,
    (unsigned long)value.footer_offset,(unsigned long)value.expected,(unsigned long)value.actual,(unsigned long)value.elapsed_us);
  if(used<0 || (unsigned)used>=capacity) return 0;
  if(failure.magic==FAILURE_MAGIC && failure.inverse==~FAILURE_MAGIC && failure.status<=(u32)Status::CRC_MISMATCH) {
    const int n=std::snprintf(out+used,capacity-used,"FIRMWARE_LAST_FAILURE=%s EXPECTED=%08lX ACTUAL=%08lX\r\n",
      resident_firmware_format::status_name((Status)failure.status),(unsigned long)failure.expected,(unsigned long)failure.actual);
    if(n<0 || (unsigned)n>=capacity-used) return 0;
    used+=n;
  }
  return (unsigned)used;
}
#endif
}
