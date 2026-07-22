#ifndef MK61_LOADABLE_MODULE_STORE_HPP
#define MK61_LOADABLE_MODULE_STORE_HPP

#include "loadable_module_format.hpp"
#include "storage_geometry.hpp"

namespace loadable_module {

struct Slot {
  u32 address;
  u32 size;
};

struct Storage {
  void* context;
  bool (*read)(void* context, u32 address, u8* output, usize size);
  bool (*program)(void* context, u32 address, const u8* data, usize size);
  bool (*erase_sector)(void* context, u32 address);
};

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
  INCOMPATIBLE_FIRMWARE,
  VERIFY_FAILED
};

bool find_slot(const storage_geometry::Geometry& geometry, Kind kind,
               Slot& output);

StoreStatus validate_source(const storage_geometry::Geometry& geometry,
                            Kind kind, const ModuleSource& source,
                            Header& output);

StoreStatus read_header(const Storage& storage,
                        const storage_geometry::Geometry& geometry,
                        Kind kind, Header& output);

// inspect() проверяет заголовок и CRC хранимого потока. CRC распакованного
// образа проверяется загрузчиком непосредственно перед передачей управления.
StoreStatus inspect(const Storage& storage,
                    const storage_geometry::Geometry& geometry,
                    Kind kind, Header& output);

// Источник — готовый файл .MOD: 64-байтовый заголовок и сжатый поток.
// Сначала стираются слоты и программируется поток, а заголовок записывается
// последним. При потере питания неполная запись никогда не выглядит валидной.
StoreStatus install(const Storage& storage,
                    const storage_geometry::Geometry& geometry,
                    Kind kind, const ModuleSource& source,
                    Header* installed = nullptr);

// Для удаления достаточно стереть первый сектор: там находятся и заголовок,
// и начало потока. Остальные сектора будут очищены при следующей установке.
StoreStatus remove(const Storage& storage,
                   const storage_geometry::Geometry& geometry,
                   Kind kind);

bool read_payload(const Storage& storage,
                  const storage_geometry::Geometry& geometry,
                  Kind kind, u32 offset, u8* output, usize size);

bool read_container(const Storage& storage,
                    const storage_geometry::Geometry& geometry,
                    Kind kind, u32 offset, u8* output, usize size);

} // namespace loadable_module

#endif
