/* 
 * This file is part of the MK61S distribution (https://gitlab.com/vitasam/mk61s).
 * Copyright (c) 2020- vitasam.
 * 
 * Based on emu145 code from F.Lazarev:
 * https://github.com/fixelsan/emu145
 * 
 * This program is free software: you can redistribute it and/or modify  
 * it under the terms of the GNU General Public License as published by  
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but 
 * WITHOUT ANY WARRANTY; without even the implied warranty of 
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU 
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License 
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
//#include "Arduino.h"
#include "mk61emu_core.h"
#include "debug.h"
#include "config.h"
#include "rust_types.h"
#include "stm32_sram_bit_band.hpp"
#include "dwt_profiler.hpp"
#if MK61_CORE_PACKED_AMK
  #include "core_packed_amk.hpp"
#endif
#if MK61_CORE_HOT_TABLES_IN_SRAM > 0
  #include "shared_memory.hpp"
  #include "workspace_swap.hpp"
#endif

// F411 compatibility builds compact cold firmware when the Arduino menu asks
// for global -O2/-O3.  This translation unit is their measured hot path, so
// restore the command-line optimization here.  F401 production instead keeps
// global -Os+LTO and uses MK61_CORE_HOT_O3 on only the loops proven below.
#if MK61_MIXED_OPTIMIZATION
  #pragma GCC reset_options
#endif

#if MK61_CORE_PACKED_AMK
  #define MK61_PACKED_AMK_PARAMETERS \
      , u8 selected_amk, u32 selected_microinstruction
#else
  #define MK61_PACKED_AMK_PARAMETERS
#endif

#if MK61_CORE_MERGED_TICK
  #define MK61_CORE_TICK_FUNCTION \
    static inline void __attribute__((always_inline))
#else
  #define MK61_CORE_TICK_FUNCTION void
#endif

typedef struct {  // Структору ПЗУ для одной микросхемы комплекта К145ИК(02,03,06)
    microinstruction_t microinstructions[68]; // микрокоманды
    instruction_t instructions[256];          // команды
} IK13_ROM;

typedef struct { // ПЗУ микрокода, микропрограмм для всего комплекта К145ИК(02,03,06) МК61
    IK13_ROM IK1302;
    IK13_ROM IK1303;
    IK13_ROM IK1306;
} mk61ROM_t;

typedef struct { // Структура микросхемы К145IИК303 
    uint8_t   *pM;
    uint8_t   R[IK13_MTICK_COUNT];
    uint8_t   ST[IK13_MTICK_COUNT];

    io_t      AMK, MOD;
    io_t      S, S1, L, T, P, flag_FC;

    const uint8_t   *pAND_AMK;  // Заранее вычисленное смещение от микропрограмм для signal_I 0..26
    const uint8_t   *pAND_AMK1; // Заранее вычисленное смещение от микропрограмм для signal_I 27..35
    uint16_t  key_x, key_xm, key_y, comma;
}  IK1303;

typedef struct { // Структура микросхемы К145IИК306 
    uint32_t  AMK;

    uint32_t  L, S, S1, P, T, MOD, flag_FC;

    uint8_t   R[IK13_MTICK_COUNT];
    uint8_t   ST[IK13_MTICK_COUNT];

    const uint8_t*  pAND_AMK1; // Заранее вычисленное смещение от микропрограмм для signal_I 27..35
    const uint8_t*  pAND_AMK;
    uint8_t*  pM;
}  IK1306;

MK61_CORE_TICK_FUNCTION IK1302_Tick(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3
    MK61_PACKED_AMK_PARAMETERS);
MK61_CORE_TICK_FUNCTION IK1303_Tick(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3
    MK61_PACKED_AMK_PARAMETERS);
MK61_CORE_TICK_FUNCTION IK1306_Tick(
    mtick_t signal_I, usize J_signal_I
    MK61_PACKED_AMK_PARAMETERS);
#if MK61_CORE_MERGED_TICK
static void MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))
IK130X_Tick_All(mtick_t signal_I, usize J_signal_I, mtick_t signal_div3);
#if MK61_CORE_NATIVE_HOT_PATHS
static void MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))
IK1302_1303_Tick_All(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3);
#endif
#endif

/* Кольцо ДОЗУ - последовательно соединенная память комплектов микросхем К145ИК(02,03,06) в МК61 */
u8 ringM[SIZE_RING_M/*252+252+42+42+42+42*/];
const u8* END_ring_M = &ringM[SIZE_RING_M/*252+252+42+42+42+42*/];
static bool expanded_program_mode = false;

// Необязательный режим случайных чисел MK61s. Обработчик пользовательской
// команды распознаёт код 3B (K RNG) и взводит однократную подстановку; затем
// низкоуровневый обработчик IK1306:A7 записывает новое значение во временное
// слово xi непосредственно перед чтением штатным ПЗУ. Каждое значение задаётся
// намеренно: при измерении штатное ПЗУ выдало до повтора лишь 179 разных значений
// (префикс из 26 значений и последующий цикл из 153 значений).
static bool external_random_enabled = false;
static bool external_random_pending = false;
static u64 external_random_state = 0xA0761D6478BD642FULL;

const bool sergey_anvarov_hack_enable = true;

MK61Emu m_emu;

static inline u8 region3_microprogram(u8 encoded) {
  // Bytes above 1F carry an inline operand in R37/R40 and execute the common
  // decoder body 5F, exactly as cycle() does before microtick 36.
  return encoded > 0x1FU ? 0x5FU : encoded;
}

#if MK61_CORE_BODY_PROFILE
static u64 body_profile_counts[3]
                              [core_61::BODY_PROFILE_REGION_COUNT]
                              [core_61::BODY_PROFILE_MICROPROGRAM_COUNT] = {};
static u64 body_profile_call_count = 0;

static inline void profile_body(core_61::RomChip chip, u8 region,
                                u8 microprogram) {
  const u8 chip_index = (u8) chip;
  if(chip_index >= 3 ||
     region >= core_61::BODY_PROFILE_REGION_COUNT ||
     microprogram >= core_61::BODY_PROFILE_MICROPROGRAM_COUNT) return;
  body_profile_counts[chip_index][region][microprogram]++;
  body_profile_call_count++;
}

static inline void profile_instruction(core_61::RomChip chip,
                                       instruction_t instruction) {
  profile_body(chip, 0, (u8) instruction);
  profile_body(chip, 1, (u8) (instruction >> 8));
  profile_body(chip, 2, region3_microprogram((u8) (instruction >> 16)));
}
#else
static inline void profile_instruction(core_61::RomChip, instruction_t) {}
#endif

#if MK61_CORE_NATIVE_HOT_PATHS
#if defined(ARDUINO)
static constexpr bool native_hot_paths_are_enabled = true;
static inline void count_native_hot_path(core_61::NativeHotPath) {}
#else
static bool native_hot_paths_are_enabled = true;
static u64 native_hot_path_counts[(u8) core_61::NativeHotPath::COUNT] = {};

static inline void count_native_hot_path(core_61::NativeHotPath path) {
  native_hot_path_counts[(u8) path]++;
}
#endif
#endif

#if MK61_CORE_PACKED_AMK && !defined(ARDUINO)
static bool packed_amk_is_enabled = true;
#endif

static const char default_symbols[16] = {
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', 'L', 'C', 'r', 'E', ' '
};

static inline char display_symbol(const char* symbols, u8 value) {
  const char* active_symbols = symbols == NULL ? default_symbols : symbols;
  return active_symbols[value < 16 ? value : 15];
}

#include "array"
#if IS_CORTEX_M4() //__ARM_ARCH == 7
#else
  // На ядрах без аппаратного деления используем таблицы констант.
  constexpr static const std::array<uint8_t, 256> div3_table = []() {
    std::array<uint8_t, 256> _{};
    for (auto i=0; i<256; i++) _[i]=i/3;
    return _;
  }();

  constexpr static const std::array<uint8_t, 256> mul9_table = []() {
    std::array<uint8_t, 256> _{};
    for (auto i=0; i<256; i++) _[i]=i*9;
    return _;
  }();
#endif

/*static std::array<uint8_t, 42+41> mod42_table = []() {
  std::array<uint8_t, 42+41> _{};
  for (auto i=0; i<42+41; i++) _[i]=i%42;
  return _;
}();*/
/*
static std::array<uint8_t, 256> __attribute__ ((aligned (16))) mod42_table = []() {
  std::array<uint8_t, 256> _{};
  for (auto i=0; i<256; i++) _[i]=i%42;
  return _;
}();
*/
static  constexpr usize MOD42_TABLE_SIZE = 42 + 41;
static  u8  __attribute__((aligned (16))) mod42_table[MOD42_TABLE_SIZE];

#define DIV3(v)         (((v)*171)>>9)  //(div3_table[v]) 
//#define DIV3(v)       (((v)*171)>>9)
//#define DIV3(v)       ((v)/3)         //udiv M3/M4 

#if IS_CORTEX_M4() //__ARM_ARCH == 7
  #define MUL9(v)       ((v)*9)
#else
  #define MUL9(v)       (mul9_table[v])
//#define MUL9(v)       ((v)*9)
//#define MUL9(v)       ( ((v)+((v)<<3)) &0xff )
#endif

#define MOD42(v)       (mod42_table[v])
//#define MOD42(v)  ( ((v) %42) &0xff )

static const mk61ROM_t ROM = {
        {
                {
                        0x0000000, 0x0800001, 0x0A00820, 0x0040020, // 1
                        0x0A03120, 0x0203081, 0x0A00181, 0x0803800,
                        0x0818001, 0x0800400, 0x0A00089, 0x0A03C20,
                        0x0800820, 0x0080020, 0x0800120, 0x1400020,
                        0x0800081, 0x0210801, 0x0040000, 0x0058001,
                        0x0808001, 0x0A03081, 0x0A01081, 0x0A01181,
                        0x0040090, 0x0800401, 0x0A00081, 0x0040001,
                        0x0800801, 0x1000000, 0x0800100, 0x1200801,
                        0x0013C01, 0x0800008, 0x0A00088, 0x0010200,
                        0x0800040, 0x0800280, 0x1801200, 0x1000208, // 10
                        0x0080001, 0x0A00082, 0x0A01008, 0x1000001,
                        0x0A00808, 0x0900001, 0x8010004, 0x0080820,
                        0x0800002, 0x0140002, 0x0008000, 0x0A00090,
                        0x0A00220, 0x0801001, 0x1203200, 0x4800001,
                        0x0011801, 0x1008001, 0x0A04020, 0x4800801,
                        0x0840801, 0x0840020, 0x0013081, 0x0010801,
                        0x0818180, 0x0800180, 0x0A00081, 0x0800001  //17
                },
                {
                        0x00204E4E, 0x00117360, 0x00114840, 0x01040240, // 1
                        0x00164040, 0x001B3240, 0x00064640, 0x015B4013,
                        0x00D93130, 0x00001040, 0x01A52014, 0x00000000,
                        0x00000000, 0x00000000, 0x00000000, 0x00C12040,
                        0x00D0536D, 0x00517740, 0x00B43130, 0x00B22223,
                        0x00C15340, 0x00FD2040, 0x002D1D1D, 0x0008403B,
                        0x00092140, 0x00094061, 0x000A2140, 0x00082140,
                        0x000D7076, 0x010D400D, 0x000A403B, 0x00056D40,
                        0x00100259, 0x010B1340, 0x00242044, 0x010B7840,
                        0x00064002, 0x01FF2008, 0x0008565A, 0x0126403F, // 10
                        0x016C400D, 0x00C12077, 0x00517740, 0x00517740,
                        0x00083240, 0x010C400D, 0x01FF200A, 0x010B3568,
                        0x00117B5A, 0x0021206D, 0x01222034, 0x01015C5B,
                        0x01D03454, 0x00005E5D, 0x010E400D, 0x010E0044,
                        0x00F44E40, 0x009A206D, 0x00F44E5A, 0x00000000,
                        0x00000000, 0x00000000, 0x00000000, 0x00C11D1D,
                        0x00063333, 0x010B403B, 0x01344043, 0x00096A6A,
                        0x000A4443, 0x00792120, 0x01D32047, 0x00081E1E,
                        0x01AF1140, 0x00AB1D1D, 0x0039324C, 0x000B324C,
                        0x0008326D, 0x000D404C, 0x00854D40, 0x00134040, // 20
                        0x0009404C, 0x006D7770, 0x006D7240, 0x01001640,
                        0x00A54C7E, 0x00F44E40, 0x01536900, 0x000A580E,
                        0x003C5262, 0x0005716D, 0x013C4013, 0x00104070,
                        0x00056F6D, 0x00A62070, 0x00106F40, 0x01056F40,
                        0x001F3E3D, 0x0028595A, 0x001E2223, 0x00064B40,
                        0x00524A40, 0x00692120, 0x001B4940, 0x00093240,
                        0x011F0140, 0x00154840, 0x00062423, 0x00062423,
                        0x01057340, 0x015E400D, 0x00095828, 0x00092223,
                        0x00992F40, 0x00982F40, 0x00622040, 0x005D5820,
                        0x00740F40, 0x00B81C20, 0x00D05373, 0x005B205C, // 30
                        0x006D2062, 0x0133200A, 0x010B7D62, 0x00A52120,
                        0x01054072, 0x01494013, 0x01040540, 0x00217362,
                        0x013D6A40, 0x00067840, 0x01AB6C6D, 0x01332014,
                        0x000E7C6C, 0x00050B3F, 0x00C15340, 0x00950853,
                        0x00E0417A, 0x00E04240, 0x00532120, 0x00365562,
                        0x008F1E20, 0x013D1740, 0x004C2120, 0x0170406A,
                        0x00C05340, 0x00061D1D, 0x00814545, 0x00063333,
                        0x00061E1E, 0x00091E1E, 0x00900720, 0x01514078,
                        0x00081D1D, 0x01622206, 0x001E4545, 0x00114060,
                        0x000B2E40, 0x000F2D40, 0x010E1F40, 0x000D7677, // 40
                        0x00D33C40, 0x01D32032, 0x00116E60, 0x011D3440,
                        0x00FF7440, 0x00073240, 0x001B430A, 0x01D32047,
                        0x00113434, 0x001E6E40, 0x00D33C40, 0x00937540,
                        0x00D01E20, 0x00043277, 0x00CA4020, 0x00107F54,
                        0x00212068, 0x000B7840, 0x017C400C, 0x00056F6D,
                        0x01470C40, 0x01716B62, 0x006B2120, 0x00332120,
                        0x006D204C, 0x00E67362, 0x010D0940, 0x00062423,
                        0x001A3A3A, 0x018F406F, 0x0151334C, 0x010D1716,
                        0x01D35340, 0x00D24061, 0x00CA6554, 0x00104064,
                        0x00512223, 0x00782120, 0x00263130, 0x001E3434, // 50
                        0x00193838, 0x00183939, 0x000D6654, 0x010D7A40,
                        0x010E1740, 0x00057340, 0x00B86140, 0x00045263,
                        0x00122773, 0x008F5373, 0x002E5150, 0x0151404C,
                        0x001E3737, 0x00894E40, 0x001E3636, 0x006D563D,
                        0x00E07A41, 0x00E12973, 0x00082640, 0x00062540,
                        0x00D87967, 0x0005565A, 0x0005286C, 0x00762041,
                        0x00952040, 0x008F1D1D, 0x01D35340, 0x008F2040,
                        0x00CC4F4F, 0x00114060, 0x00054040, 0x001E3434,
                        0x01047340, 0x011E3434, 0x00C62C2B, 0x00C53130,
                        0x003E1D1D, 0x01041740, 0x001E3535, 0x00D35353, // 60
                        0x00DE4077, 0x00E24057, 0x00064E68, 0x01E53812,
                        0x00D84067, 0x00064069, 0x000A402A, 0x00EF202A,
                        0x01015C5B, 0x00090F40, 0x00005E5D, 0x010B3613,
                        0x00144740, 0x01176806, 0x000A5A5A, 0x01D3200D  // 64
                }
        },
        {
                {
                    0x0000000, 0x0800001, 0x0040020, 0x1440090, // 1
                        0x0A00081, 0x1000000, 0x1400020, 0x0800008,
                        0x0A03180, 0x1002200, 0x0800400, 0x1418001,
                        0x0080020, 0x0841020, 0x0203100, 0x0203088,
                        0x0A00820, 0x0800120, 0x08001C0, 0x0810081,
                        0x0A00089, 0x0800401, 0x0A010A0, 0x0A01081,
                        0x0818001, 0x1A00220, 0x0201100, 0x0203420,
                        0x0008000, 0x0801020, 0x0201420, 0x0801190,
                        0x0040000, 0x0080820, 0x0800002, 0x0140002,
                        0x0800100, 0x0A03C20, 0x0A00808, 0x0A01008, // 10
                        0x0200540, 0x0601209, 0x0083100, 0x0A03081,
                        0x8800004, 0x0058001, 0x1001280, 0x1008001,
                        0x1200209, 0x4018001, 0x0040002, 0x1000001,
                        0x0010200, 0x0800840, 0x0A01181, 0x4018801,
                        0x0A10181, 0x0800801, 0x0040001, 0x0011190,
                        0x0858001, 0x0040020, 0x3200209, 0x08000C0,
                        0x4000020, 0x0600081, 0x1000000, 0x1000180  // 17
                },
                {
                        0x00386050, 0x005B3F3E, 0x000F5970, 0x00152470, // 1
                        0x000C3D50, 0x0011312F, 0x005B4544, 0x00165050,
                        0x000C3404, 0x005B3F3E, 0x00D40450, 0x00162424,
                        0x000C4962, 0x01FB5250, 0x000D4924, 0x01BB2222,
                        0x00155050, 0x010F5247, 0x00182525, 0x00080505,
                        0x000E041E, 0x00123433, 0x007F6425, 0x007F0D25,
                        0x01650950, 0x01176553, 0x007E2432, 0x00087150,
                        0x007E2455, 0x00135076, 0x00085977, 0x005B4544,
                        0x000C2E26, 0x00310D2E, 0x00100E35, 0x00316B47,
                        0x01381250, 0x0011302E, 0x01385F50, 0x00050250, // 10
                        0x011C0101, 0x00195050, 0x00382C2C, 0x016F2222,
                        0x013A2222, 0x002F6B56, 0x00093D6C, 0x00F04D50,
                        0x000C1750, 0x00074A50, 0x01B45047, 0x003C2020,
                        0x01AA2B6A, 0x00123432, 0x001D4933, 0x0113500C,
                        0x00052556, 0x00087C50, 0x01130000, 0x00142B2B,
                        0x004A1D50, 0x006E5756, 0x00496050, 0x00E57D58,
                        0x011E5D22, 0x01F35F50, 0x00EA0505, 0x001C7A50,
                        0x01080B50, 0x0054244B, 0x000C4050, 0x002A2121,
                        0x00135C5C, 0x000A4650, 0x00152504, 0x009D2B60,
                        0x00064350, 0x00192020, 0x00292C2C, 0x01235C50, // 20
                        0x006D3C3C, 0x0031017D, 0x00092D2D, 0x004E2D2D,
                        0x01596A7E, 0x00E3396E, 0x006E3654, 0x016E6E47,
                        0x00534950, 0x00EE2062, 0x0016226E, 0x00660525,
                        0x00135C5C, 0x000A4241, 0x00383B3B, 0x000C7277,
                        0x00360404, 0x00042020, 0x00100A2E, 0x00155050,
                        0x00532404, 0x0004642B, 0x01843C47, 0x01A35047,
                        0x01847250, 0x015C112F, 0x00080434, 0x00152F23,
                        0x00080505, 0x00906047, 0x0113150C, 0x006D2224,
                        0x00747250, 0x000C632B, 0x00AD672B, 0x000A612E,
                        0x01B97463, 0x00417374, 0x00BD0658, 0x00EA2450, // 30
                        0x00087166, 0x01BD3950, 0x001A2E50, 0x00BD6047,
                        0x00175079, 0x005E6035, 0x000A3847, 0x01067F47,
                        0x008C5251, 0x0013612E, 0x0087602E, 0x005B3F3E,
                        0x00DC2121, 0x00177374, 0x00182525, 0x00286050,
                        0x00064F4E, 0x000C5251, 0x006E2926, 0x008F602F,
                        0x008C502A, 0x00172928, 0x00814F4E, 0x003F534B,
                        0x000F075B, 0x00082525, 0x01E85047, 0x00790505,
                        0x00152F23, 0x0017506A, 0x00095047, 0x00082525,
                        0x00E63A62, 0x00DA0B47, 0x01174150, 0x00182525,
                        0x00090450, 0x01175B50, 0x00094850, 0x001B2F50, // 40
                        0x00806047, 0x000A3720, 0x0010382F, 0x002C0505,
                        0x009B5021, 0x00160505, 0x01ED3A50, 0x00040505,
                        0x00082525, 0x01080F50, 0x01B35047, 0x000D3D4C,
                        0x00180404, 0x01C03A50, 0x00E20421, 0x00287B50,
                        0x00097F26, 0x0013612E, 0x01B6112F, 0x00322425,
                        0x01B81847, 0x00BA714B, 0x00182450, 0x00080505,
                        0x00182525, 0x004F1D24, 0x00736F5C, 0x00A67569,
                        0x00AD2726, 0x01BE5022, 0x000A5E04, 0x00173A62,
                        0x00CB752E, 0x00B11E25, 0x00CB0953, 0x00085068,
                        0x002B2020, 0x01984150, 0x00C77C04, 0x00DA0950, // 50
                        0x00160404, 0x00F56040, 0x00DE0450, 0x01CB1160,
                        0x00CF4950, 0x000A4747, 0x001F210B, 0x00145050,
                        0x01171050, 0x00052075, 0x001D3D37, 0x00365555,
                        0x00130101, 0x01D57424, 0x00D66047, 0x01C47850,
                        0x004D2C2C, 0x01174150, 0x00174847, 0x00C90350,
                        0x000A2760, 0x0019502E, 0x00D72C2C, 0x01174850,
                        0x006C224B, 0x000A495B, 0x00100E35, 0x00312104,
                        0x01C00850, 0x00115A2F, 0x00EA0505, 0x00080574,
                        0x00152F23, 0x005C6050, 0x01C94122, 0x01A42222,
                        0x00DF2847, 0x00C9202E, 0x00A76047, 0x0117502F, // 60
                        0x002E2020, 0x01205048, 0x00F8606D, 0x002D604C,
                        0x00443A62, 0x000D3D2E, 0x015C3950, 0x01625022,
                        0x006E136E, 0x0031602E, 0x01085D1A, 0x010F6F50,
                        0x0017506A, 0x00FB5020, 0x000A3C47, 0x00174D50  // 64
                }
        },
        {
                {
                        0x0000000, 0x0800008, 0x0040020, 0x0800001, // 1
                        0x0800021, 0x0080020, 0x0A00028, 0x0040100,
                        0x4000100, 0x0010100, 0x0A00101, 0x0201089,
                        0x0213201, 0x0800004, 0x0800800, 0x0800820,
                        0x0200088, 0x4810002, 0x0A00820, 0x0800400,
                        0x0801000, 0x0100000, 0x8800004, 0x0008000,
                        0x1400020, 0x0800005, 0x4000020, 0x0A00180,
                        0x0100000, 0x4000001, 0x8241004, 0x0400000,
                        0x0080001, 0x0040001, 0x0212801, 0x0200808,
                        0x0800000, 0x0010020, 0x0A00808, 0x0040090, // 10
                        0x0A01008, 0x0800401, 0x0A00081, 0x0A01081,
                        0x0803400, 0x0A01001, 0x0A11801, 0x0011001,
                        0x0A10801, 0x0213801, 0x0098001, 0x0818001,
                        0x0800420, 0x0880090, 0x0203C08, 0x0200809,
                        0x0A00089, 0x0203090, 0x0840090, 0x0810002,
                        0x0210801, 0x0210081, 0x0010000, 0x0200090,
                        0x0210081, 0x0212801, 0x0A01020, 0x0A01020  // 17
                },
                {
                        0x0070000, 0x0060040, 0x0076A2F, 0x00B4C00, // 1
                        0x0090000, 0x00B4D00, 0x0090000, 0x0055300,
                        0x0090000, 0x00B5400, 0x0090000, 0x0054600,
                        0x0061000, 0x00B4800, 0x0065657, 0x0057300,
                        0x0090000, 0x0075655, 0x0071700, 0x0060040,
                        0x0070000, 0x0070000, 0x0074444, 0x00C4545,
                        0x0280058, 0x0682825, 0x08A0000, 0x0280059,
                        0x0800058, 0x0800059, 0x04D5F5F, 0x0FB2F22,
                        0x0FB2F21, 0x0F80000, 0x0FB2F20, 0x0940000,
                        0x0B80059, 0x0B80058, 0x0830000, 0x03D4343, // 10
                        0x0075E5E, 0x0075B00, 0x0695900, 0x007002B,
                        0x0070028, 0x0070003, 0x0070028, 0x0070052,
                        0x0070015, 0x00C0037, 0x00F5C00, 0x0075C01,
                        0x0075D5D, 0x007285F, 0x0DC585B, 0x00C005C,
                        0x0680000, 0x0070A0A, 0x0075B59, 0x0070254,
                        0x02A5F5F, 0x0075F5F, 0x00B0076, 0x0077700,
                        0x00B0039, 0x0063A2A, 0x01B3B2A, 0x0682828,
                        0x0680000, 0x0F05800, 0x00B003D, 0x04A0000,
                        0x0053200, 0x0502800, 0x0054E00, 0x0560000,
                        0x0530000, 0x00B0076, 0x0077700, 0x03E5F5F, // 20
                        0x0DC0058, 0x0050032, 0x0682828, 0x005002A,
                        0x0682C2C, 0x0682828, 0x0050039, 0x0682828,
                        0x0682C2C, 0x0CA0025, 0x0070013, 0x0070066,
                        0x0070014, 0x0070066, 0x0070014, 0x0F6005F,
                        0x00B3E00, 0x0065300, 0x00B4E00, 0x0065300,
                        0x0063B58, 0x0052A00, 0x0070058, 0x0184343,
                        0x0FC7576, 0x00A2828, 0x0052A00, 0x0065300,
                        0x00C0000, 0x0180000, 0x0682F2F, 0x0053C00,
                        0x0065300, 0x00C0000, 0x0182F2F, 0x0680000,
                        0x007042E, 0x0051600, 0x07A0000, 0x0070447, // 30
                        0x00B164B, 0x0770000, 0x00C3119, 0x0180000,
                        0x007005D, 0x0DC585F, 0x0830000, 0x0680000,
                        0x0695E5E, 0x0830000, 0x0680000, 0x00A0009,
                        0x00B0016, 0x00B0061, 0x0185A5A, 0x0075866,
                        0x0F00900, 0x0840004, 0x0052F26, 0x068002F,
                        0x0680027, 0x0056D00, 0x0180000, 0x0920000,
                        0x0F00959, 0x0180000, 0x00A0000, 0x0B50015,
                        0x0070011, 0x0070052, 0x0070066, 0x0070001,
                        0x0070001, 0x0070066, 0x0070001, 0x0070066,
                        0x0070001, 0x0070001, 0x0070066, 0x0070001, // 40
                        0x0070066, 0x0070002, 0x0070066, 0x0070001,
                        0x0075D5D, 0x0070052, 0x0075D5D, 0x0075D5D,
                        0x0590003, 0x00A5A00, 0x00B2A00, 0x01C7400,
                        0x00B3F00, 0x0185E00, 0x00B7458, 0x0B2005F,
                        0x0F00947, 0x0AE0000, 0x00B5E63, 0x0090000,
                        0x0186B2C, 0x00C006E, 0x0180000, 0x0180001,
                        0x0072828, 0x00B3000, 0x0680000, 0x00C3636,
                        0x0C10000, 0x0F07259, 0x0A90000, 0x0C45F00,
                        0x0073131, 0x0A95A5A, 0x0C45A5A, 0x0680000,
                        0x00A0000, 0x0690059, 0x0CA2C00, 0x0DC5931, // 50
                        0x0DC596B, 0x08D0000, 0x00A5A5A, 0x007000E,
                        0x0072E2E, 0x0074242, 0x0073334, 0x00B6265,
                        0x0DB5E5E, 0x0070064, 0x007075F, 0x0075F51,
                        0x00B1A03, 0x00F0051, 0x0D40068, 0x0075F5F,
                        0x0070052, 0x0070065, 0x0CF0038, 0x0180067,
                        0x00A4242, 0x005004E, 0x0070051, 0x0066000,
                        0x0065300, 0x005004F, 0x0065300, 0x0064650,
                        0x005004F, 0x0070050, 0x0070059, 0x0070052,
                        0x01B353E, 0x005002A, 0x0070058, 0x007000E,
                        0x0063B51, 0x005004E, 0x0075800, 0x0184343, // 60
                        0x00A4242, 0x0066000, 0x0063B00, 0x0070000,
                        0x0075000, 0x0605259, 0x0837125, 0x0680000,
                        0x0070023, 0x0070024, 0x0072F29, 0x0070041,
                        0x1060040, 0x0074900, 0x0075F5F, 0x0094A4A  // 64
                }
        }
};

/*
const uint8_t* IK1302_M_START = &ringM[42+42];
const uint8_t* IK1303_M_START = &ringM[42];
const uint8_t* IK1306_M_START = &ringM[0];
*/
IK1302  m_IK1302;
static  IK1303  m_IK1303;
static  IK1306  m_IK1306;

#if MK61_CORE_PACKED_AMK
static inline core_packed_amk::Selection select_amk_lanes(
    u8 ik1302, u8 ik1303, u8 ik1306) {
#if !defined(ARDUINO)
  if(!packed_amk_is_enabled) {
    return core_packed_amk::select_reference(
        ik1302, ik1303, ik1306,
        m_IK1302.L != 0, m_IK1303.L != 0, m_IK1306.L != 0);
  }
#endif
  return core_packed_amk::select(
      ik1302, ik1303, ik1306,
      m_IK1302.L != 0, m_IK1303.L != 0, m_IK1306.L != 0);
}

static inline core_packed_amk::Selection select_amk_lanes_1302_1303(
    u8 ik1302, u8 ik1303) {
#if !defined(ARDUINO)
  if(!packed_amk_is_enabled) {
    return core_packed_amk::select_reference(
        ik1302, ik1303, 0,
        m_IK1302.L != 0, m_IK1303.L != 0, true);
  }
#endif
  return core_packed_amk::select(
      ik1302, ik1303, 0,
      m_IK1302.L != 0, m_IK1303.L != 0, true);
}
#endif

#if MK61_CORE_NATIVE_HOT_PATHS
static inline void __attribute__((always_inline)) native_ik1306_wait_tick(
    mtick_t signal, usize j) {
  // Body 40 polls eight ring nibbles with 3B, then reduces the last nibble
  // to a wake bit with 12/14. Keep every ring read on its original microtick.
  m_IK1306.AMK = 0;
  m_IK1306.P = 0;
  if(j == 1 || j == 4) {
    m_IK1306.AMK = 0x3B;
    m_IK1306.S = m_IK1306.pM[signal];
    if(m_IK1306.MOD == 0) m_IK1306.R[signal] = m_IK1306.S;
  } else if(j == 6) {
    m_IK1306.AMK = 0x12;
    const u32 sum = m_IK1306.S + 1U;
    m_IK1306.P = sum >> 4;
    m_IK1306.L = m_IK1306.P & 1U;
    m_IK1306.S = sum & 15U;
  } else if(j == 7) {
    m_IK1306.AMK = 0x14;
    m_IK1306.S = m_IK1306.L;
  }
}

static inline void native_ik1306_zero_body(core_61::NativeHotPath path) {
  // AND_AMK body 00 contains only microinstruction 00. Every bit-serial tick
  // therefore clears P and leaves all persistent data untouched; the final
  // AMK latch is 00 as well.
  m_IK1306.AMK = 0;
  m_IK1306.P = 0;
  count_native_hot_path(path);
}

static inline void native_ik1306_region3_06(void) {
  // Closed form of 2A,02,00,2D,02,00 over microticks 36..41: add the
  // current S nibble to the two-nibble ASP register, then expose the updated
  // high nibble/carry in S/L. Capture S before the first microinstruction
  // replaces it with the low result.
  const u32 addend = m_IK1306.S;
  const u32 low = m_IK1306.R[36] + addend;
  m_IK1306.R[36] = low & 0x0FU;
  const u32 high = m_IK1306.R[39] + ((low >> 4) & 1U);
  m_IK1306.R[39] = high & 0x0FU;
  m_IK1306.L = (high >> 4) & 1U;
  m_IK1306.S = high & 0x0FU;
  m_IK1306.P = 0;
  m_IK1306.AMK = 0;
  count_native_hot_path(core_61::NativeHotPath::IK1306_ADD_S_REGION3);
}

static inline void native_ik1306_region3_07(void) {
  // Closed form of 03,12,05,2D,02,00 over microticks 36..41: increment the
  // two-nibble ASP register and expose its high nibble/carry in S/L.
  const u32 low = m_IK1306.R[36] + 1U;
  m_IK1306.R[36] = low & 0x0FU;
  const u32 high = m_IK1306.R[39] + ((low >> 4) & 1U);
  m_IK1306.R[39] = high & 0x0FU;
  m_IK1306.L = (high >> 4) & 1U;
  m_IK1306.S = high & 0x0FU;
  m_IK1306.P = 0;
  m_IK1306.AMK = 0;
  count_native_hot_path(core_61::NativeHotPath::IK1306_ADVANCE_REGION3);
}

static inline void native_ik1306_region3_09(void) {
  // Closed form of 0E,02,00,24,02,00 over microticks 36..41: load ASP=01.
  // L is deliberately preserved, matching the bit-serial microinstructions.
  m_IK1306.R[36] = 1;
  m_IK1306.R[39] = 0;
  m_IK1306.S = 0;
  m_IK1306.P = 0;
  m_IK1306.AMK = 0;
  count_native_hot_path(core_61::NativeHotPath::IK1306_RESET_REGION3);
}
#endif

namespace {

static constexpr u8 ROM_CHIP_COUNT = 3;
static constexpr u8 INVALID_HOOK_SLOT = 0xFF;
static constexpr usize HOOK_TARGET_COUNT = 256;
static constexpr usize HOOK_TARGET_BITMAP_SIZE = HOOK_TARGET_COUNT / 8U;
// Одно место зарезервировано встроенным обработчиком случайных чисел MK61s.
// Внешним вызывающим сторонам всегда доступна вся ёмкость из mk61emu_core.h.
static constexpr usize ROM_COMMAND_HOOK_SLOT_COUNT =
    core_61::ROM_COMMAND_HOOK_CAPACITY + 1;
static constexpr usize MK61_COMMAND_HOOK_SLOT_COUNT =
    core_61::MK61_COMMAND_HOOK_CAPACITY + 1;

struct RomCommandHookSlot {
  core_61::RomCommandHook callback;
  void* user_data;
  u32 generation;
  u8 address;
  u8 chip;
  u8 next;
  u8 flags;
};

struct Mk61CommandHookSlot {
  core_61::Mk61CommandHook callback;
  void* user_data;
  u32 generation;
  u8 opcode;
  u8 phase;
  u8 next;
  u8 flags;
};

struct ActiveMk61Command {
  bool active;
  core_61::Mk61CommandSource source;
  u8 opcode;
  u8 executed_opcode;
  u32 sequence;
};

static constexpr u8 HOOK_INTERNAL = 0x01;
static_assert(ROM_COMMAND_HOOK_SLOT_COUNT < INVALID_HOOK_SLOT,
              "ROM command hook slots must fit in their linked-list index");
static_assert(MK61_COMMAND_HOOK_SLOT_COUNT < INVALID_HOOK_SLOT,
              "MK-61 command hook slots must fit in their linked-list index");
static RomCommandHookSlot rom_command_hooks[ROM_COMMAND_HOOK_SLOT_COUNT] = {};
static u8 rom_command_hook_head = INVALID_HOOK_SLOT;
static u8 rom_command_hook_tail = INVALID_HOOK_SLOT;
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
static volatile u8
    rom_command_hook_targets[ROM_CHIP_COUNT][HOOK_TARGET_BITMAP_SIZE] = {};
#else
static u8 rom_command_hook_targets[ROM_CHIP_COUNT][HOOK_TARGET_BITMAP_SIZE] = {};
#endif
static u8 rom_command_hook_dispatch_depth;
static usize public_rom_command_hook_count;
static core_61::RomCommandHookHandle random_rom_command_hook =
    core_61::INVALID_ROM_COMMAND_HOOK;

static Mk61CommandHookSlot mk61_command_hooks[MK61_COMMAND_HOOK_SLOT_COUNT] = {};
static u8 mk61_command_hook_head = INVALID_HOOK_SLOT;
static u8 mk61_command_hook_tail = INVALID_HOOK_SLOT;
// Горячему декодеру важно только наличие хотя бы одного hook для opcode.
// Фаза остается в слотах реестра и проверяется уже при редком полном dispatch.
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
static volatile u8
    mk61_command_hook_targets[HOOK_TARGET_BITMAP_SIZE] = {};
#else
static u8 mk61_command_hook_targets[HOOK_TARGET_BITMAP_SIZE] = {};
#endif
static u8 mk61_command_hook_dispatch_depth;
static usize public_mk61_command_hook_count;
static core_61::Mk61CommandHookHandle random_mk61_command_hook =
    core_61::INVALID_MK61_COMMAND_HOOK;

static ActiveMk61Command active_mk61_command = {};
static bool keyboard_command_complete_pending;
static u32 mk61_command_sequence;
static core_61::Mk61ProgramBoundaryHook mk61_program_boundary_hook;
static void* mk61_program_boundary_user_data;
static bool mk61_program_boundary_dispatching;
static bool mk61_program_boundary_yielded;
// One-shot operand of a direct jump/conditional branch. Zero means none;
// otherwise store address + 1 so reset state needs no nonzero initializer.
static u8 mk61_jump_operand;
static constexpr u8 MK61_CALL_OPERAND_DEPTH = 5;
static u8 mk61_call_operand_addresses[MK61_CALL_OPERAND_DEPTH];
static u8 mk61_call_operand_visits[MK61_CALL_OPERAND_DEPTH];
static u8 mk61_call_operand_depth;

static bool valid_rom_chip(core_61::RomChip chip) {
  return (u8) chip < ROM_CHIP_COUNT;
}

#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
static inline volatile u32* __attribute__((always_inline))
rom_command_hook_target_bits(void) {
  return stm32_sram_bit_band::alias_base(
      &rom_command_hook_targets[0][0]);
}

static inline usize __attribute__((always_inline))
rom_command_hook_target_bit(core_61::RomChip chip, u8 address) {
  return (usize) (u8) chip * HOOK_TARGET_COUNT + address;
}
#endif

static void mark_hook_target(core_61::RomChip chip, u8 address) {
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  rom_command_hook_target_bits()[
      rom_command_hook_target_bit(chip, address)] = 1U;
#else
  rom_command_hook_targets[(u8) chip][address >> 3] |= (u8) (1U << (address & 7U));
#endif
}

static inline bool __attribute__((always_inline)) has_hook_target(
    core_61::RomChip chip, u8 address) {
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  return rom_command_hook_target_bits()[
      rom_command_hook_target_bit(chip, address)] != 0;
#else
  return (rom_command_hook_targets[(u8) chip][address >> 3] &
          (u8) (1U << (address & 7U))) != 0;
#endif
}

static void clear_hook_target_if_unused(core_61::RomChip chip, u8 address) {
  for(const RomCommandHookSlot& slot : rom_command_hooks) {
    if(slot.callback != nullptr && slot.chip == (u8) chip && slot.address == address) return;
  }
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  rom_command_hook_target_bits()[
      rom_command_hook_target_bit(chip, address)] = 0U;
#else
  rom_command_hook_targets[(u8) chip][address >> 3] &=
      (u8) ~(1U << (address & 7U));
#endif
}

static core_61::RomCommandHookHandle make_hook_handle(usize slot_index, u32 generation) {
  return (generation << 8) | (u32) (slot_index + 1U);
}

static core_61::RomCommandHookHandle add_rom_command_hook(
    core_61::RomChip chip,
    u8 address,
    core_61::RomCommandHook callback,
    void* user_data,
    bool internal) {
  if(callback == nullptr || !valid_rom_chip(chip) || rom_command_hook_dispatch_depth != 0) {
    return core_61::INVALID_ROM_COMMAND_HOOK;
  }
  if(!internal && public_rom_command_hook_count >= core_61::ROM_COMMAND_HOOK_CAPACITY) {
    return core_61::INVALID_ROM_COMMAND_HOOK;
  }

  for(usize i = 0; i < ROM_COMMAND_HOOK_SLOT_COUNT; i++) {
    RomCommandHookSlot& slot = rom_command_hooks[i];
    if(slot.callback != nullptr) continue;

    slot.generation = (slot.generation + 1U) & 0x00FFFFFFUL;
    if(slot.generation == 0) slot.generation = 1;
    slot.callback = callback;
    slot.user_data = user_data;
    slot.address = address;
    slot.chip = (u8) chip;
    slot.next = INVALID_HOOK_SLOT;
    slot.flags = internal ? HOOK_INTERNAL : 0;

    // Сначала вызываются внутренние обработчики. Внешние сохраняют порядок регистрации.
    if(internal) {
      slot.next = rom_command_hook_head;
      rom_command_hook_head = (u8) i;
      if(rom_command_hook_tail == INVALID_HOOK_SLOT) rom_command_hook_tail = (u8) i;
    } else {
      if(rom_command_hook_tail == INVALID_HOOK_SLOT) {
        rom_command_hook_head = (u8) i;
      } else {
        rom_command_hooks[rom_command_hook_tail].next = (u8) i;
      }
      rom_command_hook_tail = (u8) i;
      public_rom_command_hook_count++;
    }

    mark_hook_target(chip, address);
    return make_hook_handle(i, slot.generation);
  }
  return core_61::INVALID_ROM_COMMAND_HOOK;
}

static bool remove_rom_command_hook(core_61::RomCommandHookHandle handle, bool internal) {
  if(handle == core_61::INVALID_ROM_COMMAND_HOOK || rom_command_hook_dispatch_depth != 0) {
    return false;
  }

  const u8 encoded_slot = (u8) handle;
  if(encoded_slot == 0) return false;
  const usize slot_index = (usize) encoded_slot - 1U;
  if(slot_index >= ROM_COMMAND_HOOK_SLOT_COUNT) return false;

  RomCommandHookSlot& slot = rom_command_hooks[slot_index];
  const u32 generation = handle >> 8;
  if(slot.callback == nullptr || slot.generation != generation) return false;
  if(((slot.flags & HOOK_INTERNAL) != 0) != internal) return false;

  u8 previous = INVALID_HOOK_SLOT;
  u8 current = rom_command_hook_head;
  while(current != INVALID_HOOK_SLOT && current != slot_index) {
    previous = current;
    current = rom_command_hooks[current].next;
  }
  if(current == INVALID_HOOK_SLOT) return false;

  if(previous == INVALID_HOOK_SLOT) rom_command_hook_head = slot.next;
  else rom_command_hooks[previous].next = slot.next;
  if(rom_command_hook_tail == slot_index) rom_command_hook_tail = previous;

  const core_61::RomChip chip = (core_61::RomChip) slot.chip;
  const u8 address = slot.address;
  if(!internal) public_rom_command_hook_count--;
  slot.callback = nullptr;
  slot.user_data = nullptr;
  slot.address = 0;
  slot.chip = 0;
  slot.next = INVALID_HOOK_SLOT;
  slot.flags = 0;
  clear_hook_target_if_unused(chip, address);
  return true;
}

static u8 dispatch_rom_command_hooks(
    core_61::RomChip chip, u8 address, u8* r, u8* st) {
  core_61::RomCommandHookContext context = {chip, address, address, r, st};
  rom_command_hook_dispatch_depth++;
  for(u8 slot_index = rom_command_hook_head;
      slot_index != INVALID_HOOK_SLOT;
      slot_index = rom_command_hooks[slot_index].next) {
    RomCommandHookSlot& slot = rom_command_hooks[slot_index];
    if(slot.callback != nullptr && slot.chip == (u8) chip && slot.address == address) {
      slot.callback(context, slot.user_data);
    }
  }
  rom_command_hook_dispatch_depth--;
  return context.replacement_address;
}

static inline u8 __attribute__((always_inline)) apply_rom_command_hooks(
    core_61::RomChip chip, u8 address, u8* r, u8* st) {
  if(!has_hook_target(chip, address)) return address;
  return dispatch_rom_command_hooks(chip, address, r, st);
}

static bool valid_mk61_command_phase(core_61::Mk61CommandHookPhase phase) {
  return phase == core_61::Mk61CommandHookPhase::BEFORE_EXECUTE ||
         phase == core_61::Mk61CommandHookPhase::AFTER_EXECUTE;
}

#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
static inline volatile u32* __attribute__((always_inline))
mk61_command_hook_target_bits(void) {
  return stm32_sram_bit_band::alias_base(
      &mk61_command_hook_targets[0]);
}
#endif

static void mark_mk61_command_target(u8 opcode) {
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  mk61_command_hook_target_bits()[opcode] = 1U;
#else
  mk61_command_hook_targets[opcode >> 3] |=
      (u8) (1U << (opcode & 7U));
#endif
}

static inline bool __attribute__((always_inline)) has_mk61_command_target(
    u8 opcode) {
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  return mk61_command_hook_target_bits()[opcode] != 0;
#else
  return (mk61_command_hook_targets[opcode >> 3] &
          (u8) (1U << (opcode & 7U))) != 0;
#endif
}

static void clear_mk61_command_target_if_unused(u8 opcode) {
  for(const Mk61CommandHookSlot& slot : mk61_command_hooks) {
    if(slot.callback != nullptr && slot.opcode == opcode) return;
  }
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  mk61_command_hook_target_bits()[opcode] = 0U;
#else
  mk61_command_hook_targets[opcode >> 3] &=
      (u8) ~(1U << (opcode & 7U));
#endif
}

static core_61::Mk61CommandHookHandle make_mk61_command_hook_handle(
    usize slot_index, u32 generation) {
  return (generation << 8) | (u32) (slot_index + 1U);
}

static core_61::Mk61CommandHookHandle add_mk61_command_hook(
    u8 opcode,
    core_61::Mk61CommandHookPhase phase,
    core_61::Mk61CommandHook callback,
    void* user_data,
    bool internal) {
  if(callback == nullptr || !valid_mk61_command_phase(phase) ||
     mk61_command_hook_dispatch_depth != 0) {
    return core_61::INVALID_MK61_COMMAND_HOOK;
  }
  if(!internal && public_mk61_command_hook_count >= core_61::MK61_COMMAND_HOOK_CAPACITY) {
    return core_61::INVALID_MK61_COMMAND_HOOK;
  }

  for(usize i = 0; i < MK61_COMMAND_HOOK_SLOT_COUNT; i++) {
    Mk61CommandHookSlot& slot = mk61_command_hooks[i];
    if(slot.callback != nullptr) continue;

    slot.generation = (slot.generation + 1U) & 0x00FFFFFFUL;
    if(slot.generation == 0) slot.generation = 1;
    slot.callback = callback;
    slot.user_data = user_data;
    slot.opcode = opcode;
    slot.phase = (u8) phase;
    slot.next = INVALID_HOOK_SLOT;
    slot.flags = internal ? HOOK_INTERNAL : 0;

    if(mk61_command_hook_tail == INVALID_HOOK_SLOT) {
      mk61_command_hook_head = (u8) i;
    } else {
      mk61_command_hooks[mk61_command_hook_tail].next = (u8) i;
    }
    mk61_command_hook_tail = (u8) i;
    if(!internal) public_mk61_command_hook_count++;
    mark_mk61_command_target(opcode);
    return make_mk61_command_hook_handle(i, slot.generation);
  }
  return core_61::INVALID_MK61_COMMAND_HOOK;
}

static bool remove_mk61_command_hook(
    core_61::Mk61CommandHookHandle handle, bool internal) {
  if(handle == core_61::INVALID_MK61_COMMAND_HOOK ||
     mk61_command_hook_dispatch_depth != 0) {
    return false;
  }

  const u8 encoded_slot = (u8) handle;
  if(encoded_slot == 0) return false;
  const usize slot_index = (usize) encoded_slot - 1U;
  if(slot_index >= MK61_COMMAND_HOOK_SLOT_COUNT) return false;

  Mk61CommandHookSlot& slot = mk61_command_hooks[slot_index];
  const u32 generation = handle >> 8;
  if(slot.callback == nullptr || slot.generation != generation) return false;
  if(((slot.flags & HOOK_INTERNAL) != 0) != internal) return false;

  u8 previous = INVALID_HOOK_SLOT;
  u8 current = mk61_command_hook_head;
  while(current != INVALID_HOOK_SLOT && current != slot_index) {
    previous = current;
    current = mk61_command_hooks[current].next;
  }
  if(current == INVALID_HOOK_SLOT) return false;

  if(previous == INVALID_HOOK_SLOT) mk61_command_hook_head = slot.next;
  else mk61_command_hooks[previous].next = slot.next;
  if(mk61_command_hook_tail == slot_index) mk61_command_hook_tail = previous;

  const u8 opcode = slot.opcode;
  if(!internal) public_mk61_command_hook_count--;
  slot.callback = nullptr;
  slot.user_data = nullptr;
  slot.opcode = 0;
  slot.phase = 0;
  slot.next = INVALID_HOOK_SLOT;
  slot.flags = 0;
  clear_mk61_command_target_if_unused(opcode);
  return true;
}

static u8 dispatch_mk61_command_before(
    u8 opcode, core_61::Mk61CommandSource source, u32 sequence) {
  core_61::Mk61CommandHookContext context = {
      core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
      source,
      opcode,
      opcode,
      sequence
  };

  mk61_command_hook_dispatch_depth++;
  // Внешние обратные вызовы сопоставляются с фактически выданной командой.
  // Встроенные вызываются затем и сопоставляются с итоговой заменой, поэтому
  // замена любого кода на 3B включает улучшенный ГСЧ, а замена 3B — нет.
  for(u8 pass = 0; pass < 2; pass++) {
    const bool internal = pass != 0;
    for(u8 slot_index = mk61_command_hook_head;
        slot_index != INVALID_HOOK_SLOT;
        slot_index = mk61_command_hooks[slot_index].next) {
      Mk61CommandHookSlot& slot = mk61_command_hooks[slot_index];
      if(slot.callback == nullptr ||
         ((slot.flags & HOOK_INTERNAL) != 0) != internal ||
         slot.phase != (u8) core_61::Mk61CommandHookPhase::BEFORE_EXECUTE) {
        continue;
      }
      const u8 target = internal ? context.replacement_opcode : opcode;
      if(slot.opcode != target) continue;
      slot.callback(context, slot.user_data);
      // В фазе BEFORE разрешено изменять только replacement_opcode.
      context.phase = core_61::Mk61CommandHookPhase::BEFORE_EXECUTE;
      context.source = source;
      context.opcode = opcode;
      context.sequence = sequence;
    }
  }
  mk61_command_hook_dispatch_depth--;
  return context.replacement_opcode;
}

static void dispatch_mk61_command_after(const ActiveMk61Command& command) {
  core_61::Mk61CommandHookContext context = {
      core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
      command.source,
      command.opcode,
      command.executed_opcode,
      command.sequence
  };

  mk61_command_hook_dispatch_depth++;
  for(u8 pass = 0; pass < 2; pass++) {
    const bool internal = pass != 0;
    for(u8 slot_index = mk61_command_hook_head;
        slot_index != INVALID_HOOK_SLOT;
        slot_index = mk61_command_hooks[slot_index].next) {
      Mk61CommandHookSlot& slot = mk61_command_hooks[slot_index];
      if(slot.callback == nullptr ||
         ((slot.flags & HOOK_INTERNAL) != 0) != internal ||
         slot.phase != (u8) core_61::Mk61CommandHookPhase::AFTER_EXECUTE) {
        continue;
      }
      const u8 target = internal ? command.executed_opcode : command.opcode;
      if(slot.opcode != target) continue;
      slot.callback(context, slot.user_data);
      // На уровне диспетчеризации фаза AFTER предназначена только для наблюдения.
      // Обратный вызов всё ещё может менять видимое калькулятору состояние через
      // обычный API регистров.
      context.phase = core_61::Mk61CommandHookPhase::AFTER_EXECUTE;
      context.source = command.source;
      context.opcode = command.opcode;
      context.replacement_opcode = command.executed_opcode;
      context.sequence = command.sequence;
    }
  }
  mk61_command_hook_dispatch_depth--;
}

static void finish_active_mk61_command(void) {
  if(!active_mk61_command.active) return;
  const ActiveMk61Command completed = active_mk61_command;
  active_mk61_command = {};
  keyboard_command_complete_pending = false;
  external_random_pending = false;
  dispatch_mk61_command_after(completed);
}

static constexpr usize MK61_TETRADES_PER_PAGE = 14U;
static constexpr usize MK61_NUMERIC_TETRADES = 12U;
static constexpr usize EXTENDED_BANK_COUNT =
    (core_61::EXTENDED_ADDRESS_LIMIT + core_61::MAX_PROGRAM_STEP - 1U) /
    core_61::MAX_PROGRAM_STEP;
// Keep the same bounded SRAM footprint on F401 and F411. A slot can hold any
// one of the 90 addressable banks; the active bank also needs a backing slot.
static constexpr usize EXTENDED_BANK_SLOT_COUNT = 32;
static constexpr u8 EXTENDED_RETURN_DEPTH = 64;
static const char EXTENDED_ASCII_DIGITS[] = "0123456789-LCGE ";
static const usize indicator_pos[12] =
    {24, 21, 18, 15, 12, 9, 6, 3, 0, 33, 30, 27};

struct ExtendedProgramState {
  u8* banks[EXTENDED_BANK_COUNT];
  u16 return_addresses[EXTENDED_RETURN_DEPTH];
  // Address + 1. Flags: 8000 display strobe; 4000 target after a ROM FL.
  u16 pending_prefix;
  u8 active_bank;
  u8 bank_slots_used;
  u8 return_depth;
  u8 cursor;
  u8 segment_masks[core_61::EXTENDED_DISPLAY_CELLS];
  u8 held_digits[core_61::EXTENDED_DISPLAY_CELLS];
  u8 held_comma;
  bool auto_display;
  bool segment_display;
  bool numeric_strobe_pending;
  bool error;
  u32 display_revision;
};

static ExtendedProgramState extended_program = {};
// newlib's heap cannot grow while the C6 staging overlay is leased. Program
// banks are calculator state, so they must not depend on that transient heap.
static u8 extended_bank_slots[EXTENDED_BANK_SLOT_COUNT]
                             [core_61::CODE_PAGE_BUFFER_SIZE];

static u8* ensure_extended_bank(u8 bank) {
  if(bank >= EXTENDED_BANK_COUNT) return nullptr;
  if(extended_program.banks[bank] != nullptr) return extended_program.banks[bank];
  if(extended_program.bank_slots_used >= EXTENDED_BANK_SLOT_COUNT)
    return nullptr;
  u8* page = extended_bank_slots[extended_program.bank_slots_used++];
  // Banks are also used as register snapshots and lookup tables. Their
  // unwritten bytes have the same zero value as ordinary cleared memory.
  memset(page, 0, core_61::CODE_PAGE_BUFFER_SIZE);
  extended_program.banks[bank] = page;
  return page;
}

static bool switch_extended_bank(u8 bank) {
  if(bank >= EXTENDED_BANK_COUNT) return false;
  if(bank == extended_program.active_bank) return true;
  u8* saved = ensure_extended_bank(extended_program.active_bank);
  if(saved == nullptr) return false;
  u8* incoming = ensure_extended_bank(bank);
  if(incoming == nullptr) return false;
  // Both operations touch only the program track; data registers and Ms stay
  // live across bank switches.  In particular, K2 exchanges this active bank.
  core_61::get_code_page(saved);
  core_61::set_code_page(incoming);
  extended_program.active_bank = bank;
  return true;
}

static bool set_extended_next_pc(u16 absolute) {
  if(absolute >= core_61::EXTENDED_ADDRESS_LIMIT) return false;
  const u8 bank = (u8) (absolute / core_61::MAX_PROGRAM_STEP);
  const u8 offset = (u8) (absolute % core_61::MAX_PROGRAM_STEP);
  if(!switch_extended_bank(bank)) return false;
  core_61::set_IP((u8) ((offset + core_61::MAX_PROGRAM_STEP - 1U) %
                         core_61::MAX_PROGRAM_STEP));
  return true;
}

static bool parse_unsigned_mk61_word(const char text[15], u32 limit,
                                     u32& output) {
  if(text == nullptr || text[0] != ' ') return false;
  u32 mantissa = 0;
  for(u8 index = 0; index < 8; index++) {
    const char digit = text[index == 0 ? 1 : index + 2];
    if(digit < '0' || digit > '9') return false;
    mantissa = mantissa * 10U + (u32) (digit - '0');
  }
  if(text[12] < '0' || text[12] > '9' ||
     text[13] < '0' || text[13] > '9') return false;
  int exponent = (text[12] - '0') * 10 + (text[13] - '0');
  if(text[11] == '-') exponent = -exponent;
  else if(text[11] != ' ') return false;
  if(exponent < 7) {
    for(int index = exponent; index < 7; index++) {
      if(mantissa % 10U != 0) return false;
      mantissa /= 10U;
    }
  } else {
    for(int index = 7; index < exponent; index++) {
      if(mantissa >= limit || mantissa > (u32) (limit - 1U) / 10U)
        return false;
      mantissa *= 10U;
    }
  }
  if(mantissa >= limit) return false;
  output = mantissa;
  return true;
}

static bool read_x_unsigned(u16 limit, u16& output) {
  char text[15] = {};
  read_stack_register(stack::X, text, EXTENDED_ASCII_DIGITS);
  u32 value = 0;
  if(!parse_unsigned_mk61_word(text, limit, value)) return false;
  output = (u16) value;
  return true;
}

static bool read_register_unsigned32(u8 reg, u32 limit, u32& output) {
  char text[15] = {};
  MK61Emu_ReadRegister(reg, text, EXTENDED_ASCII_DIGITS);
  return parse_unsigned_mk61_word(text, limit, output);
}

static bool read_register_unsigned(u8 reg, u16 limit, u16& output) {
  u32 value = 0;
  if(!read_register_unsigned32(reg, limit, value)) return false;
  output = (u16) value;
  return true;
}

static void write_register_unsigned(u8 reg, u32 value) {
  const usize base = (usize) reg * MK61_MEMORY_PAGE_TETRADES;
  u8 exponent = 0;
  u32 scaled = value;
  while(scaled >= 10U) { scaled /= 10U; exponent++; }
  char digits[8] = {'0','0','0','0','0','0','0','0'};
  if(value != 0) {
    for(int index = (int) exponent; index >= 0; index--) {
      digits[index] = (char) ('0' + value % 10U);
      value /= 10U;
    }
  }
  for(u8 index = 0; index < 8; index++)
    ringM[base + 21U - (usize) index * 3U] = (u8) (digits[index] - '0');
  ringM[base + 24] = 0;
  ringM[base + 27] = exponent % 10U;
  ringM[base + 30] = exponent / 10U;
  ringM[base + 33] = 0;
}

static void capture_extended_indicator(void) {
  for(u8 index = 0; index < core_61::EXTENDED_DISPLAY_CELLS; index++)
    extended_program.held_digits[index] = m_IK1302.R[indicator_pos[index]];
  extended_program.held_comma = (u8) m_IK1302.comma;
}

static bool capture_x_for_numeric_display(void) {
  char value[15] = {};
  u8 digits[core_61::EXTENDED_DISPLAY_CELLS] = {};
  read_stack_register(stack::X, value, EXTENDED_ASCII_DIGITS);
  if((value[0] != ' ' && value[0] != '-') ||
     (value[11] != ' ' && value[11] != '-')) return false;
  digits[0] = value[0] == '-' ? 10U : 15U;
  for(u8 index = 1; index <= 8; ++index) {
    const char digit = value[index == 1 ? 1 : index + 1];
    if(digit < '0' || digit > '9') return false;
    digits[index] = (u8) (digit - '0');
  }
  digits[9] = value[11] == '-' ? 10U : 15U;
  for(u8 index = 10; index < 12; ++index) {
    const char digit = value[index + 2];
    if(digit < '0' || digit > '9') return false;
    digits[index] = (u8) (digit - '0');
  }
  memcpy(extended_program.held_digits, digits, sizeof(digits));
  extended_program.held_comma = 8; // after the first mantissa digit
  extended_program.numeric_strobe_pending = true;
  extended_program.display_revision++;
  return true;
}

static bool write_x_segment(bool advance);

// R0..R3 form a software frame buffer: three little-endian mask bytes per
// exact 24-bit integer. Formatting never publishes an intermediate frame.
static bool read_packed_segment_frame(u8 frame[core_61::EXTENDED_DISPLAY_CELLS]) {
  for(u8 reg = 0; reg < 4; ++reg) {
    u32 word = 0;
    if(!read_register_unsigned32(reg, 0x1000000U, word)) return false;
    for(u8 byte = 0; byte < 3; ++byte) {
      frame[reg * 3U + byte] = (u8) word;
      word >>= 8;
    }
  }
  return true;
}

static bool publish_packed_segment_frame(void) {
  u8 frame[core_61::EXTENDED_DISPLAY_CELLS];
  if(!read_packed_segment_frame(frame)) return false;
  if(memcmp(extended_program.segment_masks, frame, sizeof(frame)) != 0) {
    memcpy(extended_program.segment_masks, frame, sizeof(frame));
    extended_program.display_revision++;
  }
  return true;
}

static bool format_segment_register(u8 reg, bool hexadecimal) {
  static const u8 decimal_glyphs[10] =
      {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
  u8 frame[core_61::EXTENDED_DISPLAY_CELLS];
  u8 alphabet[16];
  u32 value = 0;
  if(!read_register_unsigned32(reg, hexadecimal ? 0x1000000U : 100000000U,
                               value) || !read_packed_segment_frame(frame))
    return false;
  if(hexadecimal) {
    u16 address = 0;
    if(!read_register_unsigned(0x0F, core_61::EXTENDED_ADDRESS_LIMIT - 15U,
                              address)) return false;
    for(u8 index = 0; index < 16; ++index)
      if(!core_61::read_absolute_program((u16) (address + index), alphabet[index]))
        return false;
  }
  const u8 width = hexadecimal ? 6U : 8U;
  const u8 radix = hexadecimal ? 16U : 10U;
  for(u8 digit = width; digit != 0; --digit) {
    const u8 position = (u8) ((extended_program.cursor + digit - 1U) %
                              core_61::EXTENDED_DISPLAY_CELLS);
    const u8 index = (u8) (value % radix);
    frame[position] = hexadecimal ? alphabet[index] : decimal_glyphs[index];
    value /= radix;
  }
  // All operands are validated before the first write, including aliases of
  // the source register with R0..R3. X and the calculator stack stay intact.
  for(u8 word = 0; word < 4; ++word) {
    const u8* masks = &frame[word * 3U];
    write_register_unsigned(word, (u32) masks[0] | ((u32) masks[1] << 8) |
                                   ((u32) masks[2] << 16));
  }
  extended_program.cursor = (u8) ((extended_program.cursor + width) %
                                   core_61::EXTENDED_DISPLAY_CELLS);
  return true;
}

static bool read_bcd_absolute_address(u16 address, u16& target) {
  u8 high = 0;
  u8 low = 0;
  if(!core_61::read_absolute_program(address, high) ||
     !core_61::read_absolute_program((u16) (address + 1U), low) ||
     (high >> 4) > 9 || (high & 0x0FU) > 9 ||
     (low >> 4) > 9 || (low & 0x0FU) > 9) return false;
  target = (u16) ((high >> 4) * 1000U + (high & 0x0FU) * 100U +
                  (low >> 4) * 10U + (low & 0x0FU));
  return target < core_61::EXTENDED_ADDRESS_LIMIT;
}

static bool x_condition(u8 opcode, bool& branch) {
  char text[15] = {};
  read_stack_register(stack::X, text, EXTENDED_ASCII_DIGITS);
  bool zero = true;
  for(u8 index = 0; index < 8; index++) {
    const char digit = text[index == 0 ? 1 : index + 2];
    if(digit < '0' || digit > '9') return false;
    if(digit != '0') zero = false;
  }
  const bool negative = text[0] == '-' && !zero;
  switch(opcode) {
    // These MK-61 opcodes continue to the next instruction when their named
    // predicate holds; the address operand is taken when it does not.
    case 0x57: case 0x70: branch = zero; return true;
    case 0x59: case 0x90: branch = negative; return true;
    case 0x5C: case 0xC0: branch = !negative; return true;
    case 0x5E: case 0xE0: branch = !zero; return true;
    default: return false;
  }
}

static bool read_indirect_target(u8 reg, u16 limit, u16& target) {
  if(reg > 0x0FU) return false;
  u16 value = 0;
  if(!read_register_unsigned(reg, limit, value)) return false;
  if(reg <= 3U) {
    if(value == 0) return false;
    value--;
    write_register_unsigned(reg, value);
  } else if(reg <= 6U) {
    if(value >= limit - 1U) return false;
    value++;
    write_register_unsigned(reg, value);
  }
  target = value;
  return true;
}

static bool far_loop_opcode(u8 opcode) {
  return opcode == 0x58 || opcode == 0x5A ||
      opcode == 0x5B || opcode == 0x5D;
}

static bool prepare_far_loop(u16 absolute, u8 opcode, u8& delegated_opcode) {
  const u8 reg = opcode == 0x58 ? 2U :
                 opcode == 0x5A ? 3U :
                 opcode == 0x5B ? 1U : 0U;
  u16 value = 0;
  u16 target = absolute + 4U;
  if(target >= core_61::EXTENDED_ADDRESS_LIMIT ||
     !read_register_unsigned(reg, core_61::EXTENDED_ADDRESS_LIMIT, value) ||
     value == 0) return false;
  if(value == 1U) {
    // FL exit leaves the counter intact and runs the same normalization /
    // X2 synchronization as F0. There is no ROM operand to consume here.
    delegated_opcode = 0xF0;
    return set_extended_next_pc(target);
  }
  if(!read_bcd_absolute_address(absolute + 2U, target)) return false;
  // Let the ROM perform a taken FL, including its counter representation and
  // numeric-entry latches. Only the destination is replaced with a far one.
  delegated_opcode = opcode;
  extended_program.pending_prefix = (target + 1U) | 0x4000U;
  return true;
}

static bool far_x_condition(u8 opcode) {
  return opcode == 0x57 || opcode == 0x59 || opcode == 0x5C || opcode == 0x5E ||
      (opcode & 0xF0U) == 0x70 || (opcode & 0xF0U) == 0x90 ||
      (opcode & 0xF0U) == 0xC0 || (opcode & 0xF0U) == 0xE0;
}

static bool execute_far_prefix(u16 absolute) {
  u8 opcode = 0;
  if(!core_61::read_absolute_program((u16) (absolute + 1U), opcode))
    return false;

  const bool direct = opcode == 0x51 || opcode == 0x53 ||
      opcode == 0x57 || opcode == 0x59 || opcode == 0x5C || opcode == 0x5E;
  const bool indirect = (opcode >= 0x70 && opcode <= 0xAF) ||
      (opcode >= 0xC0 && opcode <= 0xCF) ||
      (opcode >= 0xE0 && opcode <= 0xEF);
  if(!direct && !indirect) return false;
  const u16 next = (u16) (absolute + (direct ? 4U : 2U));
  if(next >= core_61::EXTENDED_ADDRESS_LIMIT) return false;
  const bool call = opcode == 0x53 || (opcode & 0xF0U) == 0xA0U;
  if(call && extended_program.return_depth >= EXTENDED_RETURN_DEPTH)
    return false;

  bool branch = true;
  if((opcode >= 0x57 && opcode <= 0x5E) ||
     (opcode >= 0x70 && opcode <= 0x7F) ||
     (opcode >= 0x90 && opcode <= 0x9F) ||
     (opcode >= 0xC0 && opcode <= 0xCF) ||
     (opcode >= 0xE0 && opcode <= 0xEF)) {
    const u8 condition_opcode = direct ? opcode : (u8) (opcode & 0xF0U);
    if(!x_condition(condition_opcode, branch)) return false;
  }
  if(!branch) return set_extended_next_pc(next);

  u16 target = 0;
  if(direct) {
    if(!read_bcd_absolute_address((u16) (absolute + 2U), target))
      return false;
  } else {
    if(!read_indirect_target((u8) (opcode & 0x0FU),
                             core_61::EXTENDED_ADDRESS_LIMIT, target))
      return false;
  }
  if(!set_extended_next_pc(target)) return false;
  if(call) extended_program.return_addresses[extended_program.return_depth++] =
      next;
  return true;
}

static bool execute_display_prefix(u16 absolute) {
  const u16 next = (u16) (absolute + 2U);
  u8 opcode = 0;
  if(next >= core_61::EXTENDED_ADDRESS_LIMIT ||
     !core_61::read_absolute_program((u16) (absolute + 1U), opcode))
    return false;

  if(opcode <= 0x0BU) {
    extended_program.cursor = opcode;
  } else if((opcode & 0xE0U) == 0x60U) {
    if(!format_segment_register((u8) (opcode & 0x0FU), (opcode & 0x10U) != 0))
      return false;
  } else {
    switch(opcode) {
      case 0x0D: // Cx: clear the display, not the arithmetic X.
        memset(extended_program.segment_masks, 0,
               sizeof(extended_program.segment_masks));
        memset(extended_program.held_digits, 15,
               sizeof(extended_program.held_digits));
        extended_program.held_comma = 0;
        extended_program.auto_display = false;
        extended_program.numeric_strobe_pending = false;
        extended_program.display_revision++;
        break;
      case 0x0E: // ENTER: publish X through the selected view.
        if(extended_program.segment_display) {
          if(!write_x_segment(true)) return false;
        } else {
          if(!capture_x_for_numeric_display()) return false;
        }
        break;
      case 0x25: // Rotate one cell without changing the frame.
        extended_program.cursor = (u8) ((extended_program.cursor + 1U) %
            core_61::EXTENDED_DISPLAY_CELLS);
        break;
      case 0x50: // C/P: stop automatic X publication.
        if(extended_program.auto_display) {
          capture_extended_indicator();
          extended_program.auto_display = false;
          extended_program.numeric_strobe_pending = false;
          extended_program.display_revision++;
        }
        break;
      case 0x52: // В/О: return to automatic X publication.
        extended_program.auto_display = true;
        extended_program.numeric_strobe_pending = false;
        extended_program.display_revision++;
        break;
      case 0x53: // Publish all twelve masks from R0..R3 as one frame.
        if(!publish_packed_segment_frame()) return false;
        break;
      case 0x2A: // numeric -> segment representation.
        extended_program.segment_display = true;
        extended_program.numeric_strobe_pending = false;
        extended_program.display_revision++;
        break;
      case 0x30: // segment -> numeric representation.
        extended_program.segment_display = false;
        extended_program.display_revision++;
        break;
      default: return false;
    }
  }
  return set_extended_next_pc(next);
}

static bool execute_virtual_control(u8 local_address, u8 opcode) {
  const u8 bank = extended_program.active_bank;
  if(opcode == 0x52) {
    if(extended_program.return_depth == 0) return false;
    const u16 destination =
        extended_program.return_addresses[extended_program.return_depth - 1U];
    if(!set_extended_next_pc(destination)) return false;
    extended_program.return_depth--;
    return true;
  }
  if(extended_program.return_depth >= EXTENDED_RETURN_DEPTH) return false;
  u16 next = 0;
  if(opcode == 0x53) {
    next = (u16) (bank * core_61::MAX_PROGRAM_STEP +
                  (local_address + 2U) % core_61::MAX_PROGRAM_STEP);
  } else if((opcode & 0xF0U) == 0xA0U) {
    next = (u16) (bank * core_61::MAX_PROGRAM_STEP +
                  (local_address + 1U) % core_61::MAX_PROGRAM_STEP);
  } else {
    return false;
  }
  // Keep only the return address here. The matching ROM jump resolves the
  // local target, including fractional/hex selectors and auto-counters.
  extended_program.return_addresses[extended_program.return_depth++] = next;
  return true;
}

static bool write_x_segment(bool advance) {
  u16 mask = 0;
  if(!read_x_unsigned(256, mask)) return false;
  const u8 cursor = extended_program.cursor;
  const bool changed = extended_program.segment_masks[cursor] != (u8) mask;
  extended_program.segment_masks[cursor] = (u8) mask;
  if(advance) extended_program.cursor =
      (u8) ((cursor + 1U) % core_61::EXTENDED_DISPLAY_CELLS);
  if(changed) extended_program.display_revision++;
  return true;
}

static inline bool extended_ms_command(u8 opcode) {
  return expanded_program_mode &&
      (opcode == MK61_EXCHANGE_DATA_WITH_MS ||
       opcode == MK61_EXCHANGE_PROGRAM_WITH_MS);
}

static inline void exchange_ring_tetrades(usize left, usize right) {
  const u8 saved = ringM[left];
  ringM[left] = ringM[right];
  ringM[right] = saved;
}

static void exchange_data_with_ms(void) {
  // M1, M2 and M3 are interleaved at offsets 0, 1 and 2 in every group
  // of three ring tetras.  A numeric word occupies 12 of a page's 14 M1/M2
  // tetras; the two service tetras in Ms must remain untouched.
  for(usize page = 0; page < MK61_EXPANDED_MS_PAGES; page++) {
    const usize base = page * MK61_MEMORY_PAGE_TETRADES;
    for(usize digit = 0; digit < MK61_NUMERIC_TETRADES; digit++) {
      exchange_ring_tetrades(base + digit * 3U,
                             base + digit * 3U + 1U);
    }
  }
}

static void exchange_program_with_ms(void) {
  // Program exchange uses the complete seven-byte page, including the two
  // M2 tetras which numeric exchange deliberately preserves.
  for(usize page = 0; page < MK61_EXPANDED_MS_PAGES; page++) {
    const usize base = page * MK61_MEMORY_PAGE_TETRADES;
    for(usize digit = 0; digit < MK61_TETRADES_PER_PAGE; digit++) {
      exchange_ring_tetrades(base + digit * 3U + 1U,
                             base + digit * 3U + 2U);
    }
  }
}

static bool execute_extended_ms_command(u8 opcode) {
  if(!extended_ms_command(opcode)) return false;
  if(opcode == MK61_EXCHANGE_DATA_WITH_MS) exchange_data_with_ms();
  else exchange_program_with_ms();
  return true;
}

static u8 begin_mk61_command(u8 opcode, core_61::Mk61CommandSource source) {
  mk61_command_sequence++;
  if(mk61_command_sequence == 0) mk61_command_sequence = 1;
  const u8 executed_opcode =
      dispatch_mk61_command_before(opcode, source, mk61_command_sequence);
  active_mk61_command = {
      true, source, opcode, executed_opcode, mk61_command_sequence
  };
  // The stock 55/56 ROM branches are inert on a serial MK-61.  In the
  // opt-in 112+RF configuration perform the architected bank exchange here,
  // after BEFORE hooks have selected the effective opcode, and let the ROM
  // complete a harmless one-step NOP.  The semantic opcode retained above is
  // still reported to AFTER hooks.
  return execute_extended_ms_command(executed_opcode)
      ? (u8) MK61_NOP : executed_opcode;
}

static void reset_mk61_command_runtime(void) {
  active_mk61_command = {};
  keyboard_command_complete_pending = false;
  external_random_pending = false;
  mk61_program_boundary_yielded = false;
  mk61_jump_operand = 0;
  memset(mk61_call_operand_addresses, 0,
         sizeof(mk61_call_operand_addresses));
  memset(mk61_call_operand_visits, 0,
         sizeof(mk61_call_operand_visits));
  mk61_call_operand_depth = 0;
  extended_program.pending_prefix = 0;
}

static inline u8 __attribute__((always_inline)) decode_mk61_opcode(void) {
  return (u8) ((m_IK1302.R[30] & 0x0FU) |
               ((m_IK1302.R[33] & 0x0FU) << 4));
}

static inline void __attribute__((always_inline)) encode_mk61_opcode(u8 opcode) {
  m_IK1302.R[30] = opcode & 0x0FU;
  m_IK1302.R[33] = opcode >> 4;
}

static inline u8 __attribute__((always_inline)) prefetched_program_address(void) {
  const usize steps = core_61::program_steps();
  if(steps == 0) return 0;
  // По адресу ПЗУ 06 код уже достиг R30/R33, а эмулируемый IP всё ещё указывает
  // на него. Выборка операнда продвинет IP позднее.
  return (u8) ((usize) core_61::get_IP() % steps);
}

static bool dispatch_mk61_program_boundary(u8 program_address, u8 opcode) {
  if(mk61_program_boundary_hook == nullptr) return false;
  const core_61::Mk61ProgramBoundaryContext context = {
      program_address, opcode
  };
  mk61_program_boundary_dispatching = true;
  const bool should_yield =
      mk61_program_boundary_hook(context, mk61_program_boundary_user_data);
  mk61_program_boundary_dispatching = false;
  return should_yield;
}

static inline bool __attribute__((always_inline)) handle_mk61_command_prefetch(
    u8 address) {
  if(address == 0x06U) {
    u8 program_address = prefetched_program_address();
    // A branch operand also visits prefetch. Finish a delegated ROM FL before
    // applying its pending far destination, and supply a harmless local
    // operand even when the prefix straddles a bank boundary.
    // Consume only this visit: a later jump to the operand is a real command.
    const u8 jump_operand = mk61_jump_operand;
    mk61_jump_operand = 0;
    if((usize) program_address + 1U == jump_operand) {
      if(extended_program.pending_prefix & 0x4000U) encode_mk61_opcode(0x00);
      return false;
    }
    if(extended_program.pending_prefix != 0) {
      // The prefix's ROM NOP (or delegated FL) has completed its numeric work.
      // At the initial prefetch even 0-19 can still expose +19.
      // Resolve the prefix before decoding its operand, then feed the target's
      // real opcode into this same fetch: no additional NOP or ROM step.
      const u16 pending = extended_program.pending_prefix;
      const u16 absolute = (pending & 0x3FFFU) - 1U;
      extended_program.pending_prefix = 0;
      u8 next_opcode = 0x50;
      const bool success = (pending & 0x4000U) ? set_extended_next_pc(absolute) :
          (pending & 0x8000U) ? execute_display_prefix(absolute) :
                               execute_far_prefix(absolute);
      if(success) {
        const u8 next = (u8) ((core_61::get_IP() + 1U) % core_61::MAX_PROGRAM_STEP);
        core_61::set_IP(next);
        if(!core_61::read_absolute_program((u16) (extended_program.active_bank *
              core_61::MAX_PROGRAM_STEP + next), next_opcode))
          extended_program.error = true;
      } else {
        extended_program.error = true;
      }
      encode_mk61_opcode(next_opcode);
      program_address = prefetched_program_address();
    }

    // Штатное ПЗУ ПП/CALL дважды показывает операнд по этому микроадресу:
    // при выборке цели и снова при возврате за эту ячейку. Ни одно посещение
    // не является границей команды. Небольшой LIFO отражает вложенные вызовы.
    if(mk61_call_operand_depth > 0 &&
       program_address ==
           mk61_call_operand_addresses[mk61_call_operand_depth - 1]) {
      u8& visits = mk61_call_operand_visits[mk61_call_operand_depth - 1];
      if(visits > 0) visits--;
      if(visits == 0) mk61_call_operand_depth--;
      return false;
    }

    // Only a real command boundary completes the preceding command; neither
    // BEFORE/AFTER callbacks nor boundary hooks may observe an address operand.
    finish_active_mk61_command();

    const u8 opcode = decode_mk61_opcode();
    if(dispatch_mk61_program_boundary(program_address, opcode)) return true;

    u8 executed_opcode = opcode;
    const bool built_in_extended = expanded_program_mode &&
        (opcode == MK61_FAR_ADDRESS_PREFIX ||
         opcode == MK61_DISPLAY_PREFIX || opcode == 0x53U ||
         (opcode >= 0xA0U && opcode <= 0xAFU) ||
         (opcode == 0x52U && extended_program.return_depth > 0));
    if(has_mk61_command_target(opcode) || extended_ms_command(opcode) ||
       built_in_extended) {
      executed_opcode = begin_mk61_command(
          opcode, core_61::Mk61CommandSource::PROGRAM);
      const u8 semantic_opcode = active_mk61_command.executed_opcode;
      if(expanded_program_mode) {
        bool handled = false;
        bool success = false;
        u8 delegated_opcode = (u8) MK61_NOP;
        if(semantic_opcode == MK61_FAR_ADDRESS_PREFIX) {
          handled = true;
          const u16 absolute = (u16) (extended_program.active_bank *
              core_61::MAX_PROGRAM_STEP + program_address);
          u8 far_opcode = 0;
          if(core_61::read_absolute_program((u16) (absolute + 1U), far_opcode) &&
             far_x_condition(far_opcode)) {
            extended_program.pending_prefix = absolute + 1U;
            success = true;
          } else if(far_loop_opcode(far_opcode)) {
            success = prepare_far_loop(absolute, far_opcode, delegated_opcode);
          } else {
            success = execute_far_prefix(absolute);
          }
        } else if(semantic_opcode == MK61_DISPLAY_PREFIX) {
          handled = true;
          const u16 absolute = (u16) (extended_program.active_bank *
              core_61::MAX_PROGRAM_STEP + program_address);
          u8 display_opcode = 0;
          if(core_61::read_absolute_program((u16) (absolute + 1U), display_opcode) &&
             display_opcode == 0x0E) {
            // X still contains a transient ROM value at prefetch: sqrt(81)
            // can expose 81, INT can expose the original fraction. Reuse the
            // prefix's NOP just as far predicates do, in either display view.
            extended_program.pending_prefix = (absolute + 1U) | 0x8000U;
            success = true;
          } else {
            success = execute_display_prefix(absolute);
          }
        } else if(semantic_opcode == 0x53U ||
                  (semantic_opcode >= 0xA0U && semantic_opcode <= 0xAFU) ||
                  (semantic_opcode == 0x52U &&
                   extended_program.return_depth > 0)) {
          handled = true;
          success = execute_virtual_control(program_address, semantic_opcode);
        }
        if(handled) {
          if(!success) extended_program.error = true;
          // A ROM return also synchronizes X -> X2 and normalizes X. The
          // virtual stack handles only its control flow; F0 preserves the
          // return's numeric side effects without touching the ROM stack.
          executed_opcode = success ? delegated_opcode : 0x50U;
          if(success) {
            if(semantic_opcode == 0x52U) executed_opcode = 0xF0U;
            else if(semantic_opcode == 0x53U) executed_opcode = 0x51U;
            else if((semantic_opcode & 0xF0U) == 0xA0U)
              executed_opcode = semantic_opcode - 0x20U;
          }
        }
      }
      encode_mk61_opcode(executed_opcode);
    }
    if(core_61::len_code_command(executed_opcode) == 2) {
      const u8 operand =
          (u8) (((usize) program_address + 1U) % core_61::program_steps());
      if(executed_opcode == 0x53U) {
        if(mk61_call_operand_depth < MK61_CALL_OPERAND_DEPTH) {
          mk61_call_operand_addresses[mk61_call_operand_depth] = operand;
          mk61_call_operand_visits[mk61_call_operand_depth++] = 2;
        }
      } else {
        mk61_jump_operand = operand + 1U;
      }
    }
    return false;
  }

  if(address == 0x97U && m_IK1302.key_y != 0 &&
     !active_mk61_command.active) {
    const u8 opcode = decode_mk61_opcode();
    // Клавиатурная В/О начинает новую цепочку вызовов калькулятора. Обычное
    // продолжение С/П намеренно сохраняет ожидающие операнды подпрограммы,
    // приостановленной клавишей С/П.
    if(opcode == 0x52U) {
      mk61_call_operand_depth = 0;
      mk61_jump_operand = 0;
    }
    if(!has_mk61_command_target(opcode) && !extended_ms_command(opcode)) return false;
    const u8 replacement = begin_mk61_command(
        opcode, core_61::Mk61CommandSource::KEYBOARD);
    encode_mk61_opcode(replacement);
    return false;
  }

  // Клавиатурные команды возвращаются к обычному циклу ожидания дисплея по
  // адресу 33 лишь после фиксации видимого калькулятору результата. Откладываем
  // AFTER до конца core_61::step(), где последовательное кольцо находится на
  // границе внешнего API и set_stack_register()/write_stack_register() безопасны.
  if(address == 0x33U && active_mk61_command.active &&
     active_mk61_command.source == core_61::Mk61CommandSource::KEYBOARD) {
    keyboard_command_complete_pending = true;
  }
  return false;
}

} // безымянное пространство имён

namespace core_61 {

RomCommandHookHandle register_rom_command_hook(
    RomChip chip, u8 address, RomCommandHook callback, void* user_data) {
  return add_rom_command_hook(chip, address, callback, user_data, false);
}

bool unregister_rom_command_hook(RomCommandHookHandle handle) {
  return remove_rom_command_hook(handle, false);
}

usize registered_rom_command_hook_count(void) {
  return public_rom_command_hook_count;
}

Mk61CommandHookHandle register_mk61_command_hook(
    u8 opcode,
    Mk61CommandHookPhase phase,
    Mk61CommandHook callback,
    void* user_data) {
  return add_mk61_command_hook(opcode, phase, callback, user_data, false);
}

bool unregister_mk61_command_hook(Mk61CommandHookHandle handle) {
  return remove_mk61_command_hook(handle, false);
}

usize registered_mk61_command_hook_count(void) {
  return public_mk61_command_hook_count;
}

bool set_mk61_program_boundary_hook(
    Mk61ProgramBoundaryHook callback, void* user_data) {
  if(callback == nullptr || mk61_program_boundary_dispatching ||
     mk61_program_boundary_hook != nullptr) return false;
  mk61_program_boundary_hook = callback;
  mk61_program_boundary_user_data = user_data;
  return true;
}

void clear_mk61_program_boundary_hook(void) {
  if(mk61_program_boundary_dispatching) return;
  mk61_program_boundary_hook = nullptr;
  mk61_program_boundary_user_data = nullptr;
  mk61_program_boundary_yielded = false;
}

bool program_boundary_yielded(void) {
  return mk61_program_boundary_yielded;
}

u32 rom_command_instruction(RomChip chip, u8 address) {
  switch(chip) {
    case RomChip::IK1302: return ROM.IK1302.instructions[address];
    case RomChip::IK1303: return ROM.IK1303.instructions[address];
    case RomChip::IK1306: return ROM.IK1306.instructions[address];
  }
  return 0;
}

#if MK61_CORE_BODY_PROFILE
void reset_body_profile(void) {
  memset(body_profile_counts, 0, sizeof(body_profile_counts));
  body_profile_call_count = 0;
}

u64 body_profile_count(RomChip chip, u8 region, u8 microprogram) {
  const u8 chip_index = (u8) chip;
  if(chip_index >= 3 || region >= BODY_PROFILE_REGION_COUNT ||
     microprogram >= BODY_PROFILE_MICROPROGRAM_COUNT) return 0;
  return body_profile_counts[chip_index][region][microprogram];
}

u64 body_profile_total(void) {
  return body_profile_call_count;
}
#endif

#if MK61_CORE_NATIVE_HOT_PATHS && !defined(ARDUINO)
void set_native_hot_paths_enabled(bool enabled) {
  native_hot_paths_are_enabled = enabled;
}

bool native_hot_paths_enabled(void) {
  return native_hot_paths_are_enabled;
}

void reset_native_hot_path_counts(void) {
  memset(native_hot_path_counts, 0, sizeof(native_hot_path_counts));
}

u64 native_hot_path_count(NativeHotPath path) {
  const u8 index = (u8) path;
  return index < (u8) NativeHotPath::COUNT
      ? native_hot_path_counts[index] : 0;
}
#endif

#if MK61_CORE_PACKED_AMK && !defined(ARDUINO)
void set_packed_amk_enabled(bool enabled) {
  packed_amk_is_enabled = enabled;
}

bool packed_amk_enabled(void) {
  return packed_amk_is_enabled;
}
#endif

} // пространство имён core_61

inline u8* IK1302_M_START(void) {
  return &ringM[expanded_program_mode ? OFFSET_IK1302_EXPANDED : OFFSET_IK1302_CLASSIC];
}

inline u8* IK1303_M_START(void) {
  return &ringM[expanded_program_mode ? OFFSET_IK1303_EXPANDED : OFFSET_IK1303_CLASSIC];
}

inline u8* IK1306_M_START(void) {
  return &ringM[expanded_program_mode ? OFFSET_IK1306_EXPANDED : OFFSET_IK1306_CLASSIC];
}

static  const   u8  IK1302_DCW[68] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x02, 0x00, 0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x02, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00,
  0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x02, 0x02,
  0x03, 0x00, 0x00, 0x00
};

static  const   u8  IK1302_DCWA[68] = {
  0x00, 0x02, 0x0C, 0x0C, 0x0C, 0x02, 0x02, 0x00, 0x02, 0x00, 0x10, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
  0x02, 0x02, 0x00, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0A, 0x02, 0x02, 0x02, 0x02, 0x00, 0x00, 0x02,
  0x02, 0x08, 0x08, 0x00, 0x0E, 0x00, 0x00, 0x08, 0x02, 0x04, 0x08, 0x02, 0x08, 0x02, 0x06, 0x0C,
  0x04, 0x04, 0x00, 0x0A, 0x0C, 0x02, 0x00, 0x02, 0x02, 0x02, 0x0C, 0x02, 0x02, 0x0C, 0x02, 0x02,
  0x00, 0x00, 0x02, 0x02
};

static  const   u8  IK1303_DCW[68] = {
  00, 00, 00, 00, 00, 00, 00, 00, 00, 00, 00, 03, 00, 00, 00, 00,
  00, 00, 00, 02, 00, 00, 00, 00, 03, 00, 00, 00, 01, 00, 00, 00,
  00, 00, 00, 00, 00, 00, 00, 00, 00, 00, 00, 00, 00, 03, 00, 01,
  00, 03, 00, 00, 02, 00, 00, 03, 02, 00, 00, 02, 03, 00, 00, 00,
  00, 00, 00, 00
};

static  const   u8  IK1306_DCW[68] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00,
  0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x02, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x02,
  0x02, 0x02, 0x03, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x02, 0x02, 0x02, 0x00,
  0x02, 0x02, 0x00, 0x00
};

// The historical source spells each nine-byte microprogram as a 16-byte row
// so it remains auditable against the original ROM transcription. Only the
// meaningful nine bytes are emitted in Flash; the hot SRAM cache expands them
// back to a 16-byte stride, retaining the measured shift-only fast path.
static constexpr usize AND_AMK_BODY_COUNT = 128;
static constexpr usize AND_AMK_PACKED_STRIDE = 9;
static constexpr usize AND_AMK_RUNTIME_STRIDE = 16;
static constexpr usize AND_AMK_PACKED_SIZE =
    AND_AMK_BODY_COUNT * AND_AMK_PACKED_STRIDE;
static constexpr usize AND_AMK_RUNTIME_SIZE =
    AND_AMK_BODY_COUNT * AND_AMK_RUNTIME_STRIDE;

struct PackedAndAmkTable {
  u8 bytes[AND_AMK_PACKED_SIZE];
};

constexpr bool and_amk_padding_is_zero(
    const u8 (&source)[AND_AMK_RUNTIME_SIZE]) {
  for(usize body = 0; body < AND_AMK_BODY_COUNT; body++) {
    for(usize column = AND_AMK_PACKED_STRIDE;
        column < AND_AMK_RUNTIME_STRIDE; column++) {
      if(source[body * AND_AMK_RUNTIME_STRIDE + column] != 0) return false;
    }
  }
  return true;
}

constexpr PackedAndAmkTable pack_and_amk_table(
    const u8 (&source)[AND_AMK_RUNTIME_SIZE]) {
  PackedAndAmkTable result = {};
  for(usize body = 0; body < AND_AMK_BODY_COUNT; body++) {
    for(usize column = 0; column < AND_AMK_PACKED_STRIDE; column++) {
      result.bytes[body * AND_AMK_PACKED_STRIDE + column] =
          source[body * AND_AMK_RUNTIME_STRIDE + column];
    }
  }
  return result;
}

// ПЗУ микропрограмм ИК1302 (3*3*128 микропрограмм).
static constexpr u8 IK1302_AND_AMK_EXPANDED[AND_AMK_RUNTIME_SIZE] = {
// 1     2     3     4     5     6     7     8     9   [ 10    11    12    13    14    15    16 ]
  0x00, 0x00, 0x00, 0x10, 0x03, 0x1D, 0x00, 0x07, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x10, 0x03, 0x1C, 0x0B, 0x07, 0x0C, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x15, 0x18, 0x09, 0x16, 0x18, 0x09, 0x16, 0x18, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x03, 0x0E, 0x1E, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x23, 0x00, 0x00, 0x00, 0x2F, 0x00, 0x2C, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x11, 0x32, 0x00, 0x00, 0x00, 0x03, 0x00, 0x0E, 0x1A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x0E, 0x0D, 0x19, 0x03, 0x2F, 0x0E, 0x0D, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1C, 0x0C, 0x0D, 0x01, 0x00, 0x00, 0x03, 0x24, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1C, 0x0C, 0x2F, 0x09, 0x1E, 0x34, 0x0E, 0x1E, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x0A, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x09, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x38, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0A, 0x26, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x35, 0x34, 0x0D, 0x24, 0x1E, 0x1A, 0x09, 0x0C, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3E, 0x00, 0x00, 0x1C, 0x03, 0x0E, 0x0A, 0x0F, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3E, 0x00, 0x0E, 0x42, 0x03, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x42, 0x33, 0x0D, 0x01, 0x08, 0x00, 0x01, 0x08, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x03, 0x0E, 0x2B, 0x3A, 0x09, 0x12, 0x1E, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x35, 0x03, 0x07, 0x0C, 0x1E, 0x1A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x35, 0x0C, 0x2F, 0x0E, 0x03, 0x01, 0x00, 0x00, 0x15, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x24, 0x1E, 0x1A, 0x23, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x09, 0x0C, 0x2F, 0x09, 0x03, 0x00, 0x24, 0x0C, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3E, 0x09, 0x1E, 0x42, 0x03, 0x07, 0x0B, 0x22, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x0B, 0x0D, 0x0C, 0x03, 0x0E, 0x1E, 0x3A, 0x2B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3C, 0x03, 0x00, 0x09, 0x34, 0x0E, 0x1E, 0x0C, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2E, 0x01, 0x31, 0x2E, 0x01, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2E, 0x30, 0x03, 0x2E, 0x30, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2E, 0x2D, 0x00, 0x2E, 0x2D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3B, 0x04, 0x2F, 0x37, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x14, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x13, 0x00, 0x01, 0x13, 0x00, 0x01, 0x13, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2E, 0x00, 0x00, 0x2E, 0x00, 0x00, 0x2E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3E, 0x07, 0x10, 0x42, 0x03, 0x00, 0x2C, 0x07, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x0F, 0x10, 0x03, 0x00, 0x1C, 0x03, 0x0F, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x03, 0x32, 0x00, 0x2B, 0x14, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x04, 0x14, 0x00, 0x00, 0x32, 0x00, 0x00, 0x32, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x32, 0x00, 0x00, 0x32, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x21, 0x15, 0x18, 0x21, 0x16, 0x18, 0x00, 0x17, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x19, 0x1A, 0x18, 0x19, 0x16, 0x18, 0x09, 0x16, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2B, 0x15, 0x00, 0x00, 0x17, 0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x1B, 0x0E, 0x0F, 0x1B, 0x0E, 0x23, 0x2B, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2C, 0x18, 0x00, 0x2A, 0x18, 0x07, 0x0B, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x14, 0x00, 0x32, 0x32, 0x11, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x09, 0x0C, 0x15, 0x03, 0x00, 0x00, 0x06, 0x3C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x2C, 0x00, 0x00, 0x2A, 0x00, 0x09, 0x16, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x11, 0x00, 0x09, 0x16, 0x18, 0x09, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x07, 0x0A, 0x29, 0x40, 0x33, 0x29, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x0B, 0x0F, 0x10, 0x03, 0x08, 0x24, 0x03, 0x23, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x01, 0x1D, 0x32, 0x08, 0x00, 0x32, 0x08, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x08, 0x23, 0x32, 0x08, 0x0F, 0x23, 0x23, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x09, 0x1E, 0x0F, 0x00, 0x00, 0x14, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x00, 0x00, 0x37, 0x00, 0x00, 0x37, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x31, 0x00, 0x01, 0x31, 0x00, 0x01, 0x31, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1A, 0x30, 0x0D, 0x00, 0x30, 0x0D, 0x00, 0x30, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x30, 0x03, 0x00, 0x30, 0x03, 0x00, 0x30, 0x03, 0x2B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2D, 0x00, 0x00, 0x2D, 0x00, 0x00, 0x2D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x30, 0x03, 0x00, 0x30, 0x03, 0x00, 0x30, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x01, 0x31, 0x00, 0x01, 0x31, 0x00, 0x01, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x2D, 0x00, 0x00, 0x2D, 0x00, 0x00, 0x2D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2C, 0x00, 0x00, 0x2A, 0x00, 0x00, 0x09, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x1E, 0x0F, 0x01, 0x00, 0x08, 0x1C, 0x0A, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x14, 0x00, 0x00, 0x32, 0x00, 0x00, 0x32, 0x2B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x00, 0x00, 0x32, 0x27, 0x36, 0x08, 0x09, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1E, 0x02, 0x1D, 0x0F, 0x0C, 0x0F, 0x26, 0x07, 0x22, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1D, 0x23, 0x23, 0x09, 0x23, 0x0C, 0x03, 0x23, 0x23, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x02, 0x35, 0x03, 0x0F, 0x00, 0x00, 0x00, 0x04, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x12, 0x00, 0x08, 0x00, 0x32, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x18, 0x00, 0x17, 0x18, 0x00, 0x17, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x01, 0x13, 0x00, 0x01, 0x13, 0x04, 0x01, 0x13, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x09, 0x15, 0x18, 0x00, 0x35, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x03, 0x09, 0x0C, 0x1B, 0x1E, 0x0F, 0x1B, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x1C, 0x03, 0x1E, 0x15, 0x02, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x1E, 0x10, 0x0F, 0x09, 0x32, 0x1E, 0x0F, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x09, 0x1E, 0x1A, 0x18, 0x1D, 0x17, 0x03, 0x0F, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x0B, 0x1A, 0x1D, 0x28, 0x00, 0x0E, 0x28, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x03, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x04, 0x2B, 0x23, 0x04, 0x08, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x03, 0x00, 0x2B, 0x2F, 0x0D, 0x12, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x08, 0x00, 0x01, 0x08, 0x00, 0x01, 0x08, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x1D, 0x2F, 0x0E, 0x03, 0x23, 0x07, 0x1E, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x12, 0x00, 0x23, 0x24, 0x1E, 0x23, 0x0F, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x26, 0x12, 0x15, 0x03, 0x12, 0x04, 0x24, 0x2F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x04, 0x01, 0x0F, 0x07, 0x1E, 0x0F, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x0F, 0x20, 0x05, 0x00, 0x07, 0x12, 0x0E, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1E, 0x00, 0x10, 0x03, 0x0F, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x01, 0x00, 0x00, 0x05, 0x00, 0x17, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x0A, 0x1A, 0x18, 0x00, 0x17, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x09, 0x0F, 0x32, 0x07, 0x0C, 0x0C, 0x1A, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x14, 0x00, 0x00, 0x32, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x1E, 0x15, 0x00, 0x00, 0x02, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x0E, 0x08, 0x0E, 0x1D, 0x23, 0x1E, 0x3A, 0x3A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1D, 0x04, 0x15, 0x00, 0x00, 0x3A, 0x00, 0x00, 0x3A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x3A, 0x00, 0x0D, 0x0E, 0x03, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3B, 0x3C, 0x2F, 0x37, 0x3C, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x30, 0x00, 0x02, 0x24, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x07, 0x0B, 0x22, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x39, 0x04, 0x25, 0x08, 0x03, 0x07, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x2C, 0x00, 0x2B, 0x2A, 0x26, 0x0D, 0x07, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x04, 0x0B, 0x08, 0x01, 0x10, 0x0D, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x01, 0x08, 0x04, 0x01, 0x08, 0x23, 0x01, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x1B, 0x00, 0x00, 0x1B, 0x1F, 0x0E, 0x1B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x2C, 0x00, 0x1B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x01, 0x0F, 0x0D, 0x01, 0x09, 0x1E, 0x2B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x23, 0x1A, 0x07, 0x1E, 0x0C, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1E, 0x12, 0x00, 0x00, 0x12, 0x00, 0x00, 0x12, 0x1A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1E, 0x00, 0x10, 0x0F, 0x24, 0x1E, 0x34, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x09, 0x2F, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x12, 0x09, 0x15, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x2B, 0x00, 0x00, 0x00, 0x09, 0x0C, 0x23, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x24, 0x0C, 0x1E, 0x0F, 0x00, 0x07, 0x03, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x01, 0x0F, 0x07, 0x0B, 0x0F, 0x25, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x04, 0x00, 0x00, 0x00, 0x12, 0x09, 0x0C, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x12, 0x00, 0x00, 0x00, 0x09, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x03, 0x00, 0x00, 0x00, 0x04, 0x32, 0x24, 0x0F, 0x23, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x09, 0x1E, 0x1A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x0B, 0x0F, 0x07, 0x0C, 0x1E, 0x1A, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x00, 0x01, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x12, 0x00, 0x00, 0x12, 0x04, 0x0C, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x32, 0x00, 0x00, 0x32, 0x00, 0x00, 0x08, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x02, 0x0D, 0x00, 0x01, 0x0F, 0x0D, 0x00, 0x0E, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1E, 0x00, 0x10, 0x0F, 0x07, 0x0B, 0x34, 0x0F, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1D, 0x04, 0x08, 0x36, 0x00, 0x08, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x03, 0x1E, 0x0F, 0x26, 0x0A, 0x02, 0x26, 0x40, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};
static_assert(and_amk_padding_is_zero(IK1302_AND_AMK_EXPANDED),
              "IK1302 AND_AMK padding contains data");
static constexpr PackedAndAmkTable IK1302_AND_AMK_STORAGE =
    pack_and_amk_table(IK1302_AND_AMK_EXPANDED);

static constexpr u8 IK1303_AND_AMK_EXPANDED[AND_AMK_RUNTIME_SIZE] = {
// 1     2     3     4     5     6     7     8     9     10    11    12    13    14    15    16  
  0x2C, 0x23, 0x00, 0x2C, 0x23, 0x00, 0x2C, 0x23, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x31, 0x32, 0x00, 0x31, 0x32, 0x12, 0x31, 0x32, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x11, 0x23, 0x00, 0x1F, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x31, 0x00, 0x1C, 0x31, 0x00, 0x00, 0x31, 0x08, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2C, 0x02, 0x0E, 0x2C, 0x02, 0x01, 0x2C, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x08, 0x3A, 0x00, 0x00, 0x3A, 0x01, 0x05, 0x3A, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x18, 0x0A, 0x2B, 0x00, 0x01, 0x33, 0x02, 0x24, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x3A, 0x18, 0x31, 0x3A, 0x1F, 0x31, 0x3A, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x02, 0x06, 0x31, 0x02, 0x12, 0x31, 0x10, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x39, 0x02, 0x26, 0x33, 0x09, 0x08, 0x19, 0x19, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x14, 0x0C, 0x00, 0x00, 0x00, 0x1B, 0x06, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x26, 0x00, 0x21, 0x12, 0x14, 0x24, 0x06, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x39, 0x00, 0x21, 0x08, 0x22, 0x00, 0x10, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x20, 0x00, 0x00, 0x39, 0x02, 0x00, 0x06, 0x25, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x19, 0x02, 0x16, 0x09, 0x11, 0x19, 0x16, 0x11, 0x13, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x18, 0x08, 0x10, 0x18, 0x00, 0x01, 0x1F, 0x06, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1A, 0x12, 0x2E, 0x19, 0x02, 0x00, 0x33, 0x38, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0D, 0x06, 0x3B, 0x13, 0x0A, 0x02, 0x00, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x33, 0x13, 0x3C, 0x00, 0x11, 0x14, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x11, 0x1D, 0x34, 0x13, 0x01, 0x00, 0x14, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2C, 0x10, 0x21, 0x2C, 0x02, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x12, 0x2A, 0x31, 0x02, 0x00, 0x12, 0x06, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x12, 0x2A, 0x31, 0x14, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x39, 0x0D, 0x12, 0x10, 0x0F, 0x00, 0x00, 0x27, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x12, 0x0C, 0x31, 0x05, 0x00, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x20, 0x0A, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x11, 0x13, 0x0E, 0x01, 0x0D, 0x11, 0x05, 0x25, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x24, 0x0C, 0x08, 0x0D, 0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x06, 0x3A, 0x31, 0x05, 0x02, 0x0A, 0x1D, 0x16, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x38, 0x14, 0x0C, 0x00, 0x08, 0x06, 0x20, 0x1B, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x02, 0x06, 0x00, 0x02, 0x1F, 0x19, 0x20, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x37, 0x10, 0x21, 0x31, 0x12, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x2D, 0x30, 0x01, 0x2D, 0x00, 0x01, 0x2D, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x33, 0x34, 0x06, 0x01, 0x18, 0x00, 0x01, 0x18, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x31, 0x20, 0x34, 0x31, 0x20, 0x05, 0x31, 0x20, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1F, 0x3A, 0x20, 0x14, 0x3A, 0x20, 0x0C, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x20, 0x06, 0x30, 0x1F, 0x0C, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x35, 0x20, 0x05, 0x34, 0x14, 0x09, 0x30, 0x20, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x08, 0x18, 0x18, 0x08, 0x18, 0x18, 0x08, 0x33, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x04, 0x16, 0x06, 0x36, 0x06, 0x0C, 0x01, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x2F, 0x08, 0x18, 0x1C, 0x00, 0x18, 0x00, 0x20, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x18, 0x14, 0x35, 0x1D, 0x06, 0x14, 0x00, 0x3B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x20, 0x05, 0x34, 0x14, 0x09, 0x19, 0x00, 0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x05, 0x3A, 0x3A, 0x06, 0x3A, 0x3A, 0x05, 0x3A, 0x3A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x23, 0x00, 0x01, 0x23, 0x00, 0x01, 0x23, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x32, 0x02, 0x01, 0x32, 0x02, 0x01, 0x32, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x15, 0x04, 0x03, 0x15, 0x17, 0x03, 0x15, 0x17, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x2B, 0x03, 0x07, 0x17, 0x03, 0x07, 0x17, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x04, 0x1E, 0x06, 0x1E, 0x42, 0x0E, 0x09, 0x11, 0x13, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x29, 0x05, 0x09, 0x28, 0x09, 0x09, 0x09, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x08, 0x0B, 0x0B, 0x1B, 0x0B, 0x0B, 0x1E, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x08, 0x0B, 0x0B, 0x0E, 0x0B, 0x0B, 0x1A, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x11, 0x1D, 0x06, 0x08, 0x10, 0x04, 0x02, 0x06, 0x2F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1F, 0x1C, 0x2F, 0x00, 0x1C, 0x1C, 0x09, 0x18, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0B, 0x0C, 0x0C, 0x0B, 0x02, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x25, 0x1C, 0x04, 0x01, 0x1C, 0x1D, 0x1D, 0x06, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x30, 0x21, 0x42, 0x2E, 0x11, 0x19, 0x25, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x16, 0x00, 0x00, 0x03, 0x0C, 0x0A, 0x19, 0x0A, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x16, 0x1B, 0x11, 0x1D, 0x10, 0x3C, 0x3A, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x20, 0x08, 0x10, 0x06, 0x22, 0x19, 0x02, 0x22, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x0C, 0x01, 0x10, 0x00, 0x00, 0x00, 0x11, 0x13, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x2B, 0x03, 0x0A, 0x17, 0x03, 0x0A, 0x17, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x14, 0x06, 0x12, 0x02, 0x00, 0x0A, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x24, 0x0C, 0x00, 0x0A, 0x21, 0x06, 0x20, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x21, 0x21, 0x35, 0x02, 0x08, 0x10, 0x02, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x12, 0x0F, 0x11, 0x24, 0x21, 0x35, 0x02, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x25, 0x0C, 0x06, 0x02, 0x12, 0x14, 0x02, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x20, 0x14, 0x00, 0x00, 0x21, 0x18, 0x12, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x24, 0x06, 0x00, 0x20, 0x08, 0x25, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x24, 0x02, 0x35, 0x18, 0x12, 0x14, 0x34, 0x00, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x14, 0x0C, 0x00, 0x0A, 0x21, 0x35, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x26, 0x03, 0x06, 0x27, 0x03, 0x06, 0x27, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x26, 0x03, 0x00, 0x27, 0x03, 0x00, 0x27, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x11, 0x04, 0x03, 0x00, 0x36, 0x03, 0x00, 0x36, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x04, 0x03, 0x07, 0x17, 0x03, 0x07, 0x17, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x20, 0x24, 0x25, 0x03, 0x06, 0x08, 0x02, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x04, 0x16, 0x0A, 0x17, 0x03, 0x0A, 0x17, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x07, 0x2B, 0x00, 0x07, 0x17, 0x00, 0x07, 0x17, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x07, 0x2B, 0x03, 0x07, 0x17, 0x03, 0x07, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x03, 0x36, 0x03, 0x11, 0x24, 0x1D, 0x24, 0x03, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x15, 0x04, 0x03, 0x15, 0x17, 0x03, 0x15, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x03, 0x12, 0x1D, 0x1D, 0x14, 0x06, 0x12, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1C, 0x1C, 0x00, 0x1C, 0x2F, 0x00, 0x06, 0x20, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x0B, 0x02, 0x00, 0x0B, 0x02, 0x00, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x18, 0x18, 0x01, 0x18, 0x18, 0x01, 0x18, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x33, 0x00, 0x08, 0x18, 0x04, 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1F, 0x0C, 0x08, 0x25, 0x06, 0x0E, 0x06, 0x00, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x0E, 0x00, 0x16, 0x16, 0x00, 0x1D, 0x20, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x18, 0x07, 0x06, 0x35, 0x10, 0x34, 0x05, 0x09, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x05, 0x09, 0x09, 0x09, 0x09, 0x01, 0x0D, 0x10, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x08, 0x25, 0x33, 0x2E, 0x06, 0x1B, 0x06, 0x00, 0x13, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1C, 0x00, 0x00, 0x1C, 0x00, 0x00, 0x1C, 0x00, 0x38, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1D, 0x3E, 0x05, 0x1D, 0x3E, 0x05, 0x1D, 0x3E, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1D, 0x20, 0x1D, 0x00, 0x18, 0x00, 0x33, 0x34, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x39, 0x3C, 0x21, 0x01, 0x3C, 0x01, 0x06, 0x1F, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x17, 0x03, 0x11, 0x13, 0x14, 0x00, 0x05, 0x35, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x05, 0x34, 0x00, 0x00, 0x34, 0x00, 0x00, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x38, 0x04, 0x02, 0x33, 0x00, 0x11, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0C, 0x00, 0x26, 0x33, 0x09, 0x09, 0x20, 0x08, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0F, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x27, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x30, 0x09, 0x20, 0x20, 0x06, 0x20, 0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x3A, 0x10, 0x2B, 0x18, 0x38, 0x38, 0x0E, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x16, 0x0C, 0x35, 0x05, 0x00, 0x00, 0x19, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x08, 0x1C, 0x18, 0x00, 0x1C, 0x00, 0x00, 0x05, 0x3A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x38, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x1F, 0x0C, 0x08, 0x25, 0x06, 0x08, 0x00, 0x00, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x1C, 0x05, 0x25, 0x1C, 0x25, 0x1F, 0x18, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x33, 0x20, 0x26, 0x0B, 0x02, 0x00, 0x34, 0x09, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x06, 0x36, 0x00, 0x00, 0x11, 0x24, 0x0B, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x20, 0x20, 0x00, 0x00, 0x39, 0x02, 0x08, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x08, 0x00, 0x40, 0x00, 0x00, 0x37, 0x08, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x20, 0x00, 0x35, 0x20, 0x05, 0x34, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x12, 0x14, 0x24, 0x34, 0x2E, 0x30, 0x1F, 0x06, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x05, 0x30, 0x04, 0x30, 0x2E, 0x06, 0x0E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x34, 0x34, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x06, 0x1B, 0x1F, 0x00, 0x00, 0x25, 0x00, 0x3B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x25, 0x10, 0x06, 0x00, 0x00, 0x0A, 0x10, 0x07, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0A, 0x10, 0x01, 0x00, 0x00, 0x00, 0x16, 0x19, 0x35, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x12, 0x10, 0x19, 0x10, 0x00, 0x00, 0x00, 0x3A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x11, 0x06, 0x09, 0x35, 0x16, 0x10, 0x40, 0x13, 0x0D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x24, 0x3E, 0x10, 0x0E, 0x12, 0x33, 0x03, 0x06, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x26, 0x00, 0x00, 0x27, 0x00, 0x00, 0x3B, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x0C, 0x0C, 0x20, 0x0A, 0x06, 0x11, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x18, 0x24, 0x06, 0x0A, 0x10, 0x18, 0x11, 0x24, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x10, 0x25, 0x05, 0x06, 0x3C, 0x05, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x06, 0x0C, 0x0C, 0x00, 0x00, 0x12, 0x24, 0x1D, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 
};
static_assert(and_amk_padding_is_zero(IK1303_AND_AMK_EXPANDED),
              "IK1303 AND_AMK padding contains data");
static constexpr PackedAndAmkTable IK1303_AND_AMK_STORAGE =
    pack_and_amk_table(IK1303_AND_AMK_EXPANDED);

static constexpr u8 IK1306_AND_AMK_EXPANDED[AND_AMK_RUNTIME_SIZE] = {
// 1     2     3     4     5     6     7     8     9     10    11    12    13    14    15    16  
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x2C, 0x2A, 0x27, 0x13, 0x2B, 0x27, 0x13, 0x2B, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x34, 0x2A, 0x27, 0x13, 0x2B, 0x27, 0x13, 0x2B, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x29, 0x2A, 0x35, 0x29, 0x2B, 0x35, 0x29, 0x2B, 0x35, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x29, 0x12, 0x35, 0x29, 0x42, 0x35, 0x29, 0x42, 0x35, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x2E, 0x00, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x2A, 0x02, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x12, 0x05, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x02, 0x00, 0x24, 0x02, 0x00, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x30, 0x1D, 0x05, 0x2F, 0x1D, 0x00, 0x00, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x22, 0x00, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0C, 0x00, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x24, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x31, 0x00, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x0E, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x0F, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x34, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x03, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x18, 0x25, 0x00, 0x03, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x03, 0x39, 0x00, 0x00, 0x00, 0x14, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x36, 0x00, 0x00, 0x03, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x03, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x37, 0x1E, 0x00, 0x00, 0x1E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x01, 0x06, 0x07, 0x01, 0x06, 0x07, 0x01, 0x06, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x34, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x3C, 0x00, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x40, 0x00, 0x00, 0x2D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x01, 0x25, 0x00, 0x01, 0x25, 0x00, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x04, 0x02, 0x03, 0x04, 0x02, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x01, 0x06, 0x07, 0x01, 0x06, 0x07, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x01, 0x04, 0x08, 0x01, 0x04, 0x08, 0x24, 0x00, 0x1A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x06, 0x09, 0x03, 0x06, 0x09, 0x24, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x25, 0x00, 0x03, 0x25, 0x00, 0x24, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x00, 0x38, 0x03, 0x00, 0x0B, 0x03, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x25, 0x00, 0x24, 0x25, 0x0E, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x25, 0x00, 0x03, 0x25, 0x00, 0x03, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x19, 0x05, 0x00, 0x19, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x29, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x21, 0x00, 0x00, 0x21, 0x24, 0x25, 0x03, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x0D, 0x02, 0x00, 0x0D, 0x02, 0x00, 0x0D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x17, 0x00, 0x00, 0x17, 0x24, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x00, 0x05, 0x24, 0x00, 0x05, 0x24, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x25, 0x00, 0x24, 0x25, 0x00, 0x24, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x13, 0x0A, 0x00, 0x00, 0x03, 0x0B, 0x00, 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x03, 0x05, 0x00, 0x03, 0x05, 0x00, 0x03, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x03, 0x00, 0x0B, 0x03, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x2C, 0x02, 0x00, 0x24, 0x02, 0x00, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x16, 0x00, 0x00, 0x16, 0x00, 0x00, 0x16, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x17, 0x00, 0x00, 0x17, 0x00, 0x00, 0x00, 0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x17, 0x00, 0x00, 0x17, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x29, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x14, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x13, 0x0A, 0x00, 0x00, 0x03, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x18, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x13, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x2A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x03, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x3B, 0x00, 0x00, 0x3B, 0x00, 0x12, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x00, 0x00, 0x0F, 0x00, 0x00, 0x05, 0x24, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x00, 0x25, 0x03, 0x00, 0x25, 0x03, 0x00, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x20, 0x00, 0x00, 0x20, 0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x11, 0x05, 0x00, 0x11, 0x05, 0x00, 0x11, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x11, 0x25, 0x00, 0x11, 0x25, 0x00, 0x11, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x00, 0x00, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x0F, 0x2A, 0x0F, 0x0F, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x1B, 0x1C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x15, 0x00, 0x03, 0x15, 0x00, 0x03, 0x15, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x02, 0x00, 0x00, 0x00, 0x00, 0x1B, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x03, 0x00, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x03, 0x12, 0x12, 0x12, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x24, 0x23, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x00, 0x24, 0x23, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x26, 0x27, 0x00, 0x28, 0x27, 0x00, 0x28, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x26, 0x27, 0x00, 0x28, 0x27, 0x00, 0x28, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x29, 0x2A, 0x27, 0x29, 0x2B, 0x27, 0x29, 0x2B, 0x3A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x12, 0x12, 0x12, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x12, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x0F, 0x00, 0x00, 0x0F, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x25, 0x00, 0x0E, 0x0F, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x0F, 0x00, 0x00, 0x0F, 0x0F, 0x0F, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0E, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x1D, 0x00, 0x00, 0x1D, 0x00, 0x00, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1F, 0x1A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x16, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x16, 0x05, 0x00, 0x16, 0x05, 0x00, 0x16, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x16, 0x02, 0x00, 0x16, 0x02, 0x00, 0x16, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x21, 0x02, 0x03, 0x21, 0x02, 0x03, 0x21, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x18, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x1B, 0x03, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x1B, 0x03, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x18, 0x03, 0x18, 0x05, 0x03, 0x18, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x00, 0x32, 0x03, 0x00, 0x32, 0x03, 0x00, 0x32, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x24, 0x33, 0x00, 0x00, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x21, 0x00, 0x00, 0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x2C, 0x2A, 0x27, 0x13, 0x2B, 0x27, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x03, 0x25, 0x00, 0x03, 0x25, 0x00, 0x13, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x3B, 0x05, 0x00, 0x3B, 0x05, 0x00, 0x3B, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x0D, 0x05, 0x00, 0x0D, 0x05, 0x00, 0x0D, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x13, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x18, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x17, 0x00, 0x00, 0x17, 0x0E, 0x05, 0x0D, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x18, 0x00, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x13, 0x09, 0x00, 0x00, 0x09, 0x00, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x0F, 0x02, 0x24, 0x25, 0x00, 0x24, 0x25, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x00, 0x00, 0x29, 0x0F, 0x0F, 0x0F, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x29, 0x12, 0x00, 0x29, 0x42, 0x00, 0x13, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x00, 0x3E, 0x00, 0x00, 0x3E, 0x00, 0x00, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x1B, 0x03, 0x00, 0x0B, 0x03, 0x0B, 0x13, 0x39, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x0E, 0x02, 0x00, 0x24, 0x02, 0x00, 0x13, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
  0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 
};
static_assert(and_amk_padding_is_zero(IK1306_AND_AMK_EXPANDED),
              "IK1306 AND_AMK padding contains data");
static constexpr PackedAndAmkTable IK1306_AND_AMK_STORAGE =
    pack_and_amk_table(IK1306_AND_AMK_EXPANDED);

#define IK1302_AND_AMK IK1302_AND_AMK_STORAGE.bytes
#define IK1303_AND_AMK IK1303_AND_AMK_STORAGE.bytes
#define IK1306_AND_AMK IK1306_AND_AMK_STORAGE.bytes

#if MK61_CORE_HOT_TABLES_IN_SRAM >= 1
struct alignas(8) CoreHotTables {
  microinstruction_t ik1302_microinstructions[68];
  microinstruction_t ik1303_microinstructions[68];
  microinstruction_t ik1306_microinstructions[68];
  u8 ik1302_dcw[68];
  u8 ik1302_dcwa[68];
  u8 ik1303_dcw[68];
  u8 ik1306_dcw[68];
#if MK61_CORE_HOT_TABLES_IN_SRAM >= 2
  u8 ik1302_and_amk[AND_AMK_RUNTIME_SIZE];
  u8 ik1303_and_amk[AND_AMK_RUNTIME_SIZE];
  u8 ik1306_and_amk[AND_AMK_RUNTIME_SIZE];
#endif
};

static_assert(sizeof(CoreHotTables) <= shared_memory::WORKSPACE_SIZE,
              "core hot tables do not fit shared workspace");

static shared_memory::Lease core_hot_tables_lease;
static CoreHotTables* core_hot_tables_memory = nullptr;
static bool core_hot_tables_cached = false;
static u32 core_hot_table_loads = 0;
static u32 core_hot_table_evictions = 0;
static u32 core_hot_table_flash_steps = 0;

static inline void increment_hot_table_counter(u32& counter) {
  if(counter != 0xFFFFFFFFUL) counter++;
}

// Keep the source tables in their canonical Flash objects. With whole-program
// LTO a series of constant-sized memcpy calls may otherwise be specialized
// into a second anonymous ~7 KiB constant pool, buying no runtime speed because
// this path runs only when the cache is (re)loaded.
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline, noclone))
#else
__attribute__((noinline))
#endif
static void copy_core_hot_table(void* destination, const void* source,
                                usize size) {
  memcpy(destination, source, size);
}

#if MK61_CORE_HOT_TABLES_IN_SRAM >= 2
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline, noclone))
#else
__attribute__((noinline))
#endif
static void expand_core_hot_and_amk(u8* destination, const u8* source) {
  memset(destination, 0, AND_AMK_RUNTIME_SIZE);
  for(usize body = 0; body < AND_AMK_BODY_COUNT; body++) {
    memcpy(destination + body * AND_AMK_RUNTIME_STRIDE,
           source + body * AND_AMK_PACKED_STRIDE,
           AND_AMK_PACKED_STRIDE);
  }
}
#endif

static const microinstruction_t* ik1302_microinstructions_active =
    ROM.IK1302.microinstructions;
static const microinstruction_t* ik1303_microinstructions_active =
    ROM.IK1303.microinstructions;
static const microinstruction_t* ik1306_microinstructions_active =
    ROM.IK1306.microinstructions;
static const u8* ik1302_dcw_active = IK1302_DCW;
static const u8* ik1302_dcwa_active = IK1302_DCWA;
static const u8* ik1303_dcw_active = IK1303_DCW;
static const u8* ik1306_dcw_active = IK1306_DCW;

#define IK1302_MICROINSTRUCTIONS_ACTIVE ik1302_microinstructions_active
#define IK1303_MICROINSTRUCTIONS_ACTIVE ik1303_microinstructions_active
#define IK1306_MICROINSTRUCTIONS_ACTIVE ik1306_microinstructions_active
#define IK1302_DCW_ACTIVE ik1302_dcw_active
#define IK1302_DCWA_ACTIVE ik1302_dcwa_active
#define IK1303_DCW_ACTIVE ik1303_dcw_active
#define IK1306_DCW_ACTIVE ik1306_dcw_active

#if MK61_CORE_HOT_TABLES_IN_SRAM >= 2
static const u8* ik1302_and_amk_active = IK1302_AND_AMK;
static const u8* ik1303_and_amk_active = IK1303_AND_AMK;
static const u8* ik1306_and_amk_active = IK1306_AND_AMK;
static usize and_amk_active_stride = AND_AMK_PACKED_STRIDE;
#define IK1302_AND_AMK_ACTIVE ik1302_and_amk_active
#define IK1303_AND_AMK_ACTIVE ik1303_and_amk_active
#define IK1306_AND_AMK_ACTIVE ik1306_and_amk_active
#define AND_AMK_ACTIVE_STRIDE and_amk_active_stride
#else
#define IK1302_AND_AMK_ACTIVE IK1302_AND_AMK
#define IK1303_AND_AMK_ACTIVE IK1303_AND_AMK
#define IK1306_AND_AMK_ACTIVE IK1306_AND_AMK
#define AND_AMK_ACTIVE_STRIDE AND_AMK_PACKED_STRIDE
#endif

static bool pointer_offset(const u8* pointer, const u8* base,
                           usize size, usize& offset) {
  if(pointer == nullptr || base == nullptr) return false;
  const uintptr_t address = (uintptr_t) pointer;
  const uintptr_t begin = (uintptr_t) base;
  if(address < begin || address - begin >= size) return false;
  offset = (usize) (address - begin);
  return true;
}

static bool and_amk_pointer_body(const u8* pointer, const u8* base,
                                 usize stride, usize& body) {
  usize offset = 0;
  if(!pointer_offset(
       pointer, base, AND_AMK_BODY_COUNT * stride, offset) ||
     offset % stride != 0) return false;
  body = offset / stride;
  return true;
}

static const u8* rebase_and_amk_pointer(
    const u8* pointer, const u8* flash_base, const u8* ram_base,
    const u8* target_base, usize target_stride) {
  usize body = 0;
  if(and_amk_pointer_body(
       pointer, flash_base, AND_AMK_PACKED_STRIDE, body) ||
     and_amk_pointer_body(
       pointer, ram_base, AND_AMK_RUNTIME_STRIDE, body)) {
    return target_base + body * target_stride;
  }
  return pointer;
}

static void select_core_hot_table_view(bool use_workspace) {
  CoreHotTables* const tables = core_hot_tables_memory;
  const bool use_ram = use_workspace && tables != nullptr;
  ik1302_microinstructions_active = use_ram
      ? tables->ik1302_microinstructions : ROM.IK1302.microinstructions;
  ik1303_microinstructions_active = use_ram
      ? tables->ik1303_microinstructions : ROM.IK1303.microinstructions;
  ik1306_microinstructions_active = use_ram
      ? tables->ik1306_microinstructions : ROM.IK1306.microinstructions;
  ik1302_dcw_active = use_ram ? tables->ik1302_dcw : IK1302_DCW;
  ik1302_dcwa_active = use_ram ? tables->ik1302_dcwa : IK1302_DCWA;
  ik1303_dcw_active = use_ram ? tables->ik1303_dcw : IK1303_DCW;
  ik1306_dcw_active = use_ram ? tables->ik1306_dcw : IK1306_DCW;

#if MK61_CORE_HOT_TABLES_IN_SRAM >= 2
  const u8* const ram1302 = tables == nullptr
      ? nullptr : tables->ik1302_and_amk;
  const u8* const ram1303 = tables == nullptr
      ? nullptr : tables->ik1303_and_amk;
  const u8* const ram1306 = tables == nullptr
      ? nullptr : tables->ik1306_and_amk;
  const u8* const next1302 = use_ram ? ram1302 : IK1302_AND_AMK;
  const u8* const next1303 = use_ram ? ram1303 : IK1303_AND_AMK;
  const u8* const next1306 = use_ram ? ram1306 : IK1306_AND_AMK;
  const usize next_stride = use_ram
      ? AND_AMK_RUNTIME_STRIDE : AND_AMK_PACKED_STRIDE;
  m_IK1302.pAND_AMK = rebase_and_amk_pointer(
      m_IK1302.pAND_AMK, IK1302_AND_AMK, ram1302, next1302,
      next_stride);
  m_IK1302.pAND_AMK1 = rebase_and_amk_pointer(
      m_IK1302.pAND_AMK1, IK1302_AND_AMK, ram1302, next1302,
      next_stride);
  m_IK1303.pAND_AMK = rebase_and_amk_pointer(
      m_IK1303.pAND_AMK, IK1303_AND_AMK, ram1303, next1303,
      next_stride);
  m_IK1303.pAND_AMK1 = rebase_and_amk_pointer(
      m_IK1303.pAND_AMK1, IK1303_AND_AMK, ram1303, next1303,
      next_stride);
  m_IK1306.pAND_AMK = rebase_and_amk_pointer(
      m_IK1306.pAND_AMK, IK1306_AND_AMK, ram1306, next1306,
      next_stride);
  m_IK1306.pAND_AMK1 = rebase_and_amk_pointer(
      m_IK1306.pAND_AMK1, IK1306_AND_AMK, ram1306, next1306,
      next_stride);
  ik1302_and_amk_active = next1302;
  ik1303_and_amk_active = next1303;
  ik1306_and_amk_active = next1306;
  and_amk_active_stride = next_stride;
#endif
  core_hot_tables_cached = use_ram;
}

static shared_memory::EvictionDecision prepare_core_hot_table_eviction(void) {
  select_core_hot_table_view(false);
  increment_hot_table_counter(core_hot_table_evictions);
  return shared_memory::EvictionDecision::RELEASE;
}

static bool ensure_core_hot_tables(void) {
  if(core_hot_tables_lease.ok()) return true;
  if(!workspace_swap::acquire(
       shared_memory::Owner::CORE_TABLES, sizeof(CoreHotTables),
       workspace_swap::AcquireMode::OPPORTUNISTIC,
       core_hot_tables_lease)) return false;
  CoreHotTables* const tables = core_hot_tables_lease.as<CoreHotTables>();
  if(tables == nullptr) {
    core_hot_tables_lease.reset();
    return false;
  }
  core_hot_tables_memory = tables;
  if(core_hot_tables_lease.fresh()) {
    copy_core_hot_table(
        tables->ik1302_microinstructions, ROM.IK1302.microinstructions,
        sizeof(tables->ik1302_microinstructions));
    copy_core_hot_table(
        tables->ik1303_microinstructions, ROM.IK1303.microinstructions,
        sizeof(tables->ik1303_microinstructions));
    copy_core_hot_table(
        tables->ik1306_microinstructions, ROM.IK1306.microinstructions,
        sizeof(tables->ik1306_microinstructions));
    copy_core_hot_table(
        tables->ik1302_dcw, IK1302_DCW, sizeof(tables->ik1302_dcw));
    copy_core_hot_table(
        tables->ik1302_dcwa, IK1302_DCWA, sizeof(tables->ik1302_dcwa));
    copy_core_hot_table(
        tables->ik1303_dcw, IK1303_DCW, sizeof(tables->ik1303_dcw));
    copy_core_hot_table(
        tables->ik1306_dcw, IK1306_DCW, sizeof(tables->ik1306_dcw));
#if MK61_CORE_HOT_TABLES_IN_SRAM >= 2
    expand_core_hot_and_amk(tables->ik1302_and_amk, IK1302_AND_AMK);
    expand_core_hot_and_amk(tables->ik1303_and_amk, IK1303_AND_AMK);
    expand_core_hot_and_amk(tables->ik1306_and_amk, IK1306_AND_AMK);
#endif
    increment_hot_table_counter(core_hot_table_loads);
  }
  select_core_hot_table_view(true);
  if(!core_hot_tables_lease.set_evictable(
       prepare_core_hot_table_eviction)) {
    select_core_hot_table_view(false);
    core_hot_tables_lease.reset();
    return false;
  }
  return true;
}

static void init_core_hot_tables(void) {
  if(!ensure_core_hot_tables()) select_core_hot_table_view(false);
}

static inline void prepare_core_hot_tables_for_step(void) {
  if(!ensure_core_hot_tables()) increment_hot_table_counter(
      core_hot_table_flash_steps);
}
static inline bool core_hot_tables_view_cached(void) {
  return core_hot_tables_lease.ok();
}
#else
#define IK1302_MICROINSTRUCTIONS_ACTIVE ROM.IK1302.microinstructions
#define IK1303_MICROINSTRUCTIONS_ACTIVE ROM.IK1303.microinstructions
#define IK1306_MICROINSTRUCTIONS_ACTIVE ROM.IK1306.microinstructions
#define IK1302_DCW_ACTIVE IK1302_DCW
#define IK1302_DCWA_ACTIVE IK1302_DCWA
#define IK1303_DCW_ACTIVE IK1303_DCW
#define IK1306_DCW_ACTIVE IK1306_DCW
#define IK1302_AND_AMK_ACTIVE IK1302_AND_AMK
#define IK1303_AND_AMK_ACTIVE IK1303_AND_AMK
#define IK1306_AND_AMK_ACTIVE IK1306_AND_AMK
#define AND_AMK_ACTIVE_STRIDE AND_AMK_PACKED_STRIDE

static inline void init_core_hot_tables(void) {}
static inline bool ensure_core_hot_tables(void) { return false; }
static inline void select_core_hot_table_view(bool) {}
static inline void prepare_core_hot_tables_for_step(void) {}
static inline bool core_hot_tables_view_cached(void) { return false; }
#endif

static inline const u8* and_amk_body(const u8* base, usize body) {
  return base + body * AND_AMK_ACTIVE_STRIDE;
}

// TODO: удалить static
#if MK61_DWT_CORE_DETAIL_SUPPORTED
inline void __attribute__((always_inline)) _CycleE(
    int J_signal_I, mtick_t &signal_I,
    dwt_profiler::Accumulator& ik1302_time,
    dwt_profiler::Accumulator& ik1303_time,
    dwt_profiler::Accumulator& ik1306_time) {
  const mtick_t signal_div3 = DIV3(signal_I);
  if(!ik1302_time.active()) {
    IK1302_Tick(signal_I, J_signal_I, signal_div3);
    IK1303_Tick(signal_I, J_signal_I, signal_div3);
    IK1306_Tick(signal_I, J_signal_I);
    return;
  }
  {
    MK61_PROFILE_ACCUMULATE_SCOPE(ik1302_time);
    IK1302_Tick(signal_I, J_signal_I, signal_div3);
  }
  {
    MK61_PROFILE_ACCUMULATE_SCOPE(ik1303_time);
    IK1303_Tick(signal_I, J_signal_I, signal_div3);
  }
  {
    MK61_PROFILE_ACCUMULATE_SCOPE(ik1306_time);
    IK1306_Tick(signal_I, J_signal_I);
  }
}

// TODO: удалить
inline void __attribute__((always_inline)) _CycleB(
    int J_signal_I, mtick_t &signal_I,
    dwt_profiler::Accumulator& ik1302_time,
    dwt_profiler::Accumulator& ik1303_time,
    dwt_profiler::Accumulator& ik1306_time) {
    _CycleE(J_signal_I, signal_I, ik1302_time, ik1303_time, ik1306_time);
    signal_I++;
}

#if MK61_CORE_NATIVE_HOT_PATHS
inline void __attribute__((always_inline)) _CycleEWithoutIK1306(
    int J_signal_I, mtick_t &signal_I,
    dwt_profiler::Accumulator& ik1302_time,
    dwt_profiler::Accumulator& ik1303_time) {
  const mtick_t signal_div3 = DIV3(signal_I);
  if(!ik1302_time.active()) {
    IK1302_Tick(signal_I, J_signal_I, signal_div3);
    IK1303_Tick(signal_I, J_signal_I, signal_div3);
    return;
  }
  {
    MK61_PROFILE_ACCUMULATE_SCOPE(ik1302_time);
    IK1302_Tick(signal_I, J_signal_I, signal_div3);
  }
  {
    MK61_PROFILE_ACCUMULATE_SCOPE(ik1303_time);
    IK1303_Tick(signal_I, J_signal_I, signal_div3);
  }
}

inline void __attribute__((always_inline)) _CycleBWithoutIK1306(
    int J_signal_I, mtick_t &signal_I,
    dwt_profiler::Accumulator& ik1302_time,
    dwt_profiler::Accumulator& ik1303_time) {
  _CycleEWithoutIK1306(
      J_signal_I, signal_I, ik1302_time, ik1303_time);
  signal_I++;
}
#endif

#define CycleE(J_signal_I) \
  _CycleE(J_signal_I, signal_I, ik1302_time, ik1303_time, ik1306_time)
#define CycleB(J_signal_I) \
  _CycleB(J_signal_I, signal_I, ik1302_time, ik1303_time, ik1306_time)
#if MK61_CORE_NATIVE_HOT_PATHS
  #define CycleEWithoutIK1306(J_signal_I) \
    _CycleEWithoutIK1306( \
        J_signal_I, signal_I, ik1302_time, ik1303_time)
  #define CycleBWithoutIK1306(J_signal_I) \
    _CycleBWithoutIK1306( \
        J_signal_I, signal_I, ik1302_time, ik1303_time)
#endif
#else
inline void __attribute__((always_inline)) _CycleE(int J_signal_I, mtick_t &signal_I) {
    const mtick_t signal_div3 = DIV3(signal_I);
#if MK61_CORE_MERGED_TICK
    IK130X_Tick_All(signal_I, J_signal_I, signal_div3);
#else
    IK1302_Tick(signal_I, J_signal_I, signal_div3);
    IK1303_Tick(signal_I, J_signal_I, signal_div3);
    IK1306_Tick(signal_I, J_signal_I);
#endif
}

// TODO: удалить
inline void __attribute__((always_inline)) _CycleB(int J_signal_I, mtick_t &signal_I) {
    _CycleE(J_signal_I, signal_I);
    signal_I++;
}

#if MK61_CORE_NATIVE_HOT_PATHS
inline void __attribute__((always_inline)) _CycleEWithoutIK1306(
    int J_signal_I, mtick_t &signal_I) {
  const mtick_t signal_div3 = DIV3(signal_I);
#if MK61_CORE_MERGED_TICK
  IK1302_1303_Tick_All(signal_I, J_signal_I, signal_div3);
#else
  IK1302_Tick(signal_I, J_signal_I, signal_div3);
  IK1303_Tick(signal_I, J_signal_I, signal_div3);
#endif
}

inline void __attribute__((always_inline)) _CycleBWithoutIK1306(
    int J_signal_I, mtick_t &signal_I) {
  _CycleEWithoutIK1306(J_signal_I, signal_I);
  signal_I++;
}
#endif

#define CycleE(J_signal_I)  _CycleE(J_signal_I, signal_I)
#define CycleB(J_signal_I)  _CycleB(J_signal_I, signal_I)
#if MK61_CORE_NATIVE_HOT_PATHS
  #define CycleEWithoutIK1306(J_signal_I) \
    _CycleEWithoutIK1306(J_signal_I, signal_I)
  #define CycleBWithoutIK1306(J_signal_I) \
    _CycleBWithoutIK1306(J_signal_I, signal_I)
#endif
#endif

#ifdef out_dump

uint16_t step = 0;

void dumpm(uint16_t sig, uint16_t cyc) {
 uint16_t i;
        printf("st %2.2d cy %3.3d si %2.2d\n(%d,%d)1302 R dump:\n",step,cyc,sig,IK1302_key_x,IK1302_key_y);
        for(i=0;i<42;i++){
                if((i % 15) == 0) printf("\n%2.2X ", i);
                printf("%2.2X ", IK1302_R[i]);
        }/*
        printf("\n\nIK1302 M dump: \n\n");
        for(i=0;i<42;i++){
                if((i % 15) == 0) printf("\n\n %4.4X ", i);
                printf("%2.2X ", m_IK1302.M[i]);
        }*/
        printf("\n1303 R dump:\n");
        for(i=0;i<42;i++){
                if((i % 15) == 0) printf("\n%2.2X ", i);
                printf("%2.2X ", m_IK1303.R[i]);
        }/*
        printf("\n\nIK1303 M dump: \n\n");
        for(i=0;i<42;i++){
                if((i % 15) == 0) printf("\n\n %4.4X ", i);
                printf("%2.2X ", m_IK1303.M[i]);
        }*/
        printf("\n1306 R dump:\n");
        for(i=0;i<42;i++){
                if((i % 15) == 0) printf("\n%2.2X ", i);
                printf("%2.2X ", IK1306_R[i]);
        }/*
        printf("\n\nIK1306 M dump: \n\n");
        for(i=0;i<42;i++){
                if((i % 15) == 0) printf("\n\n %4.4X ", i);
                printf("%2.2X ", m_IK1306.M[i]);
        }

                        printf("\n\nIR2.1 M dump: \n\n");
                        for(i=0;i<252;i++){
                                if((i % 15) == 0) printf("\n\n %4.4X ", i);
                                printf("%2.2X ", IR2_1.M[i]);
                        }
                        printf("\n\nIR2.2 M dump: \n\n");
                        for(i=0;i<252;i++){
                                if((i % 15) == 0) printf("\n\n %4.4X ", i);
                                printf("%2.2X ", IR2_2.M[i]);
                        }*/
        puts("\n");
}
#endif

inline bool __attribute__((always_inline)) IK1302_GoZero(
    usize& instruction_hi) {
    const u8 address = (u8) ((uint16_t) m_IK1302.R[36] + 16U * (uint16_t) m_IK1302.R[39]);
    if(handle_mk61_command_prefetch(address)) return false;
    const u8 command = apply_rom_command_hooks(
        core_61::RomChip::IK1302, address, m_IK1302.R, m_IK1302.ST);
    uint32_t uI = ROM.IK1302.instructions[command]; // читаем команду
    profile_instruction(core_61::RomChip::IK1302, uI);
    const usize uI_hi = uI >> 16;


    m_IK1302.pAND_AMK = and_amk_body(
        IK1302_AND_AMK_ACTIVE, uI & 0xFFU);
    m_IK1302.pAND_AMK1 = and_amk_body(
        IK1302_AND_AMK_ACTIVE, (uI >> 8) & 0xFFU);

    m_IK1302.MOD = (uint8_t) (uI >> 24);                                              // получаем из 4-ого байта команды модификатор
    m_IK1302.flag_FC = uI_hi & 0x000000FC;
    if (m_IK1302.flag_FC== 0) m_IK1302.T = 0;

    m_IK1302.key_xm = m_IK1302.key_x - 1;
  
  instruction_hi = uI_hi & 0xFF;
  return true; // от команды остался нужен только 3-ий байт из которого будет получен адрес микропрограммы-3
}

inline  usize __attribute__((always_inline))  IK1303_GoZero(void) {
    const u8 address = (u8) ((uint16_t) m_IK1303.R[36] + 16U * (uint16_t) m_IK1303.R[39]);
    const u8 command = apply_rom_command_hooks(
        core_61::RomChip::IK1303, address, m_IK1303.R, m_IK1303.ST);
    uint32_t uI = ROM.IK1303.instructions[command];
    profile_instruction(core_61::RomChip::IK1303, uI);
    const usize uI_hi = uI >> 16;

    m_IK1303.pAND_AMK = and_amk_body(
        IK1303_AND_AMK_ACTIVE, uI & 0xFFU);
    m_IK1303.pAND_AMK1 = and_amk_body(
        IK1303_AND_AMK_ACTIVE, (uI >> 8) & 0xFFU);

    m_IK1303.MOD = (uint8_t) (uI >> 24);
    m_IK1303.flag_FC = uI_hi & 0x000000FC;
    if (m_IK1303.flag_FC == 0) m_IK1303.T = 0;

    m_IK1303.key_xm = m_IK1303.key_x - 1;
  
  return uI_hi & 0xFF;
}

inline instruction_t __attribute__((always_inline)) IK1306_GoZero(void) {
    const u8 address = (u8) (m_IK1306.R[36] + 16U * m_IK1306.R[39]);
    const u8 command = apply_rom_command_hooks(
        core_61::RomChip::IK1306, address, m_IK1306.R, m_IK1306.ST);
    uint32_t uI = ROM.IK1306.instructions[command];
    profile_instruction(core_61::RomChip::IK1306, uI);

    m_IK1306.pAND_AMK = and_amk_body(
        IK1306_AND_AMK_ACTIVE, uI & 0xFFU);
    m_IK1306.pAND_AMK1 = and_amk_body(
        IK1306_AND_AMK_ACTIVE, (uI >> 8) & 0xFFU);

    m_IK1306.MOD = (uint8_t) (uI >> 24);

  return uI;
}

inline u64 __attribute__((always_inline)) random_avalanche(u64 value) {
  value ^= value >> 30;
  value *= 0xBF58476D1CE4E5B9ULL;
  value ^= value >> 27;
  value *= 0x94D049BB133111EBULL;
  return value ^ (value >> 31);
}

inline u32 __attribute__((always_inline)) next_external_random_seed(void) {
  external_random_state += 0x9E3779B97F4A7C15ULL;
  return 1U + (u32) (random_avalanche(external_random_state) % 9999999ULL);
}

static void inject_external_random_seed(
    core_61::RomCommandHookContext& context, void*) {
  if(!external_random_enabled || !external_random_pending) return;
  external_random_pending = false;
  // Эти индексы ST представляют xi только в обработчике выборки перед A7.
  // Следующая команда ПЗУ сразу их использует; ST не является постоянным
  // регистром xi. Нибблы порядка и служебные нибблы 999 входят в допустимый
  // последовательный формат BCD.
  u32 seed = next_external_random_seed();
  context.st[1] = 0;
  context.st[4] = seed % 10U; seed /= 10U;  // d7
  context.st[7] = seed % 10U; seed /= 10U;  // d6
  context.st[10] = seed % 10U; seed /= 10U; // d5
  context.st[13] = seed % 10U; seed /= 10U; // d4
  context.st[16] = seed % 10U; seed /= 10U; // d3
  context.st[19] = seed % 10U; seed /= 10U; // d2
  context.st[22] = seed % 10U;               // d1
  context.st[25] = 0;
  context.st[28] = 9;
  context.st[31] = 9;
  context.st[34] = 9;
  context.st[37] = 0;
  context.st[40] = 0;
}

static void arm_external_random_seed(
    core_61::Mk61CommandHookContext& context, void*) {
  if(external_random_enabled &&
     context.phase == core_61::Mk61CommandHookPhase::BEFORE_EXECUTE &&
     context.replacement_opcode == 0x3BU) {
    external_random_pending = true;
  }
}

#if MK61_CORE_PREDECODED_ROM
template<unsigned A, unsigned B>
static void MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))
native_ik1302_1303_region3();
#if !defined(ARDUINO)
// Host-only coverage; no counter or diagnostic command in firmware.
static u64 native_sequence_hits = 0;
#endif
#endif

void MK61_CORE_HOT_O3 cycle(void) {
  mtick_t signal_I;
  const int MAX_CYCLE = (sergey_anvarov_hack_enable)? 280 : 560;
  const u8* active_end_ring_m = &ringM[core_61::ring_size()];
  dwt_profiler::Accumulator fetch_time(dwt_profiler::Point::CORE_FETCH);
  dwt_profiler::Accumulator ticks_00_26_time(
      dwt_profiler::Point::CORE_TICKS_00_26);
  dwt_profiler::Accumulator ticks_27_35_time(
      dwt_profiler::Point::CORE_TICKS_27_35);
  dwt_profiler::Accumulator ticks_36_41_time(
      dwt_profiler::Point::CORE_TICKS_36_41);
#if MK61_DWT_CORE_DETAIL_SUPPORTED
  dwt_profiler::Accumulator ik1302_time(dwt_profiler::Point::CORE_IK1302);
  dwt_profiler::Accumulator ik1303_time(dwt_profiler::Point::CORE_IK1303);
  dwt_profiler::Accumulator ik1306_time(dwt_profiler::Point::CORE_IK1306);
#endif
  for (int count = 1; count <= MAX_CYCLE; count++){
      signal_I = 0;

      usize IK1302_uI_hi = 0;
      usize IK1303_uI_hi;
      instruction_t IK1306_uI;
      usize IK1306_uI_hi;
      {
        MK61_PROFILE_ACCUMULATE_SCOPE(fetch_time);
        if(!IK1302_GoZero(IK1302_uI_hi)) {
          mk61_program_boundary_yielded = true;
          return;
        }

        dbgtrace(CORE61, "IK1302.IP = 0x", m_IK1302.R[39]*16 + m_IK1302.R[36]);

        IK1303_uI_hi = IK1303_GoZero();
        IK1306_uI = IK1306_GoZero();
        IK1306_uI_hi = (IK1306_uI >> 16) & 0xFFU;
      }
#if defined(MK61_CORE_TEST_BOUNDARY) && !defined(ARDUINO)
      // Host-only lockstep observation; absent from firmware, including SRAM.
      MK61_CORE_TEST_BOUNDARY(count, 0);
#endif

      #ifdef out_dump
      dumpm(signal_I, count);
      #endif

      {
          MK61_PROFILE_ACCUMULATE_SCOPE(ticks_00_26_time);
#if MK61_CORE_NATIVE_HOT_PATHS
          if(native_hot_paths_are_enabled && (u8) IK1306_uI == 0) {
#if MK61_CORE_UNROLL_SCHEDULE
            #pragma GCC unroll 99
#endif
            for (auto _ : {0,1,2,3,4,5, 3,4,5,3,4,5, 3,4,5,3,4,5,
                           3,4,5,3,4,5, 6,7,8}) {
              CycleBWithoutIK1306(_);
            }
#if MK61_DWT_CORE_DETAIL_SUPPORTED
            {
              MK61_PROFILE_ACCUMULATE_SCOPE(ik1306_time);
              native_ik1306_zero_body(
                  core_61::NativeHotPath::IK1306_ZERO_REGION1);
            }
#else
            native_ik1306_zero_body(
                core_61::NativeHotPath::IK1306_ZERO_REGION1);
#endif
          } else if(native_hot_paths_are_enabled && (u8) IK1306_uI == 0x40U) {
            for(auto j : {0,1,2,3,4,5, 3,4,5,3,4,5, 3,4,5,3,4,5,
                          3,4,5,3,4,5, 6,7,8}) {
              const mtick_t current = signal_I;
              CycleBWithoutIK1306(j);
#if MK61_DWT_CORE_DETAIL_SUPPORTED
              MK61_PROFILE_ACCUMULATE_SCOPE(ik1306_time);
#endif
              native_ik1306_wait_tick(current, j);
            }
            count_native_hot_path(core_61::NativeHotPath::IK1306_WAIT_REGION1);
          } else
#endif
          {
#if MK61_CORE_UNROLL_SCHEDULE
            #pragma GCC unroll 99
#endif
            for (auto _ : {0,1,2,3,4,5, 3,4,5,3,4,5, 3,4,5,3,4,5,
                           3,4,5,3,4,5, 6,7,8}) {
              CycleB(_);
            }
          } // 0..26
      }
#if defined(MK61_CORE_TEST_BOUNDARY) && !defined(ARDUINO)
      MK61_CORE_TEST_BOUNDARY(count, 27);
#endif

      {
          MK61_PROFILE_ACCUMULATE_SCOPE(ticks_27_35_time);
          m_IK1302.pAND_AMK = m_IK1302.pAND_AMK1;
          m_IK1303.pAND_AMK = m_IK1303.pAND_AMK1;
          m_IK1306.pAND_AMK = m_IK1306.pAND_AMK1;

#if MK61_CORE_NATIVE_HOT_PATHS
          if(native_hot_paths_are_enabled &&
             (u8) (IK1306_uI >> 8) == 0) {
#if MK61_CORE_UNROLL_SCHEDULE
            #pragma GCC unroll 99
#endif
            for (auto _ : {0,1,2, 3,4,5,6,7,8}) {
              CycleBWithoutIK1306(_);
            }
#if MK61_DWT_CORE_DETAIL_SUPPORTED
            {
              MK61_PROFILE_ACCUMULATE_SCOPE(ik1306_time);
              native_ik1306_zero_body(
                  core_61::NativeHotPath::IK1306_ZERO_REGION2);
            }
#else
            native_ik1306_zero_body(
                core_61::NativeHotPath::IK1306_ZERO_REGION2);
#endif
          } else
#endif
          {
#if MK61_CORE_UNROLL_SCHEDULE
            #pragma GCC unroll 99
#endif
            for (auto _ : {0,1,2, 3,4,5,6,7,8}) {
              CycleB(_);
            }
          } // 27..35
      }
#if defined(MK61_CORE_TEST_BOUNDARY) && !defined(ARDUINO)
      MK61_CORE_TEST_BOUNDARY(count, 36);
#endif

      {
          MK61_PROFILE_ACCUMULATE_SCOPE(ticks_36_41_time);
          // signal == 36
          if (IK1302_uI_hi > 0x1f)  { // рассматриваем 3-й байт команды
              m_IK1302.R[37] = IK1302_uI_hi & 0xf;   // signal == 36
              m_IK1302.R[40] = IK1302_uI_hi >> 4;    // signal == 36
              m_IK1302.pAND_AMK = and_amk_body(
                  IK1302_AND_AMK_ACTIVE, 0x5FU);
          } else  {
              m_IK1302.pAND_AMK = and_amk_body(
                  IK1302_AND_AMK_ACTIVE, IK1302_uI_hi);
          }

          if (IK1303_uI_hi > 0x1f)  {
              m_IK1303.R[37] = IK1303_uI_hi & 0xf;   // signal == 36
              m_IK1303.R[40] = IK1303_uI_hi >> 4;    // signal == 36
              m_IK1303.pAND_AMK = and_amk_body(
                  IK1303_AND_AMK_ACTIVE, 0x5FU);
          } else  {
               m_IK1303.pAND_AMK = and_amk_body(
                   IK1303_AND_AMK_ACTIVE, IK1303_uI_hi);
          }

          if (IK1306_uI_hi > 0x1f)  {
              m_IK1306.R[37] = IK1306_uI_hi & 0xf;   // signal == 36
              m_IK1306.R[40] = IK1306_uI_hi >> 4;    // signal == 36
              m_IK1306.pAND_AMK = and_amk_body(
                  IK1306_AND_AMK_ACTIVE, 0x5FU);
          } else  {
               m_IK1306.pAND_AMK = and_amk_body(
                   IK1306_AND_AMK_ACTIVE, IK1306_uI_hi);
          }

#if MK61_CORE_NATIVE_HOT_PATHS
          const u8 IK1306_region3 = region3_microprogram(
              (u8) IK1306_uI_hi);
          if(native_hot_paths_are_enabled &&
             (IK1306_region3 == 0x06U || IK1306_region3 == 0x07U ||
              IK1306_region3 == 0x09U)) {
#if MK61_CORE_PREDECODED_ROM
            if(IK1302_uI_hi <= 1U && IK1303_uI_hi == 0x13U
#if MK61_DWT_CORE_DETAIL_SUPPORTED
                && !ik1302_time.active()
#endif
            ) {
              if(IK1302_uI_hi == 0)
                native_ik1302_1303_region3<0, 0x13>();
              else
                native_ik1302_1303_region3<1, 0x13>();
              signal_I = 41;
            } else
#endif
            {
              CycleBWithoutIK1306(0); // 36
              CycleBWithoutIK1306(1); // 37
              CycleBWithoutIK1306(2); // 38
              CycleBWithoutIK1306(3); // 39
              CycleBWithoutIK1306(4); // 40
              CycleEWithoutIK1306(5); // 41
            }
#if MK61_DWT_CORE_DETAIL_SUPPORTED
            {
              MK61_PROFILE_ACCUMULATE_SCOPE(ik1306_time);
              if(IK1306_region3 == 0x06U)
                native_ik1306_region3_06();
              else if(IK1306_region3 == 0x07U)
                native_ik1306_region3_07();
              else
                native_ik1306_region3_09();
            }
#else
            if(IK1306_region3 == 0x06U)
              native_ik1306_region3_06();
            else if(IK1306_region3 == 0x07U)
              native_ik1306_region3_07();
            else
              native_ik1306_region3_09();
#endif
          } else
#endif
          {
            CycleB(0);   // 36
            CycleB(1);   // 37
            CycleB(2);   // 38
            CycleB(3);   // 39
            CycleB(4);   // 40
            CycleE(5);   // 41
          }
#if defined(MK61_CORE_TEST_BOUNDARY) && !defined(ARDUINO)
          MK61_CORE_TEST_BOUNDARY(count, 42);
#endif

          m_IK1302.pM += 42;
          m_IK1303.pM += 42;
          m_IK1306.pM += 42;
          if(m_IK1302.pM == active_end_ring_m){
                  m_IK1302.pM = &ringM[0];
          }
          else if(m_IK1303.pM == active_end_ring_m){
                  m_IK1303.pM = &ringM[0];
          }
          else if(m_IK1306.pM == active_end_ring_m){
                   m_IK1306.pM = &ringM[0];
          }
#if defined(MK61_CORE_TEST_BOUNDARY) && !defined(ARDUINO)
          // 43 denotes transport after all 42 ticks, not an extra microtick.
          MK61_CORE_TEST_BOUNDARY(count, 43);
#endif
      }
  }
#ifdef out_dump
  step++;
#endif
}

inline void __attribute__((always_inline))  dump_1302(mtick_t signal_I, usize J_signal_I) {
  // Вывод дампа отладочной информации 
  dbg(CORE61, "I:", signal_I, " J:",  J_signal_I, " 1302.R[");
  for(u8 R : m_IK1302.R) dbghex(CORE61, ".", R);
  dbg(CORE61, "]\n 1302.ST[");
  for(u8 ST : m_IK1302.ST) dbghex(CORE61, ".", ST);
  dbghexln(CORE61, "]\n pM = $", (usize) m_IK1302.pM - (usize) &ringM[0], " pAND_AMK = $", (usize) m_IK1302.pAND_AMK - (usize) IK1302_AND_AMK_ACTIVE, " pAND_AMK1 = $", (usize) m_IK1302.pAND_AMK1 - (usize) IK1302_AND_AMK_ACTIVE);
  dbghexln(CORE61, "AMK = ", m_IK1302.AMK);
  dbghex(CORE61, "FLAGS L ", m_IK1302.L);
  dbghex(CORE61, ":S ", m_IK1302.S);
  dbghex(CORE61, ":S1 ", m_IK1302.S1);
  dbghex(CORE61, ":P ", m_IK1302.P);
  dbghex(CORE61, ":T ", m_IK1302.T);
  dbghex(CORE61, ":MOD ", m_IK1302.MOD);
  dbghexln(CORE61, ":flag_FC ", m_IK1302.flag_FC);
}

// All 68 ROM microinstructions, independent of the calculator program.
// Keep one semantic implementation per chip for constant and scalar inputs.
#if MK61_CORE_PREDECODED_ROM
#define MK61_CORE_ROM_CASES(F) \
  F(0x00) F(0x01) F(0x02) F(0x03) F(0x04) F(0x05) F(0x06) F(0x07) \
  F(0x08) F(0x09) F(0x0A) F(0x0B) F(0x0C) F(0x0D) F(0x0E) F(0x0F) \
  F(0x10) F(0x11) F(0x12) F(0x13) F(0x14) F(0x15) F(0x16) F(0x17) \
  F(0x18) F(0x19) F(0x1A) F(0x1B) F(0x1C) F(0x1D) F(0x1E) F(0x1F) \
  F(0x20) F(0x21) F(0x22) F(0x23) F(0x24) F(0x25) F(0x26) F(0x27) \
  F(0x28) F(0x29) F(0x2A) F(0x2B) F(0x2C) F(0x2D) F(0x2E) F(0x2F) \
  F(0x30) F(0x31) F(0x32) F(0x33) F(0x34) F(0x35) F(0x36) F(0x37) \
  F(0x38) F(0x39) F(0x3A) F(0x3B) F(0x3C) F(0x3D) F(0x3E) F(0x3F) \
  F(0x40) F(0x41) F(0x42) F(0x43)
#endif

static inline void __attribute__((always_inline)) IK1302_Execute(
    mtick_t signal_I, mtick_t signal_div3, u32 microinstruction, u32 dcw, u32 dcwa) {
  u32 tmp, mi_hi, val;
  mi_hi = (microinstruction >> 16);
  //---------------------------------------------------------
    if((((microinstruction >> 24) & 0x03) == 0x2) || (((microinstruction >> 24) & 0x03) == 0x3)) {
        if (signal_div3 != m_IK1302.key_xm)
           m_IK1302.S1 |= m_IK1302.key_y;
    }
  //---------------------------------------------------------
    io_t alpha = 0;
    io_t gamma = 0;
    io_t sigma = 0;

    if((microinstruction & 0x7FFF) != 0){
        switch(dcwa) {
                case 0: alpha = 0; break;
                case 0x0002: alpha = m_IK1302.R[signal_I]; break;
                case 0x0004: alpha = m_IK1302.pM[signal_I]; break;
                case 0x0006: alpha = m_IK1302.ST[signal_I]; break;
                case 0x0008: alpha = ~m_IK1302.R[signal_I] & 0xf; break;
                case 0x000A: if (m_IK1302.L == 0) alpha = 0xa; else alpha = 0; break;
                case 0x000C: alpha = m_IK1302.S; break;
                case 0x000E: alpha = 4; break;
                case 0x0010: alpha = 0xf;
        }

        if((microinstruction & 0x0F80) != 0) {
          switch(microinstruction & 0x0F80) {
                case 0x0800: alpha += 1; break;
                case 0x0400: alpha += 6; break;
                case 0x0C00: alpha += (1|6); break;
                case 0x0080: alpha += m_IK1302.S; break;
                case 0x0100: alpha += (~m_IK1302.S & 0xf); break;
                case 0x0200: alpha += m_IK1302.S1; break;
                case 0x0180: alpha += 0xf; break;
                case 0x0280: alpha += (m_IK1302.S | m_IK1302.S1); break;
          }
        }
   //---------------------------------------------------------
        if (m_IK1302.flag_FC > 0){
                if (m_IK1302.key_y == 0) m_IK1302.T = 0;
        } else {
                m_IK1302.displayed = 1;
                val = signal_div3;
                if((val == m_IK1302.key_xm) && (m_IK1302.key_y != 0)){
                                m_IK1302.S1 = m_IK1302.key_y;
                                m_IK1302.T = 1;
                }
                if((val < 12) && (m_IK1302.L != 0)) m_IK1302.comma = val;
        }
   //---------------------------------------------------------
        if((microinstruction & 0x4000) != 0) gamma = m_IK1302.T ^ 1; else gamma = 0;
        if((microinstruction & 0x2000) != 0) gamma |= m_IK1302.L ^ 1;
        if((microinstruction & 0x1000) != 0) gamma |= m_IK1302.L;

        alpha += gamma;
        sigma = alpha & 0xf;
        m_IK1302.P = alpha >> 4;
    } else {
   //---------------------------------------------------------
        if (m_IK1302.flag_FC > 0){
                if (m_IK1302.key_y == 0) m_IK1302.T = 0;
        } else {
                m_IK1302.displayed = 1;
                val = signal_div3;
                if((val == m_IK1302.key_xm) && (m_IK1302.key_y != 0)){
                                m_IK1302.S1 = m_IK1302.key_y;
                                m_IK1302.T = 1;
                }
                if((val < 12) && (m_IK1302.L != 0)) m_IK1302.comma = val;
        }
    //---------------------------------------------------------
        sigma = 0;
        m_IK1302.P = 0;
    }
  #ifdef out_dump
    printf("AMK %4.4X, microinstruction: %8.8X, MOD %u, S %u, S1 %u, sigma %u\n", m_IK1302.AMK, microinstruction, IK1302_MOD, IK1302_S, IK1302_S1, sigma);
  #endif
  //---------------------------------------------------------
    if (m_IK1302.MOD == 0 || signal_I >= 36) {
        tmp = dcw;
        if(tmp != 0){
          switch (tmp) {
            case 1: 
                m_IK1302.R[signal_I] = m_IK1302.R[MOD42(signal_I + 3)]; 
              break;
            case 2: m_IK1302.R[signal_I] = sigma; break;
            case 3: m_IK1302.R[signal_I] = m_IK1302.S; break;
            case 4: m_IK1302.R[signal_I] = m_IK1302.R[signal_I] | m_IK1302.S | sigma; break;
            case 5: m_IK1302.R[signal_I] = m_IK1302.S | sigma; break;
            case 6: m_IK1302.R[signal_I] = m_IK1302.R[signal_I] | m_IK1302.S; break;
            case 7: m_IK1302.R[signal_I] = m_IK1302.R[signal_I] | sigma;
          }
        }

        if ((mi_hi & 0x0004) !=0)    m_IK1302.R[MOD42(signal_I + 41)] = sigma;
        if ((mi_hi & 0x0008) !=0)    m_IK1302.R[MOD42(signal_I + 40)] = sigma;
    }
    if ((mi_hi & 0x0020) !=0)        m_IK1302.L = m_IK1302.P & 1;
    if ((mi_hi & 0x0010) !=0)        m_IK1302.pM[signal_I] = m_IK1302.S;
  //---------------------------------------------------------

        if((mi_hi & 0x0040) == 0){
         // 6 bit == 0, может быть 7 бит не равен?
          if((mi_hi & 0x0080) != 0)  m_IK1302.S = sigma; // 7 bit == 1
        } else {
         // 6 bit == 1, может быть 7 бит тоже равен?
                m_IK1302.S = m_IK1302.S1;
          if((mi_hi & 0x0080) != 0) m_IK1302.S |= sigma;
        }

        // 6 bit == 0, нам пофиг на состояние 7 бита
        if((mi_hi & 0x0100) != 0){
         // 6 bit == 1, может быть 7 бит тоже равен?
          if((mi_hi & 0x0200) != 0) m_IK1302.S1 |= sigma; else m_IK1302.S1 = sigma;
        }
  //----------------------------------------------------------
    mi_hi = mi_hi & 0x0C00;
    if(mi_hi != 0){
          if(mi_hi == 0x0400) {
                    m_IK1302.ST[MOD42(signal_I + 2)] = m_IK1302.ST[MOD42(signal_I + 1)];
                    m_IK1302.ST[MOD42(signal_I + 1)] = m_IK1302.ST[signal_I];
                    m_IK1302.ST[signal_I] = sigma;
          } else if(mi_hi == 0x0800) {
                    tmp = m_IK1302.ST[signal_I];
                    m_IK1302.ST[signal_I] = m_IK1302.ST[MOD42(signal_I + 1)];
                    m_IK1302.ST[MOD42(signal_I + 1)] = m_IK1302.ST[MOD42(signal_I + 2)];
                    m_IK1302.ST[MOD42(signal_I + 2)] = tmp;
          }
    }
}

MK61_CORE_TICK_FUNCTION IK1302_Tick(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3
    MK61_PACKED_AMK_PARAMETERS) {
 uint32_t  microinstruction;
 uint32_t  tmp;


  #if MK61_CORE_PACKED_AMK
    (void) J_signal_I;
    tmp = selected_amk;
    microinstruction = selected_microinstruction;
  #else
    tmp = (uint8_t) m_IK1302.pAND_AMK[J_signal_I]; // чтение из pAND_AMK: 3D(61) => 3E(62), 3E(62) => 40(64), 3F(63) => 42(66) замены в оригинальном ПЗУ
    if (tmp > 59 && m_IK1302.L == 0){ // Если AMK больше 59 (60,61,62,63), то пересчитываются (60,62,64,66) или (61,63,65,67) при L=0
       tmp++;
    }
    microinstruction = IK1302_MICROINSTRUCTIONS_ACTIVE[tmp];
  #endif
    m_IK1302.AMK = tmp;
#if MK61_CORE_PREDECODED_ROM
  if(native_hot_paths_are_enabled) {
    // The same executor sees constant ROM fields here, so the compiler
    // removes flag decoding. State changes stay on their original tick.
    #define ROM_CASE(index) \
      case index: \
        IK1302_Execute(signal_I, signal_div3, \
            ROM.IK1302.microinstructions[index], IK1302_DCW[index], IK1302_DCWA[index]); \
        return;
    switch(m_IK1302.AMK) { MK61_CORE_ROM_CASES(ROM_CASE) }
    #undef ROM_CASE
  }
#endif
  IK1302_Execute(signal_I, signal_div3, microinstruction,
      IK1302_DCW_ACTIVE[m_IK1302.AMK], IK1302_DCWA_ACTIVE[m_IK1302.AMK]);
}

static inline void __attribute__((always_inline)) IK1303_Execute(
    mtick_t signal_I, mtick_t signal_div3, u32 microinstruction, u32 dcw) {
  u32 tmp, mi_hi;
  mi_hi = (microinstruction >> 16);
  //---------------------------------------------------------
 if((((microinstruction >> 24) & 0x03) == 0x2) || (((microinstruction >> 24) & 0x03) == 0x3)) {
     if (signal_div3 != m_IK1303.key_xm) {
         // TODO: удалить if (m_IK1303.key_y > 0)
         m_IK1303.S1 |= m_IK1303.key_y;
     }
 }
  //---------------------------------------------------------
   io_t alpha = 0;
   io_t gamma = 0;
   io_t sigma = 0;
   if((microinstruction & 0x7FFF) != 0){

        switch(microinstruction & 0x007F){
                case 0x0001: alpha = m_IK1303.R[signal_I]; break;
                case 0x0002: alpha = m_IK1303.pM[signal_I]; break;
                case 0x0004: alpha = m_IK1303.ST[signal_I]; break;
                case 0x0008: alpha = ~m_IK1303.R[signal_I] & 0xf; break;
                case 0x0009: alpha = 0xf; break;
                case 0x0010: if (m_IK1303.L == 0) alpha = 0xa; else alpha = 0; break;
                case 0x0020: alpha = m_IK1303.S; break;
                case 0x0040: alpha = 4; break;
                case 0: alpha = 0;
        }

        if((microinstruction & 0x0F80) != 0){
          switch(microinstruction & 0x0F80){
                case 0x0800: alpha += 1; break;
                case 0x0400: alpha += 6; break;
                case 0x0C00: alpha += 1|6; break;
                case 0x0080: alpha += m_IK1303.S; break;
                case 0x0100: alpha += ~m_IK1303.S & 0xf; break;
                case 0x0200: alpha += m_IK1303.S1; break;
                case 0x0180: alpha += 0xf; break;
                case 0x0280: alpha += m_IK1303.S | m_IK1303.S1; break;
                case 0x0500: alpha += 6 | (~m_IK1303.S & 0xf); break;
          }
    }
   //---------------------------------------------------------
        if (m_IK1303.flag_FC > 0){
                if (m_IK1303.key_y == 0) m_IK1303.T = 0;
        }
        else{
                tmp = signal_div3;
                if (tmp == m_IK1303.key_xm)
                        if (m_IK1303.key_y > 0) {
                                m_IK1303.S1 = m_IK1303.key_y;
                                m_IK1303.T = 1;
                        }
                if (tmp < 12) if (m_IK1303.L > 0)  m_IK1303.comma = tmp;
        }
   //---------------------------------------------------------
        if((microinstruction & 0x4000) != 0) gamma = m_IK1303.T ^ 1; else gamma = 0;
        if((microinstruction & 0x2000) != 0) gamma |= m_IK1303.L ^ 1;
        if((microinstruction & 0x1000) != 0) gamma |= m_IK1303.L;

        alpha +=gamma;
        sigma = alpha & 0xf;
        m_IK1303.P = alpha >> 4;
   }
   else{
     //---------------------------------------------------------
        if (m_IK1303.flag_FC > 0){
                if (m_IK1303.key_y == 0) m_IK1303.T = 0;
        }
        else{
                tmp = signal_div3;
                if (tmp == m_IK1303.key_xm)
                        if (m_IK1303.key_y > 0) {
                                m_IK1303.S1 = m_IK1303.key_y;
                                m_IK1303.T = 1;
                        }
                if (tmp < 12) if (m_IK1303.L > 0)  m_IK1303.comma = tmp;
        }
   //---------------------------------------------------------
        sigma = 0;
        m_IK1303.P = 0;
   }
  #ifdef out_dump
    printf("AMK %4.4X, microinstruction: %8.8X, MOD %u, S %u, S1 %u, sigma %u\n", m_IK1303.AMK, microinstruction, m_IK1303.MOD, m_IK1303.S, m_IK1303.S1, sigma);
  #endif
  //---------------------------------------------------------
    if (m_IK1303.MOD == 0 || signal_I >= 36)
    {
        tmp = dcw;
                if(tmp != 0){
          switch (tmp)
          {
            case 1: m_IK1303.R[signal_I] = m_IK1303.R[MOD42(signal_I + 3)]; break;
            case 2: m_IK1303.R[signal_I] = sigma; break;
            case 3: m_IK1303.R[signal_I] = m_IK1303.S; break;
            case 4: m_IK1303.R[signal_I] = m_IK1303.R[signal_I] | m_IK1303.S | sigma; break;
            case 5: m_IK1303.R[signal_I] = m_IK1303.S | sigma; break;
            case 6: m_IK1303.R[signal_I] = m_IK1303.R[signal_I] | m_IK1303.S; break;
            case 7: m_IK1303.R[signal_I] = m_IK1303.R[signal_I] | sigma; break;
          }
                }

        if ((mi_hi & 0x0004) !=0)    m_IK1303.R[MOD42(signal_I + 41)] = sigma;
        if ((mi_hi & 0x0008) !=0)    m_IK1303.R[MOD42(signal_I + 40)] = sigma;
    }
    if ((mi_hi & 0x0020) !=0)        m_IK1303.L = m_IK1303.P & 1;
    if ((mi_hi & 0x0010) !=0)        m_IK1303.pM[signal_I] = m_IK1303.S;
  //---------------------------------------------------------

        if((mi_hi & 0x0040) == 0){
         // 6 bit == 0, может быть 7 бит не равен?
          if((mi_hi & 0x0080) != 0)  m_IK1303.S = sigma; // 7 bit == 1
        }
        else{
         // 6 bit == 1, может быть 7 бит тоже равен?
          m_IK1303.S = m_IK1303.S1;
          if((mi_hi & 0x0080) != 0) m_IK1303.S |= sigma;
        }

         // 6 bit == 0, нам пофиг на состояние 7 бита
        if((mi_hi & 0x0100) != 0){
         // 6 bit == 1, может быть 7 бит тоже равен?
          if((mi_hi & 0x0200) != 0) m_IK1303.S1 |= sigma; else m_IK1303.S1 = sigma;
        }
  //----------------------------------------------------------
    mi_hi = mi_hi & 0x0C00;
    if(mi_hi != 0){
          if(mi_hi == 0x0400){
                    m_IK1303.ST[MOD42(signal_I + 2)] = m_IK1303.ST[MOD42(signal_I + 1)];
                    m_IK1303.ST[MOD42(signal_I + 1)] = m_IK1303.ST[signal_I];
                    m_IK1303.ST[signal_I] = sigma;
          }
          else if(mi_hi == 0x0800){
                    tmp = m_IK1303.ST[signal_I];
                    m_IK1303.ST[signal_I] = m_IK1303.ST[MOD42(signal_I + 1)];
                    m_IK1303.ST[MOD42(signal_I + 1)] = m_IK1303.ST[MOD42(signal_I + 2)];
                    m_IK1303.ST[MOD42(signal_I + 2)] = tmp;
          }
    }
}

MK61_CORE_TICK_FUNCTION IK1303_Tick(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3
    MK61_PACKED_AMK_PARAMETERS) {
 uint32_t tmp;
 uint32_t microinstruction;


 #if MK61_CORE_PACKED_AMK
 (void) J_signal_I;
 tmp = selected_amk;
 microinstruction = selected_microinstruction;
 #else
 tmp = (uint8_t) m_IK1303.pAND_AMK[J_signal_I];
 if (tmp > 59 && m_IK1303.L == 0){ // Если AMK больше 59 (60,61,62,63), то пересчитываются (60,62,64,66) или (61,63,65,67) при L=0
      tmp++;
 }

 microinstruction = IK1303_MICROINSTRUCTIONS_ACTIVE[tmp];
 #endif
 m_IK1303.AMK = tmp;
#if MK61_CORE_PREDECODED_ROM
  if(native_hot_paths_are_enabled) {
    // The same executor sees constant ROM fields here, so the compiler
    // removes flag decoding. State changes stay on their original tick.
    #define ROM_CASE(index) \
      case index: \
        IK1303_Execute(signal_I, signal_div3, \
            ROM.IK1303.microinstructions[index], IK1303_DCW[index]); \
        return;
    switch(m_IK1303.AMK) { MK61_CORE_ROM_CASES(ROM_CASE) }
    #undef ROM_CASE
  }
#endif
  IK1303_Execute(signal_I, signal_div3, microinstruction,
      IK1303_DCW_ACTIVE[m_IK1303.AMK]);
}

#if MK61_CORE_PREDECODED_ROM
// Fold fixed ROM bodies. Conditional AMK selection still observes
// each chip's carry on the original tick; chip order and ring writes stay exact.
template<unsigned J, unsigned A, unsigned B>
static inline void __attribute__((always_inline))
native_region3_tick() {
  constexpr unsigned signal = 36 + J;
  constexpr unsigned a = IK1302_AND_AMK_EXPANDED[A * AND_AMK_RUNTIME_STRIDE + J];
  constexpr unsigned b = IK1303_AND_AMK_EXPANDED[B * AND_AMK_RUNTIME_STRIDE + J];
  if(a > 59 && m_IK1302.L == 0) {
    m_IK1302.AMK = a + 1;
    IK1302_Execute(signal, signal / 3, ROM.IK1302.microinstructions[a+1],
        IK1302_DCW[a+1], IK1302_DCWA[a+1]);
  } else {
    m_IK1302.AMK = a;
    IK1302_Execute(signal, signal / 3, ROM.IK1302.microinstructions[a],
        IK1302_DCW[a], IK1302_DCWA[a]);
  }
  if(b > 59 && m_IK1303.L == 0) {
    m_IK1303.AMK = b + 1;
    IK1303_Execute(signal, signal / 3, ROM.IK1303.microinstructions[b+1],
        IK1303_DCW[b+1]);
  } else {
    m_IK1303.AMK = b;
    IK1303_Execute(signal, signal / 3, ROM.IK1303.microinstructions[b],
        IK1303_DCW[b]);
  }
}
template<unsigned A, unsigned B>
static void MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))
native_ik1302_1303_region3() {
#if !defined(ARDUINO)
  ++native_sequence_hits;
#endif
  native_region3_tick<0, A, B>();
  native_region3_tick<1, A, B>();
  native_region3_tick<2, A, B>();
  native_region3_tick<3, A, B>();
  native_region3_tick<4, A, B>();
  native_region3_tick<5, A, B>();
}
#endif

static inline void __attribute__((always_inline)) IK1306_Execute(
    mtick_t signal_I, u32 microinstruction, u32 dcw) {
  u32 tmp, mi_hi;
  mi_hi = (microinstruction >> 16);
  //---------------------------------------------------------
    io_t alpha = 0;
    io_t gamma = 0;
    io_t sigma = 0;
    if((microinstruction & 0x3FFF) != 0){
        switch(microinstruction & 0x007F) {
                case 0x0001: alpha = m_IK1306.R[signal_I]; break;
                case 0x0002: alpha = m_IK1306.pM[signal_I]; break;
                case 0x0004: alpha = m_IK1306.ST[signal_I]; break;
                case 0x0005: alpha = m_IK1306.ST[signal_I] | m_IK1306.R[signal_I]; break;
                case 0x0008: alpha = ~m_IK1306.R[signal_I] & 0xf; break;
                case 0x0009: alpha = 0xf; break;
                case 0x0010: if(m_IK1306.L == 0) alpha = 0xa; else alpha = 0; break;
                case 0x0020: alpha = m_IK1306.S; break;
                case 0x0021: alpha = m_IK1306.S | m_IK1306.R[signal_I]; break;
                case 0x0028: alpha = m_IK1306.S | (~m_IK1306.R[signal_I] & 0xf); break;
                case 0x0040: alpha = 4; break;
                case 0: alpha = 0;
        }

        if((microinstruction & 0x0F80) != 0) {
           switch(microinstruction & 0x0F80) {
             case 0x0800: alpha += 1; break;
             case 0x0400: alpha += 6; break;
             case 0x0C00: alpha += 1|6; break;
             case 0x0080: alpha += m_IK1306.S; break;
             case 0x0100: alpha += ~m_IK1306.S & 0xf; break;
             case 0x0200: alpha += m_IK1306.S1; break;
             case 0x0180: alpha += m_IK1306.S | (~m_IK1306.S & 0xf); break;
           }
        }
 //---------------------------------------------------------
     if((microinstruction & 0x2000) != 0) gamma = m_IK1306.L ^ 1; else gamma=0;
     if((microinstruction & 0x1000) != 0) gamma |= m_IK1306.L;

     alpha += gamma;
     sigma = alpha & 0xf;
     m_IK1306.P = alpha >> 4;
    }
    else{
            sigma = 0;
           m_IK1306.P = 0;
    }
  #ifdef out_dump
    printf("AMK %4.4X, microinstruction: %8.8X, MOD %u, S %u, S1 %u, sigma %u\n", m_IK1306.AMK, microinstruction, IK1306_MOD, IK1306_S, IK1306_S1, sigma);
  #endif
  //---------------------------------------------------------
    if (m_IK1306.MOD == 0 || signal_I >= 36)
    {
        tmp = dcw;
        if(tmp != 0){
          switch (tmp){
            case 1: m_IK1306.R[signal_I] = m_IK1306.R[MOD42(signal_I + 3)]; break;
            case 2: m_IK1306.R[signal_I] = sigma; break;
            case 3: m_IK1306.R[signal_I] = m_IK1306.S; break;
            case 4: m_IK1306.R[signal_I] = m_IK1306.R[signal_I] | m_IK1306.S | sigma; break;
            case 5: m_IK1306.R[signal_I] = m_IK1306.S | sigma; break;
            case 6: m_IK1306.R[signal_I] = m_IK1306.R[signal_I] | m_IK1306.S; break;
            case 7: m_IK1306.R[signal_I] = m_IK1306.R[signal_I] | sigma; break;
          }
        }

        if ((mi_hi & 0x0004) !=0)    m_IK1306.R[MOD42(signal_I + 41)] = sigma;
        if ((mi_hi & 0x0008) !=0)    m_IK1306.R[MOD42(signal_I + 40)] = sigma;
    }
    if ((mi_hi & 0x0020) !=0)        m_IK1306.L = m_IK1306.P & 1;
    if ((mi_hi & 0x0010) !=0)        m_IK1306.pM[signal_I] = m_IK1306.S;
  //---------------------------------------------------------

    if((mi_hi & 0x0040) == 0){
      // 6 bit == 0, может быть 7 бит не равен?
      if((mi_hi & 0x0080) != 0)  m_IK1306.S = sigma; // 7 bit == 1
    }
    else{
      // 6 bit == 1, может быть 7 бит тоже равен?
      m_IK1306.S = m_IK1306.S1;
      if((mi_hi & 0x0080) != 0) m_IK1306.S |= sigma;
    }

    // 6 bit == 0, нам пофиг на состояние 7 бита
    if((mi_hi & 0x0100) != 0){
      // 6 bit == 1, может быть 7 бит тоже равен?
      if((mi_hi & 0x0200) != 0) m_IK1306.S1 |= sigma; else m_IK1306.S1 = sigma;
    }
  //----------------------------------------------------------
    mi_hi = mi_hi & 0x0C00;
    if(mi_hi != 0){
          if(mi_hi == 0x0400){
                    m_IK1306.ST[MOD42(signal_I + 2)] = m_IK1306.ST[MOD42(signal_I + 1)];
                    m_IK1306.ST[MOD42(signal_I + 1)] = m_IK1306.ST[signal_I];
                    m_IK1306.ST[signal_I] = sigma;
          }
          else if(mi_hi == 0x0800){
                    tmp = m_IK1306.ST[signal_I];
                    m_IK1306.ST[signal_I] = m_IK1306.ST[MOD42(signal_I + 1)];
                    m_IK1306.ST[MOD42(signal_I + 1)] = m_IK1306.ST[MOD42(signal_I + 2)];
                    m_IK1306.ST[MOD42(signal_I + 2)] = tmp;
          }
    }
}

MK61_CORE_TICK_FUNCTION IK1306_Tick(
    mtick_t signal_I, usize J_signal_I
    MK61_PACKED_AMK_PARAMETERS) {
    uint32_t tmp;
    uint32_t microinstruction;

  #if MK61_CORE_PACKED_AMK
    (void) J_signal_I;
    tmp = selected_amk;
    microinstruction = selected_microinstruction;
  #else
    tmp = (uint8_t) m_IK1306.pAND_AMK[J_signal_I];            //    AMK = AND_AMK[ASPx9 + J_signal_I];
    if (tmp > 59 && m_IK1306.L == 0){                         // Если AMK больше 59 (60,61,62,63), то пересчитываются (60,62,64,66) или (61,63,65,67) при L=0
        tmp++;
    }
    microinstruction = IK1306_MICROINSTRUCTIONS_ACTIVE[tmp];
  #endif
    m_IK1306.AMK = tmp;
#if MK61_CORE_PREDECODED_ROM
  if(native_hot_paths_are_enabled) {
    // The same executor sees constant ROM fields here, so the compiler
    // removes flag decoding. State changes stay on their original tick.
    #define ROM_CASE(index) \
      case index: \
        IK1306_Execute(signal_I, \
            ROM.IK1306.microinstructions[index], IK1306_DCW[index]); \
        return;
    switch(m_IK1306.AMK) { MK61_CORE_ROM_CASES(ROM_CASE) }
    #undef ROM_CASE
  }
#endif
  IK1306_Execute(signal_I, microinstruction,
      IK1306_DCW_ACTIVE[m_IK1306.AMK]);
}

#if MK61_CORE_PREDECODED_ROM
#undef MK61_CORE_ROM_CASES
#endif

#if MK61_CORE_MERGED_TICK
static void MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))
IK130X_Tick_All(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3) {
#if MK61_CORE_PACKED_AMK
  const core_packed_amk::Selection selected = select_amk_lanes(
      m_IK1302.pAND_AMK[J_signal_I],
      m_IK1303.pAND_AMK[J_signal_I],
      m_IK1306.pAND_AMK[J_signal_I]);
  IK1302_Tick(signal_I, J_signal_I, signal_div3,
      selected.ik1302, IK1302_MICROINSTRUCTIONS_ACTIVE[selected.ik1302]);
  IK1303_Tick(signal_I, J_signal_I, signal_div3,
      selected.ik1303, IK1303_MICROINSTRUCTIONS_ACTIVE[selected.ik1303]);
  IK1306_Tick(signal_I, J_signal_I,
      selected.ik1306, IK1306_MICROINSTRUCTIONS_ACTIVE[selected.ik1306]);
#else
  IK1302_Tick(signal_I, J_signal_I, signal_div3);
  IK1303_Tick(signal_I, J_signal_I, signal_div3);
  IK1306_Tick(signal_I, J_signal_I);
#endif
}

#if MK61_CORE_NATIVE_HOT_PATHS
static void MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))
IK1302_1303_Tick_All(
    mtick_t signal_I, usize J_signal_I, mtick_t signal_div3) {
#if MK61_CORE_PACKED_AMK
  const core_packed_amk::Selection selected = select_amk_lanes_1302_1303(
      m_IK1302.pAND_AMK[J_signal_I],
      m_IK1303.pAND_AMK[J_signal_I]);
  IK1302_Tick(signal_I, J_signal_I, signal_div3,
      selected.ik1302, IK1302_MICROINSTRUCTIONS_ACTIVE[selected.ik1302]);
  IK1303_Tick(signal_I, J_signal_I, signal_div3,
      selected.ik1303, IK1303_MICROINSTRUCTIONS_ACTIVE[selected.ik1303]);
#else
  IK1302_Tick(signal_I, J_signal_I, signal_div3);
  IK1303_Tick(signal_I, J_signal_I, signal_div3);
#endif
}
#endif
#endif

/**
 * mk61emu
 */

//uint8_t IK1302_DCWA[68];
inline  void  __attribute__((always_inline))  IK1302_Clear(void) {
    const usize size_IK1302 = sizeof(m_IK1302);
    dbgln(CORE61, "cleared IK1302 size = ", size_IK1302);
    memset(&m_IK1302, 0, size_IK1302);
    m_IK1302.pM = (uint8_t*) IK1302_M_START();
    m_IK1302.pAND_AMK = &IK1302_AND_AMK_ACTIVE[0];
    m_IK1302.pAND_AMK1 = &IK1302_AND_AMK_ACTIVE[0];
}

inline  void  __attribute__((always_inline))  IK1303_Clear(void) {
    const usize size_IK1303 = sizeof(m_IK1303);
    dbgln(CORE61, "cleared IK1303 size = ", size_IK1303);
    memset(&m_IK1303, 0, size_IK1303);
    m_IK1303.pM = (uint8_t*) IK1303_M_START();
    m_IK1303.pAND_AMK = &IK1303_AND_AMK_ACTIVE[0];
    m_IK1303.pAND_AMK1 = &IK1303_AND_AMK_ACTIVE[0];
}

inline  void  __attribute__((always_inline))  IK1306_Clear(void) {
    const usize size_IK1306 = sizeof(m_IK1306);
    dbgln(CORE61, "cleared IK1306 size = ", size_IK1306);
    memset(&m_IK1306, 0, size_IK1306);
    m_IK1306.pM = (uint8_t*) IK1306_M_START();
    m_IK1306.pAND_AMK = &IK1306_AND_AMK_ACTIVE[0];
    m_IK1306.pAND_AMK1 = &IK1306_AND_AMK_ACTIVE[0];
}

inline  void  __attribute__((always_inline))  mod42_table_init(void) {
  for(usize i=0; i < MOD42_TABLE_SIZE; i++) mod42_table[i] = i%42;
}

void MK61Emu_Cleanup() {
    reset_mk61_command_runtime();
    init_core_hot_tables();
    mod42_table_init(); // инициализация в ОЗУ таблицы остатка от деления на 42 (42+42 элемента)
    memset(&ringM,0,sizeof(ringM));
    IK1302_Clear();
    IK1303_Clear();
    IK1306_Clear();
}

void MK61Emu_SetKeyPress(const int key1, const int key2) {
    if(key1 < 0 || key1 > 11 || key2 < 0 || key2 > 9) {
      m_IK1302.key_x = 0;
      m_IK1302.key_y = 0;
      return;
    }
    m_IK1302.key_x = (uint32_t) key1;
    m_IK1302.key_y = (uint32_t) key2;
}

void MK61Emu_SetDisplayed(uint32_t value) {
    m_IK1302.displayed = value;
}

uint32_t MK61Emu_GetDisplayed(void) {
    return m_IK1302.displayed;
}

uint32_t MK61Emu_GetComma(void) {
    return m_IK1302.comma;
}

bool MK61Emu_IsRunning(void) {
    if (m_IK1302.comma == 11) {
        return true;
    }
    return false;
}

void MK61Emu_SetAngleUnit(AngleUnit angle) {
    m_emu.m_angle_unit = angle;
}

AngleUnit MK61Emu_GetAngleUnit(void) {
    return m_emu.m_angle_unit;
}

bool write_stack_register(stack reg, char sign, const char cmantissa[8], isize pow) {
  if((int) reg < (int) stack::X1 || (int) reg > (int) stack::T) return false;
  if(cmantissa == NULL || pow < -99 || pow > 99) return false;
  for(usize i = 0; i < 8; i++) {
    if(cmantissa[i] < '0' || cmantissa[i] > '9') return false;
  }

  isize addr = (isize) core_61::stack_address(reg) + 1;
  // преобразование мантиссы
  for(isize i=7; i >= 0; i--) {
    ringM[addr] = cmantissa[i] - '0';
    addr += 3;
  }
  // преобразование порядка
  ringM[addr] = (sign == '-')? 9 : 0;
  if(pow < 0) {
    pow += 100;
    ringM[addr + 9] = 9;
  } else {
    ringM[addr + 9] = 0;
  }
  ringM[addr + 6] = pow / 10;
  ringM[addr + 3] = pow % 10;
  return true;
}

/*
 buffer 012345678901234
        -1.2345678 -99
*/
const char* read_stack_register(stack reg, char cvalue[15], const char* symbols_set) {
  if(cvalue == NULL) return NULL;
  cvalue[0] = 0;
  if((int) reg < (int) stack::X1 || (int) reg > (int) stack::T) return cvalue;

  // преобразование мантиссы
  usize i = core_61::stack_address(reg) + 1;
  isize pos = 9;
  do {
    if(pos == 2) cvalue[pos--] = '.';
    cvalue[pos--] = display_symbol(symbols_set, ringM[i]);
    i += 3;
  } while(pos > 0);
  cvalue[0] = (ringM[i] == 9)? '-' : ' ';
  // преобразование порядка
  cvalue[10] = ' ';
  const usize powl = ringM[i + 3];
  const usize powh = ringM[i + 6];
  if(ringM[i + 9] == 9) {
    cvalue[11] = '-';
    const usize pow = 100 - (powh*10 + powl);
    cvalue[12] = display_symbol(symbols_set, (u8) (pow / 10));
    cvalue[13] = display_symbol(symbols_set, (u8) (pow % 10));
  } else {
    cvalue[11] = ' ';
    cvalue[12] = display_symbol(symbols_set, (u8) powh);
    cvalue[13] = display_symbol(symbols_set, (u8) powl);
  }
  cvalue[14] = 0;

  return &cvalue[0];
}

//                                           мантисса                  |  порядок
//                                       0   1   2   3   4  5  6  7  8   9  10  11
namespace ring_M {

const K745* active_chips(void) {
  return expanded_program_mode ? EXPANDED_CHIP : CLASSIC_CHIP;
}

usize active_chip_count(void) {
  return expanded_program_mode ? EXPANDED_CHIP_COUNT : CLASSIC_CHIP_COUNT;
}

} // пространство имён ring_M

namespace   core_61   {

static  usize   backstep_comma_position;
bool            edit_program;

bool expanded_program_is_on(void) {
  return expanded_program_mode;
}

void set_expanded_program_mode(bool enable) {
  expanded_program_mode = enable;
}

usize program_steps(void) {
  return expanded_program_mode ? MAX_PROGRAM_STEP : CLASSIC_PROGRAM_STEP;
}

u8 active_program_bank(void) {
  return extended_program.active_bank;
}

void clear_extended_program_banks(void) {
  if(extended_program.active_bank != 0) {
    u8 bank_zero[CODE_PAGE_BUFFER_SIZE] = {};
    if(extended_program.banks[0] != nullptr)
      memcpy(bank_zero, extended_program.banks[0], MAX_PROGRAM_STEP);
    set_code_page(bank_zero);
  }
  for(usize index = 0; index < EXTENDED_BANK_COUNT; index++) {
    extended_program.banks[index] = nullptr;
  }
  extended_program.active_bank = 0;
  extended_program.bank_slots_used = 0;
  extended_program.return_depth = 0;
  extended_program.pending_prefix = 0;
}

bool read_absolute_program(u16 address, u8& opcode) {
  if(address >= EXTENDED_ADDRESS_LIMIT ||
     (!expanded_program_mode && address >= CLASSIC_PROGRAM_STEP)) return false;
  const u8 bank = (u8) (address / MAX_PROGRAM_STEP);
  const u8 offset = (u8) (address % MAX_PROGRAM_STEP);
  if(bank == extended_program.active_bank) {
    opcode = get_code(get_ring_address(offset));
  } else {
    const u8* page = extended_program.banks[bank];
    opcode = page == nullptr ? 0x00U : page[offset];
  }
  return true;
}

bool write_absolute_program(u16 address, u8 opcode) {
  if(address >= EXTENDED_ADDRESS_LIMIT ||
     (!expanded_program_mode && address >= CLASSIC_PROGRAM_STEP)) return false;
  const u8 bank = (u8) (address / MAX_PROGRAM_STEP);
  const u8 offset = (u8) (address % MAX_PROGRAM_STEP);
  if(bank == extended_program.active_bank) {
    MK61Emu_SetCode((int) get_ring_address(offset), opcode);
    return true;
  }
  if(extended_program.banks[extended_program.active_bank] == nullptr) {
    u8* active_page = ensure_extended_bank(extended_program.active_bank);
    if(active_page == nullptr) return false;
    get_code_page(active_page);
  }
  u8* page = ensure_extended_bank(bank);
  if(page == nullptr) return false;
  page[offset] = opcode;
  return true;
}

usize ring_size(void) {
  return expanded_program_mode ? MK61_EXPANDED_RING_SIZE : MK61_CLASSIC_RING_SIZE;
}

usize stack_address(stack reg) {
  const usize base = expanded_program_mode ? OFFSET_IR2_1_1_EXPANDED : OFFSET_IR2_1_1_CLASSIC;
  return base + ((usize) reg * 42);
}

bool has_error(void) {
  for(usize pos : indicator_pos) {
    if((m_IK1302.R[pos] & 0x0F) == 0x0E) return true;
  }
  return false;
}

void  set_stack_register(stack reg, const bcd_value *value) {
  if(value == NULL || (int) reg < (int) stack::X1 || (int) reg > (int) stack::T) return;
  //                         +3   +3   +3   +3   +3   +3   +3   +3   +3    +3    +3
  // Конвертируем мантиссу 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> S -> ph -> pl -> s
  usize addr = stack_address(reg) + 1 + (3 * 7) + (3 * 4);

  // Знак мантиссы, младший разряд порядка, старщий разряд порядка, знак степени
  usize temp =  value->signs_and_pow; 
  for(isize j = 8; j < (8+1+2+1); j++) {
    const u8 tetrada = temp & 0x0F;
    dbghex(EXT_RUN, ",", tetrada);
    ringM[addr] = tetrada;
    temp >>= 4;
    addr -= 3;
  }

  usize mantissa =  value->mantissa; 
  for(isize j = 0; j < 8; j++) {
    const u8 digit = mantissa & 0x0F;
    dbghex(EXT_RUN, ",", digit);
    ringM[addr] = digit;
    mantissa >>= 4;
    addr -= 3;
  }
  dbgln(EXT_RUN,".");
}

void  get_stack_register(stack reg, bcd_value &value) {
  value.mantissa = 0;
  value.signs_and_pow = 0;
  if((int) reg < (int) stack::X1 || (int) reg > (int) stack::T) return;
  // Конвертируем мантиссу
  usize addr = stack_address(reg) + 1;

  for(isize j = 0; j < 8; j++) {
    const u32 digit = ringM[addr];
    dbghex(EXT_RUN, ",", digit);
    value.mantissa = (value.mantissa << 4) | digit;
    addr += 3;
  }

  // Знак мантиссы, младший разряд порядка, старщий разряд порядка, знак степени
  for(isize j = 8; j < (8+1+2+1); j++) {
    const u32 tetrada = ringM[addr];
    dbghex(EXT_RUN, ",", tetrada);
    value.signs_and_pow = (value.signs_and_pow << 4) | (u16) tetrada;
    addr += 3;
  }
  dbgln(EXT_RUN,".");
}

usize len_code_command(u8 cod) {
  return cod == 0x51U || cod == 0x53U || (cod >= 0x57U && cod <= 0x5EU)
      ? 2 : 1;
}

void step(void) {
    MK61_PROFILE_SCOPE(dwt_profiler::Point::CORE_STEP);
    prepare_core_hot_tables_for_step();
    mk61_program_boundary_yielded = false;
    m_IK1303.key_y = 1;
    m_IK1303.key_x = m_emu.m_angle_unit;
    ::cycle();
    if(m_IK1302.displayed) publish_x_to_extended_display();
    {
      MK61_PROFILE_SCOPE(dwt_profiler::Point::CORE_STEP_FINISH);
      m_IK1302.key_x = 0;
      m_IK1302.key_y = 0;
      if(keyboard_command_complete_pending && active_mk61_command.active &&
         active_mk61_command.source == Mk61CommandSource::KEYBOARD) {
        finish_active_mk61_command();
      }
      if(active_mk61_command.active &&
         active_mk61_command.source == Mk61CommandSource::PROGRAM && !is_RUN()) {
        finish_active_mk61_command();
      }
    }
}

HotTableCacheSnapshot hot_table_cache_statistics(void) {
#if MK61_CORE_HOT_TABLES_IN_SRAM >= 1
  const HotTableCacheSnapshot result = {
    sizeof(CoreHotTables),
    core_hot_table_loads,
    core_hot_table_evictions,
    core_hot_table_flash_steps,
    MK61_CORE_HOT_TABLES_IN_SRAM,
    true,
    core_hot_tables_cached && core_hot_tables_lease.ok()
  };
#else
  const HotTableCacheSnapshot result = {0, 0, 0, 0, 0, false, false};
#endif
  return result;
}

void reset_hot_table_cache_statistics(void) {
#if MK61_CORE_HOT_TABLES_IN_SRAM >= 1
  core_hot_table_loads = 0;
  core_hot_table_evictions = 0;
  core_hot_table_flash_steps = 0;
#endif
}

// Полное состояние ядра: кольцо ДОЗУ, структуры трёх микросхем и единица угла.
// Указатели внутри структур микросхем относятся к этому процессу, поэтому их
// побайтовое копирование безопасно, пока сохранение и восстановление происходят
// в одном запуске. Так захватывается всё наблюдаемое пользователем, включая
// экранный регистр X2 (защёлку дисплея IK1302, отдельную от стека X) и защёлку ошибки.
//
// Хранилище ContextBuffer во владении вызывающей стороны избавляет обычную
// LIBM-сборку от дополнительного скрытого снимка, но позволяет M61 приостановить ядро.
namespace {

static constexpr u32 CORE_CONTEXT_MAGIC = 0x4D4B3631UL; // "MK61"

struct PackedIK1302 {
  u32 AMK;
  u32 key_y;
  u32 key_x;
  u32 key_xm;
  u32 displayed;
  u32 comma;
  u32 L;
  u32 S;
  u32 S1;
  u32 P;
  u32 T;
  u32 MOD;
  u32 flag_FC;
  u16 p_and_amk1;
  u16 p_and_amk;
  u16 p_m;
  u8 registers[IK13_MTICK_COUNT];
};

struct PackedIK1303 {
  u32 AMK;
  u32 MOD;
  u32 S;
  u32 S1;
  u32 L;
  u32 T;
  u32 P;
  u32 flag_FC;
  u16 p_m;
  u16 p_and_amk;
  u16 p_and_amk1;
  u16 key_x;
  u16 key_xm;
  u16 key_y;
  u16 comma;
  u8 registers[IK13_MTICK_COUNT];
};

struct PackedIK1306 {
  u32 AMK;
  u32 L;
  u32 S;
  u32 S1;
  u32 P;
  u32 T;
  u32 MOD;
  u32 flag_FC;
  u16 p_and_amk1;
  u16 p_and_amk;
  u16 p_m;
  u8 registers[IK13_MTICK_COUNT];
};

struct PackedEmu {
  char indicator[INDICATOR_STRING_LENGTH];
  char stack_y[INDICATOR_STRING_LENGTH];
  u8 angle_unit;
};

struct PackedActiveCommand {
  u32 sequence;
  u8 active_and_jump_operand; // low bit: active; upper 7: operand address + 1
  u8 source;
  u8 opcode;
  u8 executed_opcode;
};
static_assert(core_61::MAX_PROGRAM_STEP < 128,
              "pending operand must fit beside the active command bit");

static constexpr u8 CONTEXT_EDIT = 0x01;
static constexpr u8 CONTEXT_EXPANDED = 0x02;
static constexpr u8 CONTEXT_RANDOM_ENABLED = 0x04;
static constexpr u8 CONTEXT_RANDOM_PENDING = 0x08;
static constexpr u8 CONTEXT_KEYBOARD_PENDING = 0x10;
static constexpr u8 CONTEXT_STATE_MASK =
    CONTEXT_EDIT | CONTEXT_EXPANDED | CONTEXT_RANDOM_ENABLED |
    CONTEXT_RANDOM_PENDING | CONTEXT_KEYBOARD_PENDING;

struct CoreContextSnapshot {
  u64 random_state;
  u32 magic;
  u32 command_sequence;
  PackedIK1302 ik1302;
  PackedIK1303 ik1303;
  PackedIK1306 ik1306;
  PackedActiveCommand active_command;
  u8 ring[sizeof(ringM) / 2U];
  PackedEmu emu;
  u8 call_operand_addresses[MK61_CALL_OPERAND_DEPTH];
  u8 call_operand_visits[MK61_CALL_OPERAND_DEPTH];
  u8 backstep_comma;
  u8 state_flags;
  u8 call_operand_depth;
  u16 extended_return_addresses[EXTENDED_RETURN_DEPTH];
  u32 extended_display_revision;
  u8 extended_segment_masks[core_61::EXTENDED_DISPLAY_CELLS];
  u8 extended_held_digits[core_61::EXTENDED_DISPLAY_CELLS];
  u8 extended_active_bank;
  u8 extended_return_depth;
  u8 extended_cursor;
  u8 extended_held_comma;
  u8 extended_flags;
  u16 extended_pending_prefix;
};

static_assert((sizeof(ringM) & 1U) == 0,
              "core ring nibble count must be even");
static_assert(sizeof(PackedIK1302) == 100, "IK1302 snapshot layout changed");
static_assert(sizeof(PackedIK1303) == 88, "IK1303 snapshot layout changed");
static_assert(sizeof(PackedIK1306) == 80, "IK1306 snapshot layout changed");
static_assert(sizeof(CoreContextSnapshot) <= core_61::CONTEXT_BUFFER_SIZE,
              "core context does not fit the public opaque buffer");

static bool pack_nibbles(const u8* input, usize count, u8* output) {
  if(input == nullptr || output == nullptr || (count & 1U) != 0) return false;
  for(usize index = 0; index < count; index += 2) {
    if(input[index] > 0x0FU || input[index + 1U] > 0x0FU) return false;
    output[index / 2U] =
        (u8) (input[index] | (u8) (input[index + 1U] << 4));
  }
  return true;
}

static void unpack_nibbles(const u8* input, usize count, u8* output) {
  for(usize index = 0; index < count; index += 2) {
    const u8 value = input[index / 2U];
    output[index] = value & 0x0FU;
    output[index + 1U] = value >> 4;
  }
}

static bool snapshot_offset(const u8* pointer, const u8* base,
                            usize size, u16& output) {
  if(pointer == nullptr || base == nullptr) return false;
  const uintptr_t address = (uintptr_t) pointer;
  const uintptr_t begin = (uintptr_t) base;
  if(address < begin || address - begin >= size ||
     address - begin > 0xFFFFU) return false;
  output = (u16) (address - begin);
  return true;
}

// Context ABI keeps the historical expanded (body * 16) offset even when the
// active fallback table is packed in Flash with a nine-byte stride.
static bool snapshot_and_amk_offset(const u8* pointer, const u8* base,
                                    u16& output) {
  if(pointer == nullptr || base == nullptr) return false;
  const uintptr_t address = (uintptr_t) pointer;
  const uintptr_t begin = (uintptr_t) base;
  if(address < begin) return false;
  const usize physical_offset = (usize) (address - begin);
  if(physical_offset >= AND_AMK_BODY_COUNT * AND_AMK_ACTIVE_STRIDE ||
     physical_offset % AND_AMK_ACTIVE_STRIDE != 0) return false;
  output = (u16) ((physical_offset / AND_AMK_ACTIVE_STRIDE) *
                  AND_AMK_RUNTIME_STRIDE);
  return true;
}

static bool valid_and_amk_snapshot_offset(u16 offset) {
  return offset < AND_AMK_RUNTIME_SIZE &&
         offset % AND_AMK_RUNTIME_STRIDE == 0;
}

static const u8* restore_and_amk_pointer(const u8* base, u16 offset) {
  return base + (offset / AND_AMK_RUNTIME_STRIDE) *
                AND_AMK_ACTIVE_STRIDE;
}

static bool save_ik1302(PackedIK1302& output) {
  output.AMK = m_IK1302.AMK;
  output.key_y = m_IK1302.key_y;
  output.key_x = m_IK1302.key_x;
  output.key_xm = m_IK1302.key_xm;
  output.displayed = m_IK1302.displayed;
  output.comma = m_IK1302.comma;
  output.L = m_IK1302.L;
  output.S = m_IK1302.S;
  output.S1 = m_IK1302.S1;
  output.P = m_IK1302.P;
  output.T = m_IK1302.T;
  output.MOD = m_IK1302.MOD;
  output.flag_FC = m_IK1302.flag_FC;
  return pack_nibbles(m_IK1302.R, sizeof(m_IK1302.R),
                      output.registers) &&
         pack_nibbles(m_IK1302.ST, sizeof(m_IK1302.ST),
                      output.registers + sizeof(m_IK1302.R) / 2U) &&
         snapshot_and_amk_offset(
             m_IK1302.pAND_AMK1, IK1302_AND_AMK_ACTIVE,
             output.p_and_amk1) &&
         snapshot_and_amk_offset(
             m_IK1302.pAND_AMK, IK1302_AND_AMK_ACTIVE,
             output.p_and_amk) &&
         snapshot_offset(m_IK1302.pM, ringM, sizeof(ringM), output.p_m);
}

static bool save_ik1303(PackedIK1303& output) {
  output.AMK = m_IK1303.AMK;
  output.MOD = m_IK1303.MOD;
  output.S = m_IK1303.S;
  output.S1 = m_IK1303.S1;
  output.L = m_IK1303.L;
  output.T = m_IK1303.T;
  output.P = m_IK1303.P;
  output.flag_FC = m_IK1303.flag_FC;
  output.key_x = m_IK1303.key_x;
  output.key_xm = m_IK1303.key_xm;
  output.key_y = m_IK1303.key_y;
  output.comma = m_IK1303.comma;
  return pack_nibbles(m_IK1303.R, sizeof(m_IK1303.R),
                      output.registers) &&
         pack_nibbles(m_IK1303.ST, sizeof(m_IK1303.ST),
                      output.registers + sizeof(m_IK1303.R) / 2U) &&
         snapshot_offset(m_IK1303.pM, ringM, sizeof(ringM), output.p_m) &&
         snapshot_and_amk_offset(
             m_IK1303.pAND_AMK, IK1303_AND_AMK_ACTIVE,
             output.p_and_amk) &&
         snapshot_and_amk_offset(
             m_IK1303.pAND_AMK1, IK1303_AND_AMK_ACTIVE,
             output.p_and_amk1);
}

static bool save_ik1306(PackedIK1306& output) {
  output.AMK = m_IK1306.AMK;
  output.L = m_IK1306.L;
  output.S = m_IK1306.S;
  output.S1 = m_IK1306.S1;
  output.P = m_IK1306.P;
  output.T = m_IK1306.T;
  output.MOD = m_IK1306.MOD;
  output.flag_FC = m_IK1306.flag_FC;
  return pack_nibbles(m_IK1306.R, sizeof(m_IK1306.R),
                      output.registers) &&
         pack_nibbles(m_IK1306.ST, sizeof(m_IK1306.ST),
                      output.registers + sizeof(m_IK1306.R) / 2U) &&
         snapshot_and_amk_offset(
             m_IK1306.pAND_AMK1, IK1306_AND_AMK_ACTIVE,
             output.p_and_amk1) &&
         snapshot_and_amk_offset(
             m_IK1306.pAND_AMK, IK1306_AND_AMK_ACTIVE,
             output.p_and_amk) &&
         snapshot_offset(m_IK1306.pM, ringM, sizeof(ringM), output.p_m);
}

static bool valid_angle_unit(u8 value) {
  return value == (u8) NONE || value == (u8) RADIAN ||
         value == (u8) DEGREE || value == (u8) GRADE ||
         value == (u8) DEGREE_ERASE;
}

static bool valid_context_snapshot(const CoreContextSnapshot& snapshot) {
  return snapshot.magic == CORE_CONTEXT_MAGIC &&
         snapshot.ik1302.p_m < sizeof(ringM) &&
         snapshot.ik1303.p_m < sizeof(ringM) &&
         snapshot.ik1306.p_m < sizeof(ringM) &&
         valid_and_amk_snapshot_offset(snapshot.ik1302.p_and_amk) &&
         valid_and_amk_snapshot_offset(snapshot.ik1302.p_and_amk1) &&
         valid_and_amk_snapshot_offset(snapshot.ik1303.p_and_amk) &&
         valid_and_amk_snapshot_offset(snapshot.ik1303.p_and_amk1) &&
         valid_and_amk_snapshot_offset(snapshot.ik1306.p_and_amk) &&
         valid_and_amk_snapshot_offset(snapshot.ik1306.p_and_amk1) &&
         (snapshot.active_command.active_and_jump_operand >> 1) <=
             core_61::MAX_PROGRAM_STEP &&
         snapshot.active_command.source <=
             (u8) core_61::Mk61CommandSource::PROGRAM &&
         (snapshot.state_flags & ~CONTEXT_STATE_MASK) == 0 &&
         snapshot.call_operand_depth <= MK61_CALL_OPERAND_DEPTH &&
         snapshot.extended_active_bank < EXTENDED_BANK_COUNT &&
         snapshot.extended_return_depth <= EXTENDED_RETURN_DEPTH &&
         snapshot.extended_cursor < core_61::EXTENDED_DISPLAY_CELLS &&
         (snapshot.extended_flags & ~0x0FU) == 0 &&
         (snapshot.extended_pending_prefix == 0 ||
          ((snapshot.extended_pending_prefix & 0xC000U) != 0xC000U &&
           (snapshot.extended_pending_prefix & 0x3FFFU) != 0 &&
           (snapshot.extended_pending_prefix & 0x3FFFU) <= core_61::EXTENDED_ADDRESS_LIMIT)) &&
         valid_angle_unit(snapshot.emu.angle_unit);
}

static void restore_ik1302(const PackedIK1302& input) {
  m_IK1302.AMK = input.AMK;
  m_IK1302.key_y = input.key_y;
  m_IK1302.key_x = input.key_x;
  m_IK1302.key_xm = input.key_xm;
  m_IK1302.displayed = input.displayed;
  m_IK1302.comma = input.comma;
  m_IK1302.L = input.L;
  m_IK1302.S = input.S;
  m_IK1302.S1 = input.S1;
  m_IK1302.P = input.P;
  m_IK1302.T = input.T;
  m_IK1302.MOD = input.MOD;
  m_IK1302.flag_FC = input.flag_FC;
  unpack_nibbles(input.registers, sizeof(m_IK1302.R), m_IK1302.R);
  unpack_nibbles(input.registers + sizeof(m_IK1302.R) / 2U,
                 sizeof(m_IK1302.ST), m_IK1302.ST);
  m_IK1302.pAND_AMK1 = restore_and_amk_pointer(
      IK1302_AND_AMK_ACTIVE, input.p_and_amk1);
  m_IK1302.pAND_AMK = restore_and_amk_pointer(
      IK1302_AND_AMK_ACTIVE, input.p_and_amk);
  m_IK1302.pM = ringM + input.p_m;
}

static void restore_ik1303(const PackedIK1303& input) {
  m_IK1303.AMK = input.AMK;
  m_IK1303.MOD = input.MOD;
  m_IK1303.S = input.S;
  m_IK1303.S1 = input.S1;
  m_IK1303.L = input.L;
  m_IK1303.T = input.T;
  m_IK1303.P = input.P;
  m_IK1303.flag_FC = input.flag_FC;
  m_IK1303.key_x = input.key_x;
  m_IK1303.key_xm = input.key_xm;
  m_IK1303.key_y = input.key_y;
  m_IK1303.comma = input.comma;
  unpack_nibbles(input.registers, sizeof(m_IK1303.R), m_IK1303.R);
  unpack_nibbles(input.registers + sizeof(m_IK1303.R) / 2U,
                 sizeof(m_IK1303.ST), m_IK1303.ST);
  m_IK1303.pM = ringM + input.p_m;
  m_IK1303.pAND_AMK = restore_and_amk_pointer(
      IK1303_AND_AMK_ACTIVE, input.p_and_amk);
  m_IK1303.pAND_AMK1 = restore_and_amk_pointer(
      IK1303_AND_AMK_ACTIVE, input.p_and_amk1);
}

static void restore_ik1306(const PackedIK1306& input) {
  m_IK1306.AMK = input.AMK;
  m_IK1306.L = input.L;
  m_IK1306.S = input.S;
  m_IK1306.S1 = input.S1;
  m_IK1306.P = input.P;
  m_IK1306.T = input.T;
  m_IK1306.MOD = input.MOD;
  m_IK1306.flag_FC = input.flag_FC;
  unpack_nibbles(input.registers, sizeof(m_IK1306.R), m_IK1306.R);
  unpack_nibbles(input.registers + sizeof(m_IK1306.R) / 2U,
                 sizeof(m_IK1306.ST), m_IK1306.ST);
  m_IK1306.pAND_AMK1 = restore_and_amk_pointer(
      IK1306_AND_AMK_ACTIVE, input.p_and_amk1);
  m_IK1306.pAND_AMK = restore_and_amk_pointer(
      IK1306_AND_AMK_ACTIVE, input.p_and_amk);
  m_IK1306.pM = ringM + input.p_m;
}

// Single-core firmware calls this API only from foreground code. Keeping the
// owner beside the slot turns accidental re-entry into a clean failure instead
// of silently corrupting the suspended calculator.
static core_61::ContextBuffer shared_context_buffer = {};
static core_61::ContextBufferOwner shared_context_owner =
    (core_61::ContextBufferOwner) 0;

} // namespace

ContextBuffer* acquire_context_buffer(ContextBufferOwner owner) {
  if((u8) owner == 0 || (u8) shared_context_owner != 0) return nullptr;
  shared_context_owner = owner;
  return &shared_context_buffer;
}

ContextBuffer* owned_context_buffer(ContextBufferOwner owner) {
  return (u8) owner != 0 && shared_context_owner == owner
      ? &shared_context_buffer : nullptr;
}

bool release_context_buffer(ContextBufferOwner owner) {
  if((u8) owner == 0 || shared_context_owner != owner) return false;
  shared_context_owner = (ContextBufferOwner) 0;
  return true;
}

bool save_context(ContextBuffer& out) {
  CoreContextSnapshot snapshot = {};
  snapshot.magic = CORE_CONTEXT_MAGIC;
  if(backstep_comma_position > 0xFFU ||
     !pack_nibbles(ringM, sizeof(ringM), snapshot.ring) ||
     !save_ik1302(snapshot.ik1302) ||
     !save_ik1303(snapshot.ik1303) ||
     !save_ik1306(snapshot.ik1306)) return false;
  memcpy(snapshot.emu.indicator, m_emu.m_indicator_str,
         sizeof(snapshot.emu.indicator));
  memcpy(snapshot.emu.stack_y, m_emu.m_stack_y_str,
         sizeof(snapshot.emu.stack_y));
  snapshot.emu.angle_unit = (u8) m_emu.m_angle_unit;
  snapshot.backstep_comma = (u8) backstep_comma_position;
  if(edit_program) snapshot.state_flags |= CONTEXT_EDIT;
  if(expanded_program_mode) snapshot.state_flags |= CONTEXT_EXPANDED;
  if(external_random_enabled) {
    snapshot.state_flags |= CONTEXT_RANDOM_ENABLED;
  }
  if(external_random_pending) {
    snapshot.state_flags |= CONTEXT_RANDOM_PENDING;
  }
  if(keyboard_command_complete_pending) {
    snapshot.state_flags |= CONTEXT_KEYBOARD_PENDING;
  }
  snapshot.random_state = external_random_state;
  snapshot.active_command.sequence = active_mk61_command.sequence;
  snapshot.active_command.active_and_jump_operand =
      (u8) ((mk61_jump_operand << 1) | (active_mk61_command.active ? 1U : 0U));
  snapshot.active_command.source = (u8) active_mk61_command.source;
  snapshot.active_command.opcode = active_mk61_command.opcode;
  snapshot.active_command.executed_opcode =
      active_mk61_command.executed_opcode;
  snapshot.command_sequence = mk61_command_sequence;
  memcpy(snapshot.call_operand_addresses, mk61_call_operand_addresses,
         sizeof(snapshot.call_operand_addresses));
  memcpy(snapshot.call_operand_visits, mk61_call_operand_visits,
         sizeof(snapshot.call_operand_visits));
  snapshot.call_operand_depth = mk61_call_operand_depth;
  memcpy(snapshot.extended_return_addresses,
         extended_program.return_addresses,
         sizeof(snapshot.extended_return_addresses));
  snapshot.extended_display_revision = extended_program.display_revision;
  memcpy(snapshot.extended_segment_masks, extended_program.segment_masks,
         sizeof(snapshot.extended_segment_masks));
  memcpy(snapshot.extended_held_digits, extended_program.held_digits,
         sizeof(snapshot.extended_held_digits));
  snapshot.extended_active_bank = extended_program.active_bank;
  snapshot.extended_return_depth = extended_program.return_depth;
  snapshot.extended_cursor = extended_program.cursor;
  snapshot.extended_held_comma = extended_program.held_comma;
  snapshot.extended_flags =
      (extended_program.auto_display ? 0x01U : 0U) |
      (extended_program.segment_display ? 0x02U : 0U) |
      (extended_program.error ? 0x04U : 0U) |
      (extended_program.numeric_strobe_pending ? 0x08U : 0U);
  snapshot.extended_pending_prefix = extended_program.pending_prefix;
  memset(out.bytes, 0, sizeof(out.bytes));
  memcpy(out.bytes, &snapshot, sizeof(snapshot));
  return true;
}

bool restore_context(const ContextBuffer& saved) {
  CoreContextSnapshot snapshot = {};
  memcpy(&snapshot, saved.bytes, sizeof(snapshot));
  if(!valid_context_snapshot(snapshot)) return false;
  unpack_nibbles(snapshot.ring, sizeof(ringM), ringM);
  expanded_program_mode =
      (snapshot.state_flags & CONTEXT_EXPANDED) != 0;
  // Между save/restore hot tables могли переселиться между Flash и workspace.
  // Сначала выбираем текущий view, затем восстанавливаем смещения относительно
  // его канонических баз — в снимке нет ни одного абсолютного указателя.
  select_core_hot_table_view(core_hot_tables_view_cached());
  restore_ik1302(snapshot.ik1302);
  restore_ik1303(snapshot.ik1303);
  restore_ik1306(snapshot.ik1306);
  memcpy(m_emu.m_indicator_str, snapshot.emu.indicator,
         sizeof(snapshot.emu.indicator));
  memcpy(m_emu.m_stack_y_str, snapshot.emu.stack_y,
         sizeof(snapshot.emu.stack_y));
  m_emu.m_angle_unit = (AngleUnit) snapshot.emu.angle_unit;
  backstep_comma_position = snapshot.backstep_comma;
  edit_program = (snapshot.state_flags & CONTEXT_EDIT) != 0;
  external_random_enabled =
      (snapshot.state_flags & CONTEXT_RANDOM_ENABLED) != 0;
  external_random_pending =
      (snapshot.state_flags & CONTEXT_RANDOM_PENDING) != 0;
  external_random_state = snapshot.random_state;
  active_mk61_command.active =
      (snapshot.active_command.active_and_jump_operand & 1U) != 0;
  mk61_jump_operand = snapshot.active_command.active_and_jump_operand >> 1;
  active_mk61_command.source =
      (core_61::Mk61CommandSource) snapshot.active_command.source;
  active_mk61_command.opcode = snapshot.active_command.opcode;
  active_mk61_command.executed_opcode =
      snapshot.active_command.executed_opcode;
  active_mk61_command.sequence = snapshot.active_command.sequence;
  mk61_command_sequence = snapshot.command_sequence;
  keyboard_command_complete_pending =
      (snapshot.state_flags & CONTEXT_KEYBOARD_PENDING) != 0;
  memcpy(mk61_call_operand_addresses, snapshot.call_operand_addresses,
         sizeof(mk61_call_operand_addresses));
  memcpy(mk61_call_operand_visits, snapshot.call_operand_visits,
         sizeof(mk61_call_operand_visits));
  mk61_call_operand_depth = snapshot.call_operand_depth;
  memcpy(extended_program.return_addresses,
         snapshot.extended_return_addresses,
         sizeof(snapshot.extended_return_addresses));
  extended_program.display_revision = snapshot.extended_display_revision;
  memcpy(extended_program.segment_masks, snapshot.extended_segment_masks,
         sizeof(snapshot.extended_segment_masks));
  memcpy(extended_program.held_digits, snapshot.extended_held_digits,
         sizeof(snapshot.extended_held_digits));
  extended_program.active_bank = snapshot.extended_active_bank;
  extended_program.return_depth = snapshot.extended_return_depth;
  extended_program.cursor = snapshot.extended_cursor;
  extended_program.held_comma = snapshot.extended_held_comma;
  extended_program.auto_display = (snapshot.extended_flags & 0x01U) != 0;
  extended_program.segment_display = (snapshot.extended_flags & 0x02U) != 0;
  extended_program.error = (snapshot.extended_flags & 0x04U) != 0;
  extended_program.numeric_strobe_pending =
      (snapshot.extended_flags & 0x08U) != 0;
  extended_program.pending_prefix = snapshot.extended_pending_prefix;
  return true;
}

void configure_random_seed(bool enable, u64 seed_material) {
  if(!enable) {
    external_random_enabled = false;
    external_random_pending = false;
    if(random_mk61_command_hook != INVALID_MK61_COMMAND_HOOK &&
       remove_mk61_command_hook(random_mk61_command_hook, true)) {
      random_mk61_command_hook = INVALID_MK61_COMMAND_HOOK;
    }
    if(random_rom_command_hook != INVALID_ROM_COMMAND_HOOK &&
       remove_rom_command_hook(random_rom_command_hook, true)) {
      random_rom_command_hook = INVALID_ROM_COMMAND_HOOK;
    }
    return;
  }

  bool command_hook_added = false;
  bool rom_hook_added = false;
  if(random_mk61_command_hook == INVALID_MK61_COMMAND_HOOK) {
    random_mk61_command_hook = add_mk61_command_hook(
        0x3BU, Mk61CommandHookPhase::BEFORE_EXECUTE,
        &arm_external_random_seed, nullptr, true);
    command_hook_added = random_mk61_command_hook != INVALID_MK61_COMMAND_HOOK;
  }
  if(random_rom_command_hook == INVALID_ROM_COMMAND_HOOK) {
    random_rom_command_hook = add_rom_command_hook(
        RomChip::IK1306, 0xA7U, &inject_external_random_seed, nullptr, true);
    rom_hook_added = random_rom_command_hook != INVALID_ROM_COMMAND_HOOK;
  }
  if(random_mk61_command_hook == INVALID_MK61_COMMAND_HOOK ||
     random_rom_command_hook == INVALID_ROM_COMMAND_HOOK) {
    if(command_hook_added &&
       remove_mk61_command_hook(random_mk61_command_hook, true)) {
      random_mk61_command_hook = INVALID_MK61_COMMAND_HOOK;
    }
    if(rom_hook_added && remove_rom_command_hook(random_rom_command_hook, true)) {
      random_rom_command_hook = INVALID_ROM_COMMAND_HOOK;
    }
    external_random_enabled = false;
    external_random_pending = false;
    return;
  }

  external_random_state = random_avalanche(seed_material ^ 0xE7037ED1A0B428DBULL);
  external_random_pending = false;
  external_random_enabled = true;
}

void update_random_seed(u64 seed_material) {
  if(!external_random_enabled) return;
  external_random_state ^= random_avalanche(seed_material + 0x8EBC6AF09C88C6E3ULL);
}

bool random_seed_enabled(void) {
  return external_random_enabled;
}

void enable(void) {
    if(extended_program.active_bank != 0) {
      if(u8* page = ensure_extended_bank(extended_program.active_bank))
        core_61::get_code_page(page);
    }
    extended_program.active_bank = 0;
    extended_program.return_depth = 0;
    extended_program.cursor = 0;
    extended_program.auto_display = true;
    extended_program.segment_display = false;
    extended_program.numeric_strobe_pending = false;
    extended_program.error = false;
    memset(extended_program.segment_masks, 0,
           sizeof(extended_program.segment_masks));
    extended_program.display_revision++;
    MK61Emu_Cleanup();
    //MK61Emu_SetAngleUnit(RADIAN);
    core_61::edit_program = false;
    core_61::clear_displayed();
    capture_extended_indicator();
    backstep_comma_position = core_61::comma_position();
    dbghexln(CORE61," IK1302_AMK $", (isize) &IK1302_AND_AMK_ACTIVE, " IK1302_DCW $", (isize) &IK1302_DCW_ACTIVE, " IK1302_DCWA $", (isize) &IK1302_DCWA_ACTIVE);
    step();
}

bool  update_indicator(char* buffer, const char* display_symbols) { // возращает false - есть изменения в дисплейной строке/ true - нет изменений
  if(buffer == NULL) return true;

  char next[INDICATOR_STRING_LENGTH] = {};
  usize out = 0;
  const bool held = expanded_program_mode &&
      (!extended_program.auto_display ||
       extended_program.numeric_strobe_pending);
  const int comma_pos = 10 - (int) (held
      ? extended_program.held_comma : m_IK1302.comma);
  for(usize i = 0; i < 12; i++) {
    if((int) i == comma_pos && comma_pos < 10) next[out++] = '.';
    const u8 digit = held ? extended_program.held_digits[i]
                          : m_IK1302.R[indicator_pos[i]];
    next[out++] = display_symbol(display_symbols, digit);
  }
  next[out] = 0;

  bool match = true;
  for(usize i = 0; i <= out; i++) match &= buffer[i] == next[i];
  if(!match) memcpy(buffer, next, out + 1);
  extended_program.numeric_strobe_pending = false;
  return match;
}

const u8* segment_display_frame(void) {
  return expanded_program_mode && extended_program.segment_display
      ? extended_program.segment_masks : nullptr;
}

u32 extended_display_revision(void) {
  return extended_program.display_revision;
}

bool extended_display_auto(void) {
  return !expanded_program_mode || extended_program.auto_display;
}

bool extended_display_segmented(void) {
  return expanded_program_mode && extended_program.segment_display;
}

u8 extended_display_cursor(void) {
  return extended_program.cursor;
}

bool restore_standard_display(void) {
  const bool changed = !extended_program.auto_display ||
      extended_program.segment_display ||
      extended_program.numeric_strobe_pending ||
      extended_program.cursor != 0;
  extended_program.cursor = 0;
  extended_program.auto_display = true;
  extended_program.segment_display = false;
  extended_program.numeric_strobe_pending = false;
  if(changed) extended_program.display_revision++;
  return changed;
}

void publish_x_to_extended_display(void) {
  if(expanded_program_mode && extended_program.auto_display &&
     extended_program.segment_display) {
    (void) write_x_segment(false);
  }
}

bool extended_program_error(void) {
  return extended_program.error;
}

void  set_code_page(const uint8_t* page) {
  if(page == NULL) return;
  const usize active_ring_size = core_61::ring_size();
  for(usize i = 41; i < active_ring_size; i+=42) {
    MK61Emu_SetCode(i, *page++);
    usize addr = i - 36;
    while(addr < i) {
          MK61Emu_SetCode(addr, *page++);
          addr += 6;
    }
  }
}

void  get_code_page(uint8_t* page) {
  uint8_t* out = page;
  const usize active_ring_size = core_61::ring_size();
  for(usize i = 41; i < active_ring_size; i+=42) {
    *out++ = core_61::get_code(i);
    usize addr = i - 36;
    while(addr < i) {
          *out++ = core_61::get_code(addr);
          addr += 6;
    }
  }
  while((usize) (out - page) < core_61::CODE_PAGE_BUFFER_SIZE) *out++ = 0;
}

u8    get_code(i32 addr){
    if(addr < 3 || addr >= (i32) core_61::ring_size()) return 0;
    return (u8) ((ringM[addr]<<4)|(ringM[addr-3]));
}

}
//                   1--------12--------23--- 
//          123456789012345678901234567890123
//   nReg*42
//     ----7--6--5--4--3--2--1--0--S--1--0--s
//   { знак_числа|знак_порядка|длина, модуль(порядка), мантисса... }

const u8* MK61Emu_UnpackRegster(u8 nReg, const u8 *pack_number) {
  if(pack_number == NULL) return NULL;
  const u8 register_count = core_61::expanded_program_is_on() ? 16 : 15;
  if(nReg >= register_count) return NULL;
  const u8 flags = pack_number[0];
  const u8 len = flags & 0b00111111;
  const u8 pow = pack_number[1];
  if(len > 4 || (pow & 0x0F) > 9 || (pow >> 4) > 9) return NULL;
  for(u8 i = 0; i < len; i++) {
    if((pack_number[2 + i] & 0x0F) > 9 || (pack_number[2 + i] >> 4) > 9) return NULL;
  }
  const u8* packed_digits = pack_number + 2;
  const int cnt_zero = len * 2;
  int   addr = nReg*42 + 21;
  u8    two_digits = 0;

      ringM[addr + 3] = (flags & 0b10000000) != 0 ? 9 : 0;
      if((flags & 0b01000000) != 0) {
        ringM[addr + 3*4] = 9;
      } else {
        ringM[addr + 3*4] = 0;
      }

      for(int j = 0; j < 8; j++){
        if(j >= cnt_zero) {
          ringM[addr] = 0; 
        } else {
          if ((j & 1) == 0) { // четные цифры
            two_digits = packed_digits[j / 2];
            ringM[addr] = two_digits >> 4;
          } else { // нечетные цифры
            ringM[addr] = two_digits & 0xF; 
          }
        }
        addr -= 3;
      }  

    ringM[addr + 27 + 3] = pow & 0xF; 
    ringM[addr + 30 + 3] = pow >> 4;
    
  return packed_digits + len;
}

void core_61::clear_memory_registers(void) {
  static const u8 packed_zero[3] = {0x01, 0x00, 0x00};
  const u8 register_count = expanded_program_is_on() ? 16 : 15;
  for(u8 reg = 0; reg < register_count; reg++) {
    (void) MK61Emu_UnpackRegster(reg, packed_zero);
  }
}

//      0       1      2     3
// 24, 21, 18, 15, 12, 9, 6, 3, 0 ::: 33, 30, 27
void    MK61Emu_ReadRegister(int nReg, char* buffer, const char* display_symbols) {
  if(buffer == NULL) return;
  buffer[0] = 0;
  const int register_count = core_61::expanded_program_is_on() ? 16 : 15;
  if(nReg < 0 || nReg >= register_count) return;

  int addr = nReg*42 + 21;
  const u8 sign_pow_tetra = ringM[addr + 3*4];
  const bool sign_pow = ringM[addr + 3*4];
  const bool sign_val = ringM[addr + 3];

  *buffer++ = (sign_val)? '-' : ' ';

  dbghex(MK61E, (isize) ringM[addr+3], ','); 

  for(int j = 3; j < 11; j++){
    *buffer++ = display_symbol(display_symbols, ringM[addr]);
    dbghex(MK61E, (isize) ringM[addr], ',');
    if(j == 3) *buffer++ = '.';
    addr -= 3;
  }  
  *buffer++ = ' ';

  dbghex(MK61E, 'E', (isize) ringM[sign_pow_tetra], ',');
  dbghex(MK61E, (isize) ringM[addr+30+3], ','); 
  dbghex(MK61E, (isize) ringM[addr+27+3], '|'); 

  if(sign_pow != 0) {
    *buffer++ = '-';
    const usize pow = 100 - ringM[addr+30+3]*10 - ringM[addr+27+3];
    *buffer++ = display_symbol(display_symbols, (u8) (pow / 10));
    *buffer++ = display_symbol(display_symbols, (u8) (pow % 10));
  } else {
    *buffer++ = ' ';
    *buffer++ = display_symbol(display_symbols, ringM[addr+30+3]);
    *buffer++ = display_symbol(display_symbols, ringM[addr+27+3]);
  }
  *buffer = 0x00;
}

usize   MK61Emu_Read_R_mantissa(usize nReg) {
  const usize register_count = core_61::expanded_program_is_on() ? 16 : 15;
  if(nReg >= register_count) return 0;
  usize addr = nReg*42 + 21;
  usize value = 0;
  for(usize j = 3; j < 11; j++){
    value = (value * 10) + ringM[addr]; 
    addr -= 3;
  } 
  
  return value;
}

usize MK61Emu_Read_X_as_byte(void) {
  isize num = 0;
    for(isize i = 21; i >= 12 ; i -= 3) {
      const int digit = m_IK1302.R[i];
      if(digit <= 9) num = num*10 + digit; else break;
      if(num > 256) break;
    }

  return num;
}

void MK61Emu_SetCode(int addr, uint8_t data) {
    if(addr < 3 || addr >= (int) core_61::ring_size()) return;
    ringM[addr] = data >> 4;
    ringM[addr-3] = data & 0x0F;
}

void  MK61Emu_ClearCodePage(void) {
    core_61::clear_extended_program_banks();
    const usize active_ring_size = core_61::ring_size();
    for(usize i = 41; i < active_ring_size; i+=42) {
      MK61Emu_SetCode(i, 0);
      for(usize addr=i-36; addr < i; addr+=6) {
        MK61Emu_SetCode(addr, 0);
      }
    }
}

void MK61Emu_get_1302_R(char* buff) {
  for(int i=0; i < IK13_MTICK_COUNT; i++) {
    const uint8_t nibl = m_IK1302.R[i];
    buff[i] = (char) (nibl < 10)? nibl + '0' : nibl - 10 + 'A';
  }
  buff[42] = 0;
}

int MK61Emu_GetDisplayReg(void) {
  int num = 0;
    for(int i = 21; i >= 0 ; i -= 3) {
      const int digit = m_IK1302.R[i];
      #ifdef DEBUG
        Serial.print(digit); Serial.print(",");
      #endif
      if(digit <= 9) num = num*10 + digit; else break;
    }
    #ifdef DEBUG
      Serial.println(num);
    #endif

  return num;
}

const char* MK61Emu_GetIndicatorStr(const char* display_symbols) {
    memset(m_emu.m_indicator_str, 0, sizeof(m_emu.m_indicator_str));
    memset(m_emu.m_indicator_str, ' ', 12);

    for (int i = 0; i < 9; i++) {
        m_emu.m_indicator_str[i] = display_symbol(display_symbols, m_IK1302.R[(8 - i) * 3]);
    }
    for (int i = 0; i < 3; i++) {
        m_emu.m_indicator_str[i + 10] = display_symbol(display_symbols, m_IK1302.R[(11 - i) * 3]);
    }

    const int comma_pos = 10 - (int) m_IK1302.comma;
    if(comma_pos >= 0 && comma_pos <= 13) {
      for (int i = 13; i > comma_pos; i--) {
          m_emu.m_indicator_str[i] = m_emu.m_indicator_str[i - 1];
      }
      m_emu.m_indicator_str[comma_pos] = ',';
    }
    return m_emu.m_indicator_str;
}
