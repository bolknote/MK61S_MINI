#include "fmk_font.hpp"
#include "prepared_font.hpp"

#include <string.h>

namespace fmk {
namespace {

void writeLe16(u8* data, u16 value) {
  data[0] = (u8) value;
  data[1] = (u8) (value >> 8U);
}

// Consume FMK bits incrementally. A compressed C9 file can feed this compiler
// directly, without keeping the FMK in RAM or decoding it once per read span.
class Compiler {
 public:
  Compiler(usize source_size, u8* output, usize capacity)
      : output_(output), capacity_(capacity), source_size_(source_size) {}

  static bool next(void* raw, u8 value) {
    auto& compiler = *static_cast<Compiler*>(raw);
    if(!compiler.valid_) return false;
    compiler.valid_ = compiler.append(value);
    return compiler.valid_;
  }

  bool finish(usize& size) {
    if(!valid_ || position_ != source_size_ || state_ != State::PADDING ||
       crc_ != ((u16) header_[14] | ((u16) header_[15] << 8U))) return false;
    const usize total = bitmap_offset_ + bitmap_size_;
    output_[0] = 'P'; output_[1] = 'F'; output_[2] = 'K'; output_[3] = '2';
    output_[4] = header_[4]; output_[5] = header_[5]; output_[6] = header_[6];
    output_[7] = (u8) ((header_[7] >> 4U) + 1U);
    output_[8] = (u8) (header_[7] & 15U); output_[9] = header_[10];
    writeLe16(output_ + 10, glyph_count_);
    writeLe16(output_ + 12, (u16) records_offset_);
    writeLe16(output_ + 14, (u16) bitmap_offset_);
    writeLe16(output_ + 16, (u16) total);
    writeLe16(output_ + prepared_font::CRC_OFFSET,
              prepared_font::checksum(output_, total));
    size = total;
    return true;
  }

 private:
  enum class State : u8 {
    HEADER, RANGE_START, RANGE_COUNT, WIDTH, ADVANCE, MODE, KIND, COUNT,
    RAW_PIXEL, LITERAL_PIXEL, REPEAT_VALUE, PADDING
  };

  void request(State state, u8 bits) {
    state_ = state; needed_ = bits; partial_ = 0;
  }

  bool append(u8 byte) {
    if(position_ >= source_size_) return false;
    const u8 checked = position_ == 14U || position_ == 15U ? 0 : byte;
    crc_ = checksumByte(crc_, checked);
    ++position_;
    for(u8 available = 8; available;) {
      const u8 count = available < needed_ ? available : needed_;
      available = (u8) (available - count);
      partial_ = (u8) ((partial_ << count) |
          ((byte >> available) & ((1U << count) - 1U)));
      needed_ = (u8) (needed_ - count);
      if(!needed_ && !field(partial_)) return false;
    }
    return true;
  }

  bool startGlyph() {
    if((header_[4] & FLAG_MONOSPACED) == 0) {
      request(State::WIDTH, 4);
      return true;
    }
    width_ = header_[5]; advance_ = (u8) ((header_[7] >> 4U) + 1U);
    return startBitmap();
  }

  bool startBitmap() {
    stride_ = (u8) ((width_ + 7U) / 8U);
    const usize bytes = (usize) stride_ * header_[6];
    if(bytes > (usize) capacity_ - bitmap_offset_ - bitmap_size_) return false;
    memset(output_ + bitmap_offset_ + bitmap_size_, 0, bytes);
    if((header_[4] & FLAG_MONOSPACED) == 0) {
      u8* record = output_ + records_offset_ +
          (usize) glyph_index_ * prepared_font::GLYPH_RECORD_SIZE;
      writeLe16(record, (u16) bitmap_size_);
      record[2] = (u8) (((width_ - 1U) << 4U) | (advance_ - 1U));
    }
    pixels_ = (u16) width_ * header_[6]; produced_ = 0;
    request(State::MODE, 1);
    return true;
  }

  __attribute__((noinline)) void pixel(u16 value) {
    if(value) output_[bitmap_offset_ + bitmap_size_ +
        (produced_ / width_) * stride_ + (produced_ % width_) / 8U] |=
        (u8) (0x80U >> ((produced_ % width_) & 7U));
    ++produced_;
  }

  __attribute__((noinline)) bool completeGlyph() {
    bitmap_size_ += (usize) stride_ * header_[6];
    if(++glyph_index_ < glyph_count_) return startGlyph();
    request(State::PADDING, 1);
    return true;
  }

  bool field(u16 value) {
    switch(state_) {
      case State::HEADER: {
        header_[header_index_++] = (u8) value;
        if(header_index_ < HEADER_SIZE) { request(State::HEADER, 8); return true; }
        if(!plausibleHeader(header_, source_size_)) return false;
        glyph_count_ = (u16) header_[8] | ((u16) header_[9] << 8U);
        records_offset_ = prepared_font::HEADER_SIZE +
            (usize) header_[10] * prepared_font::RANGE_SIZE;
        bitmap_offset_ = records_offset_ + ((header_[4] & FLAG_MONOSPACED)
            ? 0U : (usize) glyph_count_ * prepared_font::GLYPH_RECORD_SIZE);
        if(bitmap_offset_ > capacity_) return false;
        memset(output_, 0, bitmap_offset_);
        request(State::RANGE_START, 8); return true;
      }
      case State::RANGE_START:
        start_ = (u8) value; request(State::RANGE_COUNT, 8); return true;
      case State::RANGE_COUNT: {
        const u16 end = (u16) (start_ + value + 1U);
        if((range_index_ && start_ < previous_end_) || end > 256U) return false;
        for(u16 byte = start_; byte < end; ++byte)
          if(!validGlyphByte((u8) byte)) return false;
        previous_end_ = end;
        counted_ = (u16) (counted_ + value + 1U);
        if(counted_ > glyph_count_) return false;
        u8* range = output_ + prepared_font::HEADER_SIZE +
            (usize) range_index_ * prepared_font::RANGE_SIZE;
        range[0] = start_; range[1] = (u8) value;
        if(++range_index_ < header_[10]) { request(State::RANGE_START, 8); return true; }
        return counted_ == glyph_count_ && startGlyph();
      }
      case State::WIDTH:
        width_ = (u8) (value + 1U);
        if(width_ > header_[5]) return false;
        request(State::ADVANCE, 4); return true;
      case State::ADVANCE:
        advance_ = (u8) (value + 1U); return startBitmap();
      case State::MODE:
        request(value ? State::KIND : State::RAW_PIXEL, 1); return true;
      case State::KIND:
        repeat_ = value != 0; request(State::COUNT, repeat_ ? 5 : 4); return true;
      case State::COUNT:
        run_ = (u16) (value + (repeat_ ? 2U : 1U));
        if(run_ > pixels_ - produced_) return false;
        request(repeat_ ? State::REPEAT_VALUE : State::LITERAL_PIXEL, 1); return true;
      case State::RAW_PIXEL:
        pixel(value);
        if(produced_ == pixels_) return completeGlyph();
        request(State::RAW_PIXEL, 1); return true;
      case State::LITERAL_PIXEL:
        pixel(value); --run_;
        if(produced_ == pixels_) return completeGlyph();
        request(run_ ? State::LITERAL_PIXEL : State::KIND, 1); return true;
      case State::REPEAT_VALUE:
        while(run_) { pixel(value); --run_; }
        if(produced_ == pixels_) return completeGlyph();
        request(State::KIND, 1); return true;
      case State::PADDING:
        if(value || ++padding_ >= 8U) return false;
        request(State::PADDING, 1); return true;
    }
    return false;
  }

  u8* output_;
  usize capacity_, source_size_, position_ = 0;
  usize records_offset_ = 0, bitmap_offset_ = 0, bitmap_size_ = 0;
  u16 crc_ = 0xFFFFU, glyph_count_ = 0, glyph_index_ = 0;
  u16 previous_end_ = 0, counted_ = 0, pixels_ = 0, produced_ = 0, run_ = 0;
  u8 header_[HEADER_SIZE]{}, header_index_ = 0, range_index_ = 0, start_ = 0;
  u8 partial_ = 0, needed_ = 8, width_ = 0, advance_ = 0, stride_ = 0, padding_ = 0;
  State state_ = State::HEADER;
  bool repeat_ = false;
  bool valid_ = true;
};

bool streamReads(void* raw, bool (*next)(void*, u8), void* consumer) {
  const auto& source = *static_cast<const ReadSource*>(raw);
  u8 cache[128];
  for(usize offset = 0; offset < source.size;) {
    const usize length = source.size - offset < sizeof(cache)
        ? source.size - offset : sizeof(cache);
    if(!source.read(source.context, offset, cache, length)) return false;
    for(usize byte = 0; byte < length; ++byte)
      if(!next(consumer, cache[byte])) return false;
    offset += length;
  }
  return true;
}

} // namespace

bool prepare(const StreamSource& source, u8* output, usize capacity,
             usize& output_size) {
  output_size = 0;
  if(!source.stream || source.size < HEADER_SIZE || source.size > MAX_FILE_SIZE ||
     output == nullptr || capacity < prepared_font::HEADER_SIZE ||
     capacity > prepared_font::MAX_IMAGE_SIZE) return false;
  Compiler compiler(source.size, output, capacity);
  return source.stream(source.context, Compiler::next, &compiler) &&
      compiler.finish(output_size);
}

bool prepare(const ReadSource& source, u8* output, usize capacity,
             usize& output_size) {
  output_size = 0;
  if(!source.read) return false;
  const StreamSource stream = {const_cast<ReadSource*>(&source), source.size, streamReads};
  return prepare(stream, output, capacity, output_size);
}

bool prepare(const Face& face, u8* output, usize capacity,
             usize& output_size) {
  output_size = 0;
  if(!face.valid()) return false;
  const StreamSource source = {const_cast<Face*>(&face), face.size(),
      [](void* raw, bool (*next)(void*, u8), void* consumer) {
        const auto& face = *static_cast<const Face*>(raw);
        for(usize byte = 0; byte < face.size(); ++byte)
          if(!next(consumer, face.data()[byte])) return false;
        return true;
      }};
  return prepare(source, output, capacity, output_size);
}

} // namespace fmk
