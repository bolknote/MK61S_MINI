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
#ifndef _MK61EMU_H_
#define _MK61EMU_H_

#define MK_OK 0xFFFF
#define MK61EMU_VERSION_MAJOR 1
#define MK61EMU_VERSION_MINOR 2

#include <stdint.h>
#include "rust_types.h"
#include <stdbool.h>

static  constexpr usize MK61_NOP= 0x54; // NOP
static  constexpr usize MK61_CLASSIC_PROGRAM_STEPS = 105;
static  constexpr usize MK61_EXPANDED_PROGRAM_STEPS = MK61_CLASSIC_PROGRAM_STEPS + 7;
static constexpr  usize   MK61_CLASSIC_RING_SIZE       = 252 + 252 + 42 + 42 + 42;
static constexpr  usize   MK61_EXPANDED_RING_SIZE      = MK61_CLASSIC_RING_SIZE + 42;
static constexpr  usize   SIZE_RING_M                  = MK61_EXPANDED_RING_SIZE;
static constexpr  usize   MK61_LAST_PRG_STEP           = MK61_CLASSIC_PROGRAM_STEPS;
static constexpr  usize   OFFSET_IK1302_CLASSIC        = 252 + 42;
static constexpr  usize   OFFSET_IK1303_CLASSIC        = 252 + 42 + 42;
static constexpr  usize   OFFSET_IK1306_CLASSIC        = 252 + 42 + 42 + 42;
static constexpr  usize   OFFSET_IR2_1_1_CLASSIC       = 42 + 252 + 42 + 42 + 42;
static constexpr  usize   OFFSET_IK1302_EXPANDED       = 252 + 42 + 42;
static constexpr  usize   OFFSET_IK1303_EXPANDED       = 252 + 42 + 42 + 42;
static constexpr  usize   OFFSET_IK1306_EXPANDED       = 252 + 42 + 42 + 42 + 42;
static constexpr  usize   OFFSET_IR2_1_1_EXPANDED      = 42 + 42 + 252 + 42 + 42 + 42;

namespace ring_M {
  struct  K745 {
    const char  *NAME;
    const usize OFFSET;
  };
  static constexpr K745 IR2_1_0 = {"IR2.1_0", 0};
  static constexpr K745 IR2_2   = {"IR2.2",   42};
  static constexpr K745 IK130X  = {"IK130X",  42 + 42};

  static constexpr K745 IK1302_CLASSIC  = {"IK1302",  OFFSET_IK1302_CLASSIC};
  static constexpr K745 IK1303_CLASSIC  = {"IK1303",  OFFSET_IK1303_CLASSIC};
  static constexpr K745 IK1306_CLASSIC  = {"IK1306",  OFFSET_IK1306_CLASSIC};
  static constexpr K745 IR2_1_1_CLASSIC = {"IR2.1_1", OFFSET_IR2_1_1_CLASSIC};
  static constexpr K745 IK1302_EXPANDED  = {"IK1302",  OFFSET_IK1302_EXPANDED};
  static constexpr K745 IK1303_EXPANDED  = {"IK1303",  OFFSET_IK1303_EXPANDED};
  static constexpr K745 IK1306_EXPANDED  = {"IK1306",  OFFSET_IK1306_EXPANDED};
  static constexpr K745 IR2_1_1_EXPANDED = {"IR2.1_1", OFFSET_IR2_1_1_EXPANDED};
  static const K745 CLASSIC_CHIP[] = {IR2_1_0, IR2_2, IK1302_CLASSIC, IK1303_CLASSIC, IK1306_CLASSIC, IR2_1_1_CLASSIC};
  static const K745 EXPANDED_CHIP[] = {IR2_1_0, IR2_2, IK130X, IK1302_EXPANDED, IK1303_EXPANDED, IK1306_EXPANDED, IR2_1_1_EXPANDED};
  static constexpr usize CLASSIC_CHIP_COUNT = sizeof(CLASSIC_CHIP) / sizeof(CLASSIC_CHIP[0]);
  static constexpr usize EXPANDED_CHIP_COUNT = sizeof(EXPANDED_CHIP) / sizeof(EXPANDED_CHIP[0]);
  const K745* active_chips(void);
  usize active_chip_count(void);
} // namespace ring_M

typedef enum { 
  X1 = 0,
  X  = 1,
  Y  = 2,
  Z  = 3,
  T  = 4
} stack;

//enum enum_core61_stage {START, NEXT};

typedef enum
{
    MK61_OK = 0,
    MK61_ERROR
} MK61Result;

typedef enum
{
    NONE   = 0,
    RADIAN = 10,  // Р - радианы
    DEGREE = 11, // Г - градусы
    GRADE  = 12,  // ГРД - грады
    DEGREE_ERASE = 0xFF // Г - градусы установленные как стертое значение флеш (умолчание)
} AngleUnit;

typedef enum
{
    // Offsets in RingM buffer
    REG_X1  =   580 - 42 - 42,
    REG_X   =   580 - 42,
    REG_Y   =   580,
    REG_Z   =   622,
    REG_T   =   622 + 42
} StackRegister;

typedef uint32_t microinstruction_t; // 4-байтные микрокоманды
typedef uint32_t instruction_t;  // 4-байтные команды
typedef uint32_t io_t;
typedef uint32_t mtick_t;

typedef char mk61_register_position_t;

#define MK61_REGISTER_POSITIONS_COUNT       14
#define IK13_MTICK_COUNT                    42
#define IR2_MTICK_COUNT                     252

typedef mk61_register_position_t mk61_register_t[MK61_REGISTER_POSITIONS_COUNT];

typedef struct { // Структура микросхемы К145IИК302 
    uint32_t AMK;

    uint32_t  key_y, key_x, key_xm;
    uint32_t  displayed;
    uint32_t  comma;
    uint32_t  L, S, S1, P, T, MOD, flag_FC;

    uint8_t   R[IK13_MTICK_COUNT];
    uint8_t   ST[IK13_MTICK_COUNT];

    const uint8_t*  pAND_AMK1;                      // Precalc offset from microprograms for signal_I 27..35
    const uint8_t*  pAND_AMK;
    uint8_t*  pM;
}  IK1302;

/**
 * @brief The MK61 emulator object
 */
#define INDICATOR_STRING_LENGTH				15
typedef struct {
    char m_indicator_str[INDICATOR_STRING_LENGTH];
    char m_stack_y_str[INDICATOR_STRING_LENGTH];
    char m_stack_z_str[INDICATOR_STRING_LENGTH];
    AngleUnit m_angle_unit;
} MK61Emu;

extern  IK1302  m_IK1302;
extern  u8      ringM[SIZE_RING_M];

namespace core_61 {

  // The K145IK ROM contains 256 command words per chip. A hook runs immediately
  // before the selected command word is decoded. It may inspect or alter the
  // chip's live R/ST arrays and may substitute another command word for this
  // fetch by changing replacement_address. The original ROM is never modified.
  enum class RomChip : u8 {
    IK1302 = 0,
    IK1303 = 1,
    IK1306 = 2
  };

  struct RomCommandHookContext {
    RomChip chip;
    u8 address;
    u8 replacement_address;
    u8* r;
    u8* st;
  };

  using RomCommandHook = void (*)(RomCommandHookContext& context, void* user_data);
  using RomCommandHookHandle = u32;

  static constexpr usize ROM_COMMAND_HOOK_CAPACITY = 8;
  static constexpr RomCommandHookHandle INVALID_ROM_COMMAND_HOOK = 0;

  #pragma pack(push, 4)
  struct bcd_value { // тип хранимое значение mk61 8 десятичных знаков мантисса, 2 знака порядок, два знака
      u32   mantissa;
      u16   signs_and_pow; // sign mantissa, pow low, pow high, sign pow 
  };
  #pragma pack(pop)

  static constexpr  usize   CLASSIC_PROGRAM_STEP    =   MK61_CLASSIC_PROGRAM_STEPS;
  static constexpr  usize   MAX_PROGRAM_STEP        =   MK61_EXPANDED_PROGRAM_STEPS;
  static constexpr  usize   LAST_PROGRAM_STEP       =   MK61_LAST_PRG_STEP;
  static constexpr  usize   CODE_PAGE_BUFFER_SIZE   =   MAX_PROGRAM_STEP + 1;
  static constexpr  usize   COMMA_RUN_POSITION  =   11;
  extern    bool  edit_program;
  bool      expanded_program_is_on(void);
  void      set_expanded_program_mode(bool enable);
  usize     program_steps(void);
  usize     ring_size(void);
  usize     stack_address(stack reg);

  inline    isize get_ring_address(isize linear_address) {
    const isize cycle_x = ((linear_address % 7) == 0)?  linear_address : (linear_address - 7);
    return 41 + cycle_x * 6;
  }

  inline    void  clear_displayed(void) { m_IK1302.displayed = 0; }

  inline    u8    get_IPH(void)         { return  m_IK1302.R[34] & 0xF; }
  inline    u8    get_IPL(void)         { return  m_IK1302.R[31] & 0xF; }
  inline    u8    get_IP (void)         { return  get_IPH()*10 + get_IPL(); }
  inline    void  set_IP(u8 address)    { m_IK1302.R[34] = (address / 10) & 0xF; m_IK1302.R[31] = address % 10; }
  extern    u8    get_code(i32 addr);

  inline    bool  is_displayed(void)    { return (m_IK1302.displayed != 0); }
  inline    usize comma_position(void)  { return m_IK1302.comma; }
  inline    bool  is_RUN(void)          { return (comma_position() == COMMA_RUN_POSITION); }
  inline    bool  is_CALC(void)         { return (comma_position() != COMMA_RUN_POSITION); }

  extern    usize len_code_command(u8 cod);
  extern    void  set_code_page(const uint8_t* page);
  extern    void  get_code_page(uint8_t* page);
  extern    void  get_stack_register(stack reg, bcd_value &value);
  extern    void  set_stack_register(stack reg, const bcd_value *value);
  extern    void  clear_memory_registers(void);
  extern    bool  has_error(void);

  // Register independent hooks for any combination of chip and ROM command
  // address. Several public hooks may target the same command; they run in
  // registration order and share replacement_address. Registration changes
  // from inside a callback are rejected. A handle removes only its own
  // registration. The count reports public hooks only.
  extern    RomCommandHookHandle register_rom_command_hook(
      RomChip chip, u8 address, RomCommandHook callback, void* user_data = nullptr);
  extern    bool unregister_rom_command_hook(RomCommandHookHandle handle);
  extern    usize registered_rom_command_hook_count(void);
  extern    u32 rom_command_instruction(RomChip chip, u8 address);

  // Snapshot / restore the whole live calculator state (stack ring, the three
  // chip structs, UI mode flags and the angle unit) into an internal buffer.
  // Defined only in the CORE math backend; used to borrow the engine for a
  // transcendental evaluation and hand it back byte-for-byte, including the
  // screen register X2 and any error latch. The default LIBM build never
  // references them, so it pays no RAM for the snapshot buffer.
  extern    void  save_context(void);
  extern    void  restore_context(void);

  // In enhanced mode a registered IK1306:A7 ROM-command hook writes a fresh
  // seven-digit value from a seeded SplitMix stream into the hidden xi word
  // immediately before every K RNG command reads it. No visible calculator
  // register is changed beforehand.
  extern    void  configure_random_seed(bool enable, u64 seed_material);
  extern    void  update_random_seed(u64 seed_material);
  extern    bool  random_seed_enabled(void);

  extern    void  enable(void);
  extern    void  step(void);

  // возращает false - есть изменения в дисплейной строке/ true - нет изменений
  //  - дисплейный буфер buffer обновляется только измененным содержимым
  //  - display_symbols - массив набор символов замены знаков индикатора 
  extern    bool  update_indicator(char* buffer, const char* display_symbols);
}

/*
#ifdef __cplusplus
 extern "C" {
#endif
*/
void    MK61Emu_SetDisplayed(uint32_t value);
uint32_t MK61Emu_GetDisplayed(void);
int     MK61Emu_GetDisplayReg(void);
uint32_t MK61Emu_GetComma(void);
void    MK61Emu_SetKeyPress(const int key1, const int key2);
void    MK61Emu_Cleanup(void);
const u8* MK61Emu_UnpackRegster(u8 nReg, const u8 *pack_number);
void    MK61Emu_ReadRegister(int nReg, char* buffer, const char* display_symbols);

extern const char* read_stack_register(stack reg, char cvalue[15], const char* symbols_set);
extern bool write_stack_register(stack reg, char sign, const char cmantissa[8], isize pow);

usize   MK61Emu_Read_R_mantissa(usize nReg);
usize   MK61Emu_Read_X_as_byte(void);
bool    MK61Emu_IsRunning(void);

void    MK61Emu_SetCode(int addr, uint8_t data);
void    MK61Emu_ClearCodePage(void);

const char* MK61Emu_GetIndicatorStr(const char* display_symbols);
void MK61Emu_SetAngleUnit(AngleUnit angle);
AngleUnit MK61Emu_GetAngleUnit(void);

void  MK61Emu_get_1302_R(char* buff); // experement
/*
#ifdef __cplusplus
}
#endif
*/
#endif
