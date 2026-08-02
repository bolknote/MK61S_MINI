#ifndef TERMINAL_LINE_EDITOR_HPP
#define TERMINAL_LINE_EDITOR_HPP

#include "rust_types.h"
#include "utf8_view.hpp"

#include <string.h>

namespace terminal_line_editor {

enum class Key : u8 {
  NONE,
  UP,
  DOWN,
  RIGHT,
  LEFT,
  HOME,
  END,
  DELETE_FORWARD
};

// Incremental decoder for the ANSI sequences emitted by Tera Term, PuTTY and
// the usual VT100-compatible terminals.  Keeping it transport-independent
// also lets a sequence span several USB CDC packets.
class EscapeDecoder {
  public:
    constexpr EscapeDecoder(void)
      : state(State::IDLE), parameter(0), have_parameter(false),
        later_parameter(false) {}

    void reset(void) {
      state = State::IDLE;
      parameter = 0;
      have_parameter = false;
      later_parameter = false;
    }

    // Returns true when byte belongs to an escape sequence and must not be
    // inserted into the command line.  key is NONE until a known sequence is
    // complete.
    bool feed(u8 byte, Key& key) {
      key = Key::NONE;

      if(state == State::IDLE) {
        if(byte != ESC) return false;
        state = State::ESCAPE;
        return true;
      }

      if(state == State::ESCAPE) {
        if(byte == '[') {
          state = State::CSI;
          parameter = 0;
          have_parameter = false;
          later_parameter = false;
        } else if(byte == 'O') {
          state = State::SS3;
        } else {
          reset();
        }
        return true;
      }

      if(state == State::SS3) {
        key = cursor_key(byte);
        reset();
        return true;
      }

      // CSI parameters occupy 0x30..0x3f.  Only the first numeric parameter
      // selects a key; later modifier parameters (for example 1;5D) are
      // deliberately ignored while the final byte is still recognised.
      if(byte >= '0' && byte <= '9') {
        if(!later_parameter) {
          have_parameter = true;
          const u16 digit = (u16) (byte - '0');
          parameter = parameter <= 999
              ? (u16) (parameter * 10 + digit)
              : (u16) 10000;
        }
        return true;
      }
      if(byte >= 0x20 && byte <= 0x3F) {
        if(byte == ';') later_parameter = true;
        return true;
      }
      if(byte >= 0x40 && byte <= 0x7E) {
        key = byte == '~' ? tilde_key() : cursor_key(byte);
        reset();
        return true;
      }

      reset();
      return true;
    }

  private:
    enum class State : u8 { IDLE, ESCAPE, CSI, SS3 };
    static constexpr u8 ESC = 0x1B;

    State state;
    u16 parameter;
    bool have_parameter;
    bool later_parameter;

    static Key cursor_key(u8 byte) {
      switch(byte) {
        case 'A': return Key::UP;
        case 'B': return Key::DOWN;
        case 'C': return Key::RIGHT;
        case 'D': return Key::LEFT;
        case 'H': return Key::HOME;
        case 'F': return Key::END;
        default:  return Key::NONE;
      }
    }

    Key tilde_key(void) const {
      if(!have_parameter) return Key::NONE;
      switch(parameter) {
        case 1:
        case 7: return Key::HOME;
        case 3: return Key::DELETE_FORWARD;
        case 4:
        case 8: return Key::END;
        default: return Key::NONE;
      }
    }
};

inline bool valid(const u8* data, usize length, usize cursor,
                  usize capacity) {
  return data != NULL && capacity > 0 && length < capacity && cursor <= length;
}

inline bool move_left(const u8* data, usize length, usize& cursor) {
  if(!valid(data, length, cursor, length + 1) || cursor == 0) return false;
  cursor = utf8_view::previous_offset(data, (u16) length, (u16) cursor);
  return true;
}

inline bool move_right(const u8* data, usize length, usize& cursor) {
  if(!valid(data, length, cursor, length + 1) || cursor >= length) return false;
  const usize next = utf8_view::next_offset(data, (u16) length, (u16) cursor);
  cursor = next > cursor && next <= length ? next : cursor + 1;
  return true;
}

inline bool insert_byte(u8* data, usize& length, usize& cursor,
                        usize capacity, u8 byte) {
  if(!valid(data, length, cursor, capacity) || length + 1 >= capacity) return false;
  memmove(data + cursor + 1, data + cursor, length - cursor);
  data[cursor++] = byte;
  data[++length] = 0;
  return true;
}

inline bool backspace(u8* data, usize& length, usize& cursor,
                      usize capacity) {
  if(!valid(data, length, cursor, capacity) || cursor == 0) return false;
  const usize previous = utf8_view::previous_offset(
      data, (u16) length, (u16) cursor);
  const usize removed = cursor - previous;
  memmove(data + previous, data + cursor, length - cursor);
  length -= removed;
  cursor = previous;
  data[length] = 0;
  return true;
}

inline bool delete_forward(u8* data, usize& length, usize cursor,
                           usize capacity) {
  if(!valid(data, length, cursor, capacity) || cursor >= length) return false;
  usize next = utf8_view::next_offset(data, (u16) length, (u16) cursor);
  if(next <= cursor || next > length) next = cursor + 1;
  memmove(data + cursor, data + next, length - next);
  length -= next - cursor;
  data[length] = 0;
  return true;
}

} // namespace terminal_line_editor

#endif
