#include "crc32.hpp"
#include "zx0.hpp"
#include "zx0.h"
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
int main(int argc, char** argv) {
  if(argc != 3) {
    std::fprintf(stderr, "Usage: mk61_program_pack raw-image.bin program.bin\n");
    return 1;
  }
  std::ifstream in(argv[1], std::ios::binary);
  if(!in) return 2;
  std::vector<u8> data{std::istreambuf_iterator<char>(in), {}};
  if(data.empty() || data.size() > 32U * 112U) return 2;

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
  for(unsigned shift = 0; shift < 32; shift += 8) out.put(char(crc >> shift));
  out.write(reinterpret_cast<const char*>(compressed), size);
  std::free(compressed);
  out.close();
  if(!out) return 5;
  std::printf("%zu program bytes -> %d binary bytes; CRC32 %08lX\n", data.size(), size + 4, (unsigned long) crc);
}
