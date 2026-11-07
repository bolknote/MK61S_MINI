#include "mk61_ai_grammar.hpp"
#include <algorithm>
#include <cstring>
namespace mk61ai {
namespace {
constexpr const char *tags[] = {"<plan>",   "<write>", "<patch>", "<run/>",
                                "<trace/>", "<done/>", "<ask>"};
int hex(unsigned char c) {
  return c >= '0' && c <= '9'   ? c - '0'
         : c >= 'a' && c <= 'f' ? c - 'a' + 10
         : c >= 'A' && c <= 'F' ? c - 'A' + 10
                                : -1;
}
bool space(unsigned char c) {
  return c == ' ' || c == '\n' || c == '\r' || c == '\t';
}
} // namespace
unsigned ToolGrammar::tag_tail(unsigned tag) const {
  switch (tag) {
  case 0:
    return 14;
  case 1:
    return 16;
  case 2:
    return 19;
  case 6:
    return 7;
  default:
    return 0;
  }
}
bool ToolGrammar::byte(unsigned char c) {
  if (!c)
    return false;
  switch (state_) {
  case START:
    if (space(c))
      return true;
    if (c != '<')
      return false;
    tag_mask_ = run_only_ ? (1U << 3)
                          : ((planned_ ? 0U : 1U) | (explain_ ? 0U : 2U) |
                             (program_ && !explain_ ? 4U : 0U) |
                             (program_ ? 24U : 0U) | 32U | 64U);
    state_ = TAG;
    at_ = 1;
    return true;
  case TAG: {
    for (unsigned t = 0; t < 7; ++t)
      if ((tag_mask_ & (1U << t)) && tags[t][at_] != char(c))
        tag_mask_ &= ~(1U << t);
    if (!tag_mask_)
      return false;
    ++at_;
    for (unsigned t = 0; t < 7; ++t)
      if ((tag_mask_ & (1U << t)) && !tags[t][at_]) {
        tag_ = t;
        at_ = 0;
        if (t == 0 || t == 6) {
          state_ = TEXT;
          text_ = 0;
          if (t == 0)
            planned_ = true;
        } else if (t == 1) {
          state_ = HEX;
          count_ = 0;
          nibble_ = false;
        } else if (t == 2) {
          state_ = PATCH;
          patch_phase_ = count_ = range_ = address_ = 0;
          std::memset(written_, 0, sizeof(written_));
        } else
          state_ = DONE;
        break;
      }
    return true;
  }
  case TEXT:
    if (c == '<') {
      if (utf8_left_ || (tag_ == 6 && !text_))
        return false;
      state_ = CLOSE;
      at_ = 1;
      return true;
    }
    {
      const unsigned limit = tag_ == 0 ? 96U : 512U;
      if (text_ >= limit)
        return false;
      if (utf8_left_) {
        if ((c & 0xc0) != 0x80)
          return false;
        if (minimum_cp_ == 0x800 && utf8_left_ == 2 &&
            ((codepoint_ == 0 && c < 0xa0) || (codepoint_ == 13 && c > 0x9f)))
          return false;
        if (minimum_cp_ == 0x10000 && utf8_left_ == 3 &&
            ((codepoint_ == 0 && c < 0x90) || (codepoint_ == 4 && c > 0x8f)))
          return false;
        codepoint_ = (codepoint_ << 6) | (c & 63);
        --utf8_left_;
        if (!utf8_left_ && (codepoint_ < minimum_cp_ || codepoint_ > 0x10ffff ||
                            (codepoint_ >= 0xd800 && codepoint_ <= 0xdfff)))
          return false;
      } else if (c >= 0x80) {
        if (c >= 0xc2 && c <= 0xdf) {
          utf8_left_ = 1;
          codepoint_ = c & 31;
          minimum_cp_ = 0x80;
        } else if (c >= 0xe0 && c <= 0xef) {
          utf8_left_ = 2;
          codepoint_ = c & 15;
          minimum_cp_ = 0x800;
        } else if (c >= 0xf0 && c <= 0xf4) {
          utf8_left_ = 3;
          codepoint_ = c & 7;
          minimum_cp_ = 0x10000;
        } else
          return false;
        if (text_ + 1 + utf8_left_ > limit)
          return false;
      }
      ++text_;
      return true;
    }
  case CLOSE: {
    const char *closing = tag_ == 0   ? "</plan>"
                          : tag_ == 1 ? "</write>"
                          : tag_ == 2 ? "</patch>"
                                      : "</ask>";
    if (closing[at_] != char(c))
      return false;
    ++at_;
    if (!closing[at_]) {
      at_ = 0;
      if (tag_ == 6)
        state_ = DONE;
      else {
        state_ = START;
        run_only_ = tag_ == 1 || tag_ == 2;
      }
    }
    return true;
  }
  case HEX:
    if (c == '<') {
      if (nibble_ || !count_)
        return false;
      state_ = CLOSE;
      at_ = 1;
      tag_ = 1;
      return true;
    }
    if (!compact_ && space(c) && !nibble_ && count_ && !last_space_) {
      last_space_ = true;
      return true;
    }
    if (hex(c) < 0 || count_ == 105)
      return false;
    if (nibble_)
      ++count_;
    nibble_ = !nibble_;
    last_space_ = false;
    return true;
  case PATCH:
    if (patch_phase_ == 0 || patch_phase_ == 1) {
      if (hex(c) < 0)
        return false;
      address_ =
          patch_phase_ ? address_ * 16 + unsigned(hex(c)) : unsigned(hex(c));
      ++patch_phase_;
      if (patch_phase_ == 2 && address_ >= 105)
        return false;
      return true;
    }
    if (patch_phase_ == 2) {
      if (c != ':')
        return false;
      patch_phase_ = 3;
      range_ = 0;
      return true;
    }
    if (patch_phase_ == 3 && c == '<') {
      if (!range_)
        return false;
      state_ = CLOSE;
      at_ = 1;
      tag_ = 2;
      return true;
    }
    if (patch_phase_ == 3 && c == ';') {
      if (!range_)
        return false;
      patch_phase_ = address_ = 0;
      return true;
    }
    if (hex(c) < 0 || address_ >= 105 || count_ == 105)
      return false;
    if (patch_phase_ == 3) {
      if (written_[address_ / 8] & (1U << (address_ % 8)))
        return false;
      patch_phase_ = 4;
    } else {
      written_[address_ / 8] |= std::uint8_t(1U << (address_ % 8));
      ++address_;
      ++count_;
      ++range_;
      patch_phase_ = 3;
    }
    return true;
  case DONE:
    return false;
  }
  return false;
}
bool ToolGrammar::accept(const char *bytes, unsigned size) {
  ToolGrammar next = *this;
  for (unsigned i = 0; i < size; ++i)
    if (!next.byte(static_cast<unsigned char>(bytes[i])))
      return false;
  *this = next;
  return true;
}
unsigned ToolGrammar::minimum_tail() const {
  switch (state_) {
  case START:
    return run_only_ ? 6U : 7U;
  case TAG: {
    unsigned n = 1000;
    for (unsigned t = 0; t < 7; ++t)
      if (tag_mask_ & (1U << t))
        n = std::min(n, unsigned(std::strlen(tags[t])) - at_ + tag_tail(t));
    return n;
  }
  case TEXT:
    return utf8_left_ + (tag_ == 0 ? 14U : 6U + (text_ ? 0U : 1U));
  case CLOSE: {
    const unsigned n = tag_ == 0 ? 7U : tag_ == 6 ? 6U : 8U;
    return n - at_ + (tag_ == 0 ? 7U : tag_ == 6 ? 0U : 6U);
  }
  case HEX:
    return 14U + (nibble_ ? 1U : count_ ? 0U : 2U);
  case PATCH:
    if (patch_phase_ < 3)
      return 19U - patch_phase_;
    return 14U + (patch_phase_ == 4 ? 1U : range_ ? 0U : 2U);
  case DONE:
    return 0;
  }
  return 1000;
}
} // namespace mk61ai
