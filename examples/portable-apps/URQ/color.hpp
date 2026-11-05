#ifndef MK61_URQ_COLOR_HPP
#define MK61_URQ_COLOR_HPP
#include "urq/engine.hpp"
#include <string.h>
namespace urq_color {
constexpr uint16_t rgb565(uint32_t rgb) {
  return uint16_t(((rgb >> 8) & 0xF800) | ((rgb >> 5) & 0x7E0) | ((rgb >> 3) & 31));
}
inline int hex(char ch) {
  ch = char(urq::lower(uint8_t(ch)));
  return ch >= '0' && ch <= '9' ? ch - '0' : ch >= 'a' && ch <= 'f' ? ch - 'a' + 10 : -1;
}
inline uint16_t parse(const urq::Value& value, uint16_t fallback) {
  if(value.type != 1) {
    if(!(value.number > 0 && value.number <= 4294967295.0)) return fallback;
    const uint32_t bgr = uint32_t(value.number);
    return rgb565(((bgr & 255) << 16) | (bgr & 0xFF00) | ((bgr >> 16) & 255));
  }
  const char* text = value.text;
  if(!text) return fallback;
  if(*text == '#') {
    ++text;const unsigned size = strlen(text);
    if(size != 3 && size != 6) return fallback;
    uint32_t rgb = 0;
    for(unsigned i = 0; i < size; ++i) {
      const int digit = hex(text[i]);if(digit < 0) return fallback;
      rgb = size == 3 ? (rgb << 8) | unsigned(digit * 17) : (rgb << 4) | unsigned(digit);
    }
    return rgb565(rgb);
  }
  static const char* const names[] = {"black","silver","gray","white","maroon","red","purple","fuchsia",
      "green","lime","olive","yellow","navy","blue","teal","aqua","orange"};
  static const uint32_t colors[] = {0,0xC0C0C0,0x808080,0xFFFFFF,0x800000,0xFF0000,0x800080,0xFF00FF,
      0x008000,0x00FF00,0x808000,0xFFFF00,0x000080,0x0000FF,0x008080,0x00FFFF,0xFFA500};
  for(unsigned i = 0; i < sizeof(colors)/sizeof(*colors); ++i)
    if(urq::equal_name(text, names[i])) return rgb565(colors[i]);
  if(!strncmp(text, "rgb(", 4)) {
    text += 4;uint32_t rgb = 0;
    for(unsigned channel = 0; channel < 3; ++channel) {
      while(*text == ' ') ++text;
      unsigned component = 0, digits = 0;
      while(*text >= '0' && *text <= '9') { component = component * 10 + unsigned(*text++ - '0');if(++digits > 3) return fallback; }
      while(*text == ' ') ++text;
      if(!digits || component > 255 || *text++ != (channel == 2 ? ')' : ',')) return fallback;
      rgb = (rgb << 8) | component;
    }
    if(!*text) return rgb565(rgb);
  }
  return fallback;
}
}
#endif
