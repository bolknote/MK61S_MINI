#include <Arduino.h>
#include "EEPROM.h"
#include "lcd_gui.hpp"
#include "tools.hpp"
#include "program_store.hpp"
#include "mk61emu_core.h"
#include "keyboard.h"
#include "cross_hal.h"
#include "sound_driver.hpp"
#ifdef SPI_FLASH
  #include <SPI.h>
  #include <SPIFlash.h>
#endif
#include "menu.hpp"
#include "config.h"
#include "debug.h"

#include "ledcontrol.h"
using namespace led;

extern void reset_ext_program_state(void);

const  class_LCD_Label  STORE_message(0, 0);
const  class_LCD_Label  STORE_progress_message(0, 1);

const u32 ERASE_SECTOR_TIMEOUT = 5000; // таймаут операции стирания сектора ППЗУ в ms

static constexpr u8 MK61_STORE_REGISTER_F = 0x4F;
static constexpr u8 MK61_LOAD_REGISTER_F  = 0x6F;

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
}

void delay_with_sound_poll(t_time_ms duration_ms) {
  const t_time_ms stop_at = millis() + duration_ms;
  do {
    sound_poll();
    delay(1);
  } while((i32) (millis() - stop_at) < 0);
  sound_poll();
}

void  sound(usize pin, isize freq_Hz, usize duration_ms) {
  sound(pin, freq_Hz, duration_ms, library_mk61::sound_volume());
}

void  sound(usize pin, isize freq_Hz, usize duration_ms, usize volume) {
  sound_driver_play(pin, freq_Hz, duration_ms, volume);
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
  return (flash_is_ok)? flash.readByte(offset + segment_address) : EEPROM.read(offset);
}

bool load_from(isize address) {
  if(load_word(address, OFFSET_FLAG_OCCUPIED) != SLOT_OCCUPIED) {
    dbgln(SPIROM, "SPIFLASH: SLOT IS EMPTY ", address, "Nothing to load! canceled!");
    lcd.print(library_mk61::text(" is empty", " HET"));
    sound(PIN_BUZZER, 4000, 750);
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

  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  u8 code_len = 0;
  if(!program_store::read_mk61(name, &code_page[0], core_61::MAX_PROGRAM_STEP, &code_len)) return false;

  apply_program_memory_auto(&code_page[0], code_len, false);
  const usize program_steps = core_61::program_steps();
  for(usize i = 0; i < program_steps; i++) {
    MK61Emu_SetCode(core_61::get_ring_address(i), code_page[i]);
  }
  return true;
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
    } else {
      EEPROM.update(offset, data);
    }
}

inline bool check_empty_program(void) {
  usize all_to_or = 0;
  const usize program_steps = core_61::program_steps();
  for(usize i=0; i < program_steps; i++) all_to_or |= (usize) core_61::get_code(/*mk61s.*/core_61::get_ring_address(i));
  if(all_to_or == 0) {
    lcd.print(library_mk61::text("No program...", "HET \001PO\005PAMM"));
    sound(PIN_BUZZER, 4000, 750);
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
  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  core_61::get_code_page(&code_page[0]);
  const u8 code_len = (u8) seek_program_END(&code_page[0]);
  if(!program_store::write_mk61(name, &code_page[0], code_len)) return false;

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
    sound(PIN_BUZZER, 4000, 750);
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
  const u8 code_len = (u8) seek_program_END(&code_page[0]);

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
  if(!program_store::write_mk61(name, &code_page[0], code_len)) return false;

  #ifdef SERIAL_OUTPUT
    Serial.println("\nProgramm saved!");
  #endif
  return true;
}              

using namespace action;

bool  EraseFlash(void) {
  sound(PIN_BUZZER, 4000, 750);
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
  sound(PIN_BUZZER, 1000, 300);
  message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
  return action::MENU_EXIT;
}
