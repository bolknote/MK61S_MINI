#ifndef MK61_AI_WORKER_FIXTURE_HPP
#define MK61_AI_WORKER_FIXTURE_HPP
#include "worker_job_slot.hpp"
#include <atomic>
#include <cassert>
#include <thread>
struct TestAiWorker {
  WorkerJobSlot slot;
  std::atomic<bool> stop{false};
  std::atomic<unsigned> ran{0};
  unsigned submitted = 0, joined = 0;
  std::thread thread;
  TestAiWorker() : thread([this] {
    while (!stop.load(std::memory_order_acquire)) {
      if (slot.run()) ran.fetch_add(1, std::memory_order_relaxed);
      else std::this_thread::yield();
    }
  }) {}
  ~TestAiWorker() {
    assert(submitted == joined);
    stop.store(true, std::memory_order_release);thread.join();
    assert(ran.load() == submitted);
  }
  bool submit(void (*fn)(void *), void *job) {
    if (!slot.submit(job, fn)) return false;
    ++submitted;return true;
  }
  void join() {
    while (!slot.join()) std::this_thread::yield();
    ++joined;
  }
};
#endif
