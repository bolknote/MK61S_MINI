#include "basic_graphics.hpp"
#include "mk_math.hpp"
#include "mk8_codec.hpp"
#include <stdlib.h>
#include <string.h>

namespace basic_graphics {
namespace {
double rounded(double value) {
  return value < 0 ? -mk_math::floor(-value + .5) : mk_math::floor(value + .5);
}
bool flag(double value, unsigned maximum) {
  return value >= 0 && value <= maximum && value == mk_math::floor(value);
}
unsigned outside(double x, double y, unsigned w, unsigned h) {
  return (x < 0 ? 1U : x > w - 1 ? 2U : 0U) | (y < 0 ? 4U : y > h - 1 ? 8U : 0U);
}
double intersection(double a0, double a1, double b0, double b1, double target) {
  double scale = mk_math::fabs(b0);
  if (mk_math::fabs(b1) > scale)
    scale = mk_math::fabs(b1);
  if (scale < 1)
    scale = 1;
  const double fraction = (target / scale - b0 / scale) / (b1 / scale - b0 / scale);
  return a0 * (1 - fraction) + a1 * fraction;
}
} // namespace
void Session::reset() {
  print_used_ = 0;
  print_depth_ = 0;
  if (frame_) {
    if (!suspended_)
      backend_.end(backend_.context);
    if (backend_.release)
      backend_.release(backend_.context, frame_);
  }
  frame_ = nullptr;
  width_ = height_ = 0;
  dirty_ = suspended_ = false;
}
Result Session::check() const {
  uint16_t w = 0, h = 0;
  backend_.geometry(backend_.context, w, h);
  if (frame_ && (w != width_ || h != height_))
    return Result::CHANGED;
  return w && h ? Result::OK : Result::UNAVAILABLE;
}
Result Session::ensure() {
  const auto result = check();
  if (result != Result::OK || frame_)
    return result;
  uint16_t w = 0, h = 0;
  backend_.geometry(backend_.context, w, h);
  // Bound every loop and allocation independently of a backend's report.
  if (w > 192 || h > 64 || h % 8)
    return Result::UNAVAILABLE;
  if (!backend_.allocate || !backend_.release)
    return Result::FULL;
  const size_t size = (size_t)w * h / 8;
  auto *memory = backend_.allocate ? (uint8_t *)backend_.allocate(backend_.context, size) : nullptr;
  if (!memory)
    return Result::FULL;
  memset(memory, 0, size);
  if (!backend_.begin(backend_.context)) {
    backend_.release(backend_.context, memory);
    return Result::IO;
  }
  if (!backend_.capture(backend_.context, memory, size, 0, 255)) {
    backend_.end(backend_.context);
    backend_.release(backend_.context, memory);
    return Result::IO;
  }
  frame_ = memory;
  width_ = w;
  height_ = h;
  dirty_ = true;
  return Result::OK;
}
Result Session::show() {
  if (!frame_ || suspended_)
    return Result::OK;
  auto result = check();
  if (result != Result::OK)
    return result;
  if (dirty_ && !backend_.present(backend_.context, frame_, (size_t)width_ * height_ / 8))
    return Result::IO;
  dirty_ = false;
  return Result::OK;
}
void Session::pixel(int x, int y, uint8_t mode) {
  if (x < 0 || y < 0 || x >= width_ || y >= height_)
    return;
  auto &cell = frame_[(size_t)(y >> 3) * width_ + x];
  const uint8_t mask = (uint8_t)(1U << (y & 7));
  if (mode == 2)
    cell ^= mask;
  else if (mode)
    cell |= mask;
  else
    cell &= (uint8_t)~mask;
  dirty_ = true;
}
bool Session::point(int x, int y) const {
  return frame_ && x >= 0 && y >= 0 && x < width_ && y < height_ &&
         (frame_[(size_t)(y >> 3) * width_ + x] & (1U << (y & 7)));
}
void Session::line(double x0, double y0, double x1, double y1, uint8_t mode) {
  x0 = rounded(x0);
  y0 = rounded(y0);
  x1 = rounded(x1);
  y1 = rounded(y1);
  if (x0 > x1 || (x0 == x1 && y0 > y1)) {
    double t = x0;
    x0 = x1;
    x1 = t;
    t = y0;
    y0 = y1;
    y1 = t;
  }
  // Clip before integer conversion: even enormous finite coordinates cannot
  // wrap around, address outside the frame, or cause unbounded raster loops.
  for (unsigned iteration = 0; iteration < 8; ++iteration) {
    const unsigned a = outside(x0, y0, width_, height_), b = outside(x1, y1, width_, height_);
    if (a & b)
      return;
    if (!(a | b)) {
      int x = (int)rounded(x0), y = (int)rounded(y0);
      const int end_x = (int)rounded(x1), end_y = (int)rounded(y1);
      const int dx = abs(end_x - x), dy = -abs(end_y - y);
      const int sx = x < end_x ? 1 : -1, sy = y < end_y ? 1 : -1;
      int error = dx + dy;
      for (;;) {
        pixel(x, y, mode);
        if (x == end_x && y == end_y)
          return;
        const int twice = error * 2;
        if (twice >= dy) {
          error += dy;
          x += sx;
        }
        if (twice <= dx) {
          error += dx;
          y += sy;
        }
      }
    }
    const unsigned code = a ? a : b;
    double x, y;
    if (code & 12) {
      y = code & 4 ? 0 : height_ - 1;
      x = intersection(x0, x1, y0, y1, y);
    } else {
      x = code & 1 ? 0 : width_ - 1;
      y = intersection(y0, y1, x0, x1, x);
    }
    if (!mk_math::is_finite(x) || !mk_math::is_finite(y))
      return;
    if (a) {
      x0 = x;
      y0 = y;
    } else {
      x1 = x;
      y1 = y;
    }
  }
}
void Session::box(double x0, double y0, double x1, double y1, uint8_t mode, bool fill) {
  x0 = rounded(x0);
  y0 = rounded(y0);
  x1 = rounded(x1);
  y1 = rounded(y1);
  if (x0 > x1) {
    const double t = x0;
    x0 = x1;
    x1 = t;
  }
  if (y0 > y1) {
    const double t = y0;
    y0 = y1;
    y1 = t;
  }
  for (int y = 0; y < height_; ++y)
    if (y >= y0 && y <= y1)
      for (int x = 0; x < width_; ++x)
        if (x >= x0 && x <= x1 && (fill || x == x0 || x == x1 || y == y0 || y == y1))
          pixel(x, y, mode);
}
void Session::circle(double cx, double cy, double radius, uint8_t mode) {
  cx = rounded(cx);
  cy = rounded(cy);
  radius = rounded(radius);
  if (radius == 0) {
    if (cx >= 0 && cy >= 0 && cx < width_ && cy < height_)
      pixel((int)cx, (int)cy, mode);
    return;
  }
  if (cx + radius < 0 || cy + radius < 0 || cx - radius > width_ - 1 || cy - radius > height_ - 1)
    return;
  if (radius <= 4096 && mk_math::fabs(cx) < 8192 && mk_math::fabs(cy) < 8192) {
    int x = (int)radius, y = 0, error = 1 - x;
    do {
      const int offsets[8][2] = {{x, y},   {y, x},   {-y, x}, {-x, y},
                                 {-x, -y}, {-y, -x}, {y, -x}, {x, -y}};
      for (unsigned i = 0; i < 8; ++i) {
        bool duplicate = false;
        for (unsigned j = 0; j < i; ++j)
          if (offsets[i][0] == offsets[j][0] && offsets[i][1] == offsets[j][1])
            duplicate = true;
        if (!duplicate)
          pixel((int)cx + offsets[i][0], (int)cy + offsets[i][1], mode);
      }
      ++y;
      if (error < 0)
        error += 2 * y + 1;
      else {
        --x;
        error += 2 * (y - x) + 1;
      }
    } while (x >= y);
  } else {
    // A huge clipped circle still takes at most one screen's worth of work.
    const double tolerance = 1 / radius;
    for (int y = 0; y < height_; ++y)
      for (int x = 0; x < width_; ++x) {
        const double dx = (x - cx) / radius, dy = (y - cy) / radius;
        if (mk_math::fabs(dx * dx + dy * dy - 1) <= tolerance)
          pixel(x, y, mode);
      }
  }
}
Result Session::apply(Request &r) {
  if (r.count > 6)
    return Result::ARGUMENT;
  for (unsigned i = 0; i < r.count; ++i)
    if (!mk_math::is_finite(r.args[i]))
      return Result::ARGUMENT;
  if (r.operation == Operation::SAVE_PRINT) {
    if (r.count != 5 || !r.text || r.length >= 96 || !flag(r.args[2], 1) || !flag(r.args[3], 95) ||
        !flag(r.args[4], 1))
      return Result::ARGUMENT;
    if (print_depth_ == 33 || (unsigned)print_used_ + r.length + 1 > sizeof(print_text_))
      return Result::FULL;
    auto *context = &prints_[print_depth_];
    context->mark = print_used_;
    const auto coordinate = [](double value, int low, int high) -> int16_t {
      value = rounded(value);
      return (int16_t)(value < low ? low : value > high ? high : value);
    };
    context->x = coordinate(r.args[0], -576, 192);
    context->y = coordinate(r.args[1], -8, 64);
    context->cursor = (uint8_t)r.args[3];
    context->flags = (uint8_t)((r.args[2] != 0 ? 1 : 0) | (r.args[4] != 0 ? 2 : 0));
    memcpy(print_text_ + print_used_, r.text, r.length);
    print_text_[print_used_ + r.length] = 0;
    print_used_ = (uint16_t)(print_used_ + r.length + 1);
    ++print_depth_;
    return Result::OK;
  }
  if (r.operation == Operation::RESTORE_PRINT) {
    if (!print_depth_ || !r.text || r.length < 96)
      return Result::ARGUMENT;
    auto *context = &prints_[print_depth_ - 1];
    r.value = context->flags & 5 ? 1 : 0;
    if (r.value) {
      const char *saved = print_text_ + context->mark;
      memcpy((char *)r.text, saved, strlen(saved) + 1);
      r.args[0] = context->x;
      r.args[1] = context->y;
      r.args[2] = context->flags & 1 ? 1 : 0;
      r.args[3] = context->cursor;
      r.args[4] = context->flags & 2 ? 1 : 0;
    }
    print_used_ = context->mark;
    --print_depth_;
    return Result::OK;
  }
  if (r.operation == Operation::WIDTH || r.operation == Operation::HEIGHT) {
    const auto valid = check();
    if (frame_ && valid != Result::OK)
      return valid;
    uint16_t w = 0, h = 0;
    backend_.geometry(backend_.context, w, h);
    r.value = r.operation == Operation::WIDTH ? w : h;
    return Result::OK;
  }
  if (r.operation == Operation::RESET || r.operation == Operation::END) {
    reset();
    return Result::OK;
  }
  if (r.operation == Operation::CHECK)
    return frame_ ? check() : Result::OK;
  if (r.operation == Operation::ACTIVE) {
    r.value = frame_ && !suspended_ ? 1 : 0;
    return Result::OK;
  }
  if (r.operation == Operation::SHOW)
    return show();
  if (r.operation == Operation::SUSPEND) {
    if (frame_ && !suspended_) {
      const auto result = show();
      backend_.end(backend_.context);
      suspended_ = true;
      return result;
    }
    return Result::OK;
  }
  if (r.operation == Operation::RESUME) {
    if (!frame_ || !suspended_)
      return Result::OK;
    const auto valid = check();
    if (valid != Result::OK)
      return valid;
    if (!backend_.begin(backend_.context))
      return Result::IO;
    suspended_ = false;
    dirty_ = true;
    return show();
  }
  if (r.operation == Operation::CLEAR) {
    if (frame_) {
      const auto valid = check();
      if (valid != Result::OK)
        return valid;
      memset(frame_, 0, (size_t)width_ * height_ / 8);
      dirty_ = true;
    }
    return Result::OK;
  }
  if (r.operation == Operation::TEXT_ROWS) {
    if (!frame_ || suspended_)
      return Result::OK;
    const auto valid = check();
    if (valid != Result::OK)
      return valid;
    if (r.count != 2 || !flag(r.args[0], 255) || !flag(r.args[1], 255))
      return Result::ARGUMENT;
    if (!backend_.capture(backend_.context, frame_, (size_t)width_ * height_ / 8,
                          (uint8_t)r.args[0], (uint8_t)r.args[1]))
      return Result::IO;
    dirty_ = true;
    return Result::OK;
  }
  if (r.operation == Operation::TEXT_FLOW) {
    r.value = 0;
    if (!frame_ || suspended_)
      return Result::OK;
    const auto valid = check();
    if (valid != Result::OK)
      return valid;
    if (r.count != 3 || !flag(r.args[0], 255) || !flag(r.args[1], 255) || !flag(r.args[2], 1) ||
        !backend_.flow || (!r.text && r.length))
      return Result::ARGUMENT;
    const int count =
        backend_.flow(backend_.context, frame_, (size_t)width_ * height_ / 8, r.text, r.length,
                      (uint8_t)r.args[0], (uint8_t)r.args[1], r.args[2] != 0);
    if (count < 0)
      return Result::IO;
    r.value = count;
    dirty_ = true;
    return Result::OK;
  }
  if (r.count < minimum(r.operation) || r.count > maximum(r.operation))
    return Result::ARGUMENT;
  uint8_t mode = 1;
  const unsigned minimum_args = minimum(r.operation);
  if (r.count > minimum_args) {
    if (!flag(r.args[minimum_args], 2))
      return Result::ARGUMENT;
    mode = (uint8_t)r.args[minimum_args];
  }
  if (r.operation == Operation::BOX && r.count == 6 && !flag(r.args[5], 1))
    return Result::ARGUMENT;
  if (r.operation == Operation::CIRCLE && r.args[2] < 0)
    return Result::ARGUMENT;
  if (r.operation == Operation::POINT) {
    const auto valid = check();
    if (valid != Result::OK)
      return valid;
    const double x = rounded(r.args[0]), y = rounded(r.args[1]);
    r.value = x >= 0 && y >= 0 && x < width_ && y < height_ && point((int)x, (int)y) ? 1 : 0;
    return Result::OK;
  }
  if (r.operation == Operation::TEXT && (!r.text && r.length))
    return Result::ARGUMENT;
  auto valid = ensure();
  if (valid != Result::OK)
    return valid;
  switch (r.operation) {
  case Operation::PSET: {
    const double x = rounded(r.args[0]), y = rounded(r.args[1]);
    if (x >= 0 && y >= 0 && x < width_ && y < height_)
      pixel((int)x, (int)y, mode);
    break;
  }
  case Operation::LINE:
    line(r.args[0], r.args[1], r.args[2], r.args[3], mode);
    break;
  case Operation::BOX:
    box(r.args[0], r.args[1], r.args[2], r.args[3], mode, r.count == 6 && r.args[5] != 0);
    break;
  case Operation::CIRCLE:
    circle(r.args[0], r.args[1], r.args[2], mode);
    break;
  case Operation::TEXT: {
    for (unsigned i = 0; i < print_depth_; ++i)
      prints_[i].flags |= 4;
    double left = rounded(r.args[0]);
    const double top = rounded(r.args[1]);
    if (top <= -8 || top >= height_ || left >= width_)
      break;
    for (unsigned i = 0; i < r.length && left < width_; ++i, left += 6) {
      if (left <= -6)
        continue;
      const auto *glyph = backend_.glyph(mk8::codepoint((uint8_t)r.text[i]));
      if (!glyph)
        glyph = backend_.glyph('?');
      for (int y = 0; y < 8; ++y)
        for (int x = 0; x < 6; ++x)
          pixel((int)left + x, (int)top + y,
                glyph && x < 5 && (glyph[y] & (1U << (4 - x))) ? 1 : 0);
    }
    break;
  }
  default:
    return Result::ARGUMENT;
  }
  return Result::OK;
}
} // namespace basic_graphics
