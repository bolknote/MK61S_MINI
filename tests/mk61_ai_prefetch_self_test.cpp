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
  bool cache_pending=false,refuse_cache=false,fail_cache=false;
  block_io::ReadSpan cache_spans[16];unsigned cache_count=0,cache_batches=0;
  int cancel_after = -1, fail_finish_after = -1;
  unsigned began = 0, finished = 0, overlapped = 0;
  unsigned row_limit=8;
  unsigned layout_refusals=0;
  bool optimized=true;
  bool lut8=false;
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
  static bool begin_kv(void *p,const block_io::ReadSpan *spans,unsigned count) {
    auto &r=*static_cast<Runtime*>(p);r.owner();assert(!r.pending && !r.cache_pending);
    assert(r.cpu.submitted==r.cpu.joined);
    if(r.refuse_cache)return false;
    assert(count && count<=16);unsigned total=0;
    for(unsigned i=0;i<count;++i) {
      assert(spans[i].offset<=r.cache.size() && spans[i].bytes<=r.cache.size()-spans[i].offset);
      assert(!(spans[i].offset&15) && !(spans[i].bytes&15));
      assert(static_cast<unsigned char*>(spans[i].destination)==static_cast<unsigned char*>(spans[0].destination)+total);
      total+=spans[i].bytes;
    }
    assert(total<=2048);std::copy(spans,spans+count,r.cache_spans);r.cache_count=count;
    r.cache_pending=true;++r.cache_batches;return true;
  }
  static bool finish_kv(void *p) {
    auto &r=*static_cast<Runtime*>(p);r.owner();assert(r.cache_pending);
    for(unsigned i=0;i<r.cache_count;++i) {
      const auto &span=r.cache_spans[i];
      std::memcpy(span.destination,r.cache.data()+span.offset,span.bytes);
      if(r.fail_cache)break;
    }
    r.cache_pending=false;return !r.fail_cache;
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
      if ((spans[i].offset & 15) || (spans[i].bytes & 15)) return false;
      if (static_cast<std::uint8_t *>(spans[i].destination) !=
          static_cast<std::uint8_t *>(spans[0].destination) + total) {
        ++r.layout_refusals;return false;
      }
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
  explicit Runtime(const std::vector<std::uint8_t> &p,unsigned rows=8,bool optim=true,bool lut=false) : package(p),row_limit(rows),optimized(optim),lut8(lut) {
    assert(model.open({this, unsigned(p.size()), read, nullptr, begin, finish}) == ModelStatus::OK);
    ComputeExecution plan{};plan.tile_rows=row_limit;plan.share_kv=optimized;plan.lut8=lut8;model.execution(plan);
    workspace.resize((model.workspace_bytes() + 7) / 8 + 8);
    std::fill(workspace.end() - 8, workspace.end(), UINT64_C(0xb00f61a1b00f61a1));
    cache.resize(model.cache_bytes());
    assert(model.bind(workspace.data(), model.workspace_bytes(),
                      {this, unsigned(cache.size()), read_kv, write_kv,begin_kv,finish_kv}) == ModelStatus::OK);
    configure(true);
  }
  void configure(bool prefetch, bool filter = false) {
    ComputeExecution e{};e.context = this;e.kernel = LinearKernel::SRAM;
    e.prefetch = prefetch;e.filter_head = filter;e.tile_rows=row_limit;
    e.reuse_activations=optimized;e.share_kv=optimized;e.batch_kv=optimized;
    e.lut8=lut8;
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
    assert(!busy && !pending && !cache_pending && began == finished && cpu.submitted == cpu.joined);
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
  assert(argc == 2 || argc==3);std::ifstream stream(argv[1], std::ios::binary);
  const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(stream)), {});
  auto packed=bytes;
  if(argc==3) {std::ifstream input(argv[2],std::ios::binary);packed.assign(std::istreambuf_iterator<char>(input),{});}
  Runtime control(bytes,8,false), candidate(packed,28,true,argc==3);control.configure(false);
  const auto large_plan=candidate.model.execution();
  auto small_plan=large_plan;small_plan.tile_rows=24;
  candidate.model.execution(small_plan);
  const auto old_size=candidate.model.workspace_bytes();
  candidate.model.execution(large_plan);
  if(candidate.model.config().hidden==128 && candidate.model.config().intermediate==384)
    assert(candidate.model.workspace_bytes()==old_size+592);
  if(candidate.lut8) {
    auto no_table=large_plan;no_table.lut8=false;candidate.model.execution(no_table);
    const auto small=candidate.model.workspace_bytes();candidate.model.execution(large_plan);
    assert(candidate.model.workspace_bytes()==small+2064);
  }
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
      const auto &old=control.model.compute_metrics(),&fast=candidate.model.compute_metrics();
      const auto &config=candidate.model.config();
      if(config.heads==2*config.kv_heads)
        {
          assert(fast.attention_read_bytes*2==old.attention_read_bytes);
          assert(fast.attention_read_transactions<=old.attention_read_transactions/2);
          if(!candidate.refuse_cache) {
            const unsigned columns=std::max(std::max(config.hidden,config.intermediate),config.heads*config.head_dim);
            const unsigned block=std::min(16U,std::min(2048U,columns*16)/(config.head_dim*4));
            assert(fast.attention_read_transactions==config.layers*config.kv_heads*2*((p+block)/block));
          }
          if(p>0 && !candidate.refuse_cache)assert(fast.attention_batches>0);
          if(p>3 && !candidate.refuse_cache)assert(fast.attention_worker_jobs>0);
        }
      if(mode!=Arithmetic::FLOAT32) {
        assert(fast.activation_preparations==4*config.layers+(output?1:0));
        assert(fast.activation_reuses==3*config.layers);
      }
      if(candidate.lut8 && mode==Arithmetic::INT8) {
        assert(fast.lut8_preparations==3*config.layers+(output?1:0));
        assert(fast.lut8_reuses==3*config.layers);
        assert(fast.lut8_rows && fast.lut8_rows+config.hidden*config.layers==fast.rows);
      } else assert(!fast.lut8_rows);
      if (output) { assert(left == right && !std::memcmp(a.data(), b.data(), vocab * sizeof(float)));++comparisons; }
      assert(!control.model.compute_metrics().prefetches);
      assert(candidate.model.compute_metrics().prefetches == 0 || candidate.overlapped > 0);
    }
  };
  for (unsigned mode = 0; mode < 4; ++mode) compare(Arithmetic(mode), 2, true);
  if(candidate.lut8) {
    // Unconverted files retain direct dispatch. The switch can also be
    // disabled on a hybrid package for independent numerical comparison.
    for(bool converted:{false,true}) {
      Runtime fallback(converted?packed:bytes,28,true,!converted);
      control.model.reset();
      assert(control.forward(tokens[0],Arithmetic::INT8,left,a.data())==ModelStatus::OK);
      assert(fallback.forward(tokens[0],Arithmetic::INT8,right,b.data())==ModelStatus::OK);
      assert(!fallback.model.compute_metrics().lut8_rows && left==right);
      assert(!std::memcmp(a.data(),b.data(),vocab*sizeof(float)));
    }
  }
  assert(candidate.model.compute_metrics().worker_jobs < control.model.compute_metrics().worker_jobs);
  compare(Arithmetic::LUT_FLOAT32, 64, false);
  unsigned context_checked=64;
  if(candidate.model.config().context>=256) {
    const unsigned length=candidate.lut8?candidate.model.config().context:256;
    compare(Arithmetic::INT8,length,false);context_checked=length;
  }
  assert(candidate.layout_refusals==0);
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
  const auto fault_mode=candidate.lut8?Arithmetic::INT8:Arithmetic::LUT_FLOAT32;
  for (int boundary : {0, 1, 20, 100}) {
    candidate.model.reset();candidate.cancel_after = boundary;
    assert(candidate.forward(tokens[0], fault_mode, right) == ModelStatus::CANCELLED);
    assert(candidate.model.position() == 0);candidate.cancel_after = -1;
    compare(fault_mode, 1, true);
  }
  for (int boundary : {0, 1, 50}) {
    candidate.model.reset();candidate.fail_finish_after = boundary;
    assert(candidate.forward(tokens[0], fault_mode, right) == ModelStatus::IO);
    assert(candidate.model.position() == 0);candidate.fail_finish_after = -1;
    compare(fault_mode, 1, true);
  }
  candidate.refuse_cache=true;compare(Arithmetic::INT8,3,true);candidate.refuse_cache=false;
  candidate.model.reset();
  assert(candidate.forward(tokens[0],Arithmetic::INT8,right)==ModelStatus::OK);
  candidate.fail_cache=true;
  assert(candidate.forward(tokens[1],Arithmetic::INT8,right)==ModelStatus::IO);
  assert(candidate.model.position()==1 && !candidate.cache_pending);candidate.fail_cache=false;
  compare(Arithmetic::INT8,3,true);
  // Numeric failure with a next-tile DMA in flight still joins both owners.
  auto corrupted = packed;Runtime bad(corrupted,8,true,candidate.lut8);
  auto word = [&](unsigned at) { std::uint32_t n;std::memcpy(&n, corrupted.data() + at, 4);return n; };
  const unsigned projection = word(15 * 4) + 3 * 32;
  const unsigned scales = word(projection + 20), columns = word(projection + 4);
  corrupted[scales + 4 * columns / 16] = 1;corrupted[scales + 4 * columns / 16 + 1] = 0x7e;
  assert(bad.forward(tokens[0], fault_mode, right) == ModelStatus::NUMERIC);
  assert(bad.began && bad.model.position() == 0);
  std::printf("prefetch: PASS; %u full-logit comparisons, %u-position KV exact, %u DMA requests, %u overlapping worker jobs; sparse/refusal/cancel/retry/DMA-fault/numeric/join/thaw/guards PASS\n",
              comparisons, context_checked,candidate.began, candidate.overlapped);
  std::printf("KV gather: %u joined batches; bounded shared scratch, exact transactions/bytes, refusal and partial-write failure PASS\n",candidate.cache_batches);
}
