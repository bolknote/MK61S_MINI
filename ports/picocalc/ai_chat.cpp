#include "ai_chat.hpp"
#include "canvas.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "ui_font.hpp"
#include "utf8_codec.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>

#if defined(PICO_ON_DEVICE)
#define AI_CHAT_COLD __attribute__((section(".ai_diagnostic_extension"), noinline))
#else
#define AI_CHAT_COLD
#endif

namespace picocalc::ai::chat {
using namespace mk61ai;
namespace {
bool read_unsigned(char *&p, std::uint64_t &value) {
  value = 0;
  if (*p < '0' || *p > '9')
    return false;
  do {
    const unsigned digit = unsigned(*p++ - '0');
    if (value > (UINT64_MAX - digit) / 10)
      return false;
    value = value * 10 + digit;
  } while (*p >= '0' && *p <= '9');
  if (*p != ' ' && *p != '\n')
    return false;
  while (*p == ' ' || *p == '\n')
    ++p;
  return true;
}
} // namespace
void from_utf8(const char *source, char *out, unsigned cap) {
  unsigned n = 0;
  auto p = reinterpret_cast<const std::uint8_t *>(source);
  auto left = std::strlen(source);
  while (left && n + 1 < cap) {
    const auto d = utf8_codec::decode(p, left);
    std::uint8_t ch = '?';
    if (d.valid)
      mk8::from_codepoint(d.codepoint, ch);
    out[n++] = char(ch);
    const unsigned step = d.valid ? d.size : 1;
    p += step;
    left -= step;
  }
  if (cap)
    out[n] = 0;
}
void duration(std::uint64_t ms, char *out, unsigned cap) {
  const auto seconds = ms / 1000;
  std::snprintf(out, cap, "%lu:%02lu", (unsigned long)(seconds / 60),
                (unsigned long)(seconds % 60));
}
Telemetry difference(const Agent::Metrics &n, const Agent::Metrics &b,
                     std::uint64_t ms) {
  return {n.prefill_tokens - b.prefill_tokens,
          n.output_tokens - b.output_tokens,
          n.reused_tokens - b.reused_tokens,
          n.decode_tokens - b.decode_tokens,
          n.prefill_us - b.prefill_us,
          n.decode_us - b.decode_us,
          n.tool_us - b.tool_us,
          ms,
          true};
}
Turn &History::append(const char *value, std::uint32_t event) {
  if (count_ == CAPACITY) {
    for (unsigned i = 1; i < CAPACITY; ++i)
      turns_[i - 1] = turns_[i];
    --count_;
  }
  auto &t = turns_[count_++];
  t = {};
  t.event = event;
  from_utf8(value, t.user, sizeof(t.user));
  return t;
}
bool History::read(Store store, std::uint32_t id, unsigned event) {
  char path[96];
  unsigned n = 0;
  std::snprintf(path, sizeof(path), "/AI/SESSIONS/%08lu-%08lu.TXT",
                (unsigned long)id, (unsigned long)event);
  if (store.size) {
    unsigned size = 0;
    if (store.size(store.context, path, size) && size >= sizeof(record_)) {
      record_[0] = 0;
      return true; // Large PROMPT records are not chat messages.
    }
  }
  if (!store.read ||
      !store.read(store.context, path, record_, sizeof(record_) - 1, n))
    return false;
  if (n >= sizeof(record_))
    return false;
  record_[n] = 0;
  return true;
}
bool History::consume(unsigned event) {
  char *body = std::strchr(record_, '\n');
  if (!body)
    return false;
  *body++ = 0;
  char *after = std::strchr(body, '\n');
  if (!after)
    return false;
  body = after + 1;
  if (!std::strcmp(record_, "USER") || !std::strcmp(record_, "TASK")) {
    append(body, event);
    return true;
  }
  if (!count_)
    return false;
  auto &t = turns_[count_ - 1];
  if (!std::strcmp(record_, "MODEL")) {
    Reply parsed;
    if (parse_reply(body, parsed) && parsed.question[0])
      from_utf8(parsed.question, t.reply, sizeof(t.reply));
    return false;
  }
  if (std::strcmp(record_, "CHAT"))
    return false;
  if (std::strncmp(body, "CHAT1 ", 6))
    return false;
  body += 6;
  std::uint64_t fields[12];
  for (auto &field : fields)
    if (!read_unsigned(body, field))
      return false;
  for (unsigned i = 0; i < 8; ++i)
    if (fields[i] > UINT32_MAX)
      return false;
  if (fields[2] > 2 || fields[3] > unsigned(RunState::ERROR))
    return false;
  // Parse into a candidate: a truncated/corrupt record must never publish a
  // result.
  Turn candidate = t;
  candidate.revision = std::uint32_t(fields[0]);
  candidate.program.version = std::uint32_t(fields[1]);
  candidate.program.task_revision = candidate.revision;
  candidate.angle = unsigned(fields[2]);
  candidate.state = RunState(fields[3]);
  candidate.telemetry = {std::uint32_t(fields[4]),
                         std::uint32_t(fields[5]),
                         std::uint32_t(fields[6]),
                         std::uint32_t(fields[7]),
                         fields[8],
                         fields[9],
                         fields[10],
                         fields[11],
                         true};
  if (std::strncmp(body, "RUN ", 4))
    return false;
  body += 4;
  std::uint64_t status, run[5];
  if (!read_unsigned(body, status) || status > unsigned(Execution::INVALID))
    return false;
  char *end = nullptr;
  const double x = std::strtod(body, &end);
  if (end == body || *end != ' ')
    return false;
  body = end + 1;
  for (auto &field : run)
    if (!read_unsigned(body, field) || field > UINT32_MAX)
      return false;
  if (run[1] > UINT16_MAX)
    return false;
  candidate.result = {};
  candidate.result.x = x;
  candidate.result.status = Execution(status);
  candidate.result.commands = std::uint32_t(run[0]);
  candidate.result.pc = std::uint16_t(run[1]);
  candidate.result.version = std::uint32_t(run[2]);
  candidate.result.task_revision = std::uint32_t(run[3]);
  candidate.result.test_revision = std::uint32_t(run[4]);
  candidate.has_result =
      status != unsigned(Execution::NONE) &&
      status != unsigned(Execution::CANCELLED) &&
      (status != unsigned(Execution::STOPPED) || std::isfinite(x)) &&
      fields[1] == run[2] && fields[0] == run[3];
  if (std::strncmp(body, "HEX ", 4))
    return false;
  body += 4;
  candidate.program.size = 0;
  while (*body && *body != '\n') {
    if (*body == ' ') {
      ++body;
      continue;
    }
    char *end = nullptr;
    const unsigned long op = std::strtoul(body, &end, 16);
    if (end == body || end - body != 2 || op > 255 ||
        candidate.program.size == PROGRAM_SIZE)
      return false;
    candidate.program.bytes[candidate.program.size++] = std::uint8_t(op);
    body = end;
  }
  if (*body == '\n')
    ++body;
  if (std::strncmp(body, "TEXT ", 5))
    return false;
  from_utf8(body + 5, candidate.reply, sizeof(candidate.reply));
  candidate.has_result =
      candidate.has_result && valid_program(candidate.program);
  t = candidate;
  return false;
}
bool History::load(Store store, const Session &s, unsigned end) {
  count_ = 0;
  id_ = s.id;
  seen_ = 0;
  latest_ = end == s.event;
  for (unsigned event = 1; event <= end; ++event) {
    if (!read(store, id_, event))
      return false;
    consume(event);
    seen_ = event;
  }
  return true;
}
bool History::sync(Store store, const Session &s) {
  if (id_ != s.id || seen_ > s.event)
    return load(store, s, s.event);
  if (!latest_)
    return true;
  for (unsigned event = seen_ + 1; event <= s.event; ++event) {
    if (!read(store, s.id, event))
      return false;
    consume(event);
    seen_ = event;
  }
  return true;
}
void History::latest(Store store, const Session &s) {
  (void)load(store, s, s.event);
}
bool History::older(Store store, const Session &s) {
  return has_older() && load(store, s, turns_[0].event - 1);
}
bool History::newer(Store store, const Session &s) {
  unsigned added = 0;
  for (unsigned event = seen_ + 1; event <= s.event; ++event) {
    if (!read(store, s.id, event))
      return false;
    const bool start = !std::strncmp(record_, "USER\n", 5) ||
                       !std::strncmp(record_, "TASK\n", 5);
    if (start && added == CAPACITY)
      break;
    if (consume(event))
      ++added;
    seen_ = event;
  }
  latest_ = seen_ == s.event;
  return true;
}
void History::observe(const Session &s, const Telemetry &m, const Result &r,
                      unsigned angle) {
  if (!latest_)
    return;
  if (!count_ && s.task[0])
    append(s.task, 0);
  if (!count_)
    return;
  auto &t = turns_[count_ - 1];
  t.program = s.program;
  t.revision = s.task_revision;
  t.state = s.state;
  if (m.measured)
    t.telemetry = m;
  if (r.status != Execution::NONE && r.status != Execution::CANCELLED &&
      r.version == s.program.version && r.task_revision == s.task_revision) {
    t.result = r;
    t.has_result = true;
    t.angle = angle;
  } else if (t.result.version != s.program.version ||
             t.result.task_revision != s.task_revision ||
             s.state == RunState::RUNNING)
    t.has_result = false;
  if (s.test_count && t.has_result) {
    bool current = false;
    for (unsigned i = 0; i < s.test_count; ++i)
      current =
          current || (result_current(s, i) &&
                      s.results[i].test_revision == t.result.test_revision);
    t.has_result = current;
  }
  if (s.feedback[0])
    from_utf8(s.feedback, t.reply, sizeof(t.reply));
  else if (s.plan[0])
    from_utf8(s.plan, t.reply, sizeof(t.reply));
}
bool History::save(Store store, Session &s, const Telemetry &m, const Result &r,
                   unsigned angle) {
  // Save the live request even while the user is reading an older page.
  const bool has_result =
      valid_program(s.program) && r.status != Execution::NONE &&
      r.status != Execution::CANCELLED && r.version == s.program.version &&
      r.task_revision == s.task_revision;
  int used = std::snprintf(
      record_, sizeof(record_),
      "CHAT1 %lu %lu %u %u %lu %lu %lu %lu %llu %llu %llu %llu\nRUN %u %.17g "
      "%lu %u %lu %lu %lu\nHEX ",
      (unsigned long)s.task_revision, (unsigned long)s.program.version, angle,
      unsigned(s.state), (unsigned long)m.input, (unsigned long)m.output,
      (unsigned long)m.reused, (unsigned long)m.decode_steps,
      (unsigned long long)m.prefill_us, (unsigned long long)m.decode_us,
      (unsigned long long)m.tool_us, (unsigned long long)m.elapsed_ms,
      has_result ? unsigned(r.status) : unsigned(Execution::NONE),
      has_result ? r.x : 0, (unsigned long)r.commands, unsigned(r.pc),
      (unsigned long)r.version, (unsigned long)r.task_revision,
      (unsigned long)r.test_revision);
  if (used < 0 || unsigned(used) >= sizeof(record_))
    return false;
  for (unsigned i = 0; i < s.program.size; ++i) {
    const int n = std::snprintf(record_ + used, sizeof(record_) - used,
                                "%s%02X", i ? " " : "", s.program.bytes[i]);
    if (n < 0 || unsigned(n) >= sizeof(record_) - unsigned(used))
      return false;
    used += n;
  }
  const int n = std::snprintf(record_ + used, sizeof(record_) - used,
                              "\nTEXT %s", s.feedback[0] ? s.feedback : s.plan);
  if (n < 0 || unsigned(n) >= sizeof(record_) - unsigned(used))
    return false;
  if (!append_event(store, s, "CHAT", record_))
    return false;
  if (latest_)
    seen_ = s.event;
  return true;
}

namespace {
ui_font::Face face(unsigned size) {
  return {ui_font::Family::PIXEL, size == 16   ? ui_font::Size::PX16
                                  : size == 14 ? ui_font::Size::PX14
                                               : ui_font::Size::PX12};
}
constexpr std::uint16_t rgb(unsigned r, unsigned g, unsigned b) {
  return std::uint16_t((r >> 3) << 11 | (g >> 2) << 5 | b >> 3);
}
constexpr std::uint16_t palette[] = {
    rgb(21, 27, 36), rgb(231, 237, 245), rgb(156, 171, 188), rgb(53, 64, 80),
    rgb(36, 47, 61), rgb(35, 52, 80),    rgb(155, 186, 255), rgb(171, 197, 255),
    rgb(23, 36, 51), rgb(255, 170, 170), rgb(145, 216, 183)};
// Two independent 32-bit streams avoid a 64-bit multiply on Cortex-M0+.
// Hash the body separately from the editor: typing must not invalidate GRAM
// reuse. The LCD owns no full color snapshot beyond its current strip.
struct Stamp {
  std::uint32_t a = 2166136261U, b = 0x9e3779b9U;
  void bytes(const void *raw, unsigned size) {
    const auto *p = static_cast<const std::uint8_t *>(raw);
    while (size--) {
      const auto value = *p++;
      a = (a ^ value) * 16777619U;
      b = ((b << 5) | (b >> 27)) ^ (value + 0x9e3779b9U);
    }
  }
  template <typename T> void add(const T &value) { bytes(&value, sizeof(value)); }
  void text(const char *value) { bytes(value, unsigned(std::strlen(value)) + 1); }
  std::uint64_t value() const { return (std::uint64_t(a) << 32) | b; }
};
std::uint64_t body_stamp(const View &v, void (*mnemonic)(std::uint8_t, char *)) {
  Stamp hash;
  hash.add(mnemonic);
  if (v.history) {
    hash.add(v.history->count());
    hash.add(v.history->at_latest());
    hash.add(v.history->has_older());
    for (unsigned i = 0; i < v.history->count(); ++i) {
      const auto &t = (*v.history)[i];
      hash.text(t.user); hash.text(t.reply);
      // Hash values, not structure padding refreshed by History::observe.
      hash.add(t.program.version); hash.add(t.program.size);
      hash.bytes(t.program.bytes, t.program.size);
      const auto &m = t.telemetry;
      hash.add(m.measured); hash.add(m.input); hash.add(m.output);
      hash.add(m.reused); hash.add(m.decode_steps); hash.add(m.elapsed_ms);
      hash.add(m.prefill_us); hash.add(m.decode_us); hash.add(m.tool_us);
      hash.add(t.angle); hash.add(t.state); hash.add(t.has_result);
      if (t.has_result) { hash.add(t.result.status); hash.add(t.result.x); }
    }
  }
  hash.add(v.active); hash.add(v.loading); hash.add(v.paused);
  hash.add(v.expanded_code); hash.add(v.expanded_metrics);
  hash.add(v.load_kb); hash.text(v.phase); hash.text(v.live_reply);
  return hash.value();
}
std::uint64_t fixed_stamp(const View &v) {
  Stamp hash;
  hash.text(v.draft); hash.text(v.notice); hash.add(v.cursor);
  hash.add(v.typing); hash.add(v.russian); hash.add(v.active);
  hash.add(v.history && !v.history->at_latest());
  return hash.value();
}
void move_mono(std::uint8_t *mono, int delta) {
  if (!delta) return;
  const unsigned first = 22 + (delta < 0 ? unsigned(-delta) : 0),
                 last = 272 - (delta > 0 ? unsigned(delta) : 0);
  // canvas::frame is page-major: one byte holds eight vertical pixels.
  // Gather adjacent source pages, preserving fixed/exposed boundary bits.
  for (unsigned step = 0; step < 40; ++step) {
    const unsigned page = delta > 0 ? step : 39 - step, y = page * 8;
    if (y >= last || y + 8 <= first) continue;
    const unsigned lo = std::max(y, first) - y, hi = std::min(y + 8, last) - y;
    const auto mask = std::uint8_t((255U << lo) & (255U >> (8 - hi)));
    const unsigned source = unsigned(int(y) + delta), shift = source & 7;
    const auto *a = mono + (source / 8) * 320;
    const auto *b = source / 8 + 1 < 40 ? a + 320 : nullptr;
    auto *out = mono + page * 320;
    for (unsigned x = 0; x < 320; ++x) {
      const auto value = std::uint8_t((a[x] >> shift) | (shift && b ? b[x] << (8 - shift) : 0));
      out[x] = std::uint8_t((out[x] & ~mask) | (value & mask));
    }
  }
}
} // namespace
unsigned Renderer::measure(const char *value, unsigned size,
                           unsigned scale) const {
  unsigned width = 0;
  for (; *value; ++value)
    width += ui_font::glyph(face(size), mk8::codepoint(std::uint8_t(*value)))
                 .advance *
             scale;
  return width;
}
void Renderer::box(int x, int y, unsigned width, unsigned height, Color color) {
  const int bottom = std::min(clip_bottom_, y + int(height));
  y = std::max(clip_top_, y);
  if (y >= bottom || !width)
    return;
  if (count_ >= (clip_top_ == 22 ? 52U : 64U)) { budget_full_ = true; return; }
  auto &c = commands_[count_++];
  c = {};
  c.x = x;
  c.y = y;
  c.width = width;
  c.height = unsigned(bottom - y);
  c.color = color;
}
void Renderer::text(int x, int y, const char *value, unsigned size, Color color,
                    unsigned scale) {
  if (y + int(ui_font::metrics(face(size)).height * scale) <= clip_top_ ||
      y >= clip_bottom_)
    return;
  if (count_ >= (clip_top_ == 22 ? 52U : 64U)) { budget_full_ = true; return; }
  auto &c = commands_[count_++];
  c = {};
  c.x = x;
  c.y = y;
  c.size = size;
  c.scale = scale;
  c.color = color;
  c.text = true;
  std::snprintf(c.value, sizeof(c.value), "%s", value);
  c.width = unsigned(clip_top_);
  c.height = unsigned(clip_bottom_);
}
int Renderer::flow(int x, int y, const char *value, unsigned size, Color color,
                   unsigned width) {
  while (*value) {
    char line[80];
    unsigned n = 0, gap = 0;
    while (value[n] && value[n] != '\n' && n + 1 < sizeof(line)) {
      line[n] = value[n];
      line[n + 1] = 0;
      if (measure(line, size) > width && n)
        break;
      if (value[n] == ' ')
        gap = n;
      ++n;
    }
    if (!n && *value != '\n')
      n = 1;
    if (value[n] && value[n] != '\n' && gap)
      n = gap;
    std::memcpy(line, value, n);
    line[n] = 0;
    text(x, y, line, size, color);
    y += size == 16 ? 18 : size + 2;
    value += n;
    while (*value == ' ')
      ++value;
    if (*value == '\n')
      ++value;
  }
  return y;
}
AI_CHAT_COLD int Renderer::layout(const View &v, void (*mnemonic)(std::uint8_t, char *)) {
  int y = 28 - int(v.scroll);
  char label[128], time[32];
  const auto *h = v.history;
  if (!h || !h->count()) {
    text(10, y, M8("Напиши, что нужно вычислить"), 16, INK);
    text(10, y + 22, M8("или какую программу составить."), 16, INK);
    text(10, y + 55, M8("Enter отправляет сообщение."), 12, MUTED);
    return 105;
  }
  if (h->has_older()) {
    text(10, y, M8("↑ Ещё сообщения"), 12, MUTED);
    y += 18;
  }
  for (unsigned i = 0; i < h->count(); ++i) {
    const auto &t = (*h)[i];
    const bool current = i + 1 == h->count() && h->at_latest();
    if (i) {
      box(8, y, 302, 1, RULE);
      y += 12;
    }
    text(10, y, M8("Вы"), 12, MUTED);
    y += 15;
    const unsigned before = count_;
    const int top = y;
    y = flow(15, y + 2, t.user, 16, INK, 282) + 8;
    // Background must precede its glyphs in the draw list.
    if (count_ < 52 && y > clip_top_ && top < clip_bottom_) {
      const unsigned after = count_;
      box(8, top - 1, 302, unsigned(y - top + 1), USER);
      if (count_ > after) {
        const auto background = commands_[after];
        for (unsigned j = after; j > before; --j)
          commands_[j] = commands_[j - 1];
        commands_[before] = background;
      }
    }
    y += 10;
    if (current && (v.active || v.loading || v.paused)) {
      text(10, y, v.phase, 14, ACCENT);
      y += 18;
      if (v.loading)
        std::snprintf(label, sizeof(label), M8("Прочитано %u КБ"), v.load_kb);
      else {
        duration(t.telemetry.elapsed_ms, time, sizeof(time));
        std::snprintf(label, sizeof(label),
                      M8("Вход %lu | Выход %lu ток. | %s"),
                      (unsigned long)t.telemetry.input,
                      (unsigned long)t.telemetry.output, time);
      }
      text(10, y, label, 12, MUTED);
      y += 17;
      if (v.live_reply[0]) {
        char raw[385];
        from_utf8(v.live_reply, raw, sizeof(raw));
        y = flow(10, y, raw, 12, MUTED);
      }
      y += 6;
    } else if (t.telemetry.measured) {
      duration(t.telemetry.elapsed_ms, time, sizeof(time));
      std::snprintf(label, sizeof(label), M8("%c %lu токенов | %s"),
                    current && v.expanded_metrics ? 'v' : '>',
                    (unsigned long)t.telemetry.output, time);
      text(10, y, label, 12, MUTED);
      y += 20;
    }
    if (current && v.expanded_metrics && t.telemetry.measured) {
      std::snprintf(label, sizeof(label), M8("Вход %lu | кеш %lu | выход %lu"),
                    (unsigned long)t.telemetry.input,
                    (unsigned long)t.telemetry.reused,
                    (unsigned long)t.telemetry.output);
      text(10, y, label, 12, MUTED);
      y += 15;
      duration(t.telemetry.prefill_us / 1000, time, sizeof(time));
      std::snprintf(label, sizeof(label), M8("Чтение %s"), time);
      text(10, y, label, 12, MUTED);
      y += 15;
      duration(t.telemetry.decode_us / 1000, time, sizeof(time));
      std::snprintf(label, sizeof(label), M8("Генерация %s"), time);
      text(10, y, label, 12, MUTED);
      y += 15;
      if (t.telemetry.decode_steps) {
        std::snprintf(label, sizeof(label), M8("%.2f с/токен"),
                      double(t.telemetry.decode_us) / t.telemetry.decode_steps /
                          1000000.0);
        text(10, y, label, 12, MUTED);
        y += 15;
      }
      std::snprintf(label, sizeof(label), M8("Ядро МК-61 %.1f мс"),
                    double(t.telemetry.tool_us) / 1000.0);
      text(10, y, label, 12, MUTED);
      y += 20;
    }
    if (t.program.size) {
      std::snprintf(label, sizeof(label), M8("Программа v%lu / %u команд"),
                    (unsigned long)t.program.version, unsigned(t.program.size));
      text(10, y, label, 12, MUTED);
      if (current)
        text(270, y, "F1", 12, ACCENT);
      y += 18;
      if (current && v.expanded_code) {
        box(8, y, 302, t.program.size * 16 + 6, WASH);
        for (unsigned at = 0; at < t.program.size; ++at) {
          char name[16];
          mnemonic(t.program.bytes[at], name);
          std::snprintf(label, sizeof(label), "%02u", at);
          text(15, y + 3, label, 12, MUTED);
          text(48, y + 1, name, 14, INK);
          std::snprintf(label, sizeof(label), "%02X", t.program.bytes[at]);
          text(278, y + 3, label, 12, MUTED);
          y += 16;
        }
        y += 11;
      } else {
        label[0] = 0;
        unsigned used = 0;
        for (unsigned at = 0; at < t.program.size; ++at) {
          char name[16];
          mnemonic(t.program.bytes[at], name);
          const auto n = std::strlen(name);
          if (used + n + 5 >= sizeof(label))
            break;
          std::snprintf(label + used, sizeof(label) - used, "%s%s",
                        at ? "  " : "", name);
          if (measure(label, 16) > 280) {
            label[used] = 0;
            std::strcat(label, "...");
            break;
          }
          used = unsigned(std::strlen(label));
        }
        box(8, y, 302, 25, WASH);
        text(15, y + 3, label, 16, INK);
        y += 30;
      }
      if (t.has_result) {
        text(10, y,
             t.angle == 0   ? M8("Режим: градусы (DEG)")
             : t.angle == 2 ? M8("Режим: грады (GRAD)")
                            : M8("Режим: радианы (RAD)"),
             12, MUTED);
        y += 20;
      }
      if (current) {
        const char *labels[] = {M8("F2 В калькулятор"), M8("F3 Править"),
                                M8("F4 Сохранить")};
        int x = 8;
        for (unsigned b = 0; b < 3; ++b) {
          const unsigned w = measure(labels[b], 12) + 12;
          box(x, y, w, 20, b ? WASH : BUTTON);
          text(x + 6, y + 3, labels[b], 12, b ? INK : ON_BUTTON);
          x += int(w) + 6;
        }
        y += 31;
      }
    }
    if (t.has_result) {
      if (t.result.status == Execution::STOPPED) {
        text(10, y, M8("Ответ МК-61"), 12, MUTED);
        y += 16;
        std::snprintf(label, sizeof(label), "%.8g", t.result.x);
        for (char *p = label; *p; ++p)
          if (*p == '.')
            *p = ',';
        text(10, y, label, 16, INK, 2);
        y += 38;
      } else {
        text(10, y,
             t.result.status == Execution::ERROR ? M8("Ошибка МК-61: ЕГГ0Г")
             : t.result.status == Execution::LIMIT
                 ? M8("МК-61: лимит команд")
                 : M8("Ядро МК-61 недоступно"),
             14, DANGER);
        y += 22;
      }
    } else if (!v.active || !current) {
      if (t.reply[0])
        y = flow(10, y, t.reply, 14,
                 t.state == RunState::ERROR ? DANGER : MUTED) +
            8;
      else if (t.state == RunState::FINISHED) {
        y = flow(10, y, M8("Модель не выдала программу. Расчёт не выполнен."),
                 14, DANGER) +
            8;
      } else if (!t.program.size) {
        text(10, y, M8("F5: начать вычисление"), 12, MUTED);
        y += 20;
      }
    }
    y += 13;
  }
  if (!h->at_latest()) {
    text(10, y, M8("↓ Следующие сообщения / F6 к вводу"), 12, ACCENT);
    y += 18;
  }
  return y + int(v.scroll) - 22;
}
AI_CHAT_COLD void Renderer::raster(unsigned top, std::uint8_t *mono, unsigned first,
                      unsigned last) {
  std::memset(stripe_, 0, sizeof(stripe_));
  if (mono) {
    if (first == 0 && last == 320)
      std::memset(mono + top * 40, 0, 8 * 40);
    else
      for (unsigned y = top; y < top + 8; ++y)
        for (unsigned x = first; x < last; ++x)
          canvas::pixel(mono, x, y, false);
  }
  auto pixel = [&](int x, int y, unsigned color) {
    if (x < int(first) || x >= int(last) || y < int(top) || y >= int(top + 8))
      return;
    auto &b = stripe_[(unsigned(y) - top) * 160 + unsigned(x) / 2];
    if (x & 1)
      b = std::uint8_t((b & 0xF0) | color);
    else
      b = std::uint8_t((b & 15) | (color << 4));
    if (mono)
      canvas::pixel(mono, x, y,
                    color != PAPER && color != RULE && color != WASH &&
                        color != USER);
  };
  for (unsigned n = 0; n < count_; ++n) {
    const auto &c = commands_[n];
    if (!c.text) {
      for (int y = std::max(c.y, int(top));
           y < std::min(c.y + int(c.height), int(top + 8)); ++y)
        for (int x = std::max(int(first), c.x); x < std::min(int(last), c.x + int(c.width));
             ++x)
          pixel(x, y, c.color);
      continue;
    }
    int x = c.x;
    const auto f = face(c.size);
    const auto metrics = ui_font::metrics(f);
    for (const char *p = c.value; *p; ++p) {
      const auto g = ui_font::glyph(f, mk8::codepoint(std::uint8_t(*p)));
      const int left = x + g.bearing_x * c.scale,
                y0 = c.y + (metrics.ascent - g.bearing_y) * c.scale;
      if (left < int(last) && left + int(g.width * c.scale) > int(first) &&
          y0 < int(top + 8) && y0 + g.height * c.scale > int(top))
        for (unsigned gy = 0; gy < g.height; ++gy)
          for (unsigned gx = 0; gx < g.width; ++gx)
            if (font_glyph::pixel(g, gx, gy))
              for (unsigned dy = 0; dy < c.scale; ++dy)
                for (unsigned dx = 0; dx < c.scale; ++dx) {
                  const int y = y0 + int(gy * c.scale + dy);
                  if (y >= int(c.width) && y < int(c.height))
                    pixel(left + int(gx * c.scale + dx), y, c.color);
                }
      x += g.advance * c.scale;
    }
  }
}
AI_CHAT_COLD unsigned Renderer::paint(const mk61_app_api &api,
                         const mk61_app_services &services, View &v,
                         void (*mnemonic)(std::uint8_t, char *)) {
  count_ = 0;
  budget_full_ = false;
  clip_top_ = 22;
  clip_bottom_ = 272;
  height_ = unsigned(std::max(0, layout(v, mnemonic)));
  const unsigned maximum = height_ > 250 ? height_ - 250 : 0;
  const unsigned desired = v.follow ? maximum : std::min(v.scroll, maximum);
  if (desired != v.scroll) {
    v.scroll = desired;
    count_ = 0;
    budget_full_ = false;
    layout(v, mnemonic);
  }
  if (maximum) {
    box(317, 22, 2, 250, WASH);
    const unsigned h = std::max(18U, 250 * 250 / height_);
    box(317, 22 + int((250 - h) * v.scroll / maximum), 2, h, MUTED);
  }
  clip_top_ = 0;
  clip_bottom_ = 320;
  box(0, 0, 320, 22, PAPER);
  box(0, 0, 320, 2, ACCENT);
  text(8, 4, "Harness", 14, ACCENT);
  text(67, 6, v.history && !v.history->at_latest() ? M8("История") : "/ MK-61",
       12, MUTED);
  text(254, 6, M8("Tab Меню"), 12, MUTED);
  box(0, 21, 320, 1, RULE);
  box(0, 272, 320, 48, PAPER);
  box(0, 272, 320, 1, RULE);
  char input[80];
  unsigned n = unsigned(std::strlen(v.draft)), cursor = std::min(v.cursor, n),
           start = 0;
  while (start < cursor) {
    const char saved = v.draft[cursor];
    (void)saved;
    const unsigned length = cursor - start;
    if (length >= sizeof(input)) {
      ++start;
      continue;
    }
    std::memcpy(input, v.draft + start, length);
    input[length] = 0;
    if (measure(input, 16) <= 280)
      break;
    ++start;
  }
  std::snprintf(input, sizeof(input), "%s%s", v.typing ? "> " : "",
                v.draft + start);
  while (measure(input, 16) > 294 && input[0])
    input[std::strlen(input) - 1] = 0;
  if (v.typing)
    box(7, 281, 2, 17, ACCENT);
  text(13, 279, input[0] ? input : M8("Напиши сообщение..."), 16,
       input[0] ? INK : MUTED);
  if (v.typing) {
    char prefix[80];
    const unsigned length =
        std::min(cursor - start, unsigned(sizeof(prefix) - 3));
    prefix[0] = '>';
    prefix[1] = ' ';
    std::memcpy(prefix + 2, v.draft + start, length);
    prefix[length + 2] = 0;
    box(13 + int(measure(prefix, 16)), 282, 1, 15, ACCENT);
  }
  const char *hint =
      v.active   ? M8("↑↓ История  Esc Стоп  F6 Ввод")
      : v.typing ? (v.russian ? M8("Enter Отправить  F8 RU/EN  Esc Назад")
                              : M8("Enter Send  F8 EN/RU  Esc Back"))
                 : M8("↑↓ История  F6 Ввод  F5 Решать");
  if (v.notice[0])
    text(8, 306, v.notice, 12, ACCENT);
  else
    text(8, 306, hint, 12, MUTED);
  const bool color = services.call(MK61_SERVICE_COLOR_DISPLAY,
                                   MK61_COLOR_AVAILABLE, 0, 0, nullptr) != 0;
  auto *mono = canvas::frame();
  const auto body = body_stamp(v, mnemonic), fixed = fixed_stamp(v);
  const auto movement = std::int64_t(v.scroll) - previous_scroll_;
  const bool same_body = image_valid_ && !budget_full_ && body == body_stamp_ &&
                         movement > -250 && movement < 250;
  const int delta = same_body ? int(movement) : 0;
  const unsigned offset = same_body ? unsigned((int(gram_offset_) + delta + 250) % 250) : 0;
  const auto call = [&](unsigned operation, unsigned size = 0, void *payload = nullptr) {
    unsigned result;
    do {
      result = services.call(MK61_SERVICE_COLOR_DISPLAY, operation, 0, size, payload);
      if (result == 2) api.service();
    } while (result == 2);
    return result;
  };
  mk61_service_color_scroll scroll{22, 250, std::uint16_t(gram_offset_), std::uint16_t(offset)};
  const unsigned begin = color ? call(MK61_COLOR_SCROLL_BEGIN, sizeof(scroll), &scroll) : 0;
  const bool transaction = begin == 1 || begin == 3;
  bool reuse = transaction && begin == 1 && same_body;
  const auto present = [&](unsigned x, unsigned y, unsigned width, unsigned rows,
                           const std::uint8_t *pixels) {
      mk61_service_color_frame f{};
      f.pixels = pixels;
      f.pixel_bytes = ((width + 1) / 2) * rows;
      f.x = std::uint16_t(x); f.y = std::uint16_t(y);
      f.width = std::uint16_t(width); f.height = std::uint16_t(rows);
      f.format = MK61_COLOR_INDEX4 | MK61_COLOR_PRESERVE_OUTSIDE;
      f.background = palette[PAPER];
      std::copy(std::begin(palette), std::end(palette), f.palette);
      return call(MK61_COLOR_PRESENT, sizeof(f), &f) == 1;
  };
  // One failed strip invalidates reuse. Repaint at the same pending mapping
  // before publishing it; the old scan origin stays in place until END.
  for (unsigned attempt = 0; attempt < 2; ++attempt) {
    const bool fixed_changed = !reuse || fixed != fixed_stamp_;
    if (!reuse) std::memset(mono, 0, canvas::BYTES);
    else move_mono(mono, delta);
    struct Band { unsigned first, last; };
    Band bands[3]; unsigned band_count = 0;
    if (!reuse) bands[band_count++] = {0, 320};
    else {
      if (fixed_changed) bands[band_count++] = {0, 22};
      if (delta) bands[band_count++] = delta > 0 ? Band{272 - unsigned(delta), 272}
                                                               : Band{22, 22 + unsigned(-delta)};
      if (fixed_changed) bands[band_count++] = {272, 320};
    }
    std::uint8_t scrollbar[250];
    const bool redraw_bar = reuse && delta != 0;
    bool ok = true;
    for (unsigned top = 0; top < 320 && ok; top += 8) {
      bool full = false;
      for (unsigned i = 0; i < band_count; ++i)
        full |= top < bands[i].last && top + 8 > bands[i].first;
      if (full) raster(top, mono);
      else if (redraw_bar && top < 272 && top + 8 > 22) raster(top, mono, 317, 319);
      else continue;
      if (redraw_bar)
        for (unsigned y = std::max(top, 22U); y < std::min(top + 8, 272U); ++y) {
          const auto *row = stripe_ + (y - top) * 160;
          scrollbar[y - 22] = std::uint8_t(((row[158] & 15) << 4) | (row[159] >> 4));
        }
      if (color && full)
        for (unsigned i = 0; i < band_count && ok; ++i) {
          const unsigned first = std::max(top, bands[i].first), last = std::min(top + 8, bands[i].last);
          if (first < last) ok = present(0, first, 320, last - first, stripe_ + (first - top) * 160);
        }
    }
    if (ok && color && redraw_bar) ok = present(317, 22, 2, 250, scrollbar);
    if (ok && !color) ok = api.graphics_present(mono, canvas::BYTES) != 0;
    if (ok && transaction) {
      const unsigned end = call(MK61_COLOR_SCROLL_END);
      if (end != 1 && attempt == 0) { reuse = false; continue; }
      ok = end == 1;
    }
    image_valid_ = ok && transaction && !budget_full_;
    if (ok && transaction) {
      body_stamp_ = body; fixed_stamp_ = fixed;
      previous_scroll_ = v.scroll; gram_offset_ = offset;
    }
    if (!ok && transaction) (void)call(MK61_COLOR_END);
    return ok ? height_ : 0;
  }
  image_valid_ = false;
  return 0;
}
} // namespace picocalc::ai::chat
