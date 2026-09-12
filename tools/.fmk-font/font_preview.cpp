// Host-only, native monochrome FreeType atlas for choosing UI font sizes.
// No resampling, synthetic styles, firmware dependencies, or font fallback.
#include <ft2build.h>
#include FT_FREETYPE_H

#ifdef FONT_PREVIEW_BUILTIN
#include "builtin_font.hpp"
#endif

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

struct Library {
  FT_Library value = nullptr;
  Library() {
    if (FT_Init_FreeType(&value) != 0) throw std::runtime_error("cannot initialize FreeType");
  }
  ~Library() { FT_Done_FreeType(value); }
  Library(const Library&) = delete;
  Library& operator=(const Library&) = delete;
};

struct Face {
  FT_Face value = nullptr;
  Face(FT_Library library, const char* path) {
    if (FT_New_Face(library, path, 0, &value) != 0) {
      throw std::runtime_error("cannot open input font");
    }
  }
  ~Face() { FT_Done_Face(value); }
  Face(const Face&) = delete;
  Face& operator=(const Face&) = delete;
};

struct Glyph {
  std::uint32_t codepoint = 0;
  int width = 0;
  int height = 0;
  int bearing_x = 0;
  int bearing_y = 0;
  int safe_bearing_x = 0;
  int native_advance = 0;
  int advance = 0;
  std::vector<std::string> rows;
};

struct Atlas {
  int ppem = 0;
  int ascent = 0;
  int descent = 0;
  std::vector<Glyph> glyphs;
  std::vector<std::uint32_t> missing;
  std::vector<int> rejected_ppem;
};

struct RasterError : std::runtime_error {
  using std::runtime_error::runtime_error;
};

enum class InputEncoding { UNICODE, CP1251 };

constexpr std::uint32_t NO_CHARCODE = 0xffffffffU;

std::uint32_t input_charcode(std::uint32_t codepoint, InputEncoding encoding) {
  if (encoding == InputEncoding::UNICODE) return codepoint;
  if (codepoint >= 0x20U && codepoint <= 0x7eU) return codepoint;
  if (codepoint >= 0x410U && codepoint <= 0x44fU) return codepoint - 0x410U + 0xc0U;
  if (codepoint == 0xb0U) return 0xb0U;
  // RAWIN Crox declares duplicate 0xa8/0xb8 encodings for unrelated Latin
  // glyphs and contains no dedicated Ё/ё bitmaps. Treat them as missing so a
  // deliberate fallback can supply them instead of silently drawing garbage.
  return NO_CHARCODE;
}

std::vector<std::uint32_t> requested_characters() {
  std::vector<std::uint32_t> characters;
  for (std::uint32_t cp = 0x20; cp <= 0x7e; ++cp) characters.push_back(cp);
  for (std::uint32_t cp = 0x410; cp <= 0x44f; ++cp) characters.push_back(cp);
  for (const std::uint32_t cp : {0x401U, 0x451U, 0xb0U, 0x2190U, 0x2191U,
                               0x2192U, 0x2193U, 0x2026U, 0x2264U, 0x2265U}) {
    characters.push_back(cp);
  }
  std::sort(characters.begin(), characters.end());
  return characters;
}

// Grid-fitted monochrome advances normally already are integral pixels. Keep
// rounding explicit for faces whose advance still contains a fractional part.
int round_26_6(FT_Pos value) {
  if (value < 0 || value > 64L * 4096L) {
    throw std::runtime_error("unsupported glyph advance");
  }
  return static_cast<int>((value + 32) / 64);
}

void trim_empty_bitmap_border(Glyph& glyph) {
  int left = glyph.width;
  int right = -1;
  int top = glyph.height;
  int bottom = -1;
  for (int y = 0; y < glyph.height; ++y) {
    for (int x = 0; x < glyph.width; ++x) {
      if (glyph.rows[static_cast<std::size_t>(y)][static_cast<std::size_t>(x)] != '1') continue;
      left = std::min(left, x);
      right = std::max(right, x);
      top = std::min(top, y);
      bottom = std::max(bottom, y);
    }
  }
  if (right < left || bottom < top) {
    // Keep a single zero bit so firmware records never need a special empty
    // bitmap representation. The source advance remains authoritative.
    glyph.width = glyph.height = 1;
    glyph.bearing_x = 0;
    glyph.bearing_y = 1;
    glyph.rows.assign(1, "0");
    return;
  }
  std::vector<std::string> cropped;
  cropped.reserve(static_cast<std::size_t>(bottom - top + 1));
  for (int y = top; y <= bottom; ++y) {
    cropped.push_back(glyph.rows[static_cast<std::size_t>(y)].substr(
        static_cast<std::size_t>(left), static_cast<std::size_t>(right - left + 1)));
  }
  glyph.bearing_x += left;
  glyph.bearing_y -= top;
  glyph.width = right - left + 1;
  glyph.height = bottom - top + 1;
  glyph.rows = std::move(cropped);
}

Atlas rasterize_selected(FT_Face face, int ppem,
                         const std::vector<std::uint32_t>& characters,
                         InputEncoding encoding, bool trim_bitmap,
                         bool capture_rows = true) {
  Atlas atlas;
  atlas.ppem = ppem;
  for (const std::uint32_t cp : characters) {
    const std::uint32_t charcode = input_charcode(cp, encoding);
    const FT_UInt index = charcode == NO_CHARCODE ? 0 : FT_Get_Char_Index(face, charcode);
    if (index == 0) {
      atlas.missing.push_back(cp);
      continue;
    }
    const FT_Error load_error = FT_Load_Glyph(face, index, FT_LOAD_RENDER | FT_LOAD_TARGET_MONO);
    if (load_error != 0) {
      throw RasterError("cannot render codepoint " + std::to_string(cp) +
          " at ppem " + std::to_string(ppem) + " (FreeType " + std::to_string(load_error) + ")");
    }
    const FT_GlyphSlot slot = face->glyph;
    const FT_Bitmap& bitmap = slot->bitmap;
    if (bitmap.width > 4096 || bitmap.rows > 4096 ||
        (bitmap.width != 0 && bitmap.rows != 0 && bitmap.pixel_mode != FT_PIXEL_MODE_MONO)) {
      throw std::runtime_error("expected a bounded monochrome glyph bitmap");
    }
    Glyph glyph;
    glyph.codepoint = cp;
    glyph.width = static_cast<int>(bitmap.width);
    glyph.height = static_cast<int>(bitmap.rows);
    glyph.bearing_x = slot->bitmap_left;
    glyph.bearing_y = slot->bitmap_top;
    glyph.native_advance = round_26_6(slot->advance.x);
    const auto pitch = static_cast<std::ptrdiff_t>(bitmap.pitch);
    const std::size_t stride = static_cast<std::size_t>(pitch < 0 ? -pitch : pitch);
    if (stride < (static_cast<std::size_t>(glyph.width) + 7U) / 8U ||
        (glyph.width != 0 && glyph.height != 0 && bitmap.buffer == nullptr)) {
      throw std::runtime_error("invalid monochrome bitmap storage");
    }
    for (int y = 0; (capture_rows || trim_bitmap) && y < glyph.height; ++y) {
      std::string row(static_cast<std::size_t>(glyph.width), '0');
      // FreeType pitch is the signed offset for stepping DOWN one row, even
      // for an upward-flow bitmap whose first row lives at a higher address.
      const auto offset = static_cast<std::ptrdiff_t>(y) * pitch;
      for (int x = 0; x < glyph.width; ++x) {
        const auto byte = offset + static_cast<std::ptrdiff_t>(x / 8);
        if ((bitmap.buffer[byte] & (0x80U >> (static_cast<unsigned>(x) & 7U))) != 0) {
          row[static_cast<std::size_t>(x)] = '1';
        }
      }
      glyph.rows.push_back(std::move(row));
    }
    if (trim_bitmap) trim_empty_bitmap_border(glyph);
    if (!capture_rows) glyph.rows.clear();
    // Shift a negative left overhang inside its own pen interval. Preserve a
    // positive left bearing. Do this after optional cropping: bearings and
    // the envelope must describe visible pixels, not a BDF-wide padded box.
    const int shift = std::max(0, -glyph.bearing_x);
    glyph.safe_bearing_x = glyph.bearing_x + shift;
    glyph.advance = std::max(1, glyph.native_advance + shift);
    if (glyph.width != 0 && glyph.height != 0) {
      glyph.advance = std::max(glyph.advance, glyph.safe_bearing_x + glyph.width + 1);
      atlas.ascent = std::max(atlas.ascent, glyph.bearing_y);
      atlas.descent = std::max(atlas.descent, glyph.height - glyph.bearing_y);
    }
    atlas.glyphs.push_back(std::move(glyph));
  }
  return atlas;
}

Atlas rasterize_scalable(FT_Face face, int ppem,
                         const std::vector<std::uint32_t>& characters,
                         InputEncoding encoding, bool capture_rows = true) {
  if (FT_Set_Pixel_Sizes(face, 0, static_cast<FT_UInt>(ppem)) != 0) {
    throw RasterError("cannot select native pixel size " + std::to_string(ppem));
  }
  return rasterize_selected(face, ppem, characters, encoding, false, capture_rows);
}

Atlas rasterize_strike(FT_Face face, int strike,
                       const std::vector<std::uint32_t>& characters,
                       InputEncoding encoding, bool capture_rows = true) {
  if (strike < 0 || strike >= face->num_fixed_sizes || FT_Select_Size(face, strike) != 0) {
    throw RasterError("cannot select bitmap strike " + std::to_string(strike));
  }
  const FT_Pos y_ppem = face->available_sizes[strike].y_ppem;
  const int ppem = y_ppem > 0 ? round_26_6(y_ppem) : face->available_sizes[strike].height;
  return rasterize_selected(face, ppem, characters, encoding, true, capture_rows);
}

#ifdef FONT_PREVIEW_BUILTIN
Atlas rasterize_builtin() {
  Atlas atlas;
  atlas.ascent = 8;
  for (const auto cp : requested_characters()) {
    builtin_font::Raster raster = {};
    if (!builtin_font::decode(builtin_font::FaceId::FONT_5X8,
                              static_cast<std::uint16_t>(cp), raster)) {
      atlas.missing.push_back(cp);
      continue;
    }
    Glyph glyph;
    glyph.codepoint = cp;
    glyph.width = raster.width;
    glyph.height = raster.height;
    glyph.bearing_y = 8;
    glyph.native_advance = 6;
    glyph.advance = 6;
    const std::size_t stride = (static_cast<std::size_t>(raster.width) + 7U) / 8U;
    for (int y = 0; y < glyph.height; ++y) {
      std::string row(static_cast<std::size_t>(glyph.width), '0');
      for (int x = 0; x < glyph.width; ++x) {
        const std::size_t byte = static_cast<std::size_t>(y) * stride +
                                 static_cast<std::size_t>(x / 8);
        if ((raster.data[byte] & (0x80U >> (static_cast<unsigned>(x) & 7U))) != 0) {
          row[static_cast<std::size_t>(x)] = '1';
        }
      }
      glyph.rows.push_back(std::move(row));
    }
    atlas.glyphs.push_back(std::move(glyph));
  }
  return atlas;
}
#endif

void validate(const Atlas& atlas, int target_height) {
  if (atlas.glyphs.empty() || atlas.ascent + atlas.descent < 1 ||
      atlas.ascent + atlas.descent > target_height) {
    throw std::runtime_error("invalid atlas envelope");
  }
  for (const auto& glyph : atlas.glyphs) {
    if (glyph.rows.size() != static_cast<std::size_t>(glyph.height)) {
      throw std::runtime_error("inconsistent glyph row count");
    }
    for (const auto& row : glyph.rows) {
      if (row.size() != static_cast<std::size_t>(glyph.width) ||
          row.find_first_not_of("01") != std::string::npos) {
        throw std::runtime_error("invalid glyph bitmap row");
      }
    }
    if (glyph.advance < 1 || glyph.safe_bearing_x < 0) {
      throw std::runtime_error("invalid pen interval");
    }
    if (glyph.width == 0 || glyph.height == 0) continue;
    if (glyph.bearing_y > atlas.ascent || glyph.height - glyph.bearing_y > atlas.descent) {
      throw std::runtime_error("glyph clipped by atlas envelope");
    }
    for (const auto& next : atlas.glyphs) {
      if (next.width == 0 || next.height == 0) continue;
      const int gap = glyph.advance + next.safe_bearing_x -
                      (glyph.safe_bearing_x + glyph.width);
      if (gap < 1) throw std::runtime_error("safe advances let adjacent glyphs touch");
    }
  }
}

void json_string(std::ostream& out, const std::string& value) {
  constexpr char hex[] = "0123456789abcdef";
  out << '"';
  for (const char byte : value) {
    const auto c = static_cast<unsigned char>(byte);
    if (c == '"' || c == '\\') out << '\\' << static_cast<char>(c);
    else if (c < 0x20) out << "\\u00" << hex[c >> 4] << hex[c & 15];
    else out << static_cast<char>(c);
  }
  out << '"';
}

void write_json(const char* path, const std::string& family, const std::string& style,
                const std::string& rasterizer, const Atlas& atlas, int target_height) {
  std::ofstream out(path, std::ios::out | std::ios::trunc);
  if (!out) throw std::runtime_error("cannot open output JSON");
  out << "{\n  \"schema\": 1,\n  \"family\": ";
  json_string(out, family);
  out << ",\n  \"style\": ";
  json_string(out, style);
  out << ",\n  \"rasterizer\": ";
  json_string(out, rasterizer);
  out << ",\n  \"target_height\": " << target_height
      << ",\n  \"ppem\": " << atlas.ppem
      << ",\n  \"ascent\": " << atlas.ascent
      << ",\n  \"descent\": " << atlas.descent
      << ",\n  \"height\": " << atlas.ascent + atlas.descent
      << ",\n  \"spacing\": \"safe_bearing_x + advance; at least one blank column; no kerning\","
      << "\n  \"rejected_ppem\": [";
  for (std::size_t i = 0; i < atlas.rejected_ppem.size(); ++i) {
    if (i != 0) out << ',';
    out << atlas.rejected_ppem[i];
  }
  out << "],\n  \"missing\": [";
  for (std::size_t i = 0; i < atlas.missing.size(); ++i) {
    if (i != 0) out << ',';
    out << atlas.missing[i];
  }
  out << "],\n  \"glyphs\": [\n";
  for (std::size_t i = 0; i < atlas.glyphs.size(); ++i) {
    const auto& glyph = atlas.glyphs[i];
    if (i != 0) out << ",\n";
    out << "    {\"codepoint\":" << glyph.codepoint
        << ",\"width\":" << glyph.width << ",\"height\":" << glyph.height
        << ",\"bearing_x\":" << glyph.bearing_x << ",\"bearing_y\":" << glyph.bearing_y
        << ",\"safe_bearing_x\":" << glyph.safe_bearing_x
        << ",\"native_advance\":" << glyph.native_advance
        << ",\"advance\":" << glyph.advance << ",\"rows\":[";
    for (std::size_t y = 0; y < glyph.rows.size(); ++y) {
      if (y != 0) out << ',';
      json_string(out, glyph.rows[y]);
    }
    out << "]}";
  }
  out << "\n  ]\n}\n";
  out.close();
  if (!out) throw std::runtime_error("cannot write output JSON");
}

} // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--help") {
      std::cout << "usage: font_preview INPUT OUTPUT.json --height N"
                   " [--encoding unicode|cp1251]\n"
                   "       font_preview --builtin OUTPUT.json (FONT_PREVIEW_BUILTIN build)\n"
                   "INPUT may be scalable or a native bitmap font. N is the full\n"
                   "glyph envelope (7..20 pixels), not point size. Bitmap strikes\n"
                   "are never scaled; empty BDF padding is cropped.\n";
      return 0;
    }
#ifdef FONT_PREVIEW_BUILTIN
    if (argc == 3 && std::string(argv[1]) == "--builtin") {
      const Atlas atlas = rasterize_builtin();
      validate(atlas, 8);
      write_json(argv[2], "MK61 builtin", "FONT_5X8", "builtin_font::decode",
                 atlas, 8);
      std::cout << "builtin=FONT_5X8 glyphs=" << atlas.glyphs.size()
                << " missing=" << atlas.missing.size() << " spacing=verified\n";
      return 0;
    }
#endif
    if ((argc != 5 && argc != 7) || std::string(argv[3]) != "--height" ||
        (argc == 7 && std::string(argv[5]) != "--encoding")) {
      throw std::runtime_error(
          "usage: font_preview INPUT OUTPUT.json --height N [--encoding unicode|cp1251]");
    }
    std::size_t parsed = 0;
    const std::string height_text = argv[4];
    const int target_height = std::stoi(height_text, &parsed);
    if (parsed != height_text.size() || target_height < 7 || target_height > 20) {
      throw std::runtime_error("height must be an integer from 7 through 20");
    }
    InputEncoding encoding = InputEncoding::UNICODE;
    if (argc == 7) {
      const std::string value = argv[6];
      if (value == "cp1251") encoding = InputEncoding::CP1251;
      else if (value != "unicode") throw std::runtime_error("encoding must be unicode or cp1251");
    }
    Library library;
    Face font(library.value, argv[1]);
    if (encoding == InputEncoding::UNICODE) {
      if (FT_Select_Charmap(font.value, FT_ENCODING_UNICODE) != 0) {
        throw std::runtime_error("font has no Unicode character map");
      }
    } else if (font.value->charmap == nullptr && font.value->num_charmaps > 0 &&
               FT_Set_Charmap(font.value, font.value->charmaps[0]) != 0) {
      throw std::runtime_error("cannot select raw CP1251 character map");
    }
    const auto characters = requested_characters();
    Atlas best;
    std::vector<int> rejected_ppem;
    int best_strike = -1;
    std::string rasterizer;
    if (FT_IS_SCALABLE(font.value)) {
      // Enumerate integer sizes because hinted ink heights need not grow by one
      // every ppem. A deliberately generous bound is checked, never accepted as
      // an artificial maximum for an unusual face with very small glyphs.
      const int search_limit = target_height * 16;
      for (int ppem = 1; ppem <= search_limit; ++ppem) {
        try {
          Atlas candidate = rasterize_scalable(font.value, ppem, characters, encoding, false);
          const int ink_height = candidate.ascent + candidate.descent;
          if (ink_height > 0 && ink_height <= target_height) best = std::move(candidate);
        } catch (const RasterError& error) {
          rejected_ppem.push_back(ppem);
          std::cerr << "skipping unsupported size: " << error.what() << '\n';
        }
      }
      if (best.ppem == 0) throw std::runtime_error("no native integer size fits requested height");
      if (best.ppem == search_limit) throw std::runtime_error("font exceeds bounded size search");
      best = rasterize_scalable(font.value, best.ppem, characters, encoding);
      rasterizer = "FreeType native FT_LOAD_TARGET_MONO";
    } else {
      for (int strike = 0; strike < font.value->num_fixed_sizes; ++strike) {
        Atlas candidate = rasterize_strike(font.value, strike, characters, encoding, false);
        const int ink_height = candidate.ascent + candidate.descent;
        if (ink_height > 0 && ink_height <= target_height &&
            (best_strike < 0 || ink_height > best.ascent + best.descent)) {
          best = std::move(candidate);
          best_strike = strike;
        }
      }
      if (best_strike < 0) {
        throw std::runtime_error("no unscaled bitmap strike fits requested height");
      }
      best = rasterize_strike(font.value, best_strike, characters, encoding);
      rasterizer = "FreeType native bitmap strike; empty border cropped";
    }
    best.rejected_ppem = std::move(rejected_ppem);
    validate(best, target_height);
    write_json(argv[2], font.value->family_name == nullptr ? "" : font.value->family_name,
               font.value->style_name == nullptr ? "" : font.value->style_name,
               rasterizer, best, target_height);
    std::cout << "ppem=" << best.ppem << " ink=" << best.ascent << '+' << best.descent
              << " glyphs=" << best.glyphs.size() << " missing=" << best.missing.size()
              << " spacing=verified\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "font_preview: " << error.what() << '\n';
    return 1;
  }
}
