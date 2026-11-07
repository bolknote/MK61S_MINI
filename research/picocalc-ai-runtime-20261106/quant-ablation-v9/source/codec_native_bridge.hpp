#ifndef MK61_RESEARCH_H32_BRIDGE_HPP
#define MK61_RESEARCH_H32_BRIDGE_HPP

#include "mk61_ai_model.hpp"
#include <cctype>
#include <cstdint>
#include <cstring>

namespace mk61research {
// Tables are generated from the frozen training-frequency codebook.
struct Huffman32 {
  const std::uint32_t *words;
  const std::uint8_t *lengths;
  unsigned max_length;

  bool decode(const char *text, std::uint8_t *out, unsigned capacity,
              unsigned &used) const {
    used = 0;
    if (max_length == 0 || max_length > 6)
      return false;
    unsigned length = 0;
    std::uint32_t word = 0;
    while (*text) {
      if (std::isspace(static_cast<unsigned char>(*text))) {
        ++text;
        continue;
      }
      if (std::strlen(text) < 5 || text[0] != '<' || text[1] != 'h' ||
          text[2] < '0' || text[2] > '3' || text[3] < '0' ||
          text[3] > '9' || text[4] != '>')
        return false;
      const unsigned symbol = 10 * unsigned(text[2] - '0') + unsigned(text[3] - '0');
      if (symbol >= 32 || ++length > max_length)
        return false;
      word = (word << 5) | symbol;
      text += 5;
      bool possible = false;
      int byte = -1;
      for (unsigned b = 0; b < 256; ++b) {
        if (lengths[b] < length)
          continue;
        if ((words[b] >> (5 * (lengths[b] - length))) == word) {
          possible = true;
          if (lengths[b] == length)
            byte = int(b);
        }
      }
      if (!possible)
        return false;
      if (byte >= 0) {
        if (used >= capacity || used >= 105)
          return false;
        out[used++] = std::uint8_t(byte);
        word = 0;
        length = 0;
      }
    }
    return length == 0 && used != 0;
  }
};

// The original Russian BPE stays intact. Only the32 exact added tokens
// are recognized before handing intervening text to the frozen tokenizer.
inline mk61ai::ModelStatus encode_h32(mk61ai::Model &model, const char *text,
                                    std::uint16_t *out, unsigned capacity,
                                    unsigned &used) {
  used = 0;
  const char *start = text;
  char segment[mk61ai::Model::MAX_TEXT + 1];
  auto flush = [&](const char *end) {
    const auto length = unsigned(end - start);
    if (!length)
      return mk61ai::ModelStatus::OK;
    if (length > mk61ai::Model::MAX_TEXT)
      return mk61ai::ModelStatus::TEXT_LONG;
    std::memcpy(segment, start, length);
    segment[length] = 0;
    unsigned count = 0;
    const auto status = model.encode(segment, out + used, capacity - used, count, false);
    if (status == mk61ai::ModelStatus::OK)
      used += count;
    return status;
  };
  const unsigned length = unsigned(std::strlen(text));
  for (unsigned i = 0; i < length; ++i) {
    if (i + 5 > length || text[i] != '<' || text[i + 1] != 'h' ||
        text[i + 2] < '0' || text[i + 2] > '3' ||
        text[i + 3] < '0' || text[i + 3] > '9' || text[i + 4] != '>')
      continue;
    const unsigned symbol = 10 * unsigned(text[i + 2] - '0') + unsigned(text[i + 3] - '0');
    if (symbol >= 32)
      continue;
    const auto status = flush(text + i);
    if (status != mk61ai::ModelStatus::OK)
      return status;
    if (used >= capacity)
      return mk61ai::ModelStatus::TEXT_LONG;
    out[used++] = std::uint16_t(8192 + symbol);
    i += 4;
    start = text + i + 1;
  }
  return flush(text + length);
}
} // namespace mk61research
#endif
