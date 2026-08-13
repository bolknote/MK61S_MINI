#ifndef MK61_WS0010_CHARSET_HPP
#define MK61_WS0010_CHARSET_HPP

#include "rust_types.h"

namespace ws0010_charset {

// Canonical map for the WS0010 English/Russian CGROM selected by FT[1:0]=10.
// Codes are transcribed from the manufacturer character table, not from the
// HD44780 A02 table (the two layouts are materially different).
//
// The ROM deliberately reuses Latin glyphs where Cyrillic looks identical.
// Reverse conversion therefore keeps an ASCII byte canonical as Latin; this
// prevents USB Screen from silently changing an English A/B/C/... into a
// Cyrillic codepoint. Distinct Cyrillic glyphs round-trip exactly.

static constexpr u8 CYR_BE       = 0xA0; // Б
static constexpr u8 CYR_GHE      = 0xA1; // Г
static constexpr u8 CYR_IO       = 0xA2; // Ё
static constexpr u8 CYR_ZHE      = 0xA3; // Ж
static constexpr u8 CYR_ZE       = 0xA4; // З
static constexpr u8 CYR_I        = 0xA5; // И
static constexpr u8 CYR_SHORT_I  = 0xA6; // Й
static constexpr u8 CYR_EL       = 0xA7; // Л
static constexpr u8 CYR_PE       = 0xA8; // П
static constexpr u8 CYR_U        = 0xA9; // У
static constexpr u8 CYR_EF       = 0xAA; // Ф
static constexpr u8 CYR_CHE      = 0xAB; // Ч
static constexpr u8 CYR_SHA      = 0xAC; // Ш
static constexpr u8 CYR_HARD     = 0xAD; // Ъ
static constexpr u8 CYR_YERU     = 0xAE; // Ы
static constexpr u8 CYR_E        = 0xAF; // Э
static constexpr u8 CYR_YU       = 0xB0; // Ю
static constexpr u8 CYR_YA       = 0xB1; // Я
static constexpr u8 CYR_DE       = 0xE0; // Д
static constexpr u8 CYR_TSE      = 0xE1; // Ц
static constexpr u8 CYR_SHCHA    = 0xE2; // Щ

static constexpr u8 CYR_SMALL_BE      = 0xB2; // б
static constexpr u8 CYR_SMALL_VE      = 0xB3; // в
static constexpr u8 CYR_SMALL_GHE     = 0xB4; // г
static constexpr u8 CYR_SMALL_IO      = 0xB5; // ё
static constexpr u8 CYR_SMALL_ZHE     = 0xB6; // ж
static constexpr u8 CYR_SMALL_ZE      = 0xB7; // з
static constexpr u8 CYR_SMALL_I       = 0xB8; // и
static constexpr u8 CYR_SMALL_SHORT_I = 0xB9; // й
static constexpr u8 CYR_SMALL_KA      = 0xBA; // к
static constexpr u8 CYR_SMALL_EL      = 0xBB; // л
static constexpr u8 CYR_SMALL_EM      = 0xBC; // м
static constexpr u8 CYR_SMALL_EN      = 0xBD; // н
static constexpr u8 CYR_SMALL_PE      = 0xBE; // п
static constexpr u8 CYR_SMALL_TE      = 0xBF; // т
static constexpr u8 CYR_SMALL_CHE     = 0xC0; // ч
static constexpr u8 CYR_SMALL_SHA     = 0xC1; // ш
static constexpr u8 CYR_SMALL_HARD    = 0xC2; // ъ
static constexpr u8 CYR_SMALL_YERU    = 0xC3; // ы
static constexpr u8 CYR_SMALL_SOFT    = 0xC4; // ь
static constexpr u8 CYR_SMALL_E       = 0xC5; // э
static constexpr u8 CYR_SMALL_YU      = 0xC6; // ю
static constexpr u8 CYR_SMALL_YA      = 0xC7; // я
static constexpr u8 CYR_SMALL_DE      = 0xE3; // д
static constexpr u8 CYR_SMALL_EF      = 0xE4; // ф
static constexpr u8 CYR_SMALL_TSE     = 0xE5; // ц
static constexpr u8 CYR_SMALL_SHCHA   = 0xE6; // щ

static constexpr u8 RIGHT_ARROW = 0x7E;
static constexpr u8 LEFT_ARROW = 0x7F;
static constexpr u8 PI_SYMBOL = 0x93;
static constexpr u8 DEGREE = 0xDF;
static constexpr u8 DIVIDE = 0xF7;

// Default MK61S character-mode CGRAM. Keep this assignment in the controller
// charset policy so menus, USB Screen round-trip and the glyph loader cannot
// silently acquire three different meanings for the same physical slot.
namespace cgram {
static constexpr u8 GREATER_OR_EQUAL = 0;
static constexpr u8 POWER_Y = 1;
static constexpr u8 XOR = 2;
static constexpr u8 NOT_EQUAL = 3;
static constexpr u8 SQUARE_ROOT = 4;
static constexpr u8 CYCLE_ARROW = 5;
static constexpr u8 POWER_X = 6;
static constexpr u8 POWER_2 = 7;
} // namespace cgram

// These symbols do not have a verified one-cell FT=10 glyph. Their fallbacks
// are intentionally visible ASCII, never an A00/A02 byte with another WS0010
// meaning.
static constexpr u8 UP_ARROW_FALLBACK = '^';
static constexpr u8 MULTIPLY_FALLBACK = 'x';
// FT=10 has no one-cell x^-1 mark; using its old A02 byte 0xB9 would display
// Cyrillic small short-I.  A visible ASCII minus is the deterministic fallback.
static constexpr u8 INVERSE_MARKER_FALLBACK = '-';

// Every physical byte has a deterministic canonical token. Unknown or
// pictographic CGROM cells use a private-use codepoint rather than pretending
// to be a different printable character. This makes all 256 cells reversible
// and lets the hardware byte-map qualify them incrementally.
static constexpr u16 PRIVATE_USE_BASE = 0xE000;

static constexpr u8 RUSSIAN_ALPHABET_SIZE = 33;

// Russian alphabet in dictionary order, including Ё/ё after Е/е. Keeping the
// sequence as arithmetic rather than a table costs no RAM and gives terminal
// qualification and host tests one canonical source of truth.
inline u16 russianAlphabetCodepoint(bool lowercase, u8 index) {
  if(index >= RUSSIAN_ALPHABET_SIZE) return 0;
  if(index == 6) return lowercase ? 0x0451 : 0x0401;
  const u16 first = lowercase ? 0x0430 : 0x0410;
  return (u16) (first + index - (index > 6 ? 1u : 0u));
}

inline bool unicodeToByte(u16 codepoint, u8& out) {
  if(codepoint >= 0x20 && codepoint <= 0x7D) {
    out = (u8) codepoint;
    return true;
  }
  switch(codepoint) {
    // MK61S UI symbols routed through the fixed character-mode CGRAM policy.
    // These mappings make Unicode/Markdown and legacy display tokens converge
    // at the controller boundary instead of leaking A00/A02 byte values into
    // WS0010. The eight slots are loaded by the normal LCD font owner.
    case 0x2265: out = cgram::GREATER_OR_EQUAL; return true; // ≥
    case 0x02B8: out = cgram::POWER_Y; return true;          // ʸ
    case 0x22BB: out = cgram::XOR; return true;              // XOR
    case 0x2260: out = cgram::NOT_EQUAL; return true;        // ≠
    case 0x221A: out = cgram::SQUARE_ROOT; return true;      // √
    case 0x21BB: out = cgram::CYCLE_ARROW; return true;      // ↻
    case 0x02E3: out = cgram::POWER_X; return true;          // ˣ
    case 0x00B2: out = cgram::POWER_2; return true;          // ²
    case 0x2192: out = RIGHT_ARROW; return true;
    case 0x2190: out = LEFT_ARROW; return true;
    case 0x2191: out = UP_ARROW_FALLBACK; return true;
    case 0x00D7: out = MULTIPLY_FALLBACK; return true;
    case 0x03C0: out = PI_SYMBOL; return true;
    case 0x00B0: out = DEGREE; return true;
    case 0x00F7: out = DIVIDE; return true;

    case 0x0410: out = 'A'; return true;
    case 0x0411: out = CYR_BE; return true;
    case 0x0412: out = 'B'; return true;
    case 0x0413: out = CYR_GHE; return true;
    case 0x0414: out = CYR_DE; return true;
    case 0x0415: out = 'E'; return true;
    case 0x0401: out = CYR_IO; return true;
    case 0x0416: out = CYR_ZHE; return true;
    case 0x0417: out = CYR_ZE; return true;
    case 0x0418: out = CYR_I; return true;
    case 0x0419: out = CYR_SHORT_I; return true;
    case 0x041A: out = 'K'; return true;
    case 0x041B: out = CYR_EL; return true;
    case 0x041C: out = 'M'; return true;
    case 0x041D: out = 'H'; return true;
    case 0x041E: out = 'O'; return true;
    case 0x041F: out = CYR_PE; return true;
    case 0x0420: out = 'P'; return true;
    case 0x0421: out = 'C'; return true;
    case 0x0422: out = 'T'; return true;
    case 0x0423: out = CYR_U; return true;
    case 0x0424: out = CYR_EF; return true;
    case 0x0425: out = 'X'; return true;
    case 0x0426: out = CYR_TSE; return true;
    case 0x0427: out = CYR_CHE; return true;
    case 0x0428: out = CYR_SHA; return true;
    case 0x0429: out = CYR_SHCHA; return true;
    case 0x042A: out = CYR_HARD; return true;
    case 0x042B: out = CYR_YERU; return true;
    case 0x042C: out = 'b'; return true; // ROM table explicitly reuses b.
    case 0x042D: out = CYR_E; return true;
    case 0x042E: out = CYR_YU; return true;
    case 0x042F: out = CYR_YA; return true;

    case 0x0430: out = 'a'; return true;
    case 0x0431: out = CYR_SMALL_BE; return true;
    case 0x0432: out = CYR_SMALL_VE; return true;
    case 0x0433: out = CYR_SMALL_GHE; return true;
    case 0x0434: out = CYR_SMALL_DE; return true;
    case 0x0435: out = 'e'; return true;
    case 0x0451: out = CYR_SMALL_IO; return true;
    case 0x0436: out = CYR_SMALL_ZHE; return true;
    case 0x0437: out = CYR_SMALL_ZE; return true;
    case 0x0438: out = CYR_SMALL_I; return true;
    case 0x0439: out = CYR_SMALL_SHORT_I; return true;
    case 0x043A: out = CYR_SMALL_KA; return true;
    case 0x043B: out = CYR_SMALL_EL; return true;
    case 0x043C: out = CYR_SMALL_EM; return true;
    case 0x043D: out = CYR_SMALL_EN; return true;
    case 0x043E: out = 'o'; return true;
    case 0x043F: out = CYR_SMALL_PE; return true;
    case 0x0440: out = 'p'; return true;
    case 0x0441: out = 'c'; return true;
    case 0x0442: out = CYR_SMALL_TE; return true;
    case 0x0443: out = 'y'; return true;
    case 0x0444: out = CYR_SMALL_EF; return true;
    case 0x0445: out = 'x'; return true;
    case 0x0446: out = CYR_SMALL_TSE; return true;
    case 0x0447: out = CYR_SMALL_CHE; return true;
    case 0x0448: out = CYR_SMALL_SHA; return true;
    case 0x0449: out = CYR_SMALL_SHCHA; return true;
    case 0x044A: out = CYR_SMALL_HARD; return true;
    case 0x044B: out = CYR_SMALL_YERU; return true;
    case 0x044C: out = CYR_SMALL_SOFT; return true;
    case 0x044D: out = CYR_SMALL_E; return true;
    case 0x044E: out = CYR_SMALL_YU; return true;
    case 0x044F: out = CYR_SMALL_YA; return true;
    default: return false;
  }
}

inline bool byteToUnicode(u8 value, u16& out) {
  switch(value) {
    case RIGHT_ARROW: out = 0x2192; return true;
    case LEFT_ARROW: out = 0x2190; return true;
    case PI_SYMBOL: out = 0x03C0; return true;
    case DEGREE: out = 0x00B0; return true;
    case DIVIDE: out = 0x00F7; return true;

    case CYR_BE: out = 0x0411; return true;
    case CYR_GHE: out = 0x0413; return true;
    case CYR_DE: out = 0x0414; return true;
    case CYR_IO: out = 0x0401; return true;
    case CYR_ZHE: out = 0x0416; return true;
    case CYR_ZE: out = 0x0417; return true;
    case CYR_I: out = 0x0418; return true;
    case CYR_SHORT_I: out = 0x0419; return true;
    case CYR_EL: out = 0x041B; return true;
    case CYR_PE: out = 0x041F; return true;
    case CYR_U: out = 0x0423; return true;
    case CYR_EF: out = 0x0424; return true;
    case CYR_TSE: out = 0x0426; return true;
    case CYR_CHE: out = 0x0427; return true;
    case CYR_SHA: out = 0x0428; return true;
    case CYR_SHCHA: out = 0x0429; return true;
    case CYR_HARD: out = 0x042A; return true;
    case CYR_YERU: out = 0x042B; return true;
    case CYR_E: out = 0x042D; return true;
    case CYR_YU: out = 0x042E; return true;
    case CYR_YA: out = 0x042F; return true;

    case CYR_SMALL_BE: out = 0x0431; return true;
    case CYR_SMALL_VE: out = 0x0432; return true;
    case CYR_SMALL_GHE: out = 0x0433; return true;
    case CYR_SMALL_DE: out = 0x0434; return true;
    case CYR_SMALL_IO: out = 0x0451; return true;
    case CYR_SMALL_ZHE: out = 0x0436; return true;
    case CYR_SMALL_ZE: out = 0x0437; return true;
    case CYR_SMALL_I: out = 0x0438; return true;
    case CYR_SMALL_SHORT_I: out = 0x0439; return true;
    case CYR_SMALL_KA: out = 0x043A; return true;
    case CYR_SMALL_EL: out = 0x043B; return true;
    case CYR_SMALL_EM: out = 0x043C; return true;
    case CYR_SMALL_EN: out = 0x043D; return true;
    case CYR_SMALL_PE: out = 0x043F; return true;
    case CYR_SMALL_TE: out = 0x0442; return true;
    case CYR_SMALL_EF: out = 0x0444; return true;
    case CYR_SMALL_TSE: out = 0x0446; return true;
    case CYR_SMALL_CHE: out = 0x0447; return true;
    case CYR_SMALL_SHA: out = 0x0448; return true;
    case CYR_SMALL_SHCHA: out = 0x0449; return true;
    case CYR_SMALL_HARD: out = 0x044A; return true;
    case CYR_SMALL_YERU: out = 0x044B; return true;
    case CYR_SMALL_SOFT: out = 0x044C; return true;
    case CYR_SMALL_E: out = 0x044D; return true;
    case CYR_SMALL_YU: out = 0x044E; return true;
    case CYR_SMALL_YA: out = 0x044F; return true;
    default: return false;
  }
}

inline u16 canonicalForByte(u8 value) {
  if(value >= 0x20 && value <= 0x7D) return value;
  u16 codepoint = 0;
  return byteToUnicode(value, codepoint)
       ? codepoint : (u16) (PRIVATE_USE_BASE + value);
}

inline bool canonicalToByte(u16 codepoint, u8& out) {
  if(unicodeToByte(codepoint, out)) return true;
  if(codepoint >= PRIVATE_USE_BASE &&
     codepoint <= (u16) (PRIVATE_USE_BASE + 0xFFu)) {
    out = (u8) (codepoint - PRIVATE_USE_BASE);
    return true;
  }
  return false;
}

} // namespace ws0010_charset

#endif
