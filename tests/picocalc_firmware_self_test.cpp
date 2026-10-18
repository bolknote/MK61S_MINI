#include "firmware.hpp"
#include "crc32.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
void picocalc_firmware_test() {
  using namespace picocalc::firmware;
  using resident_firmware_format::Footer;
  using resident_firmware_format::Status;
  u8 image[4096];for(unsigned i=0;i<sizeof(image);++i) image[i]=(u8)(i*7);
  constexpr unsigned offset=2048;
  Footer footer{{'M','K','6','1','F','W','C',0},1,40,IMAGE_START,sizeof(image),0,0,PROFILE_ID,1,0};
  std::memcpy(image+offset,&footer,sizeof(footer));
  footer.build_id=footer.expected_crc32=mk61_crc32::calculate(image,sizeof(image));
  std::memcpy(image+offset,&footer,sizeof(footer));
  auto result=verify_image(image,sizeof(image),offset);
  assert(result.status==Status::VALID && result.actual==footer.expected_crc32);
  image[257]^=1;assert(verify_image(image,sizeof(image),offset).status==Status::CRC_MISMATCH);image[257]^=1;
  for(unsigned word:{0U,8U,10U,12U,16U,20U,24U,28U,32U,36U}) {
    image[offset+word]^=1;assert(verify_image(image,sizeof(image),offset).status!=Status::VALID);image[offset+word]^=1;
  }
  assert(verify_image(image,sizeof(image)-1,offset).status==Status::BAD_RANGE);
  assert(verify_image(image,sizeof(image),sizeof(image)-4).status==Status::BAD_RANGE);
  assert(verify_image(nullptr,4096,offset).status==Status::BAD_RANGE);
  assert(verify_image(image,FLASH_CAPACITY+1,offset).status==Status::BAD_RANGE);
  assert(verify_image(image,sizeof(image),offset).status==Status::VALID);
  std::puts("PicoCalc firmware guard: shared metadata/CRC, full image corruption, ranges and required profile PASS");
}
