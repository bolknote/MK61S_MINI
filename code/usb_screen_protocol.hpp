#ifndef MK61_USB_SCREEN_PROTOCOL_HPP
#define MK61_USB_SCREEN_PROTOCOL_HPP

#include "rust_types.h"

namespace usb_screen_protocol {

static constexpr u16 SCREEN_WIDTH = 192;
static constexpr u8 SCREEN_HEIGHT = 64;
static constexpr u8 PAGE_HEIGHT = 8;
static constexpr u8 PAGE_COUNT = SCREEN_HEIGHT / PAGE_HEIGHT;
static constexpr usize FRAME_BYTES =
  (usize) SCREEN_WIDTH * SCREEN_HEIGHT / 8;

static constexpr u8 PROTOCOL_VERSION = 2;
static constexpr u8 MAGIC_0 = 'M';
static constexpr u8 MAGIC_1 = 'S';
static constexpr usize HEADER_SIZE = 9;
static constexpr usize CRC_SIZE = 2;
static constexpr usize MAX_PAYLOAD_SIZE = 224;
static constexpr usize MAX_RAW_PACKET =
  HEADER_SIZE + MAX_PAYLOAD_SIZE + CRC_SIZE;
// COBS adds at most one code byte per 254 input bytes. USB Screen v2 wraps
// every packet in leading and trailing zeroes, leaving all non-framed bytes
// available to the interactive terminal on the same CDC byte stream.
static constexpr usize MAX_FRAMED_PACKET =
  MAX_RAW_PACKET + (MAX_RAW_PACKET / 254) + 3;

static constexpr usize RECT_HEADER_SIZE = 6;
static constexpr u8 MAX_DIFF_RUNS = 32;
static constexpr u8 DIFF_MERGE_GAP = 2;

enum class MessageType : u8 {
  OFFER = 0x10,
  ATTACH = 0x11,
  CAPS = 0x12,
  DETACH = 0x13,
  PING = 0x14,
  PONG = 0x15,
  REQUEST_KEYFRAME = 0x16,

  FRAME_BEGIN = 0x20,
  RECT = 0x21,
  FRAME_END = 0x22,

  KEY_EVENT = 0x30,
  RELEASE_ALL_KEYS = 0x31,
};

enum class Codec : u8 {
  RAW = 0,
  PACKBITS = 1,
};

enum Capability : u16 {
  CAP_DIFF = 1U << 0,
  CAP_PACKBITS = 1U << 1,
  CAP_KEY_EVENTS = 1U << 2,
  CAP_HEARTBEAT = 1U << 3,
  CAP_ATOMIC_FRAMES = 1U << 4,
  CAP_TERMINAL_MUX = 1U << 5,
};

static constexpr u16 CAPABILITIES =
  CAP_PACKBITS | CAP_KEY_EVENTS | CAP_HEARTBEAT | CAP_ATOMIC_FRAMES |
  CAP_TERMINAL_MUX;
static constexpr usize OFFER_PAYLOAD_SIZE = 10;
static constexpr usize CAPS_PAYLOAD_SIZE = 14;
static constexpr usize FRAME_BEGIN_PAYLOAD_SIZE = 4;
static constexpr usize FRAME_END_PAYLOAD_SIZE = 4;
static constexpr usize PING_PAYLOAD_SIZE = 2;
static constexpr usize KEY_EVENT_PAYLOAD_SIZE = 2;

enum class KeyboardLayout : u8 {
  MINI = 0,
  CLASSIC = 1,
  FORTIETH = 2,
};

enum class Status : u8 {
  OK,
  INVALID_ARGUMENT,
  OUTPUT_TOO_SMALL,
  MALFORMED_COBS,
  BAD_MAGIC,
  BAD_VERSION,
  BAD_LENGTH,
  BAD_CRC,
  MALFORMED_PACKBITS,
  INVALID_RECT,
  UNSUPPORTED_CODEC,
  OVERFLOW,
};

enum class PushResult : u8 {
  NONE,
  PACKET,
  ERROR,
};

enum class MultiplexPushResult : u8 {
  NONE,
  PACKET,
  TERMINAL_BYTE,
  ERROR,
};

struct PacketView {
  MessageType type;
  u8 flags;
  u16 sequence;
  const u8* payload;
  usize payload_size;
};

struct PageRun {
  u8 x;
  u8 page;
  u8 width;
};

struct DiffPlan {
  PageRun runs[MAX_DIFF_RUNS];
  u8 count;
  bool keyframe;
};

struct CodecSelection {
  Codec codec;
  usize size;
};

struct RectView {
  u16 frame_id;
  PageRun area;
  Codec codec;
  const u8* encoded;
  usize encoded_size;
};

u16 crc16_ccitt(const u8* data, usize size);

Status cobs_encode(const u8* input, usize input_size,
                   u8* output, usize output_capacity,
                   usize& output_size);
Status cobs_decode(const u8* input, usize input_size,
                   u8* output, usize output_capacity,
                   usize& output_size);

Status packbits_encode(const u8* input, usize input_size,
                       u8* output, usize output_capacity,
                       usize& output_size);
Status packbits_decode(const u8* input, usize input_size,
                       u8* output, usize output_capacity,
                       usize expected_size, usize& output_size);

Status encode_best(const u8* input, usize input_size,
                   u8* output, usize output_capacity,
                   CodecSelection& selection);

Status plan_diff(const u8* previous, const u8* current,
                 DiffPlan& plan, bool force_keyframe = false);

Status encode_rect_payload(u16 frame_id, PageRun area,
                           const u8* pixels,
                           u8* output, usize output_capacity,
                           usize& output_size, Codec& codec);
Status parse_rect_payload(const u8* payload, usize payload_size,
                          RectView& rect);
Status decode_rect_pixels(const RectView& rect,
                          u8* output, usize output_capacity);

class PacketEncoder {
  public:
    constexpr PacketEncoder(void)
      : raw{}, framed{}, framed_size(0) {}

    Status encode(MessageType type, u8 flags, u16 sequence,
                  const u8* payload, usize payload_size);
    const u8* data(void) const { return framed; }
    usize size(void) const { return framed_size; }

  private:
    u8 raw[MAX_RAW_PACKET];
    u8 framed[MAX_FRAMED_PACKET];
    usize framed_size;
};

class StreamParser {
  public:
    constexpr StreamParser(void)
      : encoded{}, decoded{}, encoded_size(0), overflowed(false),
        current_packet{}, last_status(Status::OK) {}

    void reset(void);
    PushResult push(u8 value);
    const PacketView& packet(void) const { return current_packet; }
    Status status(void) const { return last_status; }

  private:
    u8 encoded[MAX_FRAMED_PACKET];
    u8 decoded[MAX_RAW_PACKET];
    usize encoded_size;
    bool overflowed;
    PacketView current_packet;
    Status last_status;

    Status parse_decoded(usize decoded_size);
};

// Splits a v2 CDC stream into 0/COBS/0 packets and raw terminal bytes. The
// contained StreamParser owns all packet storage, so this wrapper adds only
// framing state and one returned terminal byte.
class MultiplexParser {
  public:
    constexpr MultiplexParser(void)
      : parser(), inside_packet(false), packet_nonempty(false),
        terminal_value(0) {}

    void reset(void);
    MultiplexPushResult push(u8 value);
    const PacketView& packet(void) const { return parser.packet(); }
    u8 terminalByte(void) const { return terminal_value; }
    Status status(void) const { return parser.status(); }

  private:
    StreamParser parser;
    bool inside_packet;
    bool packet_nonempty;
    u8 terminal_value;
};

const char* status_text(Status status);

} // namespace usb_screen_protocol

#endif
