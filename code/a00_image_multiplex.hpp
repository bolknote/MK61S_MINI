#ifndef MK61_A00_IMAGE_MULTIPLEX_HPP
#define MK61_A00_IMAGE_MULTIPLEX_HPP

#include "rust_types.h"

namespace a00_image_mux {

static constexpr u8 COLS = 16;
static constexpr u8 ROWS = 2;
static constexpr u8 CELL_WIDTH = 5;
static constexpr u8 CELL_HEIGHT = 7;
static constexpr u8 CELL_COUNT = COLS * ROWS;
static constexpr u16 VIEW_WIDTH = COLS * CELL_WIDTH;
static constexpr u16 VIEW_HEIGHT = ROWS * CELL_HEIGHT;
static constexpr u16 VIEW_STRIDE = (VIEW_WIDTH + 7U) / 8U;
static constexpr u16 VIEW_BYTES = VIEW_STRIDE * VIEW_HEIGHT;
static constexpr u8 PHASE_COUNT = 4;
static constexpr u8 SLOT_COUNT = 8;
static constexpr u8 GLYPH_ROWS = 8;
static constexpr u8 NO_CELL = 0xFF;
static constexpr u8 MIN_RATE_DIVISOR = 1;
static constexpr u8 MAX_RATE_DIVISOR = 16;
static constexpr u8 BLANK_CELL_CODE = ' ';
static constexpr u8 MAX_SEQUENCE_FRAMES = PHASE_COUNT;

struct TemporalFrame {
  u8 glyphs[SLOT_COUNT][GLYPH_ROWS];
  u8 cells[CELL_COUNT];
};

struct FrameSequence {
  TemporalFrame frames[MAX_SEQUENCE_FRAMES];
  u8 frame_count;
};

static_assert(sizeof(TemporalFrame) == 96,
              "Temporal image frame geometry changed unexpectedly");
static_assert(sizeof(FrameSequence) == 385,
              "Precomputed image sequence exceeds its RAM budget");

// Извлекает точный растр знакоместа из окна в аппаратном формате CGRAM:
// bit 4 — левый пиксель, восьмая строка всегда погашена.
bool glyph_for_cell(const u8 viewport[VIEW_BYTES], u8 cell,
                    u8 rows[GLYPH_ROWS]);

// Строит временную палитру без ложных пикселей и разной яркости. В каждой
// фазе восемь остаточных масок повторно используются на всех совместимых
// позициях и сразу вычитаются из них. Поэтому каждый пиксель изображения
// зажигается ровно в одном кадре цикла; пустые хвостовые кадры отбрасываются.
bool build_diffusion_sequence(const u8 viewport[VIEW_BYTES],
                              FrameSequence& sequence);

u8 faster_rate(u8 divisor);
u8 slower_rate(u8 divisor);
u32 phase_hold_us(u32 transfer_us, u8 divisor);

} // пространство имён a00_image_mux

#endif
