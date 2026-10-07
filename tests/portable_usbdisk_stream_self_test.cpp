#include "system_compat.hpp"
#include <assert.h>
#include <stdio.h>
#include <vector>

static std::vector<u8> source(1500, 'A');
static u32 result = 1;
static u32 calls;
static u32 time_ms;
extern "C" u32 millis() { return time_ms; }
void idle_main_process() {}

static u32 service(u32 operation, u32 op, u32 id, u32, void* payload) {
  assert(operation == MK61_SYS_USBDISK);
  if(op == MK61_USBDISK_STARTUP_STAGE) return 1;
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

int main() {
  portable_system::service_table.call = service;
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
  puts("portable USBDISK stream: ok");
}
