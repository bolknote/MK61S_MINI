#ifndef MK61_MK8_LITERAL_HPP
#define MK61_MK8_LITERAL_HPP

#include "mk8_codec.hpp"
#include <stddef.h>

// Source literals stay UTF-8. Only their exact-size M8 result reaches the
// binary; no Unicode text or conversion code is needed at runtime.
namespace mk8 {
namespace detail {

struct LiteralCharacter {
  u32 codepoint;
  usize width;
};

template<usize N>
constexpr LiteralCharacter read_literal(const char (&source)[N], usize at) {
  const u8 first = (u8) source[at];
  if(first < 0x80) return {first, 1}; // Includes embedded NULs.
  const usize width = first >= 0xC2 && first <= 0xDF ? 2 :
                      first >= 0xE0 && first <= 0xEF ? 3 : 0;
  if(width == 0 || at + width >= N) return {0, 0};
  u32 value = first & (width == 2 ? 0x1F : 0x0F);
  for(usize part = 1; part < width; ++part) {
    const u8 next = (u8) source[at + part];
    if((next & 0xC0) != 0x80) return {0, 0};
    value = (value << 6) | (next & 0x3F);
  }
  if((width == 2 && value < 0x80) ||
     (width == 3 && (value < 0x800 ||
                     (value >= 0xD800 && value <= 0xDFFF)))) return {0, 0};
  return {value, width};
}

} // namespace detail

// A zero size deliberately fails make_literal's static assertion. The size
// includes the terminating NUL and never includes UTF-8 padding.
template<usize N>
constexpr usize literal_size(const char (&source)[N]) {
  usize size = 1;
  for(usize at = 0; at < N - 1;) {
    const detail::LiteralCharacter current = detail::read_literal(source, at);
    u8 byte = 0;
    if(current.width == 0 ||
       (current.codepoint != 0 &&
        (!from_codepoint(current.codepoint, byte) || !valid_byte(byte)))) {
      return 0;
    }
    at += current.width;
    ++size;
  }
  return size;
}

template<usize N>
struct Literal {
  char bytes[N];

  constexpr const char* data() const { return bytes; }
  constexpr char operator[](usize at) const { return bytes[at]; }
};

// Old menu entries have an inline flexible text[] tail. Keep its compact
// storage layout instead of replacing it with an extra pointer per entry.
template<typename Action, usize N>
struct PunctLiteral {
  u8 size;
  Action action;
  char text[N];
};

template<typename Action, usize N>
constexpr PunctLiteral<Action, N> make_punct(u8 size, Action action,
                                            const Literal<N>& label) {
  PunctLiteral<Action, N> result = {size, action, {}};
  for(usize i = 0; i < N; ++i) result.text[i] = label[i];
  return result;
}

template<typename Punct, typename Action, usize N>
Punct* punct_view(const PunctLiteral<Action, N>& entry) {
  using Packed = PunctLiteral<Action, N>;
  static_assert(offsetof(Punct, text) ==
                    offsetof(Packed, text),
                "menu entry prefix must match its M8 inline text");
  static_assert(offsetof(Punct, action) ==
                    offsetof(Packed, action),
                "menu entry action must have the same layout");
  return reinterpret_cast<Punct*>(
      const_cast<PunctLiteral<Action, N>*>(&entry));
}

template<usize Output, usize Input>
constexpr Literal<Output> make_literal(const char (&source)[Input]) {
  static_assert(Output != 0, "M8 literal contains invalid UTF-8 or an unsupported character");
  Literal<Output> output = {};
  usize written = 0;
  for(usize at = 0; at < Input - 1;) {
    const detail::LiteralCharacter current = detail::read_literal(source, at);
    u8 byte = 0;
    if(current.codepoint != 0) from_codepoint(current.codepoint, byte);
    output.bytes[written++] = (char) byte;
    at += current.width;
  }
  output.bytes[written] = 0;
  return output;
}

} // namespace mk8

// M8() is for ordinary pointer sites. M8_ARRAY() produces an exact-size
// constexpr object for static arrays, including strings with embedded NULs.
// For constexpr pointer tables, name an M8_ARRAY() object at file scope and
// use its .data() so the pointer itself is a constant expression.
#define M8_ARRAY(source) ::mk8::make_literal<::mk8::literal_size(source)>(source)
#define M8(source) ([]() -> const char* { \
  static constexpr auto m8_text = M8_ARRAY(source); \
  return m8_text.data(); \
}())
#define M8_PUNCT(size, action, source) \
  ::mk8::make_punct((size), (action), M8_ARRAY(source))

#endif
