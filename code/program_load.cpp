#include "program_load.hpp"
#include "crc32.hpp"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "zx0_stream.hpp"

namespace program_load {
namespace {
bool failed = false;
u16 written_bytes = 0;
const char* last_error = nullptr;

bool fail(const char* message) {
  failed = true;
  return reject(message);
}
bool read(void* context, u16 position, u8& value) {
  return core_61::read_absolute_program(*static_cast<u16*>(context) + position, value);
}
bool write(void* context, u16 position, u8 value) {
  if(!core_61::write_absolute_program(*static_cast<u16*>(context) + position, value))
    return false;
  written_bytes = position + 1;
  return true;
}
bool space(char ch) { return ch == ' ' || ch == '\t'; }
bool end(char ch) { return ch == 0 || ch == '\r' || ch == '\n'; }
const char* skip(const char* p) { while(p != nullptr && space(*p)) ++p; return p; }
} // namespace

void reset() { failed = false; written_bytes = 0; last_error = nullptr; }
bool blocked() { return failed; }
const char* error() { return last_error == nullptr ? "Binary load failed; use reinit" : last_error; }
u16 written() { return written_bytes; }
bool reject(const char* message) { last_error = message; return false; }

Syntax parse(const char* args, Request& request) {
  const char* p = skip(args);
  if(p == nullptr) return Syntax::LEGACY;
  u16 address = 0;
  usize digits = 0;
  while(*p >= '0' && *p <= '9') {
    if(digits < 4) address = address * 10 + (*p - '0');
    ++digits; ++p;
  }
  // A single number remains a legacy slot; paths starting with a number
  // (e.g. 2026.m61) also keep the existing file-load interpretation.
  if(digits == 0 || !space(*p) || end(*skip(p))) return Syntax::LEGACY;
  // Numeric file names may contain spaces: load 2026 demo.m61.
  const char* tail = p;
  while(!end(*tail)) ++tail;
  while(tail > p && space(tail[-1])) --tail;
  if(tail - p >= 4 && tail[-4] == '.' &&
     (tail[-3] == 'm' || tail[-3] == 'M') && tail[-2] == '6' && tail[-1] == '1')
    return Syntax::LEGACY;
  if(digits != 4) return Syntax::INVALID;
  request = {address, skip(p)};
  return Syntax::BINARY;
}

bool load(u16 file_id, u16 address, u16 limit) {
  if(failed) return reject("Binary load failed; use reinit");
  if(core_61::is_RUN()) return reject("Stop calculator before binary load");
  if(limit > core_61::EXTENDED_ADDRESS_LIMIT || address >= limit)
    return reject("Program address out of range");
  program_store::Entry entry;
  if(!program_store::entry_by_id(file_id, entry) ||
     entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::MK61_BINARY ||
     entry.data_len <= 4 || entry.data_len > program_store::MAX_MK61_BINARY_SIZE)
    return reject("Invalid binary program file");

  u8 bytes[128];
  u16 count = 0;
  if(!program_store::read_range_id(file_id, 0, bytes, 4, &count) || count != 4)
    return reject("Cannot read binary program");
  const u32 expected_crc = u32(bytes[0]) | (u32(bytes[1]) << 8) |
      (u32(bytes[2]) << 16) | (u32(bytes[3]) << 24);
  zx0::StreamDecoder decoder;
  decoder.reset({&address, read, write, u16(limit - address)});
  written_bytes = 0;
  for(u16 offset = 4; offset < entry.data_len;) {
    const u16 remaining = entry.data_len - offset;
    const u16 wanted = remaining < sizeof(bytes) ? remaining : sizeof(bytes);
    if(!program_store::read_range_id(file_id, offset, bytes, wanted, &count) || count != wanted)
      return fail("Cannot read binary program");
    for(u16 i = 0; i < count; ++i) {
      if(decoder.complete()) return fail("Data after ZX0 end marker");
      if(!decoder.feed(bytes[i])) return fail("Invalid ZX0 stream or program memory full");
    }
    offset += count;
  }
  if(!decoder.complete() || written_bytes == 0) return fail("Incomplete ZX0 program");

  // Storage also uses the hardware CRC. Acquire it only after all file reads,
  // then check the actual destination, including bytes copied by matches.
  mk61_crc32::Context crc;
  for(u16 i = 0; i < written_bytes; ++i) {
    u8 value;
    if(!read(&address, i, value)) return fail("Cannot read loaded program");
    crc.update_byte(value);
  }
  if(crc.finish() != expected_crc) return fail("Program CRC32 mismatch");
  last_error = nullptr;
  return true;
}
} // namespace program_load
