#ifndef MK61_PICOCALC_USB_SCREEN_HPP
#define MK61_PICOCALC_USB_SCREEN_HPP
#include "calculator.hpp"
#include "usb_screen_protocol.hpp"
#include "usb_screen_virtual_keys.hpp"
namespace picocalc {
class UsbScreen {
public:
  struct Backend {
    void *context;
    unsigned (*available)(void *);
    unsigned (*write)(void *, const u8 *, unsigned);
    void (*frame)(void *, u8 *);
    void (*native_begin)(void*)=nullptr;
    void (*native_page)(void*,unsigned x,unsigned page,u8* out,unsigned count)=nullptr;
  };
  void init(Backend backend) { backend_ = backend; }
  void enable(bool on);
  bool enabled() const { return enabled_; }
  bool attached() const { return attached_; }
  bool holds_frame() const { return native_ && stage_!=0; }
  int receive(u8 value, u32 now);
  void tick(u32 now, bool connected = true);
  bool key(KeyEvent &event);
  u32 frames() const { return frames_; }
  u32 errors() const { return errors_; }

private:
  bool packet(usb_screen_protocol::MessageType, const u8 *, unsigned);
  void disconnect();
  Backend backend_{};
  usb_screen_protocol::MultiplexParser parser_;
  usb_screen_protocol::PacketEncoder encoder_;
  usb_screen::VirtualKeyQueue keys_;
  bool enabled_ = false, attached_ = false, caps_ = false, pong_ = false,
       force_ = true;
  u16 sequence_ = 0, frame_id_ = 0, ping_ = 0, pong_value_ = 0;
  u32 last_seen_ = 0, next_offer_ = 0, next_frame_ = 0, next_ping_ = 0,
      frames_ = 0, errors_ = 0;
  unsigned offset_ = 0, pending_ = 0, stage_ = 0;
  bool native_=false;
  u16 native_crc_=0xFFFF;
  bool clock_reply_ = false;
  u8 clock_state_[9]{};
  u8 frame_[1536]{}, previous_[1536]{};
};
} // namespace picocalc
#endif
