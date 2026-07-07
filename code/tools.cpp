#include <Arduino.h>
#include "config.h"
#if MK61_USE_ARDUINO_EEPROM_FALLBACK
  #include "EEPROM.h"
#endif
#include "lcd_gui.hpp"
#include "tools.hpp"
#include "program_store.hpp"
#include "m61_text.hpp"
#include "shared_scratch.hpp"
#include "mk61emu_core.h"
#include "keyboard.h"
#include "cross_hal.h"
#include "sound_driver.hpp"
#ifdef SPI_FLASH
  #include <SPI.h>
  #include <SPIFlash.h>
#endif
#include "menu.hpp"
#include "debug.h"

#include "ledcontrol.h"
using namespace led;

extern void reset_ext_program_state(void);

const  class_LCD_Label  STORE_message(0, 0);
const  class_LCD_Label  STORE_progress_message(0, 1);

const u32 ERASE_SECTOR_TIMEOUT = 5000; // таймаут операции стирания сектора ППЗУ в ms

static constexpr u8 MK61_STORE_REGISTER_F = 0x4F;
static constexpr u8 MK61_LOAD_REGISTER_F  = 0x6F;
static_assert(shared_scratch::SIZE >= program_store::MAX_MK61_TEXT_SIZE, "shared scratch too small for MK61 scripts");

struct SoundNote {
  isize frequency_Hz;
  usize duration_ms;
  usize gap_ms;
  usize volume_percent;
};

static const SoundNote STARTUP_JINGLE[] = {
  {392, 120, 25, 25},
  {523, 120, 25, 25},
  {587, 120, 25, 25},
  {659, 240, 0, 25},
};

static const SoundNote* sound_sequence = NULL;
static usize sound_sequence_len = 0;
static usize sound_sequence_index = 0;
static usize sound_sequence_pin = PIN_BUZZER;
static t_time_ms sound_sequence_next_at = 0;

static void sound_sequence_cancel(void) {
  sound_sequence = NULL;
  sound_sequence_len = 0;
  sound_sequence_index = 0;
}

static void sound_sequence_start(const SoundNote* sequence, usize len, usize pin) {
  sound_sequence = sequence;
  sound_sequence_len = len;
  sound_sequence_index = 0;
  sound_sequence_pin = pin;
  sound_sequence_next_at = millis();
}

static void sound_sequence_poll(void) {
  const t_time_ms now = millis();
  if(sound_sequence == NULL || (i32) (now - sound_sequence_next_at) < 0) {
    return;
  }

  if(sound_sequence_index >= sound_sequence_len) {
    sound_sequence_cancel();
    return;
  }

  const SoundNote note = sound_sequence[sound_sequence_index++];
  const usize volume = library_mk61::sound_volume();
  if(note.frequency_Hz > 0 && note.duration_ms > 0 && volume > 0) {
    sound_driver_play_scaled(sound_sequence_pin, note.frequency_Hz, note.duration_ms, volume, note.volume_percent);
  }
  sound_sequence_next_at = now + note.duration_ms + note.gap_ms;
}

static bool opcode_needs_expanded_memory(u8 opcode) {
  return opcode == MK61_STORE_REGISTER_F || opcode == MK61_LOAD_REGISTER_F;
}

bool program_needs_expanded_memory(const u8* code_page, usize code_len) {
  const usize bounded_len = (code_len > core_61::MAX_PROGRAM_STEP) ? core_61::MAX_PROGRAM_STEP : code_len;

  for(usize i = core_61::CLASSIC_PROGRAM_STEP; i < bounded_len; i++) {
    if(code_page[i] != 0) return true;
  }

  for(usize i = 0; i < bounded_len;) {
    const u8 opcode = code_page[i];
    if(opcode_needs_expanded_memory(opcode)) return true;
    const usize opcode_len = core_61::len_code_command(opcode);
    i += (opcode_len == 0) ? 1 : opcode_len;
  }

  return false;
}

void apply_program_memory_auto(const u8* code_page, usize code_len, bool preserve_program, bool force_expanded) {
  const bool enable_expanded = force_expanded || program_needs_expanded_memory(code_page, code_len);
  if(library_mk61::expanded_program_is_on() == enable_expanded) return;

  u8 saved_code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  if(preserve_program) core_61::get_code_page(&saved_code_page[0]);

  library_mk61::set_program_memory_state(enable_expanded);
  library_mk61::refresh_menu_text();
  library_mk61::store_settings_state();
  reset_ext_program_state();
  core_61::enable();

  if(preserve_program) core_61::set_code_page(&saved_code_page[0]);
}

void ensure_program_memory_for_write(usize linear_addr, u8 opcode) {
  const bool force_expanded = linear_addr >= core_61::CLASSIC_PROGRAM_STEP || opcode_needs_expanded_memory(opcode);
  if(force_expanded) apply_program_memory_auto(NULL, 0, true, true);
}

void DFU_enable(void) {
    void (*SysMemBootJump)(void);

  lcd.clear();
  library_mk61::print_localized_at(0, 0, "Прошивка DFU", " DFU flash mode!");
    __enable_irq();
    HAL_RCC_DeInit();
    HAL_DeInit();
    SysTick->CTRL = 0; SysTick->LOAD = 0; SysTick->VAL = 0;
    __HAL_SYSCFG_REMAPMEMORY_SYSTEMFLASH();

    const uint32_t p = (*((uint32_t *) 0x1FFF0000));
    __set_MSP( p );

    SysMemBootJump = (void (*)(void)) (*((uint32_t *) 0x1FFF0004));
    SysMemBootJump();

  while(true) {};
 
}

bool  Confirmation(void) {
  extern void lcd_std_display_redraw(void);

  {
    MK61DisplayUpdate update(lcd);
    lcd.setCursor(0,0); lcd.print(library_mk61::text("press OK confirm", "OK \001O\003TBEP\003"));
  }
  i32 key = kbd::get_key_wait();
  lcd_std_display_redraw();

  return (key == KEY_OK);
}

void sound_poll(void) {
  sound_driver_poll();
  sound_sequence_poll();
}

void delay_with_sound_poll(t_time_ms duration_ms) {
  const t_time_ms stop_at = millis() + duration_ms;
  do {
    sound_poll();
    delay(1);
  } while((i32) (millis() - stop_at) < 0);
  sound_poll();
}

void sound_scaled(usize pin, isize freq_Hz, usize duration_ms, usize volume, usize volume_percent) {
  sound_sequence_cancel();
  sound_driver_play_scaled(pin, freq_Hz, duration_ms, volume, volume_percent);
}

void  sound(usize pin, isize freq_Hz, usize duration_ms, usize volume) {
  sound_scaled(pin, freq_Hz, duration_ms, volume, 100);
}

void  sound_stop(void) {
  sound_sequence_cancel();
  sound_driver_stop();
}

void sound_startup(void) {
  sound_sequence_start(STARTUP_JINGLE, sizeof(STARTUP_JINGLE) / sizeof(STARTUP_JINGLE[0]), PIN_BUZZER);
}

void message_and_waitkey(const char* lcd_message) {
  led::on();
  {
    MK61DisplayUpdate update(lcd);
    lcd.setCursor(0, 1); lcd.print(lcd_message);
  }
  kbd::get_key_wait();
  led::off();
}

// Вставка команды opcode, в программу mk61s с шага step, с коррекцией команд с переходом по адресу перехода
void  insert_cmd_in_program(usize into_step, usize opcode) {
  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};

  dbgln(MINI, "Insert comand <", opcode, "> in program step ", into_step);
  
  core_61::get_code_page(&code_page[0]);

  bool  inc_operand = false;
  u8    move_code, copy_code = opcode;

  const usize program_steps = core_61::program_steps();
  for(usize i = into_step; i < program_steps; i++) {
    move_code = code_page[i];

    if(inc_operand) {
      // необходима коррекция операнда предыдущей команды
      if(copy_code >= into_step) copy_code++;
      inc_operand = false;
    } else { // рассматриваемое данное это команда, не операнд!
      if(core_61::len_code_command(copy_code) == 2) { 
      // установить необходимость коррекция второго операнда команды (адреса перехода)
        dbgln(MINI, "Step ", i, " 2 operand opcode: ", copy_code);
        inc_operand = true;
      }
    }
    code_page[i] = copy_code;
    copy_code = move_code;
  }
  core_61::set_code_page(code_page);
}

SPIFlash  flash(PIN_SPIFLASH_CS);
bool      flash_is_ok;

static constexpr u32 SETTINGS_FLASH_SECTOR = (MAX_SLOT_FOR_PROGRAM + 2) * FLASH_SECTOR_SIZE;
static constexpr usize SETTINGS_RECORD_SIZE = 16;
static constexpr u8 SETTINGS_RECORD_VERSION_1 = 1;
static constexpr u8 SETTINGS_RECORD_VERSION = 2;
static constexpr u8 SETTINGS_MAGIC_0 = 'M';
static constexpr u8 SETTINGS_MAGIC_1 = '6';
static constexpr u8 SETTINGS_MAGIC_2 = '1';
static constexpr u8 SETTINGS_MAGIC_3 = 'S';
static constexpr u8 SETTINGS_IDX_MAGIC_0 = 0;
static constexpr u8 SETTINGS_IDX_MAGIC_1 = 1;
static constexpr u8 SETTINGS_IDX_MAGIC_2 = 2;
static constexpr u8 SETTINGS_IDX_MAGIC_3 = 3;
static constexpr u8 SETTINGS_IDX_VERSION = 4;
static constexpr u8 SETTINGS_IDX_GRADE = 5;
static constexpr u8 SETTINGS_IDX_COUNTER = 6;
static constexpr u8 SETTINGS_IDX_FLAGS = 7;
static constexpr u8 SETTINGS_IDX_SOUND = 8;
static constexpr u8 SETTINGS_IDX_V1_CRC = 9;
static constexpr u8 SETTINGS_IDX_TEXT_ROWS = 9;
static constexpr u8 SETTINGS_IDX_TEXT_WIDTH = 10;
static constexpr u8 SETTINGS_IDX_TEXT_HEIGHT = 11;
static constexpr u8 SETTINGS_IDX_TEXT_GAP = 12;
static constexpr u8 SETTINGS_IDX_TEXT_EFFECT = 13;
static constexpr u8 SETTINGS_IDX_CRC = 14;
static constexpr u32 LEGACY_EEPROM_PAGE_SIZE = 8 * 1024;

struct PersistentSettings {
  u8 grade;
  u8 counter;
  u8 flags;
  u8 sound;
  lcd_display::TextProfile text_profile;
  bool text_profile_stored;
};

static PersistentSettings persistent_settings = {
  0xFF,
  0,
  0xFF,
  0xFF,
  lcd_display::defaultTextProfileForRows(lcd_display::DEFAULT_ROWS),
  false
};
static bool persistent_settings_loaded = false;
static bool persistent_settings_sector_dirty = false;
static u32 persistent_settings_next_address = SETTINGS_FLASH_SECTOR;

static u8 settings_record_crc(const u8* record, u8 crc_index) {
  u8 crc = 0xA5;
  for(u8 i = 0; i < crc_index; i++) {
    crc = (u8) ((crc << 1) | (crc >> 7));
    crc ^= record[i];
  }
  return crc;
}

static bool settings_record_is_valid(const u8* record) {
  if(record[SETTINGS_IDX_MAGIC_0] != SETTINGS_MAGIC_0) return false;
  if(record[SETTINGS_IDX_MAGIC_1] != SETTINGS_MAGIC_1) return false;
  if(record[SETTINGS_IDX_MAGIC_2] != SETTINGS_MAGIC_2) return false;
  if(record[SETTINGS_IDX_MAGIC_3] != SETTINGS_MAGIC_3) return false;
  if(record[SETTINGS_IDX_VERSION] == SETTINGS_RECORD_VERSION_1) {
    return record[SETTINGS_IDX_V1_CRC] == settings_record_crc(record, SETTINGS_IDX_V1_CRC);
  }
  if(record[SETTINGS_IDX_VERSION] == SETTINGS_RECORD_VERSION) {
    return record[SETTINGS_IDX_CRC] == settings_record_crc(record, SETTINGS_IDX_CRC);
  }
  return false;
}

static void apply_settings_record(const u8* record) {
  persistent_settings.grade = record[SETTINGS_IDX_GRADE];
  persistent_settings.counter = record[SETTINGS_IDX_COUNTER];
  persistent_settings.flags = record[SETTINGS_IDX_FLAGS];
  persistent_settings.sound = record[SETTINGS_IDX_SOUND];
  persistent_settings.text_profile_stored = false;
  if(record[SETTINGS_IDX_VERSION] == SETTINGS_RECORD_VERSION) {
    persistent_settings.text_profile = lcd_display::normalizeTextProfile({
      record[SETTINGS_IDX_TEXT_ROWS],
      record[SETTINGS_IDX_TEXT_WIDTH],
      record[SETTINGS_IDX_TEXT_HEIGHT],
      record[SETTINGS_IDX_TEXT_GAP],
      record[SETTINGS_IDX_TEXT_EFFECT]
    });
    persistent_settings.text_profile_stored = true;
  }
}

static u16 internal_flash_size_kb(void) {
#if defined(FLASHSIZE_BASE)
  return *((const volatile u16*) FLASHSIZE_BASE);
#else
  return 0;
#endif
}

static u8 read_legacy_eeprom_byte(usize offset) {
#if defined(FLASH_BASE)
  const u16 flash_size_kb = internal_flash_size_kb();
  if(flash_size_kb == 0 || flash_size_kb == 0xFFFF) return 0xFF;
  const u32 base = FLASH_BASE + ((u32) flash_size_kb * 1024UL) - LEGACY_EEPROM_PAGE_SIZE;
  return *((const volatile u8*) (base + offset));
#else
  (void) offset;
  return 0xFF;
#endif
}

static u8 read_legacy_eeprom_with_legacy(usize current_addr, usize legacy_addr) {
  const u8 current_value = read_legacy_eeprom_byte(current_addr);
  if(current_value != 0xFF) return current_value;
  return read_legacy_eeprom_byte(legacy_addr);
}

static void import_legacy_settings(void) {
  const u8 grade = read_legacy_eeprom_with_legacy(switch_R_GRD_G, legacy_switch_R_GRD_G);
  const u8 counter = read_legacy_eeprom_with_legacy(count_switch_R_GRD_G, legacy_count_switch_R_GRD_G);
  const u8 flags = read_legacy_eeprom_byte(switch_settings);
  const u8 sound = read_legacy_eeprom_byte(switch_sound_settings);

  persistent_settings.grade = grade;
  persistent_settings.counter = (counter == 0xFF) ? 0 : counter;
  persistent_settings.flags = flags;
  persistent_settings.sound = sound;
  persistent_settings.text_profile = lcd_display::defaultTextProfileForRows(lcd_display::DEFAULT_ROWS);
  persistent_settings.text_profile_stored = false;
}

static void load_persistent_settings(void) {
  if(persistent_settings_loaded) return;
  persistent_settings_loaded = true;
  persistent_settings_next_address = SETTINGS_FLASH_SECTOR;
  persistent_settings_sector_dirty = false;

  if(!flash_is_ok) {
    import_legacy_settings();
    return;
  }

  const u32 end_address = SETTINGS_FLASH_SECTOR + FLASH_SECTOR_SIZE;
  for(u32 address = SETTINGS_FLASH_SECTOR; address + SETTINGS_RECORD_SIZE <= end_address; address += SETTINGS_RECORD_SIZE) {
    const u8 first = flash.readByte(address);
    if(first == 0xFF) {
      if(address == SETTINGS_FLASH_SECTOR) import_legacy_settings();
      persistent_settings_next_address = address;
      return;
    }

    u8 record[SETTINGS_RECORD_SIZE];
    record[0] = first;
    for(u8 i = 1; i < sizeof(record); i++) record[i] = flash.readByte(address + i);

    if(!settings_record_is_valid(record)) {
      persistent_settings_next_address = end_address;
      persistent_settings_sector_dirty = true;
      return;
    }

    apply_settings_record(record);
    persistent_settings_next_address = address + SETTINGS_RECORD_SIZE;
  }

  persistent_settings_sector_dirty = true;
}

static void write_persistent_settings(void) {
  load_persistent_settings();
  if(!flash_is_ok) return;

  const u32 end_address = SETTINGS_FLASH_SECTOR + FLASH_SECTOR_SIZE;
  if(persistent_settings_sector_dirty || persistent_settings_next_address + SETTINGS_RECORD_SIZE > end_address) {
    if(!flash.eraseSector(SETTINGS_FLASH_SECTOR)) return;
    persistent_settings_next_address = SETTINGS_FLASH_SECTOR;
    persistent_settings_sector_dirty = false;
  }

  u8 record[SETTINGS_RECORD_SIZE] = {
    SETTINGS_MAGIC_0,
    SETTINGS_MAGIC_1,
    SETTINGS_MAGIC_2,
    SETTINGS_MAGIC_3,
    SETTINGS_RECORD_VERSION,
    persistent_settings.grade,
    persistent_settings.counter,
    persistent_settings.flags,
    persistent_settings.sound,
    persistent_settings.text_profile.rows,
    persistent_settings.text_profile.glyph_width,
    persistent_settings.text_profile.glyph_height,
    persistent_settings.text_profile.line_gap,
    persistent_settings.text_profile.effect,
    0xFF,
    0xFF
  };
  record[SETTINGS_IDX_CRC] = settings_record_crc(record, SETTINGS_IDX_CRC);

  const u32 address = persistent_settings_next_address;
  for(u8 i = 0; i < sizeof(record); i++) flash.writeByte(address + i, record[i]);
  persistent_settings_next_address += SETTINGS_RECORD_SIZE;
}

AngleUnit read_stored_grade_switch(void) {
  load_persistent_settings();
  return (AngleUnit) persistent_settings.grade;
}

u8 read_counter_switch(void) {
  load_persistent_settings();
  return persistent_settings.counter;
}

SettingsFlags read_settings_flags(void) {
  load_persistent_settings();
  return normalize_settings_flags(persistent_settings.flags);
}

void store_settings_flags(SettingsFlags flags) {
  load_persistent_settings();
  flags = normalize_settings_flags(flags.raw);
  if(persistent_settings.flags == flags.raw) return;

  persistent_settings.flags = flags.raw;
  write_persistent_settings();
}

SoundSettings read_sound_settings(void) {
  load_persistent_settings();
  return normalize_sound_settings(persistent_settings.sound);
}

void store_sound_settings(SoundSettings settings) {
  load_persistent_settings();
  settings = normalize_sound_settings(settings.raw);
  if(persistent_settings.sound == settings.raw) return;

  persistent_settings.sound = settings.raw;
  write_persistent_settings();
}

bool read_display_text_profile(lcd_display::TextProfile& out) {
  load_persistent_settings();
  if(!persistent_settings.text_profile_stored) return false;

  out = lcd_display::normalizeTextProfile(persistent_settings.text_profile);
  return true;
}

void store_display_text_profile(lcd_display::TextProfile profile) {
  load_persistent_settings();
  profile = lcd_display::normalizeTextProfile(profile);
  const bool unchanged = persistent_settings.text_profile_stored &&
    persistent_settings.text_profile.rows == profile.rows &&
    persistent_settings.text_profile.glyph_width == profile.glyph_width &&
    persistent_settings.text_profile.glyph_height == profile.glyph_height &&
    persistent_settings.text_profile.line_gap == profile.line_gap &&
    persistent_settings.text_profile.effect == profile.effect;
  if(unchanged) return;

  persistent_settings.text_profile = profile;
  persistent_settings.text_profile_stored = true;
  write_persistent_settings();
}

void store_grade_switch(AngleUnit angle_unit) {
  load_persistent_settings();
  const u8 next_counter = read_counter_switch() + 1;
  if(persistent_settings.grade == (u8) angle_unit && persistent_settings.counter == next_counter) return;

  persistent_settings.grade = (u8) angle_unit;
  persistent_settings.counter = next_counter;
  write_persistent_settings();
}

bool erase_slot_old(usize nSlot) {
  const isize segment_address = calc_address(nSlot);
  if(segment_address < 0) return false;
  
  dbgln(SPIROM, "SPIFLASH: erase sector #", segment_address);
  while (!flash.eraseSector(segment_address));
  return true;
}

bool erase_slot(usize nSlot) {
  const isize segment_address = calc_address(nSlot);
  if(segment_address < 0) return false;
  
  dbgln(SPIROM, "SPIFLASH: erase sector #", segment_address);
  
  const u32 TimeIsOut = millis() + ERASE_SECTOR_TIMEOUT; // Запоминаем время начала
  while (!flash.eraseSector(segment_address)) {
    if (millis() >= TimeIsOut) { // Проверяем превышение таймаута
      dbgln(SPIROM, "SPIFLASH: erase sector timeout!");
      return false;
    }
    // Возможна короткая пауза для снижения нагрузки на процессор
    // HAL_Delay(1); // Раскомментировать при необходимости
  }
  return true;
}

usize seek_program_END(u8* code_page) {
  const isize program_steps = (isize) core_61::program_steps();
  isize lastCommand = program_steps;
  while (lastCommand > 0 && code_page[lastCommand] == 0) {
    lastCommand--;
  }

  if(lastCommand == 0 && code_page[0] == 0) return 0;
  if(lastCommand < program_steps) lastCommand++;
  if(lastCommand < program_steps) lastCommand++;

  return lastCommand;
}

isize  calc_address(usize nSlot) {
  if(nSlot > MAX_SLOT_FOR_PROGRAM) return -1;

  const int address = nSlot * FLASH_SECTOR_SIZE;

  dbgln(SPIROM, "X-reg as addsress ", address);
  return address;
}

isize  calc_address(void) {
  const isize n_cell = MK61Emu_GetDisplayReg();

  if(n_cell > MAX_SLOT_FOR_PROGRAM) {
    lcd.setCursor(0, 0); lcd.print(library_mk61::text("Error! slot > ", "SLOT > ")); lcd.print(MAX_SLOT_FOR_PROGRAM);
    return -1;
  } else {
    /*lcd.print("slot ");*/ lcd.print(n_cell);
  }

  const int address = n_cell * FLASH_SECTOR_SIZE;

  #ifdef SERIAL_OUTPUT
    Serial.print("X-reg as addsress "); Serial.println(address);
  #endif
  return address;
}

void init_external_flash(void) {
  dbgln(SPIROM, "Init flash -> ");

  // Инициализация SPI
  SPI.begin();
 
  // Инициализация W25Q128
  flash_is_ok = flash.begin();
  #ifdef DEBUG_SPIFLASH
    if(flash_is_ok) {
      Serial.print("OK! size = "); Serial.print(flash.getCapacity()); Serial.println(" K");
    } else {
      Serial.println("ERROR!");
    }
  #endif
  if(flash_is_ok) program_store::init();
}

u8 load_word(isize segment_address, isize offset) {
  if(flash_is_ok) return flash.readByte(offset + segment_address);
#if MK61_USE_ARDUINO_EEPROM_FALLBACK
  return EEPROM.read(offset);
#else
  return 0xFF;
#endif
}

bool load_from(isize address) {
  if(load_word(address, OFFSET_FLAG_OCCUPIED) != SLOT_OCCUPIED) {
    dbgln(SPIROM, "SPIFLASH: SLOT IS EMPTY ", address, "Nothing to load! canceled!");
    lcd.print(library_mk61::text(" is empty", " HET"));
    sound(PIN_BUZZER, 4000, 750, library_mk61::sound_volume());
    delay_with_sound_poll(1500);
    return false; // error
  }

  dbgln(SPIROM, "SPIFLASH: read from address ", address);

  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  for(usize i=0; i < core_61::MAX_PROGRAM_STEP; i++) {
    u8 code = load_word(address, OFFSET_MK61_PROGRAMM + i);
    if(i >= core_61::CLASSIC_PROGRAM_STEP && code == 0xFF) code = 0;
    code_page[i] = code;
  }

  apply_program_memory_auto(&code_page[0], core_61::MAX_PROGRAM_STEP, false);

  const usize program_steps = core_61::program_steps();
  for(usize i=0; i < program_steps; i++){
    MK61Emu_SetCode(core_61::get_ring_address(i), code_page[i]);
  }
  return true;
}

bool Load(usize nSlot) {
  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  return LoadProgram(name);
}

bool LoadProgram(const char* name) {
  if(name == NULL || name[0] == 0) return false;
  shared_scratch::Lease scratch(shared_scratch::Owner::M61_SCRIPT, program_store::MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) return false;
  u8* script_buffer = scratch.data();
  u16 script_len = 0;
  if(!program_store::read_mk61(name, script_buffer, scratch.size(), &script_len)) return false;
  return m61_text::execute(script_buffer, script_len);
}

bool Load(void) {
  isize address;
  {
    MK61DisplayUpdate update(lcd);
    lcd.clear();
    lcd.setCursor(0, 0); lcd.print(library_mk61::text("Load ", "\321T "));
    address = calc_address();
  }
  if(address < 0) return false; // error

  return load_from(address);
}

inline void store_word(isize segment_address, isize offset, u8 data) {
    if(flash_is_ok) {
      flash.writeByte(offset + segment_address, data);
    }
#if MK61_USE_ARDUINO_EEPROM_FALLBACK
    else {
      EEPROM.update(offset, data);
    }
#endif
}

inline bool check_empty_program(void) {
  usize all_to_or = 0;
  const usize program_steps = core_61::program_steps();
  for(usize i=0; i < program_steps; i++) all_to_or |= (usize) core_61::get_code(/*mk61s.*/core_61::get_ring_address(i));
  if(all_to_or == 0) {
    lcd.print(library_mk61::text("No program...", "HET \001PO\005PAMM"));
    sound(PIN_BUZZER, 4000, 750, library_mk61::sound_volume());
    delay_with_sound_poll(1500);
    return true;
  }
  return false;
}

char* ReadSlotName(usize nSlot, char* slot_name) {
  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  if(!program_store::exists(program_store::ProgramType::MK61, name)) return NULL;
  strncpy(slot_name, name, SIZEOF_SLOT_NAME - 1);
  slot_name[SIZEOF_SLOT_NAME - 1] = 0;
  return slot_name;
}

bool clear_storage(void) {
  return program_store::format();
}

bool Rename(usize nSlot, char* slot_name) {
  char old_name[8];
  snprintf(old_name, sizeof(old_name), "%u", (unsigned) nSlot);
  return program_store::rename(program_store::ProgramType::MK61, old_name, slot_name);
}

bool Store(usize nSlot) {
  if(check_empty_program()) return false; // error

  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  shared_scratch::Lease scratch(shared_scratch::Owner::M61_SCRIPT, program_store::MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) return false;
  u8* script_buffer = scratch.data();
  u16 script_len = 0;
  if(!m61_text::format_current_program(script_buffer, scratch.size(), &script_len)) return false;
  if(!program_store::write_mk61(name, script_buffer, script_len)) return false;

  dbg(MINI, "\nProgramm saved!");
  return true;
}

bool Store(void) {
  {
    MK61DisplayUpdate update(lcd);
    lcd.clear(); lcd.setCursor(0, 0);
  }

  if(check_empty_program()) return false; // error

  isize address;
  {
    MK61DisplayUpdate update(lcd);
    lcd.print(library_mk61::text("Save ", "\001\004C ")); //lcd.setCursor(7, 0);
    address = calc_address();
  }
  if(address < 0) return false; // error

  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) (address / FLASH_SECTOR_SIZE));
  if(program_store::exists(program_store::ProgramType::MK61, name)) {
    #ifdef DEBUG_SPIFLASH
      Serial.print("SPIFLASH: SLOT IS OCCUPIED ");
      Serial.println(address);
    #endif
    sound(PIN_BUZZER, 4000, 750, library_mk61::sound_volume());
    {
      MK61DisplayUpdate update(lcd);
      lcd.setCursor(0, 0); lcd.print(library_mk61::text("OVER", "OVER")); lcd.setCursor(8, 0); lcd.print(library_mk61::text("press OK", "OK?"));
    }
    if(kbd::get_key_wait() != KEY_OK) return false; // error
  }

  #ifdef DEBUG_SPIFLASH
    Serial.print("SPIFLASH: write to address ");
    Serial.println(address);
  #endif

  #ifdef DEBUG_SPIFLASH
    Serial.print("SPIFLASH: erase sector...");
  #endif
  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  core_61::get_code_page(&code_page[0]);
  const usize code_len = seek_program_END(&code_page[0]);

  shared_scratch::Lease scratch(shared_scratch::Owner::M61_SCRIPT, program_store::MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) return false;
  u8* script_buffer = scratch.data();
  u16 script_len = 0;
  if(!m61_text::format_current_program(script_buffer, scratch.size(), &script_len)) return false;

  #ifdef SERIAL_OUTPUT
    Serial.print("Save ");
  #endif

  for(usize i = 0; i < code_len; i++){
    #ifdef SERIAL_OUTPUT
      Serial.write('#');
    #endif
    const u8 x = i / BLOCK_SIZE;
    {
      MK61DisplayUpdate update(lcd);
      lcd.setCursor(x, 1); lcd.print((char) 0xFF); lcd.print(i);
    }
  }
  if(!program_store::write_mk61(name, script_buffer, script_len)) return false;

  #ifdef SERIAL_OUTPUT
    Serial.println("\nProgramm saved!");
  #endif
  return true;
}              

using namespace action;

bool  EraseFlash(void) {
  sound(PIN_BUZZER, 4000, 750, library_mk61::sound_volume());
  {
    MK61DisplayUpdate update(lcd);
    lcd.setCursor(0, 0); lcd.print(library_mk61::text("press OK ERASED!", "OK CTEP FLASH"));
  }
  if(kbd::get_key_wait() != KEY_OK) return action::MENU_BACK;
 // стираем внешний флеш
  {
    MK61DisplayUpdate update(lcd);
    lcd.clear(); lcd.setCursor(0, 0); lcd.print(library_mk61::text("Erase slot ", "CTEP SLOT "));
  }
  for(usize i=0; i <= MAX_SLOT_FOR_PROGRAM; i++){
     erase_slot(i);
     {
       MK61DisplayUpdate update(lcd);
       lcd.setCursor(11, 0); lcd.print(i);
     }
  }
  program_store::init();
  sound(PIN_BUZZER, 1000, 300, library_mk61::sound_volume());
  message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
  return action::MENU_EXIT;
}
