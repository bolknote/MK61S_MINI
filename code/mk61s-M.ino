#include "config.h"

static  class_calc_config   config;

#include <Arduino.h>
#include "rust_types.h"
#include "keyboard.h"

using namespace kbd;

#include "display.hpp"
#include "lcd_gui.hpp"
#include "mnemo.hpp"

#include "mk61emu_core.h"

#include "cross_hal.h"
#include "disasm.hpp"
#include "tools.hpp"
#include "sound_driver.hpp"
#include "menu.hpp"
#include "basic.hpp"
#include "focal.hpp"
#include "tinybasic.hpp"
#include "usb_mass_storage.hpp"

#include "ledcontrol.h"
using namespace led;

#include "debug.h"

MK61Display lcd;

static class_menu           mk61_menu = class_menu((t_punct**) library_mk61::MENU, library_mk61::COUNT_PUNCTS);

const  class_glyph          glyph; //(lcd);
const  class_LCD_Label      MarkLabel(0, 0);
const  class_LCD_Label      XLabel(0, 1);

static  LCD_GRD_Label       GRDLabel;
static  key_mnenonic        MnemoLabel;

static  class_disassm_mk61  disassembler;
static  isize               mk61_quants;
isize                       mk61_quants_reload;

static constexpr t_time_ms  CALC_WAIT_MS           =     10;
static constexpr t_time_ms  ANGLE_SAVE_UPDATE_MS   =   3000;  // Время (мс) для запуска процесса сохранения переключателя угловых единиц Р-ГРД-Г

t_time_ms   runtime_ms; // время работы программы в ms

static  u32         wait_calc_time;
static  DeferredSave angle_save;

static  bool        YZ_ZT;
static  bool        lcd_hooked;
static  bool        need_draw_lock_message;
static  bool        turbo_display_dirty;
static  t_time_ms   turbo_next_lcd_update;
//static  bool        mk61_edit_program;

const char terminal_symbols[16] = {
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', 'L', 'C', '\303', 'E', ' '
};

const char display_symbols[16] = {
    'O', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', 'L', 'C', G_RUS, 'E', ' '
};
                                       //0123456789ABCD
char        display_text[15];          //-12345678.-12

#ifdef SERIAL_OUTPUT
  #include "terminal.hpp"
  static  class_terminal      terminal;
#endif

#ifdef MK61_EXTENDED
  static bool first_key_clean_upline;
#endif

time_t auto_start_time;

void key_press_handler(i32 keycode);

bool usb_start_mass_storage_mode(void) {
  #if defined(SERIAL_OUTPUT) && defined(USBCON) && defined(USBD_USE_CDC)
    Serial.end();
    delay(50);
  #endif

  return usb_mass_storage::init();
}

void usb_start_terminal_mode(void) {
  usb_mass_storage::deinit();
  delay(50);

  #ifdef SERIAL_OUTPUT
    terminal.init();
    dbgln(MINI, FIRMWARE_VER);
  #endif
}

/* ===================================    Extended ISA variables    ============================================ */
struct {
  u8          code;
  t_time_ms   time;
} ext_command;

enum  ext_run_stop {ENOP=0, WAIT_02, WAIT_05, WAIT_1, WAIT_2, WR_R10, RD_R10, WR_R11, RD_R11};

static  u8  ext61_program[core_61::CODE_PAGE_BUFFER_SIZE];
//static  u8  ext61_reg[16][8+1+2+1];
static  core_61::bcd_value  ext61_reg[16];

static  constexpr char  XP10[8] = {'x', '-', '>', P_RUS, '1', '0', ' ', 0};
static  constexpr char  PX10[8] = {P_RUS, '-', '>', 'x', '1', '0', ' ', 0};
static  constexpr i32   COUNT_EXT_COMMAND = 7;
const   char* mnemo[COUNT_EXT_COMMAND] = {"empty ", "0.2 sec", "0.5 sec", "1.0 sec", "2.0 sec", XP10, PX10};
/*===============================================================================================================*/

void reset_ext_program_state(void) {
  memset(&ext61_program, 0, sizeof(ext61_program));
  ext_command.code = 0;
  auto_start_time = 0;
}

#include  "automate.hpp"

void lcd_std_display_redraw(void) { // Принудительная отрисовка стандартного экрана MK61s_mini
    MK61DisplayUpdate update(lcd);
    lcd.clear();
    GRDLabel.print(MK61Emu_GetAngleUnit());
    display_text[0] = (char) -1;
    if(core_61::is_RUN()) {
      lcd.setCursor(0, 0); lcd.print("RUN");
    }
    mk61_display_refresh();
}

void mk61_display_refresh(void) {
  MK61DisplayUpdate update(lcd);
  // Обновление дисплея МК61, если изменилась информация на экране
    if(!core_61::update_indicator(&display_text[0], display_symbols)) {
      if(core_61::edit_program) { // калькулятор в режиме редактирования программы МК61 (ПРГ)
        const i32 back_step = core_61::get_IP() - 1;
        for(int i = 0; i < 3; i++) {
          const i32 program_step = back_step - i;
          if(program_step < 0 || program_step >= (i32) core_61::program_steps()) continue;
          const i32 code = core_61::get_code(core_61::get_ring_address(program_step));
          if(code == 0x50 && ext61_program[program_step] != 0) { // Есть код расширения режима старт/стоп!
            display_text[0 + i*3] = LCD_RT_ARROW_CHAR; 
          }
        }
      }
      XLabel.print(display_text); lcd.write(' ');
      dbgln(MINI, "[mk61_display_refresh] ", display_text);
    }

  // вывод содержимого счетчика команд в режимем CALC, для отладки по ПП
    if(core_61::is_CALC()) { // Режим CALC работа с калькулятором в диалоговом режиме
      disassembler.print();
    }
}

void inline lcd_stack_output(void) {
  MK61DisplayUpdate update(lcd);
  char cvalue[15];
  cvalue[14] = 0;

  lcd.clear();
  if(lcd.rows() >= 4) {
      lcd.setCursor(0,0); lcd.print("T "); lcd.print(read_stack_register(stack::T, cvalue, display_symbols));
      lcd.setCursor(0,1); lcd.print("Z "); lcd.print(read_stack_register(stack::Z, cvalue, display_symbols));
      lcd.setCursor(0,2); lcd.print("Y "); lcd.print(read_stack_register(stack::Y, cvalue, display_symbols));
      lcd.setCursor(0,3); lcd.print("X "); lcd.print(read_stack_register(stack::X, cvalue, display_symbols));
  } else if(YZ_ZT) {
      lcd.setCursor(0,1); lcd.print("Y "); lcd.print(read_stack_register(stack::Y, cvalue, display_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_Y, display_symbols));
      lcd.setCursor(0,0); lcd.print("X1"); lcd.print(read_stack_register(stack::X1, cvalue, terminal_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_Z, display_symbols));
      YZ_ZT = false;  // флаг чередования вывода пар регистров YZ или ZT -> ZT
  } else {
      lcd.setCursor(0,0); lcd.print("T "); lcd.print(read_stack_register(stack::T, cvalue, display_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_T, display_symbols));
      lcd.setCursor(0,1); lcd.print("Z "); lcd.print(read_stack_register(stack::Z, cvalue, display_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_Z, display_symbols));
      YZ_ZT = true;   // флаг чередования вывода пар регистров YZ или ZT -> YZ
  }
  //lcd.print("Z "); lcd.print(read_stack_register(stack::Z, cvalue, display_symbols));
}

void setup() {
  // При входе с зажатой кнопко ESC вызывается DFU-loader
  pinMode(PIN_KBD_COL0, INPUT_PULLDOWN);
  pinMode(PIN_KBD_ROW0, OUTPUT);
  digitalWrite(PIN_KBD_ROW0, HIGH);

  if(digitalRead(PIN_KBD_COL0) != LOW) {
    dbgln(MINI, "BOOT pressed! Need load program from DFU!");
    DFU_enable();
  } else {
    dbgln(MINI, "ESC unpressed!");
  }

  led::init();
  sound_driver_init(PIN_BUZZER);

  #ifdef SPI_FLASH
      init_external_flash();
  #endif

  library_mk61::load_settings_state();

  usb_start_terminal_mode();

  //  kbd::test();
  kbd::init();
  
  #if defined(MK61_DISPLAY_LCD1602) && (defined(REVISION_V2) || defined(REVISION_V3))
    pinMode(PIN_LCD_RW, OUTPUT);
    digitalWrite(PIN_LCD_RW, LOW);
  #endif
  lcd.begin(lcd_display::COLS, library_mk61::display_rows());
  lcd.setTextProfile(library_mk61::display_text_profile());

  glyph.draw(0);
  delay(1000);
  for(int i=1; i < 17; i++) {
    {
      MK61DisplayUpdate update(lcd);
      // смещение глифа на 1 колонку вправо
      glyph.draw(i);
      // вывод версии ПО как "бегущей строки" вслед за смещением вправо глифа
      lcd.setCursor(0,0); lcd.print((char*) &FULL_MODEL_NAME[16-i]);
      lcd.setCursor(0,1); lcd.print((char*) &FIRMWARE_VER[16-i]);
    }
    delay(2000/16);
  }
 //---  Настройка отрисовки экрана
  lcd_hooked = false;               // экран не перeхвачен
  need_draw_lock_message = true;    // флаг уже отрисованного сообщения блокировки ядра

  #ifdef MK61_EXTENDED
    first_key_clean_upline = false;
  #endif

  const class_LCD_fonts lcd_fonts;
  lcd_fonts.load();
  lcd.clear();

 // Система ззагрузки программ
  init_library();
#if MK61_ENABLE_BASIC
  InitBasic();
#endif
#if MK61_ENABLE_FOCAL
  InitFocal();
#endif
#if MK61_ENABLE_TINYBASIC
  InitTinyBasic();
#endif

 // Запуск эмулятора MK61
  GRDLabel.print(load_grade_switch()); // считаем состояние переключателя ГРД отобразим градусную меру

  YZ_ZT = true;
  wait_calc_time = millis() + CALC_WAIT_MS;
  angle_save.schedule(millis(), ANGLE_SAVE_UPDATE_MS);

 // Настройки режима MAXIMAL  
  mk61_quants_reload  =   1;
  mk61_quants         =   mk61_quants_reload;
  //mk61_edit_program   =   false;

  reset_ext_program_state();
  memset(&ext61_reg, 0, sizeof(ext61_reg));
  dbgln(EXT_RUN, "Extended register sizeof = ", sizeof(ext61_reg));

  core_61::enable();
  sound_startup();
  sound_poll();

  dbgln(MINI, "ON");
}

//===================================================================
//         Редактирование расширения программы МК61
//===================================================================
void  edit_extend_program(void) { 
  const i32 back_step = core_61::get_IP() - 1;
  if(back_step < 0 || back_step >= (i32) core_61::program_steps()) return;
  if(core_61::get_code(core_61::get_ring_address(back_step)) != 0x50) return;

  i32 ext_code = ext61_program[back_step];
  while(true) {
    {
      MK61DisplayUpdate update(lcd);
      lcd.setCursor(0, 0); lcd.print(">          "); lcd.print(mnemo[ext_code]);
    }

    const i32 last_key_code = kbd::get_key_wait();
    if(last_key_code == KEY_ESC) break;
    if(last_key_code == KEY_OK) {
      ext61_program[back_step] = ext_code;
      break;
    }
    switch(last_key_code) {
      case  KEY_LEFT:
          if(ext_code > 0) ext_code--;
        break;
      case  KEY_RIGHT:
          if(ext_code < (COUNT_EXT_COMMAND - 1)) ext_code++;
        break;
    }
  }

  lcd_std_display_redraw();
}

void  entry_programm_mode(void) { // Вход в режим ПРГ - событие генерируется key_mnemonics
  core_61::edit_program = true;
  dbgln(MINI, "AVT -> PRG");
  disassembler.enable();
}

void exit_auto_mode(void) { // Выход из режима ПРГ - событие генерируется key_mnemonics
  core_61::edit_program = false;
  dbgln(MINI, "AVT -> PRG");
  if(!config.disassm) disassembler.disable(); // Если в конфиге не включен "ВСЕГДА"
}

void key_press_handler(i32 keycode) {
  if(keycode == KEY_USER_PRESS && !core_61::edit_program) return;

  const TMK61_cross_key cross_key = KeyPairs[keycode];  // трансляция кода клавиши в координаты клавиши mk61

  dbg(KBD, "x,y = ", cross_key.x, ",", cross_key.y); dbghex(KBD, " scancode $", keycode); dbgln(KBD, " -> mk61")

  //keyboard.reset_scan_line();  // Для ускорения опроса клавиатуры - переход к первой линии сканирования
  
  MnemoLabel.print(keycode);

  const u32 now = millis();
  #ifdef MK61_EXTENDED
    first_key_clean_upline = false; // снимем флажок первого нажатия
  #endif
  switch(keycode) {
    case KEY_DEGREE:
        MK61Emu_SetAngleUnit(DEGREE);
        GRDLabel.print("  \x05");
        angle_save.schedule(now, ANGLE_SAVE_UPDATE_MS);
      break;
    case KEY_GRADE: 
        MK61Emu_SetAngleUnit(GRADE);
        GRDLabel.print("\x05P\x03");
        angle_save.schedule(now, ANGLE_SAVE_UPDATE_MS);
      break;
    case KEY_RADIAN:
        MK61Emu_SetAngleUnit(RADIAN);
        GRDLabel.print("P  ");
        angle_save.schedule(now, ANGLE_SAVE_UPDATE_MS);
      break;
    default:
      if(keycode >= 0) {
        MK61Emu_SetKeyPress(cross_key.x, cross_key.y); // передача нажатия в MK61s
      }
  }
}

inline void monitor_switch_angle_unit(t_time_ms now) {
  if(!angle_save.due(now)) return;
  angle_save.clear();

  const AngleUnit new_angle = MK61Emu_GetAngleUnit();
  const AngleUnit old_angle = read_stored_grade_switch();
  
  if(old_angle != new_angle) { // Сохраним состояние переключателя градусной меры
    store_grade_switch(new_angle);
    dbgln(MINI, "store switch from ", old_angle, " to ", new_angle);
  }
}

inline void mk61_process(void) {
  mk61_automate();
  if(core_61::is_displayed()) {
      core_61::clear_displayed();
      turbo_display_dirty = true;
  }

  if(!turbo_display_dirty) return;
  if(core_61::is_RUN() && library_mk61::speed_is_turbo()) {
      const t_time_ms now = millis();
      if(now < turbo_next_lcd_update) return;
      turbo_next_lcd_update = now + cfg::TURBO_LCD_UPDATE_MS;
  }

  turbo_display_dirty = false;
  if(!lcd_hooked) mk61_display_refresh();
}

inline void message_of_unuse(void) {
  // выдача трех сигналов
  for(int i=0; i<3; i++) {
    sound(PIN_BUZZER, 4000, 200, library_mk61::sound_volume());
    delay_with_sound_poll(250);
  }
}

// ***********************************************************************************************
// *******************************   ЦИКЛ РАБОТЫ ОС mk61s ****************************************
// ***********************************************************************************************
void   mk61_baseloop_hook(i32 key);
void   mk61_menu_hook(i32 key);

using HookFunc = void (*)(i32 key);
static HookFunc input_focus = &mk61_baseloop_hook;
static bool user_short_press_pending = false;
static bool drop_menu_exit_key_events = false;
static u8 drop_menu_exit_scan_count = 0;

static void drop_pending_key_events(void) {
  while(kbd::get_key() >= 0) {}
  kbd::clear_hold_key();
}

static void leave_menu_mode(void) {
  drop_pending_key_events();
  user_short_press_pending = false;
  drop_menu_exit_key_events = true;
  drop_menu_exit_scan_count = 0;
  lcd_std_display_redraw();
  input_focus = &mk61_baseloop_hook;
}

void   mk61_menu_hook(i32 key) {
    if(key >= 0) {
      #if MK61_USER_GAMES_MENU_SHORTCUT
      if(key == KEY_USER_PRESS) {
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        lcd_ru::restore_default_font();
        if(mk61_games_select() == action::MENU_EXIT) {
          leave_menu_mode();
          dbgln(MENU, "menu quit");
        } else {
          mk61_menu.select(-1);
        }
        return;
      }
      #endif

      const i32 result = mk61_menu.select(kbd::get_key());
      if( result < 0) {
        leave_menu_mode();
        dbgln(MENU, "menu quit");
      }
    }
}

void   mk61_baseloop_hook(i32 key) {
  #if MK61_USER_GAMES_MENU_SHORTCUT
  if(key == KEY_USER_PRESS && !core_61::edit_program) {
    kbd::get_key(); // сервисная клавиша, не передаем ее в автомат МК-61
    user_short_press_pending = true;
    return;
  }
  #endif

  switch(key) {
    case  KEY_USER_RELEASE:
      kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(core_61::edit_program) {
          const isize mk61_IP = core_61::get_IP();
          dbgln(MENU, "release [USER], insert NOP to MK61 program in step ", mk61_IP);
          insert_cmd_in_program(mk61_IP, MK61_NOP);
          //disassembler.enable(); //cache_IP_mk61 = MK61_ip + 1; 
          //lcd_std_display_redraw();
        #if MK61_USER_GAMES_MENU_SHORTCUT
        } else if(user_short_press_pending) {
          user_short_press_pending = false;
          mk61_games_select();
          lcd_std_display_redraw();
        #endif
        }
      break;
    case  KEY_ESC_PRESS:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        input_focus = &mk61_menu_hook;
        mk61_menu.select(-1);  // Отобразим меню
      break;
    case  KEY_LOAD:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(Load()) message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
        lcd_std_display_redraw(); 
      break;
    case  KEY_SAVE:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(Store()) message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
        lcd_std_display_redraw(); 
      break;
    case  KEY_RUN_PRESS:
        if(auto_start_time != 0) { // Прерываем автостарт с расширенным кодом команды
          kbd::get_key(); // очистим буфер клавиатуры от этого кода
          auto_start_time = 0;
          return_auto_mode();
        }
      /*!!!без брейка так задумано!!!!*/
    default:
      if(core_61::is_CALC()) { // Режим автоматической работы CALC без задержки!
        const u32 now = millis();
        monitor_switch_angle_unit(now); // слежение за положением b сохранением в flash переключателя градусной меры (только в АВТ режиме)

        if(ext_command.code != 0) { // Запуск расширенной программы МК-61s, после выполненого С/П
          dbgln(EXT_RUN, "AUTO START ENABLE! Extended code = ", ext_command.code);
          auto_start_time = ext_command.time;
          switch(ext_command.code) {
            case  ext_run_stop::WAIT_02:
                auto_start_time += 200;
              break;
            case  ext_run_stop::WAIT_05:
                auto_start_time += 500;
              break;
            case  ext_run_stop::WAIT_1:
                auto_start_time += 1000;
              break;
            case  ext_run_stop::WAIT_2:
                auto_start_time += 2000;
              break;
            case  ext_run_stop::WR_R10: // write X to R10
                auto_start_time += 100;
                core_61::get_stack_register(stack::X, ext61_reg[0]);
              break;
            case  ext_run_stop::RD_R10: // read R10 to X
                auto_start_time += 100;
                core_61::set_stack_register(stack::X, &ext61_reg[0]);
              break;
          }

          //while(millis() < start_time);
          //kbd::push((i8) 30); // Повторный пуск С/П

          ext_command.code = 0;
        }

        if(auto_start_time != 0 && now > auto_start_time) { // Автостарт если он включен по времени auto_start_time
           kbd::push((i8) KEY_RUN_PRESS); // Повторный пуск С/П
           auto_start_time = 0;
           dbgln(EXT_RUN, "START program by time (auto start)...");
        }

        mk61_process();
      } else {        // Режим работы по программе (СЧЕТ) задержка устанавливается в меню Speed CLASSIC/MAXIMAL
        if(--mk61_quants == 0) {
          mk61_process();
          mk61_quants = mk61_quants_reload;
        }
      }
  }
}

void  loop() {
  idle_main_process();

  const time_t time_is_now = millis();
  const bool turbo_run = core_61::is_RUN() && library_mk61::speed_is_turbo();

  // планируем реакцию на бездействие калькулятора (только для первого входа в процедуру)
  constexpr static time_t DELAY_UNUSED = 1000 * 60 * 5;
  static time_t time_message_of_unuse = time_is_now + DELAY_UNUSED; // 5 Минут повтор события

  #ifdef TERMINAL // Подмена полученной с терминала клавиши через буфер клавиатуры
    static u8 turbo_serial_poll_divider;
    bool terminal_poll_enabled = true;
    if(turbo_run) {
      terminal_poll_enabled = (turbo_serial_poll_divider == 0);
      turbo_serial_poll_divider++;
      if(turbo_serial_poll_divider >= cfg::TURBO_SERIAL_POLL_LOOPS) turbo_serial_poll_divider = 0;
    } else {
      turbo_serial_poll_divider = 0;
    }

    if(terminal_poll_enabled && !usb_mass_storage::active()) {
      const i32 key_from_terminal = terminal.serial_input_handler();
      if(key_from_terminal >= 0) kbd::push((i8) key_from_terminal);
    }
  #endif

  const i32 used_key = kbd::last_key();
  if(drop_menu_exit_key_events) {
    drop_pending_key_events();
    kbd::scan();
    if(drop_menu_exit_scan_count < 8) drop_menu_exit_scan_count++;
    drop_pending_key_events();
    if(drop_menu_exit_scan_count >= 8 && !kbd::any_key_pressed() && kbd::last_key() < 0) {
      drop_menu_exit_key_events = false;
    }
    return;
  }

  if(used_key >= 0) { 
  //== кнопка нажата - перепланировка выдачи сообщения о бездействии на следующие 5 минут
    time_message_of_unuse = time_is_now + DELAY_UNUSED;
    library_mk61::defer_settings_state_save();
  } else { 
    if(input_focus == &mk61_baseloop_hook) library_mk61::poll_settings_state_save();
  //== однако если нет нажатий проверим пора ли выдать предупреждение
    if(time_message_of_unuse < time_is_now) { // достигнуто время реакции на бездействие!!!
        time_message_of_unuse = time_is_now + DELAY_UNUSED; // через 5 Минут повтор события
      // в режиме счета по программе выдачи звукового оповещения не производится 
        if(core_61::is_CALC() && library_mk61::idle_signal_is_on()) message_of_unuse();
    }
  }

  // Перехват клавиатуры программным модулем
  input_focus(used_key);
  kbd::scan();
}

void idle_main_process(void) {
  sound_poll();
  led::control();
  lcd.flush();
}

void event_hold_key(i32 holded_key, i32 hold_quant) {
  switch(holded_key) {
      case KEY_USER_PRESS: // Удержание USER KEY, вывод стека XYZT на экран
          #if MK61_USER_GAMES_MENU_SHORTCUT
          user_short_press_pending = false;
          #endif
          lcd_hooked = true;  // перехват экрана
          dbgln(MENU, "HOLD [USER], quant = ", hold_quant);
          lcd_stack_output();
        break;
      default:
        kbd::clear_hold_key();
  }
}

void event_unhold_key(i32 unholded_key, i32 hold_quant) {
  switch(unholded_key) {
      case KEY_USER_PRESS:
          #if MK61_USER_GAMES_MENU_SHORTCUT
          user_short_press_pending = false;
          #endif
          lcd_hooked = false;
          dbgln(MENU, "UNHOLD [USER], quant = ", hold_quant);
          kbd::exclude_before(KEY_USER_PRESS); // уберем все коды отпускания/нажатия клавиш включая нажатие KEY_USER, из очереди клавиатуры
          lcd_std_display_redraw();
        break;
  }
}
