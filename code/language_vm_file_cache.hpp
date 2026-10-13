#ifndef MK61_LANGUAGE_VM_FILE_CACHE_HPP
#define MK61_LANGUAGE_VM_FILE_CACHE_HPP
#ifndef MK61_VM_FILE_CACHE
#define MK61_VM_FILE_CACHE 0
#endif
#if MK61_VM_FILE_CACHE != 0 && MK61_VM_FILE_CACHE != 1
#error "MK61_VM_FILE_CACHE must be 0 or 1"
#endif
#include "language_bytecode.hpp"
#include "loadable_module_format.hpp"
namespace language_vm::file_cache {
// Cache data uses an ordinary, valid C6 container: no filesystem migration,
// new file type or extra native execution path. Its four-byte entry rejects
// INITIALIZE, so opening a cache file cannot execute its bytecode as ARM.
static constexpr unsigned KEY_BYTES=24;
static constexpr unsigned MAX_FILES=32, MAX_TOTAL_BYTES=65536;
static constexpr char DRIVER_PATH[]="/System/VMCache/VMSTORE.APP";
struct Key {
  uint32_t compiler_crc,source_crc;
  uint16_t source_id,source_size;
  Language language;
};
bool pack(const Key&,const uint8_t* image,uint16_t size,
          uint8_t* output,uint16_t capacity,uint16_t& written);
// Full C6 CRCs, key, canonical literal-only recipe and non-executable entry
// are checked. The returned span still needs the ordinary VM verifier.
bool view(const Key&,const uint8_t* file,uint16_t size,
          const uint8_t*& image,uint16_t& image_size);
// Before replacing a stale entry, prove it is our valid cache for this source.
// A colliding filename or damaged/unrecognised file is never overwritten.
bool owned(uint16_t source_id,Language,const uint8_t* file,uint16_t size);
enum Phase:uint32_t { TRY_LOAD=0x200, LOAD_RESERVED, STORE_COMPILED, START_LOADED, AFTER_DISCARD };
}
#endif
