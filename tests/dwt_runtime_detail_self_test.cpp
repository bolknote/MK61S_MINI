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

static void runner_and_invoke() {
  reset();
  {
    Scope runner(Point::M61_RUNNER); tick(3);
    {
      Scope invoke(Point::VM_INVOKE); tick(4);
      { Scope vm(Point::APP_ENTRY_VM); tick(5); }
      tick(6);
    }
    tick(7);
  }
  const auto& runner = statistics(Point::M61_RUNNER);
  const auto& invoke = statistics(Point::VM_INVOKE);
  const auto& vm = statistics(Point::APP_ENTRY_VM);
  assert(runner.total_cycles == 25 && runner.self_cycles == 10);
  assert(invoke.total_cycles == 15 && invoke.self_cycles == 10);
  assert(vm.total_cycles == 5 && vm.self_cycles == 5);
  assert(runner.self_cycles + invoke.self_cycles + vm.self_cycles == runner.total_cycles);
  assert(scope_top == nullptr);
}

static void script_detail_tree() {
  reset();
  {
    Scope runner(Point::M61_RUNNER); tick(1);
    { Scope read(Point::M61_READ_LINE); tick(2); }
    {
      Scope command(Point::M61_COMMAND); tick(3);
      { Scope operand(Point::M61_OPERAND); tick(4); }
      { Scope lookup(Point::TERMINAL_LOOKUP); tick(5); }
      {
        Scope open(Point::M61_OPEN); tick(6);
        {
          Scope invoke(Point::VM_INVOKE); tick(7);
          { Scope vm(Point::APP_ENTRY_VM); tick(8); }
        }
      }
    }
  }
  const Point points[] = {Point::M61_RUNNER, Point::M61_READ_LINE,
      Point::M61_COMMAND, Point::M61_OPERAND, Point::TERMINAL_LOOKUP,
      Point::M61_OPEN, Point::VM_INVOKE, Point::APP_ENTRY_VM};
  u64 sum = 0;
  for(usize i = 0; i < sizeof(points) / sizeof(points[0]); ++i) {
    const auto& row = statistics(points[i]);
    assert(row.samples == 1 && row.self_cycles == i + 1);
    sum += row.self_cycles;
  }
  assert(sum == 36 && statistics(Point::M61_RUNNER).total_cycles == sum);
  assert(statistics(Point::M61_COMMAND).total_cycles == 33);
  assert(statistics(Point::M61_OPEN).total_cycles == 21);
  assert(scope_top == nullptr);
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

#if MK61_DWT_IDLE_DETAIL_SUPPORTED
static void idle_detail_tree() {
  reset();
  {
    Scope epoch(Point::IDLE_MAIN); tick(1);
    { Scope power(Point::IDLE_POWER); tick(2); }
    { Scope conditions(Point::IDLE_SLEEP_CONDITIONS); tick(3); }
    { Scope attempt(Point::IDLE_SLEEP_ATTEMPT); tick(4); }
    { Scope usb(Point::USB_SCREEN_SERVICE); tick(5); }
  }
  assert(statistics(Point::IDLE_MAIN).total_cycles==15);
  assert(statistics(Point::IDLE_MAIN).self_cycles==1);
  assert(statistics(Point::IDLE_POWER).self_cycles==2);
  assert(statistics(Point::IDLE_SLEEP_CONDITIONS).self_cycles==3);
  assert(statistics(Point::IDLE_SLEEP_ATTEMPT).self_cycles==4);
  assert(statistics(Point::USB_SCREEN_SERVICE).self_cycles==5);
  assert(scope_top==nullptr);
}
#endif

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

#if MK61_DWT_VM_OPCODE_PROFILE_SUPPORTED
static void opcode_batches() {
  reset();
  record_vm_opcodes(3,100,80,UINT64_C(0x100000000));
  record_vm_opcodes(3,20,20,240);
  const auto& row=statistics(Point::VM_ADD_SUB);
  assert(row.samples==120 && row.total_cycles==UINT64_C(0x1000000F0));
  assert(row.self_cycles==row.total_cycles && vm_opcode_integers(3)==100);
  assert(!row.minimum_cycles && !row.maximum_cycles);
  record_vm_opcodes(8,1,1,50);record_vm_opcodes(3,1,2,50);
  record_vm_opcodes(3,0,0,50);
  assert(row.samples==120);
  stop();record_vm_opcodes(3,1,1,50);assert(row.samples==120);
  assert(start() && row.samples==0 && vm_opcode_integers(3)==0);
  record_vm_opcodes(3,UINT32_MAX,UINT32_MAX,1);
  record_vm_opcodes(3,1,1,50);
  assert(row.samples==UINT32_MAX && row.total_cycles==1 &&
         vm_opcode_integers(3)==UINT32_MAX);
  assert(!vm_opcode_integers(8));
  reset();
}
#endif

int main() {
  static_assert(POINT_COUNT == 49 + (MK61_VM_OPCODE_PROFILE ? 8 : 0) +
      (MK61_DWT_IDLE_DETAIL ? 15 : 0));
  initialize(); assert(available() && start());
  nested_scopes(); runner_and_invoke(); script_detail_tree(); wrap_and_long_scope(); reset_while_active(); context_and_cache();
#if MK61_DWT_IDLE_DETAIL_SUPPORTED
  idle_detail_tree();
#endif
#if MK61_DWT_VM_OPCODE_PROFILE_SUPPORTED
  opcode_batches();
#endif
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
