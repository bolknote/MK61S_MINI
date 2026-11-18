#include "config.h"
#include "cross_hal.h"
#include "lcd_gui.hpp"

#include "cross_key_pairs.inc"

#ifndef SCAN_ROW
constexpr char m_Cx[]   = {2, 'C', 'x'};
constexpr char m_Bx[]   = {2, 'B', LCD_UP_ARROW_CHAR};
constexpr char m_mul[]  = {1, 'x'};
constexpr char m_div[]  = {1, LCD_DIVIDE_CHAR};
constexpr char m_G[]    = {3, ' ', ' ', G_RUS};
constexpr char m_E[]    = {2, 'B', P_RUS};
constexpr char m_XY[]   = {2, LCD_LT_ARROW_CHAR, LCD_RT_ARROW_CHAR};
constexpr char m_add[]  = {1, '+'};
constexpr char m_sub[]  = {1, '-'};
constexpr char m_GRD[]  = {3, G_RUS, 'P', D_RUS};
constexpr char m_NEG[]  = {3, '/', '-', '/'};
constexpr char m_3[]    = {1, '3'};
constexpr char m_6[]    = {1, '6'};
constexpr char m_9[]    = {1, '9'};
constexpr char m_R[]    = {1, 'P'};
#if defined(MK61_KEYBOARD_CLASSIC)
constexpr char m_DP[]   = {1, '.'};
#else
constexpr char m_DP[]   = {1, 0xA5};
#endif
constexpr char m_2[]    = {1, '2'};
constexpr char m_5[]    = {1, '5'};
constexpr char m_8[]    = {1, '8'};
constexpr char m_0[]    = {1, '0'};
constexpr char m_1[]    = {1, '1'};
constexpr char m_4[]    = {1, '4'};
constexpr char m_7[]    = {1, '7'};
constexpr char m_PP[]   = {2, P_RUS, P_RUS};
constexpr char m_BP[]   = {2|STORE_KEY, B_RUS, P_RUS};
#ifdef B3_34
  constexpr char m_xP[]   = {1|STORE_KEY, P_RUS};
  constexpr char m_Px[]   = {2|STORE_KEY, I_RUS, P_RUS};
#else
  constexpr char m_xP[]   = {3|STORE_KEY, 'x', LCD_RT_ARROW_CHAR, P_RUS};  // MK61 мнемоника x->П
  constexpr char m_Px[]   = {3|STORE_KEY, P_RUS, LCD_RT_ARROW_CHAR, 'x'};  // MK61 мнемоника П->x
#endif
constexpr char m_SP[]   = {3, 'C', '/', P_RUS};
constexpr char m_BO[]   = {3, 'B', '/', 'O'};
constexpr char m_SF[]   = {1, LCD_RT_ARROW_CHAR};
constexpr char m_SB[]   = {1, LCD_LT_ARROW_CHAR};
constexpr char m_F[]    = {1|STORE_KEY, 'F'};
constexpr char m_K[]    = {1|STORE_KEY, 'K'};
constexpr char m__[]    = {1, ' '};

#if defined(MK61_KEYBOARD_CLASSIC)
constexpr const char* mnemo_code[40] = {
  m_Cx,   m_E,    m_NEG,  m_DP,   m_0,
  m_Bx,   m_XY,   m_3,    m_2,    m_1,
  m_mul,  m_add,  m_6,    m_5,    m_4,
  m_div,  m_sub,  m_9,    m_8,    m_7,
  m_PP,   m_BP,   m_xP,   m_Px,   m_K,
  m_SP,   m_BO,   m_SF,   m_SB,   m_F,
  m__,    m__,    m__,    m__,    m__,
  m__,    m__,    m__,    m__,    m__
};
#else
constexpr const char* mnemo_code[40] = {
  m_Cx,   m_Bx,   m_mul,  m_div,  m_G,
  m_E,    m_XY,   m_add,  m_sub,  m_GRD,
  m_NEG,  m_3,    m_6,    m_9,    m_R,
  m_DP,   m_2,    m_5,    m_8,    m__,
  m_0,    m_1,    m_4,    m_7,    m__,
  m_PP,   m_BP,   m_xP,   m_Px,   m__,
  m_SP,   m_BO,   m_SF,   m_SB,   m__,
  m__,    m__,    m_K,    m_F,    m__
};
#endif
/*
const char* mnemo_code[40] = {
  "Cx",        "B\xC4",    "x",       "\xFD",     "  \x05",       
  "B\x01",     "\x7F\x7E", "+",       "-",        "\x05P\x03",    
  "/-/",       "3",        "6",       "9",        "P  ",          
  "\xA5",      "2",        "5",       "8",        "",          
  "0",         "1",        "4",       "7",        "",
  "\x01\x01",  "\x02\x01", "\x01",    "\x04\x01", "",
  "C/\x01",    "B/O",      "<<<",     ">>>",      "",
  "",          "",         "K",       "F",        ""
};*/
//"X\x7E\x01", "\x01\x7EX"

#if defined(MK61_KEYBOARD_CLASSIC)
const u8 mnemo_code_register[40] = {
  D_RUS,  'C',  'B', 'A', '0',
  'E',    '?',  '3', '2', '1',
  '?',    '?',  '6', '5', '4',
  '?',    '?',  '9', '8', '7',
  '?',    '?',  '?', '?', '?',
  '?',    '?',  '?', '?', '?',
  '?',    '?',  '?', '?', '?',
  '?',    '?',  '?', '?', '?'
};
#else
const u8 mnemo_code_register[40] = {
  D_RUS,  'E',  '?', '?', '?',
  'C',    '?',  '?', '?', '?',
  'B',    '3',  '6', '9', '?',
  'A',    '2',  '5', '8', '?',
  '0',    '1',  '4', '7', '?',
  '?',    '?',  '?', '?', '?',
  '?',    '?',  '?', '?', '?'
};
#endif

constexpr char m_FCx[]  = {2, 'C', 'F'};
constexpr char m_FBx[]  = {2, 'B', 'x'};
constexpr char m_FX2[]  = {2, 'x', LCD_CHAR_POW2};
constexpr char m_1DX[]  = {3, '1', '/', 'x'};
constexpr char m_FE[]   = {3, P_RUS, 'P', G_RUS};
constexpr char m_FXY[]  = {2, 'x', LCD_CHAR_POWY};
constexpr char m_FPI[]  = {1, LCD_PI_CHAR};
constexpr char m_FRT[]  = {1, LCD_SQRT_CHAR};
constexpr char m_FNEG[] = {3, 'A', 'B', 'T'};
constexpr char m_F3[]   = {2, 'l', 'n'};
constexpr char m_F6[]   = {3, 't', 'g', LCD_Em1_CHAR};
constexpr char m_F9[]   = {2, 't', 'g'};
constexpr char m_FDP[]  = {1, LCD_CYC_ARROW};
constexpr char m_F2[]   = {2, 'l', 'g'};
constexpr char m_F5[]   = {4, 'c', 'o', 's', LCD_Em1_CHAR};
constexpr char m_F8[]   = {3, 'c', 'o', 's'};
constexpr char m_F0[]   = {3, '1', '0', LCD_POW_X_CHAR};
constexpr char m_F1[]   = {2, 'e', LCD_POW_X_CHAR};
constexpr char m_F4[]   = {4, 's', 'i', 'n', LCD_Em1_CHAR};
constexpr char m_F7[]   = {3, 's', 'i', 'n'};
constexpr char m_FSB[]  = {3, 'x', '=', '0'};
constexpr char m_FSF[]  = {3, 'x', '<', '0'};
constexpr char m_FSP[]  = {3, 'x', LCD_NOT_EQU_CHAR, '0'};
constexpr char m_FBO[]  = {4, 'x', '>', '=', '0'};
constexpr char m_FPP[]  = {2, 'L', '3'};
constexpr char m_FBP[]  = {2, 'L', '2'};
constexpr char m_FxP[]  = {2, 'L', '1'};
constexpr char m_FPx[]  = {2, 'L', '0'};
constexpr char m_FF[]   = {0|STORE_KEY, 0};
constexpr char m_null[] = {0, 0};

#if defined(MK61_KEYBOARD_CLASSIC)
constexpr const char* mnemo_code_F[40] = {
  m_FCx,  m_FE,   m_FNEG, m_FDP,  m_F0,
  m_FBx,  m_FXY,  m_F3,   m_F2,   m_F1,
  m_FX2,  m_FPI,  m_F6,   m_F5,   m_F4,
  m_1DX,  m_FRT,  m_F9,   m_F8,   m_F7,
  m_FPP,  m_FBP,  m_FxP,  m_FPx,  m_K,
  m_FSP,  m_FBO,  m_FSB,  m_FSF,  m_FF,
  m__,    m__,    m__,    m__,    m__,
  m__,    m__,    m__,    m__,    m__
};
#else
constexpr const char* mnemo_code_F[40] = {
  m_FCx,  m_FBx,  m_FX2,  m_1DX,  m__,
  m_FE,   m_FXY,  m_FPI,  m_FRT,  m__,
  m_FNEG, m_F3,   m_F6,   m_F9,   m__,
  m_FDP,  m_F2,   m_F5,   m_F8,   m__,
  m_F0,   m_F1,   m_F4,   m_F7,   m__,
  m_FPP,  m_FBP,  m_FxP,  m_FPx,  m__,
  m_FSP,  m_FBO,  m_FSB,  m_FSF,  m__,
  m__,    m__,    m_K,    m_FF,   m__
};
#endif

constexpr char m_KCx[]  = {3, I_RUS, 'H', 'B'};
constexpr char m_KBx[]  = {2, 'C', CH_RUS};
constexpr char m_KE[]   = {1, LCD_CHAR_XOR};
constexpr char m_KXY[]  = {4, '"', LCD_QUOTE_CHAR, LCD_RT_ARROW_CHAR, LCD_GRAD_CHAR};
constexpr char m_KDIV[] = {3, LCD_QUOTE_CHAR, LCD_RT_ARROW_CHAR, LCD_GRAD_CHAR};
constexpr char m_KNEG[] = {1, 'v'};
constexpr char m_K3[]   = {4, '"', LCD_QUOTE_CHAR, LCD_LT_ARROW_CHAR, LCD_GRAD_CHAR};
constexpr char m_K6[]   = {3, LCD_GRAD_CHAR, LCD_LT_ARROW_CHAR, LCD_QUOTE_CHAR};
constexpr char m_K9[]   = {3, 'm', 'a', 'x'};
constexpr char m_KDP[]  = {1, '^'};
constexpr char m_K5[]   = {2, '3', 'H'};
constexpr char m_K8[]   = {3, '{', 'x', '}'};
constexpr char m_K0[]   = {3, 'H', 'O', P_RUS};
constexpr char m_K4[]   = {3, '|', 'x', '|'};
constexpr char m_K7[]   = {3, '[', 'x', ']'};
constexpr char m_KK[]   = {0|STORE_KEY, 0};
constexpr char m_KSB[]  = {3|STORE_KEY, 'x', '=', '0'};
constexpr char m_KSF[]  = {3|STORE_KEY, 'x', '<', '0'};
constexpr char m_KBO[]  = {4|STORE_KEY, 'x', '>', '=', '0'};
constexpr char m_KSP[]  = {3|STORE_KEY, 'x', LCD_NOT_EQU_CHAR, '0'};
constexpr char m_KPP[]  = {2|STORE_KEY, P_RUS, P_RUS};

#if defined(MK61_KEYBOARD_CLASSIC)
constexpr const char* mnemo_code_K[40] = {
  m_KCx,  m_KE,   m_KNEG, m_KDP,  m_K0,
  m_KBx,  m_KXY,  m_K3,   m__,    m__,
  m__,    m_KDIV, m_K6,   m_K5,   m_K4,
  m__,    m__,    m_K9,   m_K8,   m_K7,
  m_KPP,  m_BP,   m_xP,   m_Px,   m_KK,
  m_KSP,  m_KBO,  m_KSF,  m_KSB,  m_F,
  m__,    m__,    m__,    m__,    m__,
  m__,    m__,    m__,    m__,    m__
};
#else
constexpr const char* mnemo_code_K[40] = {
  m_KCx,  m_KBx,  m__,    m__,    m__,
  m_KE,   m_KXY,  m_KDIV, m__,    m__,
  m_KNEG, m_K3,   m_K6,   m_K9,   m__,
  m_KDP,  m__,    m_K5,   m_K8,   m__,
  m_K0,   m__,    m_K4,   m_K7,   m__,
  m_KPP,  m_BP,   m_xP,   m_Px,   m__,
  m_KSP,  m_KBO,  m_KSF,  m_KSB,  m__,
  m__,    m__,    m_KK,   m_F,    m__
};
#endif

#if MK61_PACKED_KEY_MNEMONICS
namespace {
using MnemonicLayout = const char* const[40];

constexpr unsigned descriptor_size(const char* label) {
  return 1U + (static_cast<u8>(label[0]) & ~STORE_KEY);
}

constexpr unsigned first_occurrence(const MnemonicLayout& labels, unsigned key) {
  const char* label = labels[key];
  for(unsigned prev = 0; prev < key; ++prev) {
    if(labels[prev][0] != label[0]) continue;
    unsigned i = 1;
    while(i < descriptor_size(label) && labels[prev][i] == label[i]) ++i;
    if(i == descriptor_size(label)) return prev;
  }
  return key;
}

constexpr unsigned bank_size(const MnemonicLayout& labels) {
  unsigned size = 40;
  for(unsigned key = 0; key < 40; ++key)
    if(first_occurrence(labels, key) == key) size += descriptor_size(labels[key]);
  return size;
}

template<unsigned Size>
struct MnemonicBank {
  static_assert(Size <= 256, "key mnemonic offsets must fit in one byte");
  char bytes[Size] = {};

  constexpr explicit MnemonicBank(const MnemonicLayout& labels) {
    unsigned next = 40;  // The first 40 bytes index the descriptors that follow.
    for(unsigned key = 0; key < 40; ++key) {
      const unsigned first = first_occurrence(labels, key);
      if(first != key) {
        bytes[key] = bytes[first];
      } else {
        bytes[key] = static_cast<char>(next);
        for(unsigned i = 0; i < descriptor_size(labels[key]); ++i)
          bytes[next++] = labels[key][i];
      }
    }
  }

  constexpr const char* operator[](unsigned key) const {
    return bytes + static_cast<u8>(bytes[key]);
  }

  constexpr bool matches(const MnemonicLayout& labels) const {
    for(unsigned key = 0; key < 40; ++key)
      for(unsigned i = 0; i < descriptor_size(labels[key]); ++i)
        if((*this)[key][i] != labels[key][i]) return false;
    return true;
  }
};

constexpr MnemonicBank<bank_size(mnemo_code)> plain(mnemo_code);
constexpr MnemonicBank<bank_size(mnemo_code_F)> shifted_f(mnemo_code_F);
constexpr MnemonicBank<bank_size(mnemo_code_K)> shifted_k(mnemo_code_K);
static_assert(plain.matches(mnemo_code) && shifted_f.matches(mnemo_code_F) &&
              shifted_k.matches(mnemo_code_K), "packed key descriptor changed");
} // namespace

const char* key_mnemonic(unsigned key) { return plain[key]; }
const char* f_key_mnemonic(unsigned key) { return shifted_f[key]; }
const char* k_key_mnemonic(unsigned key) { return shifted_k[key]; }
#endif

#endif
