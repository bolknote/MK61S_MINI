#include "mk61_ai_agent.hpp"
#include "mk61emu_core.h"
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <vector>
namespace {
using namespace mk61ai;
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
  Store store() { return {this, read, write, exists}; }
};
bool read_memory(void *p, std::uint32_t at, void *out, unsigned n) {
  auto &b = *static_cast<std::vector<std::uint8_t> *>(p);
  if (at > b.size() || n > b.size() - at)
    return false;
  std::memcpy(out, b.data() + at, n);
  return true;
}
bool write_memory(void *p, std::uint32_t at, const void *in, unsigned n) {
  auto &b = *static_cast<std::vector<std::uint8_t> *>(p);
  if (at > b.size() || n > b.size() - at)
    return false;
  std::memcpy(b.data() + at, in, n);
  return true;
}
// An explicit deterministic inference backend qualifies the controller. It
// uses the real tokenizer and real emulator, but is never a model-quality test.
struct Script {
  Model &tokenizer;
  std::vector<std::vector<std::uint16_t>> replies;
  unsigned position = 0, turn = 0, at = 0;
  bool begun = false;
  Script(Model &model, std::initializer_list<std::string> messages)
      : tokenizer(model) {
    for (const auto &text : messages) {
      std::uint16_t ids[2048];
      unsigned n = 0;
      assert(model.encode(text.c_str(), ids, 2048, n, false) ==
             ModelStatus::OK);
      replies.emplace_back(ids, ids + n);
    }
  }
  Inference engine() {
    return {
        this,
        [](void *p) -> const ModelConfig & {
          return static_cast<Script *>(p)->tokenizer.config();
        },
        [](void *p) { return static_cast<Script *>(p)->position; },
        [](void *p, unsigned n) {
          auto &s = *static_cast<Script *>(p);
          if (n > s.position)
            return false;
          s.position = n;
          s.at = 0;
          if (s.begun)
            ++s.turn;
          s.begun = true;
          return true;
        },
        [](void *p, const char *t, std::uint16_t *ids, unsigned cap,
           unsigned &n, bool bos) {
          return static_cast<Script *>(p)->tokenizer.encode(t, ids, cap, n,
                                                            bos);
        },
        [](void *p, std::uint16_t id, char *out, unsigned cap, unsigned &n) {
          return static_cast<Script *>(p)->tokenizer.decode(id, out, cap, n);
        },
        [](void *p, std::uint16_t, bool output, std::uint16_t &best,
           bool (*service)(void *), void *raw, Arithmetic,
           bool (*allowed)(void *, std::uint16_t), void *policy) {
          auto &s = *static_cast<Script *>(p);
          if (service && !service(raw))
            return ModelStatus::CANCELLED;
          if (s.position >= s.tokenizer.config().context)
            return ModelStatus::CONTEXT;
          if (output) {
            const auto &reply = s.replies[std::min<unsigned>(
                s.turn, unsigned(s.replies.size() - 1))];
            if (s.at >= reply.size())
              return ModelStatus::FORMAT;
            best = reply[s.at];
            assert(!allowed || allowed(policy, best));
            ++s.at;
          }
          ++s.position;
          return ModelStatus::OK;
        }};
  }
};
struct Pump {
  bool cancel = false;
  static bool service(void *p) { return !static_cast<Pump *>(p)->cancel; }
};
void finish(Agent &agent) {
  unsigned ticks = 0;
  while (agent.active() && ticks++ < 5000)
    agent.tick();
  assert(!agent.active());
}
void example(Session &s, unsigned i, const char *text) {
  Example e;
  assert(parse_example(text, e) && set_example(s, i, e));
}
} // namespace
int main(int argc, char **argv) {
  using namespace mk61ai;
  assert(argc == 2);
  std::ifstream file(argv[1], std::ios::binary);
  assert(file);
  std::vector<std::uint8_t> package((std::istreambuf_iterator<char>(file)), {}),
      cache;
  Model model;
  assert(model.open({&package, unsigned(package.size()), read_memory,
                     nullptr}) == ModelStatus::OK);
  cache.resize(model.cache_bytes());
  std::vector<std::uint64_t> work((model.workspace_bytes() + 7) / 8);
  assert(model.bind(work.data(), work.size() * 8,
                    {&cache, unsigned(cache.size()), read_memory,
                     write_memory}) == ModelStatus::OK);
  core_61::set_expanded_program_mode(false);
  core_61::enable();
  {
    Disk disk;
    Session s;
    s.id = 1;
    assert(set_task(s, "X=R0+R1.", false));
    example(s, 0, "R0=7 R1=5 => X=12 PRESERVE=R0,R1");
    example(s, 1, "R0=-4 R1=10 => X=6 PUBLIC=0");
    char prompt[2049];
    assert(build_prompt(s, prompt, sizeof(prompt)) &&
           !std::strstr(prompt, "60611050") && !std::strstr(prompt, "R0=-4"));
    Script script(model, {"<plan>Сложить</plan><write>60611050</write><run/>"});
    Agent agent(s, disk.store(), script.engine());
    Pump pump;
    assert(agent.start());
    pump.cancel = true;
    agent.tick(Pump::service, &pump);
    assert(agent.paused() && script.position == 0);
    pump.cancel = false;
    assert(agent.start());
    bool interrupted = false;
    for (unsigned i = 0; agent.active() && i < 3000; ++i) {
      if (!interrupted && agent.phase() == Agent::Phase::ADVANCE) {
        const auto pos = script.position;
        const std::string reply = s.reply;
        pump.cancel = true;
        agent.tick(Pump::service, &pump);
        assert(agent.paused() && script.position == pos && s.reply == reply);
        pump.cancel = false;
        interrupted = true;
        assert(agent.start());
      }
      agent.tick(Pump::service, &pump);
    }
    assert(interrupted && all_passed(s) && s.state == RunState::FINISHED);
    Session restored;
    assert(load_session(disk.store(), 1, restored) && all_passed(restored));
  }
  {
    Disk disk;
    Session s;
    s.id = 2;
    assert(set_task(s, "Покажи 0, сохрани R0.", false));
    example(s, 0, "R0=7 => X=0 PRESERVE=R0");
    std::string answer = "<write>";
    for (unsigned i = 0; i < 104; ++i)
      answer += "00 ";
    answer += "50</write><run/>";
    Script script(model, {answer});
    Agent agent(s, disk.store(), script.engine());
    assert(agent.start());
    finish(agent);
    assert(all_passed(s) && s.program.size == 105 && agent.generated() > 160 &&
           agent.generation_limit() > 330);
  }
  {
    Disk disk;
    Session s;
    s.id = 3;
    assert(set_task(s, "Последний шаг должен остановить программу.", false));
    std::uint8_t code[105]{};
    assert(accept_program(disk.store(), s, code, 105));
    example(s, 0, "=> X=0");
    Script script(model, {"<patch>68:50</patch><run/>"});
    Agent agent(s, disk.store(), script.engine());
    assert(agent.start());
    assert(agent.prompt_size() < model.config().context - 24);
    finish(agent);
    assert(all_passed(s) && s.program.size == 105 &&
           s.program.bytes[104] == 0x50);
    for (unsigned i = 0; i < 104; ++i)
      assert(s.program.bytes[i] == 0);
  }
  {
    Disk disk;
    Session s;
    s.id = 4;
    assert(set_task(s, "X=R0+R1.", false));
    example(s, 0, "R0=12 R1=0 => X=12");
    example(s, 1, "R0=7 R1=5 => X=12");
    Script script(model,
                  {"<write>6050</write><run/>", "<write>0950</write><run/>",
                   "<write>6050</write><run/>"});
    Agent agent(s, disk.store(), script.engine());
    assert(agent.start());
    finish(agent);
    assert(s.state == RunState::LIMIT && s.program.version == 1 &&
           s.last_version == 2 && passed_examples(s) == 1 &&
           s.best_score == 1 && agent.metrics().reused_tokens > 0);
  }
  {
    // Script only the model output. All tokenization, timing boundaries and
    // execution below belong to the real controller/core, including token 1
    // produced by the final prefill step and an interrupted decode.
    Disk local;
    Session task;
    task.id = 900;
    assert(set_task(task, "Вычисли синус числа 22.", false));
    const std::string reply = "<write>02 02 1C 50</write><run/>";
    Script script(model, {reply});
    Agent live(task, local.store(), script.engine());
    std::uint32_t ticks = 0;
    live.clock([](void *p) { return *static_cast<std::uint32_t *>(p) += 17000; }, &ticks);
    live.default_angle(0);
    assert(live.start());
    unsigned guard = 0;
    while (!live.metrics().output_tokens && ++guard < 5000) live.tick();
    assert(live.metrics().output_tokens == 1 && live.metrics().decode_tokens == 0);
    live.request_pause(); live.tick();
    const auto paused = live.metrics().output_tokens;
    assert(!live.active() && live.paused() && paused == 1);
    assert(live.start()); finish(live);
    assert(live.metrics().output_tokens == script.replies[0].size());
    assert(live.metrics().decode_tokens + 1 == live.metrics().output_tokens);
    assert(live.metrics().prefill_tokens && live.metrics().prefill_us &&
           live.metrics().decode_us && live.metrics().tool_us);
    const auto result = live.last_result();
    assert(result.status == Execution::STOPPED && result.commands == 4 &&
           result.version == task.program.version && result.task_revision == task.task_revision &&
           result.x == 0.3746066 && live.last_angle() == 0 && !task.test_count);
    live.reset();
    assert(live.last_result().status == Execution::NONE);
  }
  {
    ToolGrammar g;
    g.reset(false, false);
    const std::string text = "<write>60611050</write><run/>";
    for (char c : text)
      assert(g.accept(&c, 1));
    assert(g.complete());
    g.reset(false, true);
    assert(!g.accept("<write>", 7));
    g.reset(true, false);
    assert(g.accept("<patch>68:50</patch><run/>", 26) && g.complete());
    g.reset(false, false);
    assert(!g.accept("<shell/>", 8));
    g.reset(false, false);
    assert(g.accept("<plan>", 6));
    assert(!g.accept("\xED\xA0", 2));
    assert(!g.accept("\xF4\x90", 2));
    assert(g.accept("\xD0", 1));
    assert(!g.accept("</plan>", 7));
    assert(g.accept("\x90</plan><done/>", 15) && g.complete());
  }
  std::cout << "AI controller: 105-byte write beyond 160 tokens, full-page "
               "patch, hidden cases, pause/resume, prefix reuse, cycle stop "
               "and best-version rollback PASS\n";
}
