#include "usb_screen.hpp"
#include "input.hpp"
#include "clock.hpp"
#include <cstring>
namespace picocalc {
using namespace usb_screen_protocol;
namespace {
// Pico CDC accepts physical key bytes, not the STM32 terminal's `kbd` shell.
// Desktop clients must use binary KEY_EVENT instead of emitting that command.
constexpr u16 PICO_CAPABILITIES = (CAPABILITIES & ~CAP_TERMINAL_KBD) | CAP_CLOCK_SYNC | CAP_NATIVE_320;
void put16(u8 *p, u16 n) {
  p[0] = (u8)n;
  p[1] = (u8)(n >> 8);
}
u16 get16(const u8 *p) { return (u16)((u16)p[0] | (u16)p[1] << 8); }
} // namespace
void UsbScreen::disconnect() {
  attached_ = caps_ = pong_ = native_ = false;
  stage_ = 0;
  force_ = true;
  keys_.abortPending();
  // Finish an already-started packet before another writer uses CDC.
}
void UsbScreen::enable(bool on) {
  enabled_ = on;
  if (!on)
    disconnect();
  next_offer_ = 0;
}
bool UsbScreen::packet(MessageType type, const u8 *data, unsigned size) {
  if (pending_)
    return false;
  if (encoder_.encode(type, 0, sequence_++, data, size) != Status::OK) {
    ++errors_;
    return false;
  }
  offset_ = 0;
  pending_ = (unsigned)encoder_.size();
  return true;
}
int UsbScreen::receive(u8 value, u32 now) {
  const auto result = parser_.push(value);
  if (result == MultiplexPushResult::TERMINAL_BYTE)
    return parser_.terminalByte();
  if (result == MultiplexPushResult::ERROR) {
    ++errors_;
    return -1;
  }
  if (result != MultiplexPushResult::PACKET)
    return -1;
  const auto &p = parser_.packet();
  if(p.type == MessageType::ACTIVATE && p.payload_size == 0) {
    enable(true);
    return -1;
  }
  if(p.type == MessageType::CLOCK_SYNC) {
    // mode 0: read; 1: set only an unset clock; 2: explicit overwrite.
    // This framed service works without attaching or taking the display.
    const bool shape = p.payload_size == 8 && p.payload[0] <= 2;
    bool ok = shape;
    if(shape && p.payload[0] && (p.payload[0] == 2 || !clock::configured())) {
      const clock::DateTime date{get16(p.payload + 1), p.payload[3], p.payload[4],
                                  p.payload[5], p.payload[6], p.payload[7]};
      ok = clock::set(date);
    }
    const auto date = clock::get();
    clock_state_[0] = ok ? 0 : 1;
    clock_state_[1] = clock::configured();
    put16(clock_state_ + 2, (u16)date.year);
    clock_state_[4] = (u8)date.month;clock_state_[5] = (u8)date.day;
    clock_state_[6] = (u8)date.hour;clock_state_[7] = (u8)date.minute;clock_state_[8] = (u8)date.second;
    clock_reply_ = true;
    return -1;
  }
  if (!enabled_)
    return -1;
  if (p.type == MessageType::ATTACH) {
    if(p.payload_size && (p.payload_size!=1 || p.payload[0]!=1)) { ++errors_;return -1; }
    disconnect();
    native_=p.payload_size==1 && backend_.native_begin && backend_.native_page;
    attached_ = caps_ = true;
    force_ = true;
    last_seen_ = now;
    next_ping_ = now + 1000;
    return -1;
  }
  if (!attached_)
    return -1;
  last_seen_ = now;
  switch (p.type) {
  case MessageType::DETACH:
    disconnect();
    next_offer_ = now + 500;
    break;
  case MessageType::PING:
    if (p.payload_size == 2) {
      pong_value_ = get16(p.payload);
      pong_ = true;
    } else
      ++errors_;
    break;
  case MessageType::PONG:
    break;
  case MessageType::REQUEST_KEYFRAME:
    force_ = true;
    break;
  case MessageType::KEY_EVENT:
    if (p.payload_size == 2 && p.payload[1] <= 1) {
      const auto q = keys_.enqueue(p.payload[0], p.payload[1] != 0);
      if (q == usb_screen::VirtualKeyQueue::EnqueueResult::FULL ||
          q == usb_screen::VirtualKeyQueue::EnqueueResult::INVALID) {
        ++errors_;
        keys_.abortPending();
      }
    } else
      ++errors_;
    break;
  case MessageType::RELEASE_ALL_KEYS:
    keys_.scheduleReleaseAll();
    break;
  default:
    break;
  }
  return -1;
}
bool UsbScreen::key(KeyEvent &event) {
  (void)keys_.stageNextRelease();
  const i32 raw = keys_.front();
  if (raw < 0)
    return false;
  const unsigned scan = (unsigned)raw & ~keyboard_core::RELEASE_MASK;
  event = {(u8)((raw & keyboard_core::RELEASE_MASK) ? 3 : 1),
           controls::from_scan(scan),(u8)scan};
  keys_.markFrontDelivered();
  return event.code != 0;
}
void UsbScreen::tick(u32 now, bool connected) {
  if (!backend_.write || !backend_.available || !backend_.frame)
    return;
  if (!connected) {
    disconnect();
    pending_ = offset_ = 0;
    clock_reply_ = false;
    parser_.reset();
    return;
  }
  if (pending_) {
    unsigned count = backend_.available(backend_.context);
    if (count > pending_)
      count = pending_;
    // The whole framed packet enters the CDC FIFO in one foreground
    // operation. Diagnostic text can only appear between packets.
    if (!offset_ && count < pending_)
      return;
    if (count) {
      const unsigned written =
          backend_.write(backend_.context, encoder_.data() + offset_, count);
      offset_ += written;
      pending_ -= written;
    }
    if (pending_)
      return;
  }
  if(clock_reply_) {
    if(packet(MessageType::CLOCK_STATE, clock_state_, sizeof(clock_state_))) clock_reply_ = false;
    return;
  }
  if (!enabled_)
    return;
  if (attached_ && (u32)(now - last_seen_) >= 3000)
    disconnect();
  if (!attached_) {
    if ((i32)(now - next_offer_) < 0)
      return;
    u8 p[10]{};
    put16(p, 192);
    p[2] = 64;
    p[3] = 8;
    put16(p + 4, PICO_CAPABILITIES);
    put16(p + 6, 3000);
    p[8] = 0;
    p[9] = keyboard_core::KEY_COUNT;
    packet(MessageType::OFFER, p, sizeof(p));
    next_offer_ = now + 500;
    return;
  }
  if (caps_) {
    u8 p[16]{};
    put16(p, native_?320:192);
    p[2] = 64;
    p[3] = 8;
    put16(p + 4, PICO_CAPABILITIES);
    put16(p + 6, 3000);
    p[8] = 0;
    p[9] = keyboard_core::KEY_COUNT;
    p[10] = 8;
    p[11] = 6;
    p[12] = 8;
    p[13] = 0;
    if(native_) put16(p+14,320);
    if (packet(MessageType::CAPS, p, native_?16:14))
      caps_ = false;
    return;
  }
  if (pong_) {
    u8 p[2];
    put16(p, pong_value_);
    if (packet(MessageType::PONG, p, 2))
      pong_ = false;
    return;
  }
  if ((i32)(now - next_ping_) >= 0) {
    u8 p[2];
    put16(p, ++ping_);
    packet(MessageType::PING, p, 2);
    next_ping_ = now + 1000;
    return;
  }
  if (stage_ == 0) {
    if ((i32)(now - next_frame_) < 0)
      return;
    next_frame_ = now + 80;
    if(native_) { backend_.native_begin(backend_.context);native_crc_=0xFFFF; }
    else backend_.frame(backend_.context, frame_);
    if (!native_ && !force_ && !std::memcmp(frame_, previous_, sizeof(frame_)))
      return;
    force_ = false;
    ++frame_id_;
    stage_ = 1;
  }
  if (stage_ == 1) {
    u8 p[4];
    put16(p, frame_id_);
    p[2] = 1;
    p[3] = native_?80:8;
    if (packet(MessageType::FRAME_BEGIN, p, 4))
      ++stage_;
    return;
  }
  if(native_ && stage_<=81) {
    const unsigned chunk=stage_-2,x=(chunk&1)*160,page=chunk/2;
    u8 p[166];put16(p,frame_id_);p[2]=(u8)x;p[3]=(u8)page;p[4]=160;p[5]=(u8)Codec::RAW;
    backend_.native_page(backend_.context,x,page,p+6,160);
    if(packet(MessageType::RECT,p,sizeof(p))) {
      for(unsigned i=6;i<sizeof(p);++i) {
        native_crc_^=(u16)p[i]<<8;
        for(unsigned bit=0;bit<8;++bit) native_crc_=(native_crc_&0x8000)?(u16)((native_crc_<<1)^0x1021):(u16)(native_crc_<<1);
      }
      ++stage_;
    }
    return;
  }
  if (!native_ && stage_ <= 9) {
    u8 p[MAX_PAYLOAD_SIZE];
    usize size = 0;
    Codec codec;
    const u8 page = (u8)(stage_ - 2);
    if (encode_rect_payload(frame_id_, {0, page, 192}, frame_ + page * 192, p,
                            sizeof(p), size, codec) == Status::OK &&
        packet(MessageType::RECT, p, (unsigned)size))
      ++stage_;
    return;
  }
  u8 p[4];
  put16(p, frame_id_);
  put16(p + 2, native_?native_crc_:crc16_ccitt(frame_, sizeof(frame_)));
  if (packet(MessageType::FRAME_END, p, 4)) {
    if(!native_) std::memcpy(previous_, frame_, sizeof(frame_));
    stage_ = 0;
    ++frames_;
  }
}
} // namespace picocalc
