#include <ft2build.h>
#include FT_FREETYPE_H

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::size_t HEADER_SIZE = 16;
constexpr std::size_t MAX_FILE_SIZE = 1536;
constexpr std::uint8_t FLAG_MONOSPACED = 0x01;

enum class Compression { AUTO, NONE, RLE };

struct Options {
  std::string input;
  std::string output;
  std::string characters = "ascii,cyrillic";
  int width = 5;
  int height = 8;
  int point_size = 0;
  int threshold = 128;
  bool threshold_explicit = false;
  int line_gap = -1;
  bool proportional = false;
  Compression compression = Compression::AUTO;
};

struct GlyphBitmap {
  std::uint16_t codepoint;
  std::uint8_t width;
  std::uint8_t advance;
  std::vector<std::uint8_t> bits;
};

struct Choice {
  bool run = false;
  std::uint8_t length = 0;
};

class FreeTypeLibrary {
 public:
  FreeTypeLibrary() {
    if (FT_Init_FreeType(&library) != 0) throw std::runtime_error("cannot initialize FreeType");
  }
  ~FreeTypeLibrary() { FT_Done_FreeType(library); }
  operator FT_Library() const { return library; }

 private:
  FT_Library library = nullptr;
};

class FreeTypeFace {
 public:
  FreeTypeFace(FT_Library library, const std::string& path) {
    if (FT_New_Face(library, path.c_str(), 0, &face) != 0) {
      throw std::runtime_error("FreeType cannot open the input font");
    }
  }
  ~FreeTypeFace() { FT_Done_Face(face); }
  operator FT_Face() const { return face; }
  FT_Face operator->() const { return face; }

 private:
  FT_Face face = nullptr;
};

class BitWriter {
 public:
  explicit BitWriter(std::vector<std::uint8_t> initial)
      : data(std::move(initial)), position(data.size() * 8) {}

  void write(std::uint32_t value, unsigned count) {
    for (int bit = static_cast<int>(count) - 1; bit >= 0; --bit) {
      const std::size_t byte = position / 8;
      if (byte == data.size()) data.push_back(0);
      if ((value & (std::uint32_t{1} << bit)) != 0) {
        data[byte] |= static_cast<std::uint8_t>(0x80 >> (position & 7));
      }
      ++position;
    }
  }

  std::vector<std::uint8_t> data;

 private:
  std::size_t position;
};

[[noreturn]] void usage(const char* message = nullptr) {
  if (message != nullptr) std::fprintf(stderr, "error: %s\n\n", message);
  std::fprintf(stderr,
      "usage: fmk_font INPUT OUTPUT [options]\n"
      "  --cell WxH              output cell, default 5x8\n"
      "  --size N                FreeType pixel size, default 4x cell height\n"
      "  --chars SPEC            ascii,cyrillic,latin1,U+XXXX ranges, or UTF-8 text\n"
      "  --threshold N           explicit coverage cutoff 0..255; omitted adapts 128 to downscale\n"
      "  --line-gap N            suggested line gap 0..15; default follows cell height\n"
      "  --proportional          write per-glyph 4-bit width and advance\n"
      "  --compression MODE      auto, none, or rle\n");
  std::exit(message == nullptr ? 0 : 2);
}

int parse_int(const std::string& value, const char* name) {
  std::size_t end = 0;
  const int result = std::stoi(value, &end, 10);
  if (end != value.size()) throw std::runtime_error(std::string("invalid ") + name);
  return result;
}

void parse_cell(const std::string& value, int& width, int& height) {
  const std::size_t separator = value.find_first_of("xX");
  if (separator == std::string::npos) throw std::runtime_error("cell must be WIDTHxHEIGHT");
  width = parse_int(value.substr(0, separator), "cell width");
  height = parse_int(value.substr(separator + 1), "cell height");
  if (width < 1 || width > 16 || height < 1 || height > 32) {
    throw std::runtime_error("FMK1 supports cells from 1x1 through 16x32");
  }
}

Options parse_options(int argc, char** argv) {
  if (argc == 1) usage();
  if (argc == 2 && (std::strcmp(argv[1], "--help") == 0 || std::strcmp(argv[1], "-h") == 0)) usage();
  if (argc < 3) usage("input and output files are required");
  Options options;
  options.input = argv[1];
  options.output = argv[2];
  for (int index = 3; index < argc; ++index) {
    const std::string option = argv[index];
    auto value = [&]() -> std::string {
      if (++index >= argc) throw std::runtime_error("missing value after " + option);
      return argv[index];
    };
    if (option == "--cell") parse_cell(value(), options.width, options.height);
    else if (option == "--size") options.point_size = parse_int(value(), "point size");
    else if (option == "--chars") options.characters = value();
    else if (option == "--threshold") {
      options.threshold = parse_int(value(), "threshold");
      options.threshold_explicit = true;
    }
    else if (option == "--line-gap") options.line_gap = parse_int(value(), "line gap");
    else if (option == "--proportional") options.proportional = true;
    else if (option == "--compression") {
      const std::string mode = value();
      if (mode == "auto") options.compression = Compression::AUTO;
      else if (mode == "none") options.compression = Compression::NONE;
      else if (mode == "rle") options.compression = Compression::RLE;
      else throw std::runtime_error("compression must be auto, none, or rle");
    } else if (option == "--help" || option == "-h") {
      usage();
    } else {
      throw std::runtime_error("unknown option: " + option);
    }
  }
  if (options.point_size == 0) options.point_size = std::max(8, options.height * 4);
  if (options.line_gap < 0) options.line_gap = options.height <= 5 ? 1 : (options.height <= 8 ? 2 : 0);
  if (options.point_size < 1) throw std::runtime_error("point size must be positive");
  if (options.threshold < 0 || options.threshold > 255) throw std::runtime_error("threshold must be 0..255");
  if (options.line_gap < 0 || options.line_gap > 15) throw std::runtime_error("line gap must be 0..15");
  return options;
}

std::uint16_t parse_codepoint(std::string value) {
  if (value.size() >= 2 && (value[0] == 'U' || value[0] == 'u') && value[1] == '+') value.erase(0, 2);
  std::size_t end = 0;
  const unsigned long result = std::stoul(value, &end, 16);
  if (end != value.size() || result > 0xFFFF) throw std::runtime_error("invalid BMP codepoint");
  return static_cast<std::uint16_t>(result);
}

void add_utf8(std::set<std::uint16_t>& output, const std::string& text) {
  for (std::size_t index = 0; index < text.size();) {
    const auto first = static_cast<std::uint8_t>(text[index++]);
    std::uint32_t codepoint = 0;
    unsigned continuation = 0;
    if (first < 0x80) codepoint = first;
    else if ((first & 0xE0) == 0xC0) { codepoint = first & 0x1F; continuation = 1; }
    else if ((first & 0xF0) == 0xE0) { codepoint = first & 0x0F; continuation = 2; }
    else if ((first & 0xF8) == 0xF0) { codepoint = first & 0x07; continuation = 3; }
    else throw std::runtime_error("invalid UTF-8 in --chars");
    if (index + continuation > text.size()) throw std::runtime_error("truncated UTF-8 in --chars");
    for (unsigned i = 0; i < continuation; ++i) {
      const auto byte = static_cast<std::uint8_t>(text[index++]);
      if ((byte & 0xC0) != 0x80) throw std::runtime_error("invalid UTF-8 continuation");
      codepoint = (codepoint << 6) | (byte & 0x3F);
    }
    if (codepoint > 0xFFFF) throw std::runtime_error("FMK1 v1 stores BMP codepoints only");
    output.insert(static_cast<std::uint16_t>(codepoint));
  }
}

std::vector<std::uint16_t> character_set(const std::string& specification) {
  std::set<std::uint16_t> output;
  std::size_t position = 0;
  while (position <= specification.size()) {
    const std::size_t comma = specification.find(',', position);
    const std::string token = specification.substr(position, comma == std::string::npos ? comma : comma - position);
    if (token == "ascii") {
      for (std::uint16_t cp = 0x20; cp <= 0x7E; ++cp) output.insert(cp);
    } else if (token == "latin1") {
      for (std::uint16_t cp = 0x20; cp <= 0xFF; ++cp) output.insert(cp);
    } else if (token == "cyrillic") {
      output.insert(0x0401);
      for (std::uint16_t cp = 0x0410; cp <= 0x044F; ++cp) output.insert(cp);
      output.insert(0x0451);
    } else if (token.rfind("U+", 0) == 0 || token.rfind("u+", 0) == 0) {
      const std::size_t dash = token.find('-', 2);
      const std::uint16_t first = parse_codepoint(token.substr(0, dash));
      const std::uint16_t last = dash == std::string::npos ? first : parse_codepoint(token.substr(dash + 1));
      if (last < first) throw std::runtime_error("descending codepoint range");
      for (std::uint32_t cp = first; cp <= last; ++cp) output.insert(static_cast<std::uint16_t>(cp));
    } else if (!token.empty()) {
      add_utf8(output, token);
    }
    if (comma == std::string::npos) break;
    position = comma + 1;
  }
  return {output.begin(), output.end()};
}

std::uint8_t bitmap_value(const FT_Bitmap& bitmap, int x, int y) {
  if (x < 0 || y < 0 || x >= static_cast<int>(bitmap.width) || y >= static_cast<int>(bitmap.rows)) return 0;
  const int source_y = bitmap.pitch >= 0 ? y : static_cast<int>(bitmap.rows) - 1 - y;
  const auto* row = bitmap.buffer + source_y * std::abs(bitmap.pitch);
  if (bitmap.pixel_mode == FT_PIXEL_MODE_GRAY) return row[x];
  if (bitmap.pixel_mode == FT_PIXEL_MODE_MONO) return (row[x / 8] & (0x80 >> (x & 7))) != 0 ? 255 : 0;
  if (bitmap.pixel_mode == FT_PIXEL_MODE_BGRA) return row[x * 4 + 3];
  return 0;
}

double resized_coverage(const std::vector<std::uint8_t>& source, int source_width, int source_height,
                        int output_width, int output_height, int output_x, int output_y) {
  const double x0 = static_cast<double>(output_x) * source_width / output_width;
  const double x1 = static_cast<double>(output_x + 1) * source_width / output_width;
  const double y0 = static_cast<double>(output_y) * source_height / output_height;
  const double y1 = static_cast<double>(output_y + 1) * source_height / output_height;
  double sum = 0.0;
  double area = 0.0;
  for (int y = static_cast<int>(y0); y < static_cast<int>(y1 + 0.999999); ++y) {
    if (y < 0 || y >= source_height) continue;
    const double yw = std::max(0.0, std::min(y1, static_cast<double>(y + 1)) - std::max(y0, static_cast<double>(y)));
    for (int x = static_cast<int>(x0); x < static_cast<int>(x1 + 0.999999); ++x) {
      if (x < 0 || x >= source_width) continue;
      const double xw = std::max(0.0, std::min(x1, static_cast<double>(x + 1)) - std::max(x0, static_cast<double>(x)));
      const double weight = xw * yw;
      sum += source[static_cast<std::size_t>(y) * source_width + x] * weight;
      area += weight;
    }
  }
  return area == 0.0 ? 0.0 : sum / area;
}

std::vector<GlyphBitmap> render_glyphs(FT_Face face, const Options& options,
                                       const std::vector<std::uint16_t>& requested) {
  if (FT_Set_Pixel_Sizes(face, 0, static_cast<FT_UInt>(options.point_size)) != 0) {
    int closest = -1;
    int closest_distance = std::numeric_limits<int>::max();
    for (int index = 0; index < face->num_fixed_sizes; ++index) {
      const int distance = std::abs(face->available_sizes[index].height - options.point_size);
      if (distance < closest_distance) {
        closest = index;
        closest_distance = distance;
      }
    }
    if (closest < 0 || FT_Select_Size(face, closest) != 0) {
      throw std::runtime_error("FreeType cannot select the requested pixel size");
    }
  }

  std::vector<std::uint16_t> available;
  std::vector<std::uint16_t> missing;
  std::vector<std::uint16_t> unloadable;
  int left = std::numeric_limits<int>::max();
  int right = std::numeric_limits<int>::min();
  int top = 0;
  int bottom = 0;
  for (const std::uint16_t codepoint : requested) {
    if (FT_Get_Char_Index(face, codepoint) == 0) {
      missing.push_back(codepoint);
      continue;
    }
    if (FT_Load_Char(face, codepoint, FT_LOAD_RENDER) != 0) {
      unloadable.push_back(codepoint);
      continue;
    }
    available.push_back(codepoint);
    const FT_GlyphSlot glyph = face->glyph;
    left = std::min(left, glyph->bitmap_left);
    right = std::max(right, glyph->bitmap_left + static_cast<int>(glyph->bitmap.width));
    top = std::max(top, glyph->bitmap_top);
    bottom = std::max(bottom, static_cast<int>(glyph->bitmap.rows) - glyph->bitmap_top);
  }
  auto warn_skipped = [](const char* reason, const std::vector<std::uint16_t>& codepoints) {
    if (codepoints.empty()) return;
    std::fprintf(stderr, "warning: %s %zu requested character%s:", reason, codepoints.size(),
                 codepoints.size() == 1 ? "" : "s");
    const std::size_t shown = std::min<std::size_t>(codepoints.size(), 12);
    for (std::size_t i = 0; i < shown; ++i) std::fprintf(stderr, " U+%04X", codepoints[i]);
    if (shown < codepoints.size()) std::fprintf(stderr, " ...");
    std::fputc('\n', stderr);
  };
  warn_skipped("font is missing", missing);
  warn_skipped("FreeType could not rasterize", unloadable);
  if (available.empty()) throw std::runtime_error("the font contains none of the requested characters");
  if (left == std::numeric_limits<int>::max()) left = 0;
  if (right <= left) right = left + 1;
  if (top + bottom <= 0) bottom = 1;
  const int source_width = right - left;
  const int source_height = top + bottom;
  double output_threshold = options.threshold;
  if (!options.threshold_explicit) {
    // Растр FreeType по умолчанию намеренно строится с избыточной выборкой
    // (обычно с высотой в 4 раза больше ячейки). Фиксированный порог площади 50%
    // стирает штрихи тоньше половины выходного пикселя. Компенсируем наибольшим
    // линейным уменьшением, чтобы штрих в один исходный пиксель сохранился,
    // а явный --threshold по-прежнему имел точный прежний смысл.
    const double downscale_x = static_cast<double>(source_width) / options.width;
    const double downscale_y = static_cast<double>(source_height) / options.height;
    // Обычный растр по умолчанию в 4 раза выше целевого. Ограничиваем компенсацию
    // этим коэффициентом, чтобы необычно большой --size или один выбивающийся
    // глиф не делал все остальные глифы всё жирнее.
    const double linear_downscale = std::min(4.0, std::max({1.0, downscale_x, downscale_y}));
    output_threshold = std::max(1.0, output_threshold / linear_downscale);
  }

  std::vector<GlyphBitmap> result;
  for (const std::uint16_t codepoint : available) {
    if (FT_Load_Char(face, codepoint, FT_LOAD_RENDER) != 0) continue;
    const FT_GlyphSlot glyph = face->glyph;
    std::vector<std::uint8_t> source(static_cast<std::size_t>(source_width) * source_height, 0);
    const int target_x = glyph->bitmap_left - left;
    const int target_y = top - glyph->bitmap_top;
    for (int y = 0; y < static_cast<int>(glyph->bitmap.rows); ++y) {
      for (int x = 0; x < static_cast<int>(glyph->bitmap.width); ++x) {
        const int destination_x = target_x + x;
        const int destination_y = target_y + y;
        if (destination_x >= 0 && destination_x < source_width && destination_y >= 0 && destination_y < source_height) {
          source[static_cast<std::size_t>(destination_y) * source_width + destination_x] = bitmap_value(glyph->bitmap, x, y);
        }
      }
    }

    std::vector<std::uint8_t> pixels(static_cast<std::size_t>(options.width) * options.height);
    for (int y = 0; y < options.height; ++y) {
      for (int x = 0; x < options.width; ++x) {
        pixels[static_cast<std::size_t>(y) * options.width + x] =
            resized_coverage(source, source_width, source_height, options.width, options.height, x, y) >= output_threshold;
      }
    }
    if (codepoint != 0x20 && codepoint != 0xA0 &&
        std::none_of(pixels.begin(), pixels.end(), [](std::uint8_t pixel) { return pixel != 0; })) {
      std::fprintf(stderr,
                   "warning: U+%04X rasterized empty; try a lower --threshold or a larger --cell\n",
                   codepoint);
    }

    int glyph_width = options.width;
    int advance = std::min(16, options.width + 1);
    if (options.proportional) {
      int first = options.width;
      int last = -1;
      for (int x = 0; x < options.width; ++x) {
        for (int y = 0; y < options.height; ++y) {
          if (pixels[static_cast<std::size_t>(y) * options.width + x] != 0) {
            first = std::min(first, x);
            last = std::max(last, x);
          }
        }
      }
      if (last >= first) {
        glyph_width = last - first + 1;
        std::vector<std::uint8_t> cropped;
        cropped.reserve(static_cast<std::size_t>(glyph_width) * options.height);
        for (int y = 0; y < options.height; ++y) {
          for (int x = first; x <= last; ++x) cropped.push_back(pixels[static_cast<std::size_t>(y) * options.width + x]);
        }
        pixels = std::move(cropped);
      } else {
        glyph_width = std::max(1, options.width / 2);
        pixels.assign(static_cast<std::size_t>(glyph_width) * options.height, 0);
      }
      advance = std::min(16, glyph_width + 1);
    }
    result.push_back({codepoint, static_cast<std::uint8_t>(glyph_width), static_cast<std::uint8_t>(advance), std::move(pixels)});
  }
  return result;
}

std::pair<int, std::vector<Choice>> optimal_rle(const std::vector<std::uint8_t>& bits) {
  const std::size_t count = bits.size();
  std::vector<int> costs(count + 1, 0);
  std::vector<Choice> choices(count);
  for (std::size_t reverse = count; reverse-- > 0;) {
    int best_cost = std::numeric_limits<int>::max();
    Choice best;
    for (std::size_t length = 1; length <= std::min<std::size_t>(16, count - reverse); ++length) {
      const int cost = 5 + static_cast<int>(length) + costs[reverse + length];
      if (cost < best_cost) { best_cost = cost; best = {false, static_cast<std::uint8_t>(length)}; }
    }
    std::size_t run = 1;
    while (run < std::min<std::size_t>(33, count - reverse) && bits[reverse + run] == bits[reverse]) ++run;
    for (std::size_t length = 2; length <= run; ++length) {
      const int cost = 7 + costs[reverse + length];
      if (cost < best_cost) { best_cost = cost; best = {true, static_cast<std::uint8_t>(length)}; }
    }
    costs[reverse] = best_cost;
    choices[reverse] = best;
  }
  return {costs[0], std::move(choices)};
}

bool write_bitmap(BitWriter& writer, const std::vector<std::uint8_t>& bits, Compression compression) {
  const auto [rle_size, choices] = optimal_rle(bits);
  const bool compressed = compression == Compression::RLE ||
      (compression == Compression::AUTO && rle_size < static_cast<int>(bits.size()));
  writer.write(compressed ? 1 : 0, 1);
  if (!compressed) {
    for (const auto pixel : bits) writer.write(pixel, 1);
    return false;
  }

  for (std::size_t position = 0; position < bits.size();) {
    const Choice choice = choices[position];
    writer.write(choice.run ? 1 : 0, 1);
    if (choice.run) {
      writer.write(choice.length - 2, 5);
      writer.write(bits[position], 1);
    } else {
      writer.write(choice.length - 1, 4);
      for (std::size_t i = 0; i < choice.length; ++i) writer.write(bits[position + i], 1);
    }
    position += choice.length;
  }
  return true;
}

std::uint16_t crc16(const std::vector<std::uint8_t>& data) {
  std::uint16_t crc = 0xFFFF;
  for (std::size_t index = 0; index < data.size(); ++index) {
    const std::uint8_t value = index == 14 || index == 15 ? 0 : data[index];
    crc ^= static_cast<std::uint16_t>(value) << 8;
    for (int bit = 0; bit < 8; ++bit) crc = (crc & 0x8000) != 0 ? static_cast<std::uint16_t>((crc << 1) ^ 0x1021) : static_cast<std::uint16_t>(crc << 1);
  }
  return crc;
}

void put_le16(std::vector<std::uint8_t>& output, std::size_t offset, std::uint16_t value) {
  output[offset] = static_cast<std::uint8_t>(value);
  output[offset + 1] = static_cast<std::uint8_t>(value >> 8);
}

std::vector<std::pair<std::uint16_t, std::uint16_t>> make_ranges(const std::vector<GlyphBitmap>& glyphs) {
  std::vector<std::pair<std::uint16_t, std::uint16_t>> ranges;
  std::uint16_t start = glyphs.front().codepoint;
  std::uint16_t previous = start;
  std::uint16_t count = 1;
  for (std::size_t index = 1; index < glyphs.size(); ++index) {
    if (glyphs[index].codepoint == previous + 1 && count < 256) ++count;
    else { ranges.push_back({start, count}); start = glyphs[index].codepoint; count = 1; }
    previous = glyphs[index].codepoint;
  }
  ranges.push_back({start, count});
  if (ranges.size() > 255) throw std::runtime_error("FMK1 v1 supports at most 255 codepoint ranges");
  return ranges;
}

std::vector<std::uint8_t> encode_font(std::vector<GlyphBitmap> glyphs, const Options& options,
                                      int& raw_count, int& rle_count) {
  std::sort(glyphs.begin(), glyphs.end(), [](const auto& left, const auto& right) { return left.codepoint < right.codepoint; });
  const auto ranges = make_ranges(glyphs);
  std::vector<std::uint8_t> prefix(HEADER_SIZE, 0);
  std::memcpy(prefix.data(), "FMK1", 4);
  prefix[4] = options.proportional ? 0 : FLAG_MONOSPACED;
  prefix[5] = static_cast<std::uint8_t>(options.width);
  prefix[6] = static_cast<std::uint8_t>(options.height);
  prefix[7] = static_cast<std::uint8_t>(((std::min(16, options.width + 1) - 1) << 4) | options.line_gap);
  put_le16(prefix, 8, static_cast<std::uint16_t>(glyphs.size()));
  prefix[10] = static_cast<std::uint8_t>(ranges.size());
  for (const auto [start, count] : ranges) {
    prefix.push_back(static_cast<std::uint8_t>(start));
    prefix.push_back(static_cast<std::uint8_t>(start >> 8));
    prefix.push_back(static_cast<std::uint8_t>(count - 1));
  }

  BitWriter writer(std::move(prefix));
  raw_count = 0;
  rle_count = 0;
  for (const auto& glyph : glyphs) {
    if (options.proportional) {
      writer.write(glyph.width - 1, 4);
      writer.write(glyph.advance - 1, 4);
    }
    if (write_bitmap(writer, glyph.bits, options.compression)) ++rle_count;
    else ++raw_count;
  }
  if (writer.data.size() > MAX_FILE_SIZE) throw std::runtime_error("encoded font exceeds the 1536-byte firmware limit");
  put_le16(writer.data, 12, static_cast<std::uint16_t>(writer.data.size()));
  put_le16(writer.data, 14, crc16(writer.data));
  return writer.data;
}

void write_file(const std::string& path, const std::vector<std::uint8_t>& data) {
  std::ofstream output(path, std::ios::binary);
  if (!output) throw std::runtime_error("cannot open output file");
  output.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
  if (!output) throw std::runtime_error("cannot write output file");
}

}  // безымянное пространство имён

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    const std::vector<std::uint16_t> codepoints = character_set(options.characters);
    FreeTypeLibrary library;
    FreeTypeFace face(library, options.input);
    const std::vector<GlyphBitmap> glyphs = render_glyphs(face, options, codepoints);
    int raw_count = 0;
    int rle_count = 0;
    const std::vector<std::uint8_t> encoded = encode_font(glyphs, options, raw_count, rle_count);
    write_file(options.output, encoded);
    std::printf("%s: %zu bytes, %zu glyphs, %s %dx%d, raw=%d, rle=%d, source=%s\n",
        options.output.c_str(), encoded.size(), glyphs.size(), options.proportional ? "proportional" : "mono",
        options.width, options.height, raw_count, rle_count, face->family_name != nullptr ? face->family_name : "unknown");
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "fmk_font: %s\n", error.what());
    return 1;
  }
}
