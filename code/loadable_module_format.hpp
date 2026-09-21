#ifndef MK61_LOADABLE_MODULE_FORMAT_HPP
#define MK61_LOADABLE_MODULE_FORMAT_HPP

#include "rust_types.h"
#include "portable_app_config.h"

namespace loadable_module {

// Container/image limit, not a reserved SRAM window. The current ABI receives
// a block at the top of free RAM; fixed-address formats are not executable.
static constexpr u32 SRAM_FIRST_ADDRESS = 0x20000000UL;
static constexpr u32 SRAM_LAST_ADDRESS = 0x20020000UL;
static constexpr u32 APP_MAX_MEMORY_SIZE = 20U * 1024U;
static constexpr u16 HEADER_SIZE = 64;
static constexpr u32 MAX_CONTAINER_SIZE = APP_MAX_MEMORY_SIZE + HEADER_SIZE;
static constexpr u16 FORMAT_VERSION = 1;
static constexpr u16 ABI_VERSION = MK61_CURRENT_APP_ABI;

enum class Kind : u8 {
  FOCAL = 1,
  TINYBASIC = 2,
  WBMP_VIEWER = 3,
  APPLICATION = 4,
  CHIP8 = 5,
  MARKDOWN_VIEWER = 6,
  SETUP = 7,
  USBDISK = 8
};

// Только системные APP имеют канонические имена. Пользовательских APPLICATION
// может быть сколько угодно, и их M8-имена задаются самим файлом в C6.
static constexpr u8 KIND_COUNT = 7;
static constexpr char SYSTEM_DIRECTORY_NAME[] = "System";

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
  // Compressed image length and number of word relocations in the following
  // delta-coded table. Both fields are mandatory in the current ABI.
  u32 code_stored_size;
  u32 relocation_count;
  u32 stored_crc32;
  u32 image_crc32;
  // Ноль означает обычный APP. Ненулевой двухбайтовый magic C6 объявляет
  // основной тип FILE_OPEN. Графический системный MARKDOWN.APP дополнительно
  // принимает I1 как известный resident alias, не меняя формат заголовка.
  u16 handled_type_magic;
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
bool system_directory_name_matches(const char* name);
const char* file_name(Kind kind);
bool kind_from_file_name(const char* name, Kind& kind);

// Заголовок всегда кодируется явно в little-endian: формат не зависит от
// выравнивания структур и версии компилятора.
bool encode_header(const Header& header, u32 slot_size,
                   u8 output[HEADER_SIZE]);
HeaderStatus decode_header(const u8 input[HEADER_SIZE], u32 slot_size,
                           Kind expected_kind, Header& output);
HeaderStatus decode_header(const u8 input[HEADER_SIZE], u32 slot_size,
                           Header& output);

u32 crc32_begin(void);
u32 crc32_extend(u32 state, const u8* data, usize size);
u32 crc32_finish(u32 state);
u32 crc32(const u8* data, usize size);

// Читает ровно stored_size байт и распаковывает ZX0 непосредственно в SRAM.
// Уже полученная часть output служит окном, поэтому отдельный словарь и второй
// образ в памяти не требуются.
// CRC verification precedes relocation; no entry may execute on failure.
// Header must have passed decode_header. load_address is the actual allocation.
bool decode_image(const Header& header, const Reader& reader,
                  u8* output, u32 load_address);

bool decode_payload(const Reader& reader, Compression compression,
                    u32 stored_size, u8* output, u32 image_size,
                    DecodeResult& result, u32 flags = 0);

} // namespace loadable_module

#endif
