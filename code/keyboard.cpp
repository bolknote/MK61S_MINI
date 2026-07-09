#include <wiring_constants.h>
#include "keyboard.h"
#include "tools.hpp"
#include "debug.h"

// Описание геометрии и конфигурации клавиатуры
static constexpr usize KEY_IN_ROW             =   5;
static constexpr usize KEY_IN_COLUMN          =   8;
static constexpr usize LAST_SCAN_ROW          =   KEY_IN_ROW - 1;
static constexpr usize KEY_IN_KEYBOARD        =   KEY_IN_ROW * KEY_IN_COLUMN;
static constexpr usize KEY_RELEASE_BIT        =   6;
// Описание электрического расключения матрицы на ноги МК
static const   u8   data_pins[KEY_IN_COLUMN]  =   {PIN_KBD_COL0, PIN_KBD_COL1, PIN_KBD_COL2, PIN_KBD_COL3, PIN_KBD_COL4, PIN_KBD_COL5, PIN_KBD_COL6, PIN_KBD_COL7};
static const   u8   scan_pins[KEY_IN_ROW]     =   {PIN_KBD_ROW4, PIN_KBD_ROW3, PIN_KBD_ROW2, PIN_KBD_ROW1, PIN_KBD_ROW0};

static constexpr t_time_ms  TIME_DEBOUNCE     =   30;
static constexpr u32        TIME_SCAN_SETTLE_US = 1000;
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

#pragma pack(push, 4)
struct  TRowKeyStatus { // биты линий 1, 2, 4, 8, 16
  public:
    u8  now,       // последнее стабильное состояние строки
        candidate, // последнее считанное сырое состояние строки
        changed;   // изменившаяся стабильная колонка
    t_time_ms changed_at[KEY_IN_COLUMN];

    void reset(t_time_ms now_ms) {
      now = 0;
      candidate = 0;
      changed = 0;
      for(usize column = 0; column < KEY_IN_COLUMN; column++) changed_at[column] = now_ms;
    }

    u8 input(void) {
      const u8 sample = (u8) bus_in();
      const t_time_ms now_ms = millis();

      changed = 0;
      for(usize column = 0; column < KEY_IN_COLUMN; column++) {
        const u8 bit = (u8) (1u << column);

        if((candidate & bit) != (sample & bit)) {
          if((sample & bit) != 0) candidate |= bit; else candidate &= (u8) ~bit;
          changed_at[column] = now_ms;
          continue;
        }

        if((now & bit) != (candidate & bit) && (t_time_ms) (now_ms - changed_at[column]) >= TIME_DEBOUNCE) {
          if((candidate & bit) != 0) now |= bit; else now &= (u8) ~bit;
          changed = bit;
          break;
        }
      }

      return changed;
    }
    u8 get_state(usize column) {return ((~now >> column) & 1) << KEY_RELEASE_BIT;}
    bool pressed(void) const { return (now | candidate) != 0; }
};
#pragma pack(pop)

/* Циркулярный буфер для накопления скан-кодов клавиатуры FIFO */

static  constexpr usize MASK                =   7;
static  constexpr usize KEYBOARD_FIFO_LEN   =   8;
static  constexpr usize KEYBOARD_FIFO_LAST  =   KEYBOARD_FIFO_LEN - 1;

static  usize          read_count, write_count;
static  i8             buff[KEYBOARD_FIFO_LEN];

namespace cir_buff {
  inline  void    Init(void)    { read_count = 0; write_count = 0; }
  inline  bool    IsFull(void)  { return ((write_count - read_count) & ~MASK) != 0; }
  inline  bool    IsEmpty(void) { return write_count == read_count; }
  inline  usize   count(void)   { return (write_count - read_count) & MASK; }
}

i8    cir_buff_get(usize index) { 
  if(cir_buff::IsEmpty() || index > cir_buff::count()) return -1;
  return buff[(read_count + index) & MASK];
}

bool  cir_buff_write(i8 data) {
  if(cir_buff::IsFull()) {
    dbgln(KBD, " write full cir_buff");
    return false;  // буфер переполнен
  } else {
    buff[write_count++ & MASK] = data;
    dbghex(KBD, "write cbuf ", data);
    dbgln(KBD, " : read counter ", read_count, " : write counter ", write_count, cir_buff::IsFull()? " full" : " empty");
    return true;
  }
}

i32   cir_buff_read(void) {
  if(cir_buff::IsEmpty()) { // буфер пуст 
    dbgln(KBD, " read empty cir_buff");
    return -1;
  } else {
    const i8 data = buff[read_count++ & MASK];
    dbghex(KBD, "read cbuf ", data);
    dbgln(KBD, " : read counter ", read_count, " : write counter ", write_count);
    return data;
  }
}

i8    cir_buff_top(void)     { return cir_buff_get(0); }

/* Клавиатура */

static  TRowKeyStatus  RowArray[KEY_IN_ROW];
static  usize          scan_line;             // теккущая линия сканирования клавиатуры
static  i32            holded_scan_code;      // скан код клавишы взятой на удержание
static  isize          hold_quant_counter;    // счетчик квантов удержания
static  t_time_ms      press_time;            // время в ms последнего нажатия (без отжатия)
static  u32            scan_line_started_us;

inline isize get_set_bit_position(u8 row_code) {
  for(usize bit_position = 0; bit_position < KEY_IN_COLUMN; bit_position++){
    if((row_code & 1) != 0) return bit_position;
    row_code >>= 1;
  }
  return -1;
}

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
  if(holded_scan_code < 0) return;

  const t_time_ms now = millis();
  if(press_time >= now) return;

  hold_quant_counter++;
  dbgln(KBD, "hold time ", now, " hold count ", hold_quant_counter, " scan #", holded_scan_code);

  press_time = now + KEY_HOLD_MS;   // продолжаем опрашивать удержание до сброса удерживаемого скан-кода
  event_hold_key(holded_scan_code, hold_quant_counter); // генерация события удержания кнопки
}

namespace kbd {

i32   get_key(key_state state) {
  i32 key_code;
  while(!cir_buff::IsEmpty()) {
    key_code = cir_buff_read();
    dbghexln(KBD, " get_key ", key_code);
    if((key_code & (1 << KEY_RELEASE_BIT)) == (i8) state){
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
}

bool any_key_pressed(void) {
  for(usize i = 0; i < KEY_IN_ROW; i++) {
    if(RowArray[i].pressed()) return true;
  }
  return false;
}

bool is_key_pressed(i32 key_code) {
  if(key_code < 0 || key_code >= (i32) KEY_IN_KEYBOARD) return false;
  const usize code = (usize) key_code;
  const usize row = code % KEY_IN_ROW;
  const usize column = code / KEY_IN_ROW;
  return (RowArray[row].now & (u8) (1u << column)) != 0;
}

void  exclude_before(i32 before_key) { // убрать все коды клавиш в том числе before_key, из очереди клавиатуры
  i32 exclude_key;
  do {
    exclude_key = get_key();
    dbghexln(KBD, "del scancode $", exclude_key);
  } while(exclude_key > 0 && exclude_key != before_key);
}

i32   get_key_wait(void) {
  do {
    idle_main_process();  // отдаем безделье в основной поток бездействия
    const i32 scan_code = scan_and_debounced();
    if( scan_code >= 0 && scan_code < (1 << KEY_RELEASE_BIT) ) {
      kbd::exclude_before(scan_code);
      return scan_code;
    } 
  } while (true);
}

/*inline*/  /*__attribute__((always_inline))*/
void  debounce_init(void) {
  const t_time_ms init_time = millis();
  for(usize i = 0; i < KEY_IN_ROW; i++) RowArray[i].reset(init_time);
}

void  init(void) {
  debounce_init();
  // HAL init
  for(usize i=0; i < KEY_IN_ROW; i++) {
    digitalWrite(scan_pins[i], HIGH);
    pinMode(scan_pins[i], INPUT);
  }
  for(usize pin : data_pins) pinMode(pin, INPUT_PULLDOWN);
  //
  scan_line = 0;
  activate_scan_line();
  clear_hold_key();
  cir_buff::Init();

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
  const u8 bit_changed = RowArray[row].input();

  advance_scan_line();

  if(bit_changed == 0) {    // нет изменений в столбцах клавиатуры (выход)
    check_hold_key();       // Проверка врремени удержания 
    return -1;             
  }

  const usize column = get_set_bit_position(bit_changed);
  const u8 state     = RowArray[row].get_state(column);
  const u8 code      = (column*KEY_IN_ROW + row);
  const u8 scan_code = state | code;

  dbgln(KBD, "changed ", bit_changed, ",column ", column, ",row ", row,", scan_code ", scan_code);

  if(state == 0) sound_scaled(PIN_BUZZER, KEY_CLICK_FREQ_HZ, KEY_CLICK_MS, library_mk61::sound_volume(), KEY_CLICK_VOLUME_PERCENT);
  cir_buff_write(scan_code);

  if(state == 0) {
    idle_signal_reset();
  // было нажатие, принимаем на удержание клавишу (учет только одного последнего удержания)
    hold_quant_counter  =   -1;
    holded_scan_code    =   scan_code;
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

isize  scan_and_debounced(void) {
  return kbd::scan();
}

}
