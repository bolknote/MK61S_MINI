#include "config.h"

#if MK61_IMAGE1_VIEWER_IS_BUILTIN || defined(MK61_BUILD_WBMP_MODULE) || \
    (defined(MK61_BUILD_MARKDOWN_MODULE) && MK61_HAS_COMPILED_GRAPHICS)

#include "image1_viewer.hpp"

#include "cross_hal.h"
#include "keyboard.h"
#include "language_workspace.hpp"
#include "shared_scratch.hpp"

extern void idle_main_process(void);

namespace image1_viewer {
namespace {

static constexpr u16 GRAPHICS_WIDTH = 192;
static constexpr u16 GRAPHICS_HEIGHT = 64;
static constexpr usize GRAPHICS_BYTES =
    (usize) GRAPHICS_WIDTH * GRAPHICS_HEIGHT / 8U;
static constexpr i32 VIEWER_DISPLAY_CHANGED = -2;

struct ViewerWorkspace {
  u8 graphics[GRAPHICS_BYTES];
};

static_assert(sizeof(ViewerWorkspace) <= language_workspace::SIZE,
              "Image viewer must fit the shared runtime workspace");

static i32 scan_key(void) {
  const i32 scan_code = kbd::scan_and_debounced();
  if(scan_code < 0) return -1;
  kbd::exclude_before(scan_code);
  if((scan_code & (i32) key_state::RELEASED) != 0) return -1;
  return scan_code & ~(i32) key_state::RELEASED;
}

static i32 wait_key(MK61Display& display, u32 display_mode_revision) {
  while(true) {
    idle_main_process();
    if(display.displayModeRevision() != display_mode_revision) {
      return VIEWER_DISPLAY_CHANGED;
    }
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
    next_x = step_backward(x, 8);
  } else if(key == KEY_RIGHT || key == KEY_RIGHT_PRESS) {
    next_x = step_forward(x, 8, max_x);
  } else if(key == KEY_SHG_LEFT_PRESS) {
    next_y = step_backward(y, GRAPHICS_HEIGHT);
  } else if(key == KEY_SHG_RIGHT_PRESS) {
    next_y = step_forward(y, GRAPHICS_HEIGHT, max_y);
  }
  if(next_x == x && next_y == y) return false;
  x = next_x;
  y = next_y;
  return true;
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
                                    wbmp::Status& status,
                                    u32 display_mode_revision,
                                    bool& display_changed) {
  u32 view_x = 0;
  u32 view_y = 0;
  if(!display.beginFullscreenBitmap()) return Result::UNSUPPORTED_DISPLAY;
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
    const i32 key = wait_key(display, display_mode_revision);
    if(key == VIEWER_DISPLAY_CHANGED) {
      display_changed = true;
      break;
    }
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
  if(!display.graphicsMode()) return Result::UNSUPPORTED_DISPLAY;

  language_workspace::Lease lease(language_workspace::Owner::IMAGE_VIEWER,
                                   sizeof(ViewerWorkspace));
  if(!lease.ok()) return Result::BUSY;
  ViewerWorkspace& workspace = *(ViewerWorkspace*) lease.data();

  Result result = Result::OK;
  bool display_changed = false;
  do {
    if(!display.graphicsMode()) {
      result = Result::UNSUPPORTED_DISPLAY;
      break;
    }
    display_changed = false;
    result = view_graphics_display(
        display, data, size, info, workspace.graphics, status,
        display.displayModeRevision(), display_changed);
  } while(display_changed);
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
  if(!program_store::read_id(entry.id, file.data(), entry.data_len,
                             &read_len) ||
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
    case Result::UNSUPPORTED_DISPLAY: return "graphics screen required";
  }
  return "unknown image viewer error";
}

} // namespace image1_viewer

#endif
