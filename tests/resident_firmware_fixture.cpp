#include "../code/resident_firmware_format.hpp"

#include <fstream>
#include <string.h>
#include <vector>

int main(int argc, char** argv) {
  if(argc != 2) return 2;
  std::vector<u8> image(512);
  for(usize index = 0; index < image.size(); index++)
    image[index] = (u8) ((index * 29U + 7U) & 0xFFU);

  resident_firmware_format::Footer footer = {};
  memcpy(footer.magic, resident_firmware_format::MAGIC,
         sizeof(footer.magic));
  footer.version = resident_firmware_format::VERSION;
  footer.size = sizeof(footer);
  footer.image_start = resident_firmware_format::IMAGE_START;
  footer.build_id = 0x12345678UL;
  footer.profile_id = 0x89ABCDEFUL;
  footer.flags = resident_firmware_format::FLAG_CRC_REQUIRED;
  memcpy(image.data() + 128, &footer, sizeof(footer));

  std::ofstream output(argv[1], std::ios::binary | std::ios::trunc);
  output.write(reinterpret_cast<const char*>(image.data()),
               (std::streamsize) image.size());
  return output ? 0 : 1;
}
