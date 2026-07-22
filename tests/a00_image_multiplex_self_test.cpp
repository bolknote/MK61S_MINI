#include "a00_image_multiplex.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>

namespace {

static void set_pixel(u8 viewport[a00_image_mux::VIEW_BYTES], u8 x, u8 y) {
  viewport[y * a00_image_mux::VIEW_STRIDE + x / 8] |=
    (u8) (0x80U >> (x & 7U));
}

static u64 glyph_mask(const u8 rows[a00_image_mux::GLYPH_ROWS]) {
  u64 mask = 0;
  for(u8 row = 0; row < a00_image_mux::CELL_HEIGHT; row++) {
    mask |= (u64) (rows[row] & 0x1FU) <<
            (row * a00_image_mux::CELL_WIDTH);
  }
  return mask;
}

static u8 bit_count(u64 mask) {
  u8 count = 0;
  while(mask != 0) {
    mask &= mask - 1U;
    count++;
  }
  return count;
}

static u8 verify_exact_sequence(
    const u8 viewport[a00_image_mux::VIEW_BYTES]) {
  u64 targets[a00_image_mux::CELL_COUNT] = {};
  u8 rows[a00_image_mux::GLYPH_ROWS];
  u16 target_pixels = 0;
  for(u8 cell = 0; cell < a00_image_mux::CELL_COUNT; cell++) {
    assert(a00_image_mux::glyph_for_cell(viewport, cell, rows));
    targets[cell] = glyph_mask(rows);
    target_pixels += bit_count(targets[cell]);
  }

  a00_image_mux::FrameSequence sequence = {};
  assert(a00_image_mux::build_diffusion_sequence(viewport, sequence));
  assert(sequence.frame_count >= 1 &&
         sequence.frame_count <= a00_image_mux::PHASE_COUNT);
  u64 shown[a00_image_mux::CELL_COUNT] = {};
  u16 shown_pixels = 0;
  u8 most_active_cells = 0;
  for(u8 phase = 0; phase < sequence.frame_count; phase++) {
    u8 active_cells = 0;
    const a00_image_mux::TemporalFrame& frame = sequence.frames[phase];
    for(u8 slot = 0; slot < a00_image_mux::SLOT_COUNT; slot++) {
      assert(frame.glyphs[slot][7] == 0);
      for(u8 row = 0; row < 7; row++) assert(frame.glyphs[slot][row] <= 0x1F);
    }
    for(u8 cell = 0; cell < a00_image_mux::CELL_COUNT; cell++) {
      const u8 code = frame.cells[cell];
      assert(code == a00_image_mux::BLANK_CELL_CODE ||
             code < a00_image_mux::SLOT_COUNT);
      const u64 mask = code < a00_image_mux::SLOT_COUNT
                     ? glyph_mask(frame.glyphs[code]) : 0;
      assert((mask & ~targets[cell]) == 0);
      assert((mask & shown[cell]) == 0);
      if(mask != 0) active_cells++;
      shown[cell] |= mask;
      shown_pixels += bit_count(mask);
    }
    if(active_cells > most_active_cells) most_active_cells = active_cells;
  }
  for(u8 cell = 0; cell < a00_image_mux::CELL_COUNT; cell++) {
    assert(shown[cell] == targets[cell]);
  }
  assert(shown_pixels == target_pixels);
  return most_active_cells;
}

static void test_exact_cgram_extraction(void) {
  u8 viewport[a00_image_mux::VIEW_BYTES] = {};
  const u8 cell = 17;
  const u8 left = (u8) ((cell % a00_image_mux::COLS) *
                        a00_image_mux::CELL_WIDTH);
  const u8 top = (u8) ((cell / a00_image_mux::COLS) *
                       a00_image_mux::CELL_HEIGHT);
  set_pixel(viewport, left, top);
  set_pixel(viewport, (u8) (left + 4), (u8) (top + 1));
  set_pixel(viewport, (u8) (left + 1), (u8) (top + 2));
  set_pixel(viewport, (u8) (left + 3), (u8) (top + 2));

  u8 rows[a00_image_mux::GLYPH_ROWS];
  memset(rows, 0xFF, sizeof(rows));
  assert(a00_image_mux::glyph_for_cell(viewport, cell, rows));
  assert(rows[0] == 0x10);
  assert(rows[1] == 0x01);
  assert(rows[2] == 0x0A);
  for(u8 row = 3; row < a00_image_mux::GLYPH_ROWS; row++) {
    assert(rows[row] == 0);
  }

  assert(!a00_image_mux::glyph_for_cell(NULL, cell, rows));
  assert(!a00_image_mux::glyph_for_cell(viewport,
                                        a00_image_mux::CELL_COUNT, rows));
  assert(!a00_image_mux::glyph_for_cell(viewport, cell, NULL));
}

static void test_phase_rate_controls(void) {
  assert(a00_image_mux::faster_rate(4) == 3);
  assert(a00_image_mux::faster_rate(1) == 1);
  assert(a00_image_mux::faster_rate(0) == 1);
  assert(a00_image_mux::slower_rate(4) == 5);
  assert(a00_image_mux::slower_rate(16) == 16);
  assert(a00_image_mux::slower_rate(0xFF) == 16);

  assert(a00_image_mux::phase_hold_us(4000, 1) == 0);
  assert(a00_image_mux::phase_hold_us(4000, 4) == 12000);
  assert(a00_image_mux::phase_hold_us(4000, 16) == 60000);
  assert(a00_image_mux::phase_hold_us(4000, 0xFF) == 60000);
  assert(a00_image_mux::phase_hold_us(0xFFFFFFFFU, 4) == 0xFFFFFFFFU);
}

static void test_temporal_diffusion_is_exact_and_uniform(void) {
  u8 viewport[a00_image_mux::VIEW_BYTES] = {};
  for(u8 cell = 0; cell < a00_image_mux::CELL_COUNT; cell++) {
    const u8 left = (u8) ((cell % a00_image_mux::COLS) *
                          a00_image_mux::CELL_WIDTH);
    const u8 top = (u8) ((cell / a00_image_mux::COLS) *
                         a00_image_mux::CELL_HEIGHT);
    set_pixel(viewport, (u8) (left + cell % 4), top);
    if(cell >= 4) {
      set_pixel(viewport, (u8) (left + (cell * 3U) % 5U),
                (u8) (top + 1U + cell % 6U));
    }
  }

  assert(verify_exact_sequence(viewport) > a00_image_mux::SLOT_COUNT);
}

static void test_random_viewports_are_exact(void) {
  u32 random = 0x61C5A00U;
  for(u16 sample = 0; sample < 512; sample++) {
    u8 viewport[a00_image_mux::VIEW_BYTES];
    for(usize i = 0; i < sizeof(viewport); i++) {
      random ^= random << 13;
      random ^= random >> 17;
      random ^= random << 5;
      viewport[i] = (u8) random;
    }
    (void) verify_exact_sequence(viewport);
  }
}

static void test_blank_sequence(void) {
  a00_image_mux::FrameSequence blank_sequence = {};
  u8 blank_viewport[a00_image_mux::VIEW_BYTES] = {};
  assert(a00_image_mux::build_diffusion_sequence(blank_viewport,
                                                  blank_sequence));
  assert(blank_sequence.frame_count == 1);
  for(u8 cell = 0; cell < a00_image_mux::CELL_COUNT; cell++) {
    assert(blank_sequence.frames[0].cells[cell] ==
           a00_image_mux::BLANK_CELL_CODE);
  }
}

} // безымянное пространство имён

int main(void) {
  test_exact_cgram_extraction();
  test_phase_rate_controls();
  test_temporal_diffusion_is_exact_and_uniform();
  test_random_viewports_are_exact();
  test_blank_sequence();
  std::printf("a00_image_multiplex_self_test: ok\n");
  return 0;
}
