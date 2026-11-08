#ifndef MK61_AI_SPEC_HPP
#define MK61_AI_SPEC_HPP
#include "mk61_ai_harness.hpp"

namespace mk61ai {
// Frozen SPEC wire format used by the validated 3M Q4 profiles. The neural
// model chooses every operation, argument and destination. This compiler only
// translates that tree into calculator instructions; it never evaluates it.
class SpecProtocol {
public:
  bool prompt(const char *task, unsigned angle, char *out, unsigned capacity);
  bool allows(std::uint16_t token, const char *piece) const;
  bool accept(std::uint16_t token, const char *piece);
  bool compile(Program &program) const;
  void reset() {
    size_ = digits_ = half_ = 0;
    action_ = ended_ = false;
  }
  bool action() const { return action_; }
  bool ended() const { return ended_; }
  unsigned constants() const { return count_; }
  const char *constant(unsigned i) const { return i < count_ ? pool_[i] : ""; }
  static constexpr std::uint16_t WRITE = 8192, END = 30;
  static constexpr std::uint16_t HEADER[4] = {89, 84, 7804, 32};

private:
  char pool_[64][24]{};
  unsigned count_ = 0, size_ = 0, digits_ = 0, half_ = 0;
  std::uint8_t body_[96]{};
  bool action_ = false, ended_ = false;
  bool add(const char *value);
  bool collect(const char *task);
  bool expression(unsigned &at, unsigned depth, unsigned &nodes,
                  Program &p) const;
};
} // namespace mk61ai
#endif
