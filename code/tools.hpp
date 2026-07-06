#ifndef TOOLS
#define TOOLS

#include "rust_types.h"
#include "EEPROM.h"
#include "mk61emu_core.h"
#include "program_store.hpp"

#include "debug.h"

#include <stdio.h>

static constexpr usize FLASH_SECTOR_SIZE    = 4096;
static constexpr u8    SLOT_OCCUPIED        = 0x55;
static constexpr usize OFFSET_FLAG_OCCUPIED = 0;
static constexpr usize OFFSET_MK61_PROGRAMM = 1;
static constexpr usize OFFSET_AFTER_PROGRAM = OFFSET_MK61_PROGRAMM + core_61::MAX_PROGRAM_STEP;
static constexpr usize OFFSET_SLOT_NAME     = 384;
static constexpr usize SIZEOF_SLOT_NAME     = 16;
static constexpr isize MAX_SLOT_FOR_PROGRAM = 99;
static constexpr isize BLOCK_SIZE           = (core_61::MAX_PROGRAM_STEP + 1) / 13;

static constexpr usize switch_R_GRD_G = OFFSET_AFTER_PROGRAM;
static constexpr usize count_switch_R_GRD_G = switch_R_GRD_G + 1;
static constexpr usize switch_settings = switch_R_GRD_G + 2;
static constexpr usize switch_sound_settings = switch_settings + 1;
static constexpr usize legacy_switch_R_GRD_G = OFFSET_MK61_PROGRAMM + core_61::CLASSIC_PROGRAM_STEP;
static constexpr usize legacy_count_switch_R_GRD_G = legacy_switch_R_GRD_G + 1;

class DeferredSave {
  private:
    bool pending_save;
    t_time_ms save_at;

  public:
    DeferredSave(void) : pending_save(false), save_at(0) {}

    bool pending(void) const {
      return pending_save;
    }

    void schedule(t_time_ms now, t_time_ms delay_ms) {
      pending_save = true;
      save_at = now + delay_ms;
    }

    bool due(t_time_ms now) const {
      return pending_save && (i32) (now - save_at) >= 0;
    }

    void clear(void) {
      pending_save = false;
    }
};

struct SettingsFlags {
  union {
    u8 raw;
    struct {
      u8 language_ru : 1;
      u8 program_memory_mode : 2;
      u8 speed_mode : 2;
      u8 reserved : 3;
    } bits;
  };

  SettingsFlags(void) : raw(0) {}
  explicit SettingsFlags(u8 value) : raw(value) {}
};

static_assert(sizeof(SettingsFlags) == 1, "SettingsFlags must fit one EEPROM byte");

struct SoundSettings {
  union {
    u8 raw;
    struct {
      u8 volume : 4;
      u8 reserved : 4;
    } bits;
  };

  SoundSettings(void) : raw(0) {}
  explicit SoundSettings(u8 value) : raw(value) {}
};

static_assert(sizeof(SoundSettings) == 1, "SoundSettings must fit one EEPROM byte");

extern  void  DFU_enable(void);
extern  void  sound(usize pin, isize freq_Hz, usize duration_ms);
extern  void  sound_poll(void);
extern  void  delay_with_sound_poll(t_time_ms duration_ms);

extern  void  message_and_waitkey(const char* lcd_message);
extern  bool  Confirmation(void);

extern  bool  flash_is_ok;
extern  isize calc_address(usize nSlot);
extern  char* ReadSlotName(usize nSlot, char* slot_name);
extern  bool  Rename(usize nSlot, char* slot_name);
extern  bool  Store(void);
extern  bool  Store(usize nSlot);
extern  bool  Load(void);
extern  bool  Load(usize nSlot);
extern  u8    load_word(isize segment_address, isize offset);
extern  bool  EraseFlash(void);
extern  bool  clear_storage(void);
extern  bool  erase_slot(usize nSlot);
extern  void  init_external_flash(void);

extern usize  seek_program_END(u8* code_page);
extern  void  insert_cmd_in_program(usize into_step, usize opcode);
extern  bool  program_needs_expanded_memory(const u8* code_page, usize code_len);
extern  void  apply_program_memory_auto(const u8* code_page, usize code_len, bool preserve_program, bool force_expanded = false);
extern  void  ensure_program_memory_for_write(usize linear_addr, u8 opcode);

inline bool IsOccupied(usize nSlot) {
   char name[8];
   snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
   return program_store::exists(program_store::ProgramType::MK61, name);
}

inline void ErrorReaction(void) {
  sound(PIN_BUZZER, 4000, 750);
}

inline bool IsDecimalDigit(char symbol) {
  return ((symbol >= '0') && (symbol <= '9'));
}

inline isize DecimalDigit(char Symbol) {
  Symbol -= '0';
  return (Symbol <= 9)? Symbol : -1;
}

inline isize HexdecimalDigit(char Symbol) {
  if(Symbol >= '0' && Symbol <= '9')
    return Symbol - '0';
  else if (Symbol >= 'A' && Symbol <= 'F')
    return Symbol - 'A' + 10;
  else if (Symbol >= 'a' && Symbol <= 'f')
    return Symbol - 'a' + 10;
  else 
    return -1;
}

#ifdef SERIAL_OUTPUT
inline void Serial_write_hex(u8 code) {
    if(code < 0x10) Serial.write('0');
    Serial.print(code, HEX);
}

inline void Serial_writeln_hex(u8 code) {
    if(code < 0x10) Serial.write('0');
    Serial.println(code, HEX);
}
#endif

inline u64 pad_left_8_char(char* string_8_char) {
  u64 result = *(uint64_t*) string_8_char;
  while((result & 0x0000FF0000000000) == 0) {
    result = (result << 8) | 0x0000000000000020;
  }
  return result;
}

inline u8 read_eeprom_with_legacy(usize current_addr, usize legacy_addr) {
  const u8 current_value = EEPROM.read(current_addr);
  if(current_value != 0xFF) return current_value;

  const u8 legacy_value = EEPROM.read(legacy_addr);
  if(legacy_value != 0xFF) {
    EEPROM.update(current_addr, legacy_value);
    EEPROM.update(legacy_addr, 0);
    return legacy_value;
  }

  return current_value;
}

inline AngleUnit read_stored_grade_switch(void) {
  return (AngleUnit) read_eeprom_with_legacy(switch_R_GRD_G, legacy_switch_R_GRD_G);
}

inline AngleUnit read_grade_switch(void) {
  return MK61Emu_GetAngleUnit();
}

inline u8 read_counter_switch(void) {
  return read_eeprom_with_legacy(count_switch_R_GRD_G, legacy_count_switch_R_GRD_G);
}

inline SettingsFlags normalize_settings_flags(u8 raw_flags) {
  SettingsFlags flags((raw_flags == 0xFF) ? 0 : raw_flags);
  if(raw_flags == 0xFF || flags.bits.program_memory_mode > 2) flags.bits.program_memory_mode = 2;
  if(raw_flags == 0xFF || flags.bits.speed_mode > 2) flags.bits.speed_mode = 1;
  flags.bits.reserved = 0;
  return flags;
}

inline SettingsFlags read_settings_flags(void) {
  return normalize_settings_flags(EEPROM.read(switch_settings));
}

inline void store_settings_flags(SettingsFlags flags) {
  flags.bits.reserved = 0;
  EEPROM.update(switch_settings, flags.raw);
}

inline SoundSettings normalize_sound_settings(u8 raw_settings) {
  SoundSettings settings((raw_settings == 0xFF) ? 0 : raw_settings);
  if(raw_settings == 0xFF || settings.bits.volume > 10) settings.bits.volume = 10;
  settings.bits.reserved = 0;
  return settings;
}

inline SoundSettings read_sound_settings(void) {
  return normalize_sound_settings(EEPROM.read(switch_sound_settings));
}

inline void store_sound_settings(SoundSettings settings) {
  settings.bits.reserved = 0;
  EEPROM.update(switch_sound_settings, settings.raw);
}

inline AngleUnit load_grade_switch(void) {
  static const AngleUnit rom_angle = read_stored_grade_switch();
  if(rom_angle == RADIAN || rom_angle == GRADE || rom_angle == DEGREE) { // состояние переключателя считано из флеш как определнное (радианы или грады)
    MK61Emu_SetAngleUnit(rom_angle);
    dbgln(SPIROM, "get grade_switch ", rom_angle);
    return rom_angle;
  } else { // из флеш считано либо "чистое" значение (FF - градусы), либо неопределенное в следствии сбоя очистки и записи в флеш
    MK61Emu_SetAngleUnit(DEGREE);
    dbgln(SPIROM, "get grade_switch as CLEAR (FF) set to ", DEGREE);
    return DEGREE;
  }
}

inline void store_grade_switch(AngleUnit angle_unit) {
  EEPROM.update(switch_R_GRD_G, (u8) angle_unit);
  EEPROM.update(count_switch_R_GRD_G, read_counter_switch() + 1);
}

#endif
