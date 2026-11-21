#include "mk61_ai_agent.hpp"
#include "mk61_ai_direct.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>
#if defined(PICO_ON_DEVICE)
#define AI_DIRECT_CODE __attribute__((section(".ai_diagnostic_extension"), noinline))
#else
#define AI_DIRECT_CODE
#endif
namespace mk61ai {
namespace {
std::uint32_t text_hash(const char *s) {
  std::uint32_t h = 2166136261U;
  while (*s) {
    h ^= std::uint8_t(*s++);
    h *= 16777619U;
  }
  return h;
}
bool seen(const std::uint32_t *items, unsigned n, std::uint32_t h) {
  for (unsigned i = 0; i < n; ++i)
    if (items[i] == h)
      return true;
  return false;
}
void remember(std::uint32_t *items, std::uint8_t &n, std::uint32_t h) {
  if (seen(items, n, h))
    return;
  if (n == 8) {
    std::memmove(items, items + 1, 7 * sizeof(*items));
    --n;
  }
  items[n++] = h;
}
std::uint32_t case_stamp(const Session &s) {
  std::uint32_t h = s.test_count;
  for (unsigned i = 0; i < s.test_count; ++i)
    h = h * 16777619U ^ s.tests[i].revision;
  return h;
}
bool matches_user(const Result &r, const Example &input) {
  const auto mask = expectation_mask(input);
  for (unsigned i = 0; i < INPUT_COUNT; ++i) {
    if (!(mask & (1U << i))) continue;
    const double expected = expected_value(input, i), actual = r.actual[i];
    if (!std::isfinite(actual) ||
        std::fabs(actual - expected) > std::max(input.absolute, std::fabs(expected) * input.relative))
      return false;
  }
  return true;
}
bool checked_examples(const Session &s) {
  return std::any_of(s.tests, s.tests + s.test_count, has_expectations);
}
void describe_test(char *feedback, unsigned capacity, unsigned index,
                   const Example &e, const Result &r) {
  char inputs[128]{};
  unsigned used = 0;
  for (unsigned j = 0; j < INPUT_COUNT; ++j)
    if (e.inputs & (1U << j)) {
      char b[32];
      if (j < 15)
        std::snprintf(b, sizeof(b), "R%X=%.8g,", j, e.values[j]);
      else
        std::snprintf(b, sizeof(b), "%c=%.8g,", "XYZT"[j - 15],
                      e.values[j]);
      const unsigned n = unsigned(std::strlen(b));
      if (n >= sizeof(inputs) - used)
        break;
      std::memcpy(inputs + used, b, n + 1);
      used += n;
    }
  if (!e.public_case)
    std::snprintf(feedback, capacity,
                  "Скрытый тест %u не пройден; status=%u", index + 1,
                  unsigned(r.status));
  else if (r.mismatch) {
    unsigned ref = 0;
    while (ref + 1 < INPUT_COUNT && !(r.mismatch & (1U << ref)))
      ++ref;
    char name[4];
    if (ref < 15)
      std::snprintf(name, sizeof(name), "R%X", ref);
    else {
      name[0] = "XYZT"[ref - 15];
      name[1] = 0;
    }
    double expected = (e.inputs & (1U << ref)) ? e.values[ref] : 0;
    if (r.failed_stage == 0 && (expectation_mask(e) & (1U << ref)))
      expected = expected_value(e, ref);
    else if (r.failed_stage && r.failed_stage <= e.scenario_count &&
             e.scenario[r.failed_stage - 1].output_index == ref)
      expected = e.scenario[r.failed_stage - 1].expected;
    std::snprintf(feedback, capacity,
                  "FAIL %s ожидалось %s=%.8g; получено %s=%.8g; status=%u",
                  inputs, name, expected, name, r.actual[ref],
                  unsigned(r.status));
  } else
    std::snprintf(feedback, capacity,
                  "RUN %s X=%.8g status=%u; %s", inputs, r.x,
                  unsigned(r.status),
                  has_expectations(e) ? "тест не пройден" : "наблюдение");
}
} // namespace

struct Agent::DirectRun {
  DirectTask spec;
  Program candidate;
  Result results[TEST_COUNT]{}, last{};
  unsigned user = 0, bank = 0, passed = 0, angle = 1;
  bool current = false, observed = false, identical = false;
};
struct Agent::RepairRun {
  Program candidate;
  Result results[TEST_COUNT]{};
  unsigned last_public = TEST_COUNT;
};
Executor local_executor() {
  return {nullptr, [](void *, const Program &p, const Example &e,
                      std::uint32_t revision, bool (*service)(void *),
                      void *context, Trace *trace, unsigned *count) {
            return execute(p, e, revision, service, context, trace, count);
          }};
}
Inference local_inference(Model &m) {
  return {
      &m,
      [](void *p) -> const ModelConfig & {
        return static_cast<Model *>(p)->config();
      },
      [](void *p) { return static_cast<Model *>(p)->position(); },
      [](void *p, unsigned n) { return static_cast<Model *>(p)->rewind(n); },
      [](void *p, const char *t, std::uint16_t *ids, unsigned cap, unsigned &n,
         bool bos) {
        return static_cast<Model *>(p)->encode(t, ids, cap, n, bos);
      },
      [](void *p, std::uint16_t t, char *out, unsigned cap, unsigned &n) {
        return static_cast<Model *>(p)->decode(t, out, cap, n);
      },
      [](void *p, std::uint16_t t, bool output, std::uint16_t &best,
         bool (*service)(void *), void *raw, Arithmetic mode,
         bool (*allowed)(void *, std::uint16_t), void *policy) {
        return static_cast<Model *>(p)->forward(t, output, best, service, raw,
                                                mode, nullptr, allowed, policy);
      },
      &m,
      [](void *p, Arithmetic mode) -> std::size_t {
        const auto &model=*static_cast<Model *>(p);
        return model.execution().pair_prefill?model.prefill_pair_workspace_bytes(mode):0;
      },
      [](void *p, const std::uint16_t (&ids)[2], void *workspace, std::size_t bytes,
         Arithmetic mode, bool (*service)(void *), void *raw) {
        return static_cast<Model *>(p)->prefill_pair(ids,workspace,bytes,mode,service,raw);
      }};
}
Agent::Agent(Session &s, Store store, Model &m, Executor executor)
    : Agent(s, store, local_inference(m), executor) {}
Agent::Agent(Session &session, Store store, Inference model, Executor executor)
    : s_(session), store_(store), model_(model), executor_(executor) {}
Agent::~Agent() = default;
void Agent::reset() {
  phase_ = resume_ = Phase::IDLE;
  pause_ = false;
  last_result_ = {};
  direct_.reset();
  repair_.reset();
  direct_fallback_ = false;
}
void Agent::fail(const char *message) {
  std::snprintf(s_.feedback, sizeof(s_.feedback), "%s", message);
  s_.state = RunState::ERROR;
  phase_ = resume_ = Phase::IDLE;
  direct_.reset();
  repair_.reset();
  direct_fallback_ = false;
  save_session(store_, s_);
}
void Agent::halt(const char *message) {
  if (s_.best_version && s_.best_version != s_.program.version) {
    if (!select_program(store_, s_, s_.best_version)) {
      fail("Не удалось восстановить лучшую версию.");
      return;
    }
    append_event(store_, s_, "ROLLBACK", "restored best tested candidate");
  }
  std::snprintf(s_.feedback, sizeof(s_.feedback), "%s", message);
  s_.state = RunState::LIMIT;
  phase_ = resume_ = Phase::IDLE;
  checkpoint();
}
bool Agent::checkpoint() {
  if (save_session(store_, s_))
    return true;
  fail("Не удалось сохранить задачу на SD.");
  return false;
}
AI_DIRECT_CODE bool Agent::start_direct() {
  if (active() || paused() || s_.intent == Intent::EXPLAIN || !executor_.run)
    return false;
  DirectTask spec;
  Program candidate;
  if (!parse_direct_task(s_.task, default_angle_, spec) || !spec.compile(candidate))
    return false;
  for (unsigned i = 0; i < s_.test_count; ++i)
    if (s_.tests[i].scenario_count || (spec.explicit_angle && s_.tests[i].angle != spec.angle))
      return false;
  std::unique_ptr<DirectRun> run(new (std::nothrow) DirectRun);
  if (!run) return false;
  run->spec = spec;
  run->candidate = candidate;
  run->current = valid_program(s_.program);
  const unsigned length = program_text_size(candidate);
  run->identical = run->current && length == program_text_size(s_.program) &&
                   !std::memcmp(candidate.bytes, s_.program.bytes, length);
  direct_ = std::move(run);
  direct_fallback_ = false;
  pause_ = false;
  last_result_ = {};
  trace_count_ = 0;
  prompt_count_ = generated_ = reused_prefix_ = test_ = 0;
  metrics_.output_token_hash = 0;
  generation_task_ = s_.task_revision;
  generation_program_ = s_.program.version;
  generation_cases_ = case_stamp(s_);
  generation_intent_ = s_.intent;
  s_.state = RunState::RUNNING;
  phase_ = Phase::DIRECT;
  return true;
}
bool Agent::take_direct_fallback() {
  const bool needed = direct_fallback_;
  direct_fallback_ = false;
  return needed;
}
bool Agent::start(const char *prefix) {
  if (active())
    return false;
  if (resume_ != Phase::IDLE) {
    pause_ = false;
    phase_ = resume_;
    resume_ = Phase::IDLE;
    s_.state = RunState::RUNNING;
    return checkpoint();
  }
  prefix_ = prefix;
  last_result_ = {};
  pause_ = false;
  auto_continue_ = true;
  if (s_.attempts >= s_.attempt_limit) {
    if (s_.attempt_limit > 65531) {
      fail("Достигнут предел счётчика попыток.");
      return false;
    }
    s_.attempt_limit += 4;
  }
  return begin_turn();
}
bool Agent::begin_turn() {
  if (!s_.task[0]) {
    s_.state = RunState::NEEDS_INPUT;
    std::snprintf(s_.feedback, sizeof(s_.feedback),
                  "Опиши задачу или нужное исправление.");
    phase_ = Phase::IDLE;
    checkpoint();
    return false;
  }
  if (s_.attempts >= s_.attempt_limit) {
    halt("Лимит попыток. Сохранена лучшая проверенная версия.");
    return false;
  }
  if (spec_enabled_ && s_.intent == Intent::EXPLAIN) {
    fail("Эта модель составляет программы. Режим объяснения ей недоступен.");
    return false;
  }
  if (spec_enabled_ && s_.intent == Intent::FIX && valid_program(s_.program) &&
      !checked_examples(s_)) {
    s_.state = RunState::NEEDS_INPUT;
    std::snprintf(s_.feedback, sizeof(s_.feedback),
                  "Добавь пример с ожидаемым результатом для проверки правки.");
    phase_ = Phase::IDLE;
    checkpoint();
    return false;
  }
  unsigned system_bytes = 0;
  if (!(spec_enabled_ ? spec_.prompt(s_.task, default_angle_, prompt_, sizeof(prompt_),
                                    prefix_io_ ? &system_bytes : nullptr)
                     : build_prompt(s_, prompt_, sizeof(prompt_), prefix_))) {
    fail("Условие и текущая программа слишком длинные. Сократи описание.");
    return false;
  }
  const unsigned capacity = model_.config().context;
  if (!capacity) {
    fail("Модель не загружена.");
    return false;
  }
  const unsigned reserve = 8;
  if (capacity <= reserve) {
    fail("Контекст модели слишком мал для протокола.");
    return false;
  }
  ModelStatus status = ModelStatus::OK;
  const unsigned token_capacity = std::min(2047U, capacity - reserve);
  system_tokens_ = 0;
  if (spec_enabled_) {
    // Newlines are complete BPE pre-token boundaries in this fixed protocol.
    // Stream them without enlarging the model's SRAM tokenization workspace.
    prompt_count_=0;
    for (const char *p=prompt_; *p && status==ModelStatus::OK;) {
      const char *end=std::strchr(p,'\n'); end=end?end+1:p+std::strlen(p);
      const unsigned n=unsigned(end-p); char segment[Model::MAX_TEXT+1];
      if(n>Model::MAX_TEXT){status=ModelStatus::TEXT_LONG;break;}
      std::memcpy(segment,p,n);segment[n]=0;unsigned used=0;
      status=model_.encode(segment,tokens_+prompt_count_,token_capacity-prompt_count_,used,false);
      const unsigned offset = unsigned(p - prompt_);
      if (status == ModelStatus::OK && offset < system_bytes && system_bytes <= offset + n) {
        // BPE can merge across the end of the built-in constant table. Keep
        // only tokens shared with its standalone encoding.
        segment[system_bytes - offset] = 0;
        std::uint16_t fixed[128];
        unsigned count = 0;
        if (model_.encode(segment, fixed, sizeof(fixed) / sizeof(*fixed), count, false) ==
            ModelStatus::OK) {
          const auto matching = std::mismatch(fixed, fixed + std::min(count, used),
                                              tokens_ + prompt_count_).first - fixed;
          system_tokens_ = prompt_count_ + unsigned(matching);
        }
      }
      prompt_count_+=used; p=end;
    }
    if(status==ModelStatus::OK)tokens_[prompt_count_++]=30;
  } else status=model_.encode(prompt_,tokens_,token_capacity,prompt_count_);
  if (status != ModelStatus::OK) {
    s_.state = RunState::NEEDS_INPUT;
    phase_ = Phase::IDLE;
    std::snprintf(s_.feedback, sizeof(s_.feedback),
                  "Контекст заполнен. Сократи условие или программу.");
    checkpoint();
    return false;
  }
  unsigned shared = 0;
  const unsigned maximum =
      std::min({cached_count_, prompt_count_ - 1, model_.position()});
  while (shared < maximum && cached_prefix_[shared] == tokens_[shared])
    ++shared;
  if (!model_.rewind(shared)) {
    model_.reset();
    shared = 0;
  }
  reused_prefix_ = shared;
  metrics_.reused_tokens += shared;
  cached_count_ = std::min(unsigned(sizeof(cached_prefix_) / sizeof(cached_prefix_[0])), prompt_count_);
  std::copy(tokens_, tokens_ + cached_count_, cached_prefix_);
  prefilled_ = shared;
  system_angle_ = default_angle_;
  restore_prefix_ = save_prefix_ = prefix_io_ && shared < system_tokens_;
  generated_ = 0;
  metrics_.output_token_hash = 2166136261U;
  generation_limit_ = capacity - prompt_count_ - (spec_enabled_ ? 4U : 0U);
  grammar_.reset(valid_program(s_.program), s_.intent == Intent::EXPLAIN, false,
                 s_.planning || s_.intent == Intent::EXPLAIN);
  s_.reply[0] = s_.plan[0] = 0;
  ++s_.attempts;
  generation_task_ = s_.task_revision;
  generation_program_ = s_.program.version;
  generation_cases_ = case_stamp(s_);
  generation_intent_ = s_.intent;
  s_.state = RunState::RUNNING;
  phase_ = Phase::PREFILL;
  const char *part=prompt_;bool first=true;
  do {
    char record[1801];unsigned n=unsigned(std::strlen(part));
    if(n>1800){n=1800;while(n&&(static_cast<unsigned char>(part[n])&0xc0)==0x80)--n;}
    std::memcpy(record,part,n);record[n]=0;
    if(!append_event(store_,s_,first?"PROMPT":"PROMPT_PART",record)){
      fail("Не удалось записать историю задачи.");return false;
    }
    first=false;part+=n;
  } while(*part);
  return checkpoint();
}
bool Agent::run_tests(bool trace, unsigned index) {
  if (active() || !valid_program(s_.program))
    return false;
  pause_ = false;
  resume_ = Phase::IDLE;
  direct_.reset();
  direct_fallback_ = false;
  auto_continue_ = false;
  test_ = 0;
  trace_count_ = 0;
  last_result_ = {};
  if (trace) {
    if (index < s_.test_count)
      test_ = index;
    else
      for (unsigned i = 0; i < s_.test_count; ++i)
        if (result_current(s_, i) && !s_.results[i].passed) {
          test_ = i;
          break;
        }
  } else
    invalidate(s_);
  s_.state = RunState::RUNNING;
  phase_ = trace ? Phase::TRACE : Phase::TESTS;
  return checkpoint();
}

AI_DIRECT_CODE void Agent::tick_direct(bool (*service)(void *), void *context) {
  auto &run = *direct_;
  auto stale = [&] {
    return s_.task_revision != generation_task_ || s_.program.version != generation_program_ ||
           s_.intent != generation_intent_ || case_stamp(s_) != generation_cases_;
  };
  auto abandon = [&](bool use_model) {
    direct_.reset();
    direct_fallback_ = use_model;
    phase_ = resume_ = Phase::IDLE;
    s_.state = RunState::DRAFT;
  };
  auto reject = [&] {
    if (run.current && !run.identical) {
      run.current = false;
      run.user = run.bank = run.passed = 0;
      run.observed = false;
      run.last = {};
      test_ = 0;
    } else abandon(true);
  };
  if (stale()) { abandon(false); return; }

  const bool user_case = run.user < s_.test_count;
  const unsigned bank_target = run.spec.registers ? 4 : 1;
  const bool synthetic = !user_case && run.passed < bank_target;
  const bool observe = !user_case && !synthetic && !s_.test_count && !run.observed;
  if (user_case || synthetic || observe) {
    Example input{};
    if (user_case) {
      input = s_.tests[run.user];
      test_ = run.user;
    } else {
      input.angle = run.spec.angle;
      input.max_commands = 128;
      input.max_frames = 1024;
      if (synthetic) {
        // Vary all registers. Invalid inputs of the formula are skipped; a
        // program failure on a defined input always counts against it.
        constexpr double values[] = {0.004399, 0.1375, 0.267, 0.4675, 0.8125, 1.165,
                                     1.5625, 2.18, 7.2, 21.725, 0.3525, 0.7375, 2.21};
        constexpr unsigned n = sizeof(values) / sizeof(*values);
        if (run.bank >= 2 * n) { abandon(true); return; }
        input.inputs = 0x7fffU;
        const unsigned pair = run.bank / 2;
        for (unsigned i = 0; i < 15; ++i) {
          const bool negative = bool(run.bank & 1) != bool(pair && ((i + pair) & 1));
          const double magnitude = values[(pair + 3 * i) % n];
          input.values[i] = negative ? -magnitude : magnitude;
        }
      }
    }
    Example checked;
    if (!run.spec.expectation(input, checked)) {
      if (synthetic) ++run.bank;
      else if (observe) run.observed = true;
      else abandon(true);
      return;
    }
    const auto before = micros_ ? micros_(clock_context_) : 0;
    const Program program = run.current ? s_.program : run.candidate;
    const auto result = executor_.run(executor_.context, program, checked, generation_task_,
                                     service, context, nullptr, nullptr);
    if (micros_) metrics_.tool_us += micros_(clock_context_) - before;
    if (result.status == Execution::CANCELLED) {
      resume_ = phase_;
      phase_ = Phase::IDLE;
      s_.state = RunState::PAUSED;
      checkpoint();
      return;
    }
    if (stale()) { abandon(false); return; }
    if (result.status != Execution::STOPPED || !result.passed || !matches_user(result, input)) {
      reject();
      return;
    }
    if (synthetic) {
      ++run.bank;
      ++run.passed;
    } else {
      run.angle = input.angle;
      run.last = result;
      if (user_case) run.results[run.user++] = result;
      else run.observed = true;
    }
    return;
  }

  const bool unresolved = run.current && !run.identical;
  if (!run.current && !accept_program(store_, s_, run.candidate.bytes, run.candidate.size)) {
    fail("Не удалось сохранить проверенную программу.");
    return;
  }
  for (unsigned i = 0; i < s_.test_count; ++i) {
    s_.results[i] = run.results[i];
    s_.results[i].version = s_.program.version;
  }
  last_result_ = run.last;
  last_result_.version = s_.program.version;
  last_angle_ = run.angle;
  if (!unresolved) {
    s_.best_version = s_.program.version;
    s_.best_score = std::uint8_t(s_.test_count);
  }
  s_.reply[0] = s_.plan[0] = 0;
  s_.model[0] = 0;
  const char *feedback = unresolved
      ? "Текущий код сохранён. Добавь контрольный вход, чтобы различить программы."
      : last_result_.status == Execution::STOPPED ? "Формула разобрана. Программа проверена эмулятором."
      : "Программа проверена. Добавь входные значения для показа результата.";
  std::snprintf(s_.feedback, sizeof(s_.feedback), "%s", feedback);
  if (!append_event(store_, s_, "TOOL", s_.feedback)) {
    fail("Не удалось записать проверку программы.");
    return;
  }
  s_.state = unresolved ? RunState::NEEDS_INPUT : RunState::FINISHED;
  phase_ = Phase::IDLE;
  direct_.reset();
  checkpoint();
}
void Agent::process_reply() {
  if (generation_task_ != s_.task_revision ||
      generation_program_ != s_.program.version ||
      generation_cases_ != case_stamp(s_) || generation_intent_ != s_.intent) {
    phase_ = Phase::IDLE;
    s_.state = RunState::DRAFT;
    std::snprintf(s_.feedback, sizeof(s_.feedback),
                  "Устаревший ответ модели отброшен.");
    checkpoint();
    return;
  }
  if (!append_event(store_, s_, spec_enabled_ ? "COMPILE" : "MODEL", s_.reply)) {
    fail("Не удалось сохранить ответ модели.");
    return;
  }
  Reply reply{};
  pending_reply_ = text_hash(s_.reply);
  if (!parse_reply(s_.reply, reply)) {
    if (seen(s_.failed_replies, s_.failed_reply_count, pending_reply_)) {
      halt("Повтор некорректного вызова. Уточни задачу.");
      return;
    }
    remember(s_.failed_replies, s_.failed_reply_count, pending_reply_);
    std::snprintf(
        s_.feedback, sizeof(s_.feedback),
        "Неверный вызов. Нужны <write>байты HEX</write><run/> или <trace/>.");
    begin_turn();
    return;
  }
  std::snprintf(s_.plan, sizeof(s_.plan), "%s", reply.plan);
  if (reply.question[0]) {
    s_.state = RunState::NEEDS_INPUT;
    std::snprintf(s_.feedback, sizeof(s_.feedback), "%.256s", reply.question);
    phase_ = Phase::IDLE;
    checkpoint();
    return;
  }
  if (reply.write || reply.patch) {
    if (s_.intent == Intent::EXPLAIN) {
      fail("В режиме объяснения замена кода запрещена.");
      return;
    }
    Program candidate{};
    if (!reply_program(s_.program, reply, candidate)) {
      fail("Правка требует текущей программы.");
      return;
    }
    const auto hash = program_fingerprint(candidate);
    if (seen(s_.failed_programs, s_.failed_program_count, hash)) {
      halt("Повтор неудачной программы. Сохранена лучшая версия; уточни "
           "задачу.");
      return;
    }
    if (spec_enabled_ && s_.intent == Intent::FIX && valid_program(s_.program) &&
        hash != program_fingerprint(s_.program)) {
      repair_.reset(new (std::nothrow) RepairRun);
      if (!repair_) {
        fail("Не хватает памяти для проверки правки.");
        return;
      }
      repair_->candidate = candidate;
      test_ = 0;
      trace_count_ = 0;
      phase_ = Phase::TESTS;
      return;
    }
    if (!valid_program(s_.program) || hash != program_fingerprint(s_.program))
      if (!accept_program(store_, s_, candidate.bytes, candidate.size)) {
        fail("Не удалось сохранить новую версию программы.");
        return;
      }
  }
  if (reply.run || reply.trace) {
    if (!valid_program(s_.program)) {
      std::snprintf(s_.feedback, sizeof(s_.feedback),
                    "Сначала запиши программу через <write>байты</write>.");
      begin_turn();
      return;
    }
    const auto fingerprint = program_fingerprint(s_.program);
    if (!reply.write && !reply.patch && reply.run &&
        seen(s_.failed_programs, s_.failed_program_count, fingerprint)) {
      halt("Повтор запуска неудачной программы. Нужна правка кода.");
      return;
    }
    if (reply.trace) {
      const auto action = fingerprint ^ case_stamp(s_) ^ 0x74524345U;
      if (seen(s_.failed_replies, s_.failed_reply_count, action)) {
        halt("Повтор той же трассы без правки кода. Уточни задачу.");
        return;
      }
      remember(s_.failed_replies, s_.failed_reply_count, action);
    }
    test_ = 0;
    trace_count_ = 0;
    if (reply.trace) {
      test_ = s_.test_count;
      for (unsigned i = 0; i < s_.test_count; ++i)
        if (s_.tests[i].public_case) {
          test_ = i;
          break;
        }
      for (unsigned i = 0; i < s_.test_count; ++i)
        if (s_.tests[i].public_case && result_current(s_, i) &&
            !s_.results[i].passed) {
          test_ = i;
          break;
        }
    } else
      invalidate(s_);
    phase_ = reply.trace ? Phase::TRACE : Phase::TESTS;
    checkpoint();
    return;
  }
  if (reply.done || s_.intent == Intent::EXPLAIN) {
    s_.state = RunState::FINISHED;
    phase_ = Phase::IDLE;
    checkpoint();
    return;
  }
  const unsigned n = unsigned(std::strlen(s_.reply));
  if (n && s_.reply[n - 1] == '?') {
    s_.state = RunState::NEEDS_INPUT;
    std::snprintf(s_.feedback, sizeof(s_.feedback), "%.256s", s_.reply);
    phase_ = Phase::IDLE;
    checkpoint();
    return;
  }
  std::snprintf(s_.feedback, sizeof(s_.feedback),
                "Нужны <write>байты HEX</write><run/> или <trace/>.");
  begin_turn();
}
void Agent::finish_tests() {
  if (!append_event(store_, s_, "TOOL", s_.feedback)) {
    fail("Не удалось сохранить результат инструмента.");
    return;
  }
  if (phase_ == Phase::TRACE) {
    if (auto_continue_)
      begin_turn();
    else {
      s_.state = RunState::FINISHED;
      phase_ = Phase::IDLE;
      checkpoint();
    }
    return;
  }
  if (s_.test_count) {
    const unsigned score = passed_examples(s_);
    if (!s_.best_version || score > s_.best_score) {
      s_.best_version = s_.program.version;
      s_.best_score = std::uint8_t(score);
    }
  }
  if (!auto_continue_ || all_passed(s_)) {
    s_.state = RunState::FINISHED;
    phase_ = Phase::IDLE;
    checkpoint();
    return;
  }
  if (!checked_examples(s_) && s_.intent != Intent::EXPLAIN) {
    s_.state = RunState::NEEDS_INPUT;
    phase_ = Phase::IDLE;
    std::snprintf(s_.feedback, sizeof(s_.feedback),
                  "Прогон сохранён. Добавь ожидаемые результаты для проверки.");
    checkpoint();
    return;
  }
  if (spec_enabled_) {
    // The SPEC prompt depends on the condition and angle. A failed example
    // alone would send the exact same prompt and produce the same program.
    s_.state = RunState::NEEDS_INPUT;
    phase_ = Phase::IDLE;
    checkpoint();
    return;
  }
  if (valid_program(s_.program))
    remember(s_.failed_programs, s_.failed_program_count,
             program_fingerprint(s_.program));
  begin_turn();
}
AI_DIRECT_CODE void Agent::record_repair(const Example &example, const Result &result) {
  if (result.status != Execution::STOPPED ||
      (has_expectations(example) && !result.passed)) {
    const char note[] = "Правка отклонена. ";
    std::memcpy(s_.feedback, note, sizeof(note) - 1);
    describe_test(s_.feedback + sizeof(note) - 1,
                  sizeof(s_.feedback) - sizeof(note) + 1, test_, example, result);
    repair_.reset();
    if (!append_event(store_, s_, "TOOL", s_.feedback)) {
      fail("Не удалось сохранить результат проверки правки.");
      return;
    }
    s_.state = RunState::NEEDS_INPUT;
    phase_ = Phase::IDLE;
    checkpoint();
    return;
  }
  repair_->results[test_] = result;
  if (example.public_case)
    repair_->last_public = test_;
  if (++test_ < s_.test_count) return;
  const auto &candidate = repair_->candidate;
  if (!accept_program(store_, s_, candidate.bytes, candidate.size)) {
    fail("Не удалось сохранить проверенную правку.");
    return;
  }
  for (unsigned i = 0; i < s_.test_count; ++i) {
    s_.results[i] = repair_->results[i];
    s_.results[i].version = s_.program.version;
  }
  if (repair_->last_public < s_.test_count) {
    last_result_ = s_.results[repair_->last_public];
    last_angle_ = s_.tests[repair_->last_public].angle;
  }
  repair_.reset();
  std::snprintf(s_.feedback, sizeof(s_.feedback), "PASS");
  auto_continue_ = false;
  finish_tests();
}
AI_DIRECT_CODE bool Agent::tick_prefix(bool (*service)(void *), void *context) {
  const bool save = !restore_prefix_;
  if (save && (!save_prefix_ || prefilled_ != system_tokens_))
    return false;
  const auto status = prefix_io_(prefix_context_, tokens_, system_tokens_,
                                 system_angle_, arithmetic_, save, service, context);
  if (save) {
    save_prefix_ = status == ModelStatus::CANCELLED;
  } else {
    restore_prefix_ = status == ModelStatus::CANCELLED;
    if (status == ModelStatus::OK && model_.position() == system_tokens_) {
      save_prefix_ = false;
      prefilled_ = model_.position();
    } else if (model_.position() != prefilled_) {
      model_.reset();
      prefilled_ = 0;
    }
    metrics_.reused_tokens += prefilled_;
    metrics_.reused_tokens -= reused_prefix_;
    reused_prefix_ = prefilled_;
  }
  if (status == ModelStatus::CANCELLED)
    request_pause();
  return true;
}
void Agent::tick(bool (*service)(void *), void *context) {
  if (!active())
    return;
  struct Timer {
    Metrics &m;
    std::uint32_t (*read)(void *);
    void *raw;
    std::uint32_t start;
    ~Timer() {
      if (read)
        m.max_tick_us = std::max(m.max_tick_us, read(raw) - start);
    }
  } timer{metrics_, micros_, clock_context_,
          micros_ ? micros_(clock_context_) : 0};
  if (pause_) {
    resume_ = phase_;
    phase_ = Phase::IDLE;
    s_.state = RunState::PAUSED;
    checkpoint();
    return;
  }
  struct Pump {
    Agent *self;
    bool (*service)(void *);
    void *context;
  };
  Pump pump{this, service, context};
  auto callback = [](void *p) {
    auto &a = *static_cast<Pump *>(p);
    if (a.service && !a.service(a.context))
      return false;
    return !a.self->pause_;
  };
  if (phase_ == Phase::DIRECT) {
    tick_direct(callback, &pump);
    return;
  }
  auto finish_forward = [&](ModelStatus status, std::uint32_t elapsed, unsigned count) {
    if (phase_ == Phase::PREFILL || phase_ == Phase::HEADER) {
      metrics_.prefill_us += elapsed;
      if (status == ModelStatus::OK)
        metrics_.prefill_tokens += count;
    } else {
      metrics_.decode_us += elapsed;
      if (status == ModelStatus::OK)
        metrics_.decode_tokens += count;
    }
    if (status == ModelStatus::CANCELLED) {
      resume_ = phase_;
      phase_ = Phase::IDLE;
      s_.state = RunState::PAUSED;
      checkpoint();
      return false;
    }
    if (status != ModelStatus::OK) {
      fail(model_status_text(status));
      return false;
    }
    return true;
  };
  auto forwarded = [&](std::uint16_t token, bool output) {
    std::uint16_t candidate = 0;
    auto allowed = [](void *raw, std::uint16_t id) {
      auto &agent = *static_cast<Agent *>(raw);
      if (agent.spec_enabled_) {
        if (!agent.spec_.action()) return id == SpecProtocol::WRITE;
        if (!SpecProtocol::output_token(id)) return false;
        char piece[32]; unsigned n = 0;
        return agent.model_.decode(id,piece,sizeof(piece),n)==ModelStatus::OK &&
               agent.spec_.allows(id,piece);
      }
      if (id == agent.model_.config().eos)
        return agent.grammar_.complete();
      if (id == 0 || id == agent.model_.config().bos)
        return false;
      char piece[2049];
      unsigned n = 0;
      if (agent.model_.decode(id, piece, sizeof(piece), n) != ModelStatus::OK ||
          !n || std::memchr(piece, 0, n))
        return false;
      ToolGrammar next = agent.grammar_;
      const unsigned remaining = agent.generation_limit_ - agent.generated_;
      return remaining && next.accept(piece, n) &&
             next.minimum_tail() <= remaining - 1;
    };
    const auto before = micros_ ? micros_(clock_context_) : 0;
    const auto status =
        model_.forward(token, output, candidate, callback, &pump, arithmetic_,
                       output ? +allowed : nullptr, this);
    const auto elapsed = micros_ ? micros_(clock_context_) - before : 0;
    if (!finish_forward(status, elapsed, 1)) return false;
    next_ = candidate;
    return true;
  };
  if (phase_ == Phase::PREFILL) {
    if ((restore_prefix_ || save_prefix_) && tick_prefix(callback, &pump))
      return;
    if (model_.batch_capacity && model_.batch_step) {
      const unsigned end = save_prefix_ && prefilled_ < system_tokens_
                               ? system_tokens_ : prompt_count_ - 1;
      const unsigned count = std::min(end - prefilled_, model_.batch_capacity(model_.context));
      if (count > 1) {
        const auto before = micros_ ? micros_(clock_context_) : 0;
        const auto status = model_.batch_step(model_.context, tokens_ + prefilled_, count,
                                              arithmetic_, callback, &pump);
        if (finish_forward(status, micros_ ? micros_(clock_context_) - before : 0, count))
          prefilled_ += count;
        return;
      }
    }
    // Preserve the exact snapshot boundary and keep the classifier call
    // for the last input token. Lack of optional SRAM is a scalar fallback.
    if (model_.pair_workspace && model_.pair_step && prefilled_ + 2 < prompt_count_ &&
        !(save_prefix_ && prefilled_ + 1 == system_tokens_)) {
      const auto bytes = model_.pair_workspace(model_.pair_context,arithmetic_);
      if (bytes) {
        std::unique_ptr<float[]> extra(new (std::nothrow) float[bytes / sizeof(float)]);
        if (extra) {
          const std::uint16_t ids[]{tokens_[prefilled_],tokens_[prefilled_+1]};
          const auto before=micros_?micros_(clock_context_):0;
          const auto status=model_.pair_step(model_.pair_context,ids,extra.get(),bytes,arithmetic_,callback,&pump);
          const auto elapsed=micros_?micros_(clock_context_)-before:0;
          if(finish_forward(status,elapsed,2)) {
            prefilled_+=2;
            ++metrics_.prefill_pairs;
          }
          return;
        }
      }
    }
    if (forwarded(tokens_[prefilled_], prefilled_ + 1 == prompt_count_)) {
      if (++prefilled_ == prompt_count_)
        phase_ = Phase::DECODE;
    }
    return;
  }
  if (phase_ == Phase::ADVANCE) {
    if (forwarded(next_, true))
      phase_ = Phase::DECODE;
    return;
  }
  if (phase_ == Phase::HEADER) {
    if (forwarded(SpecProtocol::HEADER[header_at_], header_at_ == 3)) {
      if (++header_at_ == 4) phase_ = Phase::DECODE;
    }
    return;
  }
  if (phase_ == Phase::DECODE) {
    if (spec_enabled_) {
      char piece[32]; unsigned n = 0;
      if (generated_ >= generation_limit_ ||
          model_.decode(next_,piece,sizeof(piece),n) != ModelStatus::OK ||
          !spec_.accept(next_,piece)) {
        fail("Модель не завершила корректную спецификацию программы."); return;
      }
      metrics_.output_token_hash = (metrics_.output_token_hash ^ next_) * 16777619U;
      if (spec_.ended()) {
        Program compiled;
        if (!append_event(store_,s_,"MODEL_SPEC",s_.reply) || !spec_.compile(compiled)) {
          fail("Спецификация модели не помещается в программу МК-61."); return;
        }
        unsigned used=unsigned(std::snprintf(s_.reply,sizeof(s_.reply),"<write>"));
        for(unsigned i=0;i<compiled.size;++i)
          used+=unsigned(std::snprintf(s_.reply+used,sizeof(s_.reply)-used,"%s%02X",i?" ":"",compiled.bytes[i]));
        std::snprintf(s_.reply+used,sizeof(s_.reply)-used,"</write><run/>");
        process_reply(); return;
      }
      ++generated_; ++metrics_.output_tokens;
      if (next_ == SpecProtocol::WRITE && generated_ == 1) {
        header_at_=0; phase_=Phase::HEADER; return;
      }
      const unsigned used=unsigned(std::strlen(s_.reply));
      if(n>=sizeof(s_.reply)-used){fail("Слишком длинная спецификация модели.");return;}
      std::memcpy(s_.reply+used,piece,n+1); phase_=Phase::ADVANCE; return;
    }
    if (next_ == model_.config().eos) {
      if (grammar_.complete())
        process_reply();
      else
        fail("Незавершённый вызов инструмента.");
      return;
    }
    if (generated_ >= generation_limit_) {
      fail("Исчерпан контекст вызова инструмента.");
      return;
    }
    char piece[2049];
    unsigned n = 0;
    const auto status = model_.decode(next_, piece, sizeof(piece), n);
    if (status != ModelStatus::OK) {
      fail(model_status_text(status));
      return;
    }
    const unsigned used = unsigned(std::strlen(s_.reply));
    if (n >= sizeof(s_.reply) - used || std::memchr(piece, 0, n)) {
      fail("Ответ слишком длинный или содержит недопустимые байты.");
      return;
    }
    if (!grammar_.accept(piece, n)) {
      fail("Генератор нарушил грамматику инструментов.");
      return;
    }
    std::memcpy(s_.reply + used, piece, n + 1);
    ++generated_;
    ++metrics_.output_tokens;
    metrics_.output_token_hash = (metrics_.output_token_hash ^ next_) * 16777619U;
    Reply parsed{};
    if (parse_reply(s_.reply, parsed) &&
        (parsed.run || parsed.trace || parsed.done || parsed.question[0])) {
      process_reply();
      return;
    }
    phase_ = Phase::ADVANCE;
    return;
  }
  if (phase_ == Phase::TESTS || phase_ == Phase::TRACE) {
    const bool trace = phase_ == Phase::TRACE;
    const bool staged = bool(repair_);
    const auto version = s_.program.version;
    const Program program = staged ? repair_->candidate : s_.program;
    const auto revision = s_.task_revision;
    Example example = test_ < s_.test_count ? s_.tests[test_] : Example{};
    if (test_ >= s_.test_count)
      example.angle = std::uint8_t(default_angle_);
    if (trace) {
      example.max_commands = std::min(example.max_commands, std::uint16_t(64));
      example.max_frames = std::min(example.max_frames, std::uint16_t(1024));
    }
    const auto tool_start = micros_ ? micros_(clock_context_) : 0;
    const Result result =
        executor_.run
            ? executor_.run(executor_.context, program, example, revision,
                            callback, &pump, trace ? traces_ : nullptr,
                            trace ? &trace_count_ : nullptr)
            : Result{};
    if (micros_)
      metrics_.tool_us += micros_(clock_context_) - tool_start;
    if (staged && !repair_) return;
    if (result.status == Execution::CANCELLED) {
      resume_ = phase_;
      phase_ = Phase::IDLE;
      s_.state = RunState::PAUSED;
      checkpoint();
      return;
    }
    if (s_.program.version != version || s_.task_revision != revision ||
        (staged && (generation_cases_ != case_stamp(s_) ||
                    generation_intent_ != s_.intent)) ||
        (test_ < s_.test_count &&
         s_.tests[test_].revision != example.revision)) {
      phase_ = Phase::IDLE;
      repair_.reset();
      s_.state = RunState::DRAFT;
      std::snprintf(s_.feedback, sizeof(s_.feedback),
                    "Условие изменено. Устаревший результат отброшен.");
      checkpoint();
      return;
    }
    if (staged) {
      record_repair(example, result);
      return;
    }
    last_result_ = result;
    last_angle_ = example.angle;
    if (trace) {
      char record[1025];
      unsigned length = unsigned(std::snprintf(
          record, sizeof(record), "case=%u status=%u commands=%lu\n", test_ + 1,
          unsigned(result.status), (unsigned long)result.commands));
      for (unsigned i = 0; i < trace_count_; ++i) {
        const auto &t = traces_[i];
        const int n = std::snprintf(record + length, sizeof(record) - length,
                                    "%02u %02X X=%.17g\n", unsigned(t.pc),
                                    unsigned(t.opcode), t.x);
        if (n < 0 || unsigned(n) >= sizeof(record) - length) {
          fail("Трасса не помещается в журнал.");
          return;
        }
        length += unsigned(n);
      }
      if (!append_event(store_, s_, "TRACE", record)) {
        fail("Не удалось сохранить трассу.");
        return;
      }
      unsigned used = 0;
      used =
          unsigned(std::snprintf(s_.feedback, sizeof(s_.feedback), "TRACE "));
      for (unsigned i = trace_count_ > 6 ? trace_count_ - 6 : 0;
           i < trace_count_; ++i) {
        const auto &t = traces_[i];
        const int n = std::snprintf(
            s_.feedback + used, sizeof(s_.feedback) - used,
            "%02u:%02X X=%.8g; ", unsigned(t.pc), unsigned(t.opcode), t.x);
        if (n < 0 || unsigned(n) >= sizeof(s_.feedback) - used)
          break;
        used += unsigned(n);
      }
      if (!example.public_case)
        std::snprintf(s_.feedback, sizeof(s_.feedback),
                      "Трасса скрытого примера сохранена в журнале.");
      finish_tests();
      return;
    }
    if (s_.test_count)
      s_.results[test_] = result;
    if (!s_.test_count) {
      std::snprintf(s_.feedback, sizeof(s_.feedback),
                    "RUN X=%.8g; status=%u; ожидаемый ответ не задан", result.x,
                    unsigned(result.status));
      finish_tests();
      return;
    }
    if (!checkpoint())
      return;
    if (++test_ < s_.test_count)
      return;
    if (all_passed(s_))
      std::snprintf(s_.feedback, sizeof(s_.feedback), "PASS");
    else {
      unsigned bad = 0;
      while (bad < s_.test_count && s_.results[bad].passed)
        ++bad;
      const auto &e = s_.tests[bad];
      const auto &r = s_.results[bad];
      describe_test(s_.feedback, sizeof(s_.feedback), bad, e, r);
    }
    finish_tests();
  }
}
} // namespace mk61ai
