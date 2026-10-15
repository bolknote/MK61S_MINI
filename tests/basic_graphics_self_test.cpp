#include "basic_graphics.hpp"
#include <cassert>
#include <cstring>
#include <limits>
#include <cstdio>
#include <initializer_list>
#include <cstdlib>
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
int main() {
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
