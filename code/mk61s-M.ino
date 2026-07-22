#include "config.h"

class_calc_config config;

#include <Arduino.h>
#include "rust_types.h"
#include "keyboard.h"
#include "m61_text.hpp"

using namespace kbd;

#include "display.hpp"
#include "manual_lifetime.hpp"
#include "lcd_gui.hpp"
#include "mnemo.hpp"
#include "startup_splash.hpp"
#include "entropy_pool.hpp"

#include "mk61emu_core.h"

#include "cross_hal.h"
#include "disasm.hpp"
#include "tools.hpp"
#include "runtime_safety.hpp"
#include "rtc_clock.hpp"
#include "rtc_idle_clock.hpp"
#include "sound_driver.hpp"
#include "menu.hpp"
#include "development.hpp"
#include "focal.hpp"
#include "tinybasic.hpp"
#include "usb_mass_storage.hpp"
#include "usb_screen.hpp"

#include "ledcontrol.h"
using namespace led;

#include "debug.h"

// Аппаратно-зависимый конструктор запускается ниже, после входа в setup().
static manual_lifetime::Storage<MK61Display> mk61_lcd_storage;
MK61Display* main_lcd_pointer;

static class_menu mk61_menu((t_punct**) library_mk61::MENU,
                            library_mk61::MAIN_MENU_COUNT);

const  class_LCD_Label      MarkLabel(0, 0);
const  class_LCD_Label      XLabel(0, 1);

static  LCD_GRD_Label       GRDLabel;
static  key_mnenonic        MnemoLabel;

class_disassm_mk61 disassembler;
static  isize               mk61_quants;
isize                       mk61_quants_reload;

static constexpr t_time_ms  ANGLE_SAVE_UPDATE_MS   =   3000;  // Время (мс) для запуска процесса сохранения переключателя угловых единиц Р-ГРД-Г
static constexpr t_time_ms  IDLE_SIGNAL_DELAY_MS   = 300000;  // 5 минут до сигнала бездействия

t_time_ms   runtime_ms; // время работы программы в ms

static  t_time_ms   idle_signal_at;
static  DeferredSave angle_save;

static  bool        YZ_ZT;
static  bool        lcd_hooked;
static  bool        need_draw_lock_message;
static  bool        turbo_display_dirty;
static  t_time_ms   turbo_next_lcd_update;
//static  bool        mk61_edit_program;

extern const char terminal_symbols[16] = {
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

static runtime_safety::Deadline auto_start;

void key_press_handler(i32 keycode);
void idle_signal_reset(void);
void idle_signal_poll(void);

static void mix_rtc_startup_snapshot(u8 snapshot_index) {
  rtc_clock::StartupSnapshot snapshot = {};
  if(!rtc_clock::startup_snapshot(snapshot)) return;
  entropy_pool::note_rtc_snapshot(
    snapshot_index,
    rtc_clock::startup_calendar_material(snapshot),
    rtc_clock::startup_phase_material(snapshot));
}

bool usb_start_mass_storage_mode(void) {
  usb_screen::cancel();
  #if defined(SERIAL_OUTPUT) && defined(USBCON) && defined(USBD_USE_CDC)
    Serial.end();
    delay(50);
  #endif

  if(!program_store_suspend_font_for_usb()) return false;
  return usb_mass_storage::init();
}

bool usb_start_terminal_mode(void) {
  const bool clean_exit = usb_mass_storage::deinit();
  program_store_restore_font_after_usb();
  delay(50);

  #ifdef SERIAL_OUTPUT
    terminal.init();
    dbgln(MINI, FIRMWARE_VER);
  #endif
  return clean_exit;
}

/* =============================    Переменные расширенного набора команд    ================================== */
struct {
  u8          code;
  t_time_ms   time;
} ext_command;

enum  ext_run_stop {ENOP=0, WAIT_02, WAIT_05, WAIT_1, WAIT_2, WR_R10, RD_R10};

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
  auto_start.clear();
}

#include  "automate.hpp"

void lcd_std_display_redraw(void) { // Принудительная отрисовка стандартного экрана MK61s_mini
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    GRDLabel.print(MK61Emu_GetAngleUnit());
    display_text[0] = (char) -1;
    if(core_61::is_RUN()) {
      main_lcd().setCursor(0, 0); main_lcd().print("RUN");
    }
    mk61_display_refresh();
}

void mk61_display_refresh(void) {
  MK61DisplayUpdate update(main_lcd());
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
      XLabel.print(display_text); main_lcd().write(' ');
      dbgln(MINI, "[mk61_display_refresh] ", display_text);
    }

  // вывод содержимого счетчика команд в режимем CALC, для отладки по ПП
    if(core_61::is_CALC()) { // Режим CALC работа с калькулятором в диалоговом режиме
      disassembler.print();
    }
}

void inline lcd_stack_output(void) {
  MK61DisplayUpdate update(main_lcd());
  char cvalue[15];
  cvalue[14] = 0;

  main_lcd().clear();
  if(main_lcd().rows() >= 4) {
      main_lcd().setCursor(0,0); main_lcd().print("T "); main_lcd().print(read_stack_register(stack::T, cvalue, display_symbols));
      main_lcd().setCursor(0,1); main_lcd().print("Z "); main_lcd().print(read_stack_register(stack::Z, cvalue, display_symbols));
      main_lcd().setCursor(0,2); main_lcd().print("Y "); main_lcd().print(read_stack_register(stack::Y, cvalue, display_symbols));
      main_lcd().setCursor(0,3); main_lcd().print("X "); main_lcd().print(read_stack_register(stack::X, cvalue, display_symbols));
  } else if(YZ_ZT) {
      main_lcd().setCursor(0,1); main_lcd().print("Y "); main_lcd().print(read_stack_register(stack::Y, cvalue, display_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_Y, display_symbols));
      main_lcd().setCursor(0,0); main_lcd().print("X1"); main_lcd().print(read_stack_register(stack::X1, cvalue, terminal_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_Z, display_symbols));
      YZ_ZT = false;  // флаг чередования вывода пар регистров YZ или ZT -> ZT
  } else {
      main_lcd().setCursor(0,0); main_lcd().print("T "); main_lcd().print(read_stack_register(stack::T, cvalue, display_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_T, display_symbols));
      main_lcd().setCursor(0,1); main_lcd().print("Z "); main_lcd().print(read_stack_register(stack::Z, cvalue, display_symbols));
        //MK61Emu_GetStackStr(StackRegister::REG_Z, display_symbols));
      YZ_ZT = true;   // флаг чередования вывода пар регистров YZ или ZT -> YZ
  }
  //main_lcd().print("Z "); main_lcd().print(read_stack_register(stack::Z, cvalue, display_symbols));
}

void setup() {
  // При входе с зажатой кнопкой ESC вызывается DFU-загрузчик
  pinMode(PIN_KBD_COL0, INPUT_PULLDOWN);
  pinMode(PIN_KBD_ROW0, OUTPUT);
  digitalWrite(PIN_KBD_ROW0, HIGH);

  const bool dfu_requested = digitalRead(PIN_KBD_COL0) != LOW;

  // В mini V2 линия PC15 используется как DB7 ЖКИ. Сохранённый после сброса
  // LSE необходимо отключить до конструктора LiquidCrystal: он начинает
  // обращаться к выводам и посылать команды уже внутри конструктора.
  rtc_clock::prepare_display_gpio();
  #if defined(MK61_DISPLAY_LCD1602) && (defined(REVISION_V2) || defined(REVISION_V3))
    pinMode(PIN_LCD_RW, OUTPUT);
    digitalWrite(PIN_LCD_RW, LOW);
  #endif
  #if defined(MK61_DISPLAY_LCD1602) && defined(REVISION_V2)
    pinMode(PIN_LCD_DB7, OUTPUT);
    digitalWrite(PIN_LCD_DB7, LOW);
  #endif

  // Дисплей нужен и для короткого сообщения DFU, но создаётся только после
  // проверки ESC. Остальная периферия в DFU-ветке вообще не конструируется.
  main_lcd_pointer = &mk61_lcd_storage.construct();
  main_lcd().begin(lcd_display::COLS, lcd_display::DEFAULT_ROWS);

  if(dfu_requested) {
    DFU_enable();
    return;
  }

  // Эти конструкторы обращаются к Arduino/STM32 объектам или периферийным
  // описателям. Запускаем их только для обычной загрузки и после premain.
  sound_driver_construct();
  #ifdef SPI_FLASH
    construct_external_flash();
  #endif

  led::init();
  sound_driver_init(PIN_BUZZER);

  // Запускаем CDC до обнаружения внешней флеш-памяти. Раньше DEBUG_SPIFLASH
  // начинал вывод только после program_store::init(), поэтому медленная или
  // неудачная проверка ёмкости выглядела как зависшая плата, а её диагностика
  // так и не доходила до хоста. В DFU-ветке CDC приложения не запускается:
  // она уже завершилась переходом в системный загрузчик выше.
  usb_start_terminal_mode();
  dbgln(MINI, "ESC unpressed!");

  #ifdef SPI_FLASH
      init_external_flash();
  #endif

  library_mk61::load_settings_state();

  rtc_clock::init();

  //  kbd::test();
  kbd::init();

  dbgln(SPIROM, "LCD init: ready");
  main_lcd().setTextProfile(library_mk61::display_text_profile());

  entropy_pool::begin();
  mix_rtc_startup_snapshot(0);

  // Обычная заставка показывается только при штатной загрузке. DFU-ветка выше
  // выводит собственное короткое сообщение и сразу передаёт управление
  // системному загрузчику.
  static_assert(lcd_display::COLS == startup_splash::COLS, "Splash width must match display width");
  #if defined(MK61_DISPLAY_LCD1602)
    static_assert(lcd_display::ROWS == startup_splash::ROWS, "Splash height must match LCD height");
  #else
    static_assert(startup_splash::ROWS <= lcd_display::MIN_ROWS, "Splash must fit every graphics text profile");
  #endif
  static_assert(sizeof(FULL_MODEL_NAME) == startup_splash::COLS + 1, "Model name must fill one display row");
  static_assert(sizeof(FIRMWARE_VER) == startup_splash::COLS + 1, "Firmware version must fill one display row");
  startup_splash::show(main_lcd(), FULL_MODEL_NAME, FIRMWARE_VER,
                       startup_splash::EscapePolicy::ALLOW_SKIP);

  entropy_pool::finish_startup();
  mix_rtc_startup_snapshot(1);

 //---  Настройка отрисовки экрана
  lcd_hooked = false;               // экран не перeхвачен
  need_draw_lock_message = true;    // флаг уже отрисованного сообщения блокировки ядра

  #ifdef MK61_EXTENDED
    first_key_clean_upline = false;
  #endif

  const class_LCD_fonts lcd_fonts;
  lcd_fonts.load();
  main_lcd().clear();

 // Система ззагрузки программ
  init_library();
#if MK61_ENABLE_FOCAL
  InitFocal();
#endif
#if MK61_ENABLE_TINYBASIC
  InitTinyBasic();
#endif

 // Запуск эмулятора MK61
  GRDLabel.print(load_grade_switch()); // считаем состояние переключателя ГРД отобразим градусную меру

  YZ_ZT = true;
  angle_save.schedule(millis(), ANGLE_SAVE_UPDATE_MS);

 // Настройки режима MAXIMAL  
  mk61_quants_reload  =   1;
  mk61_quants         =   mk61_quants_reload;
  //mk61_edit_program   =   false;

  reset_ext_program_state();
  memset(&ext61_reg, 0, sizeof(ext61_reg));
  dbgln(EXT_RUN, "Extended register sizeof = ", sizeof(ext61_reg));

  core_61::enable();
  entropy_pool::configure_calculator(library_mk61::random_mode_is_mk61s());
  sound_startup();
  sound_poll();
  idle_signal_reset();

  // При загрузке инициализация хранилища может использовать индикатор дисковой
  // активности после заставки. Освобождаем индикатор здесь, когда готовы все
  // подсистемы запуска.
  led::blink_stop();

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
  if(!runtime_safety::valid_index(ext_code, COUNT_EXT_COMMAND)) ext_code = ENOP;
  while(true) {
    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(0, 0); main_lcd().print(">          "); main_lcd().print(mnemo[ext_code]);
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
  if(!runtime_safety::valid_index(keycode, keyboard_core::KEY_COUNT)) return;
  if(keycode == KEY_USER_PRESS && !core_61::edit_program) return;

  const TMK61_cross_key cross_key = KeyPairs[keycode];  // трансляция кода клавиши в координаты клавиши mk61

  dbg(KBD, "x,y = ", cross_key.x, ",", cross_key.y); dbghex(KBD, " scancode $", keycode); dbgln(KBD, " -> mk61");

  //keyboard.reset_scan_line();  // Для ускорения опроса клавиатуры - переход к первой линии сканирования
  
  MnemoLabel.print(keycode);

  const u32 now = millis();
  #ifdef MK61_EXTENDED
    first_key_clean_upline = false; // снимем флажок первого нажатия
  #endif
  switch(keycode) {
    case KEY_DEGREE:
      MK61Emu_SetAngleUnit(DEGREE);
      GRDLabel.print(DEGREE);
      angle_save.schedule(now, ANGLE_SAVE_UPDATE_MS);
      break;
    case KEY_GRADE:
      MK61Emu_SetAngleUnit(GRADE);
      GRDLabel.print(GRADE);
      angle_save.schedule(now, ANGLE_SAVE_UPDATE_MS);
      break;
    case KEY_RADIAN:
      MK61Emu_SetAngleUnit(RADIAN);
      GRDLabel.print(RADIAN);
      angle_save.schedule(now, ANGLE_SAVE_UPDATE_MS);
      break;
    default:
      if(cross_key.as_u16() != NON.as_u16()) {
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
      if(!runtime_safety::time_reached(now, turbo_next_lcd_update)) return;
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

void idle_signal_reset(void) {
  idle_signal_at = millis() + IDLE_SIGNAL_DELAY_MS;
}

void idle_signal_poll(void) {
  const t_time_ms now = millis();
  if(idle_signal_at == 0) {
    idle_signal_at = now + IDLE_SIGNAL_DELAY_MS;
    return;
  }
  if(!runtime_safety::time_reached(now, idle_signal_at)) return;

  idle_signal_at = now + IDLE_SIGNAL_DELAY_MS;
  // в режиме счета по программе выдачи звукового оповещения не производится
  if(core_61::is_CALC() && library_mk61::idle_signal_is_on()) message_of_unuse();
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
      #if MK61_USER_EXPLORER_SHORTCUT
      if(key == KEY_USER_PRESS) {
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        lcd_ru::restore_default_font();
        if(program_store_explorer_select() == action::MENU_EXIT) {
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
  #if MK61_USER_EXPLORER_SHORTCUT
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
        #if MK61_USER_EXPLORER_SHORTCUT
        } else if(user_short_press_pending) {
          user_short_press_pending = false;
          program_store_explorer_select();
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
        if(Load() && !m61_text::active()) message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
        lcd_std_display_redraw(); 
      break;
    case  KEY_SAVE:
        kbd::get_key(); // очистим буфер клавиатуры от этого кода
        if(Store()) message_and_waitkey(library_mk61::text(" press any key! ", "   OK/KEY     "));
        lcd_std_display_redraw(); 
      break;
    case  KEY_RUN_PRESS:
        if(auto_start.pending()) { // Прерываем автостарт с расширенным кодом команды
          kbd::get_key(); // очистим буфер клавиатуры от этого кода
          auto_start.clear();
          return_auto_mode();
        }
      /*!!!без брейка так задумано!!!!*/
      [[fallthrough]];
    default:
      if(core_61::is_CALC()) { // Режим автоматической работы CALC без задержки!
        const u32 now = millis();
        monitor_switch_angle_unit(now); // Слежение за положением и сохранение во флеш-памяти переключателя градусной меры (только в режиме АВТ)

        if(ext_command.code != 0) { // Запуск расширенной программы МК-61s, после выполненого С/П
          const u8 command_code = ext_command.code;
          ext_command.code = 0;
          t_time_ms delay_ms = 0;

          if(!runtime_safety::valid_extended_command(command_code, COUNT_EXT_COMMAND) ||
             !runtime_safety::extended_command_delay(command_code, delay_ms)) {
            dbgln(EXT_RUN, "Rejected extended code = ", command_code);
            return_auto_mode();
          } else {
            dbgln(EXT_RUN, "AUTO START ENABLE! Extended code = ", command_code);
            switch(command_code) {
            case  ext_run_stop::WAIT_02:
            case  ext_run_stop::WAIT_05:
            case  ext_run_stop::WAIT_1:
            case  ext_run_stop::WAIT_2:
              break;
            case  ext_run_stop::WR_R10: // Записать X в R10
                core_61::get_stack_register(stack::X, ext61_reg[0]);
              break;
            case  ext_run_stop::RD_R10: // Прочитать R10 в X
                core_61::set_stack_register(stack::X, &ext61_reg[0]);
              break;
            default:
              break;
            }
            auto_start.schedule(ext_command.time, delay_ms);
          }
        }

        if(auto_start.due(now) && kbd::push((i8) KEY_RUN_PRESS)) { // Повторный пуск С/П
           auto_start.clear();
           dbgln(EXT_RUN, "START program by time (auto start)...");
        }

        mk61_process();
      } else {        // Режим работы по программе (СЧЕТ) задержка устанавливается в меню Speed CLASSIC/MAXIMAL
        if(mk61_quants <= 1) {
          mk61_process();
          mk61_quants = runtime_safety::positive_quantum(mk61_quants_reload);
        } else {
          mk61_quants--;
        }
      }
  }
}

#ifdef TERMINAL
static bool terminal_poll_due(void) {
  static u8 turbo_serial_poll_divider;
  const bool turbo_run = core_61::is_RUN() && library_mk61::speed_is_turbo();
  if(!turbo_run) {
    turbo_serial_poll_divider = 0;
    return true;
  }
  const bool due = turbo_serial_poll_divider == 0;
  turbo_serial_poll_divider++;
  if(turbo_serial_poll_divider >= cfg::TURBO_SERIAL_POLL_LOOPS) {
    turbo_serial_poll_divider = 0;
  }
  return due;
}

// Terminal input is serviced from idle_main_process(), not only from the
// top-level loop.  This lets the desktop client start USB Screen while a
// blocking foreground editor owns the display, and keeps terminal-backed
// `kbd` commands working after attachment.  One complete command is handled
// per idle iteration.
static void service_terminal(void) {
  static bool in_progress;
  if(in_progress || usb_mass_storage::active() || usb_screen::wireBusy() ||
     !terminal_poll_due()) return;

  in_progress = true;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen::active()) {
    u8 terminal_byte = 0;
    while(usb_screen::takeTerminalByte(terminal_byte)) {
      const class_terminal::InputResult result =
        terminal.input_handler(terminal_byte);
      if(result.key >= 0) kbd::push((i8) result.key);
      if(result.line_complete) break;
    }
  } else
#endif
  {
    const i32 key_from_terminal = terminal.serial_input_handler();
    if(key_from_terminal >= 0) kbd::push((i8) key_from_terminal);
  }
  in_progress = false;
}
#endif

void  loop() {
  static u32 top_level_display_mode_revision =
    main_lcd().displayModeRevision();
  idle_main_process();
  const u32 next_display_mode_revision = main_lcd().displayModeRevision();
  if(next_display_mode_revision != top_level_display_mode_revision) {
    top_level_display_mode_revision = next_display_mode_revision;
    // A stateful menu can also span top-level loop calls, so redraw the
    // calculator only when its base hook truly owns the foreground.
    if(input_focus == &mk61_baseloop_hook && !lcd_hooked &&
       !m61_text::active() && !user_short_press_pending) {
      lcd_std_display_redraw();
    }
  }

  // A binary USB Screen packet may span several CDC writes. Serial-producing
  // services pause between its chunks, while calculator/key processing keeps
  // running. Terminal text is emitted only between complete framed packets.
  const bool usb_screen_wire_busy = usb_screen::wireBusy();

  if(!usb_screen_wire_busy) m61_text::service();

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
    rtc_idle_clock::hide(main_lcd());
    idle_signal_reset();
    library_mk61::defer_settings_state_save();
  } else { 
    if(input_focus == &mk61_baseloop_hook) library_mk61::poll_settings_state_save();
  }

  // Перехват клавиатуры программным модулем
  input_focus(used_key);
  kbd::scan();

  const bool calculator_context =
      input_focus == &mk61_baseloop_hook &&
      core_61::is_CALC() &&
      !core_61::edit_program &&
      !lcd_hooked &&
      !m61_text::active() &&
      !user_short_press_pending &&
      !drop_menu_exit_key_events;
  const bool calculator_idle =
      calculator_context &&
      mk61_calculator_is_idle() &&
      kbd::last_key() < 0 &&
      !kbd::any_key_pressed();
  rtc_idle_clock::poll(main_lcd(), calculator_context, calculator_idle);
}

void idle_main_process(void) {
  usb_mass_storage::service();
  usb_screen::service();
  // Consume the notification here, but never assume that the calculator owns
  // the foreground. The active editor/menu redraws on display-mode revision;
  // the outer loop handles the calculator after a nested UI has returned.
  (void) usb_screen::takeEvent();
  #ifdef TERMINAL
  service_terminal();
  #endif
  sound_poll();
  led::control();
  main_lcd().flush();
  idle_signal_poll();
}

void event_hold_key(i32 holded_key, i32 hold_quant) {
  switch(holded_key) {
      case KEY_USER_PRESS: // Удержание клавиши USER, вывод стека XYZT на экран
          #if MK61_USER_EXPLORER_SHORTCUT
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
          #if MK61_USER_EXPLORER_SHORTCUT
          user_short_press_pending = false;
          #endif
          lcd_hooked = false;
          dbgln(MENU, "UNHOLD [USER], quant = ", hold_quant);
          kbd::exclude_before(KEY_USER_PRESS); // уберем все коды отпускания/нажатия клавиш включая нажатие KEY_USER, из очереди клавиатуры
          lcd_std_display_redraw();
        break;
  }
}
