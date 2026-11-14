#ifndef MK61_PICOCALC_AI_CHAT_HPP
#define MK61_PICOCALC_AI_CHAT_HPP

#include "loadable_app_api.h"
#include "loadable_app_services.h"
#include "mk61_ai_agent.hpp"
#include <cstdint>

namespace picocalc::ai::chat {
struct Telemetry {
  std::uint32_t input = 0, output = 0, reused = 0, decode_steps = 0;
  std::uint64_t prefill_us = 0, decode_us = 0, tool_us = 0, elapsed_ms = 0;
  bool measured = false;
};
struct Turn {
  char user[513]{}, reply[385]{};
  mk61ai::Program program;
  mk61ai::Result result;
  Telemetry telemetry;
  std::uint32_t event = 0, revision = 0;
  unsigned angle = 1;
  mk61ai::RunState state = mk61ai::RunState::DRAFT;
  bool has_result = false;
};
// Old messages remain in the existing SD journal. Only one bounded page is in
// RAM.
class History {
public:
  static constexpr unsigned CAPACITY = 4;
  bool sync(mk61ai::Store store, const mk61ai::Session &session);
  bool older(mk61ai::Store store, const mk61ai::Session &session);
  bool newer(mk61ai::Store store, const mk61ai::Session &session);
  void latest(mk61ai::Store store, const mk61ai::Session &session);
  void observe(const mk61ai::Session &session, const Telemetry &telemetry,
               const mk61ai::Result &result, unsigned angle);
  bool save(mk61ai::Store store, mk61ai::Session &session,
            const Telemetry &telemetry, const mk61ai::Result &result,
            unsigned angle);
  unsigned count() const { return count_; }
  const Turn &operator[](unsigned index) const { return turns_[index]; }
  bool at_latest() const { return latest_; }
  bool has_older() const { return count_ && turns_[0].event > 1; }

private:
  Turn turns_[CAPACITY];
  unsigned count_ = 0;
  std::uint32_t id_ = 0, seen_ = 0;
  bool latest_ = true;
  char record_[1536]{};
  Turn &append(const char *utf8, std::uint32_t event);
  bool consume(unsigned event);
  bool read(mk61ai::Store store, std::uint32_t id, unsigned event);
  bool load(mk61ai::Store store, const mk61ai::Session &session, unsigned end);
};
struct View {
  const History *history = nullptr;
  const char *draft = "", *notice = "", *phase = ""; // M8
  const char *live_reply = ""; // UTF-8, only while generating
  unsigned cursor = 0, scroll = 0, load_kb = 0;
  bool follow = true, typing = false, russian = true, loading = false;
  bool active = false, paused = false, expanded_code = false,
       expanded_metrics = false;
};
class Renderer {
public:
  unsigned paint(const mk61_app_api &api, const mk61_app_services &services,
                 View &view, void (*mnemonic)(std::uint8_t, char *));
  unsigned content_height() const { return height_; }
  void invalidate() { image_valid_ = false; }

private:
  enum Color : std::uint8_t {
    PAPER,
    INK,
    MUTED,
    RULE,
    WASH,
    USER,
    ACCENT,
    BUTTON,
    ON_BUTTON,
    DANGER,
    GOOD
  };
  struct Command {
    int x, y;
    unsigned width, height;
    std::uint8_t color, size, scale;
    bool text;
    char value[80];
  } commands_[64];
  unsigned count_ = 0, height_ = 0;
  std::uint8_t stripe_[320 * 8 / 2]{};
  int clip_top_ = 22, clip_bottom_ = 272;
  std::uint64_t body_stamp_ = 0, fixed_stamp_ = 0;
  unsigned previous_scroll_ = 0, gram_offset_ = 0;
  bool image_valid_ = false, budget_full_ = false;
  unsigned measure(const char *m8, unsigned size, unsigned scale = 1) const;
  void box(int x, int y, unsigned width, unsigned height, Color color);
  void text(int x, int y, const char *m8, unsigned size, Color color,
            unsigned scale = 1);
  int flow(int x, int y, const char *m8, unsigned size, Color color,
           unsigned width = 294);
  int layout(const View &view, void (*mnemonic)(std::uint8_t, char *));
  void raster(unsigned top, std::uint8_t *mono, unsigned first = 0,
              unsigned last = 320);
};
void duration(std::uint64_t milliseconds, char *out, unsigned capacity);
void from_utf8(const char *text, char *out, unsigned capacity);
Telemetry difference(const mk61ai::Agent::Metrics &now,
                     const mk61ai::Agent::Metrics &before,
                     std::uint64_t elapsed_ms);
} // namespace picocalc::ai::chat
#endif
