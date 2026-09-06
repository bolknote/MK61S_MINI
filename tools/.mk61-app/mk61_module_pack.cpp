#include "loadable_module_format.hpp"
#include "storage_geometry.hpp"
#include "zx0.hpp"
#include "arm_thumb_bcj.hpp"

#include "third_party/zx0/zx0.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using loadable_module::Compression;
using loadable_module::Header;
using loadable_module::Kind;

static constexpr int ZX0_MAX_OFFSET = 32640;

struct Options {
  Kind kind = Kind::FOCAL;
  bool kind_set = false;
  std::filesystem::path resident;
  std::filesystem::path image;
  std::filesystem::path relocations;
  std::filesystem::path output;
  u32 memory_size = 0;
  u32 entry_offset = 0;
  u32 load_address = 0;
  u16 handled_type_magic = 0;
  bool memory_size_set = false;
  bool entry_offset_set = false;
  bool load_address_set = false;
  bool require_zx0 = false;
  bool portable = false;
};

[[noreturn]] void usage(const char* message = nullptr) {
  if(message != nullptr) std::fprintf(stderr, "error: %s\n\n", message);
  std::fprintf(stderr,
      "usage: mk61_module_pack --kind KIND (--resident FILE | --portable) --image FILE\n"
      "       --memory-size N --entry-offset N --load-address N\n"
      "       --output FILE [--handled-magic XX] [--require-zx0]\n"
      "  --kind KIND          app, focal, tinybasic, wbmp-viewer,\n"
      "                       markdown-viewer, chip8, or setup\n"
      "  --resident FILE      exact resident firmware .bin\n"
      "  --portable           standalone; best of ZX0 / BCJ+ZX0\n"
      "  --relocations FILE   add compact relocation table (ABI 4; otherwise ABI 3)\n"
      "  --image FILE         linked SRAM image without its .bss tail\n"
      "  --memory-size N      image plus zero-filled .bss\n"
      "  --entry-offset N     module entry offset from the load address\n"
      "  --load-address N     linked SRAM base (portable: 0x20000000)\n"
      "  --handled-magic XX   two-byte C5 type magic handled by FILE_OPEN\n"
      "  --require-zx0        reject an uncompressed result\n"
      "  --output FILE        resulting .APP container\n");
  std::exit(message == nullptr ? 0 : 2);
}

u32 parse_u32(const std::string& text, const char* name) {
  std::size_t end = 0;
  unsigned long long value = 0;
  try {
    value = std::stoull(text, &end, 0);
  } catch(const std::exception&) {
    throw std::runtime_error(std::string("invalid ") + name + ": " + text);
  }
  if(end != text.size() || value > std::numeric_limits<u32>::max()) {
    throw std::runtime_error(std::string("invalid ") + name + ": " + text);
  }
  return (u32) value;
}

Kind parse_kind(const std::string& text) {
  if(text == "setup") return Kind::SETUP;
  if(text == "app") return Kind::APPLICATION;
  if(text == "focal") return Kind::FOCAL;
  if(text == "tinybasic") return Kind::TINYBASIC;
  if(text == "wbmp-viewer") return Kind::WBMP_VIEWER;
  if(text == "markdown-viewer") return Kind::MARKDOWN_VIEWER;
  if(text == "chip8") return Kind::CHIP8;
  throw std::runtime_error("unknown module kind: " + text);
}

u16 parse_type_magic(const std::string& text) {
  const auto ascii_alnum = [](unsigned char value) {
    return (value >= '0' && value <= '9') ||
           (value >= 'A' && value <= 'Z') ||
           (value >= 'a' && value <= 'z');
  };
  if(text.size() != 2 || !ascii_alnum((unsigned char) text[0]) ||
     !ascii_alnum((unsigned char) text[1])) {
    throw std::runtime_error(
        "handled magic must contain exactly two ASCII letters or digits");
  }
  return (u16) (u8) text[0] | ((u16) (u8) text[1] << 8);
}

Options parse_options(int argc, char** argv) {
  Options options;
  for(int index = 1; index < argc; index++) {
    const std::string option = argv[index];
    if(option == "--help" || option == "-h") usage();
    if(option == "--require-zx0") {
      options.require_zx0 = true;
      continue;
    }
    if(option == "--portable") {
      options.portable = true;
      options.require_zx0 = true;
      continue;
    }
    if(index + 1 >= argc) usage(("missing value for " + option).c_str());
    const std::string value = argv[++index];
    if(option == "--kind") {
      options.kind = parse_kind(value);
      options.kind_set = true;
    } else if(option == "--resident") {
      options.resident = value;
    } else if(option == "--relocations") {
      options.relocations = value;
    } else if(option == "--image") {
      options.image = value;
    } else if(option == "--memory-size") {
      options.memory_size = parse_u32(value, "memory size");
      options.memory_size_set = true;
    } else if(option == "--entry-offset") {
      options.entry_offset = parse_u32(value, "entry offset");
      options.entry_offset_set = true;
    } else if(option == "--load-address") {
      options.load_address = parse_u32(value, "load address");
      options.load_address_set = true;
    } else if(option == "--handled-magic") {
      options.handled_type_magic = parse_type_magic(value);
    } else if(option == "--output") {
      options.output = value;
    } else {
      usage(("unknown option: " + option).c_str());
    }
  }
  if(!options.portable && !options.relocations.empty()) usage("relocations require --portable");
  if(options.portable) {
    if(!options.resident.empty() ||
       (options.load_address_set &&
        options.load_address != MK61_PORTABLE_APP_ADDRESS)) {
      usage("portable APP requires no resident and fixed SRAM");
    }
    options.load_address = MK61_PORTABLE_APP_ADDRESS;
    options.load_address_set = true;
  }
  if(!options.kind_set || (!options.portable && options.resident.empty()) ||
     options.image.empty() ||
     options.output.empty() || !options.memory_size_set ||
     !options.entry_offset_set || !options.load_address_set) {
    usage("all required options must be specified");
  }
  return options;
}

std::vector<u8> read_file(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if(!input) throw std::runtime_error("cannot open " + path.string());
  const std::streamoff end = input.tellg();
  if(end < 0 || (unsigned long long) end > std::numeric_limits<u32>::max()) {
    throw std::runtime_error("unsupported file size: " + path.string());
  }
  std::vector<u8> bytes((usize) end);
  input.seekg(0);
  if(!bytes.empty() &&
     !input.read((char*) bytes.data(), (std::streamsize) bytes.size())) {
    throw std::runtime_error("cannot read " + path.string());
  }
  return bytes;
}

void write_file(const std::filesystem::path& path,
                const std::vector<u8>& bytes) {
  if(!path.parent_path().empty()) {
    std::filesystem::create_directories(path.parent_path());
  }
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if(!output || (!bytes.empty() &&
      !output.write((const char*) bytes.data(),
                    (std::streamsize) bytes.size()))) {
    throw std::runtime_error("cannot write " + path.string());
  }
}

std::vector<u8> zx0_encode_optimal(const std::vector<u8>& input) {
  if(input.empty()) return {};
  if(input.size() > (usize) std::numeric_limits<int>::max()) {
    throw std::runtime_error("ZX0 input is too large");
  }
  std::vector<u8> mutable_input = input;
  const int input_size = (int) mutable_input.size();
  BLOCK* optimal = optimize(mutable_input.data(), input_size, 0,
                            ZX0_MAX_OFFSET);
  if(optimal == nullptr) throw std::runtime_error("ZX0 optimizer failed");
  int output_size = 0;
  int delta = 0;
  unsigned char* output = compress(optimal, mutable_input.data(), input_size,
                                   0, 0, 1, &output_size, &delta);
  if(output == nullptr || output_size <= 0) {
    std::free(output);
    throw std::runtime_error("ZX0 compressor failed");
  }
  std::vector<u8> result(output, output + output_size);
  std::free(output);
  return result;
}

struct VectorInput {
  const std::vector<u8>& bytes;
  usize position = 0;
};

bool next_vector_byte(void* context, u8& value) {
  VectorInput& input = *(VectorInput*) context;
  if(input.position >= input.bytes.size()) return false;
  value = input.bytes[input.position++];
  return true;
}

void verify_zx0(const std::vector<u8>& packed,
                const std::vector<u8>& expected) {
  VectorInput input = {packed, 0};
  const zx0::Input source = {&input, next_vector_byte};
  std::vector<u8> decoded(expected.size());
  u32 written = 0;
  if(!zx0::decode(source, (u32) packed.size(), decoded.data(),
                  (u32) decoded.size(), written) ||
     written != decoded.size() || input.position != packed.size() ||
     decoded != expected) {
    throw std::runtime_error("internal ZX0 verification failed");
  }
}

u32 slot_size(Kind kind) {
  return loadable_module::valid_kind(kind)
      ? loadable_module::MAX_CONTAINER_SIZE : 0;
}

std::vector<u8> pack(const Options& options, const std::vector<u8>& resident,
                     const std::vector<u8>& image) {
  if(!options.portable && (resident.empty() ||
     resident.size() > loadable_module::MAX_RESIDENT_SIZE)) {
    throw std::runtime_error(
        "resident image size is outside the supported range");
  }
  if(image.empty() || image.size() > options.memory_size ||
     options.memory_size > loadable_module::OVERLAY_SIZE) {
    throw std::runtime_error("module image does not fit the SRAM overlay");
  }
  if(options.entry_offset >= image.size() ||
     (options.entry_offset & 1U) != 0) {
    throw std::runtime_error(
        "entry offset must be aligned and inside the image");
  }
  if(options.load_address < loadable_module::SRAM_FIRST_ADDRESS ||
     options.load_address > loadable_module::SRAM_LAST_ADDRESS -
                                loadable_module::OVERLAY_SIZE ||
     (options.load_address & 7U) != 0) {
    throw std::runtime_error(
        "load address is outside aligned STM32F401/F411 SRAM");
  }

  std::vector<u8> stored = zx0_encode_optimal(image);
  verify_zx0(stored, image);
  u32 flags = options.portable ? MK61_PORTABLE_APP_FLAG : 0;
  if(options.portable) {
    std::vector<u8> filtered = image;
    arm_thumb_bcj::transform(filtered.data(), (u32) filtered.size(), true);
    std::vector<u8> candidate = zx0_encode_optimal(filtered);
    verify_zx0(candidate, filtered);
    arm_thumb_bcj::transform(filtered.data(), (u32) filtered.size(), false);
    if(filtered != image) throw std::runtime_error("BCJ round-trip failed");
    // Same header size; ties keep the plain stream and skip the inverse pass.
    std::printf("ZX0 candidates: plain=%zu BCJ=%zu; selected=%s\n",
                stored.size(), candidate.size(),
                candidate.size() < stored.size() ? "BCJ" : "plain");
    if(candidate.size() < stored.size()) {
      stored.swap(candidate);
      flags |= MK61_APP_ARM_THUMB_BCJ_FLAG;
    }
  }
  Compression compression = Compression::ZX0;
  if(!options.require_zx0 && stored.size() >= image.size()) {
    stored = image;
    compression = Compression::NONE;
  }

  const u32 code_stored_size = (u32) stored.size();
  u32 relocation_count = 0;
  if(!options.relocations.empty()) {
    // Empty tables are valid for position-independent images.
    std::ifstream file(options.relocations, std::ios::binary);
    if(!file) throw std::runtime_error("cannot read relocation table");
    const std::vector<u8> table((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    for(u8 byte : table) if(!(byte & 128U)) ++relocation_count;
    stored.insert(stored.end(), table.begin(), table.end());
    flags |= MK61_APP_RELOCATABLE_FLAG;
  }
  const u32 limit = slot_size(options.kind);
  if(stored.size() + loadable_module::HEADER_SIZE > limit) {
    throw std::runtime_error(
        "module uses " +
        std::to_string(stored.size() + loadable_module::HEADER_SIZE) +
        " bytes; slot limit is " + std::to_string(limit));
  }

  Header header = {};
  header.flags = flags;
  header.kind = options.kind;
  header.compression = compression;
  header.load_address = options.load_address;
  header.stored_size = (u32) stored.size();
  header.image_size = (u32) image.size();
  header.memory_size = options.memory_size;
  header.entry_offset = options.entry_offset;
  header.resident_size = (u32) resident.size();
  header.resident_crc32 =
      loadable_module::crc32(resident.data(), resident.size());
  if(flags & MK61_APP_RELOCATABLE_FLAG) {
    header.code_stored_size = code_stored_size;
    header.relocation_count = relocation_count;
  }
  header.stored_crc32 =
      loadable_module::crc32(stored.data(), stored.size());
  header.image_crc32 =
      loadable_module::crc32(image.data(), image.size());
  header.handled_type_magic = options.handled_type_magic;

  const loadable_module::Reader reader = {&stored,
      [](void* context, u32 offset, u8* out, usize size) -> bool {
        const auto& data = *(const std::vector<u8>*) context;
        if(offset > data.size() || size > data.size() - offset) return false;
        std::memcpy(out, data.data() + offset, size); return true;
      }};
  std::vector<u8> verified(image.size());
  if(!loadable_module::decode_image(header, reader, verified.data(), header.load_address) || verified != image)
    throw std::runtime_error("APP decode/relocation verification failed");

  std::vector<u8> module(loadable_module::HEADER_SIZE + stored.size());
  if(!loadable_module::encode_header(header, limit, module.data())) {
    throw std::runtime_error("cannot encode module header");
  }
  std::copy(stored.begin(), stored.end(),
            module.begin() + loadable_module::HEADER_SIZE);
  return module;
}

} // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    const std::vector<u8> resident = options.portable
        ? std::vector<u8>{} : read_file(options.resident);
    const std::vector<u8> image = read_file(options.image);
    const std::vector<u8> module = pack(options, resident, image);
    write_file(options.output, module);
    const double ratio =
        (double) (module.size() - loadable_module::HEADER_SIZE) /
        (double) image.size();
    std::printf("%s: %zu bytes, payload ratio %.1f%%\n",
                options.output.string().c_str(), module.size(), ratio * 100.0);
    return 0;
  } catch(const std::exception& error) {
    std::fprintf(stderr, "mk61_module_pack: %s\n", error.what());
    return 2;
  }
}
