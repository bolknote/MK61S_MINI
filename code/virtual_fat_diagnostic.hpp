#ifndef MK61_VIRTUAL_FAT_DIAGNOSTIC_HPP
#define MK61_VIRTUAL_FAT_DIAGNOSTIC_HPP

#include "rust_types.h"
#include <type_traits>

namespace virtual_fat {

// Public diagnostic numbers: never renumber or reuse a retired value.
// 120x names; 121x geometry/chains; 122x limits; 123x I/O;
// 124x staging/commit; 125x native APP validation.
enum class ErrorCode : u16 {
  NONE = 0,
  NAME = 1201, NAME_TOO_LONG = 1202, DIRECTORY_ENTRY = 1203,
  DIRECTORY_CLUSTER = 1210, FILE_CLUSTER = 1211,
  DUPLICATE_CLUSTER = 1212, KIND_CHANGE = 1213,
  FILE_CHAIN = 1214, DIRECTORY_CHAIN = 1215, EXTENT_CHAIN = 1216,
  DEPTH = 1217, FILE_DATA = 1218, CLUSTER_LIMIT = 1219,
  EMPTY_FILE = 1220, FILE_TOO_LARGE = 1221,
  STORAGE_UNAVAILABLE = 1230, CACHE_WRITE = 1231, FAT_READ = 1232,
  ROOT_READ = 1233, DIRECTORY_READ = 1234, FILE_READ = 1235,
  PREPARE = 1240, APPLY = 1241, PRUNE = 1242,
  STAGE_DISCARD = 1243, DIRECTORY_EXTENTS = 1244,
  APP_STAGE = 1250, APP_STAGE_RESTORE = 1251, APP_INVALID = 1252,
  VALIDATE = 1253
};

enum class Phase : u8 {
  NONE = 0, SESSION = 1, CACHE = 2, ENTRY = 3, CHAIN = 4,
  VALIDATE = 5, PREPARE = 6, APPLY = 7, COMMIT = 8
};

enum DiagnosticFlag : u8 { RETRYABLE = 1, SUBJECT_TRUNCATED = 2 };

struct Diagnostic {
  ErrorCode code;
  Phase phase;
  u8 flags;
  u32 actual;
  u32 limit;
  char subject[16]; // Safe UTF-8 prefix, always terminated; never a full path.
};
static_assert(sizeof(Diagnostic) == 28, "VFAT diagnostic RAM contract");
static_assert(std::is_trivially_copyable<Diagnostic>::value,
              "VFAT diagnostic must remain a plain value");

// A new attempt keeps the previous report until a new error or a successful
// import. Unwinding an attempt cannot replace its first, deepest cause.
struct DiagnosticState {
  Diagnostic value;
  bool recorded;
  void begin_attempt();
  void clear();
  bool fail(ErrorCode code, Phase phase) {
    return record_simple((u16) ((u16) code | ((u16) phase << 11)));
  }
  bool fail(ErrorCode code, Phase phase, u32 actual, u32 limit = 0,
            const char* subject = nullptr, bool retryable = false) {
    // 11 code bits + 4 phase bits + retry bit fit one Thumb immediate.
    // This is an internal call representation, never a wire/storage layout.
    return record((u16) ((u16) code | ((u16) phase << 11) |
                    (retryable ? 0x8000U : 0)),
                  actual, limit, subject);
  }
  [[gnu::noinline]] bool record(u16 descriptor, u32 actual, u32 limit,
                                const char* subject);
  [[gnu::noinline]] bool record_simple(u16 descriptor);
};
static_assert((u16) ErrorCode::VALIDATE < 2048 && (u8) Phase::COMMIT < 16,
              "diagnostic call descriptor capacity");
static_assert(sizeof(DiagnosticState) <= 32, "VFAT diagnostic state budget");

// Text is serialized explicitly, independently of padding and host endianness.
// The subject is hex-encoded on the machine line, so it cannot inject fields.
static constexpr usize DIAGNOSTIC_LINE_SIZE = 128;
bool format_diagnostic(const Diagnostic& value, char* output, usize capacity);
void format_error_code(ErrorCode code, char (&output)[10]); // "USB E12xx"

} // namespace virtual_fat
#endif
