#ifndef DISPLAY_SYMBOLS_HPP
#define DISPLAY_SYMBOLS_HPP

#include "rust_types.h"

namespace display_symbol {

// В старых ветках интерфейса текст UC1609 всё ещё использует байтовые строки.
// Не помещаем эти прежние токены дисплея в позиции NUL и управляющих символов,
// чтобы они были безопасны в строках C и не пересекались с позициями 0..7
// пользовательских глифов времени выполнения.
namespace uc1609 {
static constexpr u8 GE            = 0x80;
static constexpr u8 CYR_PE        = 0x81;
static constexpr u8 CYR_BE        = 0x82;
static constexpr u8 CYR_DE        = 0x83;
static constexpr u8 CYR_I         = 0x84;
static constexpr u8 CYR_GHE       = 0x85;
static constexpr u8 POW2          = 0x86;
static constexpr u8 POWY          = 0x87;
static constexpr u8 XOR           = 0x88;
static constexpr u8 CYC_ARROW     = 0x89;
static constexpr u8 DIVIDE        = 0x8A;
static constexpr u8 NOT_EQUAL     = 0x8B;
static constexpr u8 POW_X         = 0x8C;
static constexpr u8 UP_ARROW      = 0x8D;
static constexpr u8 LT_ARROW      = 0x8E;
static constexpr u8 RT_ARROW      = 0x8F;
static constexpr u8 PI_SYMBOL     = 0x90;
static constexpr u8 SQRT          = 0x91;
static constexpr u8 EM1           = 0x92;
static constexpr u8 GRAD          = 0x93;
static constexpr u8 CYR_CHE       = 0x94;

static inline u16 builtinCodepoint(u16 token) {
  switch(token) {
    case CYR_PE:    return 0x041F;
    case CYR_BE:    return 0x0411;
    case CYR_DE:    return 0x0414;
    case CYR_I:     return 0x0418;
    case CYR_GHE:   return 0x0413;
    case CYR_CHE:   return 0x0427;
    case POW2:      return 0x15;
    case POWY:      return 0x16;
    case XOR:       return 0x17;
    case CYC_ARROW: return 0x05;
    case DIVIDE:    return 0x08;
    case NOT_EQUAL: return 0x07;
    case POW_X:     return 0x06;
    case UP_ARROW:  return 0x0B;
    case LT_ARROW:  return 0x0D;
    case RT_ARROW:  return 0x0C;
    case PI_SYMBOL: return 0x0A;
    case SQRT:      return 0x09;
    case EM1:       return 0x18;
    case GRAD:      return 0x0F;
    default:        return token;
  }
}

static inline u16 unicodeCodepoint(u16 token) {
  switch(token) {
    case GE:        return 0x2265;
    case CYR_PE:    return 0x041F;
    case CYR_BE:    return 0x0411;
    case CYR_DE:    return 0x0414;
    case CYR_I:     return 0x0418;
    case CYR_GHE:   return 0x0413;
    case CYR_CHE:   return 0x0427;
    case POW2:      return 0x00B2;
    case POWY:      return 0x02B8;
    case XOR:       return 0x22BB;
    case CYC_ARROW: return 0x21BB;
    case DIVIDE:    return 0x00F7;
    case NOT_EQUAL: return 0x2260;
    case POW_X:     return 0x02E3;
    case UP_ARROW:  return 0x2191;
    case LT_ARROW:  return 0x2190;
    case RT_ARROW:  return 0x2192;
    case PI_SYMBOL: return 0x03C0;
    case SQRT:      return 0x221A;
    case GRAD:      return 0x00B0;
    default:        return token;
  }
}
} // пространство имён uc1609

} // пространство имён display_symbol

#endif
