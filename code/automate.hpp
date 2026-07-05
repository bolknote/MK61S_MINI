static constexpr usize hz_STOP_SIGNAL  =   200;  // Hz
static constexpr usize ms_STOP_SIGNAL  =   850;  // ms

inline  void  return_auto_mode(void) { // возвращение в режим АВТ
    sound(PIN_BUZZER, hz_STOP_SIGNAL, ms_STOP_SIGNAL);
    MnemoLabel.enable();
    if(!config.disassm) disassembler.disable(); // если дизассемблер включен в конфигурации "ВСЕГДА" то выключение ненужно
    #ifdef MK61_EXTENDED
      disassembler.disable();
      lcd.setCursor(0,0);
      for(usize i = 0; i < 5; i++) {
        const u8 byte = mk61s.byte_from_R(14, i);
        const char letter = (byte == 0)? ' ' : ((char) byte);
        lcd.write(letter);
      }
    #endif
}

/* СОБЫТИЯ автомата конечных состояний МК-61 */
inline  void  event_stop_in_prg_mk61(void) {
  runtime_ms = millis() - runtime_ms;
  // Для измерений производительности 
  #ifdef DEBUG_MEASURE
    char mk61_display[14];
    core_61::update_indicator(&mk61_display[0], terminal_symbols);
    dbgln(MEASURE, "time elapsed (ms): ", runtime_ms, " : ", mk61_display);
  #endif

  dbgln(MINI, "PRG: STOP dt = ", runtime_ms, " mk61_reload_quant = ", mk61_quants_reload);
  
  // >>>>>> Расширение системы команд МК-61 по режиму старт/стоп  <<<<<<<
  const i32 back_step = core_61::get_IP() - 1;
  if(back_step < 0 || back_step >= (i32) core_61::program_steps()) {
      return_auto_mode();
      return;
  }
  const i32 code = core_61::get_code(core_61::get_ring_address(back_step));
  dbgln(EXT_RUN, "IP = ", back_step, ". MK61 code = ", code);
  if(code == 0x50 && ext61_program[back_step] != 0) { 
    // Есть код расширения режима старт/стоп!
      ext_command.code  = ext61_program[back_step];
      ext_command.time  = millis();
      dbgln(EXT_RUN, "Extended code = ", ext_command.code);
  } else { 
    // Если нет расширенного кода то обычная работа в режиме ОСТАНОВ
      return_auto_mode();
  }

}

inline void  event_start_prg_mk61(void) {
  dbgln(MINI, "PRG: first step dt = ", runtime_ms, " mk61_reload_quant = ", mk61_quants_reload);
  MnemoLabel.disable();
  disassembler.disable("RUN");
  mk61_quants =   mk61_quants_reload;
  runtime_ms  =   millis();
}

inline void service_run_keypress(void) {
  const i32 keycode = kbd::get_key(PRESS);
  if(keycode >= 0) key_press_handler(keycode);
}

inline void run_program_steps(void) {
  const usize step_count = library_mk61::speed_is_turbo() ? cfg::TURBO_MK61_BATCH_STEPS : 1;

  for(usize i = 0; i < step_count; i++) {
      core_61::step();

      if(core_61::is_CALC()) {
          event_stop_in_prg_mk61();     // обработка события "ОСТАНОВ ПРОГРАММЫ"
          break;
      }
  }

  service_run_keypress();
}

/* АВТОМАТ конечных состояний МК-61 */
inline void mk61_automate(void) {
  static constexpr i32 REQUEST_IDLE_LOOP  =   1;  // любое положительное число
  static constexpr i32 REQUEST_BASE_LOOP  =  -1;  // любое отрицательное число
  static i32 sending_keycode = REQUEST_BASE_LOOP;

  if(core_61::is_RUN()) {
  // === режим работы по программе ===
      dbgln(MINI, "RUN: next steps");

      run_program_steps();
  } else {
  // === обычный режим работы каклькулятора ===
      if(sending_keycode >= 0) { 
        // в предыдущем цикле в ядро mk61 был передан код клавиши - запуск "холостых" циклов
          dbgln(MINI, "CALC: extend loop");
          core_61::step();

          if(core_61::is_RUN()) {
              event_start_prg_mk61();                 // обработка события "СТАРТ ПРОГРАММЫ"
              sending_keycode = REQUEST_IDLE_LOOP;    // планируем после останова программы дообработать нажатую кнопку в холостых циклах
          } else if(core_61::is_displayed()) {
              sending_keycode = REQUEST_BASE_LOOP;    // нет необходимости в "холостых" циклах - выход в основной цикл
          }
      } else {
        // основной цикл в котором находится устройство пока не будет наэата кнопка калькулятора
          dbgln(MINI, "CALC: base loop"); 
          sending_keycode = kbd::get_key(PRESS);
          if(sending_keycode >= 0) {
              key_press_handler(sending_keycode);
              core_61::step();
          }
      }
  }
}
