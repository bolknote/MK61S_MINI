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

static void generate_fixture(const char* image_path) {
  std::vector<u8> block(113);
  for(usize index = 0; index < block.size(); index++) {
    block[index] = (u8) (index * 13U + index / 7U);
  }
  std::vector<u8> image(10000);
  for(usize index = 0; index < image.size(); index++) {
    image[index] = block[index % block.size()];
  }
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
  assert(argc == 3 || argc == 4);
  if(strcmp(argv[1], "--generate") == 0) {
    assert(argc == 3);
    generate_fixture(argv[2]);
    return 0;
  }
  const char* expected_type = argc == 4 ? argv[3] : "focal";
  const Kind expected_kind =
      strcmp(expected_type, "app") == 0 ? Kind::APPLICATION :
      strcmp(expected_type, "chip8") == 0 ? Kind::CHIP8 :
      strcmp(expected_type, "markdown") == 0
          ? Kind::MARKDOWN_VIEWER : Kind::FOCAL;
  const u16 expected_magic =
      expected_kind == Kind::CHIP8
          ? (u16) ('C' | ((u16) '1' << 8))
          : expected_kind == Kind::MARKDOWN_VIEWER
              ? (u16) ('T' | ((u16) '2' << 8)) : 0;
  const std::vector<u8> module = read_file(argv[1]);
  const std::vector<u8> expected = read_file(argv[2]);
  assert(module.size() >= HEADER_SIZE);
  Header header = {};
  assert(memcmp(module.data(), "MK61APP", 7) == 0);
  assert(decode_header(module.data(), MAX_CONTAINER_SIZE,
                       expected_kind, header) ==
         HeaderStatus::OK);
  assert(header.compression == Compression::ZX0);
  assert(header.flags == (MK61_PORTABLE_APP_FLAG |
                          MK61_APP_RELOCATABLE_FLAG));
  assert(header.load_address == MK61_PORTABLE_APP_ADDRESS);
  assert(header.image_size == expected.size());
  assert(header.memory_size == expected.size() + 512);
  assert(header.code_stored_size == header.stored_size);
  assert(header.relocation_count == 0);
  assert(header.handled_type_magic == expected_magic);
  assert(module.size() == HEADER_SIZE + header.stored_size);

  VectorReader source = {&module, HEADER_SIZE};
  const Reader reader = {&source, read_vector};
  std::vector<u8> decoded(header.memory_size, 0xCD);
  assert(decode_image(header, reader, decoded.data(),
                      header.load_address));
  decoded.resize(header.image_size);
  assert(decoded == expected);
  printf("loadable_module_pack_self_test: ok\n");
  return 0;
}
