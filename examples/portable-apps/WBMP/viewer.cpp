#include "mk61_app.h"
#include "wbmp.hpp"

namespace {

// Private BSS fits in the 20-KiB limit of one APP allocation. The decoder is
// reused unchanged; this prototype needs no resident C++ objects or leases.
#if defined(MK61_TARGET_PICOCALC)
u8* frame=nullptr;
constexpr unsigned MAX_WIDTH=320,MAX_HEIGHT=320;
struct Source {
  const mk61_app_api* api;
  const mk61_app_services* services;
  mk61_service_buffer buffer{};
  u32 id,size,cached=UINT32_MAX,valid=0;
  u8 bytes[512]{};
  ~Source() { if(buffer.handle) mk61_app_buffer_release(services,buffer.handle); }
  bool load() {
    if(!mk61_app_buffer_acquire(services,size,MK61_BUFFER_EXTERNAL,&buffer)) return true;
    for(u32 at=0;at<size;) {
      const u32 n=size-at<sizeof(bytes)?size-at:sizeof(bytes);
      if(api->file_read(id,at,bytes,n)!=n ||
         !mk61_app_buffer_write(services,buffer.handle,at,bytes,n)) return false;
      at+=n;api->service();
    }
    return true;
  }
  static bool read(void* context,usize offset,u8* out,usize count) {
    auto& s=*(Source*)context;
    if(offset>s.size || count>s.size-offset) return false;
    while(count) {
      const u32 base=(u32)offset&~511U;
      if(s.cached!=base) {
        s.valid=s.size-base<sizeof(s.bytes)?s.size-base:sizeof(s.bytes);
        if(s.buffer.handle) {
          if(!mk61_app_buffer_read(s.services,s.buffer.handle,base,s.bytes,s.valid)) return false;
        } else if(s.api->file_read(s.id,base,s.bytes,s.valid)!=s.valid) return false;
        s.cached=base;
      }
      const u32 within=(u32)offset-base;
      const u32 n=count<s.valid-within?(u32)count:s.valid-within;
      for(u32 i=0;i<n;++i) out[i]=s.bytes[within+i];
      out+=n;offset+=n;count-=n;
    }
    return true;
  }
};
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
#if defined(MK61_TARGET_PICOCALC)
  // Keep only a small read cache in SRAM. Old Pico firmware or absent PSRAM
  // uses the same indirect decoder directly from SD, without a large lease.
  if(!size || size>4U*1024*1024) return MK61_APP_INVALID_FILE;
  Source source{api,mk61_app_get_services(api,0),{},file_id,size};
  if(!source.load()) return MK61_APP_IO_ERROR;
  const wbmp::Reader reader{&source,size,Source::read};
#else
  if(size == 0 || size > sizeof(file_bytes)) return MK61_APP_INVALID_FILE;
  if(api->file_read(file_id, 0, file_bytes, size) != size)
    return MK61_APP_IO_ERROR;
#endif
  wbmp::Info info = {};
#if defined(MK61_TARGET_PICOCALC)
  const auto inspected=wbmp::inspect(reader,info);
  if(inspected!=wbmp::Status::OK)
    return inspected==wbmp::Status::IO_ERROR?MK61_APP_IO_ERROR:MK61_APP_INVALID_FILE;
#else
  if(wbmp::inspect(file_bytes, size, info) != wbmp::Status::OK)
    return MK61_APP_INVALID_FILE;
#endif

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
#if defined(MK61_TARGET_PICOCALC)
        const auto decoded=wbmp::decode_viewport(reader,info,x,y,width,height,
            wbmp::Layout::PAGE_MAJOR_LSB,frame,bytes);
        if(decoded!=wbmp::Status::OK) {
          api->graphics_end();return decoded==wbmp::Status::IO_ERROR?MK61_APP_IO_ERROR:MK61_APP_INVALID_FILE;
        }
#else
        if(wbmp::decode_viewport(file_bytes, size, info, x, y, width, height,
                                 wbmp::Layout::PAGE_MAJOR_LSB, frame, bytes) !=
           wbmp::Status::OK) {
          api->graphics_end();
          return MK61_APP_INVALID_FILE;
        }
#endif
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
#if defined(MK61_TARGET_PICOCALC)
        case MK61_APP_KEY_BACKWARD:
#endif
        case MK61_APP_KEY_SHIFT_LEFT: y = backward(y, height); break;
#if defined(MK61_TARGET_PICOCALC)
        case MK61_APP_KEY_FORWARD:
#endif
        case MK61_APP_KEY_SHIFT_RIGHT: y = forward(y, height, max_y); break;
        default: break;
      }
      dirty = x != old_x || y != old_y;
      if(!dirty) api->delay_ms(10);
    }
    api->graphics_end();
  }
}
