#include "mk61_app.h"
#include "wbmp.hpp"

namespace {

// Private BSS fits in the 20-KiB limit of one APP allocation. The decoder is
// reused unchanged; this prototype needs no resident C++ objects or leases.
#if defined(MK61_TARGET_PICOCALC)
u8 file_bytes[16384];u8* frame=nullptr;
constexpr unsigned MAX_WIDTH=320,MAX_HEIGHT=320;
#else
u8 file_bytes[1600];u8 frame[192*64/8];
constexpr unsigned MAX_WIDTH=192,MAX_HEIGHT=64;
#endif

u32 forward(u32 position, u32 step, u32 maximum) {
  return maximum - position < step ? maximum : position + step;
}

u32 backward(u32 position, u32 step) {
  return position > step ? position - step : 0;
}

} // namespace

extern "C" uint32_t mk61_app_open_file(uint32_t file_id) {
  const mk61_app_api* api = mk61_api;
  const u32 capabilities = MK61_APP_CAP_TIME | MK61_APP_CAP_KEYBOARD |
      MK61_APP_CAP_FILES | MK61_APP_CAP_GRAPHICS;
  if(!mk61_app_api_compatible(api, sizeof(*api), capabilities))
    return MK61_APP_UNSUPPORTED_DISPLAY;
  const u32 size = api->file_size(file_id);
  if(size == 0 || size > sizeof(file_bytes)) return MK61_APP_INVALID_FILE;
  if(api->file_read(file_id, 0, file_bytes, size) != size)
    return MK61_APP_IO_ERROR;
  wbmp::Info info = {};
  if(wbmp::inspect(file_bytes, size, info) != wbmp::Status::OK)
    return MK61_APP_INVALID_FILE;

  for(;;) {
    if(!api->graphics_available() || !api->graphics_begin())
      return MK61_APP_UNSUPPORTED_DISPLAY;
    const u32 revision = api->graphics_revision();
    const u32 width = api->graphics_width();
    const u32 height = api->graphics_height();
    if(width == 0 || width > MAX_WIDTH || height == 0 || height > MAX_HEIGHT) {
      api->graphics_end();
      return MK61_APP_UNSUPPORTED_DISPLAY;
    }
#if defined(MK61_TARGET_PICOCALC)
    const auto services=(const mk61_app_services*)api->query_service(MK61_APP_SERVICE_COMMON,MK61_APP_SERVICES_VERSION);
    mk61_service_framebuffer borrowed={};
    if(!services || !services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(borrowed),0,&borrowed) ||
       borrowed.width!=width || borrowed.height!=height) { api->graphics_end();return MK61_APP_UNSUPPORTED_DISPLAY; }
    frame=borrowed.pixels;
#endif
    const u32 bytes = wbmp::viewport_bytes(width, height,
                                           wbmp::Layout::PAGE_MAJOR_LSB);
    const u32 max_x = info.width > width ? info.width - width : 0;
    const u32 max_y = info.height > height ? info.height - height : 0;
    u32 x = 0, y = 0;
    bool dirty = true;
    for(;;) {
      if(dirty) {
        if(wbmp::decode_viewport(file_bytes, size, info, x, y, width, height,
                                 wbmp::Layout::PAGE_MAJOR_LSB, frame, bytes) !=
           wbmp::Status::OK) {
          api->graphics_end();
          return MK61_APP_INVALID_FILE;
        }
        if(!api->graphics_present(frame, bytes)) {
          api->graphics_end();
          return MK61_APP_RUNTIME_ERROR;
        }
        dirty = false;
      }
      api->service();
      if(api->graphics_revision() != revision) break;
      const i32 key = api->key_poll();
      if(key == MK61_APP_KEY_ESC || key == MK61_APP_KEY_OK) {
        api->graphics_end();
        return MK61_APP_OK;
      }
      const u32 old_x = x, old_y = y;
      switch(key) {
        case MK61_APP_KEY_LEFT: x = backward(x, 8); break;
        case MK61_APP_KEY_RIGHT: x = forward(x, 8, max_x); break;
        case MK61_APP_KEY_SHIFT_LEFT: y = backward(y, height); break;
        case MK61_APP_KEY_SHIFT_RIGHT: y = forward(y, height, max_y); break;
        default: break;
      }
      dirty = x != old_x || y != old_y;
      if(!dirty) api->delay_ms(10);
    }
    api->graphics_end();
  }
}
