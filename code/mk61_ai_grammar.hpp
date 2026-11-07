#ifndef MK61_AI_GRAMMAR_HPP
#define MK61_AI_GRAMMAR_HPP
#include <cstdint>
namespace mk61ai {
// Byte grammar; tokenizer pieces may split tags, hex pairs, or UTF-8 text.
// minimum_tail() bounds an ASCII completion using byte tokens, so a valid
// tool call can always finish within the remaining model context.
class ToolGrammar {
public:
  void reset(bool program, bool explain, bool compact = true,
             bool plan = true) {
    *this = ToolGrammar{};
    program_ = program;
    explain_ = explain;
    compact_ = compact;
    planned_ = !plan;
  }
  bool accept(const char *bytes, unsigned size);
  unsigned minimum_tail() const;
  bool complete() const { return state_ == DONE; }

private:
  enum State : std::uint8_t { START, TAG, TEXT, CLOSE, HEX, PATCH, DONE };
  State state_ = START;
  bool program_ = false, explain_ = false, planned_ = false, run_only_ = false;
  unsigned tag_mask_ = 0, at_ = 0, tag_ = 0, text_ = 0, count_ = 0,
           address_ = 0, patch_phase_ = 0, range_ = 0;
  unsigned utf8_left_ = 0, codepoint_ = 0, minimum_cp_ = 0;
  bool nibble_ = false, compact_ = true, last_space_ = false;
  std::uint8_t written_[14]{};
  bool byte(unsigned char c);
  unsigned tag_tail(unsigned tag) const;
};
} // namespace mk61ai
#endif
