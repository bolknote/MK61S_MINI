#include "mk61_ai_agent.hpp"
#include "mk61_ai_worker_fixture.hpp"
#include "mk61emu_core.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <vector>
namespace {
struct Disk {
  std::map<std::string, std::vector<std::uint8_t>> files;
  static bool read(void *p, const char *path, void *out, unsigned cap,
                   unsigned &n) {
    auto &d = *static_cast<Disk *>(p);
    auto at = d.files.find(path);
    if (at == d.files.end() || at->second.size() > cap)
      return false;
    n = unsigned(at->second.size());
    std::memcpy(out, at->second.data(), n);
    return true;
  }
  static bool write(void *p, const char *path, const void *bytes, unsigned n) {
    auto *b = static_cast<const std::uint8_t *>(bytes);
    static_cast<Disk *>(p)->files[path] = {b, b + n};
    return true;
  }
  static bool exists(void *p, const char *path) {
    return static_cast<Disk *>(p)->files.count(path);
  }
  mk61ai::Store store() { return {this, read, write, exists}; }
};
bool read_memory(void *p, std::uint32_t at, void *out, unsigned n) {
  auto &v = *static_cast<std::vector<std::uint8_t> *>(p);
  if (at > v.size() || n > v.size() - at)
    return false;
  std::memcpy(out, v.data() + at, n);
  return true;
}
bool write_memory(void *p, std::uint32_t at, const void *bytes, unsigned n) {
  auto &v = *static_cast<std::vector<std::uint8_t> *>(p);
  if (at > v.size() || n > v.size() - at)
    return false;
  std::memcpy(v.data() + at, bytes, n);
  return true;
}
struct Pump {
  unsigned calls = 0;
  bool cancel = false;
  int cancel_after=-1;
  static bool tick(void *p) {
    auto &pump = *static_cast<Pump *>(p);
    ++pump.calls;
    return !pump.cancel && (pump.cancel_after<0 || pump.cancel_after-->0);
  }
};
// A valid Qwen layout can have a Q width larger than both hidden and FFN.
// Its O projection must still fit the activation and LUT work areas.
void wide_head_layout(std::vector<std::uint8_t> package) {
  using namespace mk61ai;
  auto word = [&](unsigned at, std::uint32_t value) {
    for (unsigned i = 0; i < 4; ++i)
      package[at + i] = std::uint8_t(value >> (8 * i));
  };
  auto get = [&](unsigned at) {
    return std::uint32_t(package[at]) | (std::uint32_t(package[at + 1]) << 8) |
           (std::uint32_t(package[at + 2]) << 16) |
           (std::uint32_t(package[at + 3]) << 24);
  };
  const unsigned table = get(60), layers = get(16), vocab = get(40);
  word(20, 32);
  word(24, 32);
  word(28, 16);
  word(32, 8);
  word(36, 64);
  word(44, 1);
  for (unsigned i = 0; i < 2 + 11 * layers; ++i) {
    unsigned rows = i == 0 ? vocab : 1, cols = 32;
    bool vector = i == 1;
    if (i >= 2)
      switch ((i - 2) % 11) {
      case 0:
      case 7:
        vector = true;
        break;
      case 1:
        rows = 1024;
        break;
      case 2:
      case 3:
        rows = 512;
        break;
      case 4:
      case 5:
        vector = true;
        cols = 64;
        break;
      case 6:
        rows = 32;
        cols = 1024;
        break;
      default:
        rows = 32;
        break;
      }
    const unsigned bytes = vector ? cols * 4 : rows * cols / 2,
                   scales = vector ? 0 : rows * cols / 16,
                   at = unsigned(package.size());
    package.resize(at + bytes + scales, 0);
    if (vector)
      for (unsigned j = 0; j < cols; ++j)
        word(at + 4 * j, 0x3f800000U);
    const std::uint32_t fields[] = {rows,
                                    cols,
                                    vector ? 32U : 4U,
                                    vector ? 0U : 256U,
                                    at,
                                    vector ? 0U : at + bytes,
                                    bytes,
                                    scales};
    for (unsigned j = 0; j < 8; ++j)
      word(table + 32 * i + 4 * j, fields[j]);
  }
  auto crc = [&](unsigned first, unsigned n) {
    std::uint32_t value = ~0U;
    for (unsigned i = 0; i < n; ++i) {
      value ^= package[first + i];
      for (unsigned j = 0; j < 8; ++j)
        value = (value >> 1) ^ (0xedb88320U & (0U - (value & 1)));
    }
    return ~value;
  };
  word(12, unsigned(package.size()));
  word(116, crc(128, unsigned(package.size()) - 128));
  word(124, crc(0, 124));
  Model model;
  assert(model.open({&package, unsigned(package.size()), read_memory,
                     nullptr}) == ModelStatus::OK);
  std::vector<std::uint8_t> cache(model.cache_bytes());
  std::vector<std::uint64_t> work((model.workspace_bytes() + 7) / 8);
  assert(model.bind(work.data(), work.size() * 8,
                    {&cache, unsigned(cache.size()), read_memory,
                     write_memory}) == ModelStatus::OK);
  std::uint16_t best = 999;
  for(auto kernel:{LinearKernel::REFERENCE,LinearKernel::FLASH_CODE,LinearKernel::SRAM}) {
    ComputeExecution execution{};execution.kernel=kernel;model.execution(execution);
    for(auto arithmetic:{Arithmetic::FLOAT32,Arithmetic::INT8,Arithmetic::LUT_INT8,Arithmetic::LUT_FLOAT32}) {
      model.reset();
      assert(model.forward(1,true,best,nullptr,nullptr,arithmetic)==ModelStatus::OK && best==0);
    }
  }
}
} // namespace
int main(int argc, char **argv) {
  using namespace mk61ai;
  assert(argc == 2);
  std::ifstream file(argv[1], std::ios::binary);
  assert(file);
  std::vector<std::uint8_t> package((std::istreambuf_iterator<char>(file)), {}),
      cache;
  wide_head_layout(package);
  Model model;
  assert(model.open({&package, unsigned(package.size()), read_memory,
                     nullptr}) == ModelStatus::OK);
  cache.resize(model.cache_bytes());
  std::vector<std::uint64_t> work((model.workspace_bytes() + 7) / 8);
  assert(model.bind(work.data(), work.size() * 8,
                    {&cache, unsigned(cache.size()), read_memory,
                     write_memory}) == ModelStatus::OK);
  TestAiWorker worker;
  ComputeExecution execution{};execution.context=&worker;execution.kernel=LinearKernel::SRAM;execution.filter_head=true;
  execution.submit=[](void *p,void (*fn)(void*),void *job) { return static_cast<TestAiWorker*>(p)->submit(fn,job); };
  execution.join=[](void *p) { static_cast<TestAiWorker*>(p)->join(); };
  model.execution(execution);
  core_61::set_expanded_program_mode(false);
  core_61::enable();
  Disk disk;
  Session s;
  s.id = 61;
  assert(set_task(s, "X = R0 + R1.", false));
  Example e;
  assert(parse_example("R0=7 R1=5 => X=12", e) && set_example(s, 0, e));
  assert(parse_example("R0=-4 R1=10 => X=6", e) && set_example(s, 1, e));
  Agent agent(s, disk.store(), model);
  Pump pump;
  assert(agent.start());
  pump.cancel = true;
  agent.tick(Pump::tick, &pump);
  assert(!agent.active() && s.state == RunState::PAUSED &&
         model.position() == 0);
  pump.cancel = false;
  assert(agent.start());
  unsigned ticks = 0;
  bool paused_advance = false;
  while (agent.active() && ticks++ < 4000) {
    if (!paused_advance && agent.phase() == Agent::Phase::ADVANCE) {
      const auto position = model.position();
      const std::string reply = s.reply;
      pump.cancel_after = 20;
      agent.tick(Pump::tick, &pump);
      assert(!agent.active() && s.state == RunState::PAUSED &&
             model.position() == position && s.reply == reply);
      pump.cancel_after = -1;
      assert(worker.submitted==worker.joined);
      paused_advance = true;
      assert(agent.start());
    }
    agent.tick(Pump::tick, &pump);
  }
  std::fprintf(stderr,
               "native agent: attempts=%u version=%lu checks=%u/%u ticks=%u "
               "feedback=%s\n",
               unsigned(s.attempts), (unsigned long)s.program.version,
               passed_examples(s), unsigned(s.test_count), ticks, s.feedback);
  // Quality is intentionally not asserted by an infrastructure smoke test.
  // The frozen held-out suite reports every functional failure separately.
  assert(!agent.active() && s.state != RunState::RUNNING &&
         s.state != RunState::ERROR && pump.calls && paused_advance);
  Session restored;
  assert(load_session(disk.store(), 61, restored) &&
         restored.program.size == s.program.size);
  // A manual task edit invalidates results; test-only execution does not need a
  // loaded model.
  agent.reset();
  assert(set_task(s, "Сохрани исходные регистры.", true));
  assert(!all_passed(s));
  if (valid_program(s.program)) {
    Model empty;
    Agent manual(s, disk.store(), empty);
    assert(manual.run_tests());
    while (manual.active())
      manual.tick();
    assert(result_current(s, 0) && result_current(s, 1));
  }
  assert(worker.submitted>0 && worker.submitted==worker.joined);
  std::puts("Native dual-thread model pause/resume and joined lifecycle PASS");
  std::puts("Native real-model smoke: bounded protocol/tools/session lifecycle "
            "PASS; solution quality is reported by the held-out evaluator");
}
