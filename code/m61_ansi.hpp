#ifndef M61_ANSI_HPP
#define M61_ANSI_HPP

#include "rust_types.h"

namespace m61_ansi {

using PutByte = bool (*)(u8 x, u8 y, u8 value, void* user_data);
using ClearScreen = bool (*)(void* user_data);

struct Sink {
  PutByte put_byte;
  ClearScreen clear_screen;
  void* user_data;
};

struct SavedCursor {
  u8 x;
  u8 y;
  bool valid;
};

// Ограниченный монохромный терминальный вывод на дисплей калькулятора. Входные
// координаты курсора ANSI начинаются с 1, а в обратных вызовах Sink — с 0.
// Неподдерживаемые команды CSI (включая цвет и атрибуты SGR) считываются и
// игнорируются. Дисплей очищается только по явному запросу J/K.
class Writer {
  public:
    Writer(u8 cols, u8 rows, u8 cursor_x, u8 cursor_y,
           SavedCursor& saved_cursor, Sink sink);

    bool write(u8 value);
    u8 cursorX(void) const { return cursor_x; }
    u8 cursorY(void) const { return cursor_y; }

  private:
    enum class ParseState : u8 { TEXT, ESCAPE, CSI };
    static constexpr u8 MAX_PARAMS = 4;

    u8 cols;
    u8 rows;
    u8 cursor_x;
    u8 cursor_y;
    SavedCursor& saved_cursor;
    Sink sink;
    ParseState parse_state;
    u16 params[MAX_PARAMS];
    bool param_present[MAX_PARAMS];
    u8 param_index;

    bool put(u8 x, u8 y, u8 value);
    bool putAndAdvance(u8 value);
    void resetCsi(void);
    u16 parameter(u8 index, u16 fallback, bool zero_is_default) const;
    bool applyCsi(u8 command);
    bool eraseLine(u16 mode);
    bool eraseDisplay(u16 mode);
    void saveCursor(void);
    void restoreCursor(void);
    void moveRelative(i16 dx, i16 dy);
    void setPosition(u16 row, u16 col);
  };

} // пространство имён m61_ansi

#endif
