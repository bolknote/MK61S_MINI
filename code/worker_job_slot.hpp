#ifndef MK61_WORKER_JOB_SLOT_HPP
#define MK61_WORKER_JOB_SLOT_HPP
#include <atomic>

// Single producer/consumer mailbox. Neither side owns the other's peripheral
// state. DONE remains occupied until the producer joins, so a stack descriptor
// cannot be reused while its result is still being observed.
class WorkerJobSlot {
public:
  bool submit(void *context, void (*function)(void *)) {
    if (!function || state_.load(std::memory_order_acquire) != IDLE) return false;
    context_ = context;function_ = function;
    state_.store(QUEUED, std::memory_order_release);
    return true;
  }
  bool queued() const { return state_.load(std::memory_order_acquire) == QUEUED; }
  bool active() const {
    const auto state = state_.load(std::memory_order_acquire);
    return state == QUEUED || state == WORKING;
  }
  bool run() {
    if (!queued()) return false;
    state_.store(WORKING, std::memory_order_relaxed);
    function_(context_);
    state_.store(DONE, std::memory_order_release);
    return true;
  }
  bool join() {
    if (state_.load(std::memory_order_acquire) != DONE) return false;
    state_.store(IDLE, std::memory_order_release);
    return true;
  }
private:
  enum State : unsigned { IDLE, QUEUED, WORKING, DONE };
  std::atomic<unsigned> state_{IDLE};
  void *context_ = nullptr;
  void (*function_)(void *) = nullptr;
};
#endif
