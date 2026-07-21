#include "config.h"

#if MK61_ENABLE_WBMP_VIEWER

#include "image1_viewer.hpp"

#include "a00_image_multiplex.hpp"
#include "cross_hal.h"
#include "keyboard.h"
#include "language_workspace.hpp"
#include "lcd_ru.hpp"
#include "shared_scratch.hpp"

extern void idle_main_process(void);

namespace image1_viewer {
namespace {

static_assert(MK61_IMAGE1_RATE_DIVISOR >= a00_image_mux::MIN_RATE_DIVISOR &&
              MK61_IMAGE1_RATE_DIVISOR <= a00_image_mux::MAX_RATE_DIVISOR,
              "Default Image1 rate divisor is outside the interactive range");

static constexpr u16 GRAPHICS_WIDTH = 192;
static constexpr u16 GRAPHICS_HEIGHT = 64;
static constexpr usize GRAPHICS_BYTES =
  (usize) GRAPHICS_WIDTH * GRAPHICS_HEIGHT / 8U;

struct CellWorkspace {
  u8 viewport[a00_image_mux::VIEW_BYTES];
  a00_image_mux::FrameSequence sequence;
};

union ViewerWorkspace {
  CellWorkspace cell;
  u8 graphics[GRAPHICS_BYTES];
};

static_assert(sizeof(ViewerWorkspace) <= language_workspace::SIZE,
              "Image viewer must fit the shared runtime workspace");
static_assert(GRAPHICS_BYTES == 1536,
              "UC1609 fullscreen buffer geometry changed unexpectedly");

static i32 scan_key(void) {
  const i32 scan_code = kbd::scan_and_debounced();
  if(scan_code < 0) return -1;
  kbd::exclude_before(scan_code);
  if((scan_code & (i32) key_state::RELEASED) != 0) return -1;
  return scan_code & ~(i32) key_state::RELEASED;
}

static i32 wait_phase_and_scan(u32 hold_us) {
  static constexpr u32 POLL_SLICE_US = 1000;
  const u32 started = micros();
  while(true) {
    idle_main_process();
    const i32 key = scan_key();
    if(key >= 0) return key;

    const u32 elapsed = (u32) (micros() - started);
    if(elapsed >= hold_us) return -1;
    const u32 remaining = hold_us - elapsed;
    delayMicroseconds(remaining < POLL_SLICE_US ? remaining : POLL_SLICE_US);
  }
}

static i32 wait_key(void) {
  while(true) {
    idle_main_process();
    const i32 key = scan_key();
    if(key >= 0) return key;
    delay(10);
  }
}

static u32 step_forward(u32 value, u32 step, u32 maximum) {
  if(value >= maximum) return maximum;
  const u32 remaining = maximum - value;
  return remaining < step ? maximum : value + step;
}

static u32 step_backward(u32 value, u32 step) {
  return value > step ? value - step : 0;
}

static bool navigation(i32 key, u32 max_x, u32 max_y,
                       u32& x, u32& y) {
  u32 next_x = x;
  u32 next_y = y;
  if(key == KEY_LEFT || key == KEY_LEFT_PRESS) {
    next_x = step_backward(x, a00_image_mux::CELL_WIDTH);
  } else if(key == KEY_RIGHT || key == KEY_RIGHT_PRESS) {
    next_x = step_forward(x, a00_image_mux::CELL_WIDTH, max_x);
  } else if(key == KEY_SHG_LEFT_PRESS) {
    next_y = step_backward(y, a00_image_mux::VIEW_HEIGHT);
  } else if(key == KEY_SHG_RIGHT_PRESS) {
    next_y = step_forward(y, a00_image_mux::VIEW_HEIGHT, max_y);
  }
  if(next_x == x && next_y == y) return false;
  x = next_x;
  y = next_y;
  return true;
}

static bool write_cell_frame(MK61Display& display,
                             const a00_image_mux::TemporalFrame& frame,
                             u32& transfer_us) {
  const u32 started = micros();
  const bool written = display.writeCellAnimationPaletteFrame(
    frame.glyphs, frame.cells, a00_image_mux::CELL_COUNT);
  transfer_us = (u32) (micros() - started);
  return written;
}

static bool prepare_cell_view(const u8* data, u16 size,
                              const wbmp::Info& info,
                              u32 view_x, u32 view_y,
                              CellWorkspace& workspace,
                              wbmp::Status& status) {
  status = wbmp::decode_viewport(
    data, size, info, view_x, view_y,
    a00_image_mux::VIEW_WIDTH, a00_image_mux::VIEW_HEIGHT,
    wbmp::Layout::ROW_MAJOR_MSB,
    workspace.viewport, sizeof(workspace.viewport));
  return status == wbmp::Status::OK &&
         a00_image_mux::build_diffusion_sequence(workspace.viewport,
                                                  workspace.sequence);
}

static Result view_cell_display(MK61Display& display,
                                const u8* data, u16 size,
                                const wbmp::Info& info,
                                CellWorkspace& workspace,
                                wbmp::Status& status) {
  u32 view_x = 0;
  u32 view_y = 0;
  if(!prepare_cell_view(data, size, info, view_x, view_y,
                        workspace, status)) {
    return Result::DECODE_ERROR;
  }
  if(!display.beginCellAnimation()) return Result::DISPLAY_ERROR;

  u8 phase = 0;
  u32 transfer_us = 0;
  if(!write_cell_frame(display, workspace.sequence.frames[phase],
                       transfer_us)) {
    display.endCellAnimation();
    lcd_ru::restore_default_font();
    return Result::DISPLAY_ERROR;
  }

  // Максимальная стоимость уже встреченного кадра задаёт одинаковое время
  // свечения всем фазам, даже если часть CGRAM/DDRAM не пришлось менять.
  u32 transfer_budget_us = transfer_us;
  const u32 max_x = info.width > a00_image_mux::VIEW_WIDTH
                  ? info.width - a00_image_mux::VIEW_WIDTH : 0;
  const u32 max_y = info.height > a00_image_mux::VIEW_HEIGHT
                  ? info.height - a00_image_mux::VIEW_HEIGHT : 0;
  u8 rate_divisor = MK61_IMAGE1_RATE_DIVISOR;
  kbd::debounce_init();

  Result result = Result::OK;
  while(true) {
    const u32 hold_us = a00_image_mux::phase_hold_us(transfer_budget_us,
                                                     rate_divisor);
    const i32 key = wait_phase_and_scan(hold_us);
    if(key == KEY_ESC || key == KEY_OK) break;
    if(key == KEY_DEGREE) {
      rate_divisor = a00_image_mux::faster_rate(rate_divisor);
    } else if(key == KEY_RADIAN) {
      rate_divisor = a00_image_mux::slower_rate(rate_divisor);
    }

    if(navigation(key, max_x, max_y, view_x, view_y)) {
      // Старый кадр остаётся видимым, пока новое окно декодируется и целиком
      // планируется в общей RAM; промежуточная очистка экрана не нужна.
      if(!prepare_cell_view(data, size, info, view_x, view_y,
                            workspace, status)) {
        result = Result::DECODE_ERROR;
        break;
      }
      phase = 0;
    } else {
      phase = (u8) ((phase + 1U) % workspace.sequence.frame_count);
    }

    if(!write_cell_frame(display, workspace.sequence.frames[phase],
                         transfer_us)) {
      result = Result::DISPLAY_ERROR;
      break;
    }
    if(transfer_us > transfer_budget_us) transfer_budget_us = transfer_us;
  }

  display.endCellAnimation();
  lcd_ru::restore_default_font();
  return result;
}

static bool render_graphics_view(MK61Display& display,
                                 const u8* data, u16 size,
                                 const wbmp::Info& info,
                                 u32 view_x, u32 view_y,
                                 u8 bitmap[GRAPHICS_BYTES],
                                 wbmp::Status& status) {
  status = wbmp::decode_viewport(
    data, size, info, view_x, view_y, GRAPHICS_WIDTH, GRAPHICS_HEIGHT,
    wbmp::Layout::PAGE_MAJOR_LSB, bitmap, GRAPHICS_BYTES);
  return status == wbmp::Status::OK &&
         display.showFullscreenBitmap(bitmap, GRAPHICS_BYTES);
}

static Result view_graphics_display(MK61Display& display,
                                    const u8* data, u16 size,
                                    const wbmp::Info& info,
                                    u8 bitmap[GRAPHICS_BYTES],
                                    wbmp::Status& status) {
  u32 view_x = 0;
  u32 view_y = 0;
  if(!display.beginFullscreenBitmap()) return Result::DISPLAY_ERROR;
  if(!render_graphics_view(display, data, size, info, view_x, view_y,
                           bitmap, status)) {
    display.endFullscreenBitmap();
    return status == wbmp::Status::OK ? Result::DISPLAY_ERROR
                                      : Result::DECODE_ERROR;
  }

  const u32 max_x = info.width > GRAPHICS_WIDTH
                  ? info.width - GRAPHICS_WIDTH : 0;
  const u32 max_y = info.height > GRAPHICS_HEIGHT
                  ? info.height - GRAPHICS_HEIGHT : 0;
  kbd::debounce_init();
  Result result = Result::OK;
  while(true) {
    const i32 key = wait_key();
    if(key == KEY_ESC || key == KEY_OK) break;
    if(!navigation(key, max_x, max_y, view_x, view_y)) continue;
    if(!render_graphics_view(display, data, size, info, view_x, view_y,
                             bitmap, status)) {
      result = status == wbmp::Status::OK ? Result::DISPLAY_ERROR
                                          : Result::DECODE_ERROR;
      break;
    }
  }
  display.endFullscreenBitmap();
  return result;
}

} // namespace

Result view(MK61Display& display, const u8* data, u16 size,
            wbmp::Status* image_status) {
  if(image_status != NULL) *image_status = wbmp::Status::OK;
  wbmp::Info info = {};
  wbmp::Status status = wbmp::inspect(data, size, info);
  if(status != wbmp::Status::OK) {
    if(image_status != NULL) *image_status = status;
    return Result::INVALID_IMAGE;
  }

  language_workspace::Lease lease(language_workspace::Owner::IMAGE_VIEWER,
                                   sizeof(ViewerWorkspace));
  if(!lease.ok()) return Result::BUSY;
  ViewerWorkspace& workspace = *(ViewerWorkspace*) lease.data();

#if defined(MK61_DISPLAY_LCD1602)
  const Result result = view_cell_display(display, data, size, info,
                                          workspace.cell, status);
#else
  const Result result = view_graphics_display(display, data, size, info,
                                              workspace.graphics, status);
#endif
  if(image_status != NULL) *image_status = status;
  return result;
}

Result view_entry(MK61Display& display, const program_store::Entry& entry,
                  wbmp::Status* image_status) {
  if(image_status != NULL) *image_status = wbmp::Status::OK;
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::IMAGE1 ||
     entry.data_len == 0 || entry.data_len > program_store::MAX_IMAGE1_SIZE) {
    return Result::INVALID_IMAGE;
  }

  shared_scratch::Lease file(shared_scratch::Owner::IMAGE_VIEWER,
                             program_store::MAX_IMAGE1_SIZE);
  if(!file.ok()) return Result::BUSY;
  u16 read_len = 0;
  if(!program_store::read_id(entry.id, file.data(), entry.data_len, &read_len) ||
     read_len != entry.data_len) {
    return Result::READ_ERROR;
  }
  return view(display, file.data(), read_len, image_status);
}

const char* result_text(Result result) {
  switch(result) {
    case Result::OK: return "ok";
    case Result::BUSY: return "workspace busy";
    case Result::READ_ERROR: return "read error";
    case Result::INVALID_IMAGE: return "invalid WBMP";
    case Result::DECODE_ERROR: return "decode error";
    case Result::DISPLAY_ERROR: return "display error";
  }
  return "unknown image viewer error";
}

} // namespace image1_viewer

#endif // MK61_ENABLE_WBMP_VIEWER
