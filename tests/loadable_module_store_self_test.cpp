#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "../code/loadable_module_store.hpp"

using namespace loadable_module;

namespace {

struct FakeFlash {
  std::vector<u8> bytes;
  int fail_after;
  int mutations;

  explicit FakeFlash(u32 size)
      : bytes(size, 0xFF), fail_after(-1), mutations(0) {}

  bool mutation_allowed(void) {
    if(fail_after >= 0 && mutations >= fail_after) return false;
    mutations++;
    return true;
  }
};

static bool flash_read(void* context, u32 address, u8* output, usize size) {
  FakeFlash& flash = *(FakeFlash*) context;
  if(output == nullptr || address > flash.bytes.size() ||
     size > flash.bytes.size() - address) return false;
  memcpy(output, flash.bytes.data() + address, size);
  return true;
}

static bool flash_program(void* context, u32 address, const u8* data,
                          usize size) {
  FakeFlash& flash = *(FakeFlash*) context;
  if(data == nullptr || address > flash.bytes.size() ||
     size > flash.bytes.size() - address || !flash.mutation_allowed()) {
    return false;
  }
  for(usize index = 0; index < size; index++) {
    if((flash.bytes[address + index] & data[index]) != data[index]) return false;
  }
  for(usize index = 0; index < size; index++) {
    flash.bytes[address + index] &= data[index];
  }
  return true;
}

static bool flash_erase(void* context, u32 address) {
  FakeFlash& flash = *(FakeFlash*) context;
  if(address % storage_geometry::PHYSICAL_SECTOR_SIZE != 0 ||
     address > flash.bytes.size() ||
     storage_geometry::PHYSICAL_SECTOR_SIZE > flash.bytes.size() - address ||
     !flash.mutation_allowed()) return false;
  memset(flash.bytes.data() + address, 0xFF,
         storage_geometry::PHYSICAL_SECTOR_SIZE);
  return true;
}

static Storage storage_for(FakeFlash& flash) {
  const Storage storage = {&flash, flash_read, flash_program, flash_erase};
  return storage;
}

struct MemorySource {
  std::vector<u8> bytes;
};

static bool source_read(void* context, u32 offset, u8* output, usize size) {
  MemorySource& source = *(MemorySource*) context;
  if(output == nullptr || offset > source.bytes.size() ||
     size > source.bytes.size() - offset) return false;
  memcpy(output, source.bytes.data() + offset, size);
  return true;
}

static ModuleSource source_for(MemorySource& source) {
  const ModuleSource result = {
    &source, (u32) source.bytes.size(), source_read
  };
  return result;
}

static storage_geometry::Geometry geometry(void) {
  storage_geometry::Geometry result;
  assert(storage_geometry::compute(2U * 1024U * 1024U, result,
                                   storage_geometry::MODULE_ALL));
  assert(result.module_first_sector != 0);
  return result;
}

static MemorySource make_module(Kind kind, u8 seed) {
  const u32 payload_size = kind == Kind::WBMP_VIEWER ? 777 : 2345;
  MemorySource source;
  source.bytes.resize(HEADER_SIZE + payload_size);
  for(u32 index = 0; index < payload_size; index++) {
    source.bytes[HEADER_SIZE + index] = (u8) (seed + index * 17U);
  }
  Header header = {};
  header.kind = kind;
  header.compression = Compression::ZX0;
  header.load_address = DEFAULT_LOAD_ADDRESS;
  header.stored_size = payload_size;
  header.image_size = payload_size + 100;
  header.memory_size = payload_size + 200;
  header.entry_offset = 4;
  header.resident_size = 170000;
  header.resident_crc32 = 0x12345678UL;
  header.stored_crc32 = crc32(source.bytes.data() + HEADER_SIZE, payload_size);
  header.image_crc32 = 0x87654321UL;
  Slot slot;
  assert(find_slot(geometry(), kind, slot));
  assert(encode_header(header, slot.size, source.bytes.data()));
  return source;
}

static void test_slot_layout(void) {
  const storage_geometry::Geometry layout = geometry();
  Slot focal;
  Slot basic;
  Slot viewer;
  assert(find_slot(layout, Kind::FOCAL, focal));
  assert(find_slot(layout, Kind::TINYBASIC, basic));
  assert(find_slot(layout, Kind::WBMP_VIEWER, viewer));
  assert(focal.address ==
         layout.module_first_sector * storage_geometry::PHYSICAL_SECTOR_SIZE);
  assert(focal.address + focal.size == basic.address);
  assert(basic.address + basic.size == viewer.address);
  assert(viewer.address + viewer.size ==
         layout.settings_sector * storage_geometry::PHYSICAL_SECTOR_SIZE);

  storage_geometry::Geometry small;
  assert(storage_geometry::compute(512U * 1024U, small,
                                   storage_geometry::MODULE_ALL));
  assert(!find_slot(small, Kind::FOCAL, focal));

  storage_geometry::Geometry focal_only;
  assert(storage_geometry::compute(2U * 1024U * 1024U, focal_only,
                                   storage_geometry::MODULE_FOCAL));
  assert(find_slot(focal_only, Kind::FOCAL, focal));
  assert(!find_slot(focal_only, Kind::TINYBASIC, basic));
  assert(!find_slot(focal_only, Kind::WBMP_VIEWER, viewer));
}

static void test_install_inspect_remove(void) {
  const storage_geometry::Geometry layout = geometry();
  FakeFlash flash(layout.capacity_bytes);
  const Storage storage = storage_for(flash);
  MemorySource source = make_module(Kind::FOCAL, 11);
  Header installed = {};
  assert(install(storage, layout, Kind::FOCAL, source_for(source),
                 &installed) == StoreStatus::OK);
  assert(installed.kind == Kind::FOCAL);
  Header inspected = {};
  assert(inspect(storage, layout, Kind::FOCAL, inspected) == StoreStatus::OK);
  assert(inspected.stored_crc32 == installed.stored_crc32);

  u8 sample[19] = {};
  assert(read_payload(storage, layout, Kind::FOCAL, 23, sample,
                      sizeof(sample)));
  assert(memcmp(sample, source.bytes.data() + HEADER_SIZE + 23,
                sizeof(sample)) == 0);

  assert(remove(storage, layout, Kind::FOCAL) == StoreStatus::OK);
  assert(inspect(storage, layout, Kind::FOCAL, inspected) ==
         StoreStatus::INVALID_HEADER);
}

static void test_bad_source_does_not_erase_installed_module(void) {
  const storage_geometry::Geometry layout = geometry();
  FakeFlash flash(layout.capacity_bytes);
  const Storage storage = storage_for(flash);
  MemorySource good = make_module(Kind::TINYBASIC, 21);
  assert(install(storage, layout, Kind::TINYBASIC, source_for(good)) ==
         StoreStatus::OK);
  const int mutations = flash.mutations;

  MemorySource bad = make_module(Kind::TINYBASIC, 99);
  bad.bytes.back() ^= 1;
  assert(install(storage, layout, Kind::TINYBASIC, source_for(bad)) ==
         StoreStatus::BAD_STORED_CRC);
  assert(flash.mutations == mutations);
  Header inspected = {};
  assert(inspect(storage, layout, Kind::TINYBASIC, inspected) ==
         StoreStatus::OK);
  assert(inspected.stored_crc32 ==
         crc32(good.bytes.data() + HEADER_SIZE,
               good.bytes.size() - HEADER_SIZE));
}

static void test_header_is_committed_last(void) {
  const storage_geometry::Geometry layout = geometry();
  MemorySource source = make_module(Kind::WBMP_VIEWER, 31);

  FakeFlash control(layout.capacity_bytes);
  const Storage control_storage = storage_for(control);
  assert(install(control_storage, layout, Kind::WBMP_VIEWER,
                 source_for(source)) == StoreStatus::OK);
  const int operation_count = control.mutations;

  for(int cut = 0; cut <= operation_count; cut++) {
    FakeFlash flash(layout.capacity_bytes);
    flash.fail_after = cut;
    const Storage storage = storage_for(flash);
    const StoreStatus status = install(storage, layout, Kind::WBMP_VIEWER,
                                       source_for(source));
    flash.fail_after = -1;
    Header inspected = {};
    const StoreStatus after = inspect(storage, layout, Kind::WBMP_VIEWER,
                                      inspected);
    if(status == StoreStatus::OK) {
      assert(after == StoreStatus::OK);
      assert(inspected.stored_crc32 ==
             crc32(source.bytes.data() + HEADER_SIZE,
                   source.bytes.size() - HEADER_SIZE));
    } else {
      assert(after != StoreStatus::OK);
    }
  }
}

static void test_payload_corruption_is_detected(void) {
  const storage_geometry::Geometry layout = geometry();
  FakeFlash flash(layout.capacity_bytes);
  const Storage storage = storage_for(flash);
  MemorySource source = make_module(Kind::FOCAL, 44);
  assert(install(storage, layout, Kind::FOCAL, source_for(source)) ==
         StoreStatus::OK);
  Slot slot;
  assert(find_slot(layout, Kind::FOCAL, slot));
  flash.bytes[slot.address + HEADER_SIZE + 3] ^= 1;
  Header inspected = {};
  assert(inspect(storage, layout, Kind::FOCAL, inspected) ==
         StoreStatus::BAD_STORED_CRC);
}

} // namespace

int main(void) {
  test_slot_layout();
  test_install_inspect_remove();
  test_bad_source_does_not_erase_installed_module();
  test_header_is_committed_last();
  test_payload_corruption_is_detected();
  printf("loadable_module_store_self_test: ok\n");
  return 0;
}
