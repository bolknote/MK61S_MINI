#include "a00_image_multiplex.hpp"

#include <string.h>

namespace a00_image_mux {
namespace {

static constexpr u8 VISIBLE_GLYPH_ROWS = 7;
static u64 glyph_mask(const u8 rows[GLYPH_ROWS]) {
  u64 mask = 0;
  for(u8 row = 0; row < VISIBLE_GLYPH_ROWS; row++) {
    mask |= (u64) (rows[row] & 0x1FU) << (row * CELL_WIDTH);
  }
  return mask;
}

static void mask_to_glyph(u64 mask, u8 rows[GLYPH_ROWS]) {
  for(u8 row = 0; row < VISIBLE_GLYPH_ROWS; row++) {
    rows[row] = (u8) ((mask >> (row * CELL_WIDTH)) & 0x1FU);
  }
  rows[VISIBLE_GLYPH_ROWS] = 0;
}

static u8 bit_count(u64 mask) {
  u8 count = 0;
  while(mask != 0) {
    mask &= mask - 1U;
    count++;
  }
  return count;
}

} // namespace

bool glyph_for_cell(const u8 viewport[VIEW_BYTES], u8 cell,
                    u8 rows[GLYPH_ROWS]) {
  if(viewport == NULL || rows == NULL || cell >= CELL_COUNT) return false;
  memset(rows, 0, GLYPH_ROWS);

  const u8 cell_x = (u8) ((cell % COLS) * CELL_WIDTH);
  const u8 cell_y = (u8) ((cell / COLS) * CELL_HEIGHT);
  for(u8 y = 0; y < CELL_HEIGHT; y++) {
    u8 row = 0;
    for(u8 x = 0; x < CELL_WIDTH; x++) {
      const u16 pixel_x = (u16) cell_x + x;
      const u16 pixel_y = (u16) cell_y + y;
      const u8 value = viewport[pixel_y * VIEW_STRIDE + pixel_x / 8];
      if((value & (u8) (0x80U >> (pixel_x & 7U))) != 0) {
        row |= (u8) (1U << (CELL_WIDTH - 1U - x));
      }
    }
    rows[y] = row;
  }
  return true;
}

namespace {

static void clear_frame(TemporalFrame& frame) {
  memset(frame.glyphs, 0, sizeof(frame.glyphs));
  memset(frame.cells, BLANK_CELL_CODE, sizeof(frame.cells));
}

static bool append_diffusion(const u8 viewport[VIEW_BYTES],
                             FrameSequence& sequence) {
  const u8 first_frame = sequence.frame_count;
  u64 residuals[CELL_COUNT];
  u8 rows[GLYPH_ROWS];
  for(u8 cell = 0; cell < CELL_COUNT; cell++) {
    if(!glyph_for_cell(viewport, cell, rows)) return false;
    residuals[cell] = glyph_mask(rows);
  }

  for(u8 phase = 0; phase < PHASE_COUNT; phase++) {
    bool has_residual = false;
    for(u8 cell = 0; cell < CELL_COUNT; cell++) {
      if(residuals[cell] != 0) {
        has_residual = true;
        break;
      }
    }
    if(!has_residual) break;
    if(sequence.frame_count >= MAX_SEQUENCE_FRAMES) return false;

    TemporalFrame& frame = sequence.frames[sequence.frame_count];
    clear_frame(frame);
    u8 anchors[SLOT_COUNT];
    bool selected_cells[CELL_COUNT] = {};
    u8 reusable_pixels[CELL_COUNT] = {};
    u8 selected_count = 0;

    while(selected_count < SLOT_COUNT) {
      u8 best_anchor = NO_CELL;
      u16 best_gain = 0;
      u8 best_reach = 0;
      u8 best_size = 0;
      for(u8 candidate_cell = 0; candidate_cell < CELL_COUNT;
          candidate_cell++) {
        if(selected_cells[candidate_cell] || residuals[candidate_cell] == 0) {
          continue;
        }
        const u64 candidate = residuals[candidate_cell];
        bool duplicate = false;
        for(u8 slot = 0; slot < selected_count; slot++) {
          if(candidate == glyph_mask(frame.glyphs[slot])) {
            duplicate = true;
            break;
          }
        }
        if(duplicate) continue;

        const u8 candidate_size = bit_count(candidate);
        u16 gain = 0;
        u8 reach = 0;
        for(u8 cell = 0; cell < CELL_COUNT; cell++) {
          if((candidate & ~residuals[cell]) != 0) continue;
          reach++;
          if(candidate_size > reusable_pixels[cell]) {
            gain += (u16) (candidate_size - reusable_pixels[cell]);
          }
        }
        if(best_anchor == NO_CELL || gain > best_gain ||
           (gain == best_gain && reach > best_reach) ||
           (gain == best_gain && reach == best_reach &&
            candidate_size > best_size)) {
          best_anchor = candidate_cell;
          best_gain = gain;
          best_reach = reach;
          best_size = candidate_size;
        }
      }
      if(best_anchor == NO_CELL) break;

      anchors[selected_count] = best_anchor;
      selected_cells[best_anchor] = true;
      const u64 selected = residuals[best_anchor];
      mask_to_glyph(selected, frame.glyphs[selected_count]);
      selected_count++;
      const u8 selected_size = bit_count(selected);
      for(u8 cell = 0; cell < CELL_COUNT; cell++) {
        if((selected & ~residuals[cell]) == 0 &&
           selected_size > reusable_pixels[cell]) {
          reusable_pixels[cell] = selected_size;
        }
      }
    }
    if(selected_count == 0) return false;

    for(u8 cell = 0; cell < CELL_COUNT; cell++) {
      u8 selected_slot = SLOT_COUNT;
      for(u8 slot = 0; slot < selected_count; slot++) {
        if(anchors[slot] == cell) {
          selected_slot = slot;
          break;
        }
      }
      if(selected_slot == SLOT_COUNT) {
        u8 selected_size = 0;
        for(u8 slot = 0; slot < selected_count; slot++) {
          const u64 candidate = glyph_mask(frame.glyphs[slot]);
          const u8 candidate_size = bit_count(candidate);
          if((candidate & ~residuals[cell]) == 0 &&
             (selected_slot == SLOT_COUNT || candidate_size > selected_size)) {
            selected_slot = slot;
            selected_size = candidate_size;
          }
        }
      }
      if(selected_slot < SLOT_COUNT) {
        frame.cells[cell] = selected_slot;
        residuals[cell] &= ~glyph_mask(frame.glyphs[selected_slot]);
      }
    }
    sequence.frame_count++;
  }

  for(u8 cell = 0; cell < CELL_COUNT; cell++) {
    if(residuals[cell] != 0) return false;
  }
  if(sequence.frame_count == first_frame) {
    if(sequence.frame_count >= MAX_SEQUENCE_FRAMES) return false;
    clear_frame(sequence.frames[sequence.frame_count++]);
  }
  return true;
}

} // namespace

bool build_diffusion_sequence(const u8 viewport[VIEW_BYTES],
                              FrameSequence& sequence) {
  if(viewport == NULL) return false;
  memset(&sequence, 0, sizeof(sequence));
  return append_diffusion(viewport, sequence);
}

u8 faster_rate(u8 divisor) {
  return divisor > MIN_RATE_DIVISOR ? (u8) (divisor - 1U)
                                    : MIN_RATE_DIVISOR;
}

u8 slower_rate(u8 divisor) {
  return divisor < MAX_RATE_DIVISOR ? (u8) (divisor + 1U)
                                    : MAX_RATE_DIVISOR;
}

u32 phase_hold_us(u32 transfer_us, u8 divisor) {
  if(divisor <= MIN_RATE_DIVISOR) return 0;
  if(divisor > MAX_RATE_DIVISOR) divisor = MAX_RATE_DIVISOR;
  const u32 multiplier = (u32) divisor - 1U;
  if(transfer_us > 0xFFFFFFFFU / multiplier) return 0xFFFFFFFFU;
  return transfer_us * multiplier;
}

} // namespace a00_image_mux
