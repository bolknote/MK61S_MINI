#pragma once
#include "mk61_ai_model.hpp"
#include "mk61_ai_worker_fixture.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>
using namespace mk61ai;
namespace {
struct Runtime {
  Model model;
  const std::vector<std::uint8_t> &package;
  std::vector<std::uint64_t> workspace;
  std::vector<std::uint8_t> cache;
  TestAiWorker cpu, dma;
  std::thread::id foreground = std::this_thread::get_id();
  struct ReadJob {
    Runtime *runtime;
    block_io::ReadSpan spans[16];
    unsigned count;
    bool fail;
  } job{};
  bool pending = false, busy = false, refuse = false;
  int cancel_after = -1, fail_finish_after = -1;
  unsigned began = 0, finished = 0, overlapped = 0;
  void owner() const { assert(std::this_thread::get_id() == foreground); }
  static bool read(void *p, std::uint32_t at, void *out, unsigned n) {
    auto &r = *static_cast<Runtime *>(p);r.owner();assert(!r.pending);
    if (at > r.package.size() || n > r.package.size() - at) return false;
    std::memcpy(out, r.package.data() + at, n);return true;
  }
  static bool read_kv(void *p, std::uint32_t at, void *out, unsigned n) {
    auto &r = *static_cast<Runtime *>(p);r.owner();assert(!r.pending);
    if (at > r.cache.size() || n > r.cache.size() - at) return false;
    std::memcpy(out, r.cache.data() + at, n);return true;
  }
  static bool write_kv(void *p, std::uint32_t at, const void *in, unsigned n) {
    auto &r = *static_cast<Runtime *>(p);r.owner();assert(!r.pending);
    if (at > r.cache.size() || n > r.cache.size() - at) return false;
    std::memcpy(r.cache.data() + at, in, n);return true;
  }
  static bool begin(void *p, const block_io::ReadSpan *spans, unsigned count) {
    auto &r = *static_cast<Runtime *>(p);r.owner();assert(!r.pending);
    if (r.refuse) return false;
    assert(count && count <= 16);
    unsigned total = 0;
    for (unsigned i = 0; i < count; ++i) {
      assert(spans[i].offset <= r.package.size() && spans[i].bytes <= r.package.size() - spans[i].offset);
      // Match the direct QPI backend's bounded, aligned destination contract.
      if ((spans[i].offset & 15) || (spans[i].bytes & 15) ||
          static_cast<std::uint8_t *>(spans[i].destination) !=
              static_cast<std::uint8_t *>(spans[0].destination) + total) return false;
      total += spans[i].bytes;
    }
    if (total > 2048) return false;
    r.job.runtime = &r;r.job.count = count;r.job.fail = r.fail_finish_after == 0;
    if (r.fail_finish_after > 0) --r.fail_finish_after;
    std::copy(spans, spans + count, r.job.spans);
    r.pending = true;++r.began;
    assert(r.dma.submit([](void *raw) {
      auto &j = *static_cast<ReadJob *>(raw);
      for (unsigned i = 0; i < j.count; ++i) {
        // A failed transfer may have overwritten a prefix, but must be
        // joined before the caller retries or destroys the workspace.
        if (j.fail && i) break;
        const auto &s = j.spans[i];
        std::memcpy(s.destination, j.runtime->package.data() + s.offset, s.bytes);
        std::this_thread::yield();
      }
    }, &r.job));
    return true;
  }
  static bool finish(void *p) {
    auto &r = *static_cast<Runtime *>(p);r.owner();assert(r.pending);
    r.dma.join();r.pending = false;++r.finished;return !r.job.fail;
  }
  explicit Runtime(const std::vector<std::uint8_t> &p) : package(p) {
    assert(model.open({this, unsigned(p.size()), read, nullptr, begin, finish}) == ModelStatus::OK);
    workspace.resize((model.workspace_bytes() + 7) / 8 + 8);
    std::fill(workspace.end() - 8, workspace.end(), UINT64_C(0xb00f61a1b00f61a1));
    cache.resize(model.cache_bytes());
    assert(model.bind(workspace.data(), model.workspace_bytes(),
                      {this, unsigned(cache.size()), read_kv, write_kv}) == ModelStatus::OK);
    configure(true);
  }
  void configure(bool prefetch, bool filter = false) {
    ComputeExecution e{};e.context = this;e.kernel = LinearKernel::SRAM;
    e.prefetch = prefetch;e.filter_head = filter;
    e.busy = [](void *p, bool active) {
      auto &r = *static_cast<Runtime *>(p);r.owner();
      assert(r.busy != active && !r.pending && r.began == r.finished);
      assert(r.cpu.submitted == r.cpu.joined && r.dma.submitted == r.dma.joined);
      r.busy = active;
    };
    e.submit = [](void *p, void (*fn)(void *), void *job) {
      auto &r = *static_cast<Runtime *>(p);r.owner();
      if (r.pending) ++r.overlapped;
      return r.cpu.submit(fn, job);
    };
    e.join = [](void *p) { static_cast<Runtime *>(p)->cpu.join(); };
    model.execution(e);
  }
  ModelStatus forward(std::uint16_t token, Arithmetic arithmetic, std::uint16_t &best,
                      float *logits = nullptr, bool output = true,
                      bool (*allowed)(void *, std::uint16_t) = nullptr) {
    const auto result = model.forward(token, output, best, [](void *p) {
      auto &r = *static_cast<Runtime *>(p);r.owner();assert(!r.pending && r.busy);
      return r.cancel_after < 0 || r.cancel_after-- > 0;
    }, this, arithmetic, logits, allowed, this);
    assert(!busy && !pending && began == finished && cpu.submitted == cpu.joined);
    for (unsigned i = 0; i < 8; ++i)
      assert(workspace[workspace.size() - 8 + i] == UINT64_C(0xb00f61a1b00f61a1));
    return result;
  }
};
[[maybe_unused]] bool sparse(void *p, std::uint16_t id) {
  // A real vocabulary policy may decode tokens through PSRAM. Doing this
  // while a prefetch holds the bus would self-deadlock on the MCU.
  auto &r = *static_cast<Runtime *>(p);char text[2049];unsigned used = 0;
  assert(r.model.decode(id, text, sizeof(text), used) == ModelStatus::OK);
  return id % 37 == 0;
}
}
