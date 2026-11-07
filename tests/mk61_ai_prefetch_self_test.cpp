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
bool sparse(void *p, std::uint16_t id) {
  // A real vocabulary policy may decode tokens through PSRAM. Doing this
  // while a prefetch holds the bus would self-deadlock on the MCU.
  auto &r = *static_cast<Runtime *>(p);char text[2049];unsigned used = 0;
  assert(r.model.decode(id, text, sizeof(text), used) == ModelStatus::OK);
  return id % 37 == 0;
}
}
int main(int argc, char **argv) {
  assert(argc == 2);std::ifstream stream(argv[1], std::ios::binary);
  const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(stream)), {});
  Runtime control(bytes), candidate(bytes);control.configure(false);
  std::uint16_t tokens[64];unsigned count = 0;
  assert(control.model.encode("Задача: вычисли синус и проверь результат.", tokens, 64, count) == ModelStatus::OK && count > 2);
  const auto vocab = control.model.config().vocab;
  std::vector<float> a(vocab), b(vocab);std::uint16_t left = 0, right = 0;
  unsigned comparisons = 0;
  auto compare = [&](Arithmetic mode, unsigned positions, bool every_output) {
    control.model.reset();candidate.model.reset();
    for (unsigned p = 0; p < positions; ++p) {
      const bool output = every_output || p + 1 == positions;
      assert(control.forward(tokens[p % count], mode, left, output ? a.data() : nullptr, output) == ModelStatus::OK);
      assert(candidate.forward(tokens[p % count], mode, right, output ? b.data() : nullptr, output) == ModelStatus::OK);
      assert(control.model.compute_metrics().checksum == candidate.model.compute_metrics().checksum);
      assert(control.cache == candidate.cache);
      if (output) { assert(left == right && !std::memcmp(a.data(), b.data(), vocab * sizeof(float)));++comparisons; }
      assert(!control.model.compute_metrics().prefetches);
      assert(candidate.model.compute_metrics().prefetches == 0 || candidate.overlapped > 0);
    }
  };
  for (unsigned mode = 0; mode < 4; ++mode) compare(Arithmetic(mode), 2, true);
  compare(Arithmetic::LUT_FLOAT32, 64, false);
  assert(candidate.began > 0 && candidate.overlapped > 0);
  // Sparse/non-aligned spans and a refused backend retain the serial path.
  for (bool refuse : {false, true}) {
    control.model.reset();candidate.model.reset();candidate.refuse = refuse;
    control.configure(false, true);candidate.configure(true, true);
    assert(control.forward(tokens[0], Arithmetic::LUT_FLOAT32, left, nullptr, true, sparse) == ModelStatus::OK);
    assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, right, nullptr, true, sparse) == ModelStatus::OK);
    assert(left == right && control.model.compute_metrics().checksum == candidate.model.compute_metrics().checksum);
  }
  candidate.refuse = false;control.configure(false);candidate.configure(true);
  for (int boundary : {0, 1, 20, 100}) {
    candidate.model.reset();candidate.cancel_after = boundary;
    assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, right) == ModelStatus::CANCELLED);
    assert(candidate.model.position() == 0);candidate.cancel_after = -1;
    compare(Arithmetic::LUT_FLOAT32, 1, true);
  }
  for (int boundary : {0, 1, 50}) {
    candidate.model.reset();candidate.fail_finish_after = boundary;
    assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, right) == ModelStatus::IO);
    assert(candidate.model.position() == 0);candidate.fail_finish_after = -1;
    compare(Arithmetic::LUT_FLOAT32, 1, true);
  }
  // Numeric failure with a next-tile DMA in flight still joins both owners.
  auto corrupted = bytes;Runtime bad(corrupted);
  auto word = [&](unsigned at) { std::uint32_t n;std::memcpy(&n, corrupted.data() + at, 4);return n; };
  const unsigned projection = word(15 * 4) + 3 * 32;
  const unsigned scales = word(projection + 20), columns = word(projection + 4);
  corrupted[scales + 4 * columns / 16] = 1;corrupted[scales + 4 * columns / 16 + 1] = 0x7e;
  assert(bad.forward(tokens[0], Arithmetic::LUT_FLOAT32, right) == ModelStatus::NUMERIC);
  assert(bad.began && bad.model.position() == 0);
  std::printf("prefetch: PASS; %u full-logit comparisons, 64-position KV exact, %u DMA requests, %u overlapping worker jobs; sparse/refusal/cancel/retry/DMA-fault/numeric/join/thaw/guards PASS\n",
              comparisons, candidate.began, candidate.overlapped);
}
