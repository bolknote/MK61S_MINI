#include "loadable_module_format.hpp"

#include "zx0.hpp"

#include <string.h>

namespace loadable_module {
namespace {

static constexpr u8 MAGIC[8] = {'M', 'K', '6', '1', 'M', 'O', 'D', 0};
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
static constexpr u16 RESIDENT_SIZE_OFFSET = 40;
static constexpr u16 RESIDENT_CRC_OFFSET = 44;
static constexpr u16 STORED_CRC_OFFSET = 48;
static constexpr u16 IMAGE_CRC_OFFSET = 52;
static constexpr u16 RESERVED_OFFSET = 56;
static constexpr u16 HEADER_CRC_OFFSET = 60;
static constexpr usize INPUT_BUFFER_SIZE = 64;

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
  if(!valid_kind(header.kind) ||
     !valid_compression(header.compression) ||
     header.flags != 0 ||
     header.load_address < SRAM_FIRST_ADDRESS ||
     header.load_address > SRAM_LAST_ADDRESS - OVERLAY_SIZE ||
     (header.load_address & 7U) != 0 ||
     header.stored_size == 0 ||
     header.image_size == 0 ||
     header.memory_size < header.image_size ||
     header.entry_offset >= header.image_size ||
     (header.entry_offset & 1U) != 0 ||
     header.resident_size == 0 ||
     header.resident_size > MAX_RESIDENT_SIZE) {
    return HeaderStatus::INVALID_FIELDS;
  }
  if(header.kind != expected_kind) return HeaderStatus::WRONG_KIND;
  if(header.memory_size > OVERLAY_SIZE || slot_size < HEADER_SIZE ||
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
    BufferedInput(const Reader& reader, u32 size)
      : reader_(reader), size_(size), position_(0), buffered_(0), cursor_(0),
        crc_(crc32_begin()), failed_(reader.read == nullptr) {}

    bool next(u8& value) {
      if(failed_ || position_ >= size_) return false;
      if(cursor_ == buffered_) {
        const u32 remaining = size_ - position_;
        buffered_ = (usize) (remaining < INPUT_BUFFER_SIZE
            ? remaining : INPUT_BUFFER_SIZE);
        cursor_ = 0;
        if(!reader_.read(reader_.context, position_, buffer_, buffered_)) {
          failed_ = true;
          return false;
        }
      }
      value = buffer_[cursor_++];
      position_++;
      crc_ = crc32_extend(crc_, &value, 1);
      return true;
    }

    u32 position(void) const { return position_; }
    u32 checksum(void) const { return crc32_finish(crc_); }
    bool failed(void) const { return failed_; }

  private:
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

} // namespace

bool valid_kind(Kind kind) {
  return kind == Kind::FOCAL || kind == Kind::TINYBASIC ||
         kind == Kind::WBMP_VIEWER;
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
  }
  return (Kind) 0;
}

const char* file_name(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return "FOCAL.MOD";
    case Kind::TINYBASIC: return "BASIC.MOD";
    case Kind::WBMP_VIEWER: return "WBMP.MOD";
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
  return 0xFFFFFFFFUL;
}

u32 crc32_extend(u32 state, const u8* data, usize size) {
  if(data == nullptr && size != 0) return state;
  for(usize index = 0; index < size; index++) {
    state ^= data[index];
    for(u8 bit = 0; bit < 8; bit++) {
      state = (state & 1U) != 0
          ? (state >> 1) ^ 0xEDB88320UL : state >> 1;
    }
  }
  return state;
}

u32 crc32_finish(u32 state) {
  return state ^ 0xFFFFFFFFUL;
}

u32 crc32(const u8* data, usize size) {
  return crc32_finish(crc32_extend(crc32_begin(), data, size));
}

bool encode_header(const Header& header, u32 slot_size,
                   u8 output[HEADER_SIZE]) {
  if(output == nullptr ||
     validate_header(header, slot_size, header.kind) != HeaderStatus::OK) {
    return false;
  }
  memset(output, 0, HEADER_SIZE);
  memcpy(output, MAGIC, sizeof(MAGIC));
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
  put_le32(output, RESIDENT_SIZE_OFFSET, header.resident_size);
  put_le32(output, RESIDENT_CRC_OFFSET, header.resident_crc32);
  put_le32(output, STORED_CRC_OFFSET, header.stored_crc32);
  put_le32(output, IMAGE_CRC_OFFSET, header.image_crc32);
  put_le32(output, RESERVED_OFFSET, 0);
  put_le32(output, HEADER_CRC_OFFSET,
           crc32(output, HEADER_CRC_OFFSET));
  return true;
}

HeaderStatus decode_header(const u8 input[HEADER_SIZE], u32 slot_size,
                           Kind expected_kind, Header& output) {
  memset(&output, 0, sizeof(output));
  if(input == nullptr || memcmp(input, MAGIC, sizeof(MAGIC)) != 0) {
    return HeaderStatus::BAD_MAGIC;
  }
  if(get_le32(input, HEADER_CRC_OFFSET) != crc32(input, HEADER_CRC_OFFSET)) {
    return HeaderStatus::BAD_CRC;
  }
  if(get_le16(input, FORMAT_OFFSET) != FORMAT_VERSION ||
     get_le16(input, HEADER_SIZE_OFFSET) != HEADER_SIZE) {
    return HeaderStatus::UNSUPPORTED_FORMAT;
  }
  if(get_le16(input, ABI_OFFSET) != ABI_VERSION) {
    return HeaderStatus::UNSUPPORTED_ABI;
  }
  if(get_le32(input, RESERVED_OFFSET) != 0) {
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
  output.resident_size = get_le32(input, RESIDENT_SIZE_OFFSET);
  output.resident_crc32 = get_le32(input, RESIDENT_CRC_OFFSET);
  output.stored_crc32 = get_le32(input, STORED_CRC_OFFSET);
  output.image_crc32 = get_le32(input, IMAGE_CRC_OFFSET);
  return validate_header(output, slot_size, expected_kind);
}

bool decode_payload(const Reader& reader, Compression compression,
                    u32 stored_size, u8* output, u32 image_size,
                    DecodeResult& result) {
  memset(&result, 0, sizeof(result));
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
  result.stored_crc32 = input.checksum();
  result.image_crc32 = crc32(output, image_size);
  result.input_size = input.position();
  result.output_size = written;
  return true;
}

} // namespace loadable_module
