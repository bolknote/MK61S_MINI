#include "usb_screen_protocol.hpp"

#include <string.h>

namespace usb_screen_protocol {

namespace {

static constexpr usize RECT_WIRE_OVERHEAD = RECT_HEADER_SIZE + HEADER_SIZE + CRC_SIZE;

static inline void write_u16_le(u8* out, u16 value) {
  out[0] = (u8) value;
  out[1] = (u8) (value >> 8);
}

static inline u16 read_u16_le(const u8* in) {
  return (u16) in[0] | ((u16) in[1] << 8);
}

static bool valid_page_run(PageRun area) {
  return area.width != 0 && area.page < PAGE_COUNT &&
    area.x < SCREEN_WIDTH &&
    (u16) area.x + area.width <= SCREEN_WIDTH;
}

static void make_keyframe(DiffPlan& plan) {
  plan.count = PAGE_COUNT;
  plan.keyframe = true;
  for(u8 page = 0; page < PAGE_COUNT; page++) {
    plan.runs[page] = {0, page, (u8) SCREEN_WIDTH};
  }
}

static bool add_run(DiffPlan& plan, PageRun run) {
  if(plan.count >= MAX_DIFF_RUNS) return false;
  plan.runs[plan.count++] = run;
  return true;
}

static usize repeated_count(const u8* input, usize size, usize at) {
  usize count = 1;
  while(at + count < size && count < 128 &&
        input[at + count] == input[at]) count++;
  return count;
}

} // namespace

u16 crc16_ccitt(const u8* data, usize size) {
  u16 crc = 0xFFFF;
  if(data == NULL && size != 0) return 0;
  for(usize i = 0; i < size; i++) {
    crc ^= (u16) data[i] << 8;
    for(u8 bit = 0; bit < 8; bit++) {
      crc = (crc & 0x8000U) != 0
        ? (u16) ((crc << 1) ^ 0x1021U)
        : (u16) (crc << 1);
    }
  }
  return crc;
}

Status cobs_encode(const u8* input, usize input_size,
                   u8* output, usize output_capacity,
                   usize& output_size) {
  output_size = 0;
  if((input == NULL && input_size != 0) || output == NULL) {
    return Status::INVALID_ARGUMENT;
  }
  if(output_capacity == 0) return Status::OUTPUT_TOO_SMALL;

  usize code_index = 0;
  usize write_index = 1;
  u8 code = 1;

  for(usize read_index = 0; read_index < input_size; read_index++) {
    if(input[read_index] == 0) {
      if(code_index >= output_capacity) return Status::OUTPUT_TOO_SMALL;
      output[code_index] = code;
      code_index = write_index;
      if(write_index >= output_capacity) return Status::OUTPUT_TOO_SMALL;
      write_index++;
      code = 1;
      continue;
    }

    if(write_index >= output_capacity) return Status::OUTPUT_TOO_SMALL;
    output[write_index++] = input[read_index];
    code++;
    if(code == 0xFF) {
      output[code_index] = code;
      code_index = write_index;
      if(write_index >= output_capacity) return Status::OUTPUT_TOO_SMALL;
      write_index++;
      code = 1;
    }
  }

  if(code_index >= output_capacity) return Status::OUTPUT_TOO_SMALL;
  output[code_index] = code;
  output_size = write_index;
  return Status::OK;
}

Status cobs_decode(const u8* input, usize input_size,
                   u8* output, usize output_capacity,
                   usize& output_size) {
  output_size = 0;
  if(input == NULL || input_size == 0 || output == NULL) {
    return Status::INVALID_ARGUMENT;
  }

  usize read_index = 0;
  usize write_index = 0;
  while(read_index < input_size) {
    const u8 code = input[read_index++];
    if(code == 0) return Status::MALFORMED_COBS;
    const usize copied = (usize) code - 1;
    if(copied > input_size - read_index) return Status::MALFORMED_COBS;
    if(copied > output_capacity - write_index) return Status::OUTPUT_TOO_SMALL;
    if(copied != 0) {
      memcpy(output + write_index, input + read_index, copied);
      write_index += copied;
      read_index += copied;
    }
    if(code != 0xFF && read_index < input_size) {
      if(write_index >= output_capacity) return Status::OUTPUT_TOO_SMALL;
      output[write_index++] = 0;
    }
  }

  output_size = write_index;
  return Status::OK;
}

Status packbits_encode(const u8* input, usize input_size,
                       u8* output, usize output_capacity,
                       usize& output_size) {
  output_size = 0;
  if((input == NULL && input_size != 0) || output == NULL) {
    return Status::INVALID_ARGUMENT;
  }

  usize source = 0;
  usize target = 0;
  while(source < input_size) {
    const usize run = repeated_count(input, input_size, source);
    if(run >= 3) {
      if(output_capacity - target < 2) return Status::OUTPUT_TOO_SMALL;
      output[target++] = (u8) (257 - run);
      output[target++] = input[source];
      source += run;
      continue;
    }

    const usize literal_start = source;
    source += run;
    while(source < input_size && source - literal_start < 128) {
      const usize next_run = repeated_count(input, input_size, source);
      if(next_run >= 3) break;
      const usize room = 128 - (source - literal_start);
      source += next_run < room ? next_run : room;
    }
    const usize literal_size = source - literal_start;
    if(output_capacity - target < literal_size + 1) {
      return Status::OUTPUT_TOO_SMALL;
    }
    output[target++] = (u8) (literal_size - 1);
    memcpy(output + target, input + literal_start, literal_size);
    target += literal_size;
  }

  output_size = target;
  return Status::OK;
}

Status packbits_decode(const u8* input, usize input_size,
                       u8* output, usize output_capacity,
                       usize expected_size, usize& output_size) {
  output_size = 0;
  if((input == NULL && input_size != 0) || output == NULL ||
     expected_size > output_capacity) return Status::INVALID_ARGUMENT;

  usize source = 0;
  usize target = 0;
  while(source < input_size) {
    const u8 control = input[source++];
    if(control <= 127) {
      const usize count = (usize) control + 1;
      if(count > input_size - source || count > output_capacity - target) {
        return Status::MALFORMED_PACKBITS;
      }
      memcpy(output + target, input + source, count);
      source += count;
      target += count;
    } else if(control >= 129) {
      const usize count = 257 - (usize) control;
      if(source >= input_size || count > output_capacity - target) {
        return Status::MALFORMED_PACKBITS;
      }
      memset(output + target, input[source++], count);
      target += count;
    } else {
      // The PackBits 0x80 no-op is deliberately rejected. A unique canonical
      // representation makes malformed packets and trailing garbage visible.
      return Status::MALFORMED_PACKBITS;
    }
    if(target > expected_size) return Status::MALFORMED_PACKBITS;
  }

  if(target != expected_size) return Status::MALFORMED_PACKBITS;
  output_size = target;
  return Status::OK;
}

Status encode_best(const u8* input, usize input_size,
                   u8* output, usize output_capacity,
                   CodecSelection& selection) {
  selection = {Codec::RAW, 0};
  if((input == NULL && input_size != 0) || output == NULL ||
     input_size > output_capacity) return Status::INVALID_ARGUMENT;

  usize packed_size = 0;
  const Status packed = packbits_encode(input, input_size, output,
                                        output_capacity, packed_size);
  if(packed == Status::OK && packed_size < input_size) {
    selection = {Codec::PACKBITS, packed_size};
    return Status::OK;
  }

  if(input_size != 0) memcpy(output, input, input_size);
  selection = {Codec::RAW, input_size};
  return Status::OK;
}

Status plan_diff(const u8* previous, const u8* current,
                 DiffPlan& plan, bool force_keyframe) {
  plan.count = 0;
  plan.keyframe = false;
  if(previous == NULL || current == NULL) return Status::INVALID_ARGUMENT;
  if(force_keyframe) {
    make_keyframe(plan);
    return Status::OK;
  }

  usize total_wire_cost = 0;
  const usize keyframe_wire_cost =
    (usize) PAGE_COUNT * (SCREEN_WIDTH + RECT_WIRE_OVERHEAD);

  for(u8 page = 0; page < PAGE_COUNT; page++) {
    const usize page_offset = (usize) page * SCREEN_WIDTH;
    const u8 page_plan_start = plan.count;
    usize page_wire_cost = 0;
    bool page_overflow = false;
    u16 x = 0;
    while(x < SCREEN_WIDTH) {
      while(x < SCREEN_WIDTH &&
            previous[page_offset + x] == current[page_offset + x]) x++;
      if(x >= SCREEN_WIDTH) break;

      const u16 first = x;
      u16 last_changed = x;
      u8 gap = 0;
      x++;
      while(x < SCREEN_WIDTH) {
        if(previous[page_offset + x] != current[page_offset + x]) {
          last_changed = x;
          gap = 0;
        } else {
          gap++;
          if(gap > DIFF_MERGE_GAP) break;
        }
        x++;
      }

      const PageRun run = {
        (u8) first,
        page,
        (u8) (last_changed - first + 1),
      };
      if(!add_run(plan, run)) {
        page_overflow = true;
        break;
      }
      page_wire_cost += run.width + RECT_WIRE_OVERHEAD;
    }

    if(page_overflow ||
       page_wire_cost >= SCREEN_WIDTH + RECT_WIRE_OVERHEAD) {
      plan.count = page_plan_start;
      if(!add_run(plan, {0, page, (u8) SCREEN_WIDTH})) {
        make_keyframe(plan);
        return Status::OK;
      }
      page_wire_cost = SCREEN_WIDTH + RECT_WIRE_OVERHEAD;
    }
    total_wire_cost += page_wire_cost;
  }

  if(total_wire_cost >= keyframe_wire_cost) make_keyframe(plan);
  return Status::OK;
}

Status encode_rect_payload(u16 frame_id, PageRun area,
                           const u8* pixels,
                           u8* output, usize output_capacity,
                           usize& output_size, Codec& codec) {
  output_size = 0;
  codec = Codec::RAW;
  if(!valid_page_run(area) || pixels == NULL || output == NULL) {
    return Status::INVALID_RECT;
  }
  if(output_capacity < RECT_HEADER_SIZE + area.width) {
    return Status::OUTPUT_TOO_SMALL;
  }

  CodecSelection selection = {};
  const Status status = encode_best(pixels, area.width,
                                    output + RECT_HEADER_SIZE,
                                    output_capacity - RECT_HEADER_SIZE,
                                    selection);
  if(status != Status::OK) return status;

  write_u16_le(output, frame_id);
  output[2] = area.x;
  output[3] = area.page;
  output[4] = area.width;
  output[5] = (u8) selection.codec;
  output_size = RECT_HEADER_SIZE + selection.size;
  codec = selection.codec;
  return Status::OK;
}

Status parse_rect_payload(const u8* payload, usize payload_size,
                          RectView& rect) {
  rect = {};
  if(payload == NULL || payload_size < RECT_HEADER_SIZE) {
    return Status::BAD_LENGTH;
  }
  rect.frame_id = read_u16_le(payload);
  rect.area = {payload[2], payload[3], payload[4]};
  rect.codec = (Codec) payload[5];
  rect.encoded = payload + RECT_HEADER_SIZE;
  rect.encoded_size = payload_size - RECT_HEADER_SIZE;
  if(!valid_page_run(rect.area)) return Status::INVALID_RECT;
  if(rect.codec != Codec::RAW && rect.codec != Codec::PACKBITS) {
    return Status::UNSUPPORTED_CODEC;
  }
  if(rect.codec == Codec::RAW && rect.encoded_size != rect.area.width) {
    return Status::BAD_LENGTH;
  }
  return Status::OK;
}

Status decode_rect_pixels(const RectView& rect,
                          u8* output, usize output_capacity) {
  if(!valid_page_run(rect.area) || output == NULL ||
     output_capacity < rect.area.width) return Status::INVALID_RECT;
  if(rect.codec == Codec::RAW) {
    if(rect.encoded == NULL || rect.encoded_size != rect.area.width) {
      return Status::BAD_LENGTH;
    }
    memcpy(output, rect.encoded, rect.area.width);
    return Status::OK;
  }
  if(rect.codec == Codec::PACKBITS) {
    usize decoded_size = 0;
    return packbits_decode(rect.encoded, rect.encoded_size, output,
                           output_capacity, rect.area.width, decoded_size);
  }
  return Status::UNSUPPORTED_CODEC;
}

Status PacketEncoder::encode(MessageType type, u8 flags, u16 sequence,
                             const u8* payload, usize payload_size) {
  framed_size = 0;
  if(payload_size > MAX_PAYLOAD_SIZE ||
     (payload == NULL && payload_size != 0)) return Status::INVALID_ARGUMENT;

  raw[0] = MAGIC_0;
  raw[1] = MAGIC_1;
  raw[2] = PROTOCOL_VERSION;
  raw[3] = (u8) type;
  raw[4] = flags;
  write_u16_le(raw + 5, sequence);
  write_u16_le(raw + 7, (u16) payload_size);
  if(payload_size != 0) memcpy(raw + HEADER_SIZE, payload, payload_size);
  const usize checked_size = HEADER_SIZE + payload_size;
  write_u16_le(raw + checked_size, crc16_ccitt(raw, checked_size));

  usize cobs_size = 0;
  const Status status = cobs_encode(raw, checked_size + CRC_SIZE,
                                    framed, MAX_FRAMED_PACKET - 1,
                                    cobs_size);
  if(status != Status::OK) return status;
  framed[cobs_size] = 0;
  framed_size = cobs_size + 1;
  return Status::OK;
}

void StreamParser::reset(void) {
  encoded_size = 0;
  overflowed = false;
  current_packet = {};
  last_status = Status::OK;
}

Status StreamParser::parse_decoded(usize decoded_size) {
  if(decoded_size < HEADER_SIZE + CRC_SIZE) return Status::BAD_LENGTH;
  if(decoded[0] != MAGIC_0 || decoded[1] != MAGIC_1) return Status::BAD_MAGIC;
  if(decoded[2] != PROTOCOL_VERSION) return Status::BAD_VERSION;

  const usize payload_size = read_u16_le(decoded + 7);
  if(payload_size > MAX_PAYLOAD_SIZE ||
     decoded_size != HEADER_SIZE + payload_size + CRC_SIZE) {
    return Status::BAD_LENGTH;
  }
  const usize checked_size = HEADER_SIZE + payload_size;
  const u16 expected_crc = read_u16_le(decoded + checked_size);
  if(crc16_ccitt(decoded, checked_size) != expected_crc) {
    return Status::BAD_CRC;
  }

  current_packet.type = (MessageType) decoded[3];
  current_packet.flags = decoded[4];
  current_packet.sequence = read_u16_le(decoded + 5);
  current_packet.payload = decoded + HEADER_SIZE;
  current_packet.payload_size = payload_size;
  return Status::OK;
}

PushResult StreamParser::push(u8 value) {
  if(value != 0) {
    if(overflowed) return PushResult::NONE;
    if(encoded_size >= sizeof(encoded)) {
      overflowed = true;
      last_status = Status::OVERFLOW;
      return PushResult::ERROR;
    }
    encoded[encoded_size++] = value;
    return PushResult::NONE;
  }

  if(overflowed) {
    encoded_size = 0;
    overflowed = false;
    last_status = Status::OVERFLOW;
    return PushResult::ERROR;
  }
  if(encoded_size == 0) return PushResult::NONE;

  usize decoded_size = 0;
  last_status = cobs_decode(encoded, encoded_size, decoded, sizeof(decoded),
                            decoded_size);
  encoded_size = 0;
  if(last_status != Status::OK) return PushResult::ERROR;
  last_status = parse_decoded(decoded_size);
  return last_status == Status::OK ? PushResult::PACKET : PushResult::ERROR;
}

const char* status_text(Status status) {
  switch(status) {
    case Status::OK: return "ok";
    case Status::INVALID_ARGUMENT: return "invalid argument";
    case Status::OUTPUT_TOO_SMALL: return "output too small";
    case Status::MALFORMED_COBS: return "malformed COBS";
    case Status::BAD_MAGIC: return "bad magic";
    case Status::BAD_VERSION: return "bad version";
    case Status::BAD_LENGTH: return "bad length";
    case Status::BAD_CRC: return "bad CRC";
    case Status::MALFORMED_PACKBITS: return "malformed PackBits";
    case Status::INVALID_RECT: return "invalid rectangle";
    case Status::UNSUPPORTED_CODEC: return "unsupported codec";
    case Status::OVERFLOW: return "packet overflow";
  }
  return "unknown";
}

} // namespace usb_screen_protocol
