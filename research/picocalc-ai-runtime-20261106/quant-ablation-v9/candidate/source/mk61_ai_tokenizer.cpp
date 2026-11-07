#include "mk61_ai_model.hpp"
#include <algorithm>
#include <cstring>

namespace mk61ai {
class Tokenizer {
  Model &m;
  std::uint32_t *points;
  std::uint16_t *piece;
  std::uint16_t bytes[256]{};
  ModelStatus error = ModelStatus::OK;
  bool get(unsigned offset, void *out, unsigned n) {
    if (m.read(offset, out, n))
      return true;
    error = ModelStatus::IO;
    return false;
  }
  unsigned properties(std::uint32_t cp) {
    if (cp < 128)
      return (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z') ? 1
             : cp >= '0' && cp <= '9'                             ? 2
             : cp == 32 || (cp >= 9 && cp <= 13)                  ? 4
                                                                  : 0;
    if ((cp >= 0x410 && cp <= 0x44f) || cp == 0x401 || cp == 0x451)
      return 1;
    unsigned lo = 0, hi = m.header_[25];
    std::uint32_t r[3];
    while (lo < hi) {
      const unsigned mid = (lo + hi) / 2;
      if (!get(m.header_[24] + 12 * mid, r, 12))
        return 0;
      if (cp < r[0])
        hi = mid;
      else if (cp > r[1])
        lo = mid + 1;
      else
        return r[2];
    }
    return 0;
  }
  unsigned decompose(std::uint32_t cp, std::uint32_t out[4]) {
    if (cp >= 0xac00 && cp <= 0xd7a3) {
      const unsigned s = cp - 0xac00;
      out[0] = 0x1100 + s / 588;
      out[1] = 0x1161 + (s % 588) / 28;
      if (s % 28) {
        out[2] = 0x11a7 + s % 28;
        return 3;
      }
      return 2;
    }
    if (cp < 128) {
      out[0] = cp;
      return 1;
    }
    unsigned lo = 0, hi = m.header_[21];
    std::uint32_t r[6];
    while (lo < hi) {
      const unsigned mid = (lo + hi) / 2;
      if (!get(m.header_[20] + 24 * mid, r, 24))
        return 0;
      if (cp < r[0])
        hi = mid;
      else if (cp > r[0])
        lo = mid + 1;
      else {
        if (r[1] > 4 || !r[1]) {
          error = ModelStatus::FORMAT;
          return 0;
        }
        std::memcpy(out, r + 2, r[1] * 4);
        return r[1];
      }
    }
    out[0] = cp;
    return 1;
  }
  std::uint32_t compose(std::uint32_t a, std::uint32_t b) {
    if (a >= 0x1100 && a < 0x1113 && b >= 0x1161 && b < 0x1176)
      return 0xac00 + (a - 0x1100) * 588 + (b - 0x1161) * 28;
    if (a >= 0xac00 && a <= 0xd7a3 && (a - 0xac00) % 28 == 0 && b > 0x11a7 &&
        b < 0x11c3)
      return a + b - 0x11a7;
    unsigned lo = 0, hi = m.header_[23];
    std::uint32_t r[3];
    while (lo < hi) {
      const unsigned mid = (lo + hi) / 2;
      if (!get(m.header_[22] + 12 * mid, r, 12))
        return 0;
      if (a < r[0] || (a == r[0] && b < r[1]))
        hi = mid;
      else if (a > r[0] || b > r[1])
        lo = mid + 1;
      else
        return r[2];
    }
    return 0;
  }
  bool normalize(const char *text, unsigned &count) {
    count = 0;
    unsigned consumed = 0;
    while (text[consumed]) {
      if (consumed >= Model::MAX_TEXT) {
        error = ModelStatus::TEXT_LONG;
        return false;
      }
      unsigned c = std::uint8_t(text[consumed++]), extra = 0;
      std::uint32_t cp = c, min = 0;
      if (c >= 0xc2 && c <= 0xdf) {
        cp = c & 31;
        extra = 1;
        min = 0x80;
      } else if (c >= 0xe0 && c <= 0xef) {
        cp = c & 15;
        extra = 2;
        min = 0x800;
      } else if (c >= 0xf0 && c <= 0xf4) {
        cp = c & 7;
        extra = 3;
        min = 0x10000;
      } else if (c >= 128) {
        error = ModelStatus::FORMAT;
        return false;
      }
      while (extra--) {
        if (consumed >= Model::MAX_TEXT ||
            (std::uint8_t(text[consumed]) & 0xc0) != 0x80) {
          error = ModelStatus::FORMAT;
          return false;
        }
        cp = (cp << 6) | (std::uint8_t(text[consumed++]) & 63);
      }
      if (cp < min || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) {
        error = ModelStatus::FORMAT;
        return false;
      }
      std::uint32_t decomposed[4];
      const unsigned n = decompose(cp, decomposed);
      if (error != ModelStatus::OK || count + n > Model::MAX_TEXT) {
        if (error == ModelStatus::OK)
          error = ModelStatus::TEXT_LONG;
        return false;
      }
      for (unsigned j = 0; j < n; ++j) {
        unsigned at = count++;
        points[at] = decomposed[j];
        const unsigned cls = properties(points[at]) >> 8;
        if (cls)
          while (at && (properties(points[at - 1]) >> 8) > cls) {
            std::swap(points[at], points[at - 1]);
            --at;
          }
      }
    }
    unsigned used = 0, starter = 0, previous = 0;
    for (unsigned i = 0; i < count; ++i) {
      const auto cp = points[i];
      const unsigned cls = properties(cp) >> 8;
      const auto composed = used && (previous < cls || previous == 0)
                                ? compose(points[starter], cp)
                                : 0;
      if (composed)
        points[starter] = composed;
      else {
        if (cls == 0)
          starter = used;
        points[used++] = cp;
        previous = cls;
      }
    }
    count = used;
    return error == ModelStatus::OK;
  }
  int special(unsigned at, unsigned end, unsigned &after) const {
    static constexpr char names[3][6] = {"<pad>", "<bos>", "<eos>"};
    if (end - at < 5 || points[at] != '<')
      return -1;
    for (unsigned id = 0; id < 3; ++id) {
      unsigned j = 0;
      while (j < 5 && points[at + j] == unsigned(names[id][j]))
        ++j;
      if (j == 5) {
        after = at + 5;
        return int(id);
      }
    }
    return -1;
  }
  bool emit(unsigned begin, unsigned end, std::uint16_t *out, unsigned capacity,
            unsigned &used) {
    unsigned n = 0;
    auto byte = [&](unsigned b) {
      if (n >= Model::MAX_TEXT) {
        error = ModelStatus::TEXT_LONG;
        return false;
      }
      piece[n++] = bytes[b];
      return true;
    };
    for (unsigned i = begin; i < end; ++i) {
      const auto cp = points[i];
      bool ok;
      if (cp < 0x80)
        ok = byte(cp);
      else if (cp < 0x800)
        ok = byte(0xc0 | (cp >> 6)) && byte(0x80 | (cp & 63));
      else if (cp < 0x10000)
        ok = byte(0xe0 | (cp >> 12)) && byte(0x80 | ((cp >> 6) & 63)) &&
             byte(0x80 | (cp & 63));
      else
        ok = byte(0xf0 | (cp >> 18)) && byte(0x80 | ((cp >> 12) & 63)) &&
             byte(0x80 | ((cp >> 6) & 63)) && byte(0x80 | (cp & 63));
      if (!ok)
        return false;
    }
    while (n > 1) {
      unsigned best_rank = ~0U, best_at = 0, best_token = 0;
      for (unsigned i = 0; i + 1 < n; ++i) {
        const std::uint32_t key =
            (std::uint32_t(piece[i]) << 16) | piece[i + 1];
        unsigned lo = 0, hi = m.header_[18];
        std::uint32_t r[3];
        while (lo < hi) {
          const unsigned mid = (lo + hi) / 2;
          if (!get(m.header_[17] + 12 * mid, r, 12))
            return false;
          if (key < r[0])
            hi = mid;
          else if (key > r[0])
            lo = mid + 1;
          else {
            if (r[2] < best_rank) {
              best_rank = r[2];
              best_at = i;
              best_token = r[1];
            }
            break;
          }
        }
      }
      if (best_rank == ~0U)
        break;
      if (best_token >= m.config_.vocab) {
        error = ModelStatus::FORMAT;
        return false;
      }
      piece[best_at] = std::uint16_t(best_token);
      std::memmove(piece + best_at + 1, piece + best_at + 2,
                   (n - best_at - 2) * 2);
      --n;
    }
    if (n > capacity - used) {
      error = ModelStatus::CONTEXT;
      return false;
    }
    std::memcpy(out + used, piece, n * 2);
    used += n;
    return true;
  }
  unsigned contraction(unsigned at, unsigned end) const {
    static const char *const suffixes[] = {"s", "t",  "re", "ve",
                                           "m", "ll", "d"};
    if (points[at] != '\'')
      return 0;
    for (const char *s : suffixes) {
      unsigned j = 0;
      while (s[j] && at + j + 1 < end && points[at + j + 1] == unsigned(s[j]))
        ++j;
      if (!s[j])
        return j + 1;
    }
    return 0;
  }

public:
  explicit Tokenizer(Model &model)
      : m(model), points(reinterpret_cast<std::uint32_t *>(model.workspace_)),
        piece(reinterpret_cast<std::uint16_t *>(model.workspace_ +
                                                4 * Model::MAX_TEXT)) {}
  ModelStatus encode(const char *text, std::uint16_t *out, unsigned capacity,
                     unsigned &used, bool bos) {
    used = 0;
    if (!text || !out || !m.workspace_)
      return ModelStatus::MEMORY;
    if (!get(m.header_[19], bytes, sizeof(bytes)))
      return error;
    unsigned n = 0;
    if (!normalize(text, n))
      return error;
    if (bos) {
      if (!capacity)
        return ModelStatus::CONTEXT;
      out[used++] = std::uint16_t(m.config_.bos);
    }
    unsigned i = 0;
    while (i < n && error == ModelStatus::OK) {
      unsigned after = 0;
      const int id = special(i, n, after);
      if (id >= 0) {
        if (used == capacity)
          return ModelStatus::CONTEXT;
        out[used++] = std::uint16_t(id);
        i = after;
        continue;
      }
      if (properties(points[i]) & 2) {
        if (!emit(i, i + 1, out, capacity, used))
          return error;
        ++i;
        continue;
      }
      unsigned end = i;
      while (end < n && !(properties(points[end]) & 2) &&
             special(end, n, after) < 0)
        ++end;
      while (i < end) {
        unsigned j = i, length = contraction(i, end);
        if (length)
          j += length;
        else {
          if (points[j] == 32 && j + 1 < end &&
              !(properties(points[j + 1]) & 4))
            ++j;
          const unsigned prop = properties(points[j]);
          if (prop & 1) {
            do {
              ++j;
            } while (j < end && (properties(points[j]) & 1));
          } else if (!(prop & 4)) {
            do {
              ++j;
            } while (j < end && !(properties(points[j]) & 7));
          } else {
            j = i;
            while (j < end && (properties(points[j]) & 4))
              ++j;
            if (j < end && j - i > 1)
              --j;
          }
        }
        if (j == i || !emit(i, j, out, capacity, used))
          return error == ModelStatus::OK ? ModelStatus::FORMAT : error;
        i = j;
      }
    }
    return error;
  }
};
ModelStatus Model::encode(const char *text, std::uint16_t *out,
                          unsigned capacity, unsigned &used, bool bos) {
  return Tokenizer(*this).encode(text, out, capacity, used, bos);
}
ModelStatus Model::decode(std::uint16_t token, char *out, unsigned capacity,
                          unsigned &used) {
  used = 0;
  std::uint32_t record[2];
  if (!out || token >= config_.vocab || !capacity)
    return ModelStatus::FORMAT;
  if (!read(header_[16] + token * 8, record, 8))
    return ModelStatus::IO;
  const unsigned n = record[1] & 65535;
  if (n >= capacity)
    return ModelStatus::TEXT_LONG;
  if (!read(record[0], out, n))
    return ModelStatus::IO;
  out[n] = 0;
  used = n;
  return ModelStatus::OK;
}
} // namespace mk61ai
