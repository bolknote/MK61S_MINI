#ifndef SETTINGS_JOURNAL_HPP
#define SETTINGS_JOURNAL_HPP

#include "rust_types.h"

#include <string.h>

namespace settings_journal {

static constexpr usize RECORD_SIZE = 16;
static constexpr u8 VERSION_1 = 1;
static constexpr u8 VERSION_2 = 2;
static constexpr u8 VERSION = 3;
static constexpr u8 COMMIT_MARKER = 0xA5;
static constexpr usize COMMIT_INDEX = 15;

static constexpr usize IDX_MAGIC_0 = 0;
static constexpr usize IDX_MAGIC_1 = 1;
static constexpr usize IDX_MAGIC_2 = 2;
static constexpr usize IDX_MAGIC_3 = 3;
static constexpr usize IDX_VERSION = 4;
static constexpr usize IDX_GRADE = 5;
static constexpr usize IDX_COUNTER = 6;
static constexpr usize IDX_FLAGS = 7;
static constexpr usize IDX_SOUND = 8;
static constexpr usize IDX_V1_CRC = 9;
static constexpr usize IDX_TEXT_ROWS = 9;
static constexpr usize IDX_TEXT_WIDTH = 10;
static constexpr usize IDX_TEXT_HEIGHT = 11;
static constexpr usize IDX_TEXT_GAP = 12;
static constexpr usize IDX_TEXT_RESERVED = 13;
static constexpr usize IDX_CRC = 14;

struct RecordData {
  u8 grade;
  u8 counter;
  u8 flags;
  u8 sound;
  u8 text_rows;
  u8 text_width;
  u8 text_height;
  u8 text_gap;
  bool text_profile_stored;
};

enum class RecordStatus : u8 {
  ERASED,
  VALID,
  INVALID
};

inline u8 checksum(const u8* record, usize crc_index) {
  u8 crc = 0xA5;
  for(usize i = 0; i < crc_index; i++) {
    crc = (u8) ((crc << 1) | (crc >> 7));
    crc ^= record[i];
  }
  return crc;
}

inline bool erased(const u8* record) {
  for(usize i = 0; i < RECORD_SIZE; i++) {
    if(record[i] != 0xFF) return false;
  }
  return true;
}

inline bool has_magic(const u8* record) {
  return record[IDX_MAGIC_0] == 'M' &&
    record[IDX_MAGIC_1] == '6' &&
    record[IDX_MAGIC_2] == '1' &&
    record[IDX_MAGIC_3] == 'S';
}

inline RecordStatus decode(const u8* record, RecordData& out, u8* decoded_version = NULL) {
  if(record == NULL) return RecordStatus::INVALID;
  if(erased(record)) return RecordStatus::ERASED;
  if(!has_magic(record)) return RecordStatus::INVALID;

  const u8 version = record[IDX_VERSION];
  if(version == VERSION_1) {
    if(record[IDX_V1_CRC] != checksum(record, IDX_V1_CRC)) return RecordStatus::INVALID;
  } else if(version == VERSION_2) {
    if(record[IDX_CRC] != checksum(record, IDX_CRC)) return RecordStatus::INVALID;
  } else if(version == VERSION) {
    if(record[COMMIT_INDEX] != COMMIT_MARKER) return RecordStatus::INVALID;
    if(record[IDX_CRC] != checksum(record, IDX_CRC)) return RecordStatus::INVALID;
  } else {
    return RecordStatus::INVALID;
  }

  RecordData decoded = {};
  decoded.grade = record[IDX_GRADE];
  decoded.counter = record[IDX_COUNTER];
  decoded.flags = record[IDX_FLAGS];
  decoded.sound = record[IDX_SOUND];
  decoded.text_rows = 0xFF;
  decoded.text_width = 0xFF;
  decoded.text_height = 0xFF;
  decoded.text_gap = 0xFF;
  decoded.text_profile_stored = false;

  if(version >= VERSION_2 &&
     record[IDX_TEXT_ROWS] != 0xFF &&
     record[IDX_TEXT_WIDTH] != 0xFF &&
     record[IDX_TEXT_HEIGHT] != 0xFF &&
     record[IDX_TEXT_GAP] != 0xFF) {
    decoded.text_rows = record[IDX_TEXT_ROWS];
    decoded.text_width = record[IDX_TEXT_WIDTH];
    decoded.text_height = record[IDX_TEXT_HEIGHT];
    decoded.text_gap = record[IDX_TEXT_GAP];
    decoded.text_profile_stored = true;
  }

  out = decoded;
  if(decoded_version != NULL) *decoded_version = version;
  return RecordStatus::VALID;
}

inline void encode_uncommitted(const RecordData& data, u8 record[RECORD_SIZE]) {
  memset(record, 0xFF, RECORD_SIZE);
  record[IDX_MAGIC_0] = 'M';
  record[IDX_MAGIC_1] = '6';
  record[IDX_MAGIC_2] = '1';
  record[IDX_MAGIC_3] = 'S';
  record[IDX_VERSION] = VERSION;
  record[IDX_GRADE] = data.grade;
  record[IDX_COUNTER] = data.counter;
  record[IDX_FLAGS] = data.flags;
  record[IDX_SOUND] = data.sound;
  if(data.text_profile_stored) {
    record[IDX_TEXT_ROWS] = data.text_rows;
    record[IDX_TEXT_WIDTH] = data.text_width;
    record[IDX_TEXT_HEIGHT] = data.text_height;
    record[IDX_TEXT_GAP] = data.text_gap;
  }
  record[IDX_TEXT_RESERVED] = 0xFF;
  record[IDX_CRC] = checksum(record, IDX_CRC);
  record[COMMIT_INDEX] = 0xFF;
}

class Scanner {
  public:
    explicit Scanner(usize sector_size) :
      sector_size_(sector_size - (sector_size % RECORD_SIZE)),
      next_offset_(0),
      active_(sector_size_ >= RECORD_SIZE),
      has_value_(false),
      ended_at_erased_(false),
      needs_reclaim_(sector_size_ < RECORD_SIZE),
      latest_version_(0),
      latest_{} {}

    bool active(void) const { return active_; }
    usize next_offset(void) const { return next_offset_; }
    bool has_value(void) const { return has_value_; }
    bool ended_at_erased(void) const { return ended_at_erased_; }
    bool needs_reclaim(void) const { return needs_reclaim_; }
    bool migration_needed(void) const { return has_value_ && latest_version_ != VERSION; }
    const RecordData& latest(void) const { return latest_; }

    void consume(const u8 record[RECORD_SIZE]) {
      if(!active_) return;

      RecordData decoded = {};
      u8 version = 0;
      const RecordStatus status = decode(record, decoded, &version);
      if(status == RecordStatus::ERASED) {
        active_ = false;
        ended_at_erased_ = true;
        return;
      }
      if(status == RecordStatus::INVALID) {
        active_ = false;
        needs_reclaim_ = true;
        next_offset_ = sector_size_;
        return;
      }

      latest_ = decoded;
      latest_version_ = version;
      has_value_ = true;
      next_offset_ += RECORD_SIZE;
      if(next_offset_ + RECORD_SIZE > sector_size_) {
        active_ = false;
        needs_reclaim_ = true;
        next_offset_ = sector_size_;
      }
    }

  private:
    usize sector_size_;
    usize next_offset_;
    bool active_;
    bool has_value_;
    bool ended_at_erased_;
    bool needs_reclaim_;
    u8 latest_version_;
    RecordData latest_;
};

} // namespace settings_journal

#endif
