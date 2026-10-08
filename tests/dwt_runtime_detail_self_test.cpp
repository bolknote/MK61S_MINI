#include "dwt_profiler.hpp"
#include "loadable_module_format.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <set>
#include <string>

TestDwt test_dwt;
TestCoreDebug test_core_debug;
using namespace dwt_profiler;
static void tick(u32 cycles) { test_dwt.CYCCNT += cycles; }

static void nested_scopes() {
  reset();
  {
    Scope root(Point::APP_ENTRY_VM); tick(10);
    {
      Scope file(Point::FILE_SOURCE); tick(4);
      { Scope flash(Point::FLASH_READ); tick(7); }
      tick(3);
    }
    tick(5);
  }
  const auto& root = statistics(Point::APP_ENTRY_VM);
  const auto& file = statistics(Point::FILE_SOURCE);
  const auto& flash = statistics(Point::FLASH_READ);
  assert(root.samples == 1 && root.total_cycles == 29 && root.self_cycles == 15);
  assert(file.samples == 1 && file.total_cycles == 14 && file.self_cycles == 7);
  assert(flash.samples == 1 && flash.total_cycles == 7 && flash.self_cycles == 7);
  assert(root.self_cycles + file.self_cycles + flash.self_cycles == root.total_cycles);
  assert(scope_top == nullptr);
}

static void wrap_and_long_scope() {
  test_dwt.CYCCNT = 0xFFFFFFF0UL; reset();
  { Scope scope(Point::APP_ENTRY_VM); tick(32); }
  assert(statistics(Point::APP_ENTRY_VM).total_cycles == 32);
  reset();
  {
    Scope scope(Point::APP_ENTRY_VM);
    tick(0xF0000000UL);
    { Scope child(Point::FILE_SOURCE); tick(16); }
    tick(0xF0000000UL);
    { Scope child(Point::FILE_SOURCE); tick(16); }
  }
  const auto& stats = statistics(Point::APP_ENTRY_VM);
  assert(stats.total_cycles == UINT64_C(0x1E0000020));
  assert(stats.self_cycles == UINT64_C(0x1E0000000));
  assert(stats.maximum_cycles == 0xFFFFFFFFUL && stats.average_cycles() == 0xFFFFFFFFUL);
}

static void reset_while_active() {
  reset();
  {
    Scope stale(Point::APP_ENTRY_VM); tick(3);
    DecodeContext old_decode(Point::ZX0_APP_VM);
    reset();
    { Scope fresh(Point::FILE_FONT); tick(9); }
  }
  assert(scope_top == nullptr && decode_point == Point::ZX0_OTHER);
  assert(statistics(Point::APP_ENTRY_VM).samples == 0);
  assert(statistics(Point::FILE_FONT).total_cycles == 9);
}

static void context_and_cache() {
  reset();
  {
    DecodeContext app(Point::ZX0_APP_VM);
    { DecodeContext source(Point::ZX0_SOURCE); assert(decode_point == Point::ZX0_SOURCE); }
    assert(decode_point == Point::ZX0_APP_VM);
  }
  assert(decode_point == Point::ZX0_OTHER);
  record_vm_cache(42, false, 0); record_vm_image(42, 128); record_vm_cache(42, true, 128);
  const auto& row = vm_cache_row(0);
  assert(row.id == 42 && row.size == 128 && row.hits == 1 && row.misses == 1);
  for(unsigned i = 0; i < VM_CACHE_ROWS - 1; ++i) record_vm_cache((u16)i, true, 80);
  record_vm_cache(99, false, 0);
  assert(vm_cache_dropped() == 1 && vm_cache_row(VM_CACHE_ROWS).id == 0xFFFF);
  record_vm_cache(0xFFFF, false, 0); assert(vm_cache_dropped() == 1);
  stop(); record_vm_cache(42, true, 128);
  assert(row.hits == 1);
  { Scope stopped(Point::APP_ENTRY_VM); tick(12); }
  assert(statistics(Point::APP_ENTRY_VM).samples == 0);
  assert(start() && vm_cache_row(0).id == 0xFFFF && vm_cache_dropped() == 0);
}

int main() {
  static_assert(POINT_COUNT == 42);
  initialize(); assert(available() && start());
  nested_scopes(); wrap_and_long_scope(); reset_while_active(); context_and_cache();
  std::set<std::string> names;
  for(unsigned i = 0; i < POINT_COUNT; ++i) {
    const char* name = point_name((Point)i);
    assert(std::strcmp(name, "unknown") != 0 && names.insert(name).second);
  }
  using K = loadable_module::Kind;
  assert(app_point((u8)K::TINYBASIC, false) == Point::APP_LOAD_BASIC);
  assert(app_point((u8)K::LANGUAGE_VM, true) == Point::APP_ENTRY_VM);
  assert(app_decode_point((u8)K::LANGUAGE_INPUT) == Point::ZX0_APP_INPUT);
  assert(app_decode_point(255) == Point::ZX0_APP_OTHER);
  std::cout << "DWT runtime attribution: nested/self cycles, long wraps, reset, bounded rows PASS\n";
}
