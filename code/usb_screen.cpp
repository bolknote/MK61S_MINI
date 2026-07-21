#include "usb_screen.hpp"

#if MK61_ENABLE_USB_SCREEN

#include "display.hpp"
#include "keyboard.h"
#include "keyboard_layout.hpp"
#include "runtime_safety.hpp"
#include "usb_screen_protocol.hpp"

#include <Arduino.h>
#include <string.h>

namespace usb_screen {
namespace {

using usb_screen_protocol::MessageType;

static constexpr t_time_ms OFFER_INTERVAL_MS = 500;
static constexpr t_time_ms HEARTBEAT_TIMEOUT_MS = 3000;
static constexpr t_time_ms ESCAPE_HOLD_MS = 1500;
static constexpr usize RX_BUDGET_PER_SERVICE = 96;
static constexpr u16 TERMINAL_RX_CAPACITY = 256;

enum class FrameStage : u8 {
  IDLE,
  BEGIN,
  RECTS,
  END,
};

struct PendingResponse {
  bool valid;
  MessageType type;
  u8 payload[usb_screen_protocol::CAPS_PAYLOAD_SIZE];
  u8 size;
};

struct TerminalRxFifo {
  u8 bytes[TERMINAL_RX_CAPACITY];
  u16 head;
  u16 size;

  void clear(void) {
    head = 0;
    size = 0;
  }

  bool push(u8 value) {
    if(size >= TERMINAL_RX_CAPACITY) return false;
    const u16 tail = (u16) ((head + size) & (TERMINAL_RX_CAPACITY - 1));
    bytes[tail] = value;
    size++;
    return true;
  }

  bool pop(u8& value) {
    if(size == 0) return false;
    value = bytes[head];
    head = (u16) ((head + 1) & (TERMINAL_RX_CAPACITY - 1));
    size--;
    return true;
  }
};

static_assert((TERMINAL_RX_CAPACITY & (TERMINAL_RX_CAPACITY - 1)) == 0,
              "terminal FIFO capacity must be a power of two");

struct Session {
  State state;
  Event event;
  usb_screen_protocol::MultiplexParser parser;
  usb_screen_protocol::PacketEncoder encoder;
  usize tx_offset;
  u16 tx_sequence;
  u16 frame_id;
  u16 frame_crc;
  FrameStage frame_stage;
  u8 frame_run;
  u32 frame_revision;
  u32 sent_revision;
  bool resend_requested;
  u8 snapshot[usb_screen_protocol::FRAME_BYTES];
  u8 rect_payload[usb_screen_protocol::MAX_PAYLOAD_SIZE];
  PendingResponse response;
  t_time_ms next_offer_ms;
  t_time_ms last_host_packet_ms;
  t_time_ms escape_pressed_ms;
  u64 virtual_pressed;
  bool release_all_pending;
  keyboard_core::FixedFifo<keyboard_core::KEY_COUNT * 2> virtual_events;
  TerminalRxFifo terminal_rx;
};

static Session session = {};

static inline void writeU16(u8* output, u16 value) {
  output[0] = (u8) value;
  output[1] = (u8) (value >> 8);
}

static usb_screen_protocol::KeyboardLayout keyboardLayout(void) {
#if defined(MK61_KEYBOARD_CLASSIC)
  return usb_screen_protocol::KeyboardLayout::CLASSIC;
#elif defined(MK61_KEYBOARD_40TH)
  return usb_screen_protocol::KeyboardLayout::FORTIETH;
#else
  return usb_screen_protocol::KeyboardLayout::MINI;
#endif
}

static void fillCapabilities(u8* payload, bool include_profile) {
  writeU16(payload, usb_screen_protocol::SCREEN_WIDTH);
  payload[2] = usb_screen_protocol::SCREEN_HEIGHT;
  payload[3] = usb_screen_protocol::PAGE_HEIGHT;
  writeU16(payload + 4, usb_screen_protocol::CAPABILITIES);
  writeU16(payload + 6, (u16) HEARTBEAT_TIMEOUT_MS);
  payload[8] = (u8) keyboardLayout();
  payload[9] = (u8) keyboard_core::KEY_COUNT;
  if(include_profile) {
    const lcd_display::TextProfile profile = main_lcd().textProfile();
    payload[10] = profile.rows;
    payload[11] = profile.glyph_width;
    payload[12] = profile.glyph_height;
    payload[13] = profile.line_gap;
  }
}

static bool txPending(void) {
  return session.tx_offset < session.encoder.size();
}

static bool queuePacket(MessageType type, const u8* payload, usize size,
                        u8 flags = 0) {
  if(txPending()) return false;
  const usb_screen_protocol::Status status = session.encoder.encode(
    type, flags, session.tx_sequence++, payload, size);
  if(status != usb_screen_protocol::Status::OK) return false;
  session.tx_offset = 0;
  return true;
}

static void queueResponse(MessageType type, const u8* payload, usize size) {
  if(size > sizeof(session.response.payload)) return;
  session.response.valid = true;
  session.response.type = type;
  session.response.size = (u8) size;
  if(size != 0) memcpy(session.response.payload, payload, size);
}

static void pumpTx(void) {
  if(!txPending()) return;
  const int available = Serial.availableForWrite();
  if(available <= 0) return;
  usize remaining = session.encoder.size() - session.tx_offset;
  usize chunk = remaining < (usize) available ? remaining : (usize) available;
  const usize written = Serial.write(session.encoder.data() +
                                     session.tx_offset, chunk);
  if(written <= remaining) session.tx_offset += written;
  // With no host DTR, USBSerial::write() returns zero although its software
  // queue reports free space. Do not let an unsent OFFER stall background
  // work forever; a fresh offer will be generated after reconnection.
  if(written == 0 && session.state == State::WAITING_FOR_HOST) {
    session.tx_offset = session.encoder.size();
  }
}

static void scheduleReleaseAll(void) {
  session.release_all_pending = session.virtual_pressed != 0;
}

static void serviceVirtualKeys(void) {
  if(session.release_all_pending) {
    for(u8 key = 0; key < keyboard_core::KEY_COUNT; key++) {
      const u64 bit = (u64) 1U << key;
      if((session.virtual_pressed & bit) == 0) continue;
      if(!session.virtual_events.push(key | keyboard_core::RELEASE_MASK)) break;
      session.virtual_pressed &= ~bit;
      kbd::set_external_key_pressed(key, false);
    }
    session.release_all_pending = session.virtual_pressed != 0;
  }

  const i32 event = session.virtual_events.peek();
  if(event >= 0 && kbd::push((i8) event)) session.virtual_events.pop();
}

static void setEvent(Event event) {
  if(session.event == Event::NONE) session.event = event;
}

static void resetFrameTransfer(void) {
  session.frame_stage = FrameStage::IDLE;
  session.frame_run = 0;
}

static void restorePhysicalAndWait(Event event) {
  if(main_lcd().usbScreenActive()) main_lcd().leaveUsbScreen();
  scheduleReleaseAll();
  resetFrameTransfer();
  session.resend_requested = true;
  session.tx_offset = session.encoder.size();
  session.response = {};
  session.state = State::WAITING_FOR_HOST;
  session.next_offer_ms = 0;
  session.escape_pressed_ms = 0;
  setEvent(event);
}

static void attach(t_time_ms now) {
  if(!main_lcd().enterUsbScreen()) return;
  session.state = State::ATTACHED;
  session.last_host_packet_ms = now;
  session.resend_requested = true;
  resetFrameTransfer();
  u8 caps[usb_screen_protocol::CAPS_PAYLOAD_SIZE] = {};
  fillCapabilities(caps, true);
  queueResponse(MessageType::CAPS, caps, sizeof(caps));
  setEvent(Event::ATTACHED);
}

static void handleKeyEvent(const usb_screen_protocol::PacketView& packet) {
  if(packet.payload_size != usb_screen_protocol::KEY_EVENT_PAYLOAD_SIZE) return;
  const u8 key = packet.payload[0];
  const bool down = packet.payload[1] != 0;
  if(key >= keyboard_core::KEY_COUNT || packet.payload[1] > 1) return;
  const u64 bit = (u64) 1U << key;
  if(down) {
    if((session.virtual_pressed & bit) != 0) return;
    if(session.virtual_events.push(key)) {
      session.virtual_pressed |= bit;
      kbd::set_external_key_pressed(key, true);
    } else {
      scheduleReleaseAll();
    }
  } else {
    if((session.virtual_pressed & bit) == 0) return;
    if(session.virtual_events.push(key | keyboard_core::RELEASE_MASK)) {
      session.virtual_pressed &= ~bit;
      kbd::set_external_key_pressed(key, false);
    } else {
      scheduleReleaseAll();
    }
  }
}

static void handlePacket(const usb_screen_protocol::PacketView& packet,
                         t_time_ms now) {
  if(session.state == State::WAITING_FOR_HOST) {
    if(packet.type == MessageType::ATTACH && packet.payload_size == 0) {
      attach(now);
    }
    return;
  }
  if(session.state != State::ATTACHED) return;

  session.last_host_packet_ms = now;
  switch(packet.type) {
    case MessageType::DETACH:
      restorePhysicalAndWait(Event::CONNECTION_LOST);
      break;
    case MessageType::PING:
      if(packet.payload_size == usb_screen_protocol::PING_PAYLOAD_SIZE) {
        queueResponse(MessageType::PONG, packet.payload, packet.payload_size);
      }
      break;
    case MessageType::PONG:
      break;
    case MessageType::REQUEST_KEYFRAME:
      session.resend_requested = true;
      break;
    case MessageType::KEY_EVENT:
      handleKeyEvent(packet);
      break;
    case MessageType::RELEASE_ALL_KEYS:
      scheduleReleaseAll();
      break;
    default:
      break;
  }
}

static void readRx(t_time_ms now) {
  usize budget = RX_BUDGET_PER_SERVICE;
  while(budget-- != 0 && Serial.available() > 0) {
    const int value = Serial.read();
    if(value < 0) break;
    const usb_screen_protocol::MultiplexPushResult result =
      session.parser.push((u8) value);
    if(result == usb_screen_protocol::MultiplexPushResult::PACKET) {
      handlePacket(session.parser.packet(), now);
    } else if(result ==
              usb_screen_protocol::MultiplexPushResult::TERMINAL_BYTE) {
      (void) session.terminal_rx.push(session.parser.terminalByte());
    }
  }
}

static bool beginFrame(void) {
  main_lcd().flush();
  const u8* current = main_lcd().usbScreenFramebuffer();
  if(current == NULL) return false;
  memcpy(session.snapshot, current, sizeof(session.snapshot));
  session.frame_revision = main_lcd().usbScreenRevision();
  // Clear only the request captured by this snapshot. A new request arriving
  // while the frame is in flight remains set for the following transfer.
  session.resend_requested = false;
  session.frame_id++;
  session.frame_crc = usb_screen_protocol::crc16_ccitt(
    session.snapshot, sizeof(session.snapshot));
  session.frame_run = 0;
  session.frame_stage = FrameStage::BEGIN;
  return true;
}

static bool queueFramePacket(void) {
  switch(session.frame_stage) {
    case FrameStage::IDLE:
      return false;

    case FrameStage::BEGIN: {
      u8 payload[usb_screen_protocol::FRAME_BEGIN_PAYLOAD_SIZE] = {};
      writeU16(payload, session.frame_id);
      payload[2] = 1;
      payload[3] = usb_screen_protocol::PAGE_COUNT;
      if(!queuePacket(MessageType::FRAME_BEGIN, payload, sizeof(payload))) {
        return false;
      }
      session.frame_stage = FrameStage::RECTS;
      return true;
    }

    case FrameStage::RECTS: {
      if(session.frame_run >= usb_screen_protocol::PAGE_COUNT) {
        session.frame_stage = FrameStage::END;
        return queueFramePacket();
      }
      const usb_screen_protocol::PageRun area = {
        0, session.frame_run, (u8) usb_screen_protocol::SCREEN_WIDTH,
      };
      const u8* pixels = session.snapshot +
        (usize) area.page * usb_screen_protocol::SCREEN_WIDTH + area.x;
      usize payload_size = 0;
      usb_screen_protocol::Codec codec = usb_screen_protocol::Codec::RAW;
      if(usb_screen_protocol::encode_rect_payload(
           session.frame_id, area, pixels, session.rect_payload,
           sizeof(session.rect_payload), payload_size, codec) !=
         usb_screen_protocol::Status::OK) {
        session.resend_requested = true;
        resetFrameTransfer();
        return false;
      }
      (void) codec;
      if(!queuePacket(MessageType::RECT, session.rect_payload, payload_size)) {
        return false;
      }
      session.frame_run++;
      return true;
    }

    case FrameStage::END: {
      u8 payload[usb_screen_protocol::FRAME_END_PAYLOAD_SIZE] = {};
      writeU16(payload, session.frame_id);
      writeU16(payload + 2, session.frame_crc);
      if(!queuePacket(MessageType::FRAME_END, payload, sizeof(payload))) {
        return false;
      }
      session.sent_revision = session.frame_revision;
      resetFrameTransfer();
      return true;
    }
  }
  return false;
}

static void scheduleTx(t_time_ms now) {
  if(txPending()) return;
  if(session.response.valid) {
    if(queuePacket(session.response.type, session.response.payload,
                   session.response.size)) {
      session.response.valid = false;
    }
    return;
  }

  if(session.state == State::WAITING_FOR_HOST) {
    if(session.next_offer_ms == 0 ||
       runtime_safety::time_reached(now, session.next_offer_ms)) {
      u8 offer[usb_screen_protocol::OFFER_PAYLOAD_SIZE] = {};
      fillCapabilities(offer, false);
      if(queuePacket(MessageType::OFFER, offer, sizeof(offer))) {
        session.next_offer_ms = now + OFFER_INTERVAL_MS;
      }
    }
    return;
  }
  if(session.state != State::ATTACHED) return;

  if(session.frame_stage != FrameStage::IDLE) {
    (void) queueFramePacket();
    return;
  }
  if(session.resend_requested ||
     main_lcd().usbScreenRevision() != session.sent_revision) {
    if(beginFrame()) (void) queueFramePacket();
  }
}

static void serviceEscapeHold(t_time_ms now) {
  if(session.state == State::IDLE) return;
  const i32 escape = keyboard_layout::ACTIVE.esc;
  if(!kbd::is_physical_key_pressed(escape)) {
    session.escape_pressed_ms = 0;
    return;
  }
  if(session.escape_pressed_ms == 0) {
    session.escape_pressed_ms = now == 0 ? 1 : now;
    return;
  }
  if((t_time_ms) (now - session.escape_pressed_ms) >= ESCAPE_HOLD_MS) {
    cancel();
  }
}

} // namespace

bool start(void) {
  if(session.state != State::IDLE) return true;
  session.parser.reset();
  session.state = State::WAITING_FOR_HOST;
  session.event = Event::NONE;
  session.tx_offset = session.encoder.size();
  session.tx_sequence = 0;
  session.frame_id = 0;
  session.sent_revision = 0;
  session.resend_requested = true;
  session.response = {};
  session.next_offer_ms = 0;
  session.last_host_packet_ms = millis();
  session.escape_pressed_ms = 0;
  session.terminal_rx.clear();
  resetFrameTransfer();
  return true;
}

void cancel(void) {
  if(session.state == State::IDLE) return;
  if(main_lcd().usbScreenActive()) main_lcd().leaveUsbScreen();
  scheduleReleaseAll();
  resetFrameTransfer();
  session.tx_offset = session.encoder.size();
  session.response = {};
  session.state = State::IDLE;
  session.escape_pressed_ms = 0;
  session.terminal_rx.clear();
  setEvent(Event::EXITED);
}

void service(void) {
  const t_time_ms now = millis();
  serviceVirtualKeys();
  if(session.state == State::IDLE) return;
  readRx(now);
  if(session.state == State::ATTACHED &&
     (t_time_ms) (now - session.last_host_packet_ms) >=
       HEARTBEAT_TIMEOUT_MS) {
    restorePhysicalAndWait(Event::CONNECTION_LOST);
  }
  serviceEscapeHold(now);
  pumpTx();
  scheduleTx(now);
  pumpTx();
}

State state(void) { return session.state; }
bool active(void) { return session.state != State::IDLE; }
bool attached(void) { return session.state == State::ATTACHED; }
bool wireBusy(void) { return txPending(); }

bool takeTerminalByte(u8& value) {
  return session.terminal_rx.pop(value);
}

Event takeEvent(void) {
  const Event event = session.event;
  session.event = Event::NONE;
  return event;
}

} // namespace usb_screen

#endif // MK61_ENABLE_USB_SCREEN
