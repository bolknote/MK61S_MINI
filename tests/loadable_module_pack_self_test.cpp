#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "../code/loadable_module_format.hpp"

using namespace loadable_module;

namespace {

static std::vector<u8> read_file(const char* path) {
  FILE* input = fopen(path, "rb");
  assert(input != nullptr);
  assert(fseek(input, 0, SEEK_END) == 0);
  const long size = ftell(input);
  assert(size >= 0);
  assert(fseek(input, 0, SEEK_SET) == 0);
  std::vector<u8> result((usize) size);
  assert(result.empty() ||
         fread(result.data(), 1, result.size(), input) == result.size());
  assert(fclose(input) == 0);
  return result;
}

static void write_file(const char* path, const std::vector<u8>& bytes) {
  FILE* output = fopen(path, "wb");
  assert(output != nullptr);
  assert(bytes.empty() ||
         fwrite(bytes.data(), 1, bytes.size(), output) == bytes.size());
  assert(fclose(output) == 0);
}

static void generate_fixtures(const char* resident_path,
                              const char* image_path) {
  std::vector<u8> resident(4097);
  for(usize index = 0; index < resident.size(); index++) {
    resident[index] = (u8) (index * 29U + 7U);
  }
  std::vector<u8> block(113);
  for(usize index = 0; index < block.size(); index++) {
    block[index] = (u8) (index * 13U + index / 7U);
  }
  std::vector<u8> image(10000);
  for(usize index = 0; index < image.size(); index++) {
    image[index] = block[index % block.size()];
  }
  write_file(resident_path, resident);
  write_file(image_path, image);
}

struct VectorReader {
  const std::vector<u8>* bytes;
  u32 base;
};

static bool read_vector(void* context, u32 offset, u8* output, usize size) {
  VectorReader& reader = *(VectorReader*) context;
  const u32 position = reader.base + offset;
  if(output == nullptr || position > reader.bytes->size() ||
     size > reader.bytes->size() - position) return false;
  memcpy(output, reader.bytes->data() + position, size);
  return true;
}

} // namespace

int main(int argc, char** argv) {
  assert(argc == 4);
  if(strcmp(argv[1], "--generate") == 0) {
    generate_fixtures(argv[2], argv[3]);
    return 0;
  }
  const std::vector<u8> module = read_file(argv[1]);
  const std::vector<u8> expected = read_file(argv[2]);
  const std::vector<u8> resident = read_file(argv[3]);
  assert(module.size() >= HEADER_SIZE);
  Header header = {};
  assert(decode_header(module.data(), 16U * 1024U, Kind::FOCAL, header) ==
         HeaderStatus::OK);
  assert(header.compression == Compression::ZX0);
  assert(header.image_size == expected.size());
  assert(header.memory_size == expected.size() + 512);
  assert(header.resident_size == resident.size());
  assert(header.resident_crc32 == crc32(resident.data(), resident.size()));
  assert(module.size() == HEADER_SIZE + header.stored_size);

  VectorReader source = {&module, HEADER_SIZE};
  const Reader reader = {&source, read_vector};
  std::vector<u8> decoded(header.image_size);
  DecodeResult result = {};
  assert(decode_payload(reader, header.compression, header.stored_size,
                        decoded.data(), header.image_size, result));
  assert(result.stored_crc32 == header.stored_crc32);
  assert(result.image_crc32 == header.image_crc32);
  assert(decoded == expected);
  printf("loadable_module_pack_self_test: ok\n");
  return 0;
}
