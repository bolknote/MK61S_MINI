#include "rust_types.h"

class MK61Display {
  public:
    u8 rows(void) const { return 2; }
    void clear(void) {}
    void setCursor(u8, u8) {}
    void write(u8) {}
    bool supportsCursor(void) const { return true; }
    void cursorOn(void) {}
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display&) {}
};

#define TEXT_EDITOR_HOST_TEST
#include "text_editor.hpp"
#include "lcd1602_editor_driver.hpp"
#include "lcd1602_editor_viewport.hpp"
#include "utf8_view.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

void test_init_terminates_untrusted_buffer(void) {
  char source[4] = {'A', 'B', 'C', 'D'};
  text_editor::Buffer editor;
  text_editor::init(editor, source, sizeof(source));
  assert(editor.len == 3);
  assert(source[3] == 0);
  assert(editor.cursor == 0 && editor.view_top == 0);

  text_editor::init(editor, NULL, 0);
  assert(editor.len == 0 && editor.cursor == 0);
}

void test_edit_primitives_reject_corrupt_state(void) {
  char source[8] = "ABC";
  u16 len = 3;
  u16 cursor = 7;
  assert(!text_editor::insert_text(source, len, cursor, sizeof(source), "X"));
  assert(strcmp(source, "ABC") == 0 && len == 3 && cursor == 7);
  assert(!text_editor::backspace(source, len, cursor));

  cursor = 2;
  assert(text_editor::replace_range(source, len, cursor, sizeof(source), 1, 2, "xyz"));
  assert(strcmp(source, "AxyzC") == 0);
  assert(len == 5 && cursor == 4);
  assert(!text_editor::replace_range(source, len, cursor, sizeof(source), 0, 0, "toolong"));
}

void test_sms_failure_does_not_arm_stale_state(void) {
  char full[4] = "ABC";
  u16 len = 3;
  u16 cursor = 3;
  text_editor::SmsState sms;
  text_editor::sms_reset(sms);
  assert(!text_editor::sms_tap(full, len, cursor, sizeof(full), sms, 18, 100));
  assert(!sms.active);
  assert(strcmp(full, "ABC") == 0);

  char source[8] = "AX";
  len = 2;
  cursor = 2;
  sms.active = true;
  sms.key_code = 18; // ABC
  sms.index = 0;
  sms.deadline_ms = 1000;
  assert(text_editor::sms_tap(source, len, cursor, sizeof(source), sms, 18, 200));
  assert(strcmp(source, "AXA") == 0);
}

bool corrupting_macro(char*, u16& len, u16& cursor, u16, i32, void*) {
  len = 0xFFFF;
  cursor = 0xFFFF;
  return true;
}

void test_hook_output_is_sanitized(void) {
  char source[8] = "ABC";
  text_editor::Buffer editor;
  text_editor::init(editor, source, sizeof(source));
  editor.shift = text_editor::Shift::ALPHA;

  const text_editor::KeyMap keys = {};
  const text_editor::Hooks hooks = {NULL, &corrupting_macro, NULL, NULL, NULL};
  assert(text_editor::handle_key(editor, keys, hooks, 99, 0) == text_editor::KeyResult::DIRTY);
  assert(editor.len == 3);
  assert(editor.cursor == 3);
}

void test_sms_deadline_wraparound(void) {
  text_editor::SmsState sms = {true, 1, 0, 0x00000010u};
  assert(!text_editor::sms_expired(sms, 0xFFFFFFF0u));
  assert(text_editor::sms_expired(sms, 0x00000010u));
}

void test_cx_backspaces_and_f_left_is_not_backspace(void) {
  char source[16] = "ABC";
  text_editor::Buffer editor;
  text_editor::init(editor, source, sizeof(source));
  editor.cursor = editor.len;

  const text_editor::KeyMap keys = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};
  const text_editor::Hooks hooks = {NULL, NULL, NULL, NULL, NULL};
  assert(text_editor::handle_key(editor, keys, hooks, keyboard_layout::ACTIVE.cx, 0) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(source, "AB") == 0 && editor.cursor == 2);

  assert(text_editor::handle_key(editor, keys, hooks, keys.alpha, 0) ==
         text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(editor, keys, hooks, keys.left, 0) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(source, "AB") == 0 && editor.cursor == 2);
}

void test_f_cx_clears_only_current_line_then_removes_it(void) {
  char source[32] = "ONE\nTWO\nTHREE";
  text_editor::Buffer editor;
  text_editor::init(editor, source, sizeof(source));
  editor.cursor = 6;

  const text_editor::KeyMap keys = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};
  const text_editor::Hooks hooks = {NULL, NULL, NULL, NULL, NULL};
  assert(text_editor::handle_key(editor, keys, hooks, keys.alpha, 0) == text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(editor, keys, hooks, keyboard_layout::ACTIVE.cx, 0) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(source, "ONE\n\nTHREE") == 0);
  assert(editor.cursor == 4);
  assert(text_editor::next_line_start(source, 0, editor.len) == 4);
  assert(text_editor::next_line_start(source, 4, editor.len) == 5);
  assert(text_editor::previous_line_start(source, 5) == 4);

  assert(text_editor::handle_key(editor, keys, hooks, keys.alpha, 0) == text_editor::KeyResult::DIRTY);
  assert(text_editor::handle_key(editor, keys, hooks, keyboard_layout::ACTIVE.cx, 0) ==
         text_editor::KeyResult::DIRTY);
  assert(strcmp(source, "ONE\nTHREE") == 0);
  assert(editor.cursor == 4);
}

void test_clear_current_line_removes_empty_edge_lines_and_crlf(void) {
  char first[16] = "\nSECOND";
  u16 len = (u16) strlen(first);
  u16 cursor = 0;
  assert(text_editor::clear_current_line(first, len, cursor, sizeof(first)));
  assert(strcmp(first, "SECOND") == 0 && cursor == 0);

  char last[16] = "FIRST\r\n";
  len = (u16) strlen(last);
  cursor = len;
  assert(text_editor::clear_current_line(last, len, cursor, sizeof(last)));
  assert(strcmp(last, "FIRST") == 0 && cursor == 5);
}

void test_single_line_cx_backspaces_and_clears(void) {
  char source[8] = "123";
  u16 len = 3;
  assert(text_editor::apply_single_line_cx(source, len, sizeof(source), false));
  assert(strcmp(source, "12") == 0 && len == 2);
  assert(text_editor::apply_single_line_cx(source, len, sizeof(source), true));
  assert(strcmp(source, "") == 0 && len == 0);
  assert(text_editor::apply_single_line_cx(source, len, sizeof(source), false));
  assert(strcmp(source, "") == 0 && len == 0);
}

void test_utf8_validation(void) {
  const u8 valid[] = {
    'A', 0xD0, 0x90, 0xE2, 0x82, 0xAC, 0xF0, 0x9F, 0x98, 0x80
  };
  assert(utf8_view::sequence_length(valid, sizeof(valid), 0) == 1);
  assert(utf8_view::sequence_length(valid, sizeof(valid), 1) == 2);
  assert(utf8_view::sequence_length(valid, sizeof(valid), 3) == 3);
  assert(utf8_view::sequence_length(valid, sizeof(valid), 6) == 4);

  const u8 overlong2[] = {0xC0, 0x80};
  const u8 overlong3[] = {0xE0, 0x80, 0x80};
  const u8 surrogate[] = {0xED, 0xA0, 0x80};
  const u8 too_high[] = {0xF4, 0x90, 0x80, 0x80};
  const u8 truncated[] = {0xE2, 0x82};
  assert(utf8_view::sequence_length(overlong2, sizeof(overlong2), 0) == 1);
  assert(utf8_view::sequence_length(overlong3, sizeof(overlong3), 0) == 1);
  assert(utf8_view::sequence_length(surrogate, sizeof(surrogate), 0) == 1);
  assert(utf8_view::sequence_length(too_high, sizeof(too_high), 0) == 1);
  assert(utf8_view::sequence_length(truncated, sizeof(truncated), 0) == 1);

  const char mixed[] = "AКат";
  const u16 mixed_bytes = (u16) strlen(mixed);
  assert(utf8_view::codepoint_count(mixed) == 4);
  assert(utf8_view::byte_offset(mixed, 0) == 0);
  assert(utf8_view::byte_offset(mixed, 1) == 1);
  assert(utf8_view::byte_offset(mixed, 3) == 5);
  assert(utf8_view::byte_offset(mixed, 9) == mixed_bytes);
  assert(utf8_view::previous_offset((const u8*) mixed, mixed_bytes,
                                    mixed_bytes) == 5);
  assert(utf8_view::previous_offset((const u8*) mixed, mixed_bytes, 5) == 3);
}

void test_lcd1602_editor_viewport_uses_hidden_ddram(void) {
  static const char first[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd";
  static const char second[] = "abcdefghijklmnopqrstuvwxyz0123456789ABCD";
  const lcd1602_editor_viewport::RowSpan rows[] = {
    {first, (u16) strlen(first)},
    {second, (u16) strlen(second)},
  };

  lcd1602_editor_viewport::Layout layout = {};
  lcd1602_editor_viewport::build(rows, 0, 14, layout);
  assert(lcd1602_editor_viewport::first_visible_column(14) == 0);
  assert(layout.shift == 0);
  assert(layout.cursor_col == 15);
  assert(layout.cells[0][0] == '>' && layout.cells[0][1] == 'A');
  assert(layout.cells[1][0] == ' ' && layout.cells[1][1] == 'a');

  lcd1602_editor_viewport::build(rows, 0, 15, layout);
  assert(lcd1602_editor_viewport::first_visible_column(15) == 1);
  assert(layout.shift == 1);
  assert(layout.cursor_col == 15);
  assert(layout.cells[0][0] == 'd'); // следующий символ заранее ждёт за краем кольца
  assert(layout.cells[0][1] == '>');
  assert(layout.cells[0][2] == 'B');
  assert(layout.cells[1][1] == ' ' && layout.cells[1][2] == 'b');

  lcd1602_editor_viewport::build(rows, 1, 38, layout);
  assert(lcd1602_editor_viewport::first_visible_column(38) == 24);
  assert(layout.shift == 24);
  assert(layout.cells[0][24] == ' ' && layout.cells[0][25] == 'Y');
  assert(layout.cells[1][24] == '>' && layout.cells[1][25] == 'y');

  // Вторая половина 40-символьной DDRAM тоже используется: видимое окно
  // переходит через адрес 39 и продолжает чтение с адреса 0.
  lcd1602_editor_viewport::build(rows, 1, 39, layout);
  assert(lcd1602_editor_viewport::first_visible_column(39) == 25);
  assert(layout.shift == 25);
  assert(layout.cursor_col == 15);
  assert(layout.cells[0][25] == ' ' && layout.cells[0][26] == 'Z');
  assert(layout.cells[1][25] == '>' && layout.cells[1][26] == 'z');

  lcd1602_editor_viewport::build(rows, 1, 54, layout);
  assert(lcd1602_editor_viewport::first_visible_column(54) == 40);
  assert(layout.shift == 0);
  assert(layout.cells[0][0] == ' ' && layout.cells[1][0] == '>');

  const lcd1602_editor_viewport::ShiftPlan one_left =
      lcd1602_editor_viewport::shortest_shift(0, 1);
  assert(one_left.left && one_left.steps == 1);
  const lcd1602_editor_viewport::ShiftPlan one_right =
      lcd1602_editor_viewport::shortest_shift(1, 0);
  assert(!one_right.left && one_right.steps == 1);
  const lcd1602_editor_viewport::ShiftPlan wrap_left =
      lcd1602_editor_viewport::shortest_shift(24, 0);
  assert(wrap_left.left && wrap_left.steps == 16);
  const lcd1602_editor_viewport::ShiftPlan wrap_right =
      lcd1602_editor_viewport::shortest_shift(0, 24);
  assert(!wrap_right.left && wrap_right.steps == 16);
  const lcd1602_editor_viewport::ShiftPlan ring_left =
      lcd1602_editor_viewport::shortest_shift(39, 0);
  assert(ring_left.left && ring_left.steps == 1);
  const lcd1602_editor_viewport::ShiftPlan ring_right =
      lcd1602_editor_viewport::shortest_shift(0, 39);
  assert(!ring_right.left && ring_right.steps == 1);
}

void test_lcd1602_editor_viewport_pages_long_lines(void) {
  char long_line[1536];
  char second_line[1536];
  for(u16 index = 0; index < 1535; index++) {
    long_line[index] = (char) ('A' + index % 26);
    second_line[index] = (char) ('a' + index % 26);
  }
  long_line[1535] = 0;
  second_line[1535] = 0;
  const lcd1602_editor_viewport::RowSpan rows[] = {
    {long_line, 1535},
    {second_line, 1535},
  };

  lcd1602_editor_viewport::Layout layout = {};
  lcd1602_editor_viewport::build(rows, 0, 137, layout);
  assert(lcd1602_editor_viewport::first_visible_column(137) == 123);
  assert(layout.shift == 3 && layout.cursor_col == 15);
  assert(layout.cells[0][3] == '>');
  assert(layout.cells[0][4] == (u8) long_line[123]);
  assert(layout.cells[1][4] == (u8) second_line[123]);

  // Позиция курсора после последнего байта строки также должна помещаться:
  // в видимых знакоместах остаются последние 14 символов и сам курсор.
  lcd1602_editor_viewport::build(rows, 0, 1535, layout);
  assert(lcd1602_editor_viewport::first_visible_column(1535) == 1521);
  assert(layout.shift == 1 && layout.cursor_col == 15);
  assert(layout.cells[0][1] == '>');
  assert(layout.cells[0][2] == (u8) long_line[1521]);
  assert(layout.cells[0][15] == (u8) long_line[1534]);

  // Проверяется каждый допустимый столбец редактора, а не только первые
  // 40 адресов HD44780: видимое окно должно оставаться непрерывным при всех
  // оборотах кольцевой DDRAM.
  for(u16 active_column = 0; active_column <= 1535; active_column++) {
    lcd1602_editor_viewport::build(rows, 0, active_column, layout);
    const u16 view_left =
        lcd1602_editor_viewport::first_visible_column(active_column);
    assert(layout.shift == view_left %
                           lcd1602_editor_viewport::DDRAM_COLS);
    assert(layout.cells[0][layout.shift] == '>');
    assert(layout.cells[1][layout.shift] == ' ');
    for(u8 visible = 1; visible < lcd1602_editor_viewport::VISIBLE_COLS;
        visible++) {
      const u8 address = (u8) ((layout.shift + visible) %
                               lcd1602_editor_viewport::DDRAM_COLS);
      const u32 column = (u32) view_left + visible - 1;
      const u8 expected_first = column < 1535 ? (u8) long_line[column]
                                              : (u8) ' ';
      const u8 expected_second = column < 1535 ? (u8) second_line[column]
                                               : (u8) ' ';
      assert(layout.cells[0][address] == expected_first);
      assert(layout.cells[1][address] == expected_second);
    }

    if(active_column > lcd1602_editor_viewport::TEXT_COLS - 1) {
      lcd1602_editor_viewport::Layout previous = {};
      lcd1602_editor_viewport::build(rows, 0, (u16) (active_column - 1),
                                     previous);
      u8 changed_cells = 0;
      for(u8 row = 0; row < lcd1602_editor_viewport::ROWS; row++) {
        for(u8 address = 0; address < lcd1602_editor_viewport::DDRAM_COLS;
            address++) {
          if(previous.cells[row][address] != layout.cells[row][address]) {
            changed_cells++;
          }
        }
      }
      // Независимо от длины строки один шаг меняет не более двух физических
      // знакомест на строку: старый и новый адрес служебного маркера.
      assert(changed_cells <= 4);
    }
  }
}

struct Hd44780Model {
  u8 ddram[lcd1602_editor_viewport::ROWS]
          [lcd1602_editor_viewport::DDRAM_COLS];
  u8 shift;
  u8 address_row;
  u8 address_column;
  bool address_valid;
  u32 commands;
  u32 data_writes;
  u32 homes;
  u32 shifts_left;
  u32 shifts_right;

  Hd44780Model(void)
      : ddram{{0}}, shift(0), address_row(0), address_column(0),
        address_valid(false), commands(0), data_writes(0), homes(0),
        shifts_left(0), shifts_right(0) {
    memset(ddram, ' ', sizeof(ddram));
  }

  void reset_counters(void) {
    commands = 0;
    data_writes = 0;
    homes = 0;
    shifts_left = 0;
    shifts_right = 0;
  }

  void apply(lcd1602_editor_driver::BusWrite write) {
    if(write.data) {
      assert(address_valid);
      assert(address_row < lcd1602_editor_viewport::ROWS);
      assert(address_column < lcd1602_editor_viewport::DDRAM_COLS);
      ddram[address_row][address_column] = write.value;
      data_writes++;
      if(address_column + 1 < lcd1602_editor_viewport::DDRAM_COLS) {
        address_column++;
      } else {
        // Планировщик обязан начинать следующий физический участок новой
        // командой адреса, а не полагаться на переход AC между строками.
        address_valid = false;
      }
      return;
    }

    commands++;
    if(write.value == lcd1602_editor_driver::COMMAND_RETURN_HOME) {
      shift = 0;
      address_row = 0;
      address_column = 0;
      address_valid = true;
      homes++;
      return;
    }
    if(write.value == lcd1602_editor_driver::COMMAND_SHIFT_LEFT) {
      shift = (u8) ((shift + 1) % lcd1602_editor_viewport::DDRAM_COLS);
      shifts_left++;
      return;
    }
    if(write.value == lcd1602_editor_driver::COMMAND_SHIFT_RIGHT) {
      shift = shift == 0 ? (u8) (lcd1602_editor_viewport::DDRAM_COLS - 1)
                         : (u8) (shift - 1);
      shifts_right++;
      return;
    }

    assert((write.value & lcd1602_editor_driver::COMMAND_SET_DDRAM) != 0);
    const u8 address = (u8) (write.value & 0x7Fu);
    if(address < lcd1602_editor_viewport::DDRAM_COLS) {
      address_row = 0;
      address_column = address;
    } else {
      assert(address >= 0x40u &&
             address < 0x40u + lcd1602_editor_viewport::DDRAM_COLS);
      address_row = 1;
      address_column = (u8) (address - 0x40u);
    }
    address_valid = true;
  }
};

static void assert_model_matches_layout(
    const Hd44780Model& model,
    const lcd1602_editor_viewport::Layout& layout) {
  assert(model.shift == layout.shift);
  for(u8 row = 0; row < lcd1602_editor_viewport::ROWS; row++) {
    for(u8 address = 0;
        address < lcd1602_editor_viewport::DDRAM_COLS; address++) {
      assert(model.ddram[row][address] == layout.cells[row][address]);
    }
  }
}

static void test_lcd1602_editor_driver_all_shift_transitions(void) {
  u8 shadow[lcd1602_editor_viewport::ROWS]
           [lcd1602_editor_viewport::DDRAM_COLS];
  u8 desired[lcd1602_editor_viewport::ROWS]
            [lcd1602_editor_viewport::DDRAM_COLS];
  memset(shadow, ' ', sizeof(shadow));
  memset(desired, ' ', sizeof(desired));

  for(u8 current = 0; current < lcd1602_editor_viewport::DDRAM_COLS;
      current++) {
    for(u8 target = 0; target < lcd1602_editor_viewport::DDRAM_COLS;
        target++) {
      bool active = true;
      u8 current_shift = current;
      Hd44780Model model;
      model.shift = current;
      const auto emit = [&model](lcd1602_editor_driver::BusWrite write) {
        model.apply(write);
      };

      assert(lcd1602_editor_driver::render(
          shadow, active, current_shift, desired, target, emit));
      const lcd1602_editor_viewport::ShiftPlan expected =
          lcd1602_editor_viewport::shortest_shift(current, target);
      assert(active && current_shift == target && model.shift == target);
      assert(model.homes == 0 && model.data_writes == 0);
      assert(model.commands == expected.steps);
      assert(model.shifts_left == (expected.left ? expected.steps : 0));
      assert(model.shifts_right == (expected.left ? 0 : expected.steps));
    }
  }
}

void test_lcd1602_editor_driver_command_stream(void) {
  static_assert(lcd1602_editor_driver::COMMAND_RETURN_HOME == 0x02,
                "Unexpected Return Home command");
  static_assert(lcd1602_editor_driver::COMMAND_SHIFT_LEFT == 0x18,
                "Unexpected display-left command");
  static_assert(lcd1602_editor_driver::COMMAND_SHIFT_RIGHT == 0x1C,
                "Unexpected display-right command");
  assert(lcd1602_editor_driver::set_ddram_address_command(0, 39) == 0xA7);
  assert(lcd1602_editor_driver::set_ddram_address_command(1, 39) == 0xE7);

  for(u8 shift = 0; shift < lcd1602_editor_viewport::DDRAM_COLS; shift++) {
    for(u8 visible = 0; visible < lcd1602_editor_viewport::VISIBLE_COLS;
        visible++) {
      assert(lcd1602_editor_driver::physical_address(shift, visible) ==
             (shift + visible) % lcd1602_editor_viewport::DDRAM_COLS);
    }
  }

  char first_line[1536];
  char second_line[1536];
  for(u16 index = 0; index < 1535; index++) {
    first_line[index] = (char) ('A' + index % 26);
    second_line[index] = (char) ('a' + index % 26);
  }
  first_line[1535] = 0;
  second_line[1535] = 0;
  const lcd1602_editor_viewport::RowSpan rows[] = {
    {first_line, 1535},
    {second_line, 1535},
  };

  u8 shadow[lcd1602_editor_viewport::ROWS]
           [lcd1602_editor_viewport::DDRAM_COLS];
  memset(shadow, ' ', sizeof(shadow));
  bool active = false;
  u8 current_shift = 37; // при первом входе обязан быть сброшен Return Home
  Hd44780Model model;
  model.shift = 23;
  const auto emit = [&model](lcd1602_editor_driver::BusWrite write) {
    model.apply(write);
  };

  lcd1602_editor_viewport::Layout layout = {};
  for(u16 active_column = 0; active_column <= 1535; active_column++) {
    lcd1602_editor_viewport::build(rows, 0, active_column, layout);
    model.reset_counters();
    assert(lcd1602_editor_driver::render(shadow, active, current_shift,
                                         layout.cells, layout.shift, emit));
    assert(active && current_shift == layout.shift);
    assert_model_matches_layout(model, layout);
    if(active_column == 0) {
      assert(model.homes == 1);
    } else {
      assert(model.homes == 0);
    }
    if(active_column <= lcd1602_editor_viewport::TEXT_COLS - 1) {
      assert(model.shifts_left == 0 && model.shifts_right == 0);
    } else {
      assert(model.shifts_left == 1 && model.shifts_right == 0);
      assert(model.data_writes <= 4);
    }
  }

  // Тот же диапазон в обратную сторону обязан давать одну команду вправо,
  // включая аппаратный переход адреса 0 -> 39.
  for(i32 active_column = 1535; active_column >= 0; active_column--) {
    lcd1602_editor_viewport::build(rows, 0, (u16) active_column, layout);
    model.reset_counters();
    assert(lcd1602_editor_driver::render(shadow, active, current_shift,
                                         layout.cells, layout.shift, emit));
    assert_model_matches_layout(model, layout);
    if(active_column < 1535 &&
       active_column < (i32) lcd1602_editor_viewport::TEXT_COLS - 1) {
      assert(model.shifts_left == 0 && model.shifts_right == 0);
    } else if(active_column < 1535) {
      assert(model.shifts_left == 0 && model.shifts_right == 1);
      assert(model.data_writes <= 4);
    }
  }

  // Смена активной строки при том же горизонтальном окне меняет только два
  // маркера и не должна двигать дисплей.
  lcd1602_editor_viewport::build(rows, 0, 137, layout);
  assert(lcd1602_editor_driver::render(shadow, active, current_shift,
                                       layout.cells, layout.shift, emit));
  lcd1602_editor_viewport::build(rows, 1, 137, layout);
  model.reset_counters();
  assert(lcd1602_editor_driver::render(shadow, active, current_shift,
                                       layout.cells, layout.shift, emit));
  assert(model.data_writes == 2);
  assert(model.shifts_left == 0 && model.shifts_right == 0);
  assert_model_matches_layout(model, layout);

  // Изменение одного видимого символа не должно перерисовывать всю DDRAM.
  second_line[130] = '#';
  lcd1602_editor_viewport::build(rows, 1, 137, layout);
  model.reset_counters();
  assert(lcd1602_editor_driver::render(shadow, active, current_shift,
                                       layout.cells, layout.shift, emit));
  assert(model.data_writes == 1 && model.commands == 1);
  assert_model_matches_layout(model, layout);

  model.reset_counters();
  lcd1602_editor_driver::end(active, current_shift, emit);
  assert(!active && current_shift == 0 && model.shift == 0);
  assert(model.homes == 1 && model.commands == 1 && model.data_writes == 0);
  lcd1602_editor_driver::end(active, current_shift, emit);
  assert(model.commands == 1); // повторный выход ничего не отправляет

  // Повторный вход использует сохранённое зеркало DDRAM: Home + кратчайший
  // shift без повторной передачи 80 байт.
  model.reset_counters();
  assert(lcd1602_editor_driver::render(shadow, active, current_shift,
                                       layout.cells, layout.shift, emit));
  assert(model.homes == 1 && model.data_writes == 0);
  assert(model.shifts_left == layout.shift && model.shifts_right == 0);
  assert_model_matches_layout(model, layout);

  model.reset_counters();
  const bool was_active = active;
  const u8 old_shift = current_shift;
  assert(!lcd1602_editor_driver::render(
      shadow, active, current_shift, layout.cells,
      lcd1602_editor_viewport::DDRAM_COLS, emit));
  assert(active == was_active && current_shift == old_shift);
  assert(model.commands == 0 && model.data_writes == 0);
}

} // namespace

int main(void) {
  test_init_terminates_untrusted_buffer();
  test_edit_primitives_reject_corrupt_state();
  test_sms_failure_does_not_arm_stale_state();
  test_hook_output_is_sanitized();
  test_sms_deadline_wraparound();
  test_cx_backspaces_and_f_left_is_not_backspace();
  test_f_cx_clears_only_current_line_then_removes_it();
  test_clear_current_line_removes_empty_edge_lines_and_crlf();
  test_single_line_cx_backspaces_and_clears();
  test_utf8_validation();
  test_lcd1602_editor_viewport_uses_hidden_ddram();
  test_lcd1602_editor_viewport_pages_long_lines();
  test_lcd1602_editor_driver_all_shift_transitions();
  test_lcd1602_editor_driver_command_stream();
  printf("text_editor_self_test: ok\n");
  return 0;
}
