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

static void putLe16(u8* target, u16 value) {
  target[0] = (u8) value;
  target[1] = (u8) (value >> 8);
}

static prepared_font::Face narrowFont(u8 (&data)[28]) {
  memset(data, 0, sizeof(data));
  memcpy(data, "PFK1", 4);
  data[4] = prepared_font::FLAG_MONOSPACED;
  data[5] = 3;
  data[6] = 5;
  data[7] = 4;
  data[8] = 1;
  data[9] = 1;
  putLe16(data + 10, 1);
  putLe16(data + 12, 23);
  putLe16(data + 14, 23);
  putLe16(data + 16, sizeof(data));
  putLe16(data + 20, 'A');
  data[22] = 0;
  data[23] = 0x40;
  data[24] = 0xA0;
  data[25] = 0xE0;
  data[26] = 0xA0;
  data[27] = 0xA0;
  putLe16(data + prepared_font::CRC_OFFSET,
          prepared_font::checksum(data, sizeof(data)));
  prepared_font::Face face;
  assert(face.open(data, sizeof(data)));
  return face;
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
  surface.writeCodepoint(0x0411); // Кириллическая «Б».
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

static void test_wide_external_font_layout(void) {
  u8 font_data[28] = {};
  prepared_font::Face font = narrowFont(font_data);
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin(usb_screen::profile3x5());
  surface.setFont(&font);
  surface.setTextLayout(usb_screen::profile3x5(), 40);
  assert(surface.cols() == 40);
  assert(surface.rows() == 10);
  surface.setCursor(39, 0);
  surface.writeByte('A');
  surface.flush(0);
  bool last_cell_visible = false;
  for(u16 x = 158; x <= 160; ++x) {
    for(u8 y = 2; y <= 6; ++y) {
      last_cell_visible = last_cell_visible || pixel(surface, x, y);
    }
  }
  assert(last_cell_visible);
  assert(!pixel(surface, 191, 0));
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

static void test_backend_switch_seed_and_session_reset(void) {
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  const u8 checker[8] = {
    0x15, 0x0A, 0x15, 0x0A, 0x15, 0x0A, 0x15, 0x0A,
  };

  surface.begin();
  surface.createChar(5, checker);
  surface.end();
  surface.begin();
  u8 copied[8] = {};
  assert(!surface.copyCustomChar(5, copied));

  text_screen::Grid source;
  source.reset(6);
  source.setCursor(0, 0);
  source.writeCodepoint('A');
  source.writeByte(3);
  source.setCursor(4, 2);
  u8 custom_glyphs[usb_screen::Surface::CUSTOM_GLYPHS][8] = {};
  bool custom_valid[usb_screen::Surface::CUSTOM_GLYPHS] = {};
  memcpy(custom_glyphs[3], checker, sizeof(checker));
  custom_valid[3] = true;

  surface.seedText(source, custom_glyphs, custom_valid, true, true, 100);
  surface.flush(100);
  u16 value = 0;
  bool custom = false;
  assert(surface.readCell(0, 0, value, custom));
  assert(value == 'A' && !custom);
  assert(surface.readCell(1, 0, value, custom));
  assert(value == 3 && custom);
  assert(surface.copyCustomChar(3, copied));
  assert(memcmp(copied, checker, sizeof(copied)) == 0);
  assert(surface.cursorX() == 4 && surface.cursorY() == 2);
  assert(surface.cursorUnderline());
  assert(surface.cursorBlink());
  assert(ink(surface) > 20);
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
  u32 copied_overlay[usb_screen::Surface::OVERLAY_MAX_HEIGHT] = {};
  u8 copied_width = 0;
  u8 copied_height = 0;
  u8 copied_border = 0;
  assert(surface.copyTopRightOverlay(copied_overlay, copied_width,
                                     copied_height, copied_border));
  assert(copied_width == 3 && copied_height == 2 && copied_border == 1);
  assert(copied_overlay[0] == overlay[0] &&
         copied_overlay[1] == overlay[1]);

  // Clearing/redrawing the calculator text surface must not erase the
  // independently-owned clock overlay.  This is also how the physical
  // UC1609 backend behaves during the redraw that follows USB ATTACH.
  surface.clear();
  surface.flush(3);
  assert(surface.copyTopRightOverlay(copied_overlay, copied_width,
                                     copied_height, copied_border));
  assert(copied_width == 3 && copied_height == 2 && copied_border == 1);
  assert(copied_overlay[0] == overlay[0] &&
         copied_overlay[1] == overlay[1]);
  assert(pixel(surface, 188, 1));
  assert(!pixel(surface, 189, 1));
  assert(pixel(surface, 190, 1));
  assert(pixel(surface, 189, 2));

  surface.hideTopRightOverlay();
  assert(!surface.copyTopRightOverlay(copied_overlay, copied_width,
                                      copied_height, copied_border));
  assert(copied_width == 0 && copied_height == 0 && copied_border == 0);
  surface.flush(4);
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

static void test_noop_updates_do_not_render(void) {
  u8 framebuffer[usb_screen::FRAME_BYTES] = {};
  usb_screen::Surface surface(framebuffer);
  surface.begin();
  surface.flush(0);

  u32 revision = surface.revision();
  surface.setCursor(0, 0);
  surface.writeByte(' ');
  surface.flush(1);
  assert(surface.revision() == revision);

  surface.setCursor(0, 0);
  surface.writeByte('A');
  surface.flush(2);
  revision = surface.revision();
  surface.setCursor(0, 0);
  surface.writeByte('A');
  surface.flush(3);
  assert(surface.revision() == revision);

  const u8 glyph[8] = {0x1F, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1F};
  surface.createChar(2, glyph); // Пока слот не выведен, кадр не меняется.
  surface.flush(4);
  assert(surface.revision() == revision);
  surface.createChar(2, glyph);
  surface.flush(5);
  assert(surface.revision() == revision);
  surface.clearCustomChar(2);
  surface.flush(6);
  assert(surface.revision() == revision);
  surface.clearCustomChar(2);
  surface.flush(7);
  assert(surface.revision() == revision);

  const u32 overlay[2] = {0b101, 0b010};
  assert(surface.showTopRightOverlay(overlay, 3, 2, 1));
  surface.flush(8);
  revision = surface.revision();
  assert(surface.showTopRightOverlay(overlay, 3, 2, 1));
  surface.flush(9);
  assert(surface.revision() == revision);
}

} // безымянное пространство имён

int main(void) {
  test_profiles();
  test_text_unicode_and_cursor();
  test_wide_external_font_layout();
  test_custom_glyph();
  test_backend_switch_seed_and_session_reset();
  test_fullscreen_and_overlay();
  test_update_batching();
  test_noop_updates_do_not_render();
  printf("usb_screen_surface_self_test: ok\n");
  return 0;
}
