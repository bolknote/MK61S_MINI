#include "loadable_module_format.hpp"
#include "arm_thumb_bcj.hpp"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

using namespace loadable_module;

static std::vector<u8> read_file(const char* name) {
  std::ifstream input(name, std::ios::binary);
  assert(input.good());
  return {std::istreambuf_iterator<char>(input), {}};
}

static bool read_bytes(void* context, u32 offset, u8* out, usize length) {
  const auto& data = *(const std::vector<u8>*) context;
  if(offset > data.size() || length > data.size() - offset) return false;
  std::memcpy(out, data.data() + offset, length);
  return true;
}

static void bcj_checks() {
  // XZ ARM-Thumb, start offset zero. The second BL is at file offset 4.
  u8 bytes[] = {0, 0xF0, 0, 0xF8, 0, 0xF0, 0, 0xF8, 0xCD};
  const u8 expected[] = {0, 0xF0, 2, 0xF8, 0, 0xF0, 4, 0xF8, 0xCD};
  arm_thumb_bcj::transform(bytes, sizeof(bytes), true);
  assert(std::memcmp(bytes, expected, sizeof(bytes)) == 0);
  arm_thumb_bcj::transform(bytes, sizeof(bytes), false);
  assert(bytes[2] == 0 && bytes[6] == 0 && bytes[8] == 0xCD);

  u32 state = 0x42434A31;
  auto next = [&]() { state ^= state << 13; state ^= state >> 17;
                      state ^= state << 5; return state; };
  for(u32 trial = 0; trial < 4096; ++trial) {
    const u32 size = trial < 16 ? trial : next() % 20481;
    std::vector<u8> original(size), guarded(size + 16, 0xCD);
    for(u8& byte : original) byte = (u8) next();
    // Include many matching pairs, wraparound addresses, adjacent matches,
    // odd tails and literal-data false positives, with canaries on both sides.
    for(u32 i = 0; i + 3 < size; i += 6) {
      original[i + 1] = (u8) (0xF0 | (next() & 7));
      original[i + 3] = (u8) (0xF8 | (next() & 7));
    }
    std::copy(original.begin(), original.end(), guarded.begin() + 8);
    arm_thumb_bcj::transform(guarded.data() + 8, size, true);
    arm_thumb_bcj::transform(guarded.data() + 8, size, false);
    assert(std::equal(original.begin(), original.end(), guarded.begin() + 8));
    for(u32 i = 0; i < 8; ++i) {
      assert(guarded[i] == 0xCD && guarded[size + 8 + i] == 0xCD);
    }
  }
}

static void header_checks() {
  Header header{};
  header.kind = Kind::APPLICATION;
  header.compression = Compression::ZX0;
  header.flags = MK61_PORTABLE_APP_FLAG;
  header.load_address = MK61_PORTABLE_APP_ADDRESS;
  header.stored_size = 12; header.image_size = 32; header.memory_size = 40;
  u8 encoded[HEADER_SIZE];
  assert(encode_header(header, MAX_CONTAINER_SIZE, encoded));
  assert(encoded[12] == MK61_PORTABLE_APP_ABI);
  Header decoded{};
  assert(decode_header(encoded, MAX_CONTAINER_SIZE, decoded) == HeaderStatus::OK);
  assert(decoded.resident_size == 0 && decoded.resident_crc32 == 0);
  for(u8 index = 0; index < KIND_COUNT; ++index) {
    Header system = header; system.kind = kind_at(index);
    assert(encode_header(system, MAX_CONTAINER_SIZE, encoded));
    assert(decode_header(encoded, MAX_CONTAINER_SIZE, system.kind, decoded) == HeaderStatus::OK);
    assert(decoded.kind == system.kind && decoded.flags == MK61_PORTABLE_APP_FLAG);
  }
  for(u32 flags : {0U, 2U, 4U, 5U, 7U, 0xFFFFFFFFU}) {
    Header bad = header; bad.flags = flags;
    assert(!encode_header(bad, MAX_CONTAINER_SIZE, encoded));
  }
  header.flags |= MK61_APP_ARM_THUMB_BCJ_FLAG;
  assert(encode_header(header, MAX_CONTAINER_SIZE, encoded));
  for(u32 field = 0; field < 7; ++field) {
    Header bad = header;
    switch(field) {
      case 0: bad.load_address += 8; break;
      case 1: bad.resident_size = 1; break;
      case 2: bad.resident_crc32 = 1; break;
      case 3: bad.kind = (Kind) 0xFF; break;
      case 4: bad.compression = Compression::NONE; break;
      case 5: bad.memory_size = OVERLAY_SIZE + 1; break;
      case 6: bad.entry_offset = bad.image_size; break;
    }
    assert(!encode_header(bad, MAX_CONTAINER_SIZE, encoded));
  }
}

int main(int argc, char** argv) {
  if(argc == 1) {
    bcj_checks(); header_checks();
    std::puts("portable APP format: header checks and 4096 BCJ round-trips PASS");
    return 0;
  }
  // This mode is also used before the ARM emulator: execute only bytes which
  // passed the production header, ZX0, inverse BCJ and original-image CRC.
  if(argc != 3 && argc != 4) return 2;
  const auto bytes = read_file(argv[1]);
  Header header{};
  if(bytes.size() < HEADER_SIZE ||
     decode_header(bytes.data(), MAX_CONTAINER_SIZE, header) != HeaderStatus::OK ||
     bytes.size() != HEADER_SIZE + header.stored_size) return 3;
  std::vector<u8> payload(bytes.begin() + HEADER_SIZE, bytes.end());
  std::vector<u8> memory(header.memory_size + 16, 0xCD);
  const u32 address = argc == 4 ? (u32) std::strtoul(argv[3], nullptr, 0) : header.load_address;
  const bool decoded = decode_image(header, {&payload, read_bytes}, memory.data() + 8, address);
  for(u32 i = 0; i < 8; ++i)
    assert(memory[i] == 0xCD && memory[header.memory_size + 8 + i] == 0xCD);
  if(!decoded) return 4;
  for(u32 i = 0; i < 8; ++i)
    assert(memory[i] == 0xCD && memory[header.memory_size + 8 + i] == 0xCD);
  for(u32 i = header.image_size; i < header.memory_size; ++i)
    assert(memory[i + 8] == 0xCD);
  std::memset(memory.data() + 8 + header.image_size, 0,
              header.memory_size - header.image_size);
  std::ofstream out(argv[2], std::ios::binary);
  out.write((const char*) memory.data() + 8, header.memory_size);
  return out.good() ? 0 : 5;
}
