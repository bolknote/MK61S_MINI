#ifndef MK61_AI_DIRECT_HPP
#define MK61_AI_DIRECT_HPP
#include "mk61_ai_harness.hpp"

namespace mk61ai {
// A complete arithmetic condition in the same compact SPEC as the model.
// Parsing uses fixed storage. The chosen program and condition have separate
// implementations for ROM emission and numerical checking.
struct DirectTask {
  std::uint8_t body[63]{};
  char literals[16][24]{};
  std::uint16_t registers = 0;
  std::uint8_t size = 0, literal_count = 0, angle = 1;
  bool explicit_angle = false;
  bool compile(Program &) const;
  bool expectation(const Example &input, Example &checked) const;
};

bool parse_direct_task(const char *text, unsigned angle, DirectTask &out);
} // namespace mk61ai
#endif
