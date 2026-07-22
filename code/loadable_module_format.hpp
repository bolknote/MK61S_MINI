#ifndef MK61_LOADABLE_MODULE_FORMAT_HPP
#define MK61_LOADABLE_MODULE_FORMAT_HPP

#include "rust_types.h"

namespace loadable_module {

// Основная прошивка резервирует единый 20-КиБ массив в SRAM; его фактический
// адрес извлекается из resident ELF и передаётся отдельной линковке модулей.
// Поэтому размещение остаётся проверяемым линкером и не зависит от размера .bss.
static constexpr u32 DEFAULT_LOAD_ADDRESS = 0x2000B000UL;
static constexpr u32 SRAM_FIRST_ADDRESS = 0x20000000UL;
static constexpr u32 SRAM_LAST_ADDRESS = 0x20020000UL;
static constexpr u32 OVERLAY_SIZE = 20U * 1024U;
static constexpr u16 HEADER_SIZE = 64;
static constexpr u16 FORMAT_VERSION = 1;
static constexpr u16 ABI_VERSION = 1;
static constexpr u32 MAX_RESIDENT_SIZE = 512U * 1024U;

enum class Kind : u8 {
  FOCAL = 1,
  TINYBASIC = 2,
  WBMP_VIEWER = 3
};

static constexpr u8 KIND_COUNT = 3;

enum class Compression : u8 {
  NONE = 0,
  ZX0 = 1
};

struct Header {
  Kind kind;
  Compression compression;
  u32 flags;
  u32 load_address;
  u32 stored_size;
  u32 image_size;
  u32 memory_size;
  u32 entry_offset;
  u32 resident_size;
  u32 resident_crc32;
  u32 stored_crc32;
  u32 image_crc32;
};

enum class HeaderStatus : u8 {
  OK = 0,
  BAD_MAGIC,
  BAD_CRC,
  UNSUPPORTED_FORMAT,
  UNSUPPORTED_ABI,
  WRONG_KIND,
  INVALID_FIELDS,
  TOO_LARGE
};

struct Reader {
  void* context;
  bool (*read)(void* context, u32 offset, u8* output, usize size);
};

struct DecodeResult {
  u32 stored_crc32;
  u32 image_crc32;
  u32 input_size;
  u32 output_size;
};

bool valid_kind(Kind kind);
bool valid_compression(Compression compression);
Kind kind_at(u8 index);
const char* file_name(Kind kind);
bool kind_from_file_name(const char* name, Kind& kind);

// Заголовок всегда кодируется явно в little-endian: формат не зависит от
// выравнивания структур и версии компилятора.
bool encode_header(const Header& header, u32 slot_size,
                   u8 output[HEADER_SIZE]);
HeaderStatus decode_header(const u8 input[HEADER_SIZE], u32 slot_size,
                           Kind expected_kind, Header& output);

u32 crc32_begin(void);
u32 crc32_extend(u32 state, const u8* data, usize size);
u32 crc32_finish(u32 state);
u32 crc32(const u8* data, usize size);

// Читает ровно stored_size байт и распаковывает ZX0 непосредственно в SRAM.
// Уже полученная часть output служит окном, поэтому отдельный словарь и второй
// образ в памяти не требуются.
bool decode_payload(const Reader& reader, Compression compression,
                    u32 stored_size, u8* output, u32 image_size,
                    DecodeResult& result);

} // namespace loadable_module

#endif
