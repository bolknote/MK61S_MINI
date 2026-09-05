#include "loadable_module_format.hpp"
#include "zx0.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {
constexpr u32 SEED = 0x4D4B3631;
u32 random_state = SEED;
u32 next_random() {
  random_state ^= random_state << 13;
  random_state ^= random_state >> 17;
  random_state ^= random_state << 5;
  return random_state;
}
struct Source { const std::vector<u8>& bytes; usize position = 0; };
bool next_byte(void* opaque, u8& value) {
  auto& source = *(Source*) opaque;
  if(source.position >= source.bytes.size()) return false;
  value = source.bytes[source.position++];
  return true;
}
bool read_bytes(void* opaque, u32 offset, u8* out, usize size) {
  const auto& bytes = *(const std::vector<u8>*) opaque;
  if(offset > bytes.size() || size > bytes.size() - offset) return false;
  std::memcpy(out, bytes.data() + offset, size);
  return true;
}
bool write_byte(void* opaque, u8 byte) {
  ((std::vector<u8>*) opaque)->push_back(byte); return true;
}
void put32(u8* bytes, u32 value) {
  for(u8 i = 0; i < 4; ++i) { bytes[i] = (u8) value; value >>= 8; }
}
void canaries(const std::vector<u8>& buffer, usize capacity) {
  assert(std::all_of(buffer.begin(), buffer.begin()+8, [](u8 x) { return x == 0xCD; }));
  assert(std::all_of(buffer.begin()+8+capacity, buffer.end(), [](u8 x) { return x == 0xCD; }));
}

void zx_case(const std::vector<u8>& bytes, u32 declared, u32 capacity) {
  std::vector<u8> output(capacity + 16, 0xCD);
  Source source{bytes};
  u32 written = 0;
  const bool ok = zx0::decode({&source, next_byte}, declared, output.data()+8, capacity, written);
  assert(written <= capacity);
  canaries(output, capacity);
  assert(source.position <= bytes.size());
  if(ok) {
    assert(source.position <= declared);
    // A successful contiguous decode is the oracle for production range decode.
    // 512 bytes are enough for every offset in these <=256-byte outputs.
    for(u32 start : {0U, written / 2, written}) {
      const u32 count = written - start;
      std::vector<u8> range(count + 16, 0xCD), window(512 + 16, 0xCD);
      Source again{bytes};
      assert(zx0::decode_range({&again, next_byte}, declared, written, start,
          range.data()+8, count, window.data()+8, 512));
      assert(std::memcmp(range.data()+8, output.data()+8+start, count) == 0);
      canaries(range, count); canaries(window, 512);
    }
  }
}

void app_case(const std::vector<u8>& bytes, u32 slot_size) {
  using namespace loadable_module;
  u8 encoded[HEADER_SIZE];
  // Reader boundary used by the resident before decode_header's fixed-size API.
  if(!read_bytes((void*) &bytes, 0, encoded, HEADER_SIZE)) return;
  Header header{};
  if(decode_header(encoded, slot_size, header) != HeaderStatus::OK) return;
  assert(header.memory_size <= OVERLAY_SIZE);
  assert(header.image_size <= header.memory_size);
  assert(header.entry_offset < header.image_size && (header.entry_offset & 1U) == 0);
  assert(header.load_address >= SRAM_FIRST_ADDRESS && header.load_address <= SRAM_LAST_ADDRESS - OVERLAY_SIZE);
  u8 canonical[HEADER_SIZE];
  assert(encode_header(header, slot_size, canonical));
  assert(std::memcmp(encoded, canonical, HEADER_SIZE) == 0);
  std::vector<u8> payload(bytes.begin()+HEADER_SIZE, bytes.end());
  std::vector<u8> output(header.image_size + 16, 0xCD);
  DecodeResult result{};
  const bool ok = decode_payload({&payload, read_bytes}, header.compression,
      header.stored_size, output.data()+8, header.image_size, result);
  canaries(output, header.image_size);
  if(ok) {
    assert(result.input_size == header.stored_size);
    assert(result.output_size == header.image_size);
    assert(result.stored_crc32 == crc32(payload.data(), payload.size()));
    assert(result.image_crc32 == crc32(output.data()+8, header.image_size));
  }
  // No activation/executable mapping: a parsed APP is still untrusted bytes.
}
}

int main() {
  using namespace loadable_module;
  std::vector<u8> source(128);
  for(usize i = 0; i < source.size(); ++i) source[i] = (u8) (i % 7);
  std::vector<u8> packed, workspace(4 * (source.size()+1));
  zx0::EncodeResult encoded{};
  assert(zx0::encode(source.data(), source.size(), workspace.data(), workspace.size(),
                     {&packed, write_byte}, encoded));
  usize zx_cases = 0, app_cases = 0;
  auto check_zx = [&](const std::vector<u8>& data) {
    for(u32 capacity : {0U, 1U, 127U, 128U, 129U, 256U}) {
      zx_case(data, data.size(), capacity); ++zx_cases;
    }
  };
  for(usize n = 0; n <= packed.size(); ++n) check_zx({packed.begin(), packed.begin()+n});
  for(usize byte = 0; byte < packed.size(); ++byte) {
    for(u8 bit = 0; bit < 8; ++bit) {
      auto mutated = packed; mutated[byte] ^= (u8) (1U << bit); check_zx(mutated);
    }
  }
  for(usize n = 0; n < 512; ++n) {
    std::vector<u8> bytes(next_random() % 129);
    for(u8& byte : bytes) byte = (u8) next_random();
    check_zx(bytes);
    for(u32 declared : {0U, 1U, 0x7FFFFFFFU, 0xFFFFFFFFU}) {
      zx_case(bytes, declared, 256); ++zx_cases;
    }
  }
  Header header{};
  header.kind = Kind::APPLICATION; header.compression = Compression::NONE;
  header.load_address = SRAM_FIRST_ADDRESS + 0x8000;
  header.stored_size = source.size(); header.image_size = source.size();
  header.memory_size = source.size(); header.entry_offset = 0;
  header.resident_size = 65536; header.resident_crc32 = 0x12345678;
  header.image_crc32 = header.stored_crc32 = crc32(source.data(), source.size());
  std::vector<u8> app(HEADER_SIZE + source.size());
  assert(encode_header(header, MAX_CONTAINER_SIZE, app.data()));
  std::copy(source.begin(), source.end(), app.begin()+HEADER_SIZE);
  auto check_app = [&](const std::vector<u8>& data) {
    for(u32 slot : {0U, 63U, 64U, 191U, 192U, MAX_CONTAINER_SIZE, 0xFFFFFFFFU}) {
      app_case(data, slot); ++app_cases;
    }
  };
  for(usize n = 0; n <= app.size(); ++n) check_app({app.begin(), app.begin()+n});
  for(usize byte = 0; byte < app.size(); ++byte) {
    for(u8 bit = 0; bit < 8; ++bit) {
      auto mutated = app; mutated[byte] ^= (u8) (1U << bit); check_app(mutated);
      // Correct the envelope CRC as well: exercise field validation, not only CRC.
      if(byte < 60) { put32(mutated.data()+60, crc32(mutated.data(), 60)); check_app(mutated); }
    }
  }
  for(usize offset = 16; offset <= 48; offset += 4) {
    for(u32 boundary : {0U,1U,0xFFFFU,0x10000U,0x7FFFFFFFU,0x80000000U,0xFFFFFFFFU}) {
      auto mutated = app; put32(mutated.data()+offset, boundary);
      put32(mutated.data()+60, crc32(mutated.data(), 60)); check_app(mutated);
    }
  }
  std::printf("parser hardening seed=%08lx APP=%u ZX0=%u PASS\n",
               (unsigned long) SEED, (unsigned) app_cases, (unsigned) zx_cases);
}
