#include "app_flow.hpp"
#include "rust_types.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

enum class RuntimeStatus : u8 {
  OK, DISABLED, UNAVAILABLE, INVALID_MODULE, INCOMPATIBLE_FIRMWARE, CORRUPT_MODULE, BUSY, IO_ERROR
};
enum class Kind : u8 { APPLICATION = 4, SETUP = 7 };
using FlowHost = RuntimeStatus (*)(void*, u32, u32&);
using FlowService = RuntimeStatus (*)(void*, app_flow::Step&);
static u8 g_call_depth, g_pin_depth;
static app_flow::Step* current_step;
static bool legacy;
static RuntimeStatus load_error;
static unsigned loads, native_calls;
struct Cache {
  u8 image[128] = {};
  bool live = true;
  bool ok() const { return live; }
  u8* data() { return image; }
  usize size() const { return sizeof(image); }
} g_app_cache;
static RuntimeStatus load(Kind, u16) { ++loads; return load_error; }
static u32 entry(u32 command, u32 a, u32 b, u32 c, u32 d) {
  assert(g_call_depth == 1); ++native_calls;
  if(command == MK61_APP_FLOW_INFO) return legacy ? 0 : MK61_APP_FLOW_MAGIC;
  if(command == MK61_APP_FLOW_STEP) {
    assert(a == (u32)(uintptr_t)current_step && !b && !c && !d);
    mk61_app_flow_return(current_step, 42, MK61_FLOW_OK); return 1;
  }
  assert(command == 0x407 && a == 11 && b == 22 && c == 33 && d == 44);
  return 55;
}
static auto g_active_entry = entry;
#include "app_flow_runtime.inc"

static RuntimeStatus host(void*, u32 operation, u32& result) {
  assert(!g_call_depth && operation == 17); result = 99; return RuntimeStatus::OK;
}
static RuntimeStatus tail_service(void* binding, app_flow::Step& step) {
  assert(!g_call_depth && *(const int*)binding == 17);
  mk61_app_flow_next(&step, mk61_app_flow_to(MK61_APP_KIND_APPLICATION, 43, 2));
  return RuntimeStatus::OK;
}
int main() {
  u32 context[4] = {11,22,33,44};
  app_flow::Step step = {sizeof(step), MK61_APP_FLOW_VERSION, context, sizeof(context), {}, {},
                         MK61_FLOW_INVALID, 0, 0, 0};
  current_step = &step;
  FlowBinding callback = {host, nullptr, nullptr};
  const auto target = mk61_app_flow_to(MK61_APP_KIND_APPLICATION, 42, 0);
  g_call_depth = 1;
  assert(flow_invoke(&callback, target, step) == MK61_FLOW_BUSY && !loads && !native_calls);
  g_call_depth = 0; g_pin_depth = 1;
  assert(flow_invoke(&callback, target, step) == MK61_FLOW_BUSY && !loads);
  g_pin_depth = 0;
  assert(flow_invoke(&callback, target, step) == MK61_FLOW_OK && step.result == 42 && !g_call_depth);
  legacy = true;
  assert(flow_invoke(&callback, target, step) == MK61_FLOW_INCOMPATIBLE && !g_call_depth);
  const auto direct = mk61_app_flow_direct(MK61_APP_KIND_SETUP, 0xFFFF, 0x407, 0);
  assert(flow_invoke(&callback, direct, step) == MK61_FLOW_OK && step.result == 55 && !g_call_depth);
  step.context_size = 15;
  assert(flow_invoke(&callback, direct, step) == MK61_FLOW_CORRUPT);
  step.context_size = 16;
  assert(flow_invoke(&callback, mk61_app_flow_direct(7,0xFFFF,0x407,1), step) == MK61_FLOW_CORRUPT);
  auto* first = g_app_cache.data();
  assert(flow_overlaps_app(first, 1));
  assert(flow_overlaps_app((const void*)((uintptr_t)first - 1), 2));
  assert(flow_overlaps_app(first + g_app_cache.size() - 1, 2));
  assert(!flow_overlaps_app(first + g_app_cache.size(), 1));
  step.context = first;
  assert(flow_invoke(&callback, target, step) == MK61_FLOW_CORRUPT);
  step.context = context;
  const auto service = mk61_app_flow_to(MK61_APP_FLOW_HOST, 0xFFFF, 17);
  assert(flow_invoke(&callback, service, step) == MK61_FLOW_OK && step.result == 99);
  callback.host = nullptr;
  assert(flow_invoke(&callback, service, step) == MK61_FLOW_DISABLED);
  int cookie = 17;
  callback.service = tail_service; callback.binding = &cookie;
  assert(flow_invoke(&callback, service, step) == MK61_FLOW_OK);
  assert(step.action == MK61_FLOW_NEXT && step.next.file_id == 43 && !g_call_depth);
  puts("APP resident flow: pins, active calls, overlap, compatibility, direct commands PASS");
}
