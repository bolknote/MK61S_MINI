#include "system_compat.hpp"
#include <assert.h>
#include <stdio.h>
#include <vector>
#include <string>
#include <cstring>

static std::vector<u8> source(1500, 'A');
static u32 result = 1;
static u32 calls;
static u32 time_ms;
extern "C" u32 millis() { return time_ms; }
void idle_main_process() {}

static u32 service(u32 operation, u32 op, u32 id, u32 index, void* payload) {
  assert(operation == MK61_SYS_USBDISK);
  if(op == MK61_USBDISK_STARTUP_STAGE) return 1;
  switch(op) {
    case MK61_USBDISK_C9_READY: return 9;
    case MK61_USBDISK_CATALOG_REVISION: return 123;
    case MK61_USBDISK_GEOMETRY: {
      auto& out = *(mk61_system_usbdisk_geometry*) payload;
      out = {}; out.max_nodes = 8192; out.sectors_per_cluster = 8;
      out.fat_sectors = 12; out.root_sectors = 32; out.logical_sectors = 32729;
      return 1;
    }
    case MK61_USBDISK_NODE_AVAILABLE: assert(id == 7890); return 1;
    case MK61_USBDISK_FAT_FIRST_CLUSTER:
    case MK61_USBDISK_FAT_CHAIN_COUNT:
    case MK61_USBDISK_FAT_CHAIN_CLUSTER: {
      assert(id == 7890);
      if(op == MK61_USBDISK_FAT_CHAIN_CLUSTER) assert(index == 40);
      ((mk61_system_usbdisk_extent*) payload)->id =
          op == MK61_USBDISK_FAT_FIRST_CLUSTER ? 17 : op == MK61_USBDISK_FAT_CHAIN_COUNT ? 41 : 73;
      return 1;
    }
    case MK61_USBDISK_FAT_CLUSTER_INFO: {
      assert(id == 73);
      auto& out = *(mk61_system_usbdisk_extent*) payload;
      out.owner = 7890; out.cluster_index = 40; out.next = 0xFFFF;
      return 1;
    }
    case MK61_USBDISK_IMPORT_PLAN_PUT:
    case MK61_USBDISK_IMPORT_PLAN_GET: {
      auto& request = *(mk61_system_usbdisk_extent*) payload;
      assert(request.id == 0 && request.cluster_index == 513);
      if(op == MK61_USBDISK_IMPORT_PLAN_PUT) {
        assert(request.owner == 7900 && request.next == 7890);
      } else { request.owner = 7900; request.next = 7890; }
      return 1;
    }
    case MK61_USBDISK_IMPORT_NAME_GET:
    case MK61_USBDISK_IMPORT_NAME_PUT: {
      assert(id == 123);
      auto& request = *(mk61_system_usbdisk_extent*) payload;
      if(op == MK61_USBDISK_IMPORT_NAME_PUT) assert(request.owner == 0xC99 && request.next == 987654);
      else { request.owner = 0xC99; request.next = 987654; }
      return 1;
    }
    case MK61_USBDISK_FAT_FIND_CHILD: {
      auto& request = *(mk61_system_usbdisk_name*) payload;
      assert(request.id == (u32) program_store::ProgramType::TEXT);
      assert(request.parent == 6000 && request.preferred == 0);
      assert(std::string(request.name) == "long name");
      request.out_id = 7890; return 1;
    }
    case MK61_USBDISK_CREATE_DIRECTORY_FROM_FAT: {
      auto& request = *(mk61_system_usbdisk_name*) payload;
      assert(request.id == 17 && request.parent == 6000 && request.preferred == 7891);
      request.out_id = 7891; return 1;
    }
    case MK61_USBDISK_SET_DIRECTORY_CHAIN: {
      const auto& request = *(mk61_system_usbdisk_source*) payload;
      assert(request.preferred == 7891 && request.size == 3);
      u8 bytes[4];
      assert(request.read(request.context, 2, bytes, sizeof(bytes)) == 1);
      assert(bytes[0] == 18 && bytes[1] == 0 && bytes[2] == 19 && bytes[3] == 0);
      assert(request.read(request.context, 6, bytes, 1) == 0);
      return 1;
    }
    case MK61_USBDISK_PREPARE_IMPORT_MAPPING: assert(id == 7890); return 1;
    case MK61_USBDISK_ENSURE_DIRECTORY_CHAIN: assert(id == 7891); return 1;
    case MK61_USBDISK_FAT_PROJECTION_BEGIN:
    case MK61_USBDISK_IMPORT_PLAN_BEGIN:
    case MK61_USBDISK_IMPORT_PLAN_END: return 1;
    default: break;
  }
  if(op == MK61_USBDISK_EXPORTED_SIZE) {
    assert(id == 7);
    *(u32*) payload = source.size();
    return 1;
  }
  assert(op == MK61_USBDISK_STREAM_FILE && id == 7);
  ++calls;
  const auto& sink = *(mk61_service_usbdisk_sink*) payload;
  for(u8 byte : source) {
    if(!sink.next(sink.context, byte)) return 0;
  }
  return result; // May report a late CRC failure after emitting all bytes.
}

namespace portable_system {
static mk61_system_api service_table = {};
const mk61_system_api* api = &service_table;
}

struct Capture {
  std::vector<u8> bytes;
  usize limit = 65535;
};
static bool append(void* context, u8 byte) {
  auto& out = *(Capture*) context;
  if(out.bytes.size() == out.limit) return false;
  out.bytes.push_back(byte);
  return true;
}

extern "C" void mk61_usbdisk_startup_stage(u32);

static bool read_clusters(void* context, u32 offset, u8* data, usize size) {
  if(offset > 6 || size > 6 - offset) return false;
  memcpy(data, (const u8*) context + offset, size);
  return true;
}

static void test_c9_wire() {
  using namespace program_store;
  assert(ready() && format_version() == 9);
  assert(catalog_revision() == 123 && max_fat_clusters() == 4084);
  assert(node_id_available(7890));
  u16 value = 0;
  assert(fat_first_cluster(7890, value) && value == 17);
  assert(fat_chain_count(7890, value) && value == 41);
  assert(fat_chain_cluster(7890, 40, value) && value == 73);
  FatClusterInfo info;
  assert(fat_cluster_info(73, info) == FatClusterStatus::USED);
  assert(info.owner == 7890 && info.index == 40 && info.next == INVALID_ID);
  assert(fat_projection_begin() && import_plan_begin());
  assert(import_plan_put(0, 513, 7900, 7890));
  u16 target = 0, original = 0;
  assert(import_plan_get(0, 513, target, original) && target == 7900 && original == 7890);
  assert(import_name_put(123, 0xC99, 987654));
  u16 hash = 0; u32 location = 0;
  assert(import_name_get(123, hash, location) && hash == 0xC99 && location == 987654);
  assert(fat_find_child(6000, false, ProgramType::TEXT, "long name", value) && value == 7890);
  assert(create_directory_from_fat(6000, "folder", 7891, 17, &value) && value == 7891);
  const u8 clusters[] = {17, 0, 18, 0, 19, 0};
  assert(set_directory_chain(7891, 3, {(void*) clusters, read_clusters}));
  assert(prepare_import_mapping(7890) && ensure_directory_chain(7891));
  import_plan_end();
}

int main() {
  portable_system::service_table.call = service;
  test_c9_wire();
  Capture out;
  const program_store::FileSink sink = {&out, append};
  u32 size;
  assert(program_store::exported_size_id(7, size) && size == source.size());
  assert(program_store::stream_file_id(7, sink));
  assert(calls == 1 && out.bytes == source);
  calls = 0;
  out.bytes.clear();
  result = 0;
  assert(!program_store::stream_file_id(7, sink));
  assert(calls == 1 && out.bytes == source);
  result = 1;
  out = {{}, 70};
  assert(!program_store::stream_file_id(7, sink));
  assert(out.bytes.size() == 70);
  out = {};
  source.clear();
  assert(program_store::stream_file_id(7, sink));
  assert(out.bytes.empty());
  assert(!program_store::stream_file_id(7, {nullptr, nullptr}));
  // A startup timeout must stop storage operations.
  mk61_usbdisk_startup_stage(1);
  time_ms = 5000;
  calls = 0;
  assert(!program_store::stream_file_id(7, sink));
  assert(calls == 0);
  program_store::FatClusterInfo info;
  assert(program_store::fat_cluster_info(73, info) == program_store::FatClusterStatus::ERROR);
  puts("portable USBDISK C9 wire and stream: ok");
}
