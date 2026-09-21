#include "loadable_module_format.hpp"

#include "crc32.hpp"
#include "zx0.hpp"
#include "arm_thumb_bcj.hpp"

#include <string.h>

namespace loadable_module {
namespace {

static constexpr u8 APP_MAGIC[8] = {'M', 'K', '6', '1', 'A', 'P', 'P', 0};
static constexpr u16 FORMAT_OFFSET = 8;
static constexpr u16 HEADER_SIZE_OFFSET = 10;
static constexpr u16 ABI_OFFSET = 12;
static constexpr u16 KIND_OFFSET = 14;
static constexpr u16 COMPRESSION_OFFSET = 15;
static constexpr u16 FLAGS_OFFSET = 16;
static constexpr u16 LOAD_ADDRESS_OFFSET = 20;
static constexpr u16 STORED_SIZE_OFFSET = 24;
static constexpr u16 IMAGE_SIZE_OFFSET = 28;
static constexpr u16 MEMORY_SIZE_OFFSET = 32;
static constexpr u16 ENTRY_OFFSET = 36;
static constexpr u16 CODE_STORED_SIZE_OFFSET = 40;
static constexpr u16 RELOCATION_COUNT_OFFSET = 44;
static constexpr u16 STORED_CRC_OFFSET = 48;
static constexpr u16 IMAGE_CRC_OFFSET = 52;
static constexpr u16 HANDLED_TYPE_MAGIC_OFFSET = 56;
static constexpr u16 RESERVED_OFFSET = 58;
static constexpr u16 HEADER_CRC_OFFSET = 60;
// C6 stores APP containers without a second compression layer, but a large
// APP still spans several NOR sectors.  Every Reader call has to resolve and
// validate the C6 large-file metadata, so 64-byte refills turned a 12 KiB
// system APP into almost two hundred full storage lookups on real hardware.
// One native program-store read chunk keeps the streaming decoder bounded on
// F401 while reducing that fixed I/O overhead eightfold.
static constexpr usize INPUT_BUFFER_SIZE = 512;

static u16 get_le16(const u8* data, u16 offset) {
  return (u16) (data[offset] | ((u16) data[offset + 1] << 8));
}

static u32 get_le32(const u8* data, u16 offset) {
  return (u32) data[offset] |
         ((u32) data[offset + 1] << 8) |
         ((u32) data[offset + 2] << 16) |
         ((u32) data[offset + 3] << 24);
}

static void put_le16(u8* data, u16 offset, u16 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
}

static void put_le32(u8* data, u16 offset, u32 value) {
  data[offset] = (u8) value;
  data[offset + 1] = (u8) (value >> 8);
  data[offset + 2] = (u8) (value >> 16);
  data[offset + 3] = (u8) (value >> 24);
}

static HeaderStatus validate_header(const Header& header, u32 slot_size,
                                    Kind expected_kind) {
  const u32 required_flags = MK61_PORTABLE_APP_FLAG |
                             MK61_APP_RELOCATABLE_FLAG;
  const bool binding_valid =
      (header.flags & ~MK61_APP_ARM_THUMB_BCJ_FLAG) == required_flags &&
      header.load_address == MK61_PORTABLE_APP_ADDRESS &&
      header.compression == Compression::ZX0 &&
      header.code_stored_size > 0 &&
      header.code_stored_size <= header.stored_size &&
      header.relocation_count <= header.image_size / 4 &&
      header.relocation_count <= header.stored_size - header.code_stored_size &&
      header.stored_size - header.code_stored_size <=
          3 * header.relocation_count;
  if(!valid_kind(header.kind) ||
     !valid_compression(header.compression) ||
     !binding_valid ||
     header.load_address < SRAM_FIRST_ADDRESS ||
     header.load_address > SRAM_LAST_ADDRESS - APP_MAX_MEMORY_SIZE ||
     (header.load_address & 7U) != 0 ||
     header.stored_size == 0 ||
     header.image_size == 0 ||
     header.memory_size < header.image_size ||
     header.entry_offset >= header.image_size ||
     (header.entry_offset & 1U) != 0) {
    return HeaderStatus::INVALID_FIELDS;
  }
  if(header.kind != expected_kind) return HeaderStatus::WRONG_KIND;
  if(header.memory_size > APP_MAX_MEMORY_SIZE || slot_size < HEADER_SIZE ||
     header.stored_size > slot_size - HEADER_SIZE) {
    return HeaderStatus::TOO_LARGE;
  }
  if(header.compression == Compression::NONE &&
     header.stored_size != header.image_size) {
    return HeaderStatus::INVALID_FIELDS;
  }
  return HeaderStatus::OK;
}

class BufferedInput {
  public:
    BufferedInput(const Reader& reader, u32 size, u32 seed = crc32_begin())
      : reader_(reader), size_(size), position_(0), buffered_(0), cursor_(0),
        crc_(seed), failed_(reader.read == nullptr) {}

    bool next(u8& value) {
      if(failed_ || position_ >= size_) return false;
      if(cursor_ == buffered_ && !refill()) return false;
      value = buffer_[cursor_++];
      position_++;
      return true;
    }

    u32 position(void) const { return position_; }
    u32 checksum(void) const { return crc32_finish(crc_); }
    bool failed(void) const { return failed_; }

  private:
    // Отдельная функция сохраняет коротким часто вызываемый из ZX0 путь next:
    // заполнение и CRC выполняются только раз на порцию, а не раз на байт.
    bool __attribute__((noinline)) refill(void) {
      const u32 remaining = size_ - position_;
      buffered_ = (usize) (remaining < INPUT_BUFFER_SIZE
          ? remaining : INPUT_BUFFER_SIZE);
      cursor_ = 0;
      if(!reader_.read(reader_.context, position_, buffer_, buffered_)) {
        failed_ = true;
        return false;
      }
      // Успешный decode_payload принимает только полностью прочитанный поток,
      // поэтому CRC блока эквивалентна последовательным побайтным обновлениям.
      crc_ = crc32_extend(crc_, buffer_, buffered_);
      return true;
    }

    Reader reader_;
    u32 size_;
    u32 position_;
    usize buffered_;
    usize cursor_;
    u32 crc_;
    bool failed_;
    u8 buffer_[INPUT_BUFFER_SIZE];
};

static bool next_zx0_byte(void* context, u8& value) {
  return ((BufferedInput*) context)->next(value);
}

static char ascii_upper(char value) {
  return value >= 'a' && value <= 'z' ? (char) (value - 'a' + 'A') : value;
}

static bool ascii_equal_ci(const char* left, const char* right) {
  if(left == nullptr || right == nullptr) return false;
  while(*left != 0 && *right != 0) {
    if(ascii_upper(*left) != ascii_upper(*right)) return false;
    left++;
    right++;
  }
  return *left == *right;
}

static bool magic_valid(const u8* input) {
  return input != nullptr &&
         memcmp(input, APP_MAGIC, sizeof(APP_MAGIC)) == 0;
}

} // namespace

bool valid_kind(Kind kind) {
  return kind == Kind::FOCAL || kind == Kind::TINYBASIC ||
         kind == Kind::WBMP_VIEWER || kind == Kind::APPLICATION ||
         kind == Kind::CHIP8 || kind == Kind::MARKDOWN_VIEWER ||
         kind == Kind::SETUP || kind == Kind::USBDISK;
}

bool valid_compression(Compression compression) {
  return compression == Compression::NONE ||
         compression == Compression::ZX0;
}

Kind kind_at(u8 index) {
  switch(index) {
    case 0: return Kind::FOCAL;
    case 1: return Kind::TINYBASIC;
    case 2: return Kind::WBMP_VIEWER;
    case 3: return Kind::CHIP8;
    case 4: return Kind::MARKDOWN_VIEWER;
    case 5: return Kind::SETUP;
    case 6: return Kind::USBDISK;
  }
  return (Kind) 0;
}

bool system_directory_name_matches(const char* name) {
  return ascii_equal_ci(name, SYSTEM_DIRECTORY_NAME);
}

const char* file_name(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return "FOCAL.APP";
    case Kind::TINYBASIC: return "BASIC.APP";
    case Kind::WBMP_VIEWER: return "WBMP.APP";
    case Kind::CHIP8: return "CHIP8.APP";
    case Kind::MARKDOWN_VIEWER: return "MARKDOWN.APP";
    case Kind::SETUP: return "SETUP.APP";
    case Kind::USBDISK: return "USBDISK.APP";
    case Kind::APPLICATION: break;
  }
  return nullptr;
}

bool kind_from_file_name(const char* name, Kind& kind) {
  for(u8 index = 0; index < KIND_COUNT; index++) {
    const Kind candidate = kind_at(index);
    if(ascii_equal_ci(name, file_name(candidate))) {
      kind = candidate;
      return true;
    }
  }
  kind = (Kind) 0;
  return false;
}

u32 crc32_begin(void) {
  return mk61_crc32::INITIAL_STATE;
}

u32 crc32_extend(u32 state, const u8* data, usize size) {
  return mk61_crc32::extend(state, data, size);
}

u32 crc32_finish(u32 state) {
  return mk61_crc32::finish(state);
}

u32 crc32(const u8* data, usize size) {
  return mk61_crc32::calculate(data, size);
}

bool encode_header(const Header& header, u32 slot_size,
                   u8 output[HEADER_SIZE]) {
  if(output == nullptr ||
     validate_header(header, slot_size, header.kind) != HeaderStatus::OK) {
    return false;
  }
  memset(output, 0, HEADER_SIZE);
  memcpy(output, APP_MAGIC, sizeof(APP_MAGIC));
  put_le16(output, FORMAT_OFFSET, FORMAT_VERSION);
  put_le16(output, HEADER_SIZE_OFFSET, HEADER_SIZE);
  put_le16(output, ABI_OFFSET, ABI_VERSION);
  output[KIND_OFFSET] = (u8) header.kind;
  output[COMPRESSION_OFFSET] = (u8) header.compression;
  put_le32(output, FLAGS_OFFSET, header.flags);
  put_le32(output, LOAD_ADDRESS_OFFSET, header.load_address);
  put_le32(output, STORED_SIZE_OFFSET, header.stored_size);
  put_le32(output, IMAGE_SIZE_OFFSET, header.image_size);
  put_le32(output, MEMORY_SIZE_OFFSET, header.memory_size);
  put_le32(output, ENTRY_OFFSET, header.entry_offset);
  put_le32(output, CODE_STORED_SIZE_OFFSET, header.code_stored_size);
  put_le32(output, RELOCATION_COUNT_OFFSET, header.relocation_count);
  put_le32(output, STORED_CRC_OFFSET, header.stored_crc32);
  put_le32(output, IMAGE_CRC_OFFSET, header.image_crc32);
  put_le16(output, HANDLED_TYPE_MAGIC_OFFSET, header.handled_type_magic);
  put_le16(output, RESERVED_OFFSET, 0);
  put_le32(output, HEADER_CRC_OFFSET,
           crc32(output, HEADER_CRC_OFFSET));
  return true;
}

HeaderStatus decode_header(const u8 input[HEADER_SIZE], u32 slot_size,
                           Kind expected_kind, Header& output) {
  memset(&output, 0, sizeof(output));
  if(!magic_valid(input)) {
    return HeaderStatus::BAD_MAGIC;
  }
  if(get_le32(input, HEADER_CRC_OFFSET) != crc32(input, HEADER_CRC_OFFSET)) {
    return HeaderStatus::BAD_CRC;
  }
  if(get_le16(input, FORMAT_OFFSET) != FORMAT_VERSION ||
     get_le16(input, HEADER_SIZE_OFFSET) != HEADER_SIZE) {
    return HeaderStatus::UNSUPPORTED_FORMAT;
  }
  const u16 abi = get_le16(input, ABI_OFFSET);
  const u32 flags = get_le32(input, FLAGS_OFFSET);
  if(abi != ABI_VERSION) {
    return HeaderStatus::UNSUPPORTED_ABI;
  }
  if((flags & (MK61_PORTABLE_APP_FLAG | MK61_APP_RELOCATABLE_FLAG)) !=
     (MK61_PORTABLE_APP_FLAG | MK61_APP_RELOCATABLE_FLAG))
    return HeaderStatus::INVALID_FIELDS;
  if(get_le16(input, RESERVED_OFFSET) != 0) {
    return HeaderStatus::INVALID_FIELDS;
  }
  output.kind = (Kind) input[KIND_OFFSET];
  output.compression = (Compression) input[COMPRESSION_OFFSET];
  output.flags = get_le32(input, FLAGS_OFFSET);
  output.load_address = get_le32(input, LOAD_ADDRESS_OFFSET);
  output.stored_size = get_le32(input, STORED_SIZE_OFFSET);
  output.image_size = get_le32(input, IMAGE_SIZE_OFFSET);
  output.memory_size = get_le32(input, MEMORY_SIZE_OFFSET);
  output.entry_offset = get_le32(input, ENTRY_OFFSET);
  output.code_stored_size = get_le32(input, CODE_STORED_SIZE_OFFSET);
  output.relocation_count = get_le32(input, RELOCATION_COUNT_OFFSET);
  output.stored_crc32 = get_le32(input, STORED_CRC_OFFSET);
  output.image_crc32 = get_le32(input, IMAGE_CRC_OFFSET);
  output.handled_type_magic = get_le16(input, HANDLED_TYPE_MAGIC_OFFSET);
  return validate_header(output, slot_size, expected_kind);
}

HeaderStatus decode_header(const u8 input[HEADER_SIZE], u32 slot_size,
                           Header& output) {
  memset(&output, 0, sizeof(output));
  if(!magic_valid(input)) return HeaderStatus::BAD_MAGIC;
  const Kind kind = (Kind) input[KIND_OFFSET];
  if(!valid_kind(kind)) return HeaderStatus::INVALID_FIELDS;
  return decode_header(input, slot_size, kind, output);
}

bool decode_payload(const Reader& reader, Compression compression,
                    u32 stored_size, u8* output, u32 image_size,
                    DecodeResult& result, u32 flags) {
  memset(&result, 0, sizeof(result));
  if(flags != 0) {
    if((flags != MK61_PORTABLE_APP_FLAG &&
        flags != (MK61_PORTABLE_APP_FLAG | MK61_APP_ARM_THUMB_BCJ_FLAG)) ||
       compression != Compression::ZX0) return false;
  }
  if(reader.read == nullptr || !valid_compression(compression) ||
     output == nullptr || stored_size == 0 || image_size == 0) return false;
  if(compression == Compression::NONE && stored_size != image_size) return false;

  BufferedInput input(reader, stored_size);
  u32 written = 0;
  if(compression == Compression::NONE) {
    while(written < image_size) {
      if(!input.next(output[written])) return false;
      written++;
    }
  } else {
    const zx0::Input source = {&input, next_zx0_byte};
    if(!zx0::decode(source, stored_size, output, image_size, written)) {
      return false;
    }
  }
  if(written != image_size) return false;
  if(input.failed() || input.position() != stored_size) return false;
  if((flags & MK61_APP_ARM_THUMB_BCJ_FLAG) != 0)
    arm_thumb_bcj::transform(output, image_size, false);
  result.stored_crc32 = input.checksum();
  result.image_crc32 = crc32(output, image_size);
  result.input_size = input.position();
  result.output_size = written;
  return true;
}

namespace {
struct RelocationSource { const Reader* reader; u32 offset; };
bool read_relocations(void* context, u32 offset, u8* output, usize size) {
  const auto& source = *(const RelocationSource*) context;
  return source.reader->read(source.reader->context, source.offset + offset, output, size);
}
}

bool decode_image(const Header& header, const Reader& reader, u8* output, u32 address) {
  DecodeResult decoded = {};
  const u32 code_size = header.code_stored_size;
  if(address < SRAM_FIRST_ADDRESS || header.memory_size > APP_MAX_MEMORY_SIZE ||
     address > SRAM_LAST_ADDRESS - header.memory_size || (address & 7U) ||
     code_size > header.stored_size) return false;
  if(!decode_payload(reader, header.compression, code_size, output, header.image_size, decoded
       , header.flags & ~MK61_APP_RELOCATABLE_FLAG
       ) || decoded.image_crc32 != header.image_crc32) return false;
  if(header.relocation_count > header.image_size / 4) return false;
  const RelocationSource source = {&reader, code_size};
  const Reader tail = {(void*) &source, read_relocations};
  BufferedInput input(tail, header.stored_size - code_size,
                      decoded.stored_crc32 ^ 0xFFFFFFFFU);
  u32 end = 0;
  const u32 delta = address - header.load_address;
  for(u32 i = 0; i < header.relocation_count; ++i) {
    u32 gap = 0;
    for(u32 shift = 0; ; shift += 7) {
      u8 byte = 0;
      if(shift > 14 || !input.next(byte) ||
         (shift != 0 && byte == 0)) return false;
      gap |= (u32) (byte & 127U) << shift;
      if(!(byte & 128U)) break;
    }
    if(end > header.image_size || gap > header.image_size - end ||
       header.image_size - end - gap < 4) return false;
    const u32 offset = end + gap;
    const u32 pointer = get_le32(output, (u16) offset);
    if(pointer < header.load_address ||
       pointer - header.load_address > header.memory_size) return false;
    put_le32(output, (u16) offset, pointer + delta);
    end = offset + 4;
  }
  return !input.failed() &&
         input.position() == header.stored_size - code_size &&
         input.checksum() == header.stored_crc32;
}

} // namespace loadable_module
