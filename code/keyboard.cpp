#include <Arduino.h>
#include "keyboard.h"
#include "entropy_pool.hpp"
#include "tools.hpp"
#include "debug.h"

// Описание геометрии и конфигурации клавиатуры
static constexpr usize KEY_IN_ROW             =   keyboard_core::ROW_COUNT;
static constexpr usize KEY_IN_COLUMN          =   keyboard_core::COLUMN_COUNT;
static constexpr usize LAST_SCAN_ROW          =   KEY_IN_ROW - 1;
static constexpr usize KEY_IN_KEYBOARD        =   keyboard_core::KEY_COUNT;
static constexpr u8    KEY_RELEASE_MASK       =   keyboard_core::RELEASE_MASK;
// Описание электрического расключения матрицы на ноги МК
static const   u8   data_pins[KEY_IN_COLUMN]  =   {PIN_KBD_COL0, PIN_KBD_COL1, PIN_KBD_COL2, PIN_KBD_COL3, PIN_KBD_COL4, PIN_KBD_COL5, PIN_KBD_COL6, PIN_KBD_COL7};
static const   u8   scan_pins[KEY_IN_ROW]     =   {PIN_KBD_ROW4, PIN_KBD_ROW3, PIN_KBD_ROW2, PIN_KBD_ROW1, PIN_KBD_ROW0};

static constexpr u32        TIME_SCAN_SETTLE_US = 1000;
static constexpr u32        STOP_WAKE_SETTLE_US = TIME_SCAN_SETTLE_US;
static constexpr u32        STOP_WAKE_DISCHARGE_US = 250;
static constexpr u32        STOP_WAKE_SAMPLE_INTERVAL_US = 50;
static constexpr usize      STOP_WAKE_SAMPLE_COUNT = 5;
static constexpr usize      STOP_WAKE_REQUIRED_HIGH_SAMPLES = 4;
static constexpr t_time_ms  KEY_HOLD_MS       =   1500;  // константный период времени удержания клавиши до генерации события
static constexpr isize      KEY_CLICK_FREQ_HZ =   650;
static constexpr usize      KEY_CLICK_MS      =   8;
static constexpr usize      KEY_CLICK_VOLUME_PERCENT = 35;

extern void idle_main_process(void);
extern void idle_signal_reset(void);
extern void event_hold_key(i32 holded_key, i32 hold_quant);
extern void event_unhold_key(i32 unholded_key, i32 hold_quant);

inline void scan_out(usize data) {
  for(int pin : scan_pins) {
    digitalWrite(pin, data & 1);
    data >>= 1;
  }
}

inline void bus_out(usize data) {
  for(int pin : data_pins) {
    digitalWrite(pin, data & 1);
    data >>= 1;
  }
}

inline usize bus_in(void) {
  usize input_data = 0;
  for(int pin : data_pins) input_data = (input_data << 1) | digitalRead(pin);
  return input_data;
}

/* Циркулярный буфер для накопления скан-кодов клавиатуры FIFO */

static keyboard_core::DeliveryQueue key_fifo;

namespace cir_buff {
  inline void Init(void) { key_fifo.reset(); }
  inline bool IsFull(void) { return key_fifo.full(); }
  inline bool IsEmpty(void) { return key_fifo.empty(); }
  inline usize count(void) { return key_fifo.size(); }
}

i8    cir_buff_get(usize index) {
  return (i8) key_fifo.peek(index);
}

bool  cir_buff_write(i8 data) {
  if(!key_fifo.push((i32) data)) {
    dbgln(KBD, keyboard_core::valid_scan_code((i32) data) ? " write full cir_buff" : " reject invalid scan code");
    return false;
  }
  dbghex(KBD, "write cbuf ", data);
  dbgln(KBD, " : count ", cir_buff::count(), cir_buff::IsFull()? " full" : " ready");
  return true;
}

i32   cir_buff_read(void) {
  const i32 data = key_fifo.pop();
  if(data < 0) { // буфер пуст
    dbgln(KBD, " read empty cir_buff");
    return -1;
  }
  dbghex(KBD, "read cbuf ", data);
  dbgln(KBD, " : count ", cir_buff::count());
  return data;
}

i8    cir_buff_top(void)     { return cir_buff_get(0); }

/* Клавиатура */

static  keyboard_core::DebouncedRow RowArray[KEY_IN_ROW];
static  usize          scan_line;             // теккущая линия сканирования клавиатуры
static  i32            holded_scan_code;      // скан код клавишы взятой на удержание
static  isize          hold_quant_counter;    // счетчик квантов удержания
static  t_time_ms      press_time;            // время в ms последнего нажатия (без отжатия)
static  u32            scan_line_started_us;
static  keyboard_core::ExternalKeyState external_keys;
static  keyboard_core::PressEdgeLatch immediate_presses;

#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
static bool stop_wake_armed;
static volatile bool stop_wake_irq_seen;
static volatile u8 stop_wake_rows_seen;
static u32 stop_wake_capture_events;
static i32 last_stop_wake_scan_code = -1;
static u8 last_stop_wake_capture_count;
static u8 last_stop_wake_rows;
static u8 last_stop_wake_captured_rows;
static constexpr u32 STOP_WAKE_EXTI_MASK =
    (1UL << 4) | (1UL << 5) | (1UL << 6) | (1UL << 7) | (1UL << 8);

static u8 sample_stop_wake_rows(void) {
  u8 result = 0;
  for(usize row = 0; row < KEY_IN_ROW; row++) {
    if(digitalRead(scan_pins[row]) != LOW) result |= (u8) (1U << row);
  }
  return result;
}

static void note_stop_wake_rows(u8 rows) {
  if(rows != 0) __atomic_fetch_or(&stop_wake_rows_seen, rows, __ATOMIC_RELAXED);
}

static void stop_wake_irq(void) {
  stop_wake_irq_seen = true;
  note_stop_wake_rows(sample_stop_wake_rows());
}
#endif

inline void activate_scan_line(void) {
  digitalWrite(scan_pins[scan_line], HIGH);
  pinMode(scan_pins[scan_line], OUTPUT);
  scan_line_started_us = micros();
}

inline void advance_scan_line(void) {
  pinMode(scan_pins[scan_line], INPUT);
  if(scan_line == LAST_SCAN_ROW) scan_line = 0; else scan_line++;
  activate_scan_line();
}

void 	check_hold_key(void) {
  const t_time_ms now = millis();
  if(holded_scan_code >= 0 &&
     keyboard_core::time_reached(now, press_time)) {
    hold_quant_counter++;
    dbgln(KBD, "hold time ", now, " hold count ", hold_quant_counter,
          " scan #", holded_scan_code);
    press_time = now + KEY_HOLD_MS;
    event_hold_key(holded_scan_code, hold_quant_counter);
  }
  i32 external_key = -1;
  i32 external_quant = -1;
  if(external_keys.pollHold(now, KEY_HOLD_MS,
                            external_key, external_quant)) {
    event_hold_key(external_key, external_quant);
  }
}

namespace kbd {

bool push(i8 key_code) {
  const bool suppressed = key_fifo.suppressed(key_code);
  if(!cir_buff_write(key_code)) return false;
  if(!suppressed && key_code >= 0 && key_code < (i8) KEY_RELEASE_MASK) {
    immediate_presses.note((i32) key_code);
  }
  return true;
}

i32   get_key(key_state state) {
  i32 key_code;
  while(!cir_buff::IsEmpty()) {
    key_code = cir_buff_read();
    dbghexln(KBD, " get_key ", key_code);
    if((key_code & KEY_RELEASE_MASK) == (i8) state){
      dbghexln(KBD, " get_key ret ", key_code);
      return key_code;
    }
  }
  return -1;
}

void  reset_scan_line(void) {
  pinMode(scan_pins[scan_line], INPUT);
  scan_line = KEY_IN_ROW-1;
  activate_scan_line();
}

void  clear_hold_key(void) {
  holded_scan_code = -1;
  hold_quant_counter = -1;
  external_keys.clearHold();
}

bool take_immediate_press(i32 key_code) {
  return immediate_presses.take(key_code) && !key_fifo.suppressed(key_code);
}

void clear_immediate_presses(void) {
  immediate_presses.reset();
}

bool any_key_pressed(void) {
  if(external_keys.anyPressed()) return true;
  for(usize i = 0; i < KEY_IN_ROW; i++) {
    if(RowArray[i].pressed_or_pending()) return true;
  }
  return false;
}

bool is_physical_key_pressed(i32 key_code) {
  if(key_code < 0 || key_code >= (i32) KEY_IN_KEYBOARD) return false;
  const usize code = (usize) key_code;
  const usize row = code % KEY_IN_ROW;
  const usize column = code / KEY_IN_ROW;
  return RowArray[row].pressed(column);
}

bool is_key_pressed(i32 key_code) {
  if(is_physical_key_pressed(key_code)) return true;
  return external_keys.pressed(key_code);
}

void set_external_key_pressed(i32 key_code, bool pressed) {
  if(key_code < 0 || key_code >= (i32) KEY_IN_KEYBOARD) return;

  if(pressed) {
    if(!external_keys.press(key_code, millis(), KEY_HOLD_MS)) return;
    immediate_presses.note(key_code);
    entropy_pool::note_key((u8) key_code, micros());
    sound_scaled(PIN_BUZZER, KEY_CLICK_FREQ_HZ, KEY_CLICK_MS,
                 library_mk61::sound_volume(), KEY_CLICK_VOLUME_PERCENT);
    idle_signal_reset();
    return;
  }

  i32 unhold_quant = -1;
  if(!external_keys.release(key_code, unhold_quant)) return;
  if(unhold_quant >= 0) event_unhold_key(key_code, unhold_quant);
}

bool prepare_stop_wake(void) {
#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
  if(stop_wake_armed || any_key_pressed() || kbd::last_key() >= 0) return false;

  // Remove the one driven scan row first. Then every matrix column drives the
  // same HIGH level, so any number of simultaneous keys can only connect equal
  // outputs. Rows PB4..PB8 are unique EXTI lines and use pulldowns.
  for(usize row = 0; row < KEY_IN_ROW; row++) pinMode(scan_pins[row], INPUT);
  for(usize column = 0; column < KEY_IN_COLUMN; column++) {
    digitalWrite(data_pins[column], HIGH);
    pinMode(data_pins[column], OUTPUT);
  }
  for(usize row = 0; row < KEY_IN_ROW; row++) {
    pinMode(scan_pins[row], INPUT_PULLDOWN);
  }

  stop_wake_irq_seen = false;
  __atomic_store_n(&stop_wake_rows_seen, (u8) 0, __ATOMIC_RELAXED);
  EXTI->PR = STOP_WAKE_EXTI_MASK;
  for(usize row = 0; row < KEY_IN_ROW; row++) {
    attachInterrupt(scan_pins[row], stop_wake_irq, RISING);
  }
  EXTI->PR = STOP_WAKE_EXTI_MASK;
  stop_wake_armed = true;

  // A key which became active while GPIO/EXTI were changing directions must
  // abort the pending STOP instead of being erased with the setup flags.
  const u8 active_rows = sample_stop_wake_rows();
  if(active_rows != 0) {
    note_stop_wake_rows(active_rows);
    stop_wake_irq_seen = true;
  }
  return true;
#else
  return false;
#endif
}

bool stop_wake_pending(void) {
#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
  if(!stop_wake_armed) return false;
  if(stop_wake_irq_seen || (EXTI->PR & STOP_WAKE_EXTI_MASK) != 0) return true;
  const u8 active_rows = sample_stop_wake_rows();
  if(active_rows != 0) {
    note_stop_wake_rows(active_rows);
    return true;
  }
#endif
  return false;
}

keyboard_stop_wake_snapshot stop_wake_statistics(void) {
#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
  return {
    true, stop_wake_capture_events, last_stop_wake_scan_code,
    last_stop_wake_capture_count, last_stop_wake_rows,
    last_stop_wake_captured_rows,
  };
#else
  return {false, 0, -1, 0, 0, 0};
#endif
}

void reset_stop_wake_statistics(void) {
#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
  stop_wake_capture_events = 0;
  last_stop_wake_scan_code = -1;
  last_stop_wake_capture_count = 0;
  last_stop_wake_rows = 0;
  last_stop_wake_captured_rows = 0;
#endif
}

#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
static u8 restore_stop_wake(bool preserve_presses) {
  if(!stop_wake_armed) return 0;

  u8 pressed_by_row[KEY_IN_ROW] = {};
  const u8 wake_rows = preserve_presses
      ? (u8) (__atomic_load_n(&stop_wake_rows_seen, __ATOMIC_RELAXED) |
              sample_stop_wake_rows())
      : 0;
  if(preserve_presses && wake_rows != 0) {
    // First discharge the row wiring left HIGH by the all-columns wake mode.
    // Then qualify every column for the same full millisecond used by the
    // ordinary scanner. Multiple samples reject GPIO/line-settling spikes;
    // restricting results to rows that caused the wake rejects later keys.
    for(usize column = 0; column < KEY_IN_COLUMN; column++) {
      digitalWrite(data_pins[column], LOW);
    }
    delayMicroseconds(STOP_WAKE_SETTLE_US);
    for(usize data_index = 0; data_index < KEY_IN_COLUMN; data_index++) {
      digitalWrite(data_pins[data_index], HIGH);
      delayMicroseconds(STOP_WAKE_SETTLE_US);
      u8 high_votes[KEY_IN_ROW] = {};
      for(usize sample = 0; sample < STOP_WAKE_SAMPLE_COUNT; sample++) {
        const u8 active_rows = sample_stop_wake_rows();
        for(usize row = 0; row < KEY_IN_ROW; row++) {
          if((active_rows & (u8) (1U << row)) != 0) high_votes[row]++;
        }
        if(sample + 1U < STOP_WAKE_SAMPLE_COUNT) {
          delayMicroseconds(STOP_WAKE_SAMPLE_INTERVAL_US);
        }
      }
      const u8 qualified = keyboard_core::qualified_rows(
          high_votes, wake_rows, STOP_WAKE_REQUIRED_HIGH_SAMPLES);
      const usize logical_column =
          keyboard_core::logical_column_from_data_index(data_index);
      for(usize row = 0; row < KEY_IN_ROW; row++) {
        if((qualified & (u8) (1U << row)) != 0) {
          pressed_by_row[row] |= (u8) (1U << logical_column);
        }
      }
      digitalWrite(data_pins[data_index], LOW);
      delayMicroseconds(STOP_WAKE_DISCHARGE_US);
    }
  }

  for(usize row = 0; row < KEY_IN_ROW; row++) {
    detachInterrupt(scan_pins[row]);
  }
  EXTI->PR = STOP_WAKE_EXTI_MASK;
  stop_wake_irq_seen = false;
  __atomic_store_n(&stop_wake_rows_seen, (u8) 0, __ATOMIC_RELAXED);
  stop_wake_armed = false;

  for(usize row = 0; row < KEY_IN_ROW; row++) pinMode(scan_pins[row], INPUT);
  for(usize column = 0; column < KEY_IN_COLUMN; column++) {
    pinMode(data_pins[column], INPUT_PULLDOWN);
  }

  const t_time_ms now = millis();
  u8 captured = 0;
  i32 last_captured = -1;
  for(usize row = 0; row < KEY_IN_ROW; row++) {
    RowArray[row].prime(pressed_by_row[row], now);
    immediate_presses.noteRow(row, pressed_by_row[row]);
    for(usize column = 0; column < KEY_IN_COLUMN; column++) {
      if((pressed_by_row[row] & (u8) (1U << column)) == 0) continue;
      const i32 code = (i32) (column * KEY_IN_ROW + row);
      if(cir_buff_write((i8) code) && captured != 0xFFU) captured++;
      last_captured = code;
      entropy_pool::note_key((u8) code, micros());
    }
  }

  if(captured != 0) {
    if(stop_wake_capture_events != 0xFFFFFFFFUL) stop_wake_capture_events++;
    last_stop_wake_scan_code = last_captured;
    last_stop_wake_capture_count = captured;
    last_stop_wake_rows = wake_rows;
    u8 captured_rows = 0;
    for(usize row = 0; row < KEY_IN_ROW; row++) {
      if(pressed_by_row[row] != 0) captured_rows |= (u8) (1U << row);
    }
    last_stop_wake_captured_rows = captured_rows;
  }

  scan_line = 0;
  activate_scan_line();
  if(last_captured >= 0) {
    hold_quant_counter = -1;
    holded_scan_code = last_captured;
    press_time = now + KEY_HOLD_MS;
    sound_scaled(PIN_BUZZER, KEY_CLICK_FREQ_HZ, KEY_CLICK_MS,
                 library_mk61::sound_volume(), KEY_CLICK_VOLUME_PERCENT);
    idle_signal_reset();
  }
  return captured;
}
#endif

u8 resume_from_stop(void) {
#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
  return restore_stop_wake(true);
#else
  return 0;
#endif
}

void cancel_stop_wake(void) {
#if MK61_KEYBOARD_STOP_WAKE_SUPPORTED
  (void) restore_stop_wake(false);
#endif
}

void handoff(Event cause) {
  if(!cause.press()) return;
  const i32 key = cause.key();
  const usize row = (usize) key % KEY_IN_ROW;
  const usize column = (usize) key / KEY_IN_ROW;
  const bool pending =
      (RowArray[row].candidate_mask() & (1U << column)) != 0;
  key_fifo.handoff(cause, is_key_pressed(key) || pending);
  (void) immediate_presses.take(key);
  if(key_fifo.suppressed(key) && holded_scan_code == key) {
    holded_scan_code = -1;
    hold_quant_counter = -1;
  }
  if(key_fifo.suppressed(key)) external_keys.clearHold(key);
}

bool handoff_pending() { return key_fifo.pending(); }
u32 overflow_count() { return key_fifo.overflows(); }
Event poll_event() { (void) scan(); return Event(get_key()); }

i32   get_key_wait(void) {
  do {
    idle_main_process();  // отдаем безделье в основной поток бездействия
    const i32 scan_code = poll_event().code();
    if(scan_code < 0) continue;
    if(scan_code < KEY_RELEASE_MASK) {
      handoff(Event(scan_code));
      return scan_code;
    }
  } while (true);
}

/*inline*/  /*__attribute__((always_inline))*/
static void debounce_init(void) {
  const t_time_ms init_time = millis();
  for(usize i = 0; i < KEY_IN_ROW; i++) RowArray[i].reset(init_time);
  immediate_presses.reset();
}

void  init(void) {
  debounce_init();
  // Инициализация HAL
  for(usize i=0; i < KEY_IN_ROW; i++) {
    digitalWrite(scan_pins[i], HIGH);
    pinMode(scan_pins[i], INPUT);
  }
  for(usize pin : data_pins) pinMode(pin, INPUT_PULLDOWN);
  //
  scan_line = 0;
  activate_scan_line();
  external_keys.reset();
  clear_hold_key();
  cir_buff::Init();
  reset_stop_wake_statistics();

}

void  test(void) {
  dbgln(KBD, "test kbd. ");
  for(usize pin : data_pins) {
    //if(pin != 29) {
      pinMode(pin, OUTPUT); digitalWrite(pin, HIGH);
      dbghexln(KBD, "output kbd.data <- ", pin, ", kbd.data=", digitalRead(bus_in()));
      digitalWrite(pin, LOW); pinMode(pin, INPUT_PULLDOWN);
      delay(240);
    //}
  }
/*
  for(usize pin : data_pins) pinMode(pin, INPUT_PULLDOWN);
  for(usize pin : scan_pins) pinMode(pin, INPUT);
  isize i = 0;
  for(usize pin : scan_pins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
    dbghex(KBD, (const char*) "kbd.scan_line[", i++, (const char*) "] LOW, kbd.data=", digitalRead(bus_in()));
    digitalWrite(pin, HIGH);
    dbghex(KBD, " HIGH, kbd.data=", digitalRead(bus_in()));
    pinMode(pin, INPUT);
    dbghexln(KBD, " hi-Z, kbd.data=", digitalRead(bus_in()));
    delay(40);
  }
*/
}

isize scan(void) {
  if((u32) (micros() - scan_line_started_us) < TIME_SCAN_SETTLE_US) {
    check_hold_key();
    return -1;
  }

  const u8 row = scan_line;
  const u8 sample = (u8) bus_in();
  const u8 rising =
    (u8) (sample & (u8) ~RowArray[row].candidate_mask());
  immediate_presses.noteRow(row, rising);
  const u8 bit_changed = RowArray[row].update(sample, millis());

  advance_scan_line();

  if(bit_changed == 0) {    // нет изменений в столбцах клавиатуры (выход)
    // An immediate M61 edge can be shorter than debounce and never produce
    // a RELEASE event. Once this row is entirely up for the key, end handoff.
    if(key_fifo.pending()) {
      for(usize column = 0; column < KEY_IN_COLUMN; ++column) {
        const i32 key = (i32) (column * KEY_IN_ROW + row);
        if(!RowArray[row].pressed(column) &&
           (RowArray[row].candidate_mask() & (1U << column)) == 0 &&
           !external_keys.pressed(key))
          key_fifo.released(key);
      }
    }
    check_hold_key();       // Проверка врремени удержания
    return -1;
  }

  const isize changed_column = keyboard_core::first_set_bit(bit_changed);
  if(changed_column < 0 || changed_column >= (isize) KEY_IN_COLUMN) return -1;
  const usize column = (usize) changed_column;
  const u8 state     = RowArray[row].state_mask(column);
  const u8 code      = (column*KEY_IN_ROW + row);
  const u8 scan_code = state | code;

  dbgln(KBD, "changed ", bit_changed, ",column ", column, ",row ", row,", scan_code ", scan_code);

  if(state == 0) {
    entropy_pool::note_key(code, micros());
    sound_scaled(PIN_BUZZER, KEY_CLICK_FREQ_HZ, KEY_CLICK_MS, library_mk61::sound_volume(), KEY_CLICK_VOLUME_PERCENT);
  }
  cir_buff_write(scan_code);

  if(state == 0) {
    idle_signal_reset();
  // было нажатие, принимаем на удержание клавишу (учет только одного последнего удержания)
    hold_quant_counter  =   -1;
    holded_scan_code    =   key_fifo.suppressed(code) ? -1 : scan_code;
    press_time          =   millis() + KEY_HOLD_MS;
    dbgln(KBD, "fixed press time: ", press_time, "ms, (hold) scan_code #", scan_code);
  } else {
  // было отжатие удержанной клавиши
    dbgln(KBD, "release scan_code #", scan_code);
    if(holded_scan_code == code) {
      dbg(KBD, "scan_code #", scan_code, ", ms ", millis());
      if(hold_quant_counter >= 0) {
        dbgln(KBD, " <<UNHOLD>>");
        event_unhold_key(holded_scan_code, hold_quant_counter);
        hold_quant_counter  = -1;   // снимаем счетчик квантов удержания
      }
      holded_scan_code    = -1;   // снимаем удержание
    }
  }

  return (isize) scan_code;
}

isize scan_m61_controls(void) {
  // Р, ГРД, Г и ESC находятся на одной верхней строке матрицы. Во время
  // работы M61 приоритетно возвращаем сканер на неё; после миллисекунды
  // установления обычный scan() читает строку и сохраняет как штатное
  // debounced-событие, так и короткий фронт.
  if(scan_line != LAST_SCAN_ROW) {
    pinMode(scan_pins[scan_line], INPUT);
    scan_line = LAST_SCAN_ROW;
    activate_scan_line();
    check_hold_key();
    return -1;
  }
  return scan();
}



}
