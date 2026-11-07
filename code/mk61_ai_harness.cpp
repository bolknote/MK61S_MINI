#include "mk61_ai_harness.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#include <type_traits>
namespace mk61ai {
namespace {
void (*memory_sample)(void *) = nullptr;
void *memory_context = nullptr;
void sample_memory() {
  if (memory_sample)
    memory_sample(memory_context);
}
unsigned length(const char *s, unsigned cap) {
  unsigned n = 0;
  while (n < cap && s[n])
    ++n;
  return n;
}
bool space(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }
int hex(char c) {
  return c >= '0' && c <= '9'   ? c - '0'
         : c >= 'a' && c <= 'f' ? c - 'a' + 10
         : c >= 'A' && c <= 'F' ? c - 'A' + 10
                                : -1;
}
std::uint32_t checksum(const std::uint8_t *p, unsigned n) {
  std::uint32_t v = ~0U;
  while (n--) {
    v ^= *p++;
    for (unsigned i = 0; i < 8; ++i)
      v = (v >> 1) ^ (0xedb88320U & (0U - (v & 1)));
  }
  return ~v;
}
struct Wire {
  std::uint8_t *out = nullptr;
  const std::uint8_t *in = nullptr;
  unsigned at = 16, size = 0;
  bool ok = true;
  void bytes(void *value, unsigned n) {
    if (at > size || n > size - at) {
      ok = false;
      return;
    }
    if (out)
      std::memcpy(out + at, value, n);
    else if (in)
      std::memcpy(value, in + at, n);
    at += n;
  }
  void bytes(const void *value, unsigned n) {
    if (in) {
      ok = false;
      return;
    }
    if (at > size || n > size - at) {
      ok = false;
      return;
    }
    if (out)
      std::memcpy(out + at, value, n);
    at += n;
  }
  void u8(std::uint8_t &v) { bytes(&v, 1); }
  void u16(std::uint16_t &v) {
    std::uint8_t b[2] = {std::uint8_t(v), std::uint8_t(v >> 8)};
    bytes(b, 2);
    if (in)
      v = std::uint16_t(b[0] | unsigned(b[1]) << 8);
  }
  void u32(std::uint32_t &v) {
    std::uint8_t b[4] = {std::uint8_t(v), std::uint8_t(v >> 8),
                         std::uint8_t(v >> 16), std::uint8_t(v >> 24)};
    bytes(b, 4);
    if (in)
      v = std::uint32_t(b[0]) | (std::uint32_t(b[1]) << 8) |
          (std::uint32_t(b[2]) << 16) | (std::uint32_t(b[3]) << 24);
  }
  void number(double &v) {
    std::uint64_t bits = 0;
    std::memcpy(&bits, &v, 8);
    std::uint32_t lo = std::uint32_t(bits), hi = std::uint32_t(bits >> 32);
    u32(lo);
    u32(hi);
    if (in) {
      bits = lo | (std::uint64_t(hi) << 32);
      std::memcpy(&v, &bits, 8);
    }
  }
  void u8(const std::uint8_t &v) {
    auto copy = v;
    u8(copy);
  }
  void u16(const std::uint16_t &v) {
    auto copy = v;
    u16(copy);
  }
  void u32(const std::uint32_t &v) {
    auto copy = v;
    u32(copy);
  }
  void number(const double &v) {
    auto copy = v;
    number(copy);
  }
  template <unsigned N> void text(char (&s)[N]) {
    std::uint16_t n = std::uint16_t(length(s, N));
    u16(n);
    if (n >= N) {
      ok = false;
      return;
    }
    bytes(s, n);
    if (in)
      s[n] = 0;
  }
  template <unsigned N> void text(const char (&s)[N]) {
    std::uint16_t n = std::uint16_t(length(s, N));
    u16(n);
    if (n >= N) {
      ok = false;
      return;
    }
    bytes(s, n);
  }
};
bool example_valid(const Example &e) {
  if (e.inputs >> INPUT_COUNT || e.angle > 2 || !e.revision ||
      !e.max_commands || e.max_commands > 4096 || !e.max_frames ||
      e.max_frames > 16384 || e.expected_mask >> INPUT_COUNT ||
      e.preserve >> INPUT_COUNT || e.scenario_count > SCENARIO_STEPS ||
      !std::isfinite(e.expected) || !std::isfinite(e.absolute) ||
      !std::isfinite(e.relative) || e.absolute < 0 || e.relative < 0)
    return false;
  for (unsigned i = 0; i < INPUT_COUNT; ++i)
    if ((e.inputs & (1U << i)) && !std::isfinite(e.values[i]))
      return false;
  for (unsigned i = 0; i < INPUT_COUNT; ++i)
    if ((e.expected_mask & (1U << i)) && !std::isfinite(e.expected_values[i]))
      return false;
  for (unsigned i = 0; i < e.scenario_count; ++i) {
    const auto &a = e.scenario[i];
    if ((a.input_index >= INPUT_COUNT && a.input_index != 255) ||
        (a.output_index >= INPUT_COUNT && a.output_index != 255) ||
        !std::isfinite(a.input) || !std::isfinite(a.expected) ||
        !(a.key >> 4) || (a.key >> 4) > 11 || !(a.key & 15) || (a.key & 15) > 9)
      return false;
  }
  return true;
}
template <class S> void fields(Wire &w, S &s, bool v2 = true) {
  w.u32(s.id);
  w.u32(s.task_revision);
  w.u32(s.last_version);
  w.u32(s.event);
  w.u32(s.program.version);
  w.u32(s.program.task_revision);
  w.u16(s.program.size);
  if (s.program.size > PROGRAM_SIZE) {
    w.ok = false;
    return;
  }
  w.bytes(s.program.bytes, s.program.size);
  w.u16(s.attempts);
  w.u16(s.attempt_limit);
  w.u8(s.test_count);
  w.u8(s.view);
  w.u8(s.form_kind);
  w.u8(s.form_index);
  auto intent = std::uint8_t(s.intent), state = std::uint8_t(s.state);
  w.u8(intent);
  w.u8(state);
  if (s.test_count > TEST_COUNT || s.view > 3 || s.form_kind > 6 ||
      s.form_index >= TEST_COUNT || intent > 2 || state > 6 ||
      !s.task_revision || !s.attempt_limit) {
    w.ok = false;
    return;
  }
  if constexpr (!std::is_const<S>::value) {
    s.intent = Intent(intent);
    s.state = RunState(state);
  }
  w.text(s.task);
  w.text(s.draft);
  w.text(s.form);
  w.text(s.reply);
  w.text(s.plan);
  w.text(s.feedback);
  w.text(s.model);
  for (unsigned i = 0; i < s.test_count; ++i) {
    auto &e = s.tests[i];
    w.text(e.name);
    w.u32(e.inputs);
    w.u32(e.revision);
    for (auto &v : e.values)
      w.number(v);
    w.number(e.expected);
    w.number(e.absolute);
    w.number(e.relative);
    w.u16(e.max_commands);
    w.u16(e.max_frames);
    w.u8(e.angle);
    auto expected = std::uint8_t(e.has_expected);
    w.u8(expected);
    if constexpr (!std::is_const<S>::value)
      e.has_expected = expected != 0;
    if (expected > 1 || !example_valid(e)) {
      w.ok = false;
      return;
    }
    auto &r = s.results[i];
    w.u32(r.version);
    w.u32(r.task_revision);
    w.u32(r.test_revision);
    w.u32(r.commands);
    w.number(r.x);
    w.u16(r.pc);
    auto status = std::uint8_t(r.status), passed = std::uint8_t(r.passed);
    w.u8(status);
    w.u8(passed);
    if constexpr (!std::is_const<S>::value) {
      r.status = Execution(status);
      r.passed = passed != 0;
    }
    if (status > unsigned(Execution::INVALID) || passed > 1 ||
        (r.passed && ((!v2 && !e.has_expected) ||
                      r.status != Execution::STOPPED || !std::isfinite(r.x)))) {
      w.ok = false;
      return;
    }
  }
  if (v2) {
    for (unsigned i = 0; i < s.test_count; ++i) {
      auto &e = s.tests[i];
      w.u32(e.expected_mask);
      w.u32(e.preserve);
      for (auto &value : e.expected_values)
        w.number(value);
      w.u8(e.scenario_count);
      auto visible = std::uint8_t(e.public_case);
      w.u8(visible);
      if (e.scenario_count > SCENARIO_STEPS || visible > 1) {
        w.ok = false;
        return;
      }
      if constexpr (!std::is_const<S>::value)
        e.public_case = visible != 0;
      for (unsigned j = 0; j < e.scenario_count; ++j) {
        auto &a = e.scenario[j];
        w.number(a.input);
        w.number(a.expected);
        w.u8(a.input_index);
        w.u8(a.output_index);
        w.u8(a.key);
      }
      auto &r = s.results[i];
      for (auto &value : r.actual)
        w.number(value);
      for (auto &value : r.stage_values)
        w.number(value);
      w.u32(r.mismatch);
      w.u8(r.failed_stage);
      w.u8(r.completed_stages);
      if (!example_valid(e) || r.mismatch >> INPUT_COUNT ||
          r.completed_stages > e.scenario_count ||
          (r.failed_stage > e.scenario_count && r.failed_stage != 255) ||
          (r.passed && !has_expectations(e))) {
        w.ok = false;
        return;
      }
    }
    for (auto &h : s.failed_programs)
      w.u32(h);
    for (auto &h : s.failed_replies)
      w.u32(h);
    w.u32(s.best_version);
    w.u8(s.failed_program_count);
    w.u8(s.failed_reply_count);
    w.u8(s.best_score);
    auto planning = std::uint8_t(s.planning);
    w.u8(planning);
    if (planning > 1)
      w.ok = false;
    if constexpr (!std::is_const<S>::value)
      s.planning = planning != 0;
    if (s.failed_program_count > 8 || s.failed_reply_count > 8 ||
        s.best_score > TEST_COUNT || s.best_version > s.last_version)
      w.ok = false;
  } else if constexpr (!std::is_const<S>::value) {
    for (unsigned i = 0; i < s.test_count; ++i)
      s.results[i].actual[15] = s.results[i].x;
  }
}
void path(char out[96], std::uint32_t id, const char *extension,
          std::uint32_t item = 0) {
  if (item)
    std::snprintf(out, 96, "/AI/SESSIONS/%08lu-%08lu.%s", (unsigned long)id,
                  (unsigned long)item, extension);
  else
    std::snprintf(out, 96, "/AI/SESSIONS/%08lu.%s", (unsigned long)id,
                  extension);
}
bool decode_into(const std::uint8_t *data, unsigned n, Session &s) {
  if (!data || n < 16 || n > SESSION_BYTES ||
      (std::memcmp(data, "M61SES1\0", 8) && std::memcmp(data, "M61SES2\0", 8)))
    return false;
  std::uint32_t size = 0, crc = 0;
  for (unsigned j = 0; j < 4; ++j) {
    size |= std::uint32_t(data[8 + j]) << (8 * j);
    crc |= std::uint32_t(data[12 + j]) << (8 * j);
  }
  if (size != n || crc != checksum(data + 16, n - 16))
    return false;
  s.~Session();
  new (&s) Session;
  sample_memory();
  Wire wire{nullptr, data, 16, n, true};
  fields(wire, s, data[6] == '2');
  if (!wire.ok || wire.at != n)
    return false;
  if (s.state == RunState::RUNNING)
    s.state = RunState::PAUSED;
  return true;
}
bool read_record(Store store, const char *name, Session &s) {
  if (!store.read)
    return false;
  unsigned cap = SESSION_BYTES;
  if (store.size && (!store.size(store.context, name, cap) ||
                     cap > SESSION_BYTES || cap < 16))
    return false;
  std::unique_ptr<std::uint8_t[]> buffer(new (std::nothrow) std::uint8_t[cap]);
  unsigned n = 0;
  sample_memory();
  return buffer && store.read(store.context, name, buffer.get(), cap, n) &&
         decode_into(buffer.get(), n, s);
}
bool write_record(Store store, const char *name, const Session &s) {
  if (!store.write)
    return false;
  const unsigned n = encode_session(s, nullptr, SESSION_BYTES);
  if (!n)
    return false;
  std::unique_ptr<std::uint8_t[]> buffer(new (std::nothrow) std::uint8_t[n]);
  sample_memory();
  return buffer && encode_session(s, buffer.get(), n) == n &&
         store.write(store.context, name, buffer.get(), n);
}
} // namespace
void allocation_observer(void (*sample)(void *), void *context) {
  memory_sample = sample;
  memory_context = context;
}
bool parse_reply(const char *text, Reply &reply) {
  if (!text)
    return false;
  Reply next{};
  bool planned = false, asked = false;
  const char *p = text;
  while (*p) {
    if (*p != '<') {
      ++p;
      continue;
    }
    if (!std::strncmp(p, "<plan>", 6) || !std::strncmp(p, "<ask>", 5)) {
      const bool ask = p[1] == 'a';
      const unsigned skip = ask ? 5 : 6;
      const char *end = std::strstr(p + skip, ask ? "</ask>" : "</plan>");
      if (!end || (ask ? asked : planned))
        return false;
      const unsigned n = unsigned(end - (p + skip));
      if (n >= (ask ? sizeof(next.question) : sizeof(next.plan)))
        return false;
      std::memcpy(ask ? next.question : next.plan, p + skip, n);
      if (ask)
        asked = true;
      else
        planned = true;
      p = end + (ask ? 6 : 7);
    } else if (!std::strncmp(p, "<write>", 7)) {
      if (next.write || next.patch)
        return false;
      next.write = true;
      p += 7;
      while (*p && std::strncmp(p, "</write>", 8)) {
        while (space(*p))
          ++p;
        if (!std::strncmp(p, "</write>", 8))
          break;
        if (hex(p[0]) < 0 || !p[1] || hex(p[1]) < 0 ||
            next.size == PROGRAM_SIZE)
          return false;
        next.program[next.size++] = std::uint8_t(hex(p[0]) * 16 + hex(p[1]));
        p += 2;
        if (!space(*p) && hex(*p) < 0 && std::strncmp(p, "</write>", 8))
          return false;
      }
      if (!next.size || std::strncmp(p, "</write>", 8))
        return false;
      p += 8;
    } else if (!std::strncmp(p, "<patch>", 7)) {
      if (next.write || next.patch)
        return false;
      next.patch = true;
      p += 7;
      unsigned edits = 0;
      while (*p && std::strncmp(p, "</patch>", 8)) {
        while (space(*p) || *p == ';')
          ++p;
        if (!std::strncmp(p, "</patch>", 8))
          break;
        if (hex(p[0]) < 0 || !p[1] || hex(p[1]) < 0)
          return false;
        unsigned at = unsigned(hex(p[0]) * 16 + hex(p[1]));
        p += 2;
        while (space(*p))
          ++p;
        if (*p++ != ':' || at >= PROGRAM_SIZE)
          return false;
        unsigned count = 0;
        while (*p && *p != ';' && std::strncmp(p, "</patch>", 8)) {
          while (space(*p))
            ++p;
          if (*p == ';' || !std::strncmp(p, "</patch>", 8))
            break;
          if (hex(p[0]) < 0 || !p[1] || hex(p[1]) < 0 || at >= PROGRAM_SIZE ||
              (next.patch_mask[at / 8] & (1U << (at % 8))))
            return false;
          next.program[at] = std::uint8_t(hex(p[0]) * 16 + hex(p[1]));
          next.patch_mask[at / 8] |= std::uint8_t(1U << (at % 8));
          ++at;
          ++count;
          ++edits;
          p += 2;
        }
        if (!count)
          return false;
      }
      if (!edits || std::strncmp(p, "</patch>", 8))
        return false;
      p += 8;
    } else if (!std::strncmp(p, "<run/>", 6)) {
      if (next.run)
        return false;
      next.run = true;
      p += 6;
    } else if (!std::strncmp(p, "<trace/>", 8)) {
      if (next.trace)
        return false;
      next.trace = true;
      p += 8;
    } else if (!std::strncmp(p, "<done/>", 7)) {
      if (next.done)
        return false;
      next.done = true;
      p += 7;
    } else
      return false;
  }
  if (((next.write || next.patch) && !next.run) ||
      (next.trace && (next.run || next.write || next.patch)) ||
      (asked && (next.run || next.write || next.patch || next.trace)))
    return false;
  reply = next;
  return true;
}
bool valid_program(const Program &p) {
  return p.size > 0 && p.size <= PROGRAM_SIZE;
}
bool reply_program(const Program &current, const Reply &reply, Program &out) {
  if (reply.write) {
    out = {};
    out.size = std::uint16_t(reply.size);
    std::memcpy(out.bytes, reply.program, reply.size);
    return valid_program(out);
  }
  if (!reply.patch || !valid_program(current))
    return false;
  Program next = current;
  for (unsigned i = next.size; i < PROGRAM_SIZE; ++i)
    next.bytes[i] = 0x50;
  for (unsigned i = 0; i < PROGRAM_SIZE; ++i)
    if (reply.patch_mask[i / 8] & (1U << (i % 8))) {
      next.bytes[i] = reply.program[i];
      next.size = std::uint16_t(std::max<unsigned>(next.size, i + 1));
    }
  out = next;
  return true;
}
unsigned program_text_size(const Program &p) {
  unsigned n = p.size;
  while (n > 1 && p.bytes[n - 1] == 0x50 && p.bytes[n - 2] == 0x50)
    --n;
  return n;
}
std::uint32_t program_fingerprint(const Program &p) {
  std::uint8_t bytes[PROGRAM_SIZE];
  std::memset(bytes, 0x50, sizeof(bytes));
  std::memcpy(bytes, p.bytes, std::min<unsigned>(p.size, PROGRAM_SIZE));
  return checksum(bytes, sizeof(bytes));
}
std::uint32_t expectation_mask(const Example &e) {
  return e.expected_mask | (e.has_expected ? X_MASK : 0U);
}
double expected_value(const Example &e, unsigned i) {
  return i == 15 && e.has_expected ? e.expected : e.expected_values[i];
}
bool has_expectations(const Example &e) {
  if (expectation_mask(e) || e.preserve)
    return true;
  for (unsigned i = 0; i < e.scenario_count; ++i)
    if (e.scenario[i].output_index != 255)
      return true;
  return false;
}
void reset_attempt_history(Session &s) {
  std::memset(s.failed_programs, 0, sizeof(s.failed_programs));
  std::memset(s.failed_replies, 0, sizeof(s.failed_replies));
  s.failed_program_count = s.failed_reply_count = s.best_score = 0;
  s.best_version = 0;
}
bool result_current(const Session &s, unsigned i) {
  return i < s.test_count && s.results[i].version == s.program.version &&
         s.results[i].task_revision == s.task_revision &&
         s.results[i].test_revision == s.tests[i].revision &&
         s.results[i].status != Execution::NONE;
}
unsigned passed_examples(const Session &s) {
  unsigned n = 0;
  for (unsigned i = 0; i < s.test_count; ++i)
    n += result_current(s, i) && s.results[i].passed;
  return n;
}
bool all_passed(const Session &s) {
  return s.test_count && passed_examples(s) == s.test_count;
}
void invalidate(Session &s) {
  for (auto &r : s.results)
    r = {};
}
bool set_task(Session &s, const char *text, bool append) {
  if (!text)
    return false;
  const unsigned n = length(text, sizeof(s.task)),
                 old = append ? length(s.task, sizeof(s.task)) : 0;
  if (!n || n >= sizeof(s.task) || old + n + (old ? 1 : 0) >= sizeof(s.task))
    return false;
  if (old)
    s.task[old] = '\n';
  std::memcpy(s.task + old + (old ? 1 : 0), text, n + 1);
  ++s.task_revision;
  s.attempts = 0;
  s.state = RunState::DRAFT;
  s.reply[0] = s.plan[0] = s.feedback[0] = 0;
  invalidate(s);
  reset_attempt_history(s);
  return true;
}
bool set_example(Session &s, unsigned i, const Example &e) {
  if (i > s.test_count || i >= TEST_COUNT || !example_valid(e))
    return false;
  Example next = e;
  next.name[sizeof(next.name) - 1] = 0;
  next.revision = i < s.test_count ? s.tests[i].revision + 1 : 1;
  s.tests[i] = next;
  s.results[i] = {};
  if (i == s.test_count)
    ++s.test_count;
  reset_attempt_history(s);
  return true;
}
namespace {
int reference_index(const char *key) {
  const unsigned n = unsigned(std::strlen(key));
  if (n == 2 && key[0] == 'R' && hex(key[1]) >= 0 && hex(key[1]) < 15)
    return hex(key[1]);
  if (n == 1) {
    static constexpr char names[] = "XYZT";
    const char *at = std::strchr(names, key[0]);
    if (at)
      return 15 + int(at - names);
  }
  return -1;
}
void reference_name(unsigned index, char out[4]) {
  if (index < 15)
    std::snprintf(out, 4, "R%X", index);
  else {
    out[0] = "XYZT"[index - 15];
    out[1] = 0;
  }
}
} // namespace
bool parse_example(const char *text, Example &example) {
  if (!text)
    return false;
  Example next{};
  const char *p = text;
  bool expected_side = false, assigned = false;
  unsigned stage = 0;
  std::uint32_t seen_expected = 0;
  while (*p) {
    while (space(*p) || *p == ',' || *p == ';')
      ++p;
    if (!*p)
      break;
    if (*p == '|') {
      if (!expected_side || !assigned || stage == SCENARIO_STEPS)
        return false;
      ++stage;
      next.scenario_count = std::uint8_t(stage);
      expected_side = assigned = false;
      seen_expected = 0;
      ++p;
      continue;
    }
    if (p[0] == '=' && p[1] == '>') {
      if (expected_side)
        return false;
      expected_side = true;
      p += 2;
      continue;
    }
    char key[12]{};
    unsigned n = 0;
    while ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') ||
           (*p >= '0' && *p <= '9')) {
      if (n + 1 == sizeof(key))
        return false;
      key[n++] = *p >= 'a' && *p <= 'z' ? char(*p - 'a' + 'A') : *p;
      ++p;
    }
    while (space(*p))
      ++p;
    if (!n || *p++ != '=')
      return false;
    while (space(*p))
      ++p;
    if (!stage && !std::strcmp(key, "PRESERVE")) {
      do {
        char name[4]{};
        unsigned k = 0;
        while ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') ||
               (*p >= '0' && *p <= '9')) {
          if (k == 3)
            return false;
          name[k++] = *p >= 'a' && *p <= 'z' ? char(*p - 'a' + 'A') : *p;
          ++p;
        }
        const int ref = reference_index(name);
        if (ref < 0 || (next.preserve & (1U << ref)))
          return false;
        next.preserve |= 1U << ref;
        if (*p != ',')
          break;
        ++p;
      } while (*p);
      continue;
    }
    if (!stage && !std::strcmp(key, "ANGLE")) {
      char value[8]{};
      unsigned k = 0;
      while ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z')) {
        if (k + 1 == sizeof(value))
          return false;
        value[k++] = *p >= 'a' ? char(*p - 'a' + 'A') : *p;
        ++p;
      }
      if (!std::strcmp(value, "RAD"))
        next.angle = 1;
      else if (!std::strcmp(value, "DEG"))
        next.angle = 0;
      else if (!std::strcmp(value, "GRAD"))
        next.angle = 2;
      else
        return false;
      continue;
    }
    if (stage && !expected_side && !std::strcmp(key, "KEY")) {
      if (hex(p[0]) < 0 || !p[1] || hex(p[1]) < 0)
        return false;
      next.scenario[stage - 1].key = std::uint8_t(hex(p[0]) * 16 + hex(p[1]));
      p += 2;
      continue;
    }
    const int index = reference_index(key);
    if (expected_side && index >= 0 && *p == '?') {
      if (seen_expected & (1U << index))
        return false;
      seen_expected |= 1U << index;
      ++p;
      assigned = true;
      continue;
    }
    char *end = nullptr;
    const double value = std::strtod(p, &end);
    if (end == p || !std::isfinite(value))
      return false;
    p = end;
    if (!stage) {
      if (!std::strcmp(key, "ATOL")) {
        next.absolute = value;
        continue;
      }
      if (!std::strcmp(key, "RTOL")) {
        next.relative = value;
        continue;
      }
      if (!std::strcmp(key, "PUBLIC")) {
        if (value != 0 && value != 1)
          return false;
        next.public_case = value != 0;
        continue;
      }
      if (!std::strcmp(key, "STEPS") || !std::strcmp(key, "FRAMES")) {
        if (value < 1 || value > 16384 || std::floor(value) != value)
          return false;
        if (key[0] == 'S')
          next.max_commands = std::uint16_t(value);
        else
          next.max_frames = std::uint16_t(value);
        continue;
      }
    }
    if (index < 0)
      return false;
    if (expected_side) {
      if (seen_expected & (1U << index))
        return false;
      seen_expected |= 1U << index;
      assigned = true;
      if (stage) {
        auto &action = next.scenario[stage - 1];
        if (action.output_index != 255)
          return false;
        action.output_index = std::uint8_t(index);
        action.expected = value;
      } else {
        next.expected_mask |= 1U << index;
        next.expected_values[index] = value;
        if (index == 15) {
          next.expected = value;
          next.has_expected = true;
        }
      }
    } else if (stage) {
      auto &action = next.scenario[stage - 1];
      if (action.input_index != 255)
        return false;
      action.input_index = std::uint8_t(index);
      action.input = value;
    } else {
      if (next.inputs & (1U << index))
        return false;
      next.inputs |= 1U << index;
      next.values[index] = value;
    }
  }
  if (expected_side && !assigned)
    return false;
  if (stage && !expected_side)
    return false;
  if (!example_valid(next))
    return false;
  example = next;
  return true;
}
bool format_example(const Example &e, char *out, unsigned cap, bool compact) {
  if (!out || !cap || !example_valid(e))
    return false;
  unsigned used = 0;
  bool ok = true;
  auto add = [&](const char *t) {
    const unsigned n = unsigned(std::strlen(t));
    if (n >= cap - used) {
      ok = false;
      return;
    }
    std::memcpy(out + used, t, n + 1);
    used += n;
  };
  auto value = [&](unsigned i, double v) {
    char key[4], b[48];
    reference_name(i, key);
    std::snprintf(b, sizeof(b), compact ? "%s=%.8g " : "%s=%.17g ", key, v);
    add(b);
  };
  out[0] = 0;
  for (unsigned i = 0; i < INPUT_COUNT; ++i)
    if (e.inputs & (1U << i)) {
      value(i, e.values[i]);
      if (compact && used && (e.inputs >> i) > 1)
        out[used - 1] = ',';
    }
  add("=> ");
  const auto mask = expectation_mask(e);
  if (!mask)
    add("X=? ");
  else
    for (unsigned i = 0; i < INPUT_COUNT; ++i)
      if (mask & (1U << i))
        value(i, expected_value(e, i));
  if (e.preserve) {
    add("PRESERVE=");
    bool first = true;
    for (unsigned i = 0; i < INPUT_COUNT; ++i)
      if (e.preserve & (1U << i)) {
        char key[4];
        reference_name(i, key);
        if (!first)
          add(",");
        add(key);
        first = false;
      }
    add(" ");
  }
  char b[160];
  if (!compact || e.absolute != 0.000002 || e.relative != 0.000002) {
    std::snprintf(b, sizeof(b), "ATOL=%.17g RTOL=%.17g ", e.absolute,
                  e.relative);
    add(b);
  }
  if (!compact || e.angle != 1 || e.max_commands != 256 ||
      e.max_frames != 2048) {
    std::snprintf(b, sizeof(b), "ANGLE=%s STEPS=%u FRAMES=%u ",
                  e.angle == 0   ? "DEG"
                  : e.angle == 2 ? "GRAD"
                                 : "RAD",
                  unsigned(e.max_commands), unsigned(e.max_frames));
    add(b);
  }
  if (!e.public_case)
    add("PUBLIC=0 ");
  for (unsigned j = 0; j < e.scenario_count; ++j) {
    const auto &a = e.scenario[j];
    add("| ");
    if (a.input_index != 255)
      value(a.input_index, a.input);
    if (a.key != 0x29) {
      std::snprintf(b, sizeof(b), "KEY=%02X ", unsigned(a.key));
      add(b);
    }
    add("=> ");
    if (a.output_index == 255)
      add("X=? ");
    else
      value(a.output_index, a.expected);
  }
  return ok;
}
const char *default_prompt_prefix() {
  return "МК-61. <write>HEX</write><run/>; <patch>AA:HEX</patch><run/>. AA — "
         "адрес HEX. <trace/> или <done/>.\n";
}
bool build_prompt(const Session &s, char *out, unsigned cap,
                  const char *prefix) {
  if (!out || !cap)
    return false;
  out[0] = 0;
  unsigned used = 0;
  bool ok = true;
  auto add = [&](const char *t) {
    const unsigned n = unsigned(std::strlen(t));
    if (n >= cap - used) {
      ok = false;
      return;
    }
    std::memcpy(out + used, t, n + 1);
    used += n;
  };
  add(prefix ? prefix : default_prompt_prefix());
  add("Задача: ");
  add(s.task);
  add("\n");
  if (s.intent == Intent::EXPLAIN)
    add("Объясни код, не меняй.\n");
  if (s.program.size) {
    add("Исправь код: ");
    char b[4];
    for (unsigned i = 0; i < program_text_size(s.program); ++i) {
      std::snprintf(b, sizeof(b), "%02X", s.program.bytes[i]);
      add(b);
    }
    add("\n");
  }
  unsigned cases[2]{}, count = 0, failed = TEST_COUNT;
  for (unsigned i = 0; i < s.test_count; ++i)
    if (s.tests[i].public_case && result_current(s, i) &&
        !s.results[i].passed) {
      failed = i;
      break;
    }
  if (failed < TEST_COUNT)
    cases[count++] = failed;
  for (unsigned i = 0; i < s.test_count && count < 2; ++i)
    if (s.tests[i].public_case && i != failed)
      cases[count++] = i;
  if (count) {
    add("Проверки: ");
    for (unsigned j = 0; j < count; ++j) {
      char b[1537];
      if (!format_example(s.tests[cases[j]], b, sizeof(b), true))
        return false;
      if (j)
        add("; ");
      add(b);
    }
    add("\n");
  }
  if (s.feedback[0]) {
    add("Эмулятор: ");
    add(s.feedback);
    add("\n");
  }
  add("Ассистент: ");
  return ok;
}
unsigned encode_session(const Session &s, std::uint8_t *out, unsigned cap) {
  if (cap < 16)
    return 0;
  Wire w{out, nullptr, 16, std::min<unsigned>(cap, SESSION_BYTES), true};
  fields(w, s);
  if (!w.ok)
    return 0;
  if (!out)
    return w.at;
  std::memcpy(out, "M61SES2\0", 8);
  const std::uint32_t size = w.at, crc = checksum(out + 16, size - 16);
  for (unsigned j = 0; j < 4; ++j) {
    out[8 + j] = std::uint8_t(size >> (8 * j));
    out[12 + j] = std::uint8_t(crc >> (8 * j));
  }
  return size;
}
bool decode_session(const std::uint8_t *data, unsigned n, Session &out) {
  std::unique_ptr<Session> next(new (std::nothrow) Session);
  sample_memory();
  if (!next || !decode_into(data, n, *next))
    return false;
  out = *next;
  return true;
}
bool save_session(Store store, const Session &s) {
  char name[96];
  if (s.program.version) {
    path(name, s.id, "AIR", s.program.version);
    if (!write_record(store, name, s))
      return false;
  }
  path(name, s.id, "AIS");
  return write_record(store, name, s);
}
bool load_session(Store store, std::uint32_t id, Session &s) {
  char name[96];
  path(name, id, "AIS");
  std::unique_ptr<Session> next(new (std::nothrow) Session);
  if (!next || !read_record(store, name, *next) || next->id != id)
    return false;
  s = *next;
  return true;
}
bool archive_program(Store store, const Session &s) {
  if (!s.program.version || !valid_program(s.program))
    return false;
  char name[96];
  path(name, s.id, "AIV", s.program.version);
  if (store.exists && store.exists(store.context, name)) {
    std::unique_ptr<Session> previous(new (std::nothrow) Session);
    return previous && read_record(store, name, *previous) &&
           previous->id == s.id &&
           previous->program.version == s.program.version &&
           previous->program.size == s.program.size &&
           !std::memcmp(previous->program.bytes, s.program.bytes,
                        s.program.size);
  }
  return write_record(store, name, s);
}
bool select_program(Store store, Session &s, std::uint32_t version) {
  char name[96];
  path(name, s.id, "AIR", version);
  std::unique_ptr<Session> previous(new (std::nothrow) Session);
  if (!previous)
    return false;
  if (!read_record(store, name, *previous)) {
    path(name, s.id, "AIV", version);
    if (!read_record(store, name, *previous))
      return false;
  }
  if (previous->id != s.id || previous->program.version != version ||
      !valid_program(previous->program))
    return false;
  s.program = previous->program;
  invalidate(s);
  if (previous->task_revision == s.task_revision)
    for (unsigned i = 0; i < s.test_count && i < previous->test_count; ++i)
      if (previous->tests[i].revision == s.tests[i].revision)
        s.results[i] = previous->results[i];
  s.state = RunState::PAUSED;
  return true;
}
bool append_event(Store store, Session &s, const char *type, const char *text) {
  if (!store.write || !type || !text)
    return false;
  char name[96];
  unsigned next = s.event;
  do {
    if (next == 0xffffffffU)
      return false;
    path(name, s.id, "TXT", ++next);
  } while (store.exists && store.exists(store.context, name));
  char record[2304];
  const int n = std::snprintf(
      record, sizeof(record), "%s\ntask=%lu program=%lu\n%s\n", type,
      (unsigned long)s.task_revision, (unsigned long)s.program.version, text);
  if (n < 0 || unsigned(n) >= sizeof(record) ||
      !store.write(store.context, name, record, unsigned(n)))
    return false;
  if (!std::strcmp(type, "TOOL")) {
    path(name, s.id, "AIT", next);
    if (!write_record(store, name, s))
      return false;
  }
  s.event = next;
  return true;
}
bool accept_program(Store store, Session &s, const std::uint8_t *bytes,
                    unsigned n, bool source_import) {
  if (!bytes || !n || n > PROGRAM_SIZE ||
      (s.intent == Intent::EXPLAIN && !source_import))
    return false;
  std::unique_ptr<Session> next(new (std::nothrow) Session(s));
  if (!next)
    return false;
  unsigned version = s.last_version;
  char name[96];
  do {
    if (version == 0xffffffffU)
      return false;
    path(name, s.id, "AIV", ++version);
  } while (store.exists && store.exists(store.context, name));
  next->program = {};
  next->program.version = version;
  next->program.task_revision = s.task_revision;
  next->program.size = std::uint16_t(n);
  std::memcpy(next->program.bytes, bytes, n);
  next->last_version = version;
  invalidate(*next);
  if (!archive_program(store, *next) || !save_session(store, *next))
    return false;
  s = *next;
  return true;
}
bool reserve_session_id(Store store, std::uint32_t floor, std::uint32_t &id) {
  if (!store.read || !store.write || !store.exists)
    return false;
  const char *path = "/AI/NEXT.ID";
  std::uint8_t bytes[16]{};
  std::uint32_t previous = 0;
  if (store.exists(store.context, path)) {
    unsigned n = 0;
    if (!store.read(store.context, path, bytes, sizeof(bytes), n) ||
        n != sizeof(bytes) || std::memcmp(bytes, "M61I", 4))
      return false;
    std::uint32_t crc = 0;
    for (unsigned i = 0; i < 4; ++i) {
      previous |= std::uint32_t(bytes[4 + i]) << (8 * i);
      crc |= std::uint32_t(bytes[12 + i]) << (8 * i);
    }
    if (crc != checksum(bytes, 12))
      return false;
  }
  previous = std::max(previous, floor);
  if (previous == 0xffffffffU)
    return false;
  const auto next = previous + 1;
  std::memcpy(bytes, "M61I", 4);
  for (unsigned i = 0; i < 4; ++i)
    bytes[4 + i] = std::uint8_t(next >> (8 * i));
  const auto crc = checksum(bytes, 12);
  for (unsigned i = 0; i < 4; ++i)
    bytes[12 + i] = std::uint8_t(crc >> (8 * i));
  if (!store.write(store.context, path, bytes, sizeof(bytes)))
    return false;
  id = next;
  return true;
}
} // namespace mk61ai
