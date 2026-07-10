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

} // namespace

int main(void) {
  static_assert(sizeof(TEXT) == startup_splash::COLS + 1, "Test text must fill one row");
  static_assert(startup_splash::FRAME_MS * startup_splash::FINAL_FRAME == startup_splash::ANIMATION_MS,
    "Animation duration must contain whole frames");

  test_logo_frame();
  test_first_animation_frame();
  test_halfway_frame();
  test_final_and_clamped_frames();
  printf("startup_splash_self_test: ok\n");
  return 0;
}
