#ifndef MK61_LOADABLE_MODULE_RUNTIME_HPP
#define MK61_LOADABLE_MODULE_RUNTIME_HPP

#include "config.h"
#include "loadable_module_abi.hpp"
#include "loadable_module_format.hpp"

namespace loadable_module {

struct ModuleSource {
  void* context;
  u32 size;
  bool (*read)(void* context, u32 offset, u8* output, usize size);
};

enum class StoreStatus : u8 {
  OK = 0,
  UNAVAILABLE,
  IO_ERROR,
  INVALID_HEADER,
  WRONG_FILE_SIZE,
  BAD_STORED_CRC,
  INCOMPATIBLE_FIRMWARE
};

enum class RuntimeStatus : u8 {
  OK = 0,
  DISABLED,
  UNAVAILABLE,
  INVALID_MODULE,
  INCOMPATIBLE_FIRMWARE,
  CORRUPT_MODULE,
  BUSY,
  IO_ERROR
};

bool enabled(Kind kind);
RuntimeStatus status(Kind kind);
const char* status_text(RuntimeStatus status);

RuntimeStatus invoke(Kind kind, Command command,
                     u32 argument0, u32 argument1,
                     u32 argument2, u32 argument3,
                     u32& result);
RuntimeStatus run_app(u16 file_id, u32& result);

inline RuntimeStatus invoke(Kind kind, Command command, u32& result) {
  return invoke(kind, command, 0, 0, 0, 0, result);
}

// Проверяет обычный C5-файл .APP до атомарной замены: заголовок, привязку к
// resident, CRC сжатого потока, корректность распаковки и CRC SRAM-образа.
StoreStatus validate_app(const ModuleSource& source, Header& header);

} // namespace loadable_module

#endif
