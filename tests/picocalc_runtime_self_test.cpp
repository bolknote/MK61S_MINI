#include "../ports/picocalc/usb_screen.hpp"
#include "clock.hpp"
#include "input.hpp"
#include "keyboard_core.hpp"
#include "loadable_app_api.h"
#include "loadable_module_format.hpp"
#include "power.hpp"
#include "settings.hpp"
#include "ui.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
namespace {
void require(bool ok, const char *message) {
  if (!ok) {
    std::fprintf(stderr, "Pico runtime: %s\n", message);
    std::abort();
  }
}
struct Link {
  std::vector<u8> bytes;
  unsigned space = 1024;
  u8 image[1536]{};
};
void receive(picocalc::UsbScreen &screen, usb_screen_protocol::MessageType type,
             const u8 *data = nullptr, unsigned n = 0, u32 now = 1) {
  usb_screen_protocol::PacketEncoder packet;
  require(packet.encode(type, 0, 0, data, n) == usb_screen_protocol::Status::OK,
          "encode request");
  for (unsigned i = 0; i < packet.size(); ++i)
    require(screen.receive(packet.data()[i], now) < 0,
            "packet leaked to terminal");
}
} // namespace
void picocalc_runtime_test() {
  using namespace picocalc;
  using namespace usb_screen_protocol;
  require(clock::valid({2000, 2, 29, 23, 59, 59}) &&
              !clock::valid({2100, 2, 29}),
          "Gregorian date validation");
  for (int y = 2000; y < 2100; ++y)
    for (int m = 1; m <= 12; ++m) {
      const clock::DateTime d{y, m, (int)clock::month_days(y, m), 23, 59, 58};
      const auto copy = clock::from_epoch(clock::epoch(d));
      require(copy.year == d.year && copy.month == d.month &&
                  copy.day == d.day && copy.hour == 23 && copy.second == 58,
              "calendar epoch round trip");
    }
  clock::init();
  require(!clock::configured(), "power-on RTC must start unset");
  {
    Link link;
    UsbScreen clock_screen;
    clock_screen.init({&link, [](void *p) { return ((Link *)p)->space; },
        [](void *p, const u8 *data, unsigned n) {
          auto &bytes = ((Link *)p)->bytes;
          bytes.insert(bytes.end(), data, data + n);return n;
        }, [](void *, u8 *) {}});
    u8 date[] = {1, 0xEA, 7, 10, 17, 14, 20, 0};
    receive(clock_screen, MessageType::CLOCK_SYNC, date, sizeof(date));
    require(clock::configured() && clock::get().hour == 14 && !clock_screen.enabled(),
        "cold-boot clock sync must not take the screen");
    clock_screen.tick(1);clock_screen.tick(2);
    StreamParser reply;bool acknowledged = false;
    for(u8 byte : link.bytes) if(reply.push(byte) == PushResult::PACKET) {
      const auto &p = reply.packet();
      acknowledged = p.type == MessageType::CLOCK_STATE && p.payload_size == 9 &&
          p.payload[0] == 0 && p.payload[1] == 1 && p.payload[6] == 14;
    }
    require(acknowledged, "clock sync response uses CRC-framed state");
    date[5] = 15;
    receive(clock_screen, MessageType::CLOCK_SYNC, date, sizeof(date));
    require(clock::get().hour == 14, "automatic sync preserves an already set clock");
    date[0] = 2;date[3] = 2;date[4] = 30;
    receive(clock_screen, MessageType::CLOCK_SYNC, date, sizeof(date));
    require(clock::get().hour == 14, "invalid forced date preserves good RTC");
    date[3] = 10;date[4] = 17;
    receive(clock_screen, MessageType::CLOCK_SYNC, date, sizeof(date));
    require(clock::get().hour == 15, "explicit forced clock sync");
    receive(clock_screen, MessageType::ACTIVATE);
    require(clock_screen.enabled() && !clock_screen.attached(),
        "framed activation leaves calculator input untouched");
  }
  require(clock::set({2026, 10, 17, 21, 34, 56}) && clock::configured(),
          "RTC write");
  require((clock::fat_time() & 31) == 28, "FAT timestamp seconds");
  require(!clock::set({2026, 2, 30}), "invalid RTC must not replace good date");
  unsigned alarm=9;
  require(clock::after(0,2),"relative alarm A");
  require(clock::set({2026,10,17,21,34,59}) && clock::take_alarm(alarm) && alarm==0 && !clock::alarm(0).enabled,"one-shot fires and disables");
  require(clock::schedule(1,{{2026,10,17,21,35,0},true,true}),"daily alarm B");
  u32 alarm_epochs[2];u8 alarm_flags;clock::save_alarms(alarm_epochs,alarm_flags);
  require((alarm_flags&10)==10,"alarm persistence includes daily and enabled bits");
  clock::restore_alarms(alarm_epochs,alarm_flags);
  clock::schedule(1,{clock::get(),false,false});
  SleepPolicy power;
  power.activity(100);
  require(!power.due(60000099, 1, false) && power.due(60000100, 1, false),
          "sleep deadline");
  require(!power.due(60000100, 1, true) && !power.due(60000100, 0, false),
          "busy/disabled sleep");
  power.activity(70000000);
  require(!power.due(60000100,1,false),"activity updated inside a blocking interpreter must not underflow the older loop timestamp");
  power.sleep();
  require(power.asleep() && power.wake(70000000) && !power.asleep(),
          "sleep wake preserves session");
  controls::clear();
  controls::event({1, 'q'});
  require(controls::chip8_keys(100) & (1 << 4), "CHIP-8 Q key");
  controls::event({1, 'q'}, controls::Source::REMOTE);
  controls::event({3, 'q'});
  require(controls::pressed('q', 100),
          "physical release must not clear remote hold");
  controls::event({3, 'q'}, controls::Source::REMOTE);
  require(!controls::pressed('q', 100), "remote release");
  controls::pulse('1', 0xFFFFFFC0U);
  require(controls::pressed('1', 20) && !controls::pressed('1', 200),
          "serial key expiry across wrap");
  require(controls::logical(0x1B) == MK61_APP_KEY_ESC, "native Escape key");
  Link link;
  for (unsigned i = 0; i < 1536; ++i)
    link.image[i] = (u8)(i * 37);
  UsbScreen screen;
  screen.init(
      {&link, [](void *p) { return ((Link *)p)->space; },
       [](void *p, const u8 *data, unsigned n) {
         auto &l = *(Link *)p;
         l.bytes.insert(l.bytes.end(), data, data + n);
         return n;
       },
       [](void *p, u8 *out) { std::memcpy(out, ((Link *)p)->image, 1536); }});
  screen.enable(true);
  screen.tick(0);
  screen.tick(0);
  require(!link.bytes.empty(), "USB Screen offer");
  link.bytes.clear();
  receive(screen, MessageType::ATTACH);
  require(screen.attached(), "USB attach");
  link.space = 16;
  screen.tick(1);
  screen.tick(2);
  require(link.bytes.empty(), "partial packet must not enter CDC FIFO");
  link.space = 1024;
  for (u32 i = 3; i < 28; ++i)
    screen.tick(i);
  StreamParser parser;
  u8 frame[1536]{};
  unsigned rects = 0, begin = 0, end = 0, caps = 0;
  for (u8 byte : link.bytes) {
    const auto result = parser.push(byte);
    require(result != PushResult::ERROR, "valid USB output packet");
    if (result != PushResult::PACKET)
      continue;
    const auto &p = parser.packet();
    if (p.type == MessageType::CAPS) {
      ++caps;
      require(p.payload_size == 14, "CAPS size");
      require((p.payload[4] & CAP_CLOCK_SYNC) && !(p.payload[4] & CAP_TERMINAL_KBD),
          "Pico capabilities must not request unsupported STM32 kbd commands");
    }
    if (p.type == MessageType::FRAME_BEGIN)
      ++begin;
    if (p.type == MessageType::RECT) {
      RectView r;
      require(parse_rect_payload(p.payload, p.payload_size, r) == Status::OK,
              "parse screen rectangle");
      require(decode_rect_pixels(r, frame + r.area.page * 192 + r.area.x,
                                 192 - r.area.x) == Status::OK,
              "decode screen rectangle");
      ++rects;
    }
    if (p.type == MessageType::FRAME_END) {
      ++end;
      require(p.payload_size == 4 &&
                  ((u16)p.payload[2] | (u16)p.payload[3] << 8) ==
                      crc16_ccitt(frame, 1536),
              "atomic frame CRC");
    }
  }
  require(caps == 1 && begin == 1 && end == 1 && rects == 8 &&
              !std::memcmp(frame, link.image, 1536),
          "complete shared-protocol keyframe");
  u8 event[] = {21, 1};
  receive(screen, MessageType::KEY_EVENT, event, 2, 30);
  KeyEvent key;
  require(screen.key(key) && key.pressed() && key.code == '1' && key.native_scan==21,
          "USB virtual MINI key mapping");
  receive(screen, MessageType::DETACH, nullptr, 0, 31);
  require(!screen.attached() && screen.key(key) && key.state == 3 &&
              key.code == '1' && key.native_scan==21,
          "detach releases delivered keys");
  require(screen.receive('7', 40) == '7', "terminal mux preserves text");
  receive(screen, MessageType::ATTACH, nullptr, 0, 50);
  screen.tick(3050);
  require(!screen.attached(), "USB heartbeat timeout");
  {
    Link native_link;unsigned captures=0;
    struct Context { Link* link;unsigned* captures; } context{&native_link,&captures};
    UsbScreen native;
    native.init({&context,[](void*) { return 1024U; },
      [](void* raw,const u8* bytes,unsigned n) { auto& v=((Context*)raw)->link->bytes;v.insert(v.end(),bytes,bytes+n);return n; },
      [](void*,u8*) {},[](void* raw) { ++*((Context*)raw)->captures; },
      [](void*,unsigned x,unsigned page,u8* out,unsigned n) { for(unsigned i=0;i<n;++i) out[i]=(u8)((page*320+x+i)*37+7); }});
    native.enable(true);const u8 request=1;receive(native,MessageType::ATTACH,&request,1);
    for(unsigned i=0;i<86;++i) native.tick(1);
    require(captures==1 && !native.holds_frame(),"one stable native snapshot per complete frame");
    StreamParser decoder;std::vector<u8> bitmap(12800);unsigned rectangles=0,completed=0;
    for(u8 byte:native_link.bytes) if(decoder.push(byte)==PushResult::PACKET) {
      const auto& p=decoder.packet();
      if(p.type==MessageType::CAPS) require(p.payload_size==16 && p.payload[0]==64 && p.payload[1]==1 &&
        p.payload[14]==64 && p.payload[15]==1,"native CAPS has 16-bit width and height");
      if(p.type==MessageType::FRAME_BEGIN) require(p.payload[3]==80,"native frame has 80 bounded rectangles");
      if(p.type==MessageType::RECT) {
        require(p.payload_size==166 && p.payload[4]==160 && p.payload[5]==0,"native RAW rectangle length");
        std::memcpy(bitmap.data()+p.payload[3]*320+p.payload[2],p.payload+6,160);++rectangles;
      }
      if(p.type==MessageType::FRAME_END) { ++completed;
        require(((unsigned)p.payload[2]|(unsigned)p.payload[3]<<8)==crc16_ccitt(bitmap.data(),bitmap.size()),"native whole-frame CRC"); }
    }
    require(rectangles==80 && completed==1,"complete native USB keyframe");
    for(unsigned i=0;i<bitmap.size();++i) require(bitmap[i]==(u8)(i*37+7),"native pixel positions include right/bottom edges");
    native.tick(100);require(native.holds_frame(),"native framebuffer stays frozen during transmission");
    native.enable(false);require(!native.holds_frame(),"detach releases native snapshot");
  }
  std::puts("PicoCalc RTC/sleep/key state/USB Screen runtime tests passed");
}
