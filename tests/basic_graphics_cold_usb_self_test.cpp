#include "basic_graphics.hpp"
#include "shared_memory.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <limits>

static RuntimeScreen screen;
RuntimeScreen &main_lcd() { return screen; }
namespace builtin_font {
bool copyRows5x8(uint16_t, uint8_t rows[8]) { std::memset(rows, 31, 8); return true; }
}
using namespace basic_graphics;
using namespace shared_memory;
static Request request(Operation operation) { Request r = {}; r.operation = operation; return r; }
static void apply(Operation operation) {
  auto r = request(operation);
  assert(dispatch(r) == Result::OK);
}
static void bytes(const Lease &lease, uint8_t expected) {
  assert(lease.ok());
  for (usize i = 0; i < lease.size(); ++i) assert(lease.data()[i] == expected);
}
int main(int argc, char **) {
  assert(argc == 1 || argc == 2);
  assert(prepare_disk_mode());
  assert(prepare_retained_buffers());
  auto *heap = adjust_heap(0);
  const usize total = capacity(Arena::OVERLAY);
  for (auto op : {Operation::RESET, Operation::CLEAR, Operation::SHOW,
                  Operation::END, Operation::CHECK})
    apply(op);
  auto r = request(Operation::WIDTH);
  assert(dispatch(r) == Result::OK && r.value == screen.fullscreenBitmapWidth());
  assert(adjust_heap(0) == heap && capacity(Arena::OVERLAY) == total);

  // Match the cold failure: USB owns the lower arena, an executing APP owns
  // the upper one. Retained-heap growth is correctly forbidden, not relaxed.
  Lease usb, app;
  assert(usb.acquire(Arena::OVERLAY, Owner::USB_SCREEN, 5184));
  const usize initial_app = argc == 2 ? 19452 : APP_MAX_SIZE;
  assert(app.acquire(Arena::APP, Owner::LOADABLE_MODULE, initial_app));
  std::memset(usb.data(), 0x5A, usb.size());
  std::memset(app.data(), 0xC3, app.size());
  assert(!allocate_retained_buffer(1) && validate_invariants());
  const usize before_graphics = capacity(Arena::OVERLAY);

  // Real OOM still fails safely. Releasing only the blocking buffer permits
  // retry: no early session pointer or leaked reservation survives the failure.
  LifetimeBuffer full;
  assert(full.acquire(Owner::STORAGE_WORKSPACE,
                      (before_graphics - usb.size()) & ~usize(31)));
  r = request(Operation::BOX); r.count = 4;
  r.args[2] = screen.fullscreenBitmapWidth() - 1;
  r.args[3] = screen.fullscreenBitmapHeight() - 1;
  assert(dispatch(r) == Result::FULL && adjust_heap(0) == heap);
  assert(validate_invariants());
  bytes(usb, 0x5A); bytes(app, 0xC3);
  full.reset();
  assert(dispatch(r) == Result::OK);
  assert(adjust_heap(0) == heap && capacity(Arena::OVERLAY) < before_graphics);
  r = request(Operation::PSET); r.count = 2; r.args[0] = r.args[1] = 1;
  assert(dispatch(r) == Result::OK);
  apply(Operation::SHOW);
  assert(screen.shown[1] & 2);
  const usize live_graphics = capacity(Arena::OVERLAY);
#if MK61_BASIC_GRAPHICS_DISK_EXCLUSIVE
  assert(!prepare_disk_mode());
#endif
  r = request(Operation::END); r.count = 1;
  r.args[0] = std::numeric_limits<double>::quiet_NaN();
  assert(dispatch(r) == Result::ARGUMENT && capacity(Arena::OVERLAY) == live_graphics);
  r = request(Operation::ACTIVE);
  assert(dispatch(r) == Result::OK && r.value == 1);

  // INPUT replaces the APP, not the resident canvas or nested PRINT state.
  r = request(Operation::SAVE_PRINT); r.count = 5;
  r.text = "outer"; r.length = 5; r.args[2] = 1;
  assert(dispatch(r) == Result::OK);
  apply(Operation::SUSPEND);
#if MK61_BASIC_GRAPHICS_DISK_EXCLUSIVE
  assert(!prepare_disk_mode());
#endif
  app.reset();
  assert(app.acquire(Arena::APP, Owner::LOADABLE_MODULE, initial_app));
  std::memset(app.data(), 0xD4, app.size());
  apply(Operation::RESUME);
  assert(screen.shown[1] & 2);
  char restored[96] = {};
  r = request(Operation::RESTORE_PRINT); r.text = restored; r.length = sizeof(restored);
  assert(dispatch(r) == Result::OK && std::strcmp(restored, "outer") == 0);
  bytes(usb, 0x5A); bytes(app, 0xD4);

  // A hot VM may be smaller than the next compiler/ordinary APP. END must
  // release the graphics gap before that larger image starts, even with USB
  // still pinning the bottom of a nearly full pool.
  apply(Operation::END);
  app.reset();
  assert(app.acquire(Arena::APP, Owner::LOADABLE_MODULE, APP_MAX_SIZE));
  std::memset(app.data(), 0xD4, app.size());
  const usize without_graphics = capacity(Arena::OVERLAY);
  for (unsigned repeat = 0; repeat < 3; ++repeat) {
    apply(Operation::RESET);
    r = request(Operation::PSET); r.count = 2;
    assert(dispatch(r) == Result::OK);
    assert(capacity(Arena::OVERLAY) < without_graphics && adjust_heap(0) == heap);
    assert(validate_invariants());
    bytes(app, 0xD4);
    if (repeat == 1) usb.reset(); // USB can end before the active canvas.
    apply(Operation::END);
    assert(capacity(Arena::OVERLAY) == without_graphics);
    assert(prepare_disk_mode());
  }
  apply(Operation::END);
  assert(screen.begins == screen.ends);
  puts("BASIC resident graphics: cold USB + maximum APP, real OOM/retry, INPUT and independent lifetimes PASS");
}
