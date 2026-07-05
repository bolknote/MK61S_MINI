#include "config.h"

static  class_calc_config   config;

#include <Arduino.h>
#include "rust_types.h"
#include "keyboard.h"

using namespace kbd;

#include <LiquidCrystal.h>
#include "lcd_gui.hpp"
#include "mnemo.hpp"

#include "mk61emu_core.h"

#include "cross_hal.h"
#include "disasm.hpp"
#include "tools.hpp"
#include "menu.hpp"

#include "ledcontrol.h"
using namespace led;

#include "debug.h"

LiquidCrystal lcd(PIN_LCD_RS, PIN_LCD_E, PIN_LCD_DB4, PIN_LCD_DB5, PIN_LCD_DB6, PIN_LCD_DB7);

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

static  u32         update_R_GRD_G;
static  u32         wait_calc_time;

static  bool        YZ_ZT;
static  bool        lcd_hooked;
static  bool        need_draw_lock_message;
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

/* ===================================    Extended ISA variables    ============================================ */
struct {
  u8          code;
  t_time_ms   time;
} ext_command;

enum  ext_run_stop {ENOP=0, WAIT_02, WAIT_05, WAIT_1, WAIT_2, WR_R10, RD_R10, WR_R11, RD_R11};

static  u8  ext61_program[core_61::LAST_PROGRAM_STEP + 1];
//static  u8  ext61_reg[16][8+1+2+1];
static  core_61::bcd_value  ext61_reg[16];

static  constexpr char  XP10[8] = {'x', '-', '>', P_RUS, '1', '0', ' ', 0};
static  constexpr char  PX10[8] = {P_RUS, '-', '>', 'x', '1', '0', ' ', 0};
static  constexpr i32   COUNT_EXT_COMMAND = 7;
const   char* mnemo[COUNT_EXT_COMMAND] = {"empty ", "0.2 sec", "0.5 sec", "1.0 sec", "2.0 sec", XP10, PX10};
/*===============================================================================================================*/

#include  "automate.hpp"

void lcd_std_display_redraw(void) { // Принудительная отрисовка стандартного экрана MK61s_mini
    lcd.clear();
    GRDLabel.print(MK61Emu_GetAngleUnit());
    display_text[0] = (char) -1;
    if(core_61::is_RUN()) {
      lcd.setCursor(0, 0); lcd.print("RUN");
    }
    mk61_display_refresh();
}

void mk61_display_refresh(void) {
  // Обновление дисплея МК61, если изменилась информация на экране
    if(!core_61::update_indicator(&display_text[0], display_symbols)) {
      if(core_61::edit_program) { // калькулятор в режиме редактирования программы МК61 (ПРГ)
        const i32 back_step = core_61::get_IP() - 1;
        for(int i = 0; i < 3; i++) {
          const i32 code = core_61::get_code(core_61::get_ring_address(back_step - i));
          if(code == 0x50 && ext61_program[back_step - i] != 0) { // Есть код расширения режима старт/стоп!
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
  char cvalue[15];
  cvalue[14] = 0;

  lcd.clear();
  if(YZ_ZT) {
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

  #ifdef SERIAL_OUTPUT
    terminal.init();
  #endif
  dbgln(MINI, FIRMWARE_VER);

  #ifdef SPI_FLASH
      init_external_flash();
  #endif

  //  kbd::test();
  kbd::init();
  library_mk61::load_settings_state();
  
  #if defined(REVISION_V2) || defined(REVISION_V3)
    pinMode(PIN_LCD_RW, OUTPUT);
    digitalWrite(PIN_LCD_RW, LOW);
  #endif
  lcd.begin(16, 2);

  glyph.draw(0);
  delay(1000);
  for(int i=1; i < 17; i++) {
    // смещение глифа на 1 колонку вправо
    glyph.draw(i);
    // вывод версии ПО как "бегущей строки" вслед за смещением вправо глифа
    lcd.setCursor(0,0); lcd.print((char*) &FULL_MODEL_NAME[16-i]);
    lcd.setCursor(0,1); lcd.print((char*) &FIRMWARE_VER[16-i]);
    delay(2000/16);
  }
  sound(PIN_BUZZER, 300, 200);
  led::on();
  delay(1500);
  led::off();

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

 // Запуск эмулятора MK61
  GRDLabel.print(load_grade_switch()); // считаем состояние переключателя ГРД отобразим градусную меру

  YZ_ZT = true;
  wait_calc_time = millis() + CALC_WAIT_MS;
  update_R_GRD_G = millis() + ANGLE_SAVE_UPDATE_MS;

 // Настройки режима MAXIMAL  
  mk61_quants_reload  =   1;
  mk61_quants         =   mk61_quants_reload;
  //mk61_edit_program   =   false;

  memset(&ext61_program, 0, sizeof(ext61_program));
  memset(&ext61_reg, 0, sizeof(ext61_reg));
  dbgln(EXT_RUN, "Extended register sizeof = ", sizeof(ext61_reg));

  ext_command.code = 0;
  auto_start_time = 0;

  core_61::enable();

  dbgln(MINI, "ON");
}

//===================================================================
//         Редактирование расширения программы МК61
//===================================================================
void  edit_extend_program(void) { 
  const i32 back_step = core_61::get_IP() - 1;
  if(core_61::get_code(core_61::get_ring_address(back_step)) != 0x50) return;

  i32 ext_code = ext61_program[back_step];
  while(true) {
    lcd.setCursor(0, 0); lcd.print(">          "); lcd.print(mnemo[ext_code]);

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
        update_R_GRD_G = now + ANGLE_SAVE_UPDATE_MS;
      break;
    case KEY_GRADE: 
        MK61Emu_SetAngleUnit(GRADE);
        GRDLabel.print("\x05P\x03");
        update_R_GRD_G = now + ANGLE_SAVE_UPDATE_MS;
      break;
    case KEY_RADIAN:
        MK61Emu_SetAngleUnit(RADIAN);
        GRDLabel.print("P  ");
        update_R_GRD_G = now + ANGLE_SAVE_UPDATE_MS;
      break;
    default:
      if(keycode >= 0) {
        MK61Emu_SetKeyPress(cross_key.x, cross_key.y); // передача нажатия в MK61s
      }
  }
}

inline void monitor_switch_angle_unit(t_time_ms now) {
  const AngleUnit new_angle = MK61Emu_GetAngleUnit();
  const AngleUnit old_angle = read_grade_switch();
  
  if( old_angle != new_angle && now >= update_R_GRD_G) { // Сохраним состояние переключателя градусной меры
    update_R_GRD_G = now + ANGLE_SAVE_UPDATE_MS;
    store_grade_switch(new_angle);
    dbgln(MINI, "store switch from ", old_angle, " to ", new_angle);
  }
}

inline void mk61_process(void) {
  mk61_automate();
  if(core_61::is_displayed()) {
      core_61::clear_displayed();
      if(!lcd_hooked) mk61_display_refresh();
  }
}

inline void message_of_unuse(void) {
  // выдача трех сигналов
  for(int i=0; i<3; i++) {
    sound(PIN_BUZZER, 4000, 200);
    delay(250);
  }
}

// ***********************************************************************************************
// *******************************   ЦИКЛ РАБОТЫ ОС mk61s ****************************************
// ***********************************************************************************************
void   mk61_baseloop_hook(i32 key);
void   mk61_menu_hook(i32 key);

using HookFunc = void (*)(i32 key);
static HookFunc input_focus = &mk61_baseloop_hook;

void   mk61_menu_hook(i32 key) {
    if(key >= 0) {
      const i32 result = mk61_menu.select(kbd::get_key());
      if( result < 0) {
        lcd_std_display_redraw();
        input_focus = &mk61_baseloop_hook;
        dbgln(MENU, "menu quit");
      }
    }
}

void   mk61_baseloop_hook(i32 key) {
  switch(key) {
    case  KEY_USER_RELEASE:
      kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(core_61::edit_program) {
          const isize mk61_IP = core_61::get_IP();
          dbgln(MENU, "release [USER], insert NOP to MK61 program in step ", mk61_IP);
          insert_cmd_in_program(mk61_IP, MK61_NOP);
          //disassembler.enable(); //cache_IP_mk61 = MK61_ip + 1; 
          //lcd_std_display_redraw();
        }
      break;
    case  KEY_ESC_PRESS:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        input_focus = &mk61_menu_hook;
        mk61_menu.select(-1);  // Отобразим меню
      break;
    case  KEY_LOAD:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(Load()) message_and_waitkey(" press any key! ");
        lcd_std_display_redraw(); 
      break;
    case  KEY_SAVE:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(Store()) message_and_waitkey(" press any key! ");
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
  const time_t time_is_now = millis();

  // планируем реакцию на бездействие калькулятора (только для первого входа в процедуру)
  constexpr static time_t DELAY_UNUSED = 1000 * 60 * 5;
  static time_t time_message_of_unuse = time_is_now + DELAY_UNUSED; // 5 Минут повтор события

  #ifdef TERMINAL // Подмена полученной с терминала клавиши через буфер клавиатуры
    const i32 key_from_terminal = terminal.serial_input_handler();
    if(key_from_terminal >= 0) kbd::push((i8) key_from_terminal);
  #endif

  const i32 used_key = kbd::last_key();
  if(used_key >= 0) { 
  //== кнопка нажата - перепланировка выдачи сообщения о бездействии на следующие 5 минут
    time_message_of_unuse = time_is_now + DELAY_UNUSED;
  } else { 
  //== однако если нет нажатий проверим пора ли выдать предупреждение
    if(time_message_of_unuse < time_is_now) { // достигнуто время реакции на бездействие!!!
        time_message_of_unuse = time_is_now + DELAY_UNUSED; // через 5 Минут повтор события
      // в режиме счета по программе выдачи звукового оповещения не производится 
        if(core_61::is_CALC()) message_of_unuse();
    }
  }

  // Перехват клавиатуры программным модулем
  input_focus(used_key);
  kbd::scan();
}

void idle_main_process(void) {
  led::control();
}

void event_hold_key(i32 holded_key, i32 hold_quant) {
  switch(holded_key) {
      case KEY_USER_PRESS: // Удержание USER KEY, вывод стека XYZT на экран
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
          lcd_hooked = false;
          dbgln(MENU, "UNHOLD [USER], quant = ", hold_quant);
          kbd::exclude_before(KEY_USER_PRESS); // уберем все коды отпускания/нажатия клавиш включая нажатие KEY_USER, из очереди клавиатуры
          lcd_std_display_redraw();
        break;
  }
}
