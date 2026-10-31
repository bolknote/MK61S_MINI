#include "basic_graphics.hpp"
#include <cassert>
#include <cstring>
#include <limits>
#include <cstdio>
#include <initializer_list>
#include <cstdlib>
#include <cmath>
using namespace basic_graphics;
struct Screen {
  uint16_t w = 80, h = 16;
  unsigned begins = 0, ends = 0, presents = 0;
  uint8_t shown[1536] = {};
  static const uint8_t *glyph(uint16_t cp) {
    static const uint8_t a[8] = {14, 17, 17, 31, 17, 17, 17, 0}, blank[8] = {};
    return cp == ' ' ? blank : a;
  }
  Backend backend() {
    return {this,
            [](void *p, uint16_t &w, uint16_t &h) {
              auto &s = *(Screen *)p;
              w = s.w;
              h = s.h;
            },
            [](void *p) {
              ++((Screen *)p)->begins;
              return true;
            },
            [](void *p) { ++((Screen *)p)->ends; },
            [](void *p, const uint8_t *data, size_t size) {
              auto &s = *(Screen *)p;
              ++s.presents;
              memcpy(s.shown, data, size);
              return true;
            },
            [](void *, uint8_t *, size_t, uint8_t, uint8_t) { return true; },
            glyph,
            nullptr,
            [](void *, size_t size) -> void * { return std::malloc(size); },
            [](void *, void *pointer) { std::free(pointer); }};
  }
};
static Request request(Operation op, std::initializer_list<double> values = {}) {
  Request r = {};
  r.operation = op;
  for (double value : values)
    r.args[r.count++] = value;
  return r;
}
static void run(Session &s, Operation op, std::initializer_list<double> values = {}) {
  auto r = request(op, values);
  assert(s.apply(r) == Result::OK);
}
static bool pixel(Session &s, double x, double y) {
  auto r = request(Operation::POINT, {x, y});
  assert(s.apply(r) == Result::OK);
  return r.value != 0;
}
static void box_clipping_oracle() {
  Screen screen;
  Session canvas(screen.backend());
  const double edge[] = {
      -std::numeric_limits<double>::max(), -1e100, -80.5, -16.5,
      -1.51, -1.5, -.51, -.5, -.49, 0, .49, .5, 1.49, 1.5,
      14.49, 14.5, 15.49, 15.5, 16.5, 78.5, 79.49, 79.5, 80.5,
      1e100, std::numeric_limits<double>::max()};
  uint32_t random = 0x61F401U;
  const auto rounded = [](double v) {
    return v < 0 ? -std::floor(-v + .5) : std::floor(v + .5);
  };
  for (unsigned sample = 0; sample < 2048; ++sample) {
    double coordinates[4];
    for (double &v : coordinates) {
      random = random * 1664525U + 1013904223U;
      v = edge[random % (sizeof(edge) / sizeof(*edge))];
    }
    // The oracle tests the original geometric predicate at every pixel. It
    // does not clip or convert any coordinate to an integer.
    const double x0 = rounded(coordinates[0]), y0 = rounded(coordinates[1]);
    const double x1 = rounded(coordinates[2]), y1 = rounded(coordinates[3]);
    const double left = x0 < x1 ? x0 : x1, right = x0 < x1 ? x1 : x0;
    const double top = y0 < y1 ? y0 : y1, bottom = y0 < y1 ? y1 : y0;
    for (unsigned fill = 0; fill < 2; ++fill)
      for (unsigned mode = 0; mode < 3; ++mode) {
        run(canvas, Operation::CLEAR);
        if (mode == 0)
          run(canvas, Operation::BOX, {0, 0, 79, 15, 1, 1});
        run(canvas, Operation::BOX,
            {coordinates[0], coordinates[1], coordinates[2], coordinates[3],
             (double)mode, (double)fill});
        uint8_t expected[160] = {};
        for (int y = 0; y < 16; ++y)
          for (int x = 0; x < 80; ++x) {
            const bool covered = x >= left && x <= right && y >= top && y <= bottom &&
                (fill || x == left || x == right || y == top || y == bottom);
            if (mode == 0 ? !covered : covered)
              expected[(y >> 3) * 80 + x] |= (uint8_t)(1U << (y & 7));
          }
        assert(std::memcmp(canvas.frame(), expected, sizeof(expected)) == 0);
      }
  }
}
static void text_clipping_oracle() {
  Screen screen;
  Session canvas(screen.backend());
  const double edge[] = {-std::numeric_limits<double>::max(), -1e100,
      -97, -96, -17, -9, -8, -7.5, -7, -6, -5.5, -1.5, -.5, 0, .5,
      7.5, 8, 14.5, 15, 15.5, 16, 74, 79, 79.5, 80, 1e100,
      std::numeric_limits<double>::max()};
  const char text[] = "A AAAAAAAAAAAAAA";
  const auto rounded = [](double v) {
    return v < 0 ? -std::floor(-v + .5) : std::floor(v + .5);
  };
  for (double x : edge)
    for (double y : edge)
      for (unsigned length : {0U, 1U, 3U, 16U}) {
        run(canvas, Operation::BOX, {0, 0, 79, 15, 1, 1});
        auto r = request(Operation::TEXT, {x, y});
        r.text = text;
        r.length = (uint16_t)length;
        assert(canvas.apply(r) == Result::OK);
        uint8_t expected[160];
        std::memset(expected, 255, sizeof(expected));
        double left = rounded(x);
        const double top = rounded(y);
        if (top > -8 && top < 16 && left < 80)
          for (unsigned i = 0; i < length && left < 80; ++i, left += 6) {
            if (left <= -6) continue;
            const uint8_t* glyph = Screen::glyph((uint8_t)text[i]);
            for (int row = 0; row < 8; ++row)
              for (int col = 0; col < 6; ++col) {
                const int px = (int)left + col, py = (int)top + row;
                if (px < 0 || px >= 80 || py < 0 || py >= 16) continue;
                const auto mask = (uint8_t)(1U << (py & 7));
                if (col < 5 && (glyph[row] & (1U << (4 - col))))
                  expected[(py >> 3) * 80 + px] |= mask;
                else expected[(py >> 3) * 80 + px] &= (uint8_t)~mask;
              }
          }
        assert(std::memcmp(canvas.frame(), expected, sizeof(expected)) == 0);
      }
}
int main() {
  box_clipping_oracle();
  text_clipping_oracle();
  {
    Screen panel;
    auto backend=panel.backend();
    backend.text=[](void*,uint8_t* frame,uint16_t width,uint16_t height,double x,double y,const char*,unsigned) -> unsigned {
      assert(width==80 && height==16 && x==2 && y==2);
      frame[width+7]^=4;return 12;
    };
    Session native(backend);run(native,Operation::PSET,{0,0});
    run(native,Operation::CLEAR);run(native,Operation::SHOW);
    assert(panel.presents==1 && !pixel(native,7,10));
    auto text=request(Operation::TEXT,{2,2});text.text="A";text.length=1;
    assert(native.apply(text)==Result::OK && text.value==12 && pixel(native,7,10));
    run(native,Operation::SHOW);assert(panel.presents==2);
    assert(native.apply(text)==Result::OK && !pixel(native,7,10));
    run(native,Operation::SHOW);assert(panel.presents==3);
  }
  Screen screen;
  Session s(screen.backend());
  assert(!pixel(s, 0, 0) && !s.active());
  run(s, Operation::PSET, {.5, .5});
  assert(pixel(s, 1, 1));
  run(s, Operation::PSET, {-.5, 0});
  assert(!pixel(s, 0, 0));
  run(s, Operation::PSET, {1e200, -1e200});
  assert(!screen.presents);
  run(s, Operation::SHOW);
  assert(screen.presents == 1);
  run(s, Operation::SHOW);
  assert(screen.presents == 1);
  run(s, Operation::CLEAR);
  run(s, Operation::LINE, {-100, 7, 200, 7});
  for (unsigned x = 0; x < 80; ++x)
    assert(pixel(s, x, 7));
  run(s, Operation::CLEAR);
  run(s, Operation::BOX, {1, 1, 4, 4, 2});
  assert(pixel(s, 1, 1) && pixel(s, 4, 4) && !pixel(s, 2, 2));
  run(s, Operation::BOX, {4, 4, 1, 1, 2});
  for (unsigned y = 0; y < 16; ++y)
    for (unsigned x = 0; x < 80; ++x)
      assert(!pixel(s, x, y));
  run(s, Operation::CIRCLE, {8, 8, 1, 2});
  assert(pixel(s, 8, 7) && pixel(s, 8, 9) && pixel(s, 7, 8) && pixel(s, 9, 8));
  run(s, Operation::CIRCLE, {8, 8, 1, 2});
  assert(!pixel(s, 8, 7));
  run(s, Operation::CIRCLE, {8, 8, 0, 2});
  assert(pixel(s, 8, 8));
  run(s, Operation::CIRCLE, {8, 8, 0, 2});
  assert(!pixel(s, 8, 8));
  run(s, Operation::BOX, {0, 0, 79, 15, 1, 1});
  auto text = request(Operation::TEXT, {2, 2});
  text.text = "A ";
  text.length = 2;
  assert(s.apply(text) == Result::OK);
  assert(pixel(s, 3, 2) && !pixel(s, 2, 2) && !pixel(s, 8, 2));
  assert(pixel(s, 79, 15));
  text.text = "  ";
  assert(s.apply(text) == Result::OK);
  assert(!pixel(s, 3, 2));
  run(s, Operation::SUSPEND);
  assert(screen.ends == 1);
  run(s, Operation::RESUME);
  assert(screen.begins == 2 && screen.presents == 3);
  screen.w = 192;
  auto changed = request(Operation::SHOW);
  assert(s.apply(changed) == Result::CHANGED);
  s.reset();
  assert(!s.active());
  auto invalid = request(Operation::PSET, {0, 0, 1.5});
  assert(s.apply(invalid) == Result::ARGUMENT && !s.active());
  invalid = request(Operation::CIRCLE, {0, 0, -1});
  assert(s.apply(invalid) == Result::ARGUMENT);
  run(s, Operation::CLEAR);
  uint32_t seed = 42;
  for (unsigned i = 0; i < 2000; ++i) {
    const auto random = [&]() {
      seed = seed * 1664525U + 1013904223U;
      return (double)(int(seed % 1000) - 500);
    };
    const double x0 = random(), y0 = random(), x1 = random(), y1 = random();
    run(s, Operation::LINE, {x0, y0, x1, y1, 2});
    run(s, Operation::LINE, {x1, y1, x0, y0, 2});
  }
  for (unsigned i = 0; i < (unsigned)s.width() * s.height() / 8; ++i)
    assert(!s.frame()[i]);
  run(s, Operation::LINE, {-1e308, -1e308, 1e308, 1e308});
  assert(pixel(s, 0, 0) && pixel(s, 15, 15));
  invalid = request(Operation::PSET, {std::numeric_limits<double>::infinity(), 0});
  assert(s.apply(invalid) == Result::ARGUMENT);
  s.reset();
  screen.w = screen.h = 0;
  auto absent = request(Operation::WIDTH);
  assert(s.apply(absent) == Result::OK && absent.value == 0);
  absent = request(Operation::PSET, {0, 0});
  assert(s.apply(absent) == Result::UNAVAILABLE && !s.active());
  std::puts("basic_graphics_self_test: ok");
}
