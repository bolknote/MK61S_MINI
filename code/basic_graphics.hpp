#ifndef MK61_BASIC_GRAPHICS_HPP
#define MK61_BASIC_GRAPHICS_HPP
#include "basic_graphics_protocol.hpp"
#include <stddef.h>

namespace basic_graphics {
struct Backend {
  void *context;
  void (*geometry)(void *, uint16_t &, uint16_t &);
  bool (*begin)(void *);
  void (*end)(void *);
  bool (*present)(void *, const uint8_t *, size_t);
  bool (*capture)(void *, uint8_t *, size_t, uint8_t, uint8_t);
  const uint8_t *(*glyph)(uint16_t);
  int (*flow)(void *, uint8_t *, size_t, const char *, uint16_t, uint8_t, uint8_t, bool) = nullptr;
  void *(*allocate)(void *, size_t) = nullptr;
  void (*release)(void *, void *) = nullptr;
  // Optional panel-native text painter. Zero retains the historical 5x8 path.
  unsigned (*text)(void *, uint8_t *, uint16_t, uint16_t, double, double,
                   const char *, unsigned) = nullptr;
};

// One foreground session lives outside APP/workspace storage. INPUT may evict
// an executor without invalidating the canvas or borrowing BASIC array cells.
class Session {
public:
  explicit Session(Backend backend) : backend_(backend) {}
  ~Session() { reset(); }
  Session(const Session &) = delete;
  Session &operator=(const Session &) = delete;
  Result apply(Request &request);
  void reset();
  bool active() const { return frame_ != nullptr; }
  const uint8_t *frame() const { return frame_; }
  uint16_t width() const { return width_; }
  uint16_t height() const { return height_; }

private:
  Backend backend_;
  uint8_t *frame_ = nullptr;
  uint16_t width_ = 0, height_ = 0;
  bool dirty_ = false, suspended_ = false;
  struct PrintContext {
    uint16_t mark;
    int16_t x, y;
    uint8_t cursor;
    uint8_t flags;
  };
  PrintContext prints_[33];
  char print_text_[1536];
  uint16_t print_used_ = 0;
  uint8_t print_depth_ = 0;
  Result check() const;
  Result ensure();
  Result show();
  void pixel(int x, int y, uint8_t mode);
  bool point(int x, int y) const;
  void line(double x0, double y0, double x1, double y1, uint8_t mode);
  void box(double x0, double y0, double x1, double y1, uint8_t mode, bool fill);
  void circle(double x, double y, double radius, uint8_t mode);
};

Result dispatch(Request &request);
class RunScope {
public:
  explicit RunScope(bool enabled = true) : enabled_(enabled) {
    if (enabled_) {
      Request r = {};
      r.operation = Operation::RESET;
      dispatch(r);
    }
  }
  ~RunScope() {
    if (enabled_) {
      Request r = {};
      r.operation = Operation::END;
      dispatch(r);
    }
  }

private:
  bool enabled_;
};
} // namespace basic_graphics
#endif
