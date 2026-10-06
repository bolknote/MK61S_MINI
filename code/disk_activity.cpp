#include "disk_activity.hpp"

#if MK61_DISK_ACTIVITY_SUPPORTED
#include "display.hpp"
#include "builtin_font.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include <string.h>

namespace disk_activity {
namespace {
// program_store's outermost DiskActivity owns this flag. Nested file reads
// during a copy/import must not turn it off before the outer operation ends.
bool file_operation_active = false;

bool foreground(void) {
#if defined(__arm__) || defined(__thumb__)
  if(__get_IPSR() != 0) return false;
#endif
  return main_lcd_pointer != nullptr;
}
}

void note(void) {
  if(!foreground()) return;
  const u32 now = millis();
  main_lcd().noteDiskActivity(now);
  main_lcd().pollDiskActivity(now);
}
void poll(void) {
  if(foreground()) main_lcd().pollDiskActivity(millis());
}

void setFileOperation(bool active) {
  file_operation_active = active;
}

void storageIO(void) {
  if(file_operation_active) note();
  else poll(); // still animate a USB commit and expire a previous indicator
}

Pause::Pause(MK61Display& display) : display_(display) {
  display_.pauseDiskActivity();
}
Pause::~Pause() { display_.resumeDiskActivity(); }

#if defined(MK61_DISPLAY_UC1609)
namespace {
struct Page {
  u8 index;
  u8* pixels;
  void rect(i16 x, i16 y, i16 w, i16 h, bool ink = true) {
    const i16 top = index * 8;
    for(i16 py = y < top ? top : y; py < y+h && py < top+8; ++py) {
      const u8 mask = (u8) (1U << (py-top));
      for(i16 px = x < 0 ? 0 : x; px < x+w && px < 192; ++px) {
        if(ink) pixels[px] |= mask; else pixels[px] &= (u8) ~mask;
      }
    }
  }
  void box(u8 x, u8 y, u8 w, u8 h) {
    rect(x,y,w,h); rect(x+1,y+1,w-2,h-2,false);
  }
  void centered(const char* text, u8 y) {
    if(y >= (index+1U)*8U || y+8U <= index*8U) return;
    i16 x = (192 - (i16) strlen(text)*6 + 1) / 2;
    while(*text) {
      builtin_font::Raster glyph;
      if(builtin_font::decode(builtin_font::FaceId::FONT_5X8,
                              mk8::codepoint((u8) *text++), glyph)) {
        for(u8 gy=0; gy<8; ++gy)
          for(u8 gx=0; gx<5; ++gx)
            if(glyph.data[gy] & (0x80U >> gx)) rect(x+gx,y+gy,1,1);
      }
      x += 6;
    }
  }
};
}

void savingPage(u8 page, u8 step, bool russian, u8* pixels) {
  memset(pixels, 0, 192);
  Page p{page, pixels};
  p.centered(russian ? M8("USB-ДИСК") : "USB DISK", 3);
  p.rect(12,14,168,1);
  p.box(32,23,19,23);
  p.rect(46,23,5,5,false);
  for(u8 i=0; i<6; ++i) p.rect(45+i,23+i,1,1);
  p.rect(45,27,6,1);
  for(u8 y=31; y<42; y+=4) p.rect(36,y,10,1);
  for(u8 i=0; i<3; ++i) p.box(59+(step*5U+i*24U)%72U,32,4,4);
  p.box(137,23,21,22);
  for(u8 y=26; y<=42; y+=5) { p.rect(134,y,3,1); p.rect(158,y,3,1); }
  for(u8 i=0; i<6; ++i) {
    const u8 x=142+(i%2)*7, y=27+(i/2)*5;
    p.box(x,y,4,3);
    if((i+step)%4 == 0) p.rect(x+1,y+1,2,1);
  }
  p.centered(russian ? M8("СОХРАНЕНИЕ...") : "SAVING...", 55);
}
#endif
} // namespace disk_activity

void MK61Display::pollDiskActivity(u32 now) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.setDiskActivity(disk_activity_.indicator(now));
    return;
  }
#endif
#if defined(MK61_DISPLAY_UC1609)
  if(!initialized || update_depth != 0) return;
#if MK61_ENABLE_USB_SCREEN
  if(!physical_screen_enabled) return;
#endif
  if(disk_saving_) {
    if((u32) (now - disk_frame_at_) < 160U && disk_step_ != 0xFF) return;
    const bool first = disk_step_ == 0xFF;
    disk_step_ = first ? 0 : (u8) ((disk_step_+1U)%72U);
    disk_frame_at_ = now;
    for(u8 page = first ? 0 : 2; page < (first ? 8 : 6); ++page) {
      disk_activity::savingPage(page, disk_step_, disk_saving_ru_, render_buffer);
      lcd.LCDBuffer(0, page*8U, 192, 8, render_buffer);
    }
    return;
  }
  if(!disk_overlay_.set(disk_activity_.indicator(now))) return;
  // Do not use the renderer's shared buffer: storage can be read by a
  // foreground owner that is in the middle of preparing its next frame.
  u8 pixels[disk_activity::Overlay::WIDTH];
  for(u8 page=0; page<disk_activity::Overlay::PAGES; ++page) {
    disk_overlay_.page(page, pixels);
    lcd.LCDBuffer(disk_activity::Overlay::LEFT, page*8U,
                  disk_activity::Overlay::WIDTH, 8, pixels);
  }
#endif
}

#if defined(MK61_DISPLAY_UC1609)
void MK61Display::beginDiskSaving(bool russian) {
  if(disk_saving_) return;
  disk_saving_ = true;
  disk_saving_ru_ = russian;
  disk_step_ = 0xFF;
  pollDiskActivity(millis());
}
void MK61Display::endDiskSaving(void) {
  if(!disk_saving_) return;
  disk_saving_ = false;
  markScreenDirty();
}
void MK61Display::presentPage(u8 page, u8 first, u8 count, u8* pixels) {
  disk_overlay_.compose(page, first, count, pixels);
  lcd.LCDBuffer(first, page*8U, count, 8, pixels);
}
#endif
#endif
