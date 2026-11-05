#ifndef MK61_URQ_PACK_HPP
#define MK61_URQ_PACK_HPP
#include <stddef.h>
#include <stdint.h>

namespace urq {
constexpr uint16_t PAGE_BYTES = 512, FILE_BYTES = 60 * 1024, PACK_VERSION = 1;
enum class Mode : uint8_t { URQW, DOS, RIP, AK };
enum class Error : uint8_t {
  NONE, IO, FORMAT, CRC, MEMORY, SYNTAX, LABEL, STACK, LIMIT, UNSUPPORTED
};
struct Reader {
  void* context;
  // file 0 is game.urq, file 1 is p0000.uqd, and so on.
  bool (*read)(void*, uint16_t file, uint32_t offset, uint8_t*, uint32_t);
  uint32_t (*size)(void*, uint16_t file);
  uint8_t* cache = nullptr;
};
uint16_t le16(const uint8_t*);
uint32_t le32(const uint8_t*);
void put16(uint8_t*, uint16_t);
void put32(uint8_t*, uint32_t);
uint32_t crc32(const uint8_t*, uint32_t, uint32_t initial = 0);
uint8_t lower(uint8_t);
uint32_t hash_name(const char*);
bool equal_name(const char*, const char*);
int compare_name(const char*, const char*);
char* copy_string(char*, const char*);
char* join_string(char*, const char*);
const char* find_string(const char*, const char*);

class Pack {
 public:
  bool open(Reader reader);
  bool read(uint32_t offset, void* output, uint32_t size);
  bool line(uint32_t index, char* output, uint16_t capacity);
  bool label(const char* name, uint32_t& line);
  bool label_at(uint32_t index, char* name, uint16_t capacity, uint32_t& line);
  bool info(uint8_t field, char* output, uint16_t capacity);
  bool resource(const char* name,char* output,uint16_t capacity,bool url=false);
  uint32_t lines() const { return lines_; }
  uint32_t labels() const { return labels_; }
  Mode mode() const { return mode_; }
  bool html() const { return html_; }
  const uint8_t* id() const { return id_; }
  Error error() const { return error_; }
  void invalidate() { page_ = UINT32_MAX; }
  void cache(uint8_t* memory) { data_ = memory; invalidate(); }
 private:
  bool page(uint32_t index);
  bool string(uint32_t offset, char*, uint16_t);
  Reader reader_{};
  uint32_t logical_ = 0, lines_ = 0, labels_ = 0, line_table_ = 0,
           label_table_ = 0, metadata_ = 0, pages_ = 0, page_ = UINT32_MAX;
  uint16_t parts_ = 0, valid_ = 0;
  uint8_t id_[16]{};
  uint8_t* data_ = nullptr;
  Mode mode_ = Mode::URQW;
  bool html_ = false;
  bool resources_ = false;
  Error error_ = Error::NONE;
};
}
#endif
