#include <Arduino.h>
#include "bounded_string.hpp"
#include "config.h"
#if MK61_USE_ARDUINO_EEPROM_FALLBACK
  #include "EEPROM.h"
#endif
#include "lcd_gui.hpp"
#include "tools.hpp"
#include "development.hpp"
#include "focal.hpp"
#include "program_store.hpp"
#include "m61_text.hpp"
#include "shared_scratch.hpp"
#include "settings_journal.hpp"
#include "storage_path.hpp"
#include "runtime_safety.hpp"
#include "mk61emu_core.h"
#include "keyboard.h"
#include "cross_hal.h"
#include "sound_driver.hpp"
#include "tinybasic.hpp"
#if MK61_ANY_LOADABLE_MODULE
  #include "loadable_module_runtime.hpp"
  #include "virtual_fat.hpp"
#endif
#ifdef SPI_FLASH
  #include <SPI.h>
  #include "spi_nor_flash.hpp"
  #include "manual_lifetime.hpp"
#endif
#include "menu.hpp"
#include "debug.h"
#include "dfu_splash.hpp"

#include "ledcontrol.h"
#include <string.h>
using namespace led;

extern void reset_ext_program_state(void);

const  class_LCD_Label  STORE_message(0, 0);
const  class_LCD_Label  STORE_progress_message(0, 1);

static constexpr u8 MK61_STORE_REGISTER_F = 0x4F;
static constexpr u8 MK61_LOAD_REGISTER_F  = 0x6F;
static_assert(shared_scratch::SIZE >= program_store::MAX_MK61_TEXT_SIZE, "shared scratch too small for MK61 scripts");

static const SoundNote STARTUP_JINGLE[] = {
  {392, 120, 25, 25},
  {523, 120, 25, 25},
  {587, 120, 25, 25},
  {659, 240, 0, 25},
};

bool ResolveStoredFile(u16 cwd, const char* args,
                       program_store::Entry& entry) {
  return storage_path::resolve_file(cwd, args, entry) ==
         storage_path::Status::OK;
}

bool ResolveStoredFile(const char* args, program_store::Entry& entry) {
  return ResolveStoredFile(program_store::ROOT_ID, args, entry);
}

// Единая точка запуска сохранённого файла: используется терминалом,
// m61-сценариями и проводником. МК61-скрипты уходят в m61_text::open_program,
// который сам решает — вложенный вызов (изнутри сценария) или свежая загрузка.
bool OpenStoredEntry(const program_store::Entry& entry) {
  switch(entry.type) {
    case program_store::ProgramType::MK61:
      return m61_text::open_program(entry.id);
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      return FocalRunSucceeded(RunFocalProgram(entry.id));
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      return RunTinyBasicProgram(entry.id);
#endif
    case program_store::ProgramType::TEXT:
    case program_store::ProgramType::MK61_STATE:
      return program_store_view_entry(entry);
    case program_store::ProgramType::FONT:
      return program_store_apply_font(entry);
    case program_store::ProgramType::IMAGE1:
#if MK61_ENABLE_WBMP_VIEWER
      return program_store_view_entry(entry);
#else
      return false;
#endif
  }
  return false;
}

bool OpenStoredFile(const char* args) {
  return OpenStoredFile(program_store::ROOT_ID, args);
}

bool OpenStoredFile(u16 cwd, const char* args) {
  program_store::Entry entry;
  if(!ResolveStoredFile(cwd, args, entry)) return false;
  return OpenStoredEntry(entry);
}

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
  if(sequence == NULL || len == 0) {
    sound_sequence_cancel();
    return;
  }
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
  if(runtime_safety::valid_sound_note(note.frequency_Hz, note.duration_ms, note.volume_percent) &&
     note.frequency_Hz > 0 && volume > 0) {
    sound_driver_play_scaled(sound_sequence_pin, note.frequency_Hz, note.duration_ms, volume, note.volume_percent);
  }
  sound_sequence_next_at = now + (t_time_ms) note.duration_ms + (t_time_ms) note.gap_ms;
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

static void Show_DFU_splash(void) {
#if defined(MK61_DISPLAY_UC1609)
  static_assert(dfu_splash::WIDTH == lcd_display::PIXEL_WIDTH,
                "DFU bitmap width must match UC1609 panel");
  static_assert(dfu_splash::HEIGHT == lcd_display::PIXEL_HEIGHT,
                "DFU bitmap height must match UC1609 panel");
  if(main_lcd().showFullscreenBitmap(dfu_splash::BITMAP, dfu_splash::BYTE_COUNT)) return;
#endif

  main_lcd().clear();
  library_mk61::print_localized_at(0, 0, "Прошивка DFU", " DFU flash mode!");
}

void DFU_enable(void) {
    void (*SysMemBootJump)(void);

    Show_DFU_splash();
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
    MK61DisplayUpdate update(main_lcd());
    library_mk61::print_localized_at(0, 0, "OK подтверд", "press OK confirm");
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

// Паттерн из терминала копируется в свой буфер: строка ввода не переживает
// асинхронное воспроизведение.
static SoundNote user_pattern[SOUND_PATTERN_MAX];

bool sound_pattern_start(const SoundNote* notes, usize count) {
  if(notes == NULL || count == 0 || count > SOUND_PATTERN_MAX) return false;
  for(usize i = 0; i < count; i++) {
    if(!runtime_safety::valid_sound_note(notes[i].frequency_Hz, notes[i].duration_ms,
                                         notes[i].volume_percent)) return false;
  }

  sound_stop();
  for(usize i = 0; i < count; i++) user_pattern[i] = notes[i];
  sound_sequence_start(user_pattern, count, PIN_BUZZER);
  return true;
}

void message_and_waitkey(const char* lcd_message) {
  led::on();
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().setCursor(0, 1); main_lcd().print(lcd_message);
  }
  kbd::get_key_wait();
  led::off();
}

// Вставка кода операции в программу mk61s с указанного шага с коррекцией команд,
// содержащих адрес перехода
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

#if defined(ARDUINO_ARCH_STM32) && !defined(PROGRAM_STORE_HOST_TEST)
static manual_lifetime::Storage<SpiNorFlash> mk61_flash_storage;
SpiNorFlash* external_flash_pointer;

void construct_external_flash(void) {
  external_flash_pointer =
    &mk61_flash_storage.construct(PIN_SPIFLASH_CS, &SPI);
}
#else
SpiNorFlash flash(PIN_SPIFLASH_CS);
SpiNorFlash& external_flash(void) { return flash; }
void construct_external_flash(void) {}
#endif
bool      flash_is_ok;

static constexpr u32 LEGACY_EEPROM_PAGE_SIZE = 8 * 1024;

static u32 settings_flash_address(void) {
  return program_store::settings_address();
}

static u16 settings_flash_size(void) {
  return program_store::settings_size();
}

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
  lcd_display::defaultSettingsTextProfile(),
  false
};
static bool persistent_settings_loaded = false;
static bool persistent_settings_sector_dirty = false;
static bool persistent_settings_needs_save = false;
static bool persistent_settings_write_blocked = false;
static u32 persistent_settings_next_address;

static void reset_persistent_settings_cache(void) {
  persistent_settings.grade = 0xFF;
  persistent_settings.counter = 0;
  persistent_settings.flags = 0xFF;
  persistent_settings.sound = 0xFF;
  persistent_settings.text_profile = lcd_display::defaultSettingsTextProfile();
  persistent_settings.text_profile_stored = false;
  persistent_settings_loaded = true;
  persistent_settings_sector_dirty = false;
  persistent_settings_needs_save = true;
  persistent_settings_write_blocked = false;
  persistent_settings_next_address = settings_flash_address();
}

static void apply_settings_record(const settings_journal::RecordData& record) {
  persistent_settings.grade = record.grade;
  persistent_settings.counter = record.counter;
  persistent_settings.flags = record.flags;
  persistent_settings.sound = record.sound;
  persistent_settings.text_profile_stored = false;
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  if(record.text_profile_stored) {
    persistent_settings.text_profile = lcd_display::normalizeSettingsTextProfile({
      record.text_rows,
      record.text_width,
      record.text_height,
      record.text_gap
    });
    persistent_settings.text_profile_stored = true;
  } else {
    persistent_settings.text_profile = lcd_display::defaultSettingsTextProfile();
  }
#else
  persistent_settings.text_profile = lcd_display::defaultSettingsTextProfile();
#endif
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
  persistent_settings.text_profile = lcd_display::defaultSettingsTextProfile();
  persistent_settings.text_profile_stored = false;
  persistent_settings_needs_save = true;
}

static void load_persistent_settings(void) {
  if(persistent_settings_loaded) return;
  persistent_settings_loaded = true;
  const u32 settings_address = settings_flash_address();
  const u16 settings_size = settings_flash_size();
  persistent_settings_next_address = settings_address;
  persistent_settings_sector_dirty = false;
  persistent_settings_needs_save = false;
  persistent_settings_write_blocked = false;

  // Сектор настроек имеет собственный защитный маркер и остаётся пригодным,
  // когда действительный указатель C5 подключён, но оба банка файлового каталога
  // требуют восстановления.
  if(!flash_is_ok || settings_size == 0) {
    import_legacy_settings();
    return;
  }

  settings_journal::Scanner scanner(settings_size);
  while(scanner.active()) {
    u8 record[settings_journal::RECORD_SIZE];
    const u32 address = settings_address + (u32) scanner.next_offset();
    if(!external_flash().readByteArray(address, record, sizeof(record))) {
      // Временная ошибка чтения ни при каких условиях не должна приводить
      // к стиранию потенциально действительных настроек. В течение этой загрузки
      // продолжаем использовать значения по умолчанию и блокируем запись.
      persistent_settings_write_blocked = true;
      persistent_settings_needs_save = true;
      return;
    }
    scanner.consume(record);
  }

  if(scanner.has_value()) {
    apply_settings_record(scanner.latest());
    persistent_settings_needs_save = scanner.migration_needed();
  } else if(scanner.ended_at_erased()) {
    import_legacy_settings();
  } else {
    persistent_settings_needs_save = true;
  }

  persistent_settings_sector_dirty = scanner.needs_reclaim();
  persistent_settings_next_address = settings_address + (u32) scanner.next_offset();
  if(persistent_settings_sector_dirty) persistent_settings_needs_save = true;
}

static bool write_persistent_settings(void) {
  load_persistent_settings();
  // Если флеш-память отсутствует или чтение настроек завершилось ошибкой,
  // повторная попытка в течение этой загрузки бесполезна. Сохраняем изменённое
  // состояние ОЗУ для диагностики, но не заставляем таймер интерфейса повторять
  // попытки бесконечно.
  if(!flash_is_ok || persistent_settings_write_blocked) return true;
  if(!persistent_settings_needs_save) return true;

  const u32 settings_address = settings_flash_address();
  const u16 settings_size = settings_flash_size();
  if(settings_address == 0 || settings_size == 0) return true;
  const u32 end_address = settings_address + settings_size;
  if(persistent_settings_sector_dirty ||
     persistent_settings_next_address > end_address - settings_journal::RECORD_SIZE) {
    if(!program_store::erase_settings()) return false;
    persistent_settings_next_address = settings_address;
    persistent_settings_sector_dirty = false;
  }

  settings_journal::RecordData data = {};
  data.grade = persistent_settings.grade;
  data.counter = persistent_settings.counter;
  data.flags = persistent_settings.flags;
  data.sound = persistent_settings.sound;
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  data.text_profile_stored = persistent_settings.text_profile_stored;
  data.text_rows = persistent_settings.text_profile.rows;
  data.text_width = persistent_settings.text_profile.glyph_width;
  data.text_height = persistent_settings.text_profile.glyph_height;
  data.text_gap = persistent_settings.text_profile.line_gap;
#endif

  u8 record[settings_journal::RECORD_SIZE];
  settings_journal::encode_uncommitted(data, record);
  const u32 address = persistent_settings_next_address;
  if(!external_flash().writeByteArray(address, record, settings_journal::COMMIT_INDEX)) {
    persistent_settings_sector_dirty = true;
    persistent_settings_next_address = end_address;
    return false;
  }
  if(!external_flash().writeByte(address + settings_journal::COMMIT_INDEX, settings_journal::COMMIT_MARKER)) {
    persistent_settings_sector_dirty = true;
    persistent_settings_next_address = end_address;
    return false;
  }

  persistent_settings_next_address += settings_journal::RECORD_SIZE;
  persistent_settings_needs_save = false;
  return true;
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
  if(persistent_settings.flags != flags.raw) {
    persistent_settings.flags = flags.raw;
    persistent_settings_needs_save = true;
  }

  write_persistent_settings();
}

SoundSettings read_sound_settings(void) {
  load_persistent_settings();
  return normalize_sound_settings(persistent_settings.sound);
}

void store_sound_settings(SoundSettings settings) {
  load_persistent_settings();
  settings = normalize_sound_settings(settings.raw);
  if(persistent_settings.sound != settings.raw) {
    persistent_settings.sound = settings.raw;
    persistent_settings_needs_save = true;
  }

  write_persistent_settings();
}

bool read_display_text_profile(lcd_display::TextProfile& out) {
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  load_persistent_settings();
  if(!persistent_settings.text_profile_stored) return false;

  out = lcd_display::normalizeSettingsTextProfile(persistent_settings.text_profile);
  return true;
#else
  (void) out;
  load_persistent_settings();
  return false;
#endif
}

void store_display_text_profile(lcd_display::TextProfile profile) {
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  load_persistent_settings();
  profile = lcd_display::normalizeSettingsTextProfile(profile);
  const bool unchanged = persistent_settings.text_profile_stored &&
    persistent_settings.text_profile.rows == profile.rows &&
    persistent_settings.text_profile.glyph_width == profile.glyph_width &&
    persistent_settings.text_profile.glyph_height == profile.glyph_height &&
    persistent_settings.text_profile.line_gap == profile.line_gap;
  if(!unchanged) {
    persistent_settings.text_profile = profile;
    persistent_settings.text_profile_stored = true;
    persistent_settings_needs_save = true;
  }
  write_persistent_settings();
#else
  (void) profile;
#endif
}

bool store_settings_snapshot(
  SettingsFlags flags,
  SoundSettings sound,
  const lcd_display::TextProfile* text_profile
) {
  load_persistent_settings();
  flags = normalize_settings_flags(flags.raw);
  sound = normalize_sound_settings(sound.raw);

  if(persistent_settings.flags != flags.raw) {
    persistent_settings.flags = flags.raw;
    persistent_settings_needs_save = true;
  }
  if(persistent_settings.sound != sound.raw) {
    persistent_settings.sound = sound.raw;
    persistent_settings_needs_save = true;
  }

#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  if(text_profile != NULL) {
    const lcd_display::TextProfile profile = lcd_display::normalizeSettingsTextProfile(*text_profile);
    const bool unchanged = persistent_settings.text_profile_stored &&
      persistent_settings.text_profile.rows == profile.rows &&
      persistent_settings.text_profile.glyph_width == profile.glyph_width &&
      persistent_settings.text_profile.glyph_height == profile.glyph_height &&
      persistent_settings.text_profile.line_gap == profile.line_gap;
    if(!unchanged) {
      persistent_settings.text_profile = profile;
      persistent_settings.text_profile_stored = true;
      persistent_settings_needs_save = true;
    }
  }
#else
  (void) text_profile;
#endif

  return write_persistent_settings();
}

void store_grade_switch(AngleUnit angle_unit) {
  load_persistent_settings();
  if(angle_unit != RADIAN && angle_unit != GRADE && angle_unit != DEGREE) return;
  if(persistent_settings.grade == (u8) angle_unit) {
    write_persistent_settings();
    return;
  }

  persistent_settings.grade = (u8) angle_unit;
  persistent_settings.counter++;
  persistent_settings_needs_save = true;
  write_persistent_settings();
}

bool erase_slot_old(usize nSlot) {
  if(nSlot > MAX_SLOT_FOR_PROGRAM) return false;
  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  return !program_store::exists(program_store::ProgramType::MK61, name) ||
         program_store::remove(program_store::ProgramType::MK61, name);
}

bool erase_slot(usize nSlot) {
  return erase_slot_old(nSlot);
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
    main_lcd().setCursor(0, 0); main_lcd().print(library_mk61::text("Error! slot > ", "SLOT > ")); main_lcd().print(MAX_SLOT_FOR_PROGRAM);
    return -1;
  } else {
    /*main_lcd().print("slot ");*/ main_lcd().print(n_cell);
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
 
  // Обнаружение через JEDEC/SFDP; для неизвестных микросхем C5 проверяет границы.
  flash_is_ok = external_flash().begin();
  #ifdef DEBUG_SPIFLASH
    if(flash_is_ok) {
      Serial.println("SPI NOR link: OK");
      Serial.print("JEDEC ID: 0x"); Serial.println(external_flash().getJEDECID(), HEX);
      Serial.print("SFDP: "); Serial.println(external_flash().sfdpPresent() ? "yes" : "no");
      Serial.print("declared upper bound: ");
      Serial.print(external_flash().capacityProbeUpper()); Serial.println(" bytes");
    } else {
      Serial.println("SPI NOR link: ERROR");
    }
  #endif
  if(!flash_is_ok) return;

  dbgln(SPIROM, "C5 init: start");
  program_store::init();
#if MK61_ANY_LOADABLE_MODULE
  if(program_store::stage_layout_migration_pending()) {
    dbgln(SPIROM, "C5 module layout migration: recover USB staging");
    const bool session_ready = virtual_fat::reset_session();
    const bool committed = session_ready && virtual_fat::flush_pending();
    virtual_fat::end_session();
    const bool activated = committed &&
        program_store::finish_stage_layout_migration();
    dbgln(SPIROM, activated
        ? "C5 module layout migration: complete"
        : "C5 module layout migration: deferred");
  }
  loadable_module::discard_transfer_staging();
#endif
  #ifdef DEBUG_SPIFLASH
    if(program_store::ready()) {
      Serial.print("C5 init: ready, measured capacity: ");
      Serial.print(external_flash().getCapacity()); Serial.println(" bytes");
    } else if(program_store::mount_status() ==
              program_store::MountStatus::REPAIR_REQUIRED) {
      Serial.println("C5 init: catalogs damaged; explicit format required");
    } else {
      Serial.println("C5 init: failed");
    }
  #endif
}

u8 load_word(isize segment_address, isize offset) {
  (void) segment_address;
  (void) offset;
#if MK61_USE_ARDUINO_EEPROM_FALLBACK
  return EEPROM.read(offset);
#else
  return 0xFF;
#endif
}

bool load_from(isize address) {
  if(address < 0 || address % FLASH_SECTOR_SIZE != 0) return false;
  char name[8];
  snprintf(name, sizeof(name), "%u",
           (unsigned) (address / FLASH_SECTOR_SIZE));
  return m61_text::load_program(name);
}

bool Load(usize nSlot) {
  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  return LoadProgram(name);
}

bool LoadProgram(const char* name) {
  return m61_text::load_program(name);
}

bool LoadProgram(u16 id) {
  return m61_text::load_program(id);
}

bool Load(void) {
  isize address;
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    library_mk61::print_localized_at(0, 0, "ЧТ ", "Load ", 5);
    address = calc_address();
  }
  if(address < 0) return false; // Ошибка

  const usize slot = (usize) (address / FLASH_SECTOR_SIZE);
  return Load(slot);
}

inline bool check_empty_program(void) {
  usize all_to_or = 0;
  const usize program_steps = core_61::program_steps();
  for(usize i=0; i < program_steps; i++) all_to_or |= (usize) core_61::get_code(/*mk61s.*/core_61::get_ring_address(i));
  if(all_to_or == 0) {
    library_mk61::print_localized_at(0, 0, "Нет программ", "No program...");
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
  bounded_string::copy(slot_name, SIZEOF_SLOT_NAME, name);
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

bool DeleteSlot(usize nSlot) {
  if(nSlot > MAX_SLOT_FOR_PROGRAM) return false;
  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  return program_store::remove(program_store::ProgramType::MK61, name);
}

bool StoreProgram(const char* name) {
  return StoreProgram(program_store::ROOT_ID, name);
}

bool StoreProgram(u16 parent_id, const char* name) {
  if(check_empty_program()) return false; // Ошибка
  if(name == NULL || name[0] == 0) return false;

  shared_scratch::Lease scratch(shared_scratch::Owner::M61_FORMAT, program_store::MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) return false;
  u8* script_buffer = scratch.data();
  u16 script_len = 0;
  if(!m61_text::format_current_program(script_buffer, scratch.size(), &script_len)) return false;
  if(!program_store::write_file(parent_id, program_store::INVALID_ID,
                                program_store::ProgramType::MK61, name,
                                script_buffer, script_len, NULL)) return false;

  dbg(MINI, "\nProgramm saved!");
  return true;
}

bool Store(usize nSlot) {
  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) nSlot);
  return StoreProgram(name);
}

bool Store(void) {
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear(); main_lcd().setCursor(0, 0);
  }

  if(check_empty_program()) return false; // Ошибка

  isize address;
  {
    MK61DisplayUpdate update(main_lcd());
    library_mk61::print_localized_at(0, 0, "ПИС ", "Save ", 5); //main_lcd().setCursor(7, 0);
    address = calc_address();
  }
  if(address < 0) return false; // Ошибка

  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) (address / FLASH_SECTOR_SIZE));
  if(program_store::exists(program_store::ProgramType::MK61, name)) {
    #ifdef DEBUG_SPIFLASH
      Serial.print("SPIFLASH: SLOT IS OCCUPIED ");
      Serial.println(address);
    #endif
    sound(PIN_BUZZER, 4000, 750, library_mk61::sound_volume());
    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(0, 0); main_lcd().print(library_mk61::text("OVER", "OVER")); main_lcd().setCursor(8, 0); main_lcd().print(library_mk61::text("press OK", "OK?"));
    }
    if(kbd::get_key_wait() != KEY_OK) return false; // Ошибка
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

  shared_scratch::Lease scratch(shared_scratch::Owner::M61_FORMAT, program_store::MAX_MK61_TEXT_SIZE);
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
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(x, 1); main_lcd().print((char) 0xFF); main_lcd().print(i);
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
    MK61DisplayUpdate update(main_lcd());
    main_lcd().setCursor(0, 0); main_lcd().print(library_mk61::text("press OK ERASED!", "OK CTEP FLASH"));
  }
  if(kbd::get_key_wait() != KEY_OK) return action::MENU_BACK;
 // стираем внешний флеш
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear(); main_lcd().setCursor(0, 0); main_lcd().print(library_mk61::text("Erase slot ", "CTEP SLOT "));
  }
  if(!program_store::format()) {
    message_and_waitkey(library_mk61::text("Flash error", "FLASH ERROR"));
    return action::MENU_BACK;
  }
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear(); main_lcd().setCursor(0, 0); main_lcd().print(library_mk61::text("Erase settings", "CTEP SETUP"));
  }
  bool settings_reset_ok = true;
  if(flash_is_ok) settings_reset_ok = program_store::erase_settings();
  reset_persistent_settings_cache();
  if(settings_reset_ok) write_persistent_settings();
  library_mk61::load_settings_state();
  main_lcd().setTextProfile(library_mk61::display_text_profile());
  sound(PIN_BUZZER, 1000, 300, library_mk61::sound_volume());
  message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
  return action::MENU_EXIT;
}
