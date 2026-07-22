#include "usb_screen_surface.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

static bool pixel(const usb_screen::Surface& surface, u16 x, u8 y) {
  assert(x < usb_screen::WIDTH && y < usb_screen::HEIGHT);
  const u8 value = surface.framebuffer()[
    (usize) (y / usb_screen::PAGE_HEIGHT) * usb_screen::WIDTH + x];
  return (value & ((u8) 1U << (y & 7))) != 0;
}

static usize ink(const usb_screen::Surface& surface) {
  usize count = 0;
  for(u8 y = 0; y < usb_screen::HEIGHT; y++) {
    for(u16 x = 0; x < usb_screen::WIDTH; x++) {
      if(pixel(surface, x, y)) count++;
    }
  }
  return count;
}

static void test_profiles(void) {
  const usb_screen::TextProfile huge =
    usb_screen::normalizeProfile({255, 255, 255, 255});
  assert(huge.rows == 10);
  assert(huge.glyph_width == 10);
  assert(huge.glyph_height == 6);
  assert(huge.line_gap == 0);

  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin(usb_screen::profile5x8());
  surface.flush(0);
  assert(surface.active());
  assert(surface.rows() == 6);
  assert(surface.revision() >= 2);
  assert(ink(surface) == 0);

  surface.setTextProfile(usb_screen::profile3x5());
  surface.flush(1);
  assert(surface.rows() == 10);
}

static void test_text_unicode_and_cursor(void) {
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin();
  surface.setCursor(0, 0);
  surface.writeByte('A');
  surface.writeCodepoint(0x0411); // Cyrillic Be.
  surface.flush(0);
  assert(ink(surface) > 10);
  assert(pixel(surface, 5, 0) || pixel(surface, 6, 0) ||
         pixel(surface, 7, 0));

  const u32 before = surface.revision();
  surface.setCursor(2, 0);
  surface.cursorOn();
  assert(surface.cursorX() == 2 && surface.cursorY() == 0);
  assert(surface.cursorUnderline());
  assert(!surface.cursorBlink());
  surface.flush(1);
  assert(surface.revision() > before);
  bool underline = false;
  for(u16 x = 24; x < 36; x++) underline = underline || pixel(surface, x, 7);
  assert(underline);

  surface.blinkOn(10);
  assert(surface.cursorBlink());
  surface.flush(10);
  const u32 blink_before = surface.revision();
  surface.flush(510);
  assert(surface.revision() > blink_before);
}

static void test_custom_glyph(void) {
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin();
  const u8 checker[8] = {
    0x15, 0x0A, 0x15, 0x0A, 0x15, 0x0A, 0x15, 0x0A,
  };
  surface.createChar(3, checker);
  surface.writeByte(3);
  surface.flush(0);
  u16 cell = 0;
  bool custom = false;
  assert(surface.readCell(0, 0, cell, custom));
  assert(cell == 3 && custom);
  u8 copied[8] = {};
  assert(surface.copyCustomChar(3, copied));
  assert(memcmp(copied, checker, sizeof(copied)) == 0);
  assert(ink(surface) == 20);
}

static void test_fullscreen_and_overlay(void) {
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin();
  u8 bitmap[usb_screen::FRAME_BYTES] = {};
  bitmap[0] = 0x81;
  bitmap[usb_screen::WIDTH * 7 + 191] = 0x80;
  assert(surface.beginFullscreenBitmap());
  assert(surface.showFullscreenBitmap(bitmap, sizeof(bitmap)));
  assert(pixel(surface, 0, 0));
  assert(pixel(surface, 0, 7));
  assert(pixel(surface, 191, 63));
  surface.endFullscreenBitmap();
  surface.flush(1);
  assert(!pixel(surface, 191, 63));

  const u32 overlay[2] = {0b101, 0b010};
  assert(surface.showTopRightOverlay(overlay, 3, 2, 1));
  surface.flush(2);
  assert(pixel(surface, 188, 1));
  assert(!pixel(surface, 189, 1));
  assert(pixel(surface, 190, 1));
  assert(pixel(surface, 189, 2));
  surface.hideTopRightOverlay();
  surface.flush(3);
  assert(!pixel(surface, 188, 1));
}

static void test_update_batching(void) {
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin();
  surface.flush(0);
  const u32 before = surface.revision();
  surface.beginUpdate();
  surface.writeByte('1');
  surface.writeByte('2');
  surface.flush(1);
  assert(surface.revision() == before);
  surface.endUpdate();
  surface.flush(2);
  assert(surface.revision() == before + 1);
}

} // namespace

int main(void) {
  test_profiles();
  test_text_unicode_and_cursor();
  test_custom_glyph();
  test_fullscreen_and_overlay();
  test_update_batching();
  printf("usb_screen_surface_self_test: ok\n");
  return 0;
}
