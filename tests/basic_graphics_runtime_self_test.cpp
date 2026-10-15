#include "basic_graphics.hpp"
#include <cassert>
#include <cstdio>
#include <limits>
#include <initializer_list>
static RuntimeScreen screen;
static void *allocation = nullptr;
static unsigned allocations = 0;
static bool fail_allocation = false;
RuntimeScreen &main_lcd() { return screen; }
namespace builtin_font {
bool copyRows5x8(uint16_t, uint8_t rows[8]) { std::memset(rows, 31, 8); return true; }
}
void *shared_memory::allocate_retained_buffer(unsigned int size) {
  assert(!allocation);
  if (fail_allocation) return nullptr;
  allocation = std::malloc(size);
  std::memset(allocation, 0, size);
  ++allocations;
  return allocation;
}
using namespace basic_graphics;
static Request request(Operation operation) { Request r = {}; r.operation = operation; return r; }
static void apply(Operation operation) {
  auto r = request(operation);
  assert(dispatch(r) == Result::OK);
}
int main() {
  fail_allocation = true;
  for (auto op : {Operation::RESET, Operation::END, Operation::CHECK, Operation::SHOW,
                  Operation::CLEAR, Operation::SUSPEND, Operation::RESUME, Operation::TEXT_ROWS})
    apply(op);
  auto r = request(Operation::WIDTH);
  assert(dispatch(r) == Result::OK && r.value == screen.fullscreenBitmapWidth());
  r = request(Operation::ACTIVE);
  assert(dispatch(r) == Result::OK && r.value == 0 && allocations == 0);
  r = request(Operation::POINT); r.count = 2;
  assert(dispatch(r) == Result::OK && r.value == 0 && allocations == 0);
  screen.available = false;
  assert(dispatch(r) == Result::UNAVAILABLE && allocations == 0);
  screen.available = true;
  r = request(Operation::PSET); r.count = 2; r.args[0] = r.args[1] = 1;
  assert(dispatch(r) == Result::FULL && !allocation);
  fail_allocation = false;
  assert(dispatch(r) == Result::OK);
  assert(allocation && allocations == 1);
  apply(Operation::SHOW);
  assert(screen.shown[1] & 2);

  // INPUT/APP eviction may overwrite caller-owned storage; the resident state
  // and pixels stay alive across suspend/resume and nested PRINT callbacks.
  apply(Operation::SUSPEND);
  auto *held = allocation;
  r = request(Operation::SAVE_PRINT); r.count = 5; r.text = "outer"; r.length = 5;
  r.args[2] = 1;
  assert(dispatch(r) == Result::OK && allocation == held);
  apply(Operation::RESUME);
  assert(allocation == held && screen.shown[1] & 2);
  char restored[96] = {};
  r = request(Operation::RESTORE_PRINT); r.text = restored; r.length = sizeof(restored);
  assert(dispatch(r) == Result::OK && std::strcmp(restored, "outer") == 0);
  r = request(Operation::END); r.count = 1;
  r.args[0] = std::numeric_limits<double>::quiet_NaN();
  assert(dispatch(r) == Result::ARGUMENT && allocation == held);
  r = request(Operation::ACTIVE);
  assert(dispatch(r) == Result::OK && r.value == 1);
  apply(Operation::END);
  assert(allocation == held);
  r = request(Operation::ACTIVE);
  assert(dispatch(r) == Result::OK && r.value == 0);
  apply(Operation::END);
  assert(allocations == 1);
  r = request(Operation::PSET); r.count = 2;
  assert(dispatch(r) == Result::OK && allocation == held && allocations == 1);
  apply(Operation::RESET);
  assert(allocation == held && allocations == 1);
  assert(screen.begins == screen.ends);
  std::puts("BASIC resident graphics: retained/OOM lifetime, INPUT pixels and state reset PASS");
}
