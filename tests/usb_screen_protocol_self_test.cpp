#include "usb_screen_protocol.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

using namespace usb_screen_protocol;

namespace {

static void test_cobs_roundtrip(void) {
  const u8 source[] = {0, 1, 2, 0, 3, 0, 0, 4, 5};
  u8 encoded[32] = {};
  u8 decoded[sizeof(source)] = {};
  usize encoded_size = 0;
  usize decoded_size = 0;
  assert(cobs_encode(source, sizeof(source), encoded, sizeof(encoded),
                     encoded_size) == Status::OK);
  for(usize i = 0; i < encoded_size; i++) assert(encoded[i] != 0);
  assert(cobs_decode(encoded, encoded_size, decoded, sizeof(decoded),
                     decoded_size) == Status::OK);
  assert(decoded_size == sizeof(source));
  assert(memcmp(source, decoded, sizeof(source)) == 0);

  const u8 malformed[] = {3, 1};
  assert(cobs_decode(malformed, sizeof(malformed), decoded, sizeof(decoded),
                     decoded_size) == Status::MALFORMED_COBS);
}

static void assert_packbits_roundtrip(const u8* source, usize size,
                                      bool expect_smaller) {
  u8 packed[256] = {};
  u8 decoded[256] = {};
  usize packed_size = 0;
  usize decoded_size = 0;
  assert(packbits_encode(source, size, packed, sizeof(packed), packed_size) ==
         Status::OK);
  assert((packed_size < size) == expect_smaller);
  assert(packbits_decode(packed, packed_size, decoded, sizeof(decoded), size,
                         decoded_size) == Status::OK);
  assert(decoded_size == size);
  assert(memcmp(source, decoded, size) == 0);
}

static void test_packbits(void) {
  u8 blank[192] = {};
  assert_packbits_roundtrip(blank, sizeof(blank), true);

  u8 literal[192] = {};
  for(usize i = 0; i < sizeof(literal); i++) literal[i] = (u8) i;
  assert_packbits_roundtrip(literal, sizeof(literal), false);

  const u8 mixed[] = {
    1, 2, 3, 3, 4, 4, 4, 4, 5, 6, 7, 8, 8, 8, 9, 10,
  };
  assert_packbits_roundtrip(mixed, sizeof(mixed), false);

  u8 output[8] = {};
  usize output_size = 0;
  const u8 no_op[] = {0x80};
  assert(packbits_decode(no_op, sizeof(no_op), output, sizeof(output), 0,
                         output_size) == Status::MALFORMED_PACKBITS);
  const u8 missing_literal[] = {3, 1, 2};
  assert(packbits_decode(missing_literal, sizeof(missing_literal), output,
                         sizeof(output), 4, output_size) ==
         Status::MALFORMED_PACKBITS);
  const u8 missing_repeat[] = {0xFF};
  assert(packbits_decode(missing_repeat, sizeof(missing_repeat), output,
                         sizeof(output), 2, output_size) ==
         Status::MALFORMED_PACKBITS);
}

static void test_packet_roundtrip_and_resync(void) {
  const u8 payload[] = {1, 0, 2, 3, 0, 4};
  PacketEncoder encoder;
  assert(encoder.encode(MessageType::CAPS, 0xA5, 0x1234,
                        payload, sizeof(payload)) == Status::OK);
  assert(encoder.size() > sizeof(payload));
  assert(encoder.data()[0] == 0);
  assert(encoder.data()[encoder.size() - 1] == 0);

  StreamParser parser;
  for(usize i = 1; i + 1 < encoder.size(); i++) {
    assert(parser.push(encoder.data()[i]) == PushResult::NONE);
  }
  assert(parser.push(0) == PushResult::PACKET);
  const PacketView& packet = parser.packet();
  assert(packet.type == MessageType::CAPS);
  assert(packet.flags == 0xA5);
  assert(packet.sequence == 0x1234);
  assert(packet.payload_size == sizeof(payload));
  assert(memcmp(packet.payload, payload, sizeof(payload)) == 0);

  parser.reset();
  for(usize i = 1; i < encoder.size(); i++) {
    const PushResult result = parser.push(encoder.data()[i]);
    if(i + 1 == encoder.size()) assert(result == PushResult::PACKET);
    else assert(result == PushResult::NONE);
  }
}

static void test_packet_crc_rejection(void) {
  PacketEncoder encoder;
  const u8 payload[] = {9, 8, 7, 6};
  assert(encoder.encode(MessageType::PING, 0, 17, payload,
                        sizeof(payload)) == Status::OK);
  u8 raw[MAX_RAW_PACKET] = {};
  u8 damaged[MAX_FRAMED_PACKET] = {};
  usize raw_size = 0;
  usize damaged_size = 0;
  assert(cobs_decode(encoder.data() + 1, encoder.size() - 2, raw, sizeof(raw),
                     raw_size) == Status::OK);
  raw[HEADER_SIZE] ^= 0x40; // полезная нагрузка меняется, сохранённая CRC намеренно нет
  assert(cobs_encode(raw, raw_size, damaged, sizeof(damaged) - 1,
                     damaged_size) == Status::OK);
  damaged[damaged_size++] = 0;

  StreamParser parser;
  PushResult final_result = PushResult::NONE;
  for(usize i = 0; i < damaged_size; i++) {
    final_result = parser.push(damaged[i]);
  }
  assert(final_result == PushResult::ERROR);
  assert(parser.status() == Status::BAD_CRC);
}

static void test_terminal_multiplex(void) {
  const u8 payload[] = {7, 0};
  PacketEncoder encoder;
  assert(encoder.encode(MessageType::PONG, 0, 99, payload,
                        sizeof(payload)) == Status::OK);

  MultiplexParser parser;
  const char prefix[] = "MK61> ver\r\n";
  usize terminal_index = 0;
  for(usize i = 0; i < sizeof(prefix) - 1; i++) {
    assert(parser.push((u8) prefix[i]) ==
           MultiplexPushResult::TERMINAL_BYTE);
    assert(parser.terminalByte() == (u8) prefix[terminal_index++]);
  }

  MultiplexPushResult result = MultiplexPushResult::NONE;
  for(usize i = 0; i < encoder.size(); i++) result = parser.push(encoder.data()[i]);
  assert(result == MultiplexPushResult::PACKET);
  assert(parser.packet().type == MessageType::PONG);
  assert(parser.packet().sequence == 99);
  assert(memcmp(parser.packet().payload, payload, sizeof(payload)) == 0);

  // Между соседними пакетами в кадрах допустимы два граничных нуля.
  assert(parser.push(0) == MultiplexPushResult::NONE);
  for(usize i = 1; i < encoder.size(); i++) result = parser.push(encoder.data()[i]);
  assert(result == MultiplexPushResult::PACKET);
}

static void test_diff_plan(void) {
  u8 previous[FRAME_BYTES] = {};
  u8 current[FRAME_BYTES] = {};
  DiffPlan plan = {};

  assert(plan_diff(previous, current, plan) == Status::OK);
  assert(plan.count == 0);
  assert(!plan.keyframe);

  current[2 * SCREEN_WIDTH + 10] = 1;
  current[2 * SCREEN_WIDTH + 13] = 2; // промежуток 2 объединяется
  assert(plan_diff(previous, current, plan) == Status::OK);
  assert(plan.count == 1);
  assert(plan.runs[0].page == 2);
  assert(plan.runs[0].x == 10);
  assert(plan.runs[0].width == 4);

  assert(plan_diff(previous, current, plan, true) == Status::OK);
  assert(plan.keyframe);
  assert(plan.count == PAGE_COUNT);
  for(u8 page = 0; page < PAGE_COUNT; page++) {
    assert(plan.runs[page].page == page);
    assert(plan.runs[page].x == 0);
    assert(plan.runs[page].width == SCREEN_WIDTH);
  }

  memset(current, 0, sizeof(current));
  for(u16 x = 0; x < SCREEN_WIDTH; x += 4) current[x] = 0x55;
  assert(plan_diff(previous, current, plan) == Status::OK);
  // Множество маленьких прямоугольников на одной странице дешевле передать всей страницей.
  assert(plan.count == 1);
  assert(plan.runs[0].x == 0);
  assert(plan.runs[0].width == SCREEN_WIDTH);
}

static void test_rect_payload(void) {
  u8 source[192] = {};
  memset(source, 0xAA, sizeof(source));
  u8 payload[MAX_PAYLOAD_SIZE] = {};
  usize payload_size = 0;
  Codec codec = Codec::RAW;
  const PageRun area = {0, 3, 192};
  assert(encode_rect_payload(42, area, source, payload, sizeof(payload),
                             payload_size, codec) == Status::OK);
  assert(codec == Codec::PACKBITS);
  assert(payload_size < RECT_HEADER_SIZE + sizeof(source));

  RectView rect = {};
  assert(parse_rect_payload(payload, payload_size, rect) == Status::OK);
  assert(rect.frame_id == 42);
  assert(rect.area.x == 0);
  assert(rect.area.page == 3);
  assert(rect.area.width == 192);
  u8 decoded[192] = {};
  assert(decode_rect_pixels(rect, decoded, sizeof(decoded)) == Status::OK);
  assert(memcmp(source, decoded, sizeof(source)) == 0);

  payload[4] = 0;
  assert(parse_rect_payload(payload, payload_size, rect) ==
         Status::INVALID_RECT);
}

} // безымянное пространство имён

int main(void) {
  static_assert(FRAME_BYTES == 1536, "unexpected framebuffer size");
  test_cobs_roundtrip();
  test_packbits();
  test_packet_roundtrip_and_resync();
  test_packet_crc_rejection();
  test_terminal_multiplex();
  test_diff_plan();
  test_rect_payload();
  assert(strcmp(status_text(Status::OK), "ok") == 0);
  printf("usb_screen_protocol_self_test: ok\n");
  return 0;
}
