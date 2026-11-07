#include "mk61_ai_model.hpp"
#include "mk61_ai_perf.hpp"
#include "worker_job_slot.hpp"
#include "mk61_ai_worker_fixture.hpp"
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <thread>
#include <vector>
using namespace mk61ai;
namespace {
using Worker=TestAiWorker;
struct Runtime {
  Model model;
  const std::vector<std::uint8_t> &package;
  std::vector<std::uint64_t> workspace;
  std::vector<std::uint8_t> cache;
  Worker *worker = nullptr;
  std::thread::id foreground = std::this_thread::get_id();
  int cancel_after = -1, fail_read_after = -1;
  unsigned busy_begin = 0, busy_end = 0;
  bool busy = false, refuse = false;
  static bool read(void *raw, std::uint32_t at, void *p, unsigned n) {
    auto &r = *static_cast<Runtime *>(raw);
    assert(std::this_thread::get_id() == r.foreground);
    if (r.fail_read_after == 0) return false;
    if (r.fail_read_after > 0) --r.fail_read_after;
    if (at > r.package.size() || n > r.package.size() - at) return false;
    std::memcpy(p, r.package.data() + at, n);return true;
  }
  static bool read_kv(void *raw, std::uint32_t at, void *p, unsigned n) {
    auto &r = *static_cast<Runtime *>(raw);
    assert(std::this_thread::get_id() == r.foreground);
    if (at > r.cache.size() || n > r.cache.size() - at) return false;
    std::memcpy(p, r.cache.data() + at, n);return true;
  }
  static bool write_kv(void *raw, std::uint32_t at, const void *p, unsigned n) {
    auto &r = *static_cast<Runtime *>(raw);
    assert(std::this_thread::get_id() == r.foreground);
    if (at > r.cache.size() || n > r.cache.size() - at) return false;
    std::memcpy(r.cache.data() + at, p, n);return true;
  }
  static bool service(void *raw) {
    auto &r = *static_cast<Runtime *>(raw);
    assert(std::this_thread::get_id() == r.foreground && r.busy);
    return r.cancel_after < 0 || r.cancel_after-- > 0;
  }
  explicit Runtime(const std::vector<std::uint8_t> &p) : package(p) {
    assert(model.open({this, unsigned(p.size()), read, nullptr}) == ModelStatus::OK);
    workspace.resize((model.workspace_bytes() + 7) / 8 + 8);
    cache.resize(model.cache_bytes());
    std::fill(workspace.end() - 8, workspace.end(), UINT64_C(0x61a11e1f61a11e1f));
    assert(model.bind(workspace.data(), model.workspace_bytes() - 1,
                      {this, unsigned(cache.size()), read_kv, write_kv}) == ModelStatus::MEMORY);
    assert(model.bind(workspace.data(), model.workspace_bytes(),
                      {this, unsigned(cache.size()), read_kv, write_kv}) == ModelStatus::OK);
    configure(LinearKernel::REFERENCE);
  }
  void configure(LinearKernel kernel, Worker *w = nullptr, bool filter = false) {
    worker = w;
    ComputeExecution e{};e.context = this;e.kernel = kernel;e.filter_head = filter;
    e.busy = [](void *raw, bool active) {
      auto &r = *static_cast<Runtime *>(raw);
      assert(r.busy != active);
      if (r.worker) assert(r.worker->submitted == r.worker->joined);
      r.busy = active;
      if (active) ++r.busy_begin;else ++r.busy_end;
    };
    if (w) {
      e.submit = [](void *raw, void (*fn)(void *), void *job) {
        auto &r = *static_cast<Runtime *>(raw);
        return !r.refuse && r.worker->submit(fn, job);
      };
      e.join = [](void *raw) { static_cast<Runtime *>(raw)->worker->join(); };
    }
    model.execution(e);
  }
  ModelStatus forward(std::uint16_t token, Arithmetic mode,
                      std::uint16_t &best, float *logits = nullptr,
                      bool (*allowed)(void *, std::uint16_t) = nullptr,bool output=true) {
    auto result = model.forward(token, output, best, service, this, mode, logits, allowed, this);
    assert(!busy && busy_begin == busy_end);
    if (worker) assert(worker->submitted == worker->joined);
    for (unsigned i = 0; i < 8; ++i)
      assert(workspace[workspace.size() - 8 + i] == UINT64_C(0x61a11e1f61a11e1f));
    return result;
  }
};
bool sparse(void *, std::uint16_t id) { return id % 37 == 0; }
bool none(void *, std::uint16_t) { return false; }
} // namespace
int main(int argc, char **argv) {
  WorkerJobSlot slot;unsigned value=0;
  auto increment=[](void *p) { ++*static_cast<unsigned*>(p); };
  assert(!slot.join() && !slot.submit(&value,nullptr));
  assert(slot.submit(&value,increment) && slot.queued() && slot.active());
  assert(!slot.submit(&value,increment) && !slot.join());
  assert(slot.run() && value==1 && !slot.active() && !slot.queued());
  assert(!slot.submit(&value,increment) && slot.join());
  assert(slot.submit(&value,increment) && slot.run() && slot.join() && value==2);
  const char valid[]="AIPERF1\nkernel=2\narithmetic=3\ncores=2\nfreeze=1\nfilter=0\nmhz=250\nprefill=8\ndecode=4\nrepeat=2\nstress_ms=120000\ncontrol=1\nconstrained=0\n";
  PerfConfig config;
  assert(parse_perf_config(valid,sizeof(valid)-1,config) && config.mhz==250 && config.cores==2);
  auto prefetch_config=std::string(valid);prefetch_config[6]='2';prefetch_config+="prefetch=1\n";
  assert(parse_perf_config(prefetch_config.data(),unsigned(prefetch_config.size()),config) &&
         config.version==2 && config.prefetch==1 && config.cores==2);
  auto invalid_prefetch=prefetch_config;invalid_prefetch.replace(invalid_prefetch.find("prefetch=1"),10,"prefetch=2");
  assert(!parse_perf_config(invalid_prefetch.data(),unsigned(invalid_prefetch.size()),config));
  for (const auto &bad : {std::string(valid)+"mhz=300\n",std::string(valid)+"unknown=1\n",
                         std::string(valid).replace(std::string(valid).find("mhz=250"),7,"mhz=301"),
                         std::string(valid).replace(std::string(valid).find("cores=2"),7,"cores=0"),
                         std::string(valid).replace(std::string(valid).find("filter=0"),8,"filter=1"),
                         std::string(valid).replace(std::string(valid).find("kernel=2"),8,"kernel=0")})
    assert(!parse_perf_config(bad.data(),unsigned(bad.size()),config));
  assert(argc == 2);
  std::ifstream stream(argv[1], std::ios::binary);
  const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(stream)), {});
  assert(bytes.size() > 128);
  Runtime reference(bytes), candidate(bytes);
  Worker worker;
  std::uint16_t tokens[64]{};unsigned count = 0;
  assert(reference.model.encode("Задача: сложи R0 и R1.", tokens, 64, count) == ModelStatus::OK && count >= 4);
  const auto vocab = reference.model.config().vocab;
  std::vector<float> a(vocab), b(vocab);
  unsigned comparisons = 0;
  for (unsigned mode = 0; mode < 4; ++mode) {
    std::vector<std::vector<float>> oracle;
    std::vector<std::uint32_t> checksum;
    reference.model.reset();
    for (unsigned p = 0; p < 4; ++p) {
      std::uint16_t best = 0;
      assert(reference.forward(tokens[p], Arithmetic(mode), best, a.data()) == ModelStatus::OK);
      oracle.push_back(a);
      checksum.push_back(reference.model.compute_metrics().checksum);
    }
    for (auto kernel : {LinearKernel::FLASH, LinearKernel::SRAM}) {
      for (bool parallel : {false, true}) {
        candidate.configure(kernel, parallel ? &worker : nullptr);
        candidate.model.reset();
        for (unsigned p = 0; p < 4; ++p) {
          std::uint16_t best = 0;
          assert(candidate.forward(tokens[p], Arithmetic(mode), best, b.data()) == ModelStatus::OK);
          assert(std::memcmp(oracle[p].data(), b.data(), vocab * sizeof(float)) == 0);
          assert(candidate.model.compute_metrics().checksum==checksum[p]);
          assert(best == std::max_element(b.begin(), b.end()) - b.begin());
          if (parallel) assert(candidate.model.compute_metrics().worker_rows > 0);
          ++comparisons;
        }
      }
    }
  }
  for (bool filter : {false, true}) {
    reference.model.reset();candidate.model.reset();
    candidate.configure(LinearKernel::SRAM, &worker, filter);
    for (unsigned p = 0; p < 4; ++p) {
      std::uint16_t ar = 0, br = 0;
      assert(reference.forward(tokens[p], Arithmetic::LUT_FLOAT32, ar, nullptr, sparse) == ModelStatus::OK);
      assert(candidate.forward(tokens[p], Arithmetic::LUT_FLOAT32, br, nullptr, sparse) == ModelStatus::OK);
      assert(ar == br);
      if (filter) assert(candidate.model.compute_metrics().skipped_rows > vocab / 2);
    }
  }
  candidate.configure(LinearKernel::SRAM, &worker, true);
  candidate.model.reset();std::uint16_t next = 0;
  assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, next, nullptr, none) == ModelStatus::FORMAT);
  assert(candidate.model.position() == 0);
  // Requesting logits preserves all unmasked logits, even with an argmax policy.
  assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, next, b.data(), sparse) == ModelStatus::OK);
  reference.model.reset();std::uint16_t ar = 0;
  assert(reference.forward(tokens[0], Arithmetic::LUT_FLOAT32, ar, a.data(), sparse) == ModelStatus::OK);
  assert(next == ar && std::memcmp(a.data(), b.data(), vocab * sizeof(float)) == 0);
  // Failure/refusal paths must not leave a worker referencing the old LUT.
  for (int boundary : {0, 1, 20, 100, 500}) {
    candidate.model.reset();candidate.cancel_after = boundary;
    assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, next) == ModelStatus::CANCELLED);
    assert(candidate.model.position() == 0);
    candidate.cancel_after = -1;
    assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, next, b.data()) == ModelStatus::OK);
    reference.model.reset();
    assert(reference.forward(tokens[0], Arithmetic::LUT_FLOAT32, ar, a.data()) == ModelStatus::OK);
    assert(std::memcmp(a.data(), b.data(), vocab * sizeof(float)) == 0);
  }
  for (int boundary : {0, 2, 20, 100, 500}) {
    candidate.model.reset();candidate.fail_read_after = boundary;
    assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, next) == ModelStatus::IO);
    assert(candidate.model.position() == 0);
    candidate.fail_read_after = -1;
  }
  candidate.refuse = true;candidate.model.reset();
  assert(candidate.forward(tokens[0], Arithmetic::LUT_FLOAT32, next, b.data()) == ModelStatus::OK);
  assert(!candidate.model.compute_metrics().worker_jobs);
  assert(std::memcmp(a.data(), b.data(), vocab * sizeof(float)) == 0);
  // A numeric fault in core 1's half of the first tile must join and thaw.
  auto corrupted=bytes;Runtime bad(corrupted);bad.configure(LinearKernel::SRAM,&worker);
  auto word=[&](unsigned at) { std::uint32_t n;std::memcpy(&n,corrupted.data()+at,4);return n; };
  const unsigned tensors=word(15*4),q_projection=tensors+3*32;
  const unsigned scales=word(q_projection+20),columns=word(q_projection+4);
  corrupted[scales+4*columns/16]=1;corrupted[scales+4*columns/16+1]=0x7e;
  assert(bad.forward(tokens[0],Arithmetic::LUT_FLOAT32,next)==ModelStatus::NUMERIC && bad.model.position()==0);
  // Fill the actual 512-position KV, comparing all linear-row hashes and
  // every KV byte, with full logits at distant positions. No short-context
  // equivalence is extrapolated into a long-context speed/quality claim.
  reference.model.reset();candidate.model.reset();candidate.refuse=false;
  candidate.configure(LinearKernel::SRAM,&worker);
  const unsigned context=reference.model.config().context;
  for(unsigned p=0;p<context;++p) {
    const bool output=p==0 || p==context/4 || p==context/2 || p+1==context;
    assert(reference.forward(tokens[p%count],Arithmetic::LUT_FLOAT32,ar,output?a.data():nullptr,nullptr,output)==ModelStatus::OK);
    assert(candidate.forward(tokens[p%count],Arithmetic::LUT_FLOAT32,next,output?b.data():nullptr,nullptr,output)==ModelStatus::OK);
    assert(reference.model.compute_metrics().checksum==candidate.model.compute_metrics().checksum);
    if(output) { assert(ar==next && std::memcmp(a.data(),b.data(),vocab*sizeof(float))==0);++comparisons; }
  }
  assert(reference.cache==candidate.cache && candidate.model.position()==context);
  assert(candidate.forward(tokens[0],Arithmetic::LUT_FLOAT32,next)==ModelStatus::CONTEXT);
  std::printf("parallel: PASS; bit-identical full-logit comparisons=%u, worker_jobs=%u; context=%u KV=%zu bytes exact; mask/cancel/retry/io/numeric/refusal/join/thaw PASS\n",
              comparisons, worker.submitted,context,reference.cache.size());
}
