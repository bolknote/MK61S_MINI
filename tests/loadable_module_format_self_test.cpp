#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../code/loadable_module_format.hpp"

using namespace loadable_module;

namespace {

static constexpr u32 VALID_LOAD_ADDRESS = 0x2000B000UL;

struct MemoryReader {
  const u8* data;
  u32 size;
  u8 maximum_chunk;
};

static bool read_memory(void* context, u32 offset, u8* output, usize size) {
  MemoryReader& source = *(MemoryReader*) context;
  if(output == nullptr || offset > source.size || size > source.size - offset ||
     (source.maximum_chunk != 0 && size > source.maximum_chunk)) return false;
  memcpy(output, source.data + offset, size);
  return true;
}

static Header valid_header(void) {
  Header header = {};
  header.kind = Kind::FOCAL;
  header.compression = Compression::ZX0;
  header.load_address = VALID_LOAD_ADDRESS;
  header.stored_size = 1234;
  header.image_size = 4096;
  header.memory_size = 4608;
  header.entry_offset = 24;
  header.resident_size = 177777;
  header.resident_crc32 = 0x11223344UL;
  header.stored_crc32 = 0x55667788UL;
  header.image_crc32 = 0xAABBCCDDUL;
  return header;
}

static void test_kind_file_names(void) {
  Kind kind = (Kind) 0;
  assert(KIND_COUNT == 3);
  assert(kind_at(0) == Kind::FOCAL);
  assert(kind_at(1) == Kind::TINYBASIC);
  assert(kind_at(2) == Kind::WBMP_VIEWER);
  assert(kind_at(KIND_COUNT) == (Kind) 0);
  assert(valid_kind(Kind::APPLICATION));
  assert(strcmp(SYSTEM_DIRECTORY_NAME, "System") == 0);
  assert(system_directory_name_matches("system"));
  assert(system_directory_name_matches("SYSTEM"));
  assert(!system_directory_name_matches("Systems"));
  assert(strcmp(file_name(Kind::FOCAL), "FOCAL.APP") == 0);
  assert(strcmp(file_name(Kind::TINYBASIC), "BASIC.APP") == 0);
  assert(strcmp(file_name(Kind::WBMP_VIEWER), "WBMP.APP") == 0);
  assert(file_name(Kind::APPLICATION) == nullptr);
  assert(file_name((Kind) 0) == nullptr);
  assert(kind_from_file_name("focal.app", kind) && kind == Kind::FOCAL);
  assert(kind_from_file_name("Basic.App", kind) &&
         kind == Kind::TINYBASIC);
  assert(kind_from_file_name("WBMP.APP", kind) &&
         kind == Kind::WBMP_VIEWER);
  assert(!kind_from_file_name("OTHER.APP", kind));
  assert(!valid_kind(kind));
}

static void rewrite_crc(u8 header[HEADER_SIZE]) {
  const u32 checksum = crc32(header, 60);
  header[60] = (u8) checksum;
  header[61] = (u8) (checksum >> 8);
  header[62] = (u8) (checksum >> 16);
  header[63] = (u8) (checksum >> 24);
}

static void test_header_round_trip(void) {
  const Header source = valid_header();
  u8 bytes[HEADER_SIZE];
  assert(encode_header(source, 16U * 1024U, bytes));
  Header decoded = {};
  assert(decode_header(bytes, 16U * 1024U, Kind::FOCAL, decoded) ==
         HeaderStatus::OK);
  assert(decoded.kind == source.kind);
  assert(decoded.compression == source.compression);
  assert(decoded.stored_size == source.stored_size);
  assert(decoded.image_size == source.image_size);
  assert(decoded.memory_size == source.memory_size);
  assert(decoded.entry_offset == source.entry_offset);
  assert(decoded.resident_size == source.resident_size);
  assert(decoded.resident_crc32 == source.resident_crc32);
  assert(decoded.stored_crc32 == source.stored_crc32);
  assert(decoded.image_crc32 == source.image_crc32);

  Header any_kind = {};
  assert(decode_header(bytes, 16U * 1024U, any_kind) ==
         HeaderStatus::OK);
  assert(any_kind.kind == Kind::FOCAL);

  // Единственный поддерживаемый контейнер имеет сигнатуру MK61APP.
  memcpy(bytes + 4, "MOD", 3);
  rewrite_crc(bytes);
  assert(decode_header(bytes, 16U * 1024U, Kind::FOCAL, decoded) ==
         HeaderStatus::BAD_MAGIC);
}

static void test_header_rejects_incompatible_images(void) {
  u8 bytes[HEADER_SIZE];
  Header header = valid_header();
  assert(encode_header(header, 16U * 1024U, bytes));
  Header decoded = {};
  assert(decode_header(bytes, 16U * 1024U, Kind::TINYBASIC, decoded) ==
         HeaderStatus::WRONG_KIND);
  assert(decode_header(bytes, 512, Kind::FOCAL, decoded) ==
         HeaderStatus::TOO_LARGE);

  bytes[12]++;
  rewrite_crc(bytes);
  assert(decode_header(bytes, 16U * 1024U, Kind::FOCAL, decoded) ==
         HeaderStatus::UNSUPPORTED_ABI);

  assert(encode_header(header, 16U * 1024U, bytes));
  bytes[56] = 1;
  rewrite_crc(bytes);
  assert(decode_header(bytes, 16U * 1024U, Kind::FOCAL, decoded) ==
         HeaderStatus::INVALID_FIELDS);

  header.entry_offset = 25;
  assert(!encode_header(header, 16U * 1024U, bytes));
  header = valid_header();
  header.memory_size = OVERLAY_SIZE + 1;
  assert(!encode_header(header, 16U * 1024U, bytes));
}

static void test_uncompressed_payload(void) {
  const u8 source[] = {0, 1, 2, 3, 4, 5};
  MemoryReader memory = {source, sizeof(source), 0};
  const Reader reader = {&memory, read_memory};
  u8 output[sizeof(source)] = {};
  DecodeResult result = {};
  assert(decode_payload(reader, Compression::NONE, sizeof(source), output,
                        sizeof(output), result));
  assert(memcmp(source, output, sizeof(source)) == 0);
  assert(result.stored_crc32 == crc32(source, sizeof(source)));
  assert(result.image_crc32 == crc32(source, sizeof(source)));
}

static void test_buffered_crc_across_blocks(void) {
  u8 source[129];
  for(usize index = 0; index < sizeof(source); index++) {
    source[index] = (u8) (index * 37U + 11U);
  }
  // 129 байт пересекают две полные внутренние порции по 64 байта и последнюю
  // неполную. Ограничение reader дополнительно фиксирует размер порции.
  MemoryReader memory = {source, sizeof(source), 64};
  const Reader reader = {&memory, read_memory};
  u8 output[sizeof(source)] = {};
  DecodeResult result = {};
  assert(decode_payload(reader, Compression::NONE, sizeof(source), output,
                        sizeof(output), result));
  assert(memcmp(source, output, sizeof(source)) == 0);
  assert(result.input_size == sizeof(source));
  assert(result.output_size == sizeof(source));
  assert(result.stored_crc32 == crc32(source, sizeof(source)));
  assert(result.image_crc32 == crc32(source, sizeof(source)));
}

static void test_zx0_payload(void) {
  // Оптимальный ZX0 v2: литералы ABC, перекрывающаяся ссылка и перевод строки.
  const u8 packed[] = {
    0x79, 0x41, 0x42, 0x43, 0xFA, 0xB5, 0x0A, 0x55, 0x58
  };
  const u8 expected[] = {
    'A', 'B', 'C', 'A', 'B', 'C', 'A', 'B', 'C', '\n'
  };
  MemoryReader memory = {packed, sizeof(packed), 0};
  const Reader reader = {&memory, read_memory};
  u8 output[sizeof(expected)] = {};
  DecodeResult result = {};
  assert(decode_payload(reader, Compression::ZX0, sizeof(packed), output,
                        sizeof(output), result));
  assert(memcmp(expected, output, sizeof(expected)) == 0);
  assert(result.stored_crc32 == crc32(packed, sizeof(packed)));
  assert(result.image_crc32 == crc32(expected, sizeof(expected)));

  // Перекрывающаяся ссылка расстояния 1 должна развернуться без второго буфера.
  const u8 run[] = {0x90, 0x78, 0x16, 0xD5, 0x0A, 0x55, 0x60};
  MemoryReader run_memory = {run, sizeof(run), 0};
  const Reader run_reader = {&run_memory, read_memory};
  u8 repeated[101] = {};
  assert(decode_payload(run_reader, Compression::ZX0, sizeof(run), repeated,
                        sizeof(repeated), result));
  for(usize index = 0; index < 100; index++) assert(repeated[index] == 'x');
  assert(repeated[100] == '\n');

  // Новый offset с двухбайтовым совпадением: младший бит байта offset равен 1
  // и сразу завершает gamma-код длины. Это проверяет ZX0 backtrack без флага.
  const u8 short_match[] = {
    0x38, 0x41, 0x42, 0xFD, 0xD5, 0x58, 0x0A, 0x55, 0x60
  };
  const u8 short_expected[] = {'A', 'B', 'A', 'B', 'X', '\n'};
  MemoryReader short_memory = {
    short_match, sizeof(short_match), 0
  };
  const Reader short_reader = {&short_memory, read_memory};
  u8 short_output[sizeof(short_expected)] = {};
  assert(decode_payload(short_reader, Compression::ZX0,
                        sizeof(short_match), short_output,
                        sizeof(short_output), result));
  assert(memcmp(short_expected, short_output, sizeof(short_expected)) == 0);
}

static void test_zx0_rejects_bad_streams(void) {
  const u8 truncated[] = {
    0x79, 0x41, 0x42, 0x43, 0xFA, 0xB5, 0x0A, 0x55
  };
  MemoryReader memory = {truncated, sizeof(truncated), 0};
  const Reader reader = {&memory, read_memory};
  u8 output[10] = {};
  DecodeResult result = {};
  assert(!decode_payload(reader, Compression::ZX0, sizeof(truncated),
                         output, sizeof(output), result));

  const u8 invalid[] = {0x00};
  MemoryReader invalid_memory = {
    invalid, sizeof(invalid), 0
  };
  const Reader invalid_reader = {&invalid_memory, read_memory};
  assert(!decode_payload(invalid_reader, Compression::ZX0,
                         sizeof(invalid), output, 1, result));

  const u8 trailing[] = {
    0x79, 0x41, 0x42, 0x43, 0xFA, 0xB5, 0x0A, 0x55, 0x58, 0x00
  };
  MemoryReader trailing_memory = {trailing, sizeof(trailing), 0};
  const Reader trailing_reader = {&trailing_memory, read_memory};
  assert(!decode_payload(trailing_reader, Compression::ZX0, sizeof(trailing),
                         output, sizeof(output), result));

  const u8 valid[] = {
    0x79, 0x41, 0x42, 0x43, 0xFA, 0xB5, 0x0A, 0x55, 0x58
  };
  MemoryReader valid_memory = {valid, sizeof(valid), 0};
  const Reader valid_reader = {&valid_memory, read_memory};
  assert(!decode_payload(valid_reader, Compression::ZX0, sizeof(valid),
                         output, sizeof(output) - 1, result));
  assert(!decode_payload(valid_reader, Compression::ZX0, sizeof(valid),
                         output, sizeof(output) + 1, result));
}

static void test_zx0_corruption_is_bounded(void) {
  const u8 packed[] = {
    0x79, 0x41, 0x42, 0x43, 0xFA, 0xB5, 0x0A, 0x55, 0x58
  };
  DecodeResult result = {};
  u8 output[32] = {};
  for(u32 size = 1; size < sizeof(packed); size++) {
    MemoryReader memory = {packed, size, 0};
    const Reader reader = {&memory, read_memory};
    (void) decode_payload(reader, Compression::ZX0, size, output,
                          sizeof(output), result);
  }
  for(usize byte = 0; byte < sizeof(packed); byte++) {
    for(u8 bit = 0; bit < 8; bit++) {
      u8 damaged[sizeof(packed)];
      memcpy(damaged, packed, sizeof(damaged));
      damaged[byte] ^= (u8) (1U << bit);
      MemoryReader memory = {damaged, sizeof(damaged), 0};
      const Reader reader = {&memory, read_memory};
      (void) decode_payload(reader, Compression::ZX0, sizeof(damaged), output,
                            sizeof(output), result);
    }
  }

  u8 noise[64] = {};
  u32 state = 0x31415926UL;
  for(usize sample = 0; sample < 256; sample++) {
    const u32 size = 1U + (state % sizeof(noise));
    for(u32 index = 0; index < size; index++) {
      state = state * 1664525UL + 1013904223UL;
      noise[index] = (u8) (state >> 24);
    }
    MemoryReader memory = {noise, size, 0};
    const Reader reader = {&memory, read_memory};
    (void) decode_payload(reader, Compression::ZX0, size, output,
                          sizeof(output), result);
  }
}

} // namespace

int main(void) {
  test_kind_file_names();
  test_header_round_trip();
  test_header_rejects_incompatible_images();
  test_uncompressed_payload();
  test_buffered_crc_across_blocks();
  test_zx0_payload();
  test_zx0_rejects_bad_streams();
  test_zx0_corruption_is_bounded();
  printf("loadable_module_format_self_test: ok\n");
  return 0;
}
