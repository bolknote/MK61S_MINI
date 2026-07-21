#include "startup_splash.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

static constexpr char TEXT[] = "0123456789ABCDEF";
static constexpr u8 LOGO[startup_splash::COLS] = {
  0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
  0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F
};

void read_lcd1602_window(
    const u8 ddram[lcd1602_shifted_viewport::DDRAM_COLS], u8 shift,
    u8 out[startup_splash::COLS]) {
  for(u8 col = 0; col < startup_splash::COLS; col++) {
    const u8 address = lcd1602_shifted_viewport::physical_address(shift, col);
    out[col] = ddram[address];
  }
}

struct CommandSummary {
  u32 homes = 0;
  u32 shifts_left = 0;
  u32 shifts_right = 0;
  u32 data_writes = 0;

  void reset(void) {
    homes = 0;
    shifts_left = 0;
    shifts_right = 0;
    data_writes = 0;
  }

  void add(lcd1602_shifted_viewport::BusWrite write) {
    if(write.data) {
      data_writes++;
    } else if(write.value ==
              lcd1602_shifted_viewport::COMMAND_RETURN_HOME) {
      homes++;
    } else if(write.value ==
              lcd1602_shifted_viewport::COMMAND_SHIFT_LEFT) {
      shifts_left++;
    } else if(write.value ==
              lcd1602_shifted_viewport::COMMAND_SHIFT_RIGHT) {
      shifts_right++;
    }
  }
};

void test_logo_frame(void) {
  u8 row[startup_splash::COLS] = {};
  startup_splash::composeRow(TEXT, LOGO, 0, row);
  assert(memcmp(row, LOGO, sizeof(row)) == 0);
}

void test_first_animation_frame(void) {
  u8 row[startup_splash::COLS] = {};
  startup_splash::composeRow(TEXT, LOGO, 1, row);
  assert(row[0] == 'F');
  assert(memcmp(row + 1, LOGO, startup_splash::COLS - 1) == 0);
}

void test_halfway_frame(void) {
  u8 row[startup_splash::COLS] = {};
  startup_splash::composeRow(TEXT, LOGO, 8, row);
  assert(memcmp(row, "89ABCDEF", 8) == 0);
  assert(memcmp(row + 8, LOGO, 8) == 0);
}

void test_final_and_clamped_frames(void) {
  u8 row[startup_splash::COLS] = {};
  startup_splash::composeRow(TEXT, LOGO, startup_splash::FINAL_FRAME, row);
  assert(memcmp(row, TEXT, startup_splash::COLS) == 0);

  memset(row, 0, sizeof(row));
  startup_splash::composeRow(TEXT, LOGO, 0xFF, row);
  assert(memcmp(row, TEXT, startup_splash::COLS) == 0);
}

void test_lcd1602_hidden_ddram_matches_every_frame(void) {
  u8 ddram[lcd1602_shifted_viewport::DDRAM_COLS] = {};
  startup_splash::composeLcd1602DdramRow(TEXT, LOGO, ddram);

  for(u8 address = startup_splash::COLS;
      address < startup_splash::LCD1602_TEXT_START; address++) {
    assert(ddram[address] == ' ');
  }

  u8 previous_shift = startup_splash::lcd1602ShiftForFrame(0);
  for(u8 frame = 0; frame <= startup_splash::FINAL_FRAME; frame++) {
    u8 expected[startup_splash::COLS] = {};
    u8 actual[startup_splash::COLS] = {};
    startup_splash::composeRow(TEXT, LOGO, frame, expected);
    const u8 shift = startup_splash::lcd1602ShiftForFrame(frame);
    read_lcd1602_window(ddram, shift, actual);
    assert(memcmp(actual, expected, sizeof(actual)) == 0);

    if(frame != 0) {
      const lcd1602_shifted_viewport::ShiftPlan plan =
          lcd1602_shifted_viewport::shortest_shift(previous_shift, shift);
      assert(plan.steps == 1 && !plan.left);
    }
    previous_shift = shift;
  }

  assert(startup_splash::lcd1602ShiftForFrame(0xFF) ==
         startup_splash::LCD1602_TEXT_START);
}

void test_lcd1602_home_is_restored_without_changing_final_frame(void) {
  u8 ddram[lcd1602_shifted_viewport::DDRAM_COLS] = {};
  u8 visible[startup_splash::COLS] = {};
  startup_splash::composeLcd1602DdramRow(TEXT, LOGO, ddram);
  const u8 final_shift = startup_splash::lcd1602ShiftForFrame(
      startup_splash::FINAL_FRAME);

  read_lcd1602_window(ddram, final_shift, visible);
  assert(memcmp(visible, TEXT, sizeof(visible)) == 0);

  startup_splash::stabilizeLcd1602DdramRow(TEXT, ddram);
  memset(visible, 0, sizeof(visible));
  read_lcd1602_window(ddram, final_shift, visible);
  assert(memcmp(visible, TEXT, sizeof(visible)) == 0);

  memset(visible, 0, sizeof(visible));
  read_lcd1602_window(ddram, 0, visible);
  assert(memcmp(visible, TEXT, sizeof(visible)) == 0);
}

void test_lcd1602_cleanup_after_every_possible_escape_frame(void) {
  for(u8 stop_frame = 0; stop_frame <= startup_splash::FINAL_FRAME;
      stop_frame++) {
    u8 desired[lcd1602_shifted_viewport::ROWS]
              [lcd1602_shifted_viewport::DDRAM_COLS] = {};
    u8 shadow[lcd1602_shifted_viewport::ROWS]
             [lcd1602_shifted_viewport::DDRAM_COLS];
    memset(shadow, ' ', sizeof(shadow));
    for(u8 row = 0; row < lcd1602_shifted_viewport::ROWS; row++) {
      startup_splash::composeLcd1602DdramRow(TEXT, LOGO, desired[row]);
    }

    bool active = false;
    u8 current_shift = 37;
    CommandSummary commands;
    const auto emit = [&commands](lcd1602_shifted_viewport::BusWrite write) {
      commands.add(write);
    };

    assert(lcd1602_shifted_viewport::render(
        shadow, active, current_shift, desired,
        startup_splash::lcd1602ShiftForFrame(0), emit));
    assert(active && current_shift == 0 && commands.homes == 1);

    for(u8 frame = 1; frame <= stop_frame; frame++) {
      commands.reset();
      assert(lcd1602_shifted_viewport::render(
          shadow, active, current_shift, desired,
          startup_splash::lcd1602ShiftForFrame(frame), emit));
      assert(commands.data_writes == 0);
      assert(commands.shifts_left == 0 && commands.shifts_right == 1);
    }

    for(u8 row = 0; row < lcd1602_shifted_viewport::ROWS; row++) {
      startup_splash::stabilizeLcd1602DdramRow(TEXT, desired[row]);
    }
    commands.reset();
    assert(lcd1602_shifted_viewport::render(
        shadow, active, current_shift, desired,
        startup_splash::lcd1602ShiftForFrame(stop_frame), emit));
    lcd1602_shifted_viewport::end(active, current_shift, emit);
    assert(!active && current_shift == 0);
    assert(commands.homes == 1);
    assert(commands.shifts_left == 0 && commands.shifts_right == 0);
    for(u8 row = 0; row < lcd1602_shifted_viewport::ROWS; row++) {
      assert(memcmp(shadow[row], TEXT, startup_splash::COLS) == 0);
    }
  }
}

void test_boot_escape_policy(void) {
  assert(startup_splash::escapeMaySkip(
      startup_splash::escapePolicyForBoot(false)));
  assert(!startup_splash::escapeMaySkip(
      startup_splash::escapePolicyForBoot(true)));
}

} // namespace

int main(void) {
  static_assert(sizeof(TEXT) == startup_splash::COLS + 1, "Test text must fill one row");
  static_assert(startup_splash::FRAME_MS * startup_splash::FINAL_FRAME == startup_splash::ANIMATION_MS,
    "Animation duration must contain whole frames");
  static_assert(startup_splash::FINAL_HOLD_MS > startup_splash::FRAME_MS,
    "Completed splash must remain visible longer than an animation frame");

  test_logo_frame();
  test_first_animation_frame();
  test_halfway_frame();
  test_final_and_clamped_frames();
  test_lcd1602_hidden_ddram_matches_every_frame();
  test_lcd1602_home_is_restored_without_changing_final_frame();
  test_lcd1602_cleanup_after_every_possible_escape_frame();
  test_boot_escape_policy();
  printf("startup_splash_self_test: ok\n");
  return 0;
}
