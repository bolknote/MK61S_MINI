#include "base91.hpp"
#include "crc32.hpp"
#include "zx0.hpp"
#include "zx0.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <vector>

struct Reader { const u8* data; usize size, position; };
static bool next(void* context, u8& value) {
  auto& r = *static_cast<Reader*>(context);
  if(r.position == r.size) return false;
  value = r.data[r.position++];
  return true;
}
static bool put(void* context, char value) {
  return bool(static_cast<std::ofstream*>(context)->put(value));
}

int main(int argc, char** argv) {
  if(argc != 3 && argc != 4) {
    std::fprintf(stderr, "Usage: mk61_program_pack input.bin output.m61 [decimal-address]\n");
    return 1;
  }
  char* end = nullptr;
  const long address = argc == 4 ? std::strtol(argv[3], &end, 10) : 0;
  if(address < 0 || address >= 10000 || (argc == 4 && (*argv[3] == 0 || *end != 0))) return 2;
  std::ifstream in(argv[1], std::ios::binary);
  if(!in) return 2;
  std::vector<u8> data{std::istreambuf_iterator<char>(in), {}};
  if(data.empty() || data.size() > usize(10000 - address)) return 2;

  BLOCK* optimal = optimize(data.data(), int(data.size()), 0, 32640);
  int size = 0, delta = 0;
  auto* compressed = compress(optimal, data.data(), int(data.size()), 0, 0, 1, &size, &delta);
  if(compressed == nullptr) return 3;
  Reader r{compressed, usize(size), 0};
  std::vector<u8> check(data.size());
  u32 written = 0;
  if(!zx0::decode({&r, next}, size, check.data(), check.size(), written) || check != data) {
    std::free(compressed);
    return 4;
  }

  std::ofstream out(argv[2], std::ios::binary);
  const u32 crc = mk61_crc32::finish(mk61_crc32::extend(
      mk61_crc32::INITIAL_STATE, data.data(), data.size()));
  char header[32];
  std::snprintf(header, sizeof(header), "ztart %04ld %08lX\n", address, (unsigned long) crc);
  out << header;
  for(int i = 0; i < size; i += 176) {
    out << "zin ";
    if(!base91::encode(compressed + i, std::min(176, size - i), {&out, put})) {
      std::free(compressed);
      return 5;
    }
    out << '\n';
  }
  std::free(compressed);
  out.close();
  if(!out) return 5;
  std::printf("%zu program bytes -> %d ZX0 bytes; CRC32 %08lX\n", data.size(), size, (unsigned long) crc);
}
