#ifndef MK61_AI_AGENT_HPP
#define MK61_AI_AGENT_HPP
#include "mk61_ai_grammar.hpp"
#include "mk61_ai_harness.hpp"
#include "mk61_ai_model.hpp"
namespace mk61ai {
struct Executor {
  void *context = nullptr;
  Result (*run)(void *, const Program &, const Example &, std::uint32_t,
                bool (*)(void *), void *, Trace *, unsigned *) = nullptr;
};
Executor local_executor();
// Local inference is the default. The interface also permits deterministic
// protocol tests and a later on-device coprocessor without changing the FSM.
struct Inference {
  void *context = nullptr;
  const ModelConfig &(*configuration)(void *) = nullptr;
  unsigned (*cursor)(void *) = nullptr;
  bool (*seek)(void *, unsigned) = nullptr;
  ModelStatus (*encode_text)(void *, const char *, std::uint16_t *, unsigned,
                             unsigned &, bool) = nullptr;
  ModelStatus (*decode_token)(void *, std::uint16_t, char *, unsigned,
                              unsigned &) = nullptr;
  ModelStatus (*step)(void *, std::uint16_t, bool, std::uint16_t &,
                      bool (*)(void *), void *, Arithmetic,
                      bool (*)(void *, std::uint16_t), void *) = nullptr;
  const ModelConfig &config() const { return configuration(context); }
  unsigned position() const { return cursor(context); }
  void reset() { seek(context, 0); }
  bool rewind(unsigned n) { return seek(context, n); }
  ModelStatus encode(const char *text, std::uint16_t *ids, unsigned cap,
                     unsigned &n, bool bos = true) {
    return encode_text(context, text, ids, cap, n, bos);
  }
  ModelStatus decode(std::uint16_t token, char *text, unsigned cap,
                     unsigned &n) {
    return decode_token(context, token, text, cap, n);
  }
  ModelStatus forward(std::uint16_t token, bool output, std::uint16_t &best,
                      bool (*service)(void *), void *raw, Arithmetic mode,
                      bool (*allowed)(void *, std::uint16_t), void *policy) {
    return step(context, token, output, best, service, raw, mode, allowed,
                policy);
  }
};
Inference local_inference(Model &model);
class Agent {
public:
  struct Metrics {
    std::uint64_t prefill_us = 0, decode_us = 0, tool_us = 0;
    std::uint32_t max_tick_us = 0, prefill_tokens = 0, decode_tokens = 0,
                  reused_tokens = 0, output_tokens = 0;
  };
  enum class Phase : std::uint8_t {
    IDLE,
    PREFILL,
    DECODE,
    ADVANCE,
    TESTS,
    TRACE
  };
  Agent(Session &session, Store store, Model &model,
        Executor executor = local_executor());
  Agent(Session &session, Store store, Inference model,
        Executor executor = local_executor());
  bool start(const char *prefix = nullptr);
  bool run_tests(bool trace = false, unsigned index = ~0U);
  void request_pause() { pause_ = true; }
  void reset() {
    phase_ = resume_ = Phase::IDLE;
    pause_ = false;
    last_result_ = {};
  }
  bool active() const { return phase_ != Phase::IDLE; }
  Phase phase() const { return phase_; }
  unsigned prompt_size() const { return prompt_count_; }
  unsigned generated() const { return generated_; }
  unsigned generation_limit() const { return generation_limit_; }
  unsigned reused_prefix() const { return reused_prefix_; }
  bool paused() const { return resume_ != Phase::IDLE; }
  unsigned test_index() const { return test_; }
  const Trace *trace() const { return traces_; }
  unsigned trace_count() const { return trace_count_; }
  void arithmetic(Arithmetic value) {
    if (value != arithmetic_) {
      reset();
      cached_count_ = 0;
      model_.reset();
    }
    arithmetic_ = value;
  }
  void clock(std::uint32_t (*micros)(void *), void *context) {
    micros_ = micros;
    clock_context_ = context;
  }
  const Metrics &metrics() const { return metrics_; }
  // Completed, revision-tagged core output; never infer a result from model text.
  const Result &last_result() const { return last_result_; }
  unsigned last_angle() const { return last_angle_; }
  void default_angle(unsigned angle) { if (angle < 3) default_angle_ = angle; }
  // One token or one bounded emulator request. service() remains active
  // inside both operations; a pause leaves only completed results visible.
  void tick(bool (*service)(void *) = nullptr, void *context = nullptr);

private:
  Session &s_;
  Store store_;
  Inference model_;
  Executor executor_;
  Phase phase_ = Phase::IDLE, resume_ = Phase::IDLE;
  bool pause_ = false, auto_continue_ = false;
  Arithmetic arithmetic_ = Arithmetic::LUT_FLOAT32;
  const char *prefix_ = nullptr;
  char prompt_[Model::MAX_TEXT + 1]{};
  std::uint16_t tokens_[2048]{}, next_ = 0;
  unsigned prompt_count_ = 0, prefilled_ = 0, generated_ = 0, test_ = 0;
  unsigned generation_limit_ = 0, reused_prefix_ = 0, cached_count_ = 0;
  std::uint16_t cached_prefix_[256]{};
  std::uint32_t pending_reply_ = 0;
  ToolGrammar grammar_;
  Metrics metrics_{};
  Result last_result_{};
  unsigned default_angle_ = 1, last_angle_ = 1;
  std::uint32_t (*micros_)(void *) = nullptr;
  void *clock_context_ = nullptr;
  std::uint32_t generation_task_ = 0, generation_program_ = 0,
                generation_cases_ = 0;
  Intent generation_intent_ = Intent::WRITE;
  Trace traces_[16]{};
  unsigned trace_count_ = 0;
  bool begin_turn();
  void process_reply();
  void finish_tests();
  void fail(const char *message);
  bool checkpoint();
  void halt(const char *message);
};
} // namespace mk61ai
#endif
