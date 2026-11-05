#include "resident_firmware_format.hpp"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using resident_firmware_format::Footer;

struct Options {
  bool seal;
  std::string input;
  std::string output;
  size_t maximum_size = 512U * 1024U;
};

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

u16 get_le16(const std::vector<u8>& bytes, size_t offset) {
  if(offset > bytes.size() || sizeof(u16) > bytes.size() - offset)
    fail("truncated 16-bit field");
  return (u16) bytes[offset] | ((u16) bytes[offset + 1] << 8);
}

u32 get_le32(const std::vector<u8>& bytes, size_t offset) {
  if(offset > bytes.size() || sizeof(u32) > bytes.size() - offset)
    fail("truncated 32-bit field");
  return (u32) bytes[offset] |
         ((u32) bytes[offset + 1] << 8) |
         ((u32) bytes[offset + 2] << 16) |
         ((u32) bytes[offset + 3] << 24);
}

void put_le32(std::vector<u8>& bytes, size_t offset, u32 value) {
  if(offset > bytes.size() || sizeof(u32) > bytes.size() - offset)
    fail("truncated 32-bit field");
  bytes[offset] = (u8) value;
  bytes[offset + 1] = (u8) (value >> 8);
  bytes[offset + 2] = (u8) (value >> 16);
  bytes[offset + 3] = (u8) (value >> 24);
}

u32 crc32(const std::vector<u8>& bytes) {
  u32 state = 0xFFFFFFFFUL;
  for(u8 value : bytes) {
    state ^= value;
    for(u8 bit = 0; bit < 8; bit++) {
      state = (state & 1U) != 0
          ? (state >> 1) ^ 0xEDB88320UL : state >> 1;
    }
  }
  return state ^ 0xFFFFFFFFUL;
}

std::vector<u8> read_file(const std::string& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if(!input) fail("cannot open input: " + path);
  const std::streamoff end = input.tellg();
  if(end <= 0 || (u64) end > std::numeric_limits<size_t>::max())
    fail("invalid input size: " + path);
  std::vector<u8> bytes((size_t) end);
  input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),
             (std::streamsize) bytes.size());
  if(!input) fail("cannot read input: " + path);
  return bytes;
}

void write_file(const std::string& path, const std::vector<u8>& bytes) {
  const std::string temporary = path + ".mk61-seal.tmp";
  {
    std::ofstream output(temporary,
                         std::ios::binary | std::ios::trunc);
    if(!output) fail("cannot create output: " + temporary);
    output.write(reinterpret_cast<const char*>(bytes.data()),
                 (std::streamsize) bytes.size());
    output.flush();
    if(!output) fail("cannot write output: " + temporary);
  }
  if(std::rename(temporary.c_str(), path.c_str()) != 0) {
#if defined(_WIN32)
    if(std::remove(path.c_str()) == 0 &&
       std::rename(temporary.c_str(), path.c_str()) == 0) return;
#endif
    const int error = errno;
    std::remove(temporary.c_str());
    fail("cannot replace output: " + path + ": " +
         std::strerror(error));
  }
}

bool magic_at(const std::vector<u8>& bytes, size_t offset) {
  if(offset > bytes.size() || sizeof(resident_firmware_format::MAGIC) >
     bytes.size() - offset) return false;
  return std::memcmp(bytes.data() + offset,
                     resident_firmware_format::MAGIC,
                     sizeof(resident_firmware_format::MAGIC)) == 0;
}

bool structural_footer_at(const std::vector<u8>& bytes, size_t offset) {
  if(!magic_at(bytes, offset) || offset > bytes.size() ||
     sizeof(Footer) > bytes.size() - offset) return false;
  return get_le16(bytes, offset + offsetof(Footer, version)) ==
             resident_firmware_format::VERSION &&
         get_le16(bytes, offset + offsetof(Footer, size)) == sizeof(Footer) &&
         get_le32(bytes, offset + offsetof(Footer, image_start)) ==
             resident_firmware_format::IMAGE_START;
}

size_t find_footer(const std::vector<u8>& bytes) {
  size_t found = std::numeric_limits<size_t>::max();
  for(size_t offset = 0; offset + sizeof(Footer) <= bytes.size(); offset++) {
    if(!structural_footer_at(bytes, offset)) continue;
    if(found != std::numeric_limits<size_t>::max())
      fail("multiple resident firmware footers");
    found = offset;
  }
  if(found == std::numeric_limits<size_t>::max())
    fail("resident firmware footer not found");
  if((found & 3U) != 0) fail("resident firmware footer is not aligned");
  return found;
}

u32 canonical_crc(std::vector<u8>& bytes, size_t footer) {
  const size_t crc_offset = footer +
      resident_firmware_format::CRC32_OFFSET;
  const size_t build_offset = footer +
      resident_firmware_format::BUILD_ID_OFFSET;
  const u32 stored_crc = get_le32(bytes, crc_offset);
  const u32 stored_build = get_le32(bytes, build_offset);
  put_le32(bytes, crc_offset, 0);
  put_le32(bytes, build_offset, 0);
  const u32 result = crc32(bytes);
  put_le32(bytes, crc_offset, stored_crc);
  put_le32(bytes, build_offset, stored_build);
  return result;
}

void validate_static_fields(const std::vector<u8>& bytes, size_t footer) {
  const u32 profile = get_le32(bytes, footer + offsetof(Footer, profile_id));
  const u32 flags = get_le32(bytes, footer + offsetof(Footer, flags));
  const u32 reserved = get_le32(bytes, footer + offsetof(Footer, reserved));
  if(profile == 0)
    fail("resident footer has an invalid profile identity");
  if((flags & resident_firmware_format::FLAG_CRC_REQUIRED) == 0)
    fail("resident image was not compiled with CRC required");
  if((flags & ~resident_firmware_format::KNOWN_FLAGS) != 0 || reserved != 0)
    fail("resident footer has unsupported flags/reserved data");
}

void inspect_or_seal(const Options& options) {
  std::vector<u8> bytes = read_file(options.input);
  if(bytes.size() > options.maximum_size)
    fail("resident image exceeds configured Flash capacity");
  if(bytes.size() > std::numeric_limits<u32>::max())
    fail("resident image is too large for footer format");
  const size_t footer = find_footer(bytes);
  validate_static_fields(bytes, footer);

  const size_t image_size_offset = footer +
      resident_firmware_format::IMAGE_SIZE_OFFSET;
  const size_t crc_offset = footer +
      resident_firmware_format::CRC32_OFFSET;
  const size_t build_offset = footer +
      resident_firmware_format::BUILD_ID_OFFSET;
  if(options.seal) {
    put_le32(bytes, image_size_offset, (u32) bytes.size());
    put_le32(bytes, crc_offset, 0);
    put_le32(bytes, build_offset, 0);
    const u32 checksum = crc32(bytes);
    put_le32(bytes, crc_offset, checksum);
    put_le32(bytes, build_offset, checksum);
    if(canonical_crc(bytes, footer) != checksum)
      fail("internal post-link CRC verification failed");
    write_file(options.output, bytes);
  }

  const u32 declared_size = get_le32(bytes, image_size_offset);
  const u32 expected = get_le32(bytes, crc_offset);
  const u32 build = get_le32(bytes, build_offset);
  const u32 actual = canonical_crc(bytes, footer);
  if(declared_size != bytes.size())
    fail("resident footer image size does not match BIN");
  if(actual != expected)
    fail("resident firmware CRC mismatch");
  if(build == 0 || build != expected)
    fail("resident firmware build identity mismatch");

  std::printf(
      "resident firmware: %s size=%zu footer=%zu crc=%08lX build=%08lX profile=%08lX\n",
      options.seal ? "sealed" : "valid", bytes.size(), footer,
      (unsigned long) expected,
      (unsigned long) build,
      (unsigned long) get_le32(bytes, footer + offsetof(Footer, profile_id)));
}

Options parse_options(int argc, char** argv) {
  if(argc < 3) fail(
      "usage: mk61_firmware_seal <seal|check> [--max-size BYTES] INPUT [OUTPUT]");
  Options result = {};
  const std::string mode = argv[1];
  if(mode == "seal") result.seal = true;
  else if(mode == "check") result.seal = false;
  else fail("first argument must be seal or check");

  int index = 2;
  if(index < argc && std::string(argv[index]) == "--max-size") {
    if(++index >= argc) fail("--max-size requires a value");
    const std::string text = argv[index++];
    size_t consumed = 0;
    unsigned long long value = 0;
    try {
      value = std::stoull(text, &consumed, 10);
    } catch(...) {
      fail("invalid --max-size value");
    }
    if(consumed != text.size() || value == 0 ||
       value > std::numeric_limits<size_t>::max())
      fail("invalid --max-size value");
    result.maximum_size = (size_t) value;
  }
  if(index >= argc) fail("input BIN is missing");
  result.input = argv[index++];
  if(result.seal) {
    result.output = index < argc ? argv[index++] : result.input;
  } else {
    result.output = result.input;
  }
  if(index != argc) fail("unexpected extra argument");
  return result;
}

} // namespace

int main(int argc, char** argv) {
  try {
    inspect_or_seal(parse_options(argc, argv));
    return 0;
  } catch(const std::exception& error) {
    std::fprintf(stderr, "mk61_firmware_seal: %s\n", error.what());
    return 2;
  }
}
